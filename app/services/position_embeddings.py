"""
app/services/position_embeddings.py
Sistema automatico de embeddings para posiciones
Genera contexto enriquecido que el agente puede consultar
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from uuid import UUID
from typing import Dict, List, Any
from app.services.embeddings import embedding_service
from app.models import JobPosition


async def generate_position_embedding(db: AsyncSession, position_id: str) -> bool:
    try:
        result = await db.execute(
            select(JobPosition).where(JobPosition.id == UUID(position_id))
        )
        position = result.scalar_one_or_none()
        
        if not position:
            return False
        
        context = _build_position_context(position)
        
        embedding = await embedding_service.embed_text(context)
        
        await db.execute(
            text("""
                INSERT INTO conocimiento_rag (tipo, titulo, contenido, embedding, metadata)
                VALUES ('job_position', :title, :content, :embedding::vector, :metadata::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    contenido = EXCLUDED.contenido,
                    embedding = EXCLUDED.embedding,
                    updated_at = CURRENT_TIMESTAMP
            """),
            {
                "title": position.title,
                "content": context,
                "embedding": embedding,
                "metadata": {"position_id": position_id}
            }
        )
        
        return True
        
    except Exception as e:
        print(f"Error generando embedding: {e}")
        return False


async def delete_position_embedding(db: AsyncSession, position_id: str) -> bool:
    try:
        result = await db.execute(
            text("""
                DELETE FROM conocimiento_rag
                WHERE tipo = 'job_position'
                AND metadata->>'position_id' = :position_id
                RETURNING id
            """),
            {"position_id": position_id}
        )
        
        return result.fetchone() is not None
        
    except Exception:
        return False


async def regenerate_all_position_embeddings(db: AsyncSession) -> Dict[str, Any]:
    result = await db.execute(
        select(JobPosition).where(JobPosition.is_active == True)
    )
    positions = result.scalars().all()
    
    success_count = 0
    failed = []
    
    for position in positions:
        success = await generate_position_embedding(db, str(position.id))
        if success:
            success_count += 1
        else:
            failed.append(str(position.id))
    
    await db.commit()
    
    return {
        "total_positions": len(positions),
        "successful": success_count,
        "failed": len(failed),
        "failed_ids": failed
    }


async def search_positions_by_cv(
    db: AsyncSession,
    cv_summary: dict,
    limit: int = 3
) -> List[Dict[str, Any]]:
    cv_text = _extract_cv_text(cv_summary)
    
    query_embedding = await embedding_service.embed_text(cv_text)
    
    result = await db.execute(
        text("""
            SELECT 
                metadata->>'position_id' as position_id,
                titulo,
                contenido,
                1 - (embedding <=> :query_embedding::vector) as similarity
            FROM conocimiento_rag
            WHERE tipo = 'job_position'
            AND activo = true
            ORDER BY embedding <=> :query_embedding::vector
            LIMIT :limit
        """),
        {
            "query_embedding": query_embedding,
            "limit": limit
        }
    )
    
    matches = []
    for row in result.fetchall():
        matches.append({
            "position_id": row[0],
            "title": row[1],
            "description": row[2],
            "similarity": round(float(row[3]), 4)
        })
    
    return matches


async def get_position_context(db: AsyncSession, position_id: str) -> str:
    result = await db.execute(
        select(JobPosition).where(JobPosition.id == UUID(position_id))
    )
    position = result.scalar_one_or_none()
    
    if not position:
        return None
    
    return _build_position_context(position)


def _build_position_context(position: JobPosition) -> str:
    context = f"Posición: {position.title}\n\n"
    
    if position.description:
        context += f"Descripción: {position.description}\n\n"
    
    context += f"Salario: {position.currency} {position.salary}\n"
    context += f"Vacantes: {position.slots_available}\n\n"
    
    if position.requirements:
        context += "Requisitos:\n"
        for key, value in position.requirements.items():
            context += f"- {key}: {value}\n"
    
    return context


def _extract_cv_text(cv_summary: dict) -> str:
    parts = []
    
    if "experience" in cv_summary:
        parts.append(f"Experiencia: {cv_summary['experience']}")
    
    if "skills" in cv_summary:
        skills = ", ".join(cv_summary["skills"]) if isinstance(cv_summary["skills"], list) else cv_summary["skills"]
        parts.append(f"Habilidades: {skills}")
    
    if "education" in cv_summary:
        parts.append(f"Educación: {cv_summary['education']}")
    
    return " ".join(parts)