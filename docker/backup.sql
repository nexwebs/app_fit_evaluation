--
-- PostgreSQL database dump
--

\restrict vUgjkY3yjJ0o43jctEEHc8mTxyNmHLCK4ar3lFQHWe3cpcdYCrfqkWrIUzK2qTx

-- Dumped from database version 17.7
-- Dumped by pg_dump version 17.7

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: btree_gist; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;


--
-- Name: EXTENSION btree_gist; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION btree_gist IS 'support for indexing common datatypes in GiST';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: advance_evaluation(uuid); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.advance_evaluation(p_evaluation_id uuid) RETURNS boolean
    LANGUAGE plpgsql
    AS $$
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
$$;


ALTER FUNCTION public.advance_evaluation(p_evaluation_id uuid) OWNER TO postgres;

--
-- Name: calculate_evaluation_scores(uuid); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.calculate_evaluation_scores(p_evaluation_id uuid) RETURNS void
    LANGUAGE plpgsql
    AS $$
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
$$;


ALTER FUNCTION public.calculate_evaluation_scores(p_evaluation_id uuid) OWNER TO postgres;

--
-- Name: can_reapply_to_position(uuid, uuid, integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.can_reapply_to_position(p_prospect_id uuid, p_position_id uuid, p_cooldown_days integer DEFAULT 30) RETURNS TABLE(can_apply boolean, reason text, last_evaluation_date timestamp with time zone, days_remaining integer)
    LANGUAGE plpgsql
    AS $$
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
$$;


ALTER FUNCTION public.can_reapply_to_position(p_prospect_id uuid, p_position_id uuid, p_cooldown_days integer) OWNER TO postgres;

--
-- Name: cleanup_old_graph_checkpoints(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.cleanup_old_graph_checkpoints() RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    DELETE FROM graph_checkpoints
    WHERE created_at < NOW() - INTERVAL '7 days';

    DELETE FROM graph_checkpoint_writes
    WHERE created_at < NOW() - INTERVAL '7 days';
END;
$$;


ALTER FUNCTION public.cleanup_old_graph_checkpoints() OWNER TO postgres;

--
-- Name: get_evaluation_graph_checkpoint(text); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.get_evaluation_graph_checkpoint(p_session_token text) RETURNS TABLE(checkpoint_id text, checkpoint_data bytea, created_at timestamp with time zone)
    LANGUAGE plpgsql
    AS $$
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
$$;


ALTER FUNCTION public.get_evaluation_graph_checkpoint(p_session_token text) OWNER TO postgres;

--
-- Name: get_next_question(uuid); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.get_next_question(p_evaluation_id uuid) RETURNS TABLE(question_id uuid, question_text text, test_number integer, question_order integer, validation_type character varying, expected_keywords jsonb)
    LANGUAGE plpgsql
    AS $$
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
$$;


ALTER FUNCTION public.get_next_question(p_evaluation_id uuid) OWNER TO postgres;

--
-- Name: log_document_access(uuid, uuid, character varying, character varying); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.log_document_access(p_document_id uuid, p_user_id uuid, p_access_type character varying, p_ip_address character varying) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    INSERT INTO prospect_documents_access_log (document_id, accessed_by, access_type, ip_address)
    VALUES (p_document_id, p_user_id, p_access_type, p_ip_address);
END;
$$;


ALTER FUNCTION public.log_document_access(p_document_id uuid, p_user_id uuid, p_access_type character varying, p_ip_address character varying) OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: conocimiento_rag; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.conocimiento_rag (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tipo character varying(50) NOT NULL,
    titulo character varying(255) NOT NULL,
    contenido text NOT NULL,
    embedding public.vector(1536),
    activo boolean DEFAULT true,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.conocimiento_rag OWNER TO postgres;

--
-- Name: TABLE conocimiento_rag; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.conocimiento_rag IS 'Base de conocimiento con embeddings para RAG';


--
-- Name: COLUMN conocimiento_rag.tipo; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.conocimiento_rag.tipo IS 'Tipos: job_position, guia_producto, faq, etc';


--
-- Name: COLUMN conocimiento_rag.contenido; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.conocimiento_rag.contenido IS 'Texto completo para generacion de respuestas';


--
-- Name: COLUMN conocimiento_rag.embedding; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.conocimiento_rag.embedding IS 'Vector 1536D para busqueda semantica';


--
-- Name: COLUMN conocimiento_rag.metadata; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.conocimiento_rag.metadata IS 'Datos adicionales (position_id, category, etc)';


--
-- Name: evaluation_answers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.evaluation_answers (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    evaluation_id uuid NOT NULL,
    question_id uuid NOT NULL,
    answer_text text NOT NULL,
    answer_embedding public.vector(1536),
    score numeric(5,2) NOT NULL,
    similarity_score numeric(5,4),
    matched_keywords jsonb DEFAULT '[]'::jsonb,
    feedback_points jsonb DEFAULT '{}'::jsonb,
    response_time_seconds integer,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.evaluation_answers OWNER TO postgres;

--
-- Name: evaluations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.evaluations (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    prospect_id uuid NOT NULL,
    position_id uuid NOT NULL,
    session_token character varying(100) NOT NULL,
    status character varying(30) DEFAULT 'in_progress'::character varying NOT NULL,
    current_test integer DEFAULT 1,
    current_question integer DEFAULT 1,
    conversation_history jsonb DEFAULT '[]'::jsonb,
    test_1_score numeric(5,2),
    test_2_score numeric(5,2),
    total_score numeric(5,2),
    passed_ai boolean,
    feedback_generated jsonb DEFAULT '{}'::jsonb,
    email_sent boolean DEFAULT false,
    started_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamp with time zone,
    duration_seconds integer,
    CONSTRAINT evaluations_status_check CHECK (((status)::text = ANY ((ARRAY['in_progress'::character varying, 'completed'::character varying, 'abandoned'::character varying, 'pending_review'::character varying, 'scheduled_interview'::character varying, 'interviewing'::character varying, 'final_approved'::character varying, 'rejected_human'::character varying])::text[])))
);


ALTER TABLE public.evaluations OWNER TO postgres;

--
-- Name: graph_checkpoint_writes; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.graph_checkpoint_writes (
    thread_id text NOT NULL,
    checkpoint_ns text DEFAULT ''::text NOT NULL,
    checkpoint_id text NOT NULL,
    task_id text NOT NULL,
    idx integer NOT NULL,
    channel text NOT NULL,
    type text,
    value jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.graph_checkpoint_writes OWNER TO postgres;

--
-- Name: graph_checkpoints; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.graph_checkpoints (
    thread_id text NOT NULL,
    checkpoint_ns text DEFAULT ''::text NOT NULL,
    checkpoint_id text NOT NULL,
    parent_checkpoint_id text,
    type text,
    checkpoint bytea NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.graph_checkpoints OWNER TO postgres;

--
-- Name: hr_actions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.hr_actions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    evaluation_id uuid NOT NULL,
    action_type character varying(50) NOT NULL,
    notes text,
    action_metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT hr_actions_action_type_check CHECK (((action_type)::text = ANY ((ARRAY['approved_for_interview'::character varying, 'rejected'::character varying, 'scheduled_interview'::character varying, 'added_notes'::character varying, 'downloaded_cv'::character varying, 'sent_email'::character varying])::text[])))
);


ALTER TABLE public.hr_actions OWNER TO postgres;

--
-- Name: job_positions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.job_positions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    salary numeric(10,2),
    currency character varying(3) DEFAULT 'PEN'::character varying,
    is_active boolean DEFAULT true,
    slots_available integer DEFAULT 1,
    requirements jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.job_positions OWNER TO postgres;

--
-- Name: prospect_documents; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.prospect_documents (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    prospect_id uuid NOT NULL,
    document_type character varying(50) DEFAULT 'cv'::character varying NOT NULL,
    file_name character varying(255) NOT NULL,
    original_file_name character varying(255) NOT NULL,
    storage_type character varying(20) DEFAULT 'database'::character varying NOT NULL,
    storage_path text,
    file_data bytea,
    file_size integer NOT NULL,
    mime_type character varying(100) NOT NULL,
    checksum character varying(64),
    sharepoint_url text,
    sync_status character varying(20),
    uploaded_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT prospect_documents_storage_type_check CHECK (((storage_type)::text = ANY ((ARRAY['database'::character varying, 's3'::character varying])::text[]))),
    CONSTRAINT prospect_documents_sync_status_check CHECK (((sync_status)::text = ANY ((ARRAY['pending'::character varying, 'synced'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT valid_storage CHECK (((((storage_type)::text = 'database'::text) AND (file_data IS NOT NULL)) OR (((storage_type)::text = 's3'::text) AND (storage_path IS NOT NULL))))
);


ALTER TABLE public.prospect_documents OWNER TO postgres;

--
-- Name: prospect_documents_access_log; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.prospect_documents_access_log (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    document_id uuid NOT NULL,
    accessed_by uuid NOT NULL,
    access_type character varying(20),
    ip_address character varying(50),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT prospect_documents_access_log_access_type_check CHECK (((access_type)::text = ANY ((ARRAY['view'::character varying, 'download'::character varying])::text[])))
);


ALTER TABLE public.prospect_documents_access_log OWNER TO postgres;

--
-- Name: prospects; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.prospects (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    first_name character varying(100),
    last_name character varying(100),
    email character varying(255),
    phone character varying(50),
    parsed_from_cv boolean DEFAULT false,
    cv_summary jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.prospects OWNER TO postgres;

--
-- Name: question_templates; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.question_templates (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    position_id uuid,
    question_text text NOT NULL,
    question_type character varying(20) NOT NULL,
    test_number integer NOT NULL,
    question_order integer NOT NULL,
    validation_type character varying(20) NOT NULL,
    expected_keywords jsonb DEFAULT '[]'::jsonb,
    ideal_answer text,
    ideal_embedding public.vector(1536),
    min_similarity numeric(3,2) DEFAULT 0.65,
    weight numeric(3,2) DEFAULT 1.00,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT question_templates_question_type_check CHECK (((question_type)::text = ANY ((ARRAY['role_specific'::character varying, 'transversal'::character varying])::text[]))),
    CONSTRAINT question_templates_test_number_check CHECK ((test_number = ANY (ARRAY[1, 2]))),
    CONSTRAINT question_templates_validation_type_check CHECK (((validation_type)::text = ANY ((ARRAY['semantic'::character varying, 'boolean'::character varying, 'keyword'::character varying, 'numeric'::character varying])::text[])))
);


ALTER TABLE public.question_templates OWNER TO postgres;

--
-- Name: sesiones; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sesiones (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    usuario_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    expira_at timestamp with time zone NOT NULL,
    revocado boolean DEFAULT false,
    ip_address character varying(50),
    user_agent text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.sesiones OWNER TO postgres;

--
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    full_name character varying(255) NOT NULL,
    role character varying(20) DEFAULT 'recruiter'::character varying NOT NULL,
    is_active boolean DEFAULT true,
    last_login timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT users_role_check CHECK (((role)::text = ANY ((ARRAY['admin'::character varying, 'recruiter'::character varying, 'interviewer'::character varying, 'vendedor'::character varying, 'viewer'::character varying])::text[])))
);


ALTER TABLE public.users OWNER TO postgres;

--
-- Name: v_evaluation_details; Type: VIEW; Schema: public; Owner: postgres
--

CREATE VIEW public.v_evaluation_details AS
 SELECT e.id AS evaluation_id,
    (((p.first_name)::text || ' '::text) || (p.last_name)::text) AS prospect_name,
    p.email,
    p.phone,
    p.cv_summary,
    jp.title AS "position",
    jp.salary,
    e.status,
    e.total_score,
    e.test_1_score,
    e.test_2_score,
    e.passed_ai,
    e.duration_seconds,
    e.completed_at,
    jsonb_agg(jsonb_build_object('question', qt.question_text, 'answer', ea.answer_text, 'score', ea.score, 'similarity', ea.similarity_score, 'feedback', ea.feedback_points) ORDER BY qt.test_number, qt.question_order) AS answers_detail
   FROM ((((public.evaluations e
     JOIN public.prospects p ON ((e.prospect_id = p.id)))
     JOIN public.job_positions jp ON ((e.position_id = jp.id)))
     LEFT JOIN public.evaluation_answers ea ON ((e.id = ea.evaluation_id)))
     LEFT JOIN public.question_templates qt ON ((ea.question_id = qt.id)))
  GROUP BY e.id, p.first_name, p.last_name, p.email, p.phone, p.cv_summary, jp.title, jp.salary, e.status, e.total_score, e.test_1_score, e.test_2_score, e.passed_ai, e.duration_seconds, e.completed_at;


ALTER VIEW public.v_evaluation_details OWNER TO postgres;

--
-- Name: v_pending_prospects; Type: VIEW; Schema: public; Owner: postgres
--

CREATE VIEW public.v_pending_prospects AS
 SELECT e.id AS evaluation_id,
    p.id AS prospect_id,
    (((p.first_name)::text || ' '::text) || (p.last_name)::text) AS prospect_name,
    p.email,
    p.phone,
    jp.title AS "position",
    e.total_score,
    e.test_1_score,
    e.test_2_score,
    e.completed_at,
    e.status,
        CASE
            WHEN (pd.id IS NOT NULL) THEN true
            ELSE false
        END AS has_cv,
    pd.id AS document_id
   FROM (((public.evaluations e
     JOIN public.prospects p ON ((e.prospect_id = p.id)))
     JOIN public.job_positions jp ON ((e.position_id = jp.id)))
     LEFT JOIN public.prospect_documents pd ON ((p.id = pd.prospect_id)))
  WHERE ((e.status)::text = 'pending_review'::text)
  ORDER BY e.completed_at DESC;


ALTER VIEW public.v_pending_prospects OWNER TO postgres;

--
-- Name: v_position_stats; Type: VIEW; Schema: public; Owner: postgres
--

CREATE VIEW public.v_position_stats AS
 SELECT jp.id,
    jp.title,
    jp.salary,
    jp.slots_available,
    count(DISTINCT e.id) AS total_applications,
    count(DISTINCT
        CASE
            WHEN ((e.status)::text = 'completed'::text) THEN e.id
            ELSE NULL::uuid
        END) AS completed_evaluations,
    count(
        CASE
            WHEN (e.passed_ai = true) THEN 1
            ELSE NULL::integer
        END) AS ai_approved,
    count(
        CASE
            WHEN ((e.status)::text = 'pending_review'::text) THEN 1
            ELSE NULL::integer
        END) AS pending_review,
    round(avg(
        CASE
            WHEN ((e.status)::text = ANY ((ARRAY['completed'::character varying, 'pending_review'::character varying])::text[])) THEN e.total_score
            ELSE NULL::numeric
        END), 2) AS avg_score
   FROM (public.job_positions jp
     LEFT JOIN public.evaluations e ON ((jp.id = e.position_id)))
  WHERE (jp.is_active = true)
  GROUP BY jp.id, jp.title, jp.salary, jp.slots_available;


ALTER VIEW public.v_position_stats OWNER TO postgres;

--
-- Data for Name: conocimiento_rag; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.conocimiento_rag (id, tipo, titulo, contenido, embedding, activo, metadata, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: evaluation_answers; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.evaluation_answers (id, evaluation_id, question_id, answer_text, answer_embedding, score, similarity_score, matched_keywords, feedback_points, response_time_seconds, created_at) FROM stdin;
\.


--
-- Data for Name: evaluations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.evaluations (id, prospect_id, position_id, session_token, status, current_test, current_question, conversation_history, test_1_score, test_2_score, total_score, passed_ai, feedback_generated, email_sent, started_at, completed_at, duration_seconds) FROM stdin;
\.


--
-- Data for Name: graph_checkpoint_writes; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.graph_checkpoint_writes (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, value, created_at) FROM stdin;
\.


--
-- Data for Name: graph_checkpoints; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.graph_checkpoints (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata, created_at) FROM stdin;
\.


--
-- Data for Name: hr_actions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.hr_actions (id, user_id, evaluation_id, action_type, notes, action_metadata, created_at) FROM stdin;
\.


--
-- Data for Name: job_positions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.job_positions (id, title, description, salary, currency, is_active, slots_available, requirements, created_at, updated_at) FROM stdin;
ab30c217-a196-4873-acd9-075a2474b542	Ejecutivo de Ventas	Responsable de ventas B2B y gestión de cartera de clientes	2500.00	PEN	t	2	{"skills": ["ventas", "negociación", "crm"], "availability": "full_time", "experience_years": 2}	2026-02-14 17:16:05.931775-05	2026-02-14 17:16:05.931775-05
a3983c16-9d1a-4b9c-acb3-29bcfa42c664	Asistente Administrativo	Apoyo en gestión documental y atención al cliente	1800.00	PEN	t	1	{"skills": ["excel", "organización", "comunicación"], "availability": "full_time", "experience_years": 1}	2026-02-14 17:16:05.931775-05	2026-02-14 17:16:05.931775-05
\.


--
-- Data for Name: prospect_documents; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.prospect_documents (id, prospect_id, document_type, file_name, original_file_name, storage_type, storage_path, file_data, file_size, mime_type, checksum, sharepoint_url, sync_status, uploaded_at) FROM stdin;
\.


--
-- Data for Name: prospect_documents_access_log; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.prospect_documents_access_log (id, document_id, accessed_by, access_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: prospects; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.prospects (id, first_name, last_name, email, phone, parsed_from_cv, cv_summary, created_at) FROM stdin;
\.


--
-- Data for Name: question_templates; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.question_templates (id, position_id, question_text, question_type, test_number, question_order, validation_type, expected_keywords, ideal_answer, ideal_embedding, min_similarity, weight, is_active, created_at) FROM stdin;
4afec245-b3f9-452e-bf2c-35d01616ca98	ab30c217-a196-4873-acd9-075a2474b542	¿Cuál es tu experiencia en ventas B2B?	role_specific	1	1	semantic	[]	Tengo experiencia en ventas B2B trabajando con empresas medianas y grandes, gestionando ciclos de venta largos, negociando contratos y manteniendo relaciones comerciales a largo plazo.	\N	0.65	1.00	t	2026-02-14 17:16:05.941162-05
10df0ba1-6180-4c9b-882f-2c0e747d6be0	ab30c217-a196-4873-acd9-075a2474b542	¿Cómo manejarías una objeción de precio alto?	role_specific	1	2	semantic	[]	Enfocándome en el valor y ROI del producto, mostrando casos de éxito similares, ofreciendo comparativas con la competencia y explorando opciones de pago flexibles si es necesario.	\N	0.65	1.00	t	2026-02-14 17:16:05.941162-05
94c1aafe-a6b5-43ff-80af-2ae6a7dcd7d4	ab30c217-a196-4873-acd9-075a2474b542	Describe tu mejor cierre de venta	role_specific	1	3	semantic	[]	Logré cerrar una venta importante identificando las necesidades reales del cliente, demostrando valor tangible y construyendo confianza durante el proceso de negociación.	\N	0.60	1.00	t	2026-02-14 17:16:05.941162-05
a008f909-55c5-4b38-86d7-52840ed8a0f4	ab30c217-a196-4873-acd9-075a2474b542	¿Qué CRM has utilizado?	role_specific	1	4	keyword	[]	He trabajado con Salesforce, HubSpot y Zoho CRM para gestión de pipeline y seguimiento de oportunidades.	\N	0.50	1.00	t	2026-02-14 17:16:05.941162-05
6ace42b3-c19e-490c-ae29-2328a8392671	ab30c217-a196-4873-acd9-075a2474b542	¿Cuál es tu meta de ventas mensual realista?	role_specific	1	5	numeric	[]	Mi meta mensual realista es entre S/50,000 y S/100,000 dependiendo del producto y ciclo de venta.	\N	0.60	1.00	t	2026-02-14 17:16:05.941162-05
9f55dffe-ce42-49c9-b174-beca559fe8c2	ab30c217-a196-4873-acd9-075a2474b542	¿Cómo priorizas múltiples tareas urgentes?	transversal	2	1	semantic	[]	Evalúo el impacto y urgencia de cada tarea, comunico prioridades al equipo, delego cuando es posible y mantengo flexibilidad para ajustar según cambios.	\N	0.65	1.00	t	2026-02-14 17:16:05.941162-05
228bb0cd-c637-486a-a41c-5b5cb62497cc	ab30c217-a196-4873-acd9-075a2474b542	Describe un conflicto laboral que hayas resuelto	transversal	2	2	semantic	[]	Tuve un desacuerdo con un compañero, conversamos abiertamente, escuché su perspectiva, llegamos a un acuerdo de colaboración y establecimos reglas claras para el futuro.	\N	0.65	1.00	t	2026-02-14 17:16:05.941162-05
78a18d3a-2780-42fa-ac93-a6d62e2dd63b	ab30c217-a196-4873-acd9-075a2474b542	¿Estás de acuerdo con el salario de S/2,500 mensuales?	transversal	2	3	boolean	[]	Sí, estoy de acuerdo con la propuesta salarial.	\N	0.80	1.00	t	2026-02-14 17:16:05.941162-05
c595df0d-84d3-4bb5-8fe2-88ab334dedb1	ab30c217-a196-4873-acd9-075a2474b542	¿Qué harías si un cliente te pide algo fuera de política?	transversal	2	4	semantic	[]	Explicaría las políticas de la empresa, buscaría alternativas dentro del marco permitido, escalaría con mi supervisor si es necesario y mantendría la relación positiva con el cliente.	\N	0.65	1.00	t	2026-02-14 17:16:05.941162-05
5fae1ddd-4143-4c5a-9c22-db674b00e893	ab30c217-a196-4873-acd9-075a2474b542	¿Tienes disponibilidad para trabajar ocasionalmente fines de semana?	transversal	2	5	boolean	[]	Sí, tengo disponibilidad para trabajar fines de semana cuando sea necesario.	\N	0.75	1.00	t	2026-02-14 17:16:05.941162-05
64756d4e-b61a-457e-b4d3-6bd4d37b5c9a	a3983c16-9d1a-4b9c-acb3-29bcfa42c664	¿Qué herramientas ofimáticas dominas?	role_specific	1	2	keyword	[]	Domino Microsoft Office especialmente Excel con fórmulas y tablas dinámicas, Word para documentos profesionales, PowerPoint para presentaciones, y Outlook para gestión de correos.	\N	0.50	1.00	t	2026-02-14 17:16:06.100367-05
9109e575-2681-489d-a9fa-b791ad27e899	a3983c16-9d1a-4b9c-acb3-29bcfa42c664	¿Tienes experiencia con sistemas ERP o CRM?	role_specific	1	5	boolean	[]	Sí, he trabajado con sistemas de gestión empresarial para registro de operaciones y seguimiento de clientes.	\N	0.70	1.00	t	2026-02-14 17:16:06.100367-05
ca2c5ebc-2fbd-4922-bd25-06d786ab01ba	a3983c16-9d1a-4b9c-acb3-29bcfa42c664	¿Estás de acuerdo con el salario de S/1,800 mensuales?	transversal	2	3	boolean	[]	Sí, estoy de acuerdo con la propuesta salarial.	\N	0.80	1.00	t	2026-02-14 17:16:06.100367-05
965dc811-3658-4213-885b-10d0c2323288	a3983c16-9d1a-4b9c-acb3-29bcfa42c664	¿Tienes disponibilidad inmediata?	transversal	2	4	boolean	[]	Sí, tengo disponibilidad inmediata para empezar.	\N	0.75	1.00	t	2026-02-14 17:16:06.100367-05
0bc93624-4085-4fec-bd26-eda236d14860	a3983c16-9d1a-4b9c-acb3-29bcfa42c664	¿Qué experiencia tienes en atención al cliente?	role_specific	1	1	semantic	[]	Tengo experiencia atendiendo clientes de manera presencial, telefónica y por email, resolviendo consultas, gestionando quejas y brindando información sobre productos o servicios.	\N	0.65	1.00	t	2026-02-14 17:16:06.100367-05
32540906-2c34-4511-afb2-4adb9509c388	a3983c16-9d1a-4b9c-acb3-29bcfa42c664	Describe tu experiencia en gestión documental	role_specific	1	3	semantic	[]	He gestionado archivos físicos y digitales, organizado documentación por fechas y categorías, digitalizado documentos, y mantenido sistemas de archivo ordenados y actualizados.	\N	0.60	1.00	t	2026-02-14 17:16:06.100367-05
e00b0700-00eb-4146-9087-ab9fc225106f	a3983c16-9d1a-4b9c-acb3-29bcfa42c664	¿Cómo organizas múltiples tareas diarias?	role_specific	1	4	semantic	[]	Utilizo listas de prioridades, calendario digital, establezco deadlines realistas, comunico avances, y mantengo flexibilidad para ajustar según urgencias.	\N	0.60	1.00	t	2026-02-14 17:16:06.100367-05
b4958f75-00ee-45a3-b793-e5e3d0e264b2	a3983c16-9d1a-4b9c-acb3-29bcfa42c664	Describe un error que hayas cometido y cómo lo resolviste	transversal	2	1	semantic	[]	Cometí un error al enviar información incorrecta, lo reporté inmediatamente a mi supervisor, corregí el error, implementé un checklist de verificación y aprendí a revisar dos veces antes de enviar.	\N	0.65	1.00	t	2026-02-14 17:16:06.100367-05
43393bb8-3c6e-426d-99c7-e5dc680253fc	a3983c16-9d1a-4b9c-acb3-29bcfa42c664	¿Cómo manejas situaciones de estrés o presión?	transversal	2	2	semantic	[]	Respiro profundo, priorizo lo urgente, comunico mi capacidad actual, pido ayuda si es necesario, y mantengo la calma para tomar decisiones acertadas.	\N	0.65	1.00	t	2026-02-14 17:16:06.100367-05
e7c23461-975b-44dd-b715-94dee3746a20	a3983c16-9d1a-4b9c-acb3-29bcfa42c664	¿Por qué te interesa trabajar como Asistente Administrativo?	transversal	2	5	semantic	[]	Me gusta la organización, el trabajo administrativo me permite usar mis habilidades de atención al detalle, comunicación y gestión, además de contribuir al funcionamiento eficiente de la empresa.	\N	0.65	1.00	t	2026-02-14 17:16:06.100367-05
\.


--
-- Data for Name: sesiones; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.sesiones (id, usuario_id, token_hash, expira_at, revocado, ip_address, user_agent, created_at) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (id, email, password_hash, full_name, role, is_active, last_login, created_at) FROM stdin;
6238d835-1e7a-4763-8d48-3d1a7dfc59aa	rrhh@empresa.com	$2a$06$J0cKUOg2sOjCtFxqkuzgaO3Jyt9FH1gnFuVjZkbuWdPOMcNWwcu3O	María Rodríguez	admin	t	\N	2026-02-14 17:16:05.954806-05
\.


--
-- Name: conocimiento_rag conocimiento_rag_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.conocimiento_rag
    ADD CONSTRAINT conocimiento_rag_pkey PRIMARY KEY (id);


--
-- Name: evaluation_answers evaluation_answers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.evaluation_answers
    ADD CONSTRAINT evaluation_answers_pkey PRIMARY KEY (id);


--
-- Name: evaluations evaluations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.evaluations
    ADD CONSTRAINT evaluations_pkey PRIMARY KEY (id);


--
-- Name: evaluations evaluations_session_token_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.evaluations
    ADD CONSTRAINT evaluations_session_token_key UNIQUE (session_token);


--
-- Name: graph_checkpoint_writes graph_checkpoint_writes_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.graph_checkpoint_writes
    ADD CONSTRAINT graph_checkpoint_writes_pkey PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx);


--
-- Name: graph_checkpoints graph_checkpoints_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.graph_checkpoints
    ADD CONSTRAINT graph_checkpoints_pkey PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id);


--
-- Name: hr_actions hr_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.hr_actions
    ADD CONSTRAINT hr_actions_pkey PRIMARY KEY (id);


--
-- Name: job_positions job_positions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_positions
    ADD CONSTRAINT job_positions_pkey PRIMARY KEY (id);


--
-- Name: prospect_documents_access_log prospect_documents_access_log_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prospect_documents_access_log
    ADD CONSTRAINT prospect_documents_access_log_pkey PRIMARY KEY (id);


--
-- Name: prospect_documents prospect_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prospect_documents
    ADD CONSTRAINT prospect_documents_pkey PRIMARY KEY (id);


--
-- Name: prospects prospects_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prospects
    ADD CONSTRAINT prospects_email_key UNIQUE (email);


--
-- Name: prospects prospects_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prospects
    ADD CONSTRAINT prospects_pkey PRIMARY KEY (id);


--
-- Name: question_templates question_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.question_templates
    ADD CONSTRAINT question_templates_pkey PRIMARY KEY (id);


--
-- Name: sesiones sesiones_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sesiones
    ADD CONSTRAINT sesiones_pkey PRIMARY KEY (id);


--
-- Name: sesiones sesiones_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sesiones
    ADD CONSTRAINT sesiones_token_hash_key UNIQUE (token_hash);


--
-- Name: evaluations unique_active_evaluation; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.evaluations
    ADD CONSTRAINT unique_active_evaluation EXCLUDE USING gist (prospect_id WITH =, position_id WITH =, tstzrange(started_at, COALESCE(completed_at, 'infinity'::timestamp with time zone), '[)'::text) WITH &&) WHERE (((status)::text = ANY ((ARRAY['in_progress'::character varying, 'pending_review'::character varying])::text[])));


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_answers_embedding; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_answers_embedding ON public.evaluation_answers USING ivfflat (answer_embedding public.vector_cosine_ops) WITH (lists='50');


--
-- Name: idx_answers_evaluation; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_answers_evaluation ON public.evaluation_answers USING btree (evaluation_id);


--
-- Name: idx_conocimiento_embedding; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_conocimiento_embedding ON public.conocimiento_rag USING ivfflat (embedding public.vector_cosine_ops) WITH (lists='50');


--
-- Name: idx_conocimiento_metadata; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_conocimiento_metadata ON public.conocimiento_rag USING gin (metadata);


--
-- Name: idx_conocimiento_tipo; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_conocimiento_tipo ON public.conocimiento_rag USING btree (tipo) WHERE (activo = true);


--
-- Name: idx_documents_prospect; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_documents_prospect ON public.prospect_documents USING btree (prospect_id);


--
-- Name: idx_evaluations_pending; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_evaluations_pending ON public.evaluations USING btree (status) WHERE ((status)::text = 'pending_review'::text);


--
-- Name: idx_evaluations_position; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_evaluations_position ON public.evaluations USING btree (position_id);


--
-- Name: idx_evaluations_prospect; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_evaluations_prospect ON public.evaluations USING btree (prospect_id);


--
-- Name: idx_evaluations_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_evaluations_status ON public.evaluations USING btree (status);


--
-- Name: idx_graph_checkpoint_writes_checkpoint; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_graph_checkpoint_writes_checkpoint ON public.graph_checkpoint_writes USING btree (checkpoint_id);


--
-- Name: idx_graph_checkpoint_writes_thread; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_graph_checkpoint_writes_thread ON public.graph_checkpoint_writes USING btree (thread_id);


--
-- Name: idx_graph_checkpoints_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_graph_checkpoints_created ON public.graph_checkpoints USING btree (created_at);


--
-- Name: idx_graph_checkpoints_parent; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_graph_checkpoints_parent ON public.graph_checkpoints USING btree (parent_checkpoint_id);


--
-- Name: idx_graph_checkpoints_thread; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_graph_checkpoints_thread ON public.graph_checkpoints USING btree (thread_id);


--
-- Name: idx_hr_actions_evaluation; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_hr_actions_evaluation ON public.hr_actions USING btree (evaluation_id);


--
-- Name: idx_hr_actions_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_hr_actions_user ON public.hr_actions USING btree (user_id);


--
-- Name: idx_positions_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_positions_active ON public.job_positions USING btree (is_active) WHERE (is_active = true);


--
-- Name: idx_prospects_email; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_prospects_email ON public.prospects USING btree (email);


--
-- Name: idx_questions_embedding; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_questions_embedding ON public.question_templates USING ivfflat (ideal_embedding public.vector_cosine_ops) WITH (lists='50');


--
-- Name: idx_questions_position; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_questions_position ON public.question_templates USING btree (position_id, test_number, question_order);


--
-- Name: idx_sesiones_expiracion; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_sesiones_expiracion ON public.sesiones USING btree (expira_at);


--
-- Name: idx_sesiones_token; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_sesiones_token ON public.sesiones USING btree (token_hash);


--
-- Name: idx_sesiones_usuario; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_sesiones_usuario ON public.sesiones USING btree (usuario_id);


--
-- Name: evaluation_answers evaluation_answers_evaluation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.evaluation_answers
    ADD CONSTRAINT evaluation_answers_evaluation_id_fkey FOREIGN KEY (evaluation_id) REFERENCES public.evaluations(id) ON DELETE CASCADE;


--
-- Name: evaluation_answers evaluation_answers_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.evaluation_answers
    ADD CONSTRAINT evaluation_answers_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.question_templates(id) ON DELETE CASCADE;


--
-- Name: evaluations evaluations_position_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.evaluations
    ADD CONSTRAINT evaluations_position_id_fkey FOREIGN KEY (position_id) REFERENCES public.job_positions(id) ON DELETE CASCADE;


--
-- Name: evaluations evaluations_prospect_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.evaluations
    ADD CONSTRAINT evaluations_prospect_id_fkey FOREIGN KEY (prospect_id) REFERENCES public.prospects(id) ON DELETE CASCADE;


--
-- Name: graph_checkpoint_writes graph_checkpoint_writes_thread_id_checkpoint_ns_checkpoint_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.graph_checkpoint_writes
    ADD CONSTRAINT graph_checkpoint_writes_thread_id_checkpoint_ns_checkpoint_fkey FOREIGN KEY (thread_id, checkpoint_ns, checkpoint_id) REFERENCES public.graph_checkpoints(thread_id, checkpoint_ns, checkpoint_id) ON DELETE CASCADE;


--
-- Name: hr_actions hr_actions_evaluation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.hr_actions
    ADD CONSTRAINT hr_actions_evaluation_id_fkey FOREIGN KEY (evaluation_id) REFERENCES public.evaluations(id);


--
-- Name: hr_actions hr_actions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.hr_actions
    ADD CONSTRAINT hr_actions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: prospect_documents_access_log prospect_documents_access_log_accessed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prospect_documents_access_log
    ADD CONSTRAINT prospect_documents_access_log_accessed_by_fkey FOREIGN KEY (accessed_by) REFERENCES public.users(id);


--
-- Name: prospect_documents_access_log prospect_documents_access_log_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prospect_documents_access_log
    ADD CONSTRAINT prospect_documents_access_log_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.prospect_documents(id);


--
-- Name: prospect_documents prospect_documents_prospect_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prospect_documents
    ADD CONSTRAINT prospect_documents_prospect_id_fkey FOREIGN KEY (prospect_id) REFERENCES public.prospects(id) ON DELETE CASCADE;


--
-- Name: question_templates question_templates_position_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.question_templates
    ADD CONSTRAINT question_templates_position_id_fkey FOREIGN KEY (position_id) REFERENCES public.job_positions(id) ON DELETE CASCADE;


--
-- Name: sesiones sesiones_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sesiones
    ADD CONSTRAINT sesiones_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict vUgjkY3yjJ0o43jctEEHc8mTxyNmHLCK4ar3lFQHWe3cpcdYCrfqkWrIUzK2qTx

