from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from decimal import Decimal


class ProspectBase(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None


class ProspectCreate(ProspectBase):
    parsed_from_cv: bool = False
    cv_summary: Optional[Dict[str, Any]] = {}


class ProspectUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    cv_summary: Optional[Dict[str, Any]] = None


class ProspectResponse(ProspectBase):
    id: UUID
    parsed_from_cv: bool
    cv_summary: Dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class JobPositionBase(BaseModel):
    title: str
    description: Optional[str] = None
    salary: Optional[Decimal] = None
    currency: str = "PEN"
    slots_available: int = 1
    requirements: Optional[Dict[str, Any]] = {}


class JobPositionCreate(JobPositionBase):
    is_active: bool = True


class JobPositionResponse(JobPositionBase):
    id: UUID
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class QuestionTemplateBase(BaseModel):
    question_text: str
    question_type: str
    test_number: int
    question_order: int
    validation_type: str
    expected_keywords: Optional[List[str]] = []
    ideal_answer: Optional[str] = None
    min_similarity: Optional[Decimal] = Decimal("0.65")
    weight: Optional[Decimal] = Decimal("1.00")

    @field_validator('question_type')
    @classmethod
    def validate_question_type(cls, v):
        if v not in ['role_specific', 'transversal']:
            raise ValueError('question_type must be role_specific or transversal')
        return v

    @field_validator('test_number')
    @classmethod
    def validate_test_number(cls, v):
        if v not in [1, 2]:
            raise ValueError('test_number must be 1 or 2')
        return v

    @field_validator('validation_type')
    @classmethod
    def validate_validation_type(cls, v):
        if v not in ['semantic', 'boolean', 'keyword', 'numeric']:
            raise ValueError('validation_type must be semantic, boolean, keyword or numeric')
        return v


class QuestionTemplateCreate(QuestionTemplateBase):
    position_id: UUID
    is_active: bool = True


class QuestionTemplateResponse(QuestionTemplateBase):
    id: UUID
    position_id: UUID
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class EvaluationCreate(BaseModel):
    prospect_id: UUID
    position_id: UUID


class EvaluationUpdate(BaseModel):
    status: Optional[str] = None
    current_test: Optional[int] = None
    current_question: Optional[int] = None
    conversation_history: Optional[List[Dict]] = None


class EvaluationResponse(BaseModel):
    id: UUID
    prospect_id: UUID
    position_id: UUID
    session_token: str
    status: str
    current_test: int
    current_question: int
    test_1_score: Optional[Decimal] = None
    test_2_score: Optional[Decimal] = None
    total_score: Optional[Decimal] = None
    passed_ai: Optional[bool] = None
    email_sent: bool
    started_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AnswerSubmit(BaseModel):
    answer_text: str
    response_time_seconds: Optional[int] = None


class EvaluationAnswerResponse(BaseModel):
    id: UUID
    evaluation_id: UUID
    question_id: UUID
    answer_text: str
    score: Decimal
    similarity_score: Optional[Decimal] = None
    matched_keywords: List[str]
    feedback_points: Dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class CVUploadRequest(BaseModel):
    position_id: UUID
    file_name: str
    file_size: int
    mime_type: str = "application/pdf"


class CVUploadResponse(BaseModel):
    prospect_id: UUID
    document_id: UUID
    parsed_data: Dict[str, Any]
    message: str


class ChatMessageRequest(BaseModel):
    session_token: str
    message: str


class ChatMessageResponse(BaseModel):
    response: str
    session_token: str
    current_test: int
    current_question: int
    total_questions_test: int
    is_evaluation_complete: bool


class EvaluationResult(BaseModel):
    evaluation_id: UUID
    prospect_name: str
    position: str
    total_score: Decimal
    test_1_score: Decimal
    test_2_score: Decimal
    passed: bool
    feedback: Dict[str, Any]
    completed_at: datetime


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class SesionCreate(BaseModel):
    usuario_id: UUID
    token_hash: str
    expira_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class SesionResponse(BaseModel):
    id: UUID
    usuario_id: UUID
    expira_at: datetime
    revocado: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class HRActionCreate(BaseModel):
    evaluation_id: UUID
    action_type: str
    notes: Optional[str] = None
    action_metadata: Optional[Dict[str, Any]] = {}

    @field_validator('action_type')
    @classmethod
    def validate_action_type(cls, v):
        valid_types = [
            'approved_for_interview', 'rejected', 'scheduled_interview',
            'added_notes', 'downloaded_cv', 'sent_email'
        ]
        if v not in valid_types:
            raise ValueError(f'action_type must be one of {valid_types}')
        return v


class HRActionResponse(BaseModel):
    id: UUID
    user_id: UUID
    evaluation_id: UUID
    action_type: str
    notes: Optional[str]
    action_metadata: Dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class PendingProspectResponse(BaseModel):
    evaluation_id: UUID
    prospect_id: UUID
    prospect_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    position: str
    total_score: Optional[float] = None
    test_1_score: Optional[float] = None
    test_2_score: Optional[float] = None
    completed_at: Optional[datetime] = None
    status: str
    has_cv: bool
    document_id: Optional[UUID] = None


class EvaluationDetailResponse(BaseModel):
    evaluation_id: UUID
    prospect_name: str
    email: Optional[str]
    phone: Optional[str]
    cv_summary: Dict[str, Any]
    position: str
    salary: Optional[Decimal]
    status: str
    total_score: Decimal
    test_1_score: Decimal
    test_2_score: Decimal
    passed_ai: bool
    duration_seconds: Optional[int]
    completed_at: datetime
    answers_detail: List[Dict[str, Any]]


class ReapplicationCheck(BaseModel):
    can_apply: bool
    reason: str
    last_evaluation_date: Optional[datetime] = None
    days_remaining: int


class GraphCheckpointResponse(BaseModel):
    checkpoint_id: str
    checkpoint_data: Dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class SlotsUpdate(BaseModel):
    slots_available: int = Field(ge=0, description="Número de vacantes disponibles")