"""
FIX CRÍTICO: Cambiar EMBEDDING_DIMENSIONS de 384 a 1536
"""

import os
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_NAME: str = "Agent AI LeadsProfile"
    LOG_LEVEL: str = "ERROR"

    DOMAIN: str = os.getenv("DOMAIN", "localhost")
    USE_SSL: bool = os.getenv("USE_SSL", "false").lower() == "true"

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_RELOAD: bool = False

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:adminsa007@postgres:5432/crm_leadsdb",
    )

    DB_POOL_SIZE: int = 1
    DB_MAX_OVERFLOW: int = 1
    DB_POOL_TIMEOUT: int = 20
    DB_POOL_RECYCLE: int = 900
    DB_ECHO: bool = False

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TIMEOUT: int = 20
    OPENAI_MAX_RETRIES: int = 2

    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536  # ← CAMBIADO DE 384 A 1536
    EMBEDDING_BATCH_SIZE: int = 3
    EMBEDDING_CACHE_SIZE: int = 10

    CHAT_MODEL: str = "gpt-4o-mini"
    CHAT_MAX_TOKENS: int = 400
    CHAT_TEMPERATURE: float = 0.7
    CHAT_CONTEXT_MESSAGES: int = 4

    MAX_CONCURRENT_REQUESTS: int = 2
    MAX_WEBSOCKET_CONNECTIONS: int = 3
    REQUEST_TIMEOUT: int = 25

    RAG_TOP_K: int = 2
    RAG_SIMILARITY_THRESHOLD: float = 0.65

    SECRET_KEY: str = os.getenv("SECRET_KEY", "CAMBIAR-EN-PRODUCCION")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"

    RATE_LIMIT_PUBLIC_RPM: int = 10
    RATE_LIMIT_PUBLIC_RPH: int = 100
    RATE_LIMIT_AUTH_RPM: int = 5
    RATE_LIMIT_AUTH_RPH: int = 20
    RATE_LIMIT_WS_RPM: int = 30
    RATE_LIMIT_WS_RPH: int = 500

    CORS_ORIGINS: List[str] = [
        os.getenv("CORS_ORIGIN_1", "http://localhost:4321"),
        os.getenv("CORS_ORIGIN_2", "http://localhost:5173"),
        os.getenv("CORS_ORIGIN_3", ""),
        os.getenv("CORS_ORIGIN_4", ""),
    ]

    MAX_REQUEST_SIZE_MB: int = 2
    WEBSOCKET_TIMEOUT: int = 300

    UVICORN_WORKERS: int = 1

    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")

    EMAIL_VENTAS: str = os.getenv("EMAIL_VENTAS", "ventas@empresa.com")
    EMAIL_SOPORTE: str = os.getenv("EMAIL_SOPORTE", "soporte@empresa.com")

    NOMBRE_EMPRESA: str = os.getenv("NOMBRE_EMPRESA", "NexWebs")
    SITIO_WEB: str = os.getenv("SITIO_WEB", "https://nexwebs.com")
    TELEFONO_SOPORTE: str = os.getenv("TELEFONO_SOPORTE", "+51 907 321 211")

    GOOGLE_CLIENT_CONFIG: str = os.getenv("GOOGLE_CLIENT_CONFIG", "")

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()

MEMORY_LIMITS = {
    "app_max_mb": 400,
    "embedding_cache_mb": 5,
    "conversation_cache_mb": 10,
    "buffer_mb": 97,
}

GC_CONFIG = {
    "enabled": True,
    "threshold": (700, 10, 5),
    "interval_seconds": 60,
}
