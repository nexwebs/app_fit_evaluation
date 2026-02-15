"""
app/main.py
FastAPI con rutas organizadas y coherentes
"""

import gc
import asyncio
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import uvicorn
from fastapi.staticfiles import StaticFiles

from app.config import settings, GC_CONFIG
from app.middleware.security import (
    SecurityHeadersMiddleware,
    RateLimitMiddleware,
    InputValidationMiddleware,
    public_rate_limiter,
    auth_rate_limiter,
    websocket_rate_limiter,
)


async def run_garbage_collector():
    while True:
        await asyncio.sleep(GC_CONFIG["interval_seconds"])
        collected = gc.collect()


async def run_rate_limiter_cleanup():
    await asyncio.gather(
        public_rate_limiter.start_cleanup_task(),
        auth_rate_limiter.start_cleanup_task(),
        websocket_rate_limiter.start_cleanup_task(),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 60)
    print(f"Entorno: {settings.APP_ENV}")
    print(f"Dominio: {settings.DOMAIN}")
    print(f"JWT Expire: {settings.ACCESS_TOKEN_EXPIRE_MINUTES} min")
    print("=" * 60)

    if GC_CONFIG["enabled"]:
        gc.set_threshold(*GC_CONFIG["threshold"])
        gc.enable()

    try:
        from app.services.database import engine

        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"PostgreSQL: {version[:50]}")

            await conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname='vector'")
            )
            print("pgvector OK")

    except Exception as e:
        print(f"Error DB: {e}")

    try:
        from app.services.checkpointer import create_checkpointer

        checkpointer_url = settings.DATABASE_URL.replace(
            "postgresql+asyncpg://", "postgresql://"
        )
        app.state.checkpointer = create_checkpointer(checkpointer_url)
        print("Checkpointer OK")
    except Exception as e:
        print(f"Error Checkpointer: {e}")
        app.state.checkpointer = None

    try:
        from app.services.embeddings import embedding_service

        print(f"Embeddings: {settings.EMBEDDING_MODEL}")
    except Exception as e:
        print(f"Embeddings: {e}")

    print(f"Rate Limits:")
    print(
        f"   Public: {settings.RATE_LIMIT_PUBLIC_RPM}/min, {settings.RATE_LIMIT_PUBLIC_RPH}/hora"
    )
    print(
        f"   Auth: {settings.RATE_LIMIT_AUTH_RPM}/min, {settings.RATE_LIMIT_AUTH_RPH}/hora"
    )
    print(
        f"   WebSocket: {settings.RATE_LIMIT_WS_RPM}/min, {settings.RATE_LIMIT_WS_RPH}/hora"
    )

    gc_task = None
    cleanup_task = None

    if GC_CONFIG["enabled"]:
        gc_task = asyncio.create_task(run_garbage_collector())

    cleanup_task = asyncio.create_task(run_rate_limiter_cleanup())

    print("=" * 60)
    print(f"API: http://{settings.API_HOST}:{settings.API_PORT}")
    print(f"Docs: http://{settings.API_HOST}:{settings.API_PORT}/docs")
    print("=" * 60)

    yield

    if gc_task:
        gc_task.cancel()
    if cleanup_task:
        cleanup_task.cancel()

    try:
        from app.services.database import engine

        await engine.dispose()
    except Exception:
        pass

    if hasattr(app.state, "checkpointer") and app.state.checkpointer:
        try:
            app.state.checkpointer.engine.dispose()
        except Exception:
            pass

    gc.collect()


app = FastAPI(
    title="CRM Lead Capture",
    description="Sistema multi-agente optimizado para 512MB RAM con seguridad reforzada",
    version="2.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/api/v1/openapi.json",
)


if settings.APP_ENV == "production":
    allowed_origins = [origin for origin in settings.CORS_ORIGINS if origin != "*"]
else:
    allowed_origins = settings.CORS_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=3600,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(InputValidationMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)


class ConcurrencyLimitMiddleware:
    def __init__(self, app, max_concurrent: int):
        self.app = app
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async with self.semaphore:
            await self.app(scope, receive, send)


app.add_middleware(
    ConcurrencyLimitMiddleware, max_concurrent=settings.MAX_CONCURRENT_REQUESTS
)

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.evaluations import router as evaluations_router
from app.api.embeddings import router as embeddings_router
from app.api.public import router as public_router

app.include_router(public_router)

app.include_router(auth_router, prefix="/api/v1/auth", tags=["Autenticación"])

app.include_router(chat_router, prefix="/api/v1/chat", tags=["Chat"])

app.include_router(embeddings_router, prefix="/api/v1/embeddings", tags=["Embeddings"])
app.include_router(
    evaluations_router, prefix="/api/v1/evaluations", tags=["Evaluations"]
)


@app.get("/", tags=["Sistema"])
async def root():
    protocol = "https" if settings.USE_SSL else "http"
    ws_protocol = "wss" if settings.USE_SSL else "ws"
    base_url = f"{protocol}://{settings.DOMAIN}"

    return {
        "app": settings.APP_NAME,
        "version": "2.2.0",
        "status": "online",
        "environment": settings.APP_ENV,
        "security": {
            "rate_limiting": True,
            "jwt_expiration_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            "cors_restricted": settings.APP_ENV == "production",
        },
        "endpoints": {
            "documentacion": f"{base_url}/docs",
            "health": f"{base_url}/health",
            "chat_ws": f"{ws_protocol}://{settings.DOMAIN}/api/v1/chat/ws/{{session_id}}",
            "auth": f"{base_url}/api/v1/auth/login",
            "evaluations": f"{base_url}/api/v1/positions",
        },
    }


@app.get("/health", tags=["Sistema"])
async def health():
    import psutil
    import os

    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    memory_mb = memory_info.rss / 1024 / 1024

    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": settings.APP_ENV,
        "memory": {
            "used_mb": round(memory_mb, 2),
            "limit_mb": 512,
            "usage_pct": round((memory_mb / 512) * 100, 2),
        },
        "security": {
            "rate_limiting_active": True,
            "jwt_expiration_min": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        },
    }


@app.get("/metrics", tags=["Sistema"])
async def metrics():
    import psutil
    import os

    process = psutil.Process(os.getpid())

    return {
        "memory": {
            "rss_mb": round(process.memory_info().rss / 1024 / 1024, 2),
            "vms_mb": round(process.memory_info().vms / 1024 / 1024, 2),
            "percent": round(process.memory_percent(), 2),
        },
        "cpu": {
            "percent": round(process.cpu_percent(interval=0.1), 2),
            "num_threads": process.num_threads(),
        },
        "limits": {
            "max_concurrent": settings.MAX_CONCURRENT_REQUESTS,
            "embedding_cache": settings.EMBEDDING_CACHE_SIZE,
            "db_pool": settings.DB_POOL_SIZE,
        },
    }


@app.post("/admin/gc", tags=["Sistema"])
async def force_gc():
    import psutil
    import os

    before_mb = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    collected = gc.collect()
    after_mb = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

    return {
        "collected_objects": collected,
        "memory_before_mb": round(before_mb, 2),
        "memory_after_mb": round(after_mb, 2),
        "freed_mb": round(before_mb - after_mb, 2),
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        workers=settings.UVICORN_WORKERS,
        reload=settings.API_RELOAD,
        log_level=settings.LOG_LEVEL.lower(),
        timeout_keep_alive=5,
        limit_concurrency=settings.MAX_CONCURRENT_REQUESTS,
        limit_max_requests=1000,
        access_log=False,
    )
