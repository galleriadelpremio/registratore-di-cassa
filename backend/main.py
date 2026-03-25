import asyncio
import os
from datetime import datetime, timezone, timedelta, date
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import get_db, init_db, Utente, Prodotto, Incasso, ContatoreRicevute
from auth import verifica_password, hash_password, crea_token, get_utente_corrente, richiedi_admin
from ricevuta import genera_ricevuta_pdf
from modulo_excel import genera_modulo_excel

app = FastAPI(title="Galleria del Premio — Registro Corrispettivi")
scheduler = AsyncIOScheduler(timezone="Europe/Rome")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

TZ_IT = timezone(timedelta(hours=1))

def ora_italia():
    return datetime.now(TZ_IT).replace(tzinfo=None)

MESI_IT = ["","Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno",
           "Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"]

# ─── SCHEDULER ───────────────────────────────────────────────────────────────

async def task_report_giornaliero():
    from email_report import invia_report_giornaliero
    db = next(get_db())
    try:
        await invia_report_giornaliero(db)
    finally:
        db.close()

async def task_report_mensile():
    from email_report import invia_report_mensile
    oggi = date.today()
    db = next(get_db())
    try:
        await invia_report_mensile(db, oggi.month, oggi.year)
    finally:
        db.close()

# ─── STARTUP / SHUTDOWN ──────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    init_db()
    db = next(get_db())
    if not db.query(Utente).first():
        db.add(Utente(username="admin", nome="Amministratore", password_hash=hash_password("galleria2025"), ruolo="admin"))
        db.commit()
    if not db.query(Prodotto).first():
        db.add(Prodotto(nome="Biglietto singolo", descrizione="Ingresso standard alla galleria", prezzo=3.00))
        db.add(Prodotto(nome="Tessera fedeltà", descrizione="Abbonamento annuale", prezzo=30.00))
        db.commit()
    db.close()
    scheduler.add_job(task_report_giornaliero, CronTrigger(hour=18, minute=0, timezone="Europe/Rome"), id="report_giornaliero", replace_existing=True)
    scheduler.add_job(task_report_mensile, CronTrigger(day="last", hour=18, minute=0, timezone="Europe/Rome"), id="report_mensile", replace_existing=True)
    scheduler.start()

@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown()

# ─── PING ────────────────────────────────────────────────────────────────────

@app.get("/ping")
def ping():
    return {"ok": True}

# ─── AUTH ────────────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    utente = db.query(Utente).filter(Utente.username == form.username, Utente.attivo == True).first()
    if not utente or not verifica_password(form.password, utente.password_hash):
        raise HTTPException(status_code=401, detail="Credenziali non valide.")
    token = crea_token({"sub": utente.username})
    return {"access_token": token, "token_type": "bearer", "ruolo": utente.ruolo, "nome": utente.nome}

@app.get("/api/auth/me")
def me(utente: Utente = Depends(get_utente_corrente)):
    return {"username": utente.username, "nome": utente.nome, "ruolo": utente.ruolo}

# ─── PRODOTTI ────────────────────────────────────────────────────────────────

class ProdottoIn(BaseModel):
    nome: str
    descrizione: str = ""
    prezzo: float
    attivo: bool = True

@app.get("/api/prodotti")
def lista_prodotti(solo_attivi: bool = True, db: Session = Depends(get_db), _=Depends(get_utente_corrente)):
    q = db.query(Prodotto)
    if solo_attivi:
        q = q.filter(Prodotto.attivo == True)
    return q.order_by(Prodotto.id).all()

@app.post("/api/prodotti")
def crea_prodotto(data: ProdottoIn, db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    p = Prodotto(**data.dict())
    db.add(p); db.commit(); db.refresh(p)
    return p

@app.put("/api/prodotti/{pid}")
def aggiorna_prodotto(pid: int, data: ProdottoIn, db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    p = db.query(Prodotto).filter(Prodotto.id == pid).first()
    if not p: raise HTTPException(404, "Prodotto non trovato.")
    for k, v in data.dict().items(): setattr(p, k, v)
    db.commit(); db.refresh(p)
    return p

@app.delete("/api/prodotti/{pid}")
def disattiva_prodotto(pid: int, db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    p = db.query(Prodotto).filter(Prodotto.id == pid).first()
    if not p: raise HTTPException(404, "Prodotto non trovato.")
    p.attivo = False; db.commit()
    return {"ok": True}

# ─── INCASSI ─────────────────────────────────────────────────────────────────

class IncassoIn(BaseModel):
    prodotto_id: int
    quantita: int = 1
    modalita: str
    data: Optional[str] = None
    ricevuta_da: Optional[int] = None
    ricevuta_a: Optional[int] = None
    note: Optional[str] = ""

def prossimo_numero(db: Session, anno: int) -> int:
    contatore = db.query(ContatoreRicevute).filter(ContatoreRicevute.anno == anno).first()
    if not contatore:
        contatore = ContatoreRicevute(anno=anno, ultimo_numero=0)
        db.add(contatore)
    contatore.ultimo_numero += 1
    db.commit()
    return contatore.ultimo_numero

@app.post("/api/incassi")
def registra_incasso(data: IncassoIn, db: Session = Depends(get_db), utente: Utente = Depends(get_utente_corrente)):
    prodotto = db.query(Prodotto).filter(Prodotto.id == data.prodotto_id, Prodotto.attivo == True).first()
    if not prodotto: raise HTTPException(404, "Prodotto non trovato.")
    if data.modalita not in ("Contante", "POS"): raise HTTPException(400, "Modalità deve essere 'Contante' o 'POS'.")
    data_incasso = datetime.fromisoformat(data.data) if data.data else ora_italia()
    anno = data_incasso.year
    numero = prossimo_numero(db, anno)
    inc = Incasso(
        numero_ricevuta=numero, data=data_incasso,
        prodotto_id=prodotto.id, prodotto_nome=prodotto.nome, prodotto_prezzo=prodotto.prezzo,
        quantita=data.quantita, importo_totale=round(prodotto.prezzo * data.quantita, 2),
        modalita=data.modalita, ricevuta_da=data.ricevuta_da, ricevuta_a=data.ricevuta_a,
        note=data.note or "", operatore_id=utente.id, operatore_nome=utente.nome,
        anno=anno, mese=data_incasso.month,
    )
    db.add(inc); db.commit(); db.refresh(inc)
    return inc

@app.get("/api/incassi")
def lista_incassi(anno: Optional[int] = None, mese: Optional[int] = None, db: Session = Depends(get_db), _=Depends(get_utente_corrente)):
    q = db.query(Incasso)
    if anno: q = q.filter(Incasso.anno == anno)
    if mese: q = q.filter(Incasso.mese == mese)
    return q.order_by(Incasso.data.desc()).all()

@app.get("/api/incassi/{inc_id}/ricevuta")
def scarica_ricevuta(inc_id: int, db: Session = Depends(get_db), _=Depends(get_utente_corrente)):
    inc = db.query(Incasso).filter(Incasso.id == inc_id).first()
    if not inc: raise HTTPException(404, "Registrazione non trovata.")
    payload = {"numero_ricevuta": inc.numero_ricevuta, "anno": inc.anno, "data": inc.data.isoformat(),
               "prodotto_nome": inc.prodotto_nome, "quantita": inc.quantita, "importo_totale": inc.importo_totale,
               "modalita": inc.modalita, "note": inc.note, "operatore_nome": inc.operatore_nome}
    pdf = genera_ricevuta_pdf(payload)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=ricevuta_{inc.numero_ricevuta:04d}_{inc.anno}.pdf"})

@app.delete("/api/incassi/{inc_id}")
def elimina_incasso(inc_id: int, db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    inc = db.query(Incasso).filter(Incasso.id == inc_id).first()
    if not inc: raise HTTPException(404, "Registrazione non trovata.")
    db.delete(inc); db.commit()
    return {"ok": True}

class AggiornamentoData(BaseModel):
    data: str

@app.put("/api/incassi/{inc_id}/data")
def aggiorna_data_incasso(inc_id: int, body: AggiornamentoData, db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    inc = db.query(Incasso).filter(Incasso.id == inc_id).first()
    if not inc: raise HTTPException(404, "Registrazione non trovata.")
    try:
        nuova_data = datetime.fromisoformat(body.data)
    except ValueError:
        raise HTTPException(400, "Formato data non valido. Usa YYYY-MM-DD.")
    inc.data = nuova_data; inc.anno = nuova_data.year; inc.mese = nuova_data.month
    db.commit()
    return {"ok": True}

# ─── RIEPILOGO ───────────────────────────────────────────────────────────────

@app.get("/api/riepilogo")
def riepilogo(anno: int, mese: int, db: Session = Depends(get_db), _=Depends(get_utente_corrente)):
    incassi = db.query(Incasso).filter(Incasso.anno == anno, Incasso.mese == mese).order_by(Incasso.data).all()
    tot = sum(i.importo_totale for i in incassi)
    cash = sum(i.importo_totale for i in incassi if i.modalita == "Contante")
    pos = sum(i.importo_totale for i in incassi if i.modalita == "POS")
    return {"totale": tot, "contante": cash, "pos": pos, "righe": len(incassi)}

# ─── EXPORT EXCEL ────────────────────────────────────────────────────────────

@app.get("/api/export/excel")
def export_excel(anno: int, mese: int, db: Session = Depends(get_db), _=Depends(get_utente_corrente)):
    incassi = db.query(Incasso).filter(Incasso.anno == anno, Incasso.mese == mese).order_by(Incasso.data).all()
    if not incassi: raise HTTPException(404, "Nessun dato per il periodo selezionato.")
    payload = [{"data": i.data.isoformat(), "ricevuta_da": i.ricevuta_da, "ricevuta_a": i.ricevuta_a,
                "importo_totale": i.importo_totale, "modalita": i.modalita, "note": i.note} for i in incassi]
    xlsx = genera_modulo_excel(payload, mese, anno)
    return Response(content=xlsx, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=Corrispettivi_{MESI_IT[mese]}_{anno}.xlsx"})

# ─── UTENTI ──────────────────────────────────────────────────────────────────

class UtenteIn(BaseModel):
    username: str
    nome: str
    password: str
    ruolo: str = "operatore"

@app.get("/api/utenti")
def lista_utenti(db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    return db.query(Utente).filter(Utente.attivo == True).all()

@app.post("/api/utenti")
def crea_utente(data: UtenteIn, db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    if db.query(Utente).filter(Utente.username == data.username).first():
        raise HTTPException(400, "Username già esistente.")
    u = Utente(username=data.username, nome=data.nome, password_hash=hash_password(data.password), ruolo=data.ruolo)
    db.add(u); db.commit(); db.refresh(u)
    return {"id": u.id, "username": u.username, "nome": u.nome, "ruolo": u.ruolo}

class CambiaPassword(BaseModel):
    password_attuale: str
    nuova_password: str

@app.put("/api/utenti/me/password")
def cambia_password(data: CambiaPassword, db: Session = Depends(get_db), utente: Utente = Depends(get_utente_corrente)):
    if not verifica_password(data.password_attuale, utente.password_hash):
        raise HTTPException(400, "Password attuale non corretta.")
    utente.password_hash = hash_password(data.nuova_password); db.commit()
    return {"ok": True}

@app.delete("/api/utenti/{uid}")
def disattiva_utente(uid: int, db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    u = db.query(Utente).filter(Utente.id == uid).first()
    if not u: raise HTTPException(404)
    u.attivo = False; db.commit()
    return {"ok": True}

# ─── EMAIL REPORT ────────────────────────────────────────────────────────────

@app.post("/api/report/giornaliero")
async def trigger_report_giornaliero(db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    from email_report import invia_report_giornaliero
    ok = await invia_report_giornaliero(db)
    return {"ok": ok}

@app.post("/api/report/mensile")
async def trigger_report_mensile(anno: int = None, mese: int = None, db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    from email_report import invia_report_mensile
    oggi = date.today()
    ok = await invia_report_mensile(db, mese or oggi.month, anno or oggi.year)
    return {"ok": ok}

@app.post("/api/report/test")
async def test_email(_=Depends(richiedi_admin)):
    from email_report import invia_email
    ok = invia_email("Test configurazione email — Galleria del Premio",
                     "<div style='font-family:Arial;padding:20px'><h2>Email di test</h2><p>Configurazione corretta.</p></div>")
    return {"ok": ok}

# ─── FRONTEND ────────────────────────────────────────────────────────────────

frontend_path = os.path.join(os.path.dirname(__file__), "../frontend")
if os.path.exists(os.path.join(frontend_path, "static")):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_path, "static")), name="static")

import asyncio
import os
from datetime import datetime, timezone, timedelta, date
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import get_db, init_db, Utente, Prodotto, Incasso, ContatoreRicevute
from auth import verifica_password, hash_password, crea_token, get_utente_corrente, richiedi_admin
from ricevuta import genera_ricevuta_pdf
from modulo_excel import genera_modulo_excel

app = FastAPI(title="Galleria del Premio — Registro Corrispettivi")
scheduler = AsyncIOScheduler(timezone="Europe/Rome")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

TZ_IT = timezone(timedelta(hours=1))

def ora_italia():
    return datetime.now(TZ_IT).replace(tzinfo=None)

MESI_IT = ["","Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno",
           "Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"]

# ─── SCHEDULER ───────────────────────────────────────────────────────────────

async def task_report_giornaliero():
    from email_report import invia_report_giornaliero
    db = next(get_db())
    try:
        await invia_report_giornaliero(db)
    finally:
        db.close()

async def task_report_mensile():
    from email_report import invia_report_mensile
    oggi = date.today()
    db = next(get_db())
    try:
        await invia_report_mensile(db, oggi.month, oggi.year)
    finally:
        db.close()

# ─── STARTUP / SHUTDOWN ──────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    init_db()
    db = next(get_db())
    if not db.query(Utente).first():
        db.add(Utente(username="admin", nome="Amministratore", password_hash=hash_password("galleria2025"), ruolo="admin"))
        db.commit()
    if not db.query(Prodotto).first():
        db.add(Prodotto(nome="Biglietto singolo", descrizione="Ingresso standard alla galleria", prezzo=3.00))
        db.add(Prodotto(nome="Tessera fedeltà", descrizione="Abbonamento annuale", prezzo=30.00))
        db.commit()
    db.close()
    scheduler.add_job(task_report_giornaliero, CronTrigger(hour=18, minute=0, timezone="Europe/Rome"), id="report_giornaliero", replace_existing=True)
    scheduler.add_job(task_report_mensile, CronTrigger(day="last", hour=18, minute=0, timezone="Europe/Rome"), id="report_mensile", replace_existing=True)
    scheduler.start()

@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown()

# ─── PING ────────────────────────────────────────────────────────────────────

@app.get("/ping")
def ping():
    return {"ok": True}

# ─── AUTH ────────────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    utente = db.query(Utente).filter(Utente.username == form.username, Utente.attivo == True).first()
    if not utente or not verifica_password(form.password, utente.password_hash):
        raise HTTPException(status_code=401, detail="Credenziali non valide.")
    token = crea_token({"sub": utente.username})
    return {"access_token": token, "token_type": "bearer", "ruolo": utente.ruolo, "nome": utente.nome}

@app.get("/api/auth/me")
def me(utente: Utente = Depends(get_utente_corrente)):
    return {"username": utente.username, "nome": utente.nome, "ruolo": utente.ruolo}

# ─── PRODOTTI ────────────────────────────────────────────────────────────────

class ProdottoIn(BaseModel):
    nome: str
    descrizione: str = ""
    prezzo: float
    attivo: bool = True

@app.get("/api/prodotti")
def lista_prodotti(solo_attivi: bool = True, db: Session = Depends(get_db), _=Depends(get_utente_corrente)):
    q = db.query(Prodotto)
    if solo_attivi:
        q = q.filter(Prodotto.attivo == True)
    return q.order_by(Prodotto.id).all()

@app.post("/api/prodotti")
def crea_prodotto(data: ProdottoIn, db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    p = Prodotto(**data.dict())
    db.add(p); db.commit(); db.refresh(p)
    return p

@app.put("/api/prodotti/{pid}")
def aggiorna_prodotto(pid: int, data: ProdottoIn, db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    p = db.query(Prodotto).filter(Prodotto.id == pid).first()
    if not p: raise HTTPException(404, "Prodotto non trovato.")
    for k, v in data.dict().items(): setattr(p, k, v)
    db.commit(); db.refresh(p)
    return p

@app.delete("/api/prodotti/{pid}")
def disattiva_prodotto(pid: int, db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    p = db.query(Prodotto).filter(Prodotto.id == pid).first()
    if not p: raise HTTPException(404, "Prodotto non trovato.")
    p.attivo = False; db.commit()
    return {"ok": True}

# ─── INCASSI ─────────────────────────────────────────────────────────────────

class IncassoIn(BaseModel):
    prodotto_id: int
    quantita: int = 1
    modalita: str
    data: Optional[str] = None
    ricevuta_da: Optional[int] = None
    ricevuta_a: Optional[int] = None
    note: Optional[str] = ""

def prossimo_numero(db: Session, anno: int) -> int:
    contatore = db.query(ContatoreRicevute).filter(ContatoreRicevute.anno == anno).first()
    if not contatore:
        contatore = ContatoreRicevute(anno=anno, ultimo_numero=0)
        db.add(contatore)
    contatore.ultimo_numero += 1
    db.commit()
    return contatore.ultimo_numero

@app.post("/api/incassi")
def registra_incasso(data: IncassoIn, db: Session = Depends(get_db), utente: Utente = Depends(get_utente_corrente)):
    prodotto = db.query(Prodotto).filter(Prodotto.id == data.prodotto_id, Prodotto.attivo == True).first()
    if not prodotto: raise HTTPException(404, "Prodotto non trovato.")
    if data.modalita not in ("Contante", "POS"): raise HTTPException(400, "Modalità deve essere 'Contante' o 'POS'.")
    data_incasso = datetime.fromisoformat(data.data) if data.data else ora_italia()
    anno = data_incasso.year
    numero = prossimo_numero(db, anno)
    inc = Incasso(
        numero_ricevuta=numero, data=data_incasso,
        prodotto_id=prodotto.id, prodotto_nome=prodotto.nome, prodotto_prezzo=prodotto.prezzo,
        quantita=data.quantita, importo_totale=round(prodotto.prezzo * data.quantita, 2),
        modalita=data.modalita, ricevuta_da=data.ricevuta_da, ricevuta_a=data.ricevuta_a,
        note=data.note or "", operatore_id=utente.id, operatore_nome=utente.nome,
        anno=anno, mese=data_incasso.month,
    )
    db.add(inc); db.commit(); db.refresh(inc)
    return inc

@app.get("/api/incassi")
def lista_incassi(anno: Optional[int] = None, mese: Optional[int] = None, db: Session = Depends(get_db), _=Depends(get_utente_corrente)):
    q = db.query(Incasso)
    if anno: q = q.filter(Incasso.anno == anno)
    if mese: q = q.filter(Incasso.mese == mese)
    return q.order_by(Incasso.data.desc()).all()

@app.get("/api/incassi/{inc_id}/ricevuta")
def scarica_ricevuta(inc_id: int, db: Session = Depends(get_db), _=Depends(get_utente_corrente)):
    inc = db.query(Incasso).filter(Incasso.id == inc_id).first()
    if not inc: raise HTTPException(404, "Registrazione non trovata.")
    payload = {"numero_ricevuta": inc.numero_ricevuta, "anno": inc.anno, "data": inc.data.isoformat(),
               "prodotto_nome": inc.prodotto_nome, "quantita": inc.quantita, "importo_totale": inc.importo_totale,
               "modalita": inc.modalita, "note": inc.note, "operatore_nome": inc.operatore_nome}
    pdf = genera_ricevuta_pdf(payload)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=ricevuta_{inc.numero_ricevuta:04d}_{inc.anno}.pdf"})

@app.delete("/api/incassi/{inc_id}")
def elimina_incasso(inc_id: int, db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    inc = db.query(Incasso).filter(Incasso.id == inc_id).first()
    if not inc: raise HTTPException(404, "Registrazione non trovata.")
    db.delete(inc); db.commit()
    return {"ok": True}

class AggiornamentoData(BaseModel):
    data: str

@app.put("/api/incassi/{inc_id}/data")
def aggiorna_data_incasso(inc_id: int, body: AggiornamentoData, db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    inc = db.query(Incasso).filter(Incasso.id == inc_id).first()
    if not inc: raise HTTPException(404, "Registrazione non trovata.")
    try:
        nuova_data = datetime.fromisoformat(body.data)
    except ValueError:
        raise HTTPException(400, "Formato data non valido. Usa YYYY-MM-DD.")
    inc.data = nuova_data; inc.anno = nuova_data.year; inc.mese = nuova_data.month
    db.commit()
    return {"ok": True}

# ─── RIEPILOGO ───────────────────────────────────────────────────────────────

@app.get("/api/riepilogo")
def riepilogo(anno: int, mese: int, db: Session = Depends(get_db), _=Depends(get_utente_corrente)):
    incassi = db.query(Incasso).filter(Incasso.anno == anno, Incasso.mese == mese).order_by(Incasso.data).all()
    tot = sum(i.importo_totale for i in incassi)
    cash = sum(i.importo_totale for i in incassi if i.modalita == "Contante")
    pos = sum(i.importo_totale for i in incassi if i.modalita == "POS")
    return {"totale": tot, "contante": cash, "pos": pos, "righe": len(incassi)}

# ─── EXPORT EXCEL ────────────────────────────────────────────────────────────

@app.get("/api/export/excel")
def export_excel(anno: int, mese: int, db: Session = Depends(get_db), _=Depends(get_utente_corrente)):
    incassi = db.query(Incasso).filter(Incasso.anno == anno, Incasso.mese == mese).order_by(Incasso.data).all()
    if not incassi: raise HTTPException(404, "Nessun dato per il periodo selezionato.")
    payload = [{"data": i.data.isoformat(), "ricevuta_da": i.ricevuta_da, "ricevuta_a": i.ricevuta_a,
                "importo_totale": i.importo_totale, "modalita": i.modalita, "note": i.note} for i in incassi]
    xlsx = genera_modulo_excel(payload, mese, anno)
    return Response(content=xlsx, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=Corrispettivi_{MESI_IT[mese]}_{anno}.xlsx"})

# ─── UTENTI ──────────────────────────────────────────────────────────────────

class UtenteIn(BaseModel):
    username: str
    nome: str
    password: str
    ruolo: str = "operatore"

@app.get("/api/utenti")
def lista_utenti(db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    return db.query(Utente).filter(Utente.attivo == True).all()

@app.post("/api/utenti")
def crea_utente(data: UtenteIn, db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    if db.query(Utente).filter(Utente.username == data.username).first():
        raise HTTPException(400, "Username già esistente.")
    u = Utente(username=data.username, nome=data.nome, password_hash=hash_password(data.password), ruolo=data.ruolo)
    db.add(u); db.commit(); db.refresh(u)
    return {"id": u.id, "username": u.username, "nome": u.nome, "ruolo": u.ruolo}

class CambiaPassword(BaseModel):
    password_attuale: str
    nuova_password: str

@app.put("/api/utenti/me/password")
def cambia_password(data: CambiaPassword, db: Session = Depends(get_db), utente: Utente = Depends(get_utente_corrente)):
    if not verifica_password(data.password_attuale, utente.password_hash):
        raise HTTPException(400, "Password attuale non corretta.")
    utente.password_hash = hash_password(data.nuova_password); db.commit()
    return {"ok": True}

@app.delete("/api/utenti/{uid}")
def disattiva_utente(uid: int, db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    u = db.query(Utente).filter(Utente.id == uid).first()
    if not u: raise HTTPException(404)
    u.attivo = False; db.commit()
    return {"ok": True}

# ─── EMAIL REPORT ────────────────────────────────────────────────────────────

@app.post("/api/report/giornaliero")
async def trigger_report_giornaliero(db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    from email_report import invia_report_giornaliero
    ok = await invia_report_giornaliero(db)
    return {"ok": ok}

@app.post("/api/report/mensile")
async def trigger_report_mensile(anno: int = None, mese: int = None, db: Session = Depends(get_db), _=Depends(richiedi_admin)):
    from email_report import invia_report_mensile
    oggi = date.today()
    ok = await invia_report_mensile(db, mese or oggi.month, anno or oggi.year)
    return {"ok": ok}

@app.post("/api/report/test")
async def test_email(_=Depends(richiedi_admin)):
    from email_report import invia_email
    ok = invia_email("Test configurazione email — Galleria del Premio",
                     "<div style='font-family:Arial;padding:20px'><h2>Email di test</h2><p>Configurazione corretta.</p></div>")
    return {"ok": ok}

# ─── FRONTEND ────────────────────────────────────────────────────────────────

frontend_path = os.path.join(os.path.dirname(__file__), "../frontend")
if os.path.exists(os.path.join(frontend_path, "static")):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_path, "static")), name="static")

@app.get("/{full_path:path}", response_class=HTMLResponse)
def serve_frontend(full_path: str):
    index = os.path.join(frontend_path, "templates", "index.html")
    if os.path.exists(index):
        with open(index) as f: return f.read()
    return HTMLResponse("<h1>Frontend non trovato</h1>", status_code=404)
