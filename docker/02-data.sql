CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "btree_gist";
SET CLIENT_ENCODING TO 'UTF8';

CREATE TABLE job_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    salary DECIMAL(10,2),
    currency VARCHAR(3) DEFAULT 'PEN',
    is_active BOOLEAN DEFAULT true,
    slots_available INTEGER DEFAULT 1,
    requirements JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE question_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    position_id UUID REFERENCES job_positions(id) ON DELETE CASCADE,
    question_text TEXT NOT NULL,
    question_type VARCHAR(20) NOT NULL CHECK (question_type IN ('role_specific', 'transversal')),
    test_number INTEGER NOT NULL CHECK (test_number IN (1, 2)),
    question_order INTEGER NOT NULL,
    validation_type VARCHAR(20) NOT NULL CHECK (validation_type IN ('semantic', 'boolean', 'keyword', 'numeric')),
    expected_keywords JSONB DEFAULT '[]'::jsonb,
    ideal_answer TEXT,
    ideal_embedding vector(1536),
    min_similarity DECIMAL(3,2) DEFAULT 0.65,
    weight DECIMAL(3,2) DEFAULT 1.00,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE prospects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    email VARCHAR(255) UNIQUE,
    phone VARCHAR(50),
    parsed_from_cv BOOLEAN DEFAULT false,
    cv_summary JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE prospect_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prospect_id UUID NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    document_type VARCHAR(50) NOT NULL DEFAULT 'cv',
    file_name VARCHAR(255) NOT NULL,
    original_file_name VARCHAR(255) NOT NULL,
    storage_type VARCHAR(20) NOT NULL CHECK (storage_type IN ('database', 's3')) DEFAULT 'database',
    storage_path TEXT,
    file_data BYTEA,
    file_size INTEGER NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    checksum VARCHAR(64),
    sharepoint_url TEXT,
    sync_status VARCHAR(20) CHECK (sync_status IN ('pending', 'synced', 'failed')),
    uploaded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_storage CHECK (
        (storage_type = 'database' AND file_data IS NOT NULL) OR
        (storage_type = 's3' AND storage_path IS NOT NULL)
    )
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'recruiter', 'interviewer', 'vendedor', 'viewer')) DEFAULT 'recruiter',
    is_active BOOLEAN DEFAULT true,
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sesiones (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    usuario_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) UNIQUE NOT NULL,
    expira_at TIMESTAMPTZ NOT NULL,
    revocado BOOLEAN DEFAULT false,
    ip_address VARCHAR(50),
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE evaluations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prospect_id UUID NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    position_id UUID NOT NULL REFERENCES job_positions(id) ON DELETE CASCADE,
    session_token VARCHAR(100) UNIQUE NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'in_progress' CHECK (status IN (
        'in_progress',
        'completed',
        'abandoned',
        'pending_review',
        'scheduled_interview',
        'interviewing',
        'final_approved',
        'rejected_human'
    )),
    current_test INTEGER DEFAULT 1,
    current_question INTEGER DEFAULT 1,
    conversation_history JSONB DEFAULT '[]'::jsonb,
    test_1_score DECIMAL(5,2),
    test_2_score DECIMAL(5,2),
    total_score DECIMAL(5,2),
    passed_ai BOOLEAN,
    feedback_generated JSONB DEFAULT '{}'::jsonb,
    email_sent BOOLEAN DEFAULT false,
    started_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    duration_seconds INTEGER
);

CREATE TABLE evaluation_answers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    evaluation_id UUID NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    question_id UUID NOT NULL REFERENCES question_templates(id) ON DELETE CASCADE,
    answer_text TEXT NOT NULL,
    answer_embedding vector(1536),
    score DECIMAL(5,2) NOT NULL,
    similarity_score DECIMAL(5,4),
    matched_keywords JSONB DEFAULT '[]'::jsonb,
    feedback_points JSONB DEFAULT '{}'::jsonb,
    response_time_seconds INTEGER,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE hr_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id),
    evaluation_id UUID NOT NULL REFERENCES evaluations(id),
    action_type VARCHAR(50) NOT NULL CHECK (action_type IN (
        'approved_for_interview',
        'rejected',
        'scheduled_interview',
        'added_notes',
        'downloaded_cv',
        'sent_email'
    )),
    notes TEXT,
    action_metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE prospect_documents_access_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES prospect_documents(id),
    accessed_by UUID NOT NULL REFERENCES users(id),
    access_type VARCHAR(20) CHECK (access_type IN ('view', 'download')),
    ip_address VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE graph_checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint BYTEA NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE graph_checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    value JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx),
    FOREIGN KEY (thread_id, checkpoint_ns, checkpoint_id)
        REFERENCES graph_checkpoints(thread_id, checkpoint_ns, checkpoint_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_positions_active ON job_positions(is_active) WHERE is_active = true;
CREATE INDEX idx_questions_position ON question_templates(position_id, test_number, question_order);
CREATE INDEX idx_questions_embedding ON question_templates USING ivfflat (ideal_embedding vector_cosine_ops) WITH (lists = 50);
CREATE INDEX idx_prospects_email ON prospects(email);
CREATE INDEX idx_documents_prospect ON prospect_documents(prospect_id);
CREATE INDEX idx_sesiones_usuario ON sesiones(usuario_id);
CREATE INDEX idx_sesiones_token ON sesiones(token_hash);
CREATE INDEX idx_sesiones_expiracion ON sesiones(expira_at);
CREATE INDEX idx_evaluations_prospect ON evaluations(prospect_id);
CREATE INDEX idx_evaluations_position ON evaluations(position_id);
CREATE INDEX idx_evaluations_status ON evaluations(status);
CREATE INDEX idx_evaluations_pending ON evaluations(status) WHERE status = 'pending_review';
CREATE INDEX idx_answers_evaluation ON evaluation_answers(evaluation_id);
CREATE INDEX idx_answers_embedding ON evaluation_answers USING ivfflat (answer_embedding vector_cosine_ops) WITH (lists = 50);
CREATE INDEX idx_hr_actions_evaluation ON hr_actions(evaluation_id);
CREATE INDEX idx_hr_actions_user ON hr_actions(user_id);
CREATE INDEX idx_graph_checkpoints_thread ON graph_checkpoints(thread_id);
CREATE INDEX idx_graph_checkpoints_parent ON graph_checkpoints(parent_checkpoint_id);
CREATE INDEX idx_graph_checkpoints_created ON graph_checkpoints(created_at);
CREATE INDEX idx_graph_checkpoint_writes_thread ON graph_checkpoint_writes(thread_id);
CREATE INDEX idx_graph_checkpoint_writes_checkpoint ON graph_checkpoint_writes(checkpoint_id);

ALTER TABLE evaluations
ADD CONSTRAINT unique_active_evaluation
EXCLUDE USING gist (
    prospect_id WITH =,
    position_id WITH =,
    tstzrange(started_at, COALESCE(completed_at, 'infinity'::timestamptz), '[)') WITH &&
)
WHERE (status IN ('in_progress', 'pending_review'));

CREATE OR REPLACE FUNCTION calculate_evaluation_scores(p_evaluation_id UUID)
RETURNS void AS $$
DECLARE
    v_test_1_score DECIMAL(5,2);
    v_test_2_score DECIMAL(5,2);
    v_total_score DECIMAL(5,2);
    v_passed BOOLEAN;
    v_pass_threshold DECIMAL(5,2) := 70.00;
BEGIN
    SELECT ROUND(AVG(ea.score)::numeric, 2)
    INTO v_test_1_score
    FROM evaluation_answers ea
    JOIN question_templates qt ON ea.question_id = qt.id
    WHERE ea.evaluation_id = p_evaluation_id AND qt.test_number = 1;

    SELECT ROUND(AVG(ea.score)::numeric, 2)
    INTO v_test_2_score
    FROM evaluation_answers ea
    JOIN question_templates qt ON ea.question_id = qt.id
    WHERE ea.evaluation_id = p_evaluation_id AND qt.test_number = 2;

    v_total_score := ROUND((COALESCE(v_test_1_score, 0) * 0.60 + COALESCE(v_test_2_score, 0) * 0.40)::numeric, 2);
    v_passed := v_total_score >= v_pass_threshold;

    UPDATE evaluations
    SET test_1_score = v_test_1_score,
        test_2_score = v_test_2_score,
        total_score = v_total_score,
        passed_ai = v_passed,
        status = CASE
            WHEN v_passed THEN 'pending_review'
            ELSE 'completed'
        END,
        completed_at = CURRENT_TIMESTAMP,
        duration_seconds = EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - started_at))::integer
    WHERE id = p_evaluation_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_next_question(p_evaluation_id UUID)
RETURNS TABLE(
    question_id UUID,
    question_text TEXT,
    test_number INTEGER,
    question_order INTEGER,
    validation_type VARCHAR,
    expected_keywords JSONB
) AS $$
DECLARE
    v_position_id UUID;
    v_current_test INTEGER;
    v_current_question INTEGER;
BEGIN
    SELECT position_id, current_test, current_question
    INTO v_position_id, v_current_test, v_current_question
    FROM evaluations
    WHERE id = p_evaluation_id;

    RETURN QUERY
    SELECT
        qt.id,
        qt.question_text,
        qt.test_number,
        qt.question_order,
        qt.validation_type,
        qt.expected_keywords
    FROM question_templates qt
    WHERE qt.position_id = v_position_id
        AND qt.test_number = v_current_test
        AND qt.question_order = v_current_question
        AND qt.is_active = true
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION advance_evaluation(p_evaluation_id UUID)
RETURNS BOOLEAN AS $$
DECLARE
    v_current_test INTEGER;
    v_current_question INTEGER;
    v_position_id UUID;
    v_total_questions_test_1 INTEGER;
    v_total_questions_test_2 INTEGER;
    v_is_finished BOOLEAN := false;
BEGIN
    SELECT position_id, current_test, current_question
    INTO v_position_id, v_current_test, v_current_question
    FROM evaluations
    WHERE id = p_evaluation_id;

    SELECT COUNT(*) INTO v_total_questions_test_1
    FROM question_templates
    WHERE position_id = v_position_id AND test_number = 1 AND is_active = true;

    SELECT COUNT(*) INTO v_total_questions_test_2
    FROM question_templates
    WHERE position_id = v_position_id AND test_number = 2 AND is_active = true;

    IF v_current_test = 1 AND v_current_question >= v_total_questions_test_1 THEN
        UPDATE evaluations
        SET current_test = 2, current_question = 1
        WHERE id = p_evaluation_id;
    ELSIF v_current_test = 2 AND v_current_question >= v_total_questions_test_2 THEN
        PERFORM calculate_evaluation_scores(p_evaluation_id);
        v_is_finished := true;
    ELSE
        UPDATE evaluations
        SET current_question = current_question + 1
        WHERE id = p_evaluation_id;
    END IF;

    RETURN v_is_finished;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION log_document_access(
    p_document_id UUID,
    p_user_id UUID,
    p_access_type VARCHAR,
    p_ip_address VARCHAR
)
RETURNS void AS $$
BEGIN
    INSERT INTO prospect_documents_access_log (document_id, accessed_by, access_type, ip_address)
    VALUES (p_document_id, p_user_id, p_access_type, p_ip_address);
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION cleanup_old_graph_checkpoints()
RETURNS void AS $$
BEGIN
    DELETE FROM graph_checkpoints
    WHERE created_at < NOW() - INTERVAL '7 days';

    DELETE FROM graph_checkpoint_writes
    WHERE created_at < NOW() - INTERVAL '7 days';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_evaluation_graph_checkpoint(p_session_token TEXT)
RETURNS TABLE (
    checkpoint_id TEXT,
    checkpoint_data BYTEA,
    created_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.checkpoint_id,
        c.checkpoint,
        c.created_at
    FROM graph_checkpoints c
    WHERE c.thread_id = p_session_token
    ORDER BY c.created_at DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Función corregida para manejar correctamente sesiones abandonadas
CREATE OR REPLACE FUNCTION can_reapply_to_position(
    p_prospect_id UUID,
    p_position_id UUID,
    p_cooldown_days INTEGER DEFAULT 30
) RETURNS TABLE (
    can_apply BOOLEAN,
    reason TEXT,
    last_evaluation_date TIMESTAMPTZ,
    days_remaining INTEGER
) AS $$
DECLARE
    v_last_eval RECORD;
    v_days_since INTEGER;
BEGIN
    -- Buscar la última evaluación SIGNIFICATIVA (con respuestas o completada)
    SELECT
        e.id,
        e.status,
        e.completed_at,
        e.started_at,
        e.current_test,
        e.current_question,
        EXTRACT(DAY FROM (CURRENT_TIMESTAMP - COALESCE(e.completed_at, e.started_at)))::INTEGER as days_since,
        EXISTS(SELECT 1 FROM evaluation_answers WHERE evaluation_id = e.id) as has_answers
    INTO v_last_eval
    FROM evaluations e
    WHERE e.prospect_id = p_prospect_id
      AND e.position_id = p_position_id
      -- FIX CRÍTICO: Excluir 'abandoned' sin respuestas
      AND NOT (e.status = 'abandoned' AND NOT EXISTS(SELECT 1 FROM evaluation_answers WHERE evaluation_id = e.id))
    ORDER BY COALESCE(e.completed_at, e.started_at) DESC
    LIMIT 1;

    -- Si no hay evaluaciones significativas previas
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            TRUE,
            'No hay evaluaciones previas'::TEXT,
            NULL::TIMESTAMPTZ,
            0;
        RETURN;
    END IF;

    -- Evaluación en progreso CON respuestas
    IF v_last_eval.status = 'in_progress' THEN
        IF v_last_eval.has_answers THEN
            RETURN QUERY SELECT
                FALSE,
                'Evaluación en progreso. Por favor completa la actual.'::TEXT,
                v_last_eval.started_at,
                0;
            RETURN;
        ELSE
            -- En progreso SIN respuestas = abandonada, permitir continuar
            RETURN QUERY SELECT
                TRUE,
                'Sesión anterior abandonada antes de comenzar'::TEXT,
                v_last_eval.started_at,
                0;
            RETURN;
        END IF;
    END IF;

    -- Pendiente de revisión por RRHH
    IF v_last_eval.status = 'pending_review' THEN
        RETURN QUERY SELECT
            FALSE,
            'Evaluación pendiente de revisión por RRHH'::TEXT,
            v_last_eval.started_at,
            0;
        RETURN;
    END IF;

    -- Evaluación completada o abandonada CON respuestas: aplicar cooldown
    IF v_last_eval.status IN ('completed', 'abandoned', 'rejected_human') THEN
        v_days_since := EXTRACT(DAY FROM (CURRENT_TIMESTAMP - COALESCE(v_last_eval.completed_at, v_last_eval.started_at)))::INTEGER;

        IF v_days_since < p_cooldown_days THEN
            RETURN QUERY SELECT
                FALSE,
                format('Debe esperar %s días más para volver a postular', p_cooldown_days - v_days_since)::TEXT,
                COALESCE(v_last_eval.completed_at, v_last_eval.started_at),
                p_cooldown_days - v_days_since;
            RETURN;
        END IF;
    END IF;

    -- Cooldown cumplido
    RETURN QUERY SELECT
        TRUE,
        'Puede aplicar nuevamente'::TEXT,
        COALESCE(v_last_eval.completed_at, v_last_eval.started_at),
        0;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE VIEW v_pending_prospects AS
SELECT
    e.id AS evaluation_id,
    p.id AS prospect_id,
    p.first_name || ' ' || p.last_name AS prospect_name,
    p.email,
    p.phone,
    jp.title AS position,
    e.total_score,
    e.test_1_score,
    e.test_2_score,
    e.completed_at,
    e.status,
    CASE WHEN pd.id IS NOT NULL THEN true ELSE false END AS has_cv,
    pd.id AS document_id
FROM evaluations e
JOIN prospects p ON e.prospect_id = p.id
JOIN job_positions jp ON e.position_id = jp.id
LEFT JOIN prospect_documents pd ON p.id = pd.prospect_id
WHERE e.status = 'pending_review'
ORDER BY e.completed_at DESC;

CREATE OR REPLACE VIEW v_evaluation_details AS
SELECT
    e.id AS evaluation_id,
    p.first_name || ' ' || p.last_name AS prospect_name,
    p.email,
    p.phone,
    p.cv_summary,
    jp.title AS position,
    jp.salary,
    e.status,
    e.total_score,
    e.test_1_score,
    e.test_2_score,
    e.passed_ai,
    e.duration_seconds,
    e.completed_at,
    jsonb_agg(
        jsonb_build_object(
            'question', qt.question_text,
            'answer', ea.answer_text,
            'score', ea.score,
            'similarity', ea.similarity_score,
            'feedback', ea.feedback_points
        ) ORDER BY qt.test_number, qt.question_order
    ) AS answers_detail
FROM evaluations e
JOIN prospects p ON e.prospect_id = p.id
JOIN job_positions jp ON e.position_id = jp.id
LEFT JOIN evaluation_answers ea ON e.id = ea.evaluation_id
LEFT JOIN question_templates qt ON ea.question_id = qt.id
GROUP BY e.id, p.first_name, p.last_name, p.email, p.phone, p.cv_summary,
         jp.title, jp.salary, e.status, e.total_score, e.test_1_score,
         e.test_2_score, e.passed_ai, e.duration_seconds, e.completed_at;

CREATE OR REPLACE VIEW v_position_stats AS
SELECT
    jp.id,
    jp.title,
    jp.salary,
    jp.slots_available,
    COUNT(DISTINCT e.id) AS total_applications,
    COUNT(DISTINCT CASE WHEN e.status = 'completed' THEN e.id END) AS completed_evaluations,
    COUNT(CASE WHEN e.passed_ai = true THEN 1 END) AS ai_approved,
    COUNT(CASE WHEN e.status = 'pending_review' THEN 1 END) AS pending_review,
    ROUND(AVG(CASE WHEN e.status IN ('completed', 'pending_review') THEN e.total_score END)::numeric, 2) AS avg_score
FROM job_positions jp
LEFT JOIN evaluations e ON jp.id = e.position_id
WHERE jp.is_active = true
GROUP BY jp.id, jp.title, jp.salary, jp.slots_available;

INSERT INTO job_positions (title, description, salary, slots_available, requirements) VALUES
('Ejecutivo de Ventas', 'Responsable de ventas B2B y gestión de cartera de clientes', 2500.00, 2, '{
    "experience_years": 2,
    "skills": ["ventas", "negociación", "crm"],
    "availability": "full_time"
}'::jsonb),
('Asistente Administrativo', 'Apoyo en gestión documental y atención al cliente', 1800.00, 1, '{
    "experience_years": 1,
    "skills": ["excel", "organización", "comunicación"],
    "availability": "full_time"
}'::jsonb);

INSERT INTO question_templates (position_id, question_text, question_type, test_number, question_order, validation_type, ideal_answer, min_similarity)
SELECT id, '¿Cuál es tu experiencia en ventas B2B?', 'role_specific', 1, 1, 'semantic',
'Tengo experiencia en ventas B2B trabajando con empresas medianas y grandes, gestionando ciclos de venta largos, negociando contratos y manteniendo relaciones comerciales a largo plazo.', 0.65
FROM job_positions WHERE title = 'Ejecutivo de Ventas'
UNION ALL
SELECT id, '¿Cómo manejarías una objeción de precio alto?', 'role_specific', 1, 2, 'semantic',
'Enfocándome en el valor y ROI del producto, mostrando casos de éxito similares, ofreciendo comparativas con la competencia y explorando opciones de pago flexibles si es necesario.', 0.65
FROM job_positions WHERE title = 'Ejecutivo de Ventas'
UNION ALL
SELECT id, 'Describe tu mejor cierre de venta', 'role_specific', 1, 3, 'semantic',
'Logré cerrar una venta importante identificando las necesidades reales del cliente, demostrando valor tangible y construyendo confianza durante el proceso de negociación.', 0.60
FROM job_positions WHERE title = 'Ejecutivo de Ventas'
UNION ALL
SELECT id, '¿Qué CRM has utilizado?', 'role_specific', 1, 4, 'keyword',
'He trabajado con Salesforce, HubSpot y Zoho CRM para gestión de pipeline y seguimiento de oportunidades.', 0.50
FROM job_positions WHERE title = 'Ejecutivo de Ventas'
UNION ALL
SELECT id, '¿Cuál es tu meta de ventas mensual realista?', 'role_specific', 1, 5, 'numeric',
'Mi meta mensual realista es entre S/50,000 y S/100,000 dependiendo del producto y ciclo de venta.', 0.60
FROM job_positions WHERE title = 'Ejecutivo de Ventas'
UNION ALL
SELECT id, '¿Cómo priorizas múltiples tareas urgentes?', 'transversal', 2, 1, 'semantic',
'Evalúo el impacto y urgencia de cada tarea, comunico prioridades al equipo, delego cuando es posible y mantengo flexibilidad para ajustar según cambios.', 0.65
FROM job_positions WHERE title = 'Ejecutivo de Ventas'
UNION ALL
SELECT id, 'Describe un conflicto laboral que hayas resuelto', 'transversal', 2, 2, 'semantic',
'Tuve un desacuerdo con un compañero, conversamos abiertamente, escuché su perspectiva, llegamos a un acuerdo de colaboración y establecimos reglas claras para el futuro.', 0.65
FROM job_positions WHERE title = 'Ejecutivo de Ventas'
UNION ALL
SELECT id, '¿Estás de acuerdo con el salario de S/2,500 mensuales?', 'transversal', 2, 3, 'boolean',
'Sí, estoy de acuerdo con la propuesta salarial.', 0.80
FROM job_positions WHERE title = 'Ejecutivo de Ventas'
UNION ALL
SELECT id, '¿Qué harías si un cliente te pide algo fuera de política?', 'transversal', 2, 4, 'semantic',
'Explicaría las políticas de la empresa, buscaría alternativas dentro del marco permitido, escalaría con mi supervisor si es necesario y mantendría la relación positiva con el cliente.', 0.65
FROM job_positions WHERE title = 'Ejecutivo de Ventas'
UNION ALL
SELECT id, '¿Tienes disponibilidad para trabajar ocasionalmente fines de semana?', 'transversal', 2, 5, 'boolean',
'Sí, tengo disponibilidad para trabajar fines de semana cuando sea necesario.', 0.75
FROM job_positions WHERE title = 'Ejecutivo de Ventas';

INSERT INTO users (email, password_hash, full_name, role)
VALUES (
    'rrhh@empresa.com',
    crypt('admin123', gen_salt('bf')),
    'María Rodríguez',
    'admin'
);


CREATE TABLE IF NOT EXISTS conocimiento_rag (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tipo VARCHAR(50) NOT NULL,
    titulo VARCHAR(255) NOT NULL,
    contenido TEXT NOT NULL,
    embedding vector(1536),
    activo BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conocimiento_embedding 
ON conocimiento_rag 
USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 50);

CREATE INDEX IF NOT EXISTS idx_conocimiento_tipo 
ON conocimiento_rag(tipo) 
WHERE activo = true;

CREATE INDEX IF NOT EXISTS idx_conocimiento_metadata 
ON conocimiento_rag 
USING gin(metadata);

COMMENT ON TABLE conocimiento_rag IS 'Base de conocimiento con embeddings para RAG';
COMMENT ON COLUMN conocimiento_rag.tipo IS 'Tipos: job_position, guia_producto, faq, etc';
COMMENT ON COLUMN conocimiento_rag.contenido IS 'Texto completo para generacion de respuestas';
COMMENT ON COLUMN conocimiento_rag.embedding IS 'Vector 1536D para busqueda semantica';
COMMENT ON COLUMN conocimiento_rag.metadata IS 'Datos adicionales (position_id, category, etc)';


UPDATE evaluations
SET 
    status = 'abandoned',
    completed_at = CURRENT_TIMESTAMP
WHERE status = 'in_progress'
  AND NOT EXISTS (
      SELECT 1 FROM evaluation_answers WHERE evaluation_id = evaluations.id
  )
  AND started_at < CURRENT_TIMESTAMP - INTERVAL '2 hours';



-- 3. Verificar que se limpiaron correctamente
SELECT 
    status,
    COUNT(*) as count
FROM evaluations
WHERE prospect_id = (SELECT id FROM prospects WHERE email = 'clblommberg@gmail.com')
GROUP BY status;

-- Verificar la función con un caso de prueba
SELECT * FROM can_reapply_to_position(
    (SELECT id FROM prospects WHERE email = 'clblommberg@gmail.com'),
    (SELECT id FROM job_positions WHERE title = 'Asistente Administrativo'),
    30
);


INSERT INTO question_templates (position_id, question_text, question_type, test_number, question_order, validation_type, ideal_answer, min_similarity)
SELECT id, '¿Qué experiencia tienes en atención al cliente?', 'role_specific', 1, 1, 'semantic',
'Tengo experiencia atendiendo clientes de manera presencial, telefónica y por email, resolviendo consultas, gestionando quejas y brindando información sobre productos o servicios.', 0.65
FROM job_positions WHERE title = 'Asistente Administrativo'
UNION ALL
SELECT id, '¿Qué herramientas ofimáticas dominas?', 'role_specific', 1, 2, 'keyword',
'Domino Microsoft Office especialmente Excel con fórmulas y tablas dinámicas, Word para documentos profesionales, PowerPoint para presentaciones, y Outlook para gestión de correos.', 0.50
FROM job_positions WHERE title = 'Asistente Administrativo'
UNION ALL
SELECT id, 'Describe tu experiencia en gestión documental', 'role_specific', 1, 3, 'semantic',
'He gestionado archivos físicos y digitales, organizado documentación por fechas y categorías, digitalizado documentos, y mantenido sistemas de archivo ordenados y actualizados.', 0.60
FROM job_positions WHERE title = 'Asistente Administrativo'
UNION ALL
SELECT id, '¿Cómo organizas múltiples tareas diarias?', 'role_specific', 1, 4, 'semantic',
'Utilizo listas de prioridades, calendario digital, establezco deadlines realistas, comunico avances, y mantengo flexibilidad para ajustar según urgencias.', 0.60
FROM job_positions WHERE title = 'Asistente Administrativo'
UNION ALL
SELECT id, '¿Tienes experiencia con sistemas ERP o CRM?', 'role_specific', 1, 5, 'boolean',
'Sí, he trabajado con sistemas de gestión empresarial para registro de operaciones y seguimiento de clientes.', 0.70
FROM job_positions WHERE title = 'Asistente Administrativo'
UNION ALL
SELECT id, 'Describe un error que hayas cometido y cómo lo resolviste', 'transversal', 2, 1, 'semantic',
'Cometí un error al enviar información incorrecta, lo reporté inmediatamente a mi supervisor, corregí el error, implementé un checklist de verificación y aprendí a revisar dos veces antes de enviar.', 0.65
FROM job_positions WHERE title = 'Asistente Administrativo'
UNION ALL
SELECT id, '¿Cómo manejas situaciones de estrés o presión?', 'transversal', 2, 2, 'semantic',
'Respiro profundo, priorizo lo urgente, comunico mi capacidad actual, pido ayuda si es necesario, y mantengo la calma para tomar decisiones acertadas.', 0.65
FROM job_positions WHERE title = 'Asistente Administrativo'
UNION ALL
SELECT id, '¿Estás de acuerdo con el salario de S/1,800 mensuales?', 'transversal', 2, 3, 'boolean',
'Sí, estoy de acuerdo con la propuesta salarial.', 0.80
FROM job_positions WHERE title = 'Asistente Administrativo'
UNION ALL
SELECT id, '¿Tienes disponibilidad inmediata?', 'transversal', 2, 4, 'boolean',
'Sí, tengo disponibilidad inmediata para empezar.', 0.75
FROM job_positions WHERE title = 'Asistente Administrativo'
UNION ALL
SELECT id, '¿Por qué te interesa trabajar como Asistente Administrativo?', 'transversal', 2, 5, 'semantic',
'Me gusta la organización, el trabajo administrativo me permite usar mis habilidades de atención al detalle, comunicación y gestión, además de contribuir al funcionamiento eficiente de la empresa.', 0.65
FROM job_positions WHERE title = 'Asistente Administrativo';

UPDATE question_templates 
SET ideal_embedding = NULL 
WHERE position_id = (SELECT id FROM job_positions WHERE title = 'Asistente Administrativo')
AND validation_type = 'semantic';

-- =====================================================
-- LangGraph Checkpoints (sin prefijo graph_ para LangGraph)
-- =====================================================

CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    blob BYTEA,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA NOT NULL,
    task_path TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

CREATE TABLE IF NOT EXISTS checkpoint_migrations (
    v INTEGER PRIMARY KEY
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_thread ON checkpoints(thread_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_parent ON checkpoints(parent_checkpoint_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_created ON checkpoints(created_at);
CREATE INDEX IF NOT EXISTS idx_checkpoint_blobs_thread ON checkpoint_blobs(thread_id);
CREATE INDEX IF NOT EXISTS idx_checkpoint_writes_thread ON checkpoint_writes(thread_id);