from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from ..config import settings
from ..schemas.auth import TokenData


def hash_password(password: str) -> str:
    """Gera o hash bcrypt de uma senha."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha corresponde ao hash armazenado."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(usuario_id: int, email: str, role: Optional[str] = None) -> str:
    """Cria um JWT de acesso com validade configurada."""
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(usuario_id),
        "email": email,
        "role": role,
        "tipo": "access",
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(usuario_id: int, email: str) -> str:
    """Cria um JWT de refresh com validade mais longa."""
    expire = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(usuario_id),
        "email": email,
        "tipo": "refresh",
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[TokenData]:
    """Decodifica e valida um JWT. Retorna TokenData ou None em caso de erro."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        usuario_id = int(payload.get("sub"))
        email: str = payload.get("email")
        role: Optional[str] = payload.get("role")
        tipo: str = payload.get("tipo", "access")
        if usuario_id is None or email is None:
            return None
        return TokenData(usuario_id=usuario_id, email=email, role=role, tipo=tipo)
    except (JWTError, ValueError, TypeError):
        return None