from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db, Utente
import os

SECRET_KEY = os.getenv("SECRET_KEY", "cambia-questa-chiave-in-produzione-con-stringa-lunga-e-casuale")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 12

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def verifica_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def crea_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_utente_corrente(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Utente:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sessione scaduta o non valida. Effettua nuovamente il login.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise exc
    except JWTError:
        raise exc
    utente = db.query(Utente).filter(Utente.username == username, Utente.attivo == True).first()
    if not utente:
        raise exc
    return utente


def richiedi_admin(utente: Utente = Depends(get_utente_corrente)) -> Utente:
    if utente.ruolo != "admin":
        raise HTTPException(status_code=403, detail="Accesso riservato agli amministratori.")
    return utente
