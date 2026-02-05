from sqlalchemy import Column, String, Integer, Boolean, Text, DECIMAL, TIMESTAMP, ForeignKey, CheckConstraint, Index, ForeignKeyConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB, BYTEA
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import uuid

from app.services.database import Base


class JobPosition(Base):
    __tablename__ = "job_positions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    salary = Column(DECIMAL(10, 2))
    currency = Column(String(3), default='PEN')
    is_active = Column(Boolean, default=True)
    slots_available = Column(Integer, default=1)
    requirements = Column(JSONB, default=dict)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    questions = relationship("QuestionTemplate", back_populates="position", cascade="all, delete-orphan")
    evaluations = relationship("Evaluation", back_populates="position")


class QuestionTemplate(Base):
    __tablename__ = "question_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    position_id = Column(UUID(as_uuid=True), ForeignKey('job_positions.id', ondelete='CASCADE'))
    question_text = Column(Text, nullable=False)
    question_type = Column(String(20), nullable=False)
    test_number = Column(Integer, nullable=False)
    question_order = Column(Integer, nullable=False)
    validation_type = Column(String(20), nullable=False)
    expected_keywords = Column(JSONB, default=list)
    ideal_answer = Column(Text)
    ideal_embedding = Column(Vector(1536))
    min_similarity = Column(DECIMAL(3, 2), default=0.65)
    weight = Column(DECIMAL(3, 2), default=1.00)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.current_timestamp())

    position = relationship("JobPosition", back_populates="questions")
    answers = relationship("EvaluationAnswer", back_populates="question")

    __table_args__ = (
        CheckConstraint("question_type IN ('role_specific', 'transversal')", name='check_question_type'),
        CheckConstraint("test_number IN (1, 2)", name='check_test_number'),
        CheckConstraint("validation_type IN ('semantic', 'boolean', 'keyword', 'numeric')", name='check_validation_type'),
        Index('idx_questions_position', 'position_id', 'test_number', 'question_order'),
    )


class Prospect(Base):
    __tablename__ = "prospects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name = Column(String(100))
    last_name = Column(String(100))
    email = Column(String(255), unique=True)
    phone = Column(String(50))
    parsed_from_cv = Column(Boolean, default=False)
    cv_summary = Column(JSONB, default=dict)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.current_timestamp())

    documents = relationship("ProspectDocument", back_populates="prospect", cascade="all, delete-orphan")
    evaluations = relationship("Evaluation", back_populates="prospect", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_prospects_email', 'email'),
    )


class ProspectDocument(Base):
    __tablename__ = "prospect_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prospect_id = Column(UUID(as_uuid=True), ForeignKey('prospects.id', ondelete='CASCADE'), nullable=False)
    document_type = Column(String(50), nullable=False, default='cv')
    file_name = Column(String(255), nullable=False)
    original_file_name = Column(String(255), nullable=False)
    storage_type = Column(String(20), nullable=False, default='database')
    storage_path = Column(Text)
    file_data = Column(BYTEA)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    checksum = Column(String(64))
    sharepoint_url = Column(Text)
    sync_status = Column(String(20))
    uploaded_at = Column(TIMESTAMP(timezone=True), server_default=func.current_timestamp())

    prospect = relationship("Prospect", back_populates="documents")
    access_logs = relationship("ProspectDocumentAccessLog", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("storage_type IN ('database', 's3')", name='check_storage_type'),
        CheckConstraint("sync_status IN ('pending', 'synced', 'failed')", name='check_sync_status'),
        CheckConstraint(
            "(storage_type = 'database' AND file_data IS NOT NULL) OR (storage_type = 's3' AND storage_path IS NOT NULL)",
            name='valid_storage'
        ),
        Index('idx_documents_prospect', 'prospect_id'),
    )


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default='recruiter')
    is_active = Column(Boolean, default=True)
    last_login = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.current_timestamp())

    sesiones = relationship("Sesion", back_populates="usuario", cascade="all, delete-orphan")
    hr_actions = relationship("HRAction", back_populates="user")
    document_accesses = relationship("ProspectDocumentAccessLog", back_populates="user")

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'recruiter', 'interviewer', 'vendedor', 'viewer')", name='check_role'),
    )


Usuario = User


class Sesion(Base):
    __tablename__ = "sesiones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False)
    expira_at = Column(TIMESTAMP(timezone=True), nullable=False)
    revocado = Column(Boolean, default=False)
    ip_address = Column(String(50))
    user_agent = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.current_timestamp())

    usuario = relationship("User", back_populates="sesiones")

    __table_args__ = (
        Index('idx_sesiones_usuario', 'usuario_id'),
        Index('idx_sesiones_token', 'token_hash'),
        Index('idx_sesiones_expiracion', 'expira_at'),
    )


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prospect_id = Column(UUID(as_uuid=True), ForeignKey('prospects.id', ondelete='CASCADE'), nullable=False)
    position_id = Column(UUID(as_uuid=True), ForeignKey('job_positions.id', ondelete='CASCADE'), nullable=False)
    session_token = Column(String(100), unique=True, nullable=False)
    status = Column(String(30), nullable=False, default='in_progress')
    current_test = Column(Integer, default=1)
    current_question = Column(Integer, default=1)
    conversation_history = Column(JSONB, default=list)
    test_1_score = Column(DECIMAL(5, 2))
    test_2_score = Column(DECIMAL(5, 2))
    total_score = Column(DECIMAL(5, 2))
    passed_ai = Column(Boolean)
    feedback_generated = Column(JSONB, default=dict)
    email_sent = Column(Boolean, default=False)
    started_at = Column(TIMESTAMP(timezone=True), server_default=func.current_timestamp())
    completed_at = Column(TIMESTAMP(timezone=True))
    duration_seconds = Column(Integer)

    prospect = relationship("Prospect", back_populates="evaluations")
    position = relationship("JobPosition", back_populates="evaluations")
    answers = relationship("EvaluationAnswer", back_populates="evaluation", cascade="all, delete-orphan")
    hr_actions = relationship("HRAction", back_populates="evaluation", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress', 'completed', 'abandoned', 'pending_review', "
            "'scheduled_interview', 'interviewing', 'final_approved', 'rejected_human')",
            name='check_status'
        ),
        Index('idx_evaluations_prospect', 'prospect_id'),
        Index('idx_evaluations_position', 'position_id'),
        Index('idx_evaluations_status', 'status'),
        Index('idx_evaluations_pending', 'status', postgresql_where="status = 'pending_review'"),
    )


class EvaluationAnswer(Base):
    __tablename__ = "evaluation_answers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id = Column(UUID(as_uuid=True), ForeignKey('evaluations.id', ondelete='CASCADE'), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey('question_templates.id', ondelete='CASCADE'), nullable=False)
    answer_text = Column(Text, nullable=False)
    answer_embedding = Column(Vector(1536))
    score = Column(DECIMAL(5, 2), nullable=False)
    similarity_score = Column(DECIMAL(5, 4))
    matched_keywords = Column(JSONB, default=list)
    feedback_points = Column(JSONB, default=dict)
    response_time_seconds = Column(Integer)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.current_timestamp())

    evaluation = relationship("Evaluation", back_populates="answers")
    question = relationship("QuestionTemplate", back_populates="answers")

    __table_args__ = (
        Index('idx_answers_evaluation', 'evaluation_id'),
    )


class HRAction(Base):
    __tablename__ = "hr_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    evaluation_id = Column(UUID(as_uuid=True), ForeignKey('evaluations.id'), nullable=False)
    action_type = Column(String(50), nullable=False)
    notes = Column(Text)
    action_metadata = Column(JSONB, default=dict)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.current_timestamp())

    user = relationship("User", back_populates="hr_actions")
    evaluation = relationship("Evaluation", back_populates="hr_actions")

    __table_args__ = (
        CheckConstraint(
            "action_type IN ('approved_for_interview', 'rejected', 'scheduled_interview', "
            "'added_notes', 'downloaded_cv', 'sent_email')",
            name='check_action_type'
        ),
        Index('idx_hr_actions_evaluation', 'evaluation_id'),
        Index('idx_hr_actions_user', 'user_id'),
    )


class ProspectDocumentAccessLog(Base):
    __tablename__ = "prospect_documents_access_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey('prospect_documents.id'), nullable=False)
    accessed_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    access_type = Column(String(20))
    ip_address = Column(String(50))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.current_timestamp())

    document = relationship("ProspectDocument", back_populates="access_logs")
    user = relationship("User", back_populates="document_accesses")

    __table_args__ = (
        CheckConstraint("access_type IN ('view', 'download')", name='check_access_type'),
    )


class GraphCheckpoint(Base):
    __tablename__ = "graph_checkpoints"

    thread_id = Column(Text, primary_key=True)
    checkpoint_ns = Column(Text, primary_key=True, default='')
    checkpoint_id = Column(Text, primary_key=True)
    parent_checkpoint_id = Column(Text)
    type = Column(Text)
    checkpoint = Column(BYTEA, nullable=False)
    checkpoint_metadata = Column('metadata', JSONB, nullable=False, default=dict)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.current_timestamp())

    __table_args__ = (
        Index('idx_graph_checkpoints_thread', 'thread_id'),
        Index('idx_graph_checkpoints_parent', 'parent_checkpoint_id'),
        Index('idx_graph_checkpoints_created', 'created_at'),
    )


class GraphCheckpointWrite(Base):
    __tablename__ = "graph_checkpoint_writes"

    thread_id = Column(Text, primary_key=True)
    checkpoint_ns = Column(Text, primary_key=True, default='')
    checkpoint_id = Column(Text, primary_key=True)
    task_id = Column(Text, primary_key=True)
    idx = Column(Integer, primary_key=True)
    channel = Column(Text, nullable=False)
    type = Column(Text)
    value = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.current_timestamp())

    __table_args__ = (
        ForeignKeyConstraint(
            ['thread_id', 'checkpoint_ns', 'checkpoint_id'],
            ['graph_checkpoints.thread_id', 'graph_checkpoints.checkpoint_ns', 'graph_checkpoints.checkpoint_id'],
            ondelete='CASCADE'
        ),
        Index('idx_graph_checkpoint_writes_thread', 'thread_id'),
        Index('idx_graph_checkpoint_writes_checkpoint', 'checkpoint_id'),
    )