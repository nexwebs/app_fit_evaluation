"""
app/tools/rag_tools.py
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.services.embeddings import embedding_service
from typing import Dict, Any, List, Optional


async def retrieve_evaluation_context(
    db: AsyncSession,
    question_id: str,
    question_text: str,
    prospect_cv: Optional[Dict[str, Any]] = None,
    limit: int = 3
) -> str:
    query_embedding = embedding_service.encode_single(question_text)
    context_parts = []
    
    if prospect_cv:
        cv_context = build_cv_context(prospect_cv)
        if cv_context:
            context_parts.append(cv_context)
    
    similar_answers = await fetch_similar_answers(db, question_id, query_embedding, limit)
    if similar_answers:
        context_parts.append(format_similar_answers(similar_answers))
    
    knowledge_base = await fetch_knowledge_base(db, query_embedding)
    if knowledge_base:
        context_parts.append(format_knowledge_base(knowledge_base))
    
    return "\n".join(context_parts) if context_parts else ""


async def fetch_similar_answers(db: AsyncSession, question_id: str, query_embedding, limit: int):
    result = await db.execute(
        text("""
            SELECT 
                ea.answer_text,
                ea.score,
                1 - (ea.answer_embedding <=> CAST(:embedding AS vector)) as similarity
            FROM evaluation_answers ea
            JOIN evaluations e ON e.id = ea.evaluation_id
            WHERE ea.question_id = :q_id
              AND ea.score >= 70
              AND e.status = 'completed'
              AND (1 - (ea.answer_embedding <=> CAST(:embedding AS vector))) >= 0.7
            ORDER BY ea.score DESC, similarity DESC
            LIMIT :limit
        """),
        {
            "embedding": str(query_embedding),
            "q_id": question_id,
            "limit": limit
        }
    )
    return result.fetchall()


async def fetch_knowledge_base(db: AsyncSession, query_embedding):
    result = await db.execute(
        text("""
            SELECT 
                tipo,
                titulo,
                contenido,
                1 - (embedding <=> CAST(:embedding AS vector)) as similarity
            FROM conocimiento_rag
            WHERE activo = TRUE
              AND (1 - (embedding <=> CAST(:embedding AS vector))) >= 0.65
            ORDER BY similarity DESC
            LIMIT 2
        """),
        {"embedding": str(query_embedding)}
    )
    return result.fetchall()


def format_similar_answers(rows) -> str:
    parts = ["\nEJEMPLOS DE RESPUESTAS EXITOSAS:"]
    for answer_text, score, sim in rows:
        truncated = answer_text[:120] + "..." if len(answer_text) > 120 else answer_text
        parts.append(f"- Score {score:.0f} ({sim:.2f} similitud): {truncated}")
    return "\n".join(parts)


def format_knowledge_base(rows) -> str:
    parts = ["\nCONOCIMIENTO BASE:"]
    for tipo, titulo, contenido, sim in rows:
        truncated = contenido[:150] + "..." if len(contenido) > 150 else contenido
        parts.append(f"[{tipo}] {titulo}: {truncated}")
    return "\n".join(parts)


def build_cv_context(cv_summary: Dict[str, Any]) -> str:
    parts = ["PERFIL DEL CANDIDATO:"]
    
    experience = cv_summary.get("years_experience", 0)
    if experience > 0:
        parts.append(f"- Experiencia: {experience} años")
    
    education = cv_summary.get("education")
    if education:
        parts.append(f"- Educación: {education}")
    
    skills = cv_summary.get("skills", [])
    if skills:
        top_skills = ', '.join(skills[:5])
        parts.append(f"- Habilidades clave: {top_skills}")
    
    work_history = cv_summary.get("work_history", [])
    if work_history:
        parts.append(f"- Empresas previas: {len(work_history)}")
        if work_history[0].get("company"):
            parts.append(f"  Última: {work_history[0]['company']} ({work_history[0].get('position', 'N/A')})")
    
    certifications = cv_summary.get("certifications", [])
    if certifications:
        parts.append(f"- Certificaciones: {', '.join(certifications[:3])}")
    
    languages = cv_summary.get("languages", [])
    if languages:
        parts.append(f"- Idiomas: {', '.join(languages)}")
    
    return "\n".join(parts)


async def search_similar_evaluations(
    db: AsyncSession,
    position_id: str,
    min_score: float = 70.0,
    limit: int = 5
) -> List[Dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT 
                e.id,
                p.first_name || ' ' || p.last_name as name,
                e.total_score,
                e.test_1_score,
                e.test_2_score,
                e.completed_at
            FROM evaluations e
            JOIN prospects p ON p.id = e.prospect_id
            WHERE e.position_id = :pos_id
              AND e.status = 'completed'
              AND e.total_score >= :min_score
            ORDER BY e.total_score DESC
            LIMIT :limit
        """),
        {
            "pos_id": position_id,
            "min_score": min_score,
            "limit": limit
        }
    )
    
    rows = result.fetchall()
    
    return [
        {
            "id": str(row[0]),
            "name": row[1],
            "total_score": float(row[2]),
            "test_1_score": float(row[3]),
            "test_2_score": float(row[4]),
            "completed_at": row[5].isoformat() if row[5] else None
        }
        for row in rows
    ]


async def get_question_statistics(
    db: AsyncSession,
    question_id: str
) -> Dict[str, Any]:
    result = await db.execute(
        text("""
            SELECT 
                COUNT(*) as total_answers,
                AVG(score) as avg_score,
                STDDEV(score) as stddev_score,
                MIN(score) as min_score,
                MAX(score) as max_score,
                COUNT(CASE WHEN score >= 70 THEN 1 END) as passed_count
            FROM evaluation_answers
            WHERE question_id = :q_id
        """),
        {"q_id": question_id}
    )
    
    row = result.fetchone()
    
    if not row or row[0] == 0:
        return {
            "total_answers": 0,
            "avg_score": 0.0,
            "difficulty": "unknown"
        }
    
    stats = build_statistics(row)
    stats["difficulty"] = calculate_difficulty(stats["avg_score"])
    
    return stats


def build_statistics(row) -> Dict[str, Any]:
    return {
        "total_answers": row[0],
        "avg_score": float(row[1]) if row[1] else 0.0,
        "stddev_score": float(row[2]) if row[2] else 0.0,
        "min_score": float(row[3]) if row[3] else 0.0,
        "max_score": float(row[4]) if row[4] else 0.0,
        "passed_count": row[5],
        "pass_rate": (row[5] / row[0] * 100) if row[0] > 0 else 0.0
    }


def calculate_difficulty(avg_score: float) -> str:
    if avg_score >= 75:
        return "fácil"
    elif avg_score >= 60:
        return "moderada"
    else:
        return "difícil"


async def update_question_difficulty(
    db: AsyncSession,
    question_id: str
) -> bool:
    try:
        stats = await get_question_statistics(db, question_id)
        
        if stats["total_answers"] < 5:
            return False
        
        difficulty_map = {
            "fácil": "easy",
            "moderada": "medium",
            "difícil": "hard"
        }
        
        difficulty = difficulty_map.get(stats["difficulty"], "medium")
        
        await db.execute(
            text("""
                UPDATE question_templates
                SET 
                    metadata = COALESCE(metadata, '{}'::jsonb) || 
                    jsonb_build_object(
                        'avg_score', :avg_score,
                        'difficulty', :difficulty,
                        'total_answers', :total_answers,
                        'pass_rate', :pass_rate
                    )
                WHERE id = :q_id
            """),
            {
                "q_id": question_id,
                "avg_score": stats["avg_score"],
                "difficulty": difficulty,
                "total_answers": stats["total_answers"],
                "pass_rate": stats["pass_rate"]
            }
        )
        
        await db.commit()
        return True
        
    except Exception:
        return False