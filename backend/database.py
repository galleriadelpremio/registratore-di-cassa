from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./galleria.db")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Utente(Base):
    __tablename__ = "utenti"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    nome = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    ruolo = Column(String, default="operatore")  # "admin" o "operatore"
    attivo = Column(Boolean, default=True)
    creato_il = Column(DateTime, default=datetime.utcnow)


class Prodotto(Base):
    __tablename__ = "prodotti"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    descrizione = Column(String, default="")
    prezzo = Column(Float, nullable=False)
    attivo = Column(Boolean, default=True)
    creato_il = Column(DateTime, default=datetime.utcnow)


class Incasso(Base):
    __tablename__ = "incassi"
    id = Column(Integer, primary_key=True, index=True)
    numero_ricevuta = Column(Integer, nullable=False, unique=True)
    data = Column(DateTime, nullable=False)
    prodotto_id = Column(Integer, nullable=False)
    prodotto_nome = Column(String, nullable=False)
    prodotto_prezzo = Column(Float, nullable=False)
    quantita = Column(Integer, default=1)
    importo_totale = Column(Float, nullable=False)
    modalita = Column(String, nullable=False)  # "Contante" o "POS"
    ricevuta_da = Column(Integer, nullable=True)
    ricevuta_a = Column(Integer, nullable=True)
    note = Column(Text, default="")
    operatore_id = Column(Integer, nullable=False)
    operatore_nome = Column(String, nullable=False)
    anno = Column(Integer, nullable=False)
    mese = Column(Integer, nullable=False)
    creato_il = Column(DateTime, default=datetime.utcnow)


class ContatoreRicevute(Base):
    __tablename__ = "contatore_ricevute"
    id = Column(Integer, primary_key=True)
    anno = Column(Integer, nullable=False, unique=True)
    ultimo_numero = Column(Integer, default=0)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
