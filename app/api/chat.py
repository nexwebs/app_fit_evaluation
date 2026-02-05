"""
app/api/chat.py
Optimizado para 512MB RAM, 2 CPUs
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.database import AsyncSessionLocal
from sqlalchemy import text, select
from app.config import settings
from app.middleware.security import ws_manager, websocket_rate_limiter
from app.tools.cv_parser import parse_cv_with_llm
from app.models import Prospect, ProspectDocument
import json
import logging
import asyncio
import hashlib
from uuid import UUID

logger = logging.getLogger(__name__)

router = APIRouter()

_checkpointer = None


def get_checkpointer():
    global _checkpointer
    
    if _checkpointer is None:
        from app.services.checkpointer import create_checkpointer
        
        checkpointer_url = settings.DATABASE_URL.replace(
            "postgresql+asyncpg://", "postgresql://"
        )
        _checkpointer = create_checkpointer(checkpointer_url)
    
    return _checkpointer


@router.websocket("/ws/{session_token}")
async def websocket_evaluation(websocket: WebSocket, session_token: str):
    client_host = websocket.client.host if websocket.client else "unknown"
    
    if not await validate_connection(websocket, client_host):
        return
    
    await websocket.accept()
    ws_manager.connect(client_host)
    
    db = None
    ws_closed = False
    
    try:
        db = AsyncSessionLocal()
        checkpointer = get_checkpointer()
        
        from app.agents.graph_system import initialize_graph_system
        
        agent = await initialize_graph_system(
            db=db,
            openai_key=settings.OPENAI_API_KEY,
            checkpointer=checkpointer
        )
        
        try:
            greeting_sent = await handle_initial_greeting(websocket, agent, session_token)
            
            if not greeting_sent:
                ws_closed = True
                return
            
            await handle_conversation_loop(websocket, agent, session_token, db)
            ws_closed = True
        except WebSocketDisconnect:
            ws_closed = True
            logger.info(f"Cliente desconectado: {session_token}")
        
    except Exception as e:
        ws_closed = True
        logger.error(f"Error critico en WebSocket {session_token}: {str(e)}", exc_info=True)
        try:
            await send_error_message(websocket)
        except:
            pass
    finally:
        cleanup_connection(client_host, db, websocket, ws_closed)


async def validate_connection(websocket: WebSocket, client_host: str) -> bool:
    can_connect, message = await ws_manager.can_connect(client_host)
    
    if not can_connect:
        await websocket.close(code=1008, reason=message)
        return False
    
    allowed, rate_message = await websocket_rate_limiter.check_rate_limit(
        type('Request', (), {'client': websocket.client, 'headers': websocket.headers})()
    )
    
    if not allowed:
        await websocket.close(code=1008, reason=rate_message)
        return False
    
    return True


async def handle_initial_greeting(websocket: WebSocket, agent, session_token: str) -> bool:
    config = {"configurable": {"thread_id": session_token}}
    
    checkpoint = await agent.checkpointer.aget_tuple(config)
    
    if checkpoint and checkpoint.checkpoint.get("channel_values"):
        existing_state = checkpoint.checkpoint["channel_values"]
        
        if existing_state.get("workflow_stage") == "awaiting_position":
            await websocket.send_json({
                "type": "greeting",
                "data": {
                    "response": "Sesion recuperada. Por favor selecciona una posicion.",
                    "workflow_stage": "awaiting_position"
                }
            })
            return True
        
        if existing_state.get("workflow_stage") == "awaiting_start":
            await websocket.send_json({
                "type": "greeting",
                "data": {
                    "response": "Sesión activa. Escribe 'Listo' cuando estés preparado para comenzar el test.",
                    "workflow_stage": "awaiting_start",
                    "current_test": existing_state.get("current_test", 0),
                    "current_question": existing_state.get("current_question", 0)
                }
            })
            return True
        
        if existing_state.get("workflow_stage") != "initial":
            last_message = None
            messages = existing_state.get("messages", [])
            for msg in reversed(messages):
                if hasattr(msg, 'content'):
                    last_message = msg.content
                    break
            
            response_data = {
                "type": "greeting",
                "data": {
                    "response": last_message or "Sesion activa. Continua donde lo dejaste.",
                    "workflow_stage": existing_state.get("workflow_stage", "unknown")
                }
            }
            
            if existing_state.get("current_test", 0) > 0:
                response_data["data"]["current_test"] = existing_state["current_test"]
                response_data["data"]["current_question"] = existing_state["current_question"]
            
            await websocket.send_json(response_data)
            return True
    
    initial_result = await agent.process_message(
        session_token=session_token,
        message=None,
        initial_state=None
    )
    
    if initial_result.get("should_close"):
        try:
            await websocket.send_json({
                "type": "close",
                "data": {
                    "message": initial_result["response"]
                }
            })
        except Exception:
            pass
        return False
    
    await websocket.send_json({
        "type": "greeting",
        "data": {
            "response": initial_result["response"],
            "workflow_stage": initial_result.get("workflow_stage", "initial")
        }
    })
    
    return True


async def handle_conversation_loop(websocket: WebSocket, agent, session_token: str, db: AsyncSession):
    message_count = 0
    max_messages = 50
    
    while True:
        data = await websocket.receive_text()
        message_data = json.loads(data)
        
        if message_data.get("type") == "ping":
            await websocket.send_json({"type": "pong"})
            continue
        
        if message_data.get("type") == "cv_upload":
            await handle_cv_upload(websocket, message_data, session_token, db, agent)
            continue
        
        message_count += 1
        if message_count > max_messages:
            await websocket.send_json({
                "type": "error",
                "message": "Limite de mensajes alcanzado"
            })
            break
        
        result = await agent.process_message(
            session_token=session_token,
            message=message_data["message"],
            initial_state=None
        )
        
        response_data = {
            "type": "message",
            "data": {
                "response": result["response"],
                "workflow_stage": result.get("workflow_stage", "unknown"),
                "is_complete": result["is_complete"]
            }
        }
        
        if result.get("current_test", 0) > 0:
            response_data["data"]["current_test"] = result["current_test"]
            response_data["data"]["current_question"] = result["current_question"]
        
        await websocket.send_json(response_data)
        
        if result["should_close"]:
            await websocket.send_json({
                "type": "close",
                "data": {
                    "message": "Evaluacion finalizada",
                    "is_complete": result["is_complete"]
                }
            })
            break


async def handle_cv_upload(websocket: WebSocket, message_data: dict, session_token: str, db: AsyncSession, agent):
    try:
        import base64
        
        file_content_b64 = message_data.get("file_content")
        file_name = message_data.get("file_name", "cv.pdf")
        
        if not file_content_b64:
            await websocket.send_json({
                "type": "error",
                "message": "Faltan datos del archivo"
            })
            return
        
        config = {"configurable": {"thread_id": session_token}}
        
        checkpoint = await agent.checkpointer.aget_tuple(config)
        
        if not checkpoint or not checkpoint.checkpoint.get("channel_values"):
            await websocket.send_json({
                "type": "error",
                "message": "No hay sesion activa"
            })
            return
        
        channel_values = checkpoint.checkpoint["channel_values"]
        position_id = channel_values.get("position_id")
        
        if not position_id:
            await websocket.send_json({
                "type": "error",
                "message": "Debes seleccionar una posicion primero"
            })
            return
        
        file_content = base64.b64decode(file_content_b64)
        
        if len(file_content) > 5_000_000:
            await websocket.send_json({
                "type": "error",
                "message": "Archivo muy grande (max 5MB)"
            })
            return
        
        checksum = hashlib.sha256(file_content).hexdigest()
        
        parsed_data = await parse_cv_with_llm(file_content)
        
        if not parsed_data.get("email"):
            await websocket.send_json({
                "type": "error",
                "message": "No se pudo extraer email del CV"
            })
            return
        
        prospect = await find_or_create_prospect(db, parsed_data)
        
        await store_cv_document(
            db, prospect.id, file_name, file_content, checksum
        )
        
        await db.flush()
        await db.commit()
        
        update_state = {
            "cv_uploaded": True,
            "prospect_id": str(prospect.id),
            "prospect_name": f"{prospect.first_name} {prospect.last_name}",
            "prospect_email": prospect.email,
            "workflow_stage": "cv_just_uploaded"
        }
        
        result = await agent.process_message(
            session_token=session_token,
            message=None,
            initial_state=update_state,
            event_type="cv_uploaded"
        )
        
        await websocket.send_json({
            "type": "cv_processed",
            "data": {
                "response": result["response"],
                "prospect_id": str(prospect.id),
                "workflow_stage": result.get("workflow_stage")
            }
        })
        
    except Exception as e:
        logger.error(f"Error procesando CV: {e}", exc_info=True)
        await db.rollback()
        await websocket.send_json({
            "type": "error",
            "message": "Error procesando CV"
        })


async def find_or_create_prospect(db: AsyncSession, parsed_data: dict):
    from sqlalchemy import select
    
    if parsed_data.get("email"):
        result = await db.execute(
            select(Prospect).where(Prospect.email == parsed_data["email"])
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            existing.first_name = parsed_data.get("first_name") or existing.first_name
            existing.last_name = parsed_data.get("last_name") or existing.last_name
            existing.phone = parsed_data.get("phone") or existing.phone
            existing.cv_summary = parsed_data
            
            await db.flush()
            return existing
    
    prospect = Prospect(
        first_name=parsed_data.get("first_name"),
        last_name=parsed_data.get("last_name"),
        email=parsed_data.get("email"),
        phone=parsed_data.get("phone"),
        parsed_from_cv=True,
        cv_summary=parsed_data
    )
    
    db.add(prospect)
    await db.flush()
    
    return prospect


async def store_cv_document(db: AsyncSession, prospect_id: UUID, file_name: str, file_content: bytes, checksum: str):
    file_size = len(file_content)
    storage_type = "database" if file_size < 500_000 else "s3"
    
    if storage_type == "database":
        document = ProspectDocument(
            prospect_id=prospect_id,
            document_type="cv",
            file_name=f"cv_{prospect_id}.pdf",
            original_file_name=file_name,
            storage_type="database",
            file_data=file_content,
            file_size=file_size,
            mime_type="application/pdf",
            checksum=checksum
        )
    else:
        from app.services.r2_storage import upload_to_r2
        
        storage_path = await upload_to_r2(
            file_content=file_content,
            prospect_id=str(prospect_id),
            filename=file_name
        )
        
        document = ProspectDocument(
            prospect_id=prospect_id,
            document_type="cv",
            file_name=f"cv_{prospect_id}.pdf",
            original_file_name=file_name,
            storage_type="s3",
            storage_path=storage_path,
            file_size=file_size,
            mime_type="application/pdf",
            checksum=checksum
        )
    
    db.add(document)
    return document


async def send_error_message(websocket: WebSocket):
    try:
        await websocket.send_json({
            "type": "error",
            "message": "Error interno del servidor"
        })
    except:
        pass


def cleanup_connection(client_host: str, db, websocket: WebSocket, ws_closed: bool):
    ws_manager.disconnect(client_host)
    
    if db:
        asyncio.create_task(db.close())


@router.get("/health")
async def chat_health():
    ws_url = build_websocket_url()
    
    return {
        "status": "online",
        "endpoints": {
            "websocket": ws_url
        },
        "environment": settings.APP_ENV,
        "features": {
            "rag_enabled": True,
            "cv_parsing": True,
            "postgres_checkpointer": True,
            "cv_upload_via_ws": True,
            "position_embeddings": True
        },
        "security": {
            "rate_limiting": True,
            "max_connections_per_ip": 3
        }
    }


def build_websocket_url() -> str:
    if settings.APP_ENV == "production":
        protocol = "wss" if settings.USE_SSL else "ws"
        return f"{protocol}://{settings.DOMAIN}/api/v1/chat/ws/{{session_token}}"
    
    return f"ws://{settings.DOMAIN}/api/v1/chat/ws/{{session_token}}"


@router.post("/checkpoint/clear/{session_token}")
async def clear_checkpoint(session_token: str):
    try:
        checkpointer = get_checkpointer()
        
        def delete_sync():
            with checkpointer._pool.connection() as conn:
                conn.execute(
                    text("DELETE FROM graph_checkpoints WHERE thread_id = :thread_id"),
                    {"thread_id": session_token}
                )
                conn.commit()
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, delete_sync)
        
        return {"success": True, "message": "Checkpoint eliminado"}
    except Exception as e:
        logger.error(f"Error eliminando checkpoint: {e}")
        return {"success": False, "error": str(e)}