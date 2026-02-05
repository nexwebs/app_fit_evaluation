"""
app/api/admin_embeddings.py
Endpoints para gestion de embeddings de posiciones
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.services.database import get_db
from app.services.embeddings import embedding_service
from app.services.position_embeddings import (
    generate_position_embedding,
    delete_position_embedding,
    regenerate_all_position_embeddings,
    search_positions_by_cv,
    get_position_context
)
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class CVSearchRequest(BaseModel):
    cv_summary: dict
    limit: Optional[int] = 3


class GenerateEmbeddingsResponse(BaseModel):
    success: bool
    position_title: str
    embeddings_generated: int
    message: str


@router.post("/questions/generate/{position_title}", response_model=GenerateEmbeddingsResponse)
async def generate_question_embeddings(
    position_title: str,
    db: AsyncSession = Depends(get_db)
):
    try:
        result = await db.execute(
            text("""
                SELECT qt.id, qt.question_text, qt.ideal_answer
                FROM question_templates qt
                JOIN job_positions jp ON qt.position_id = jp.id
                WHERE jp.title = :position_title
                AND qt.validation_type = 'semantic'
                AND qt.ideal_embedding IS NULL
                ORDER BY qt.test_number, qt.question_order
            """),
            {"position_title": position_title}
        )
        
        questions = result.fetchall()
        
        if not questions:
            return GenerateEmbeddingsResponse(
                success=True,
                position_title=position_title,
                embeddings_generated=0,
                message="No hay preguntas pendientes"
            )
        
        success_count = 0
        
        for question_id, question_text, ideal_answer in questions:
            if not ideal_answer or not ideal_answer.strip():
                continue
            
            try:
                embedding = await embedding_service.embed_text(ideal_answer)
                
                await db.execute(
                    text("""
                        UPDATE question_templates 
                        SET ideal_embedding = :embedding::vector 
                        WHERE id = :question_id
                    """),
                    {
                        "question_id": str(question_id),
                        "embedding": embedding
                    }
                )
                
                success_count += 1
                
            except Exception as e:
                print(f"Error procesando pregunta {question_id}: {e}")
                continue
        
        await db.commit()
        
        return GenerateEmbeddingsResponse(
            success=True,
            position_title=position_title,
            embeddings_generated=success_count,
            message=f"Se generaron {success_count} embeddings exitosamente"
        )
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/questions/generate-all")
async def generate_all_question_embeddings(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            text("SELECT DISTINCT title FROM job_positions WHERE is_active = true")
        )
        
        positions = [row[0] for row in result.fetchall()]
        results = []
        total_generated = 0
        
        for position_title in positions:
            result = await db.execute(
                text("""
                    SELECT qt.id, qt.ideal_answer
                    FROM question_templates qt
                    JOIN job_positions jp ON qt.position_id = jp.id
                    WHERE jp.title = :position_title
                    AND qt.validation_type = 'semantic'
                    AND qt.ideal_embedding IS NULL
                """),
                {"position_title": position_title}
            )
            
            questions = result.fetchall()
            count = 0
            
            for question_id, ideal_answer in questions:
                if not ideal_answer:
                    continue
                
                try:
                    embedding = await embedding_service.embed_text(ideal_answer)
                    
                    await db.execute(
                        text("""
                            UPDATE question_templates 
                            SET ideal_embedding = :embedding::vector 
                            WHERE id = :question_id
                        """),
                        {
                            "question_id": str(question_id),
                            "embedding": embedding
                        }
                    )
                    
                    count += 1
                    
                except Exception as e:
                    print(f"Error: {e}")
                    continue
            
            results.append({
                "position": position_title,
                "embeddings_generated": count
            })
            
            total_generated += count
        
        await db.commit()
        
        return {
            "success": True,
            "total_embeddings_generated": total_generated,
            "positions_processed": len(positions),
            "details": results
        }
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/questions/status/{position_title}")
async def check_embeddings_status(
    position_title: str,
    db: AsyncSession = Depends(get_db)
):
    try:
        result = await db.execute(
            text("""
                SELECT 
                    COUNT(*) FILTER (WHERE validation_type = 'semantic') as total_semantic,
                    COUNT(*) FILTER (WHERE validation_type = 'semantic' AND ideal_embedding IS NOT NULL) as with_embedding,
                    COUNT(*) FILTER (WHERE validation_type = 'semantic' AND ideal_embedding IS NULL) as missing_embedding
                FROM question_templates qt
                JOIN job_positions jp ON qt.position_id = jp.id
                WHERE jp.title = :position_title
                AND qt.is_active = true
            """),
            {"position_title": position_title}
        )
        
        row = result.fetchone()
        
        if not row or row[0] == 0:
            raise HTTPException(status_code=404, detail="Posición no encontrada o sin preguntas")
        
        return {
            "success": True,
            "position_title": position_title,
            "total_semantic_questions": row[0],
            "questions_with_embedding": row[1],
            "questions_missing_embedding": row[2],
            "completion_percentage": round((row[1] / row[0]) * 100, 2) if row[0] > 0 else 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/positions/{position_id}/embedding")
async def create_position_embedding(
    position_id: str,
    db: AsyncSession = Depends(get_db)
):
    try:
        success = await generate_position_embedding(db, position_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Position not found")
        
        await db.commit()
        
        return {
            "success": True,
            "position_id": position_id,
            "message": "Embedding generated successfully"
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/positions/{position_id}/embedding")
async def remove_position_embedding(
    position_id: str,
    db: AsyncSession = Depends(get_db)
):
    try:
        success = await delete_position_embedding(db, position_id)
        await db.commit()
        
        return {
            "success": success,
            "position_id": position_id
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/positions/embeddings/regenerate")
async def regenerate_embeddings(db: AsyncSession = Depends(get_db)):
    try:
        result = await regenerate_all_position_embeddings(db)
        
        return {
            "success": True,
            "statistics": result
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/positions/search-by-cv")
async def search_by_cv(
    request: CVSearchRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        matches = await search_positions_by_cv(
            db,
            request.cv_summary,
            request.limit
        )
        
        return {
            "success": True,
            "matches": matches
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions/{position_id}/context")
async def get_context(
    position_id: str,
    db: AsyncSession = Depends(get_db)
):
    try:
        context = await get_position_context(db, position_id)
        
        if not context:
            raise HTTPException(status_code=404, detail="Context not found")
        
        return {
            "success": True,
            "position_id": position_id,
            "context": context
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))