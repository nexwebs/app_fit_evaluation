"""
app/api/auth.py
Sistema de autenticación JWT con sesiones persistentes
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr

from app.services.database import get_db
from app.services.auth_service import (
    AuthService,
    SessionService,
    UserRepository,
    TokenPayload
)
from app.config import settings

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    nombre_completo: str
    rol: str = 'vendedor'


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    nombre_completo: str
    rol: str
    activo: bool
    
    class Config:
        from_attributes = True


class ChangePasswordRequest(BaseModel):
    password_actual: str
    password_nueva: str


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = AuthService.decode_token(token)
    except ValueError:
        raise credentials_exception
    
    user = await UserRepository.get_by_email(db, email=payload.sub)
    
    if not user or not user.is_active:
        raise credentials_exception
    
    if not await SessionService.verify_active(db, user.id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión expirada o inválida"
        )
    
    return user


async def get_current_active_user(
    current_user = Depends(get_current_user)
):
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo"
        )
    return current_user


def require_role(required_role: str):
    async def role_checker(current_user = Depends(get_current_active_user)):
        if current_user.role not in [required_role, 'admin']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requiere rol {required_role}"
            )
        return current_user
    return role_checker


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    if len(user.password) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contraseña no puede exceder 72 caracteres"
        )
    
    if await UserRepository.get_by_email(db, user.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email ya registrado"
        )
    
    valid_roles = ['admin', 'recruiter', 'interviewer', 'vendedor', 'viewer']
    if user.rol not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rol inválido. Debe ser uno de: {', '.join(valid_roles)}"
        )
    
    new_user = await UserRepository.create(
        db=db,
        email=user.email,
        password=user.password,
        full_name=user.nombre_completo,
        role=user.rol
    )
    
    return UserResponse(
        id=str(new_user.id),
        email=new_user.email,
        nombre_completo=new_user.full_name,
        rol=new_user.role,
        activo=new_user.is_active
    )


@router.post("/token", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    user = await UserRepository.authenticate(
        db=db,
        email=form_data.username,
        password=form_data.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = AuthService.create_access_token(
        email=user.email,
        user_id=user.id,
        rol=user.role
    )
    
    await SessionService.create(db, user.id, access_token)
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/login", response_model=Token)
async def login_json(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    user = await UserRepository.authenticate(
        db=db,
        email=credentials.email,
        password=credentials.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos"
        )
    
    access_token = AuthService.create_access_token(
        email=user.email,
        user_id=user.id,
        rol=user.role
    )
    
    await SessionService.create(db, user.id, access_token)
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/logout")
async def logout(
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    await SessionService.revoke_all(db, current_user.id)
    return {"message": "Sesión cerrada exitosamente"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user = Depends(get_current_active_user)
):
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        nombre_completo=current_user.full_name,
        rol=current_user.role,
        activo=current_user.is_active
    )


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    if len(request.password_nueva) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nueva contraseña no puede exceder 72 caracteres"
        )
    
    if not AuthService.verify_password(
        request.password_actual,
        current_user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contraseña actual incorrecta"
        )
    
    await UserRepository.update_password(
        db=db,
        user_id=current_user.id,
        new_password=request.password_nueva
    )
    
    await SessionService.revoke_all(db, current_user.id)
    
    return {"message": "Contraseña actualizada. Inicia sesión nuevamente"}


@router.get("/verify-token")
async def verify_token(current_user = Depends(get_current_active_user)):
    return {
        "valid": True,
        "user_id": str(current_user.id),
        "email": current_user.email,
        "rol": current_user.role
    }