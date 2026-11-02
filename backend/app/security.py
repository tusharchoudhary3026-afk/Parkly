from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models import Role, User

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/token")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)

def issue_token(user: User) -> str:
    expires = datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": str(user.id), "operator_id": str(user.operator_id), "role": user.role.value, "exp": expires}, settings.jwt_secret, algorithm="HS256")

async def current_user(token: str = Depends(oauth2), db: AsyncSession = Depends(get_db)) -> User:
    unauthorized = HTTPException(status_code=401, detail={"error": "invalid_credentials"}, headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user_id = UUID(claims["sub"])
    except (JWTError, KeyError, ValueError):
        raise unauthorized
    user = await db.scalar(select(User).where(User.id == user_id, User.operator_id == UUID(claims["operator_id"])))
    if user is None: raise unauthorized
    return user

def require_roles(*roles: Role):
    async def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail={"error": "forbidden"})
        return user
    return dependency
