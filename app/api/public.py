"""
app/api/public.py
Endpoints con generación directa (sin BackgroundTasks ni schedulers)
"""
from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(
        "static/favicon.ico",
        media_type="image/x-icon",
        headers={
            "Cache-Control": "public, max-age=3600",
            "ETag": "v1"
        }
    )