"""
Docstring for app.middleware.security
"""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, Tuple
import asyncio
import hashlib


class InMemoryRateLimiter:
    def __init__(
        self,
        requests_per_minute: int = 10,
        requests_per_hour: int = 100,
        cleanup_interval: int = 300
    ):
        self.rpm = requests_per_minute
        self.rph = requests_per_hour
        
        self.minute_buckets: Dict[str, list] = defaultdict(list)
        self.hour_buckets: Dict[str, list] = defaultdict(list)
        self.blocked_ips: Dict[str, datetime] = {}
        
        self.cleanup_interval = cleanup_interval
        self._cleanup_task = None
    
    def _get_client_key(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"
        
        return hashlib.sha256(ip.encode()).hexdigest()[:16]
    
    def _cleanup_old_entries(self):
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)
        
        for key in list(self.minute_buckets.keys()):
            self.minute_buckets[key] = [
                ts for ts in self.minute_buckets[key] if ts > minute_ago
            ]
            if not self.minute_buckets[key]:
                del self.minute_buckets[key]
        
        for key in list(self.hour_buckets.keys()):
            self.hour_buckets[key] = [
                ts for ts in self.hour_buckets[key] if ts > hour_ago
            ]
            if not self.hour_buckets[key]:
                del self.hour_buckets[key]
        
        for ip, blocked_until in list(self.blocked_ips.items()):
            if now > blocked_until:
                del self.blocked_ips[ip]
    
    async def check_rate_limit(self, request: Request) -> Tuple[bool, str]:
        client_key = self._get_client_key(request)
        now = datetime.now()
        
        if client_key in self.blocked_ips:
            blocked_until = self.blocked_ips[client_key]
            if now < blocked_until:
                remaining = int((blocked_until - now).total_seconds())
                return False, f"IP bloqueada. Reintenta en {remaining}s"
            del self.blocked_ips[client_key]
        
        self.minute_buckets[client_key].append(now)
        self.hour_buckets[client_key].append(now)
        
        minute_count = len(self.minute_buckets[client_key])
        hour_count = len(self.hour_buckets[client_key])
        
        if minute_count > self.rpm:
            self.blocked_ips[client_key] = now + timedelta(minutes=5)
            return False, f"Límite excedido: {self.rpm} req/min"
        
        if hour_count > self.rph:
            self.blocked_ips[client_key] = now + timedelta(minutes=15)
            return False, f"Límite excedido: {self.rph} req/hora"
        
        return True, "OK"
    
    async def start_cleanup_task(self):
        while True:
            await asyncio.sleep(self.cleanup_interval)
            self._cleanup_old_entries()


public_rate_limiter = InMemoryRateLimiter(
    requests_per_minute=10,
    requests_per_hour=100
)

auth_rate_limiter = InMemoryRateLimiter(
    requests_per_minute=5,
    requests_per_hour=20
)

websocket_rate_limiter = InMemoryRateLimiter(
    requests_per_minute=30,
    requests_per_hour=500
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        if path.startswith("/api/v1/auth"):
            limiter = auth_rate_limiter
        elif path.startswith("/api/v1/chat") or path.startswith("/api/v1/leads"):
            limiter = public_rate_limiter
        else:
            return await call_next(request)
        
        allowed, message = await limiter.check_rate_limit(request)
        
        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": message,
                    "retry_after": "Espera antes de reintentar"
                }
            )
        
        return await call_next(request)


class InputValidationMiddleware(BaseHTTPMiddleware):
    MAX_BODY_SIZE = 2 * 1024 * 1024
    
    DANGEROUS_HEADERS = [
        "X-Forwarded-Host",
        "X-Original-URL",
        "X-Rewrite-URL"
    ]
    
    async def dispatch(self, request: Request, call_next):
        for header in self.DANGEROUS_HEADERS:
            if header.lower() in [h.lower() for h in request.headers.keys()]:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Header no permitido"}
                )
        
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.MAX_BODY_SIZE:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "Payload demasiado grande (max 2MB)"}
                )
        
        return await call_next(request)


class WebSocketConnectionManager:
    def __init__(self, max_connections: int = 10):
        self.active_connections: Dict[str, int] = defaultdict(int)
        self.max_connections = max_connections
        self.connection_times: Dict[str, list] = defaultdict(list)
    
    def _get_client_key(self, client_host: str) -> str:
        return hashlib.sha256(client_host.encode()).hexdigest()[:16]
    
    async def can_connect(self, client_host: str) -> Tuple[bool, str]:
        client_key = self._get_client_key(client_host)
        
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        self.connection_times[client_key] = [
            ts for ts in self.connection_times[client_key] if ts > minute_ago
        ]
        
        if len(self.connection_times[client_key]) > 3:
            return False, "Demasiadas conexiones en corto tiempo"
        
        if self.active_connections[client_key] >= self.max_connections:
            return False, f"Límite de {self.max_connections} conexiones alcanzado"
        
        return True, "OK"
    
    def connect(self, client_host: str):
        client_key = self._get_client_key(client_host)
        self.active_connections[client_key] += 1
        self.connection_times[client_key].append(datetime.now())
    
    def disconnect(self, client_host: str):
        client_key = self._get_client_key(client_host)
        if self.active_connections[client_key] > 0:
            self.active_connections[client_key] -= 1


ws_manager = WebSocketConnectionManager(max_connections=3)