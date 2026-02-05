"""
app/services/auth_service.py
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
import bcrypt
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
import hashlib
import time

from app.config import settings


class TokenPayload(BaseModel):
    sub: str
    user_id: str
    rol: str
    exp: int


class AuthService:
    ALGORITHM = "HS256"
    
    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        if not plain or not hashed:
            return False
        
        try:
            return bcrypt.checkpw(
                plain[:72].encode('utf-8'),
                hashed.encode('utf-8')
            )
        except Exception:
            return False
    
    @staticmethod
    def hash_password(password: str) -> str:
        if not password or len(password) > 72:
            raise ValueError("Contraseña inválida")
        
        return bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt(rounds=12)
        ).decode('utf-8')
    
    @staticmethod
    def create_access_token(
        email: str,
        user_id: uuid.UUID,
        rol: str,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        expire = datetime.now(timezone.utc) + (
            expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        payload = {
            "sub": email,
            "user_id": str(user_id),
            "rol": rol,
            "exp": int(expire.timestamp())
        }
        
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=AuthService.ALGORITHM)
    
    @staticmethod
    def decode_token(token: str) -> TokenPayload:
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[AuthService.ALGORITHM]
            )
            return TokenPayload(**payload)
        except jwt.ExpiredSignatureError:
            raise ValueError("Token expirado")
        except jwt.InvalidTokenError:
            raise ValueError("Token inválido")
    
    @staticmethod
    def generate_token_hash(token: str) -> str:
        unique = f"{token}:{time.time_ns()}:{uuid.uuid4()}"
        return hashlib.sha256(unique.encode()).hexdigest()


class SessionService:
    @staticmethod
    async def create(
        db: AsyncSession,
        usuario_id: uuid.UUID,
        token: str
    ):
        from app.models import Sesion
        
        token_hash = AuthService.generate_token_hash(token)
        expira_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        
        sesion = Sesion(
            usuario_id=usuario_id,
            token_hash=token_hash,
            expira_at=expira_at
        )
        
        db.add(sesion)
        await db.commit()
        await db.refresh(sesion)
        return sesion
    
    @staticmethod
    async def verify_active(db: AsyncSession, user_id: uuid.UUID) -> bool:
        from app.models import Sesion
        
        result = await db.execute(
            select(Sesion).where(
                Sesion.usuario_id == user_id,
                Sesion.expira_at > datetime.now(timezone.utc),
                Sesion.revocado == False
            ).limit(1)
        )
        
        return result.scalar_one_or_none() is not None
    
    @staticmethod
    async def revoke_all(db: AsyncSession, user_id: uuid.UUID):
        from app.models import Sesion
        from sqlalchemy import update
        
        await db.execute(
            update(Sesion)
            .where(Sesion.usuario_id == user_id, Sesion.revocado == False)
            .values(revocado=True)
        )
        await db.commit()


class UserRepository:
    @staticmethod
    async def get_by_email(db: AsyncSession, email: str):
        from app.models import User
        
        result = await db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def authenticate(
        db: AsyncSession,
        email: str,
        password: str
    ):
        user = await UserRepository.get_by_email(db, email)
        
        if not user:
            return None
        
        if not AuthService.verify_password(password, user.password_hash):
            return None
        
        if not user.is_active:
            return None
        
        return user
    
    @staticmethod
    async def create(
        db: AsyncSession,
        email: str,
        password: str,
        full_name: str,
        role: str = 'vendedor'
    ):
        from app.models import User
        
        user = User(
            email=email,
            password_hash=AuthService.hash_password(password),
            full_name=full_name,
            role=role
        )
        
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user
    
    @staticmethod
    async def update_password(
        db: AsyncSession,
        user_id: uuid.UUID,
        new_password: str
    ):
        from app.models import User
        from sqlalchemy import update
        
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(password_hash=AuthService.hash_password(new_password))
        )
        await db.commit()