"""
Autenticación JWT + hashing de contraseñas.
"""
import os
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, Header, Depends

SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_hex(32))
ALGORITHM = "HS256"
INACTIVIDAD_HORAS = 8

# passlib 1.7.4 + bcrypt 4.x requiere este parche
import bcrypt as _bcrypt_lib
if not hasattr(_bcrypt_lib, '__about__'):
    _bcrypt_lib.__about__ = type('about', (), {'__version__': _bcrypt_lib.__version__})()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def crear_token(user_id: int, email: str, nombre: str, rol: str) -> str:
    exp = datetime.utcnow() + timedelta(hours=INACTIVIDAD_HORAS)
    payload = {
        "sub": str(user_id),
        "email": email,
        "nombre": nombre,
        "rol": rol,
        "exp": exp,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decodificar_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")


def generar_password_temporal(largo: int = 12) -> str:
    """Genera contraseña segura aleatoria."""
    chars = string.ascii_letters + string.digits + "!@#$%"
    while True:
        pwd = ''.join(secrets.choice(chars) for _ in range(largo))
        # Asegurar al menos 1 mayúscula, 1 minúscula, 1 dígito
        if (any(c.isupper() for c in pwd)
                and any(c.islower() for c in pwd)
                and any(c.isdigit() for c in pwd)):
            return pwd


# ── Dependency para endpoints protegidos ──────────────────────────────────────

def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """Extrae y valida el JWT del header Authorization: Bearer <token>."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token de autenticación requerido")
    token = authorization.split(" ", 1)[1]
    return decodificar_token(token)


def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    """Requiere que el usuario tenga rol 'admin'."""
    if current_user.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="Se requiere rol de administrador")
    return current_user
