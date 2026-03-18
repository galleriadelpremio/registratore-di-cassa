# Galleria del Premio — Registro Corrispettivi

Applicazione web per la gestione degli incassi giornalieri della Galleria del Premio, Suzzara (MN).

## Accesso di default

Alla prima apertura, viene creato automaticamente un utente amministratore:

- **Username:** `admin`
- **Password:** `galleria2025`

⚠️ Cambia la password appena accedi, dalla sezione Utenti.

## Funzionalità

- **Cassa**: registra incassi con un clic, genera ricevuta PDF automaticamente
- **Storico**: visualizza e filtra tutte le registrazioni per mese/anno
- **Riepilogo mensile**: totali con suddivisione contante/POS
- **Genera modulo**: esporta il modulo corrispettivi in Excel (formato originale)
- **Catalogo prezzi**: aggiungi/modifica/disattiva prodotti senza toccare il codice
- **Utenti**: crea account per i collaboratori con ruoli (admin / operatore)

## Deploy su Render

1. Carica questa cartella su GitHub (repository pubblico o privato)
2. Vai su [render.com](https://render.com) → New → Blueprint
3. Collega il repository GitHub
4. Render legge automaticamente `render.yaml` e configura tutto
5. Dopo il deploy, apri l'URL fornito da Render

## Sviluppo locale

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Apri `http://localhost:8000` nel browser.

## Struttura del progetto

```
galleria_premio/
├── backend/
│   ├── main.py          # API FastAPI
│   ├── database.py      # Modelli database SQLite
│   ├── auth.py          # Autenticazione JWT
│   ├── ricevuta.py      # Generatore PDF ricevute
│   ├── modulo_excel.py  # Generatore Excel corrispettivi
│   └── requirements.txt
├── frontend/
│   └── templates/
│       └── index.html   # Interfaccia utente (SPA)
├── render.yaml          # Configurazione deploy Render
└── README.md
```

## Note tecniche

- I dati sono salvati in SQLite su disco persistente (1 GB incluso nel piano Render)
- Le password sono cifrate con bcrypt
- Le sessioni durano 12 ore (token JWT)
- Il numero ricevuta riparte da 1 ogni anno
- L'app è responsive e funziona su smartphone
