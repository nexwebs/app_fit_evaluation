import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv() 

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:adminp@localhost:5432/fitdb_evaluation")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is required")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=30.0, max_retries=3)


async def generate_embedding(text: str) -> list[float]:
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
        dimensions=1536
    )
    return response.data[0].embedding


async def generate_embeddings_for_position(session: AsyncSession, position_title: str):
    print(f"\n{'='*60}")
    print(f"Generando embeddings para: {position_title}")
    print(f"{'='*60}\n")
    
    result = await session.execute(
        text("""
            SELECT qt.id, qt.question_text, qt.ideal_answer, qt.validation_type
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
        print(f"✓ No hay preguntas pendientes para '{position_title}'")
        return 0
    
    print(f"Encontradas {len(questions)} preguntas semánticas sin embeddings\n")
    
    success_count = 0
    
    for idx, (question_id, question_text, ideal_answer, validation_type) in enumerate(questions, 1):
        try:
            print(f"[{idx}/{len(questions)}] Procesando pregunta: {question_id}")
            print(f"  Texto: {question_text[:80]}...")
            
            if not ideal_answer or not ideal_answer.strip():
                print(f"  ⚠ Saltando: sin respuesta ideal")
                continue
            
            embedding = await generate_embedding(ideal_answer)
            
            await session.execute(
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
            
            await session.commit()
            success_count += 1
            
            print(f"  ✓ Embedding generado y guardado")
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
            await session.rollback()
            continue
    
    return success_count


async def main():
    print("\n" + "="*60)
    print("GENERADOR DE EMBEDDINGS PARA PREGUNTAS")
    print("="*60)
    
    async with async_session_factory() as session:
        try:
            result = await session.execute(
                text("SELECT title FROM job_positions WHERE is_active = true ORDER BY title")
            )
            positions = [row[0] for row in result.fetchall()]
            
            if not positions:
                print("\n✗ No hay posiciones activas en la base de datos")
                return
            
            print(f"\nPosiciones activas encontradas: {len(positions)}")
            for pos in positions:
                print(f"  - {pos}")
            
            total_generated = 0
            
            for position_title in positions:
                count = await generate_embeddings_for_position(session, position_title)
                total_generated += count
            
            print(f"\n{'='*60}")
            print(f"RESUMEN")
            print(f"{'='*60}")
            print(f"Total embeddings generados: {total_generated}")
            print(f"Posiciones procesadas: {len(positions)}")
            print(f"\n✓ Proceso completado exitosamente\n")
            
        except Exception as e:
            print(f"\n✗ Error crítico: {e}\n")
            await session.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())