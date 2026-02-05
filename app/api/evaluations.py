from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from typing import List
import uuid
import hashlib

from app.services.database import get_db
from app.models import JobPosition, Prospect, ProspectDocument, Evaluation, QuestionTemplate
from app.schemas import (
    JobPositionResponse, CVUploadResponse,
    EvaluationResponse, EvaluationCreate, PendingProspectResponse,
    EvaluationDetailResponse, ReapplicationCheck
)
from app.tools.cv_parser import parse_cv_with_llm
from app.api.auth import get_current_user, require_role

router = APIRouter()


@router.get("/positions", response_model=List[JobPositionResponse])
async def get_active_positions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(JobPosition).where(
            JobPosition.is_active == True,
            JobPosition.slots_available > 0
        )
    )
    return result.scalars().all()


@router.get("/check-eligibility/{prospect_id}/{position_id}", 
            response_model=ReapplicationCheck)
async def check_reapplication_eligibility(
    prospect_id: uuid.UUID,
    position_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        text("""
            SELECT * FROM can_reapply_to_position(
                :prospect_id,
                :position_id,
                30
            )
        """),
        {
            "prospect_id": str(prospect_id),
            "position_id": str(position_id)
        }
    )
    
    row = result.fetchone()
    
    if not row:
        raise HTTPException(
            status_code=500,
            detail="Error verificando elegibilidad"
        )
    
    return ReapplicationCheck(
        can_apply=row[0],
        reason=row[1],
        last_evaluation_date=row[2],
        days_remaining=row[3]
    )


@router.get("/positions/{position_id}", response_model=JobPositionResponse)
async def get_position(position_id: str, db: AsyncSession = Depends(get_db)):
    position = await fetch_position_by_id(db, position_id)
    
    if not position:
        raise HTTPException(status_code=404, detail="Posición no encontrada")
    
    return position


@router.post("/upload-cv", response_model=CVUploadResponse)
async def upload_cv(
    position_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    validate_file_type(file)
    
    file_content = await file.read()
    validate_file_size(file_content)
    
    checksum = calculate_checksum(file_content)
    parsed_data = await parse_cv_with_llm(file_content)
    
    existing_prospect = await find_prospect_by_email(db, parsed_data.get("email"))
    
    if existing_prospect:
        prospect = existing_prospect
        await update_prospect_cv(db, prospect.id, parsed_data)
    else:
        prospect = await create_prospect(db, parsed_data)
    
    document = await store_cv_document(
        db, prospect.id, file, file_content, checksum
    )
    
    await db.commit()
    
    return CVUploadResponse(
        prospect_id=prospect.id,
        document_id=document.id,
        parsed_data=parsed_data,
        message="CV procesado exitosamente"
    )


@router.post("/start-evaluation", response_model=EvaluationResponse)
async def start_evaluation(
    data: EvaluationCreate,
    db: AsyncSession = Depends(get_db)
):
    await validate_questions_exist(db, data.position_id)
    
    eligibility = await check_prospect_eligibility(
        db, data.prospect_id, data.position_id
    )
    
    if not eligibility["can_apply"]:
        raise HTTPException(
            status_code=400,
            detail=eligibility["reason"]
        )
    
    evaluation = Evaluation(
        prospect_id=data.prospect_id,
        position_id=data.position_id,
        session_token=data.session_token,
        status="in_progress"
    )
    
    db.add(evaluation)
    await db.commit()
    
    return evaluation


@router.get("/pending-prospects", response_model=List[PendingProspectResponse])
async def get_pending_prospects(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        text("SELECT * FROM v_pending_prospects ORDER BY completed_at DESC")
    )
    
    rows = result.fetchall()
    
    return [
        PendingProspectResponse(
            evaluation_id=row[0],
            prospect_id=row[1],
            prospect_name=row[2],
            email=row[3],
            phone=row[4],
            position=row[5],
            total_score=row[6],
            test_1_score=row[7],
            test_2_score=row[8],
            completed_at=row[9],
            status=row[10],
            has_cv=row[11],
            document_id=row[12]
        )
        for row in rows
    ]


@router.get("/evaluation/{evaluation_id}/details", response_model=EvaluationDetailResponse)
async def get_evaluation_details(
    evaluation_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    row = await fetch_evaluation_detail(db, evaluation_id)
    
    if not row:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada")
    
    return EvaluationDetailResponse(
        evaluation_id=row[0],
        prospect_name=row[1],
        email=row[2],
        phone=row[3],
        cv_summary=row[4],
        position=row[5],
        salary=row[6],
        status=row[7],
        total_score=row[8],
        test_1_score=row[9],
        test_2_score=row[10],
        passed_ai=row[11],
        duration_seconds=row[12],
        completed_at=row[13],
        answers_detail=row[14]
    )


@router.get("/cv/{document_id}")
async def download_cv(
    document_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    document = await fetch_document(db, document_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    
    if document.storage_type == "database":
        return create_pdf_response(document)
    else:
        return await create_redirect_response(document)


@router.patch("/positions/{position_id}/deactivate")
async def deactivate_position(
    position_id: str,
    current_user = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    position = await fetch_position_by_id(db, position_id)
    
    if not position:
        raise HTTPException(status_code=404, detail="Posición no encontrada")
    
    position.is_active = False
    await db.commit()
    
    return {"message": "Posición desactivada", "position_id": position_id}


@router.patch("/positions/{position_id}/activate")
async def activate_position(
    position_id: str,
    current_user = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    position = await fetch_position_by_id(db, position_id)
    
    if not position:
        raise HTTPException(status_code=404, detail="Posición no encontrada")
    
    position.is_active = True
    await db.commit()
    
    return {"message": "Posición activada", "position_id": position_id}


@router.patch("/positions/{position_id}/slots")
async def update_slots(
    position_id: str,
    slots_available: int,
    current_user = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    if slots_available < 0:
        raise HTTPException(status_code=400, detail="Slots no pueden ser negativos")
    
    position = await fetch_position_by_id(db, position_id)
    
    if not position:
        raise HTTPException(status_code=404, detail="Posición no encontrada")
    
    position.slots_available = slots_available
    
    if slots_available == 0:
        position.is_active = False
    
    await db.commit()
    
    return {
        "message": "Slots actualizados",
        "position_id": position_id,
        "slots_available": slots_available,
        "is_active": position.is_active
    }


async def fetch_position_by_id(db: AsyncSession, position_id: str):
    result = await db.execute(
        select(JobPosition).where(JobPosition.id == uuid.UUID(position_id))
    )
    return result.scalar_one_or_none()


def validate_file_type(file: UploadFile):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Solo archivos PDF permitidos")


def validate_file_size(file_content: bytes):
    if len(file_content) > 5_000_000:
        raise HTTPException(status_code=400, detail="Archivo muy grande (máx 5MB)")


def calculate_checksum(file_content: bytes) -> str:
    return hashlib.sha256(file_content).hexdigest()


async def find_prospect_by_email(db: AsyncSession, email: str):
    if not email:
        return None
    
    result = await db.execute(
        select(Prospect).where(Prospect.email == email)
    )
    return result.scalar_one_or_none()


async def create_prospect(db: AsyncSession, parsed_data: dict) -> Prospect:
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


async def update_prospect_cv(db: AsyncSession, prospect_id: uuid.UUID, parsed_data: dict):
    await db.execute(
        text("""
            UPDATE prospects 
            SET cv_summary = :cv_summary,
                first_name = COALESCE(:first_name, first_name),
                last_name = COALESCE(:last_name, last_name),
                phone = COALESCE(:phone, phone)
            WHERE id = :prospect_id
        """),
        {
            "prospect_id": str(prospect_id),
            "cv_summary": parsed_data,
            "first_name": parsed_data.get("first_name"),
            "last_name": parsed_data.get("last_name"),
            "phone": parsed_data.get("phone")
        }
    )
    await db.flush()


async def store_cv_document(
    db: AsyncSession,
    prospect_id: uuid.UUID,
    file: UploadFile,
    file_content: bytes,
    checksum: str
) -> ProspectDocument:
    file_size = len(file_content)
    storage_type = "database" if file_size < 500_000 else "s3"
    
    if storage_type == "database":
        document = create_database_document(
            prospect_id, file, file_content, file_size, checksum
        )
    else:
        document = await create_s3_document(
            prospect_id, file, file_content, file_size, checksum
        )
    
    db.add(document)
    return document


def create_database_document(
    prospect_id: uuid.UUID,
    file: UploadFile,
    file_content: bytes,
    file_size: int,
    checksum: str
) -> ProspectDocument:
    return ProspectDocument(
        prospect_id=prospect_id,
        document_type="cv",
        file_name=f"cv_{prospect_id}.pdf",
        original_file_name=file.filename,
        storage_type="database",
        file_data=file_content,
        file_size=file_size,
        mime_type="application/pdf",
        checksum=checksum
    )


async def create_s3_document(
    prospect_id: uuid.UUID,
    file: UploadFile,
    file_content: bytes,
    file_size: int,
    checksum: str
) -> ProspectDocument:
    from app.services.r2_storage import upload_to_r2
    
    storage_path = await upload_to_r2(
        file_content=file_content,
        prospect_id=str(prospect_id),
        filename=file.filename
    )
    
    return ProspectDocument(
        prospect_id=prospect_id,
        document_type="cv",
        file_name=f"cv_{prospect_id}.pdf",
        original_file_name=file.filename,
        storage_type="s3",
        storage_path=storage_path,
        file_size=file_size,
        mime_type="application/pdf",
        checksum=checksum
    )


async def check_prospect_eligibility(
    db: AsyncSession,
    prospect_id: uuid.UUID,
    position_id: uuid.UUID
) -> dict:
    result = await db.execute(
        text("""
            SELECT * FROM can_reapply_to_position(
                :prospect_id,
                :position_id,
                30
            )
        """),
        {
            "prospect_id": str(prospect_id),
            "position_id": str(position_id)
        }
    )
    
    row = result.fetchone()
    
    return {
        "can_apply": row[0],
        "reason": row[1],
        "last_evaluation_date": row[2],
        "days_remaining": row[3]
    }


async def validate_questions_exist(db: AsyncSession, position_id: uuid.UUID):
    result = await db.execute(
        select(QuestionTemplate)
        .where(
            QuestionTemplate.position_id == position_id,
            QuestionTemplate.is_active == True
        )
    )
    questions = result.scalars().all()
    
    if not questions:
        raise HTTPException(
            status_code=400,
            detail="No hay preguntas configuradas para esta posición"
        )


async def fetch_evaluation_detail(db: AsyncSession, evaluation_id: str):
    result = await db.execute(
        text("SELECT * FROM v_evaluation_details WHERE evaluation_id = :eval_id"),
        {"eval_id": evaluation_id}
    )
    return result.fetchone()


async def fetch_document(db: AsyncSession, document_id: str):
    result = await db.execute(
        select(ProspectDocument).where(ProspectDocument.id == uuid.UUID(document_id))
    )
    return result.scalar_one_or_none()


def create_pdf_response(document: ProspectDocument):
    from fastapi.responses import Response
    return Response(
        content=document.file_data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={document.original_file_name}"
        }
    )


async def create_redirect_response(document: ProspectDocument):
    from app.services.r2_storage import get_presigned_url
    from fastapi.responses import RedirectResponse
    
    url = await get_presigned_url(document.storage_path)
    return RedirectResponse(url=url)