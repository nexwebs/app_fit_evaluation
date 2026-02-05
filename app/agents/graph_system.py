"""
app/agents/graph_system.py
"""
from typing import TypedDict, Annotated, Sequence, Dict, Any, List
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from uuid import UUID

from app.models import Evaluation, QuestionTemplate, EvaluationAnswer, Prospect, JobPosition
from app.services.embeddings import embedding_service
from app.tools.email_tools import send_evaluation_result_email, send_hr_notification


def limit_messages(existing: Sequence[BaseMessage], new: Sequence[BaseMessage]) -> Sequence[BaseMessage]:
    MAX_MESSAGES = 6
    combined = list(existing) + list(new)
    return combined[-MAX_MESSAGES:] if len(combined) > MAX_MESSAGES else combined


class EvaluationState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], limit_messages]
    evaluation_id: str
    session_token: str
    position_id: str
    current_test: int
    current_question: int
    total_questions_test_1: int
    total_questions_test_2: int
    current_question_data: Dict[str, Any]
    prospect_id: str
    prospect_name: str
    prospect_email: str
    should_close: bool
    is_complete: bool
    workflow_stage: str
    selected_position: str
    cv_uploaded: bool
    data_confirmed: bool
    available_positions: List[Dict[str, Any]]
    waiting_for_start: bool


class EvaluationAgent:

    def __init__(self, db: AsyncSession, openai_key: str, checkpointer=None):
        self.db = db
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.7,
            api_key=openai_key,
            max_tokens=300,
            timeout=20.0
        )
        self.checkpointer = checkpointer
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(EvaluationState)

        workflow.add_node("router", self._route_workflow)
        workflow.add_node("greet_and_list_positions", self._greet_and_list_positions)
        workflow.add_node("process_position_selection", self._process_position_selection)
        workflow.add_node("request_cv_upload", self._request_cv_upload)
        workflow.add_node("display_extracted_data", self._display_extracted_data)
        workflow.add_node("process_confirmation", self._process_confirmation)
        workflow.add_node("initialize_evaluation", self._initialize_evaluation)
        workflow.add_node("await_start_confirmation", self._await_start_confirmation)
        workflow.add_node("fetch_current_question", self._fetch_current_question)
        workflow.add_node("send_question", self._send_question)
        workflow.add_node("score_answer", self._score_answer)
        workflow.add_node("complete_evaluation", self._complete_evaluation)

        workflow.set_entry_point("router")
        
        workflow.add_conditional_edges(
            "router",
            self._route_by_stage,
            {
                "greet": "greet_and_list_positions",
                "select_position": "process_position_selection",
                "request_cv": "request_cv_upload",
                "display_cv": "display_extracted_data",
                "confirm": "process_confirmation",
                "init_eval": "initialize_evaluation",
                "await_start": "await_start_confirmation",
                "eval": "fetch_current_question",
                "score": "score_answer",
                "end": END
            }
        )
        
        workflow.add_edge("greet_and_list_positions", END)
        workflow.add_edge("process_position_selection", END)
        workflow.add_edge("request_cv_upload", END)
        workflow.add_edge("display_extracted_data", END)
        
        workflow.add_conditional_edges(
            "process_confirmation",
            lambda s: "init" if s.get("data_confirmed") else "wait",
            {"init": "initialize_evaluation", "wait": END}
        )
        
        workflow.add_conditional_edges(
            "initialize_evaluation",
            lambda s: "eval" if s.get("workflow_stage") == "in_progress" else "await_start",
            {"eval": "fetch_current_question", "await_start": "await_start_confirmation"}
        )
        
        workflow.add_conditional_edges(
            "await_start_confirmation",
            lambda s: "eval" if s.get("workflow_stage") == "in_progress" else "end",
            {"eval": "fetch_current_question", "end": END}
        )
        
        workflow.add_edge("fetch_current_question", "send_question")
        workflow.add_edge("send_question", END)

        workflow.add_conditional_edges(
            "score_answer",
            lambda s: "next" if not s.get("is_complete") else "finish",
            {"next": "fetch_current_question", "finish": "complete_evaluation"}
        )

        workflow.add_edge("complete_evaluation", END)

        return workflow.compile(checkpointer=self.checkpointer)

    def _route_workflow(self, state: EvaluationState) -> EvaluationState:
        return state
    
    def _route_by_stage(self, state: EvaluationState) -> str:
        stage = state.get("workflow_stage", "initial")
        
        if state.get("should_close") or state.get("is_complete"):
            return "end"
        
        if stage == "initial":
            return "greet"
        elif stage == "awaiting_position":
            return "select_position"
        elif stage == "position_selected":
            return "request_cv"
        elif stage == "awaiting_cv":
            return "end"
        elif stage == "cv_just_uploaded":
            return "display_cv"
        elif stage == "awaiting_confirmation":
            return "confirm"
        elif stage == "data_confirmed":
            return "init_eval"
        elif stage == "evaluation_initialized":
            return "await_start"
        elif stage == "awaiting_start":
            messages = state.get("messages", [])
            if messages and isinstance(messages[-1], HumanMessage):
                return "await_start"
            else:
                return "end"
        elif stage == "in_progress":
            eval_id = state.get("evaluation_id")
            if not eval_id:
                return "end"
            
            messages = state.get("messages", [])
            if messages and isinstance(messages[-1], HumanMessage):
                content = messages[-1].content
                if not content.startswith("[SYSTEM_EVENT"):
                    return "score"
            
            return "eval"
        else:
            return "end"

    def _extract_user_message(self, state: EvaluationState) -> str:
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                content = msg.content
                if content.startswith("[SYSTEM_EVENT:") and content.endswith("]"):
                    continue
                return content
        return ""

    async def _greet_and_list_positions(self, state: EvaluationState) -> EvaluationState:
        positions = await self._load_active_positions()
        
        if not positions:
            state["should_close"] = True
            state["messages"] = list(state.get("messages", [])) + [AIMessage(content="No hay posiciones activas.")]
            return state

        state["available_positions"] = positions

        greeting = "Bienvenido al proceso de selección.\n\nPosiciones disponibles:\n\n"
        
        for idx, pos in enumerate(positions, 1):
            greeting += f"{idx}. {pos['title']}\n"
            greeting += f"   Salario: {pos['currency']} {pos['salary']}\n"
            if pos['description']:
                desc = pos['description'][:150]
                greeting += f"   {desc}\n"
            greeting += "\n"
        
        greeting += "Escribe el número o nombre de la posición que te interesa."

        state["messages"] = list(state.get("messages", [])) + [AIMessage(content=greeting)]
        state["workflow_stage"] = "awaiting_position"
        state["should_close"] = False
        state["is_complete"] = False
        
        return state

    async def _process_position_selection(self, state: EvaluationState) -> EvaluationState:
        user_input = self._extract_user_message(state).strip()
        
        if not user_input:
            return state
        
        positions = state.get("available_positions", [])
        
        if not positions:
            positions = await self._load_active_positions()
            state["available_positions"] = positions
        
        selected = None
        
        try:
            num = int(user_input)
            if 1 <= num <= len(positions):
                selected = positions[num - 1]
        except ValueError:
            selected = self._match_position_by_name(user_input, positions)
        
        if selected:
            state["position_id"] = str(selected["id"])
            state["selected_position"] = selected["title"]
            state["workflow_stage"] = "position_selected"
            
            state["messages"] = list(state.get("messages", [])) + [AIMessage(
                content=f"Has seleccionado: {selected['title']}.\n\nPerfecto, ahora necesito tu CV."
            )]
        else:
            state["messages"] = list(state.get("messages", [])) + [AIMessage(
                content="No encontré esa posición. Ingresa el número o nombre exacto."
            )]
        
        return state

    def _match_position_by_name(self, user_input: str, positions: List[Dict]) -> Dict[str, Any]:
        lower = user_input.lower()
        
        for pos in positions:
            if pos['title'].lower() == lower:
                return pos
        
        for pos in positions:
            if lower in pos['title'].lower():
                return pos
        
        user_words = set(lower.split())
        for pos in positions:
            title_words = set(pos['title'].lower().split())
            if len(user_words & title_words) >= min(2, len(user_words)):
                return pos
        
        return None

    async def _request_cv_upload(self, state: EvaluationState) -> EvaluationState:
        state["messages"] = list(state.get("messages", [])) + [AIMessage(
            content="Por favor, sube tu CV en formato PDF."
        )]
        state["workflow_stage"] = "awaiting_cv"
        
        return state

    async def _display_extracted_data(self, state: EvaluationState) -> EvaluationState:
        if not state.get("prospect_id"):
            state["messages"] = list(state.get("messages", [])) + [AIMessage(
                content="Error: No se encontró información del prospecto"
            )]
            return state
        
        prospect = await self._load_prospect(UUID(state["prospect_id"]))
        
        confirmation = f"Datos extraídos de tu CV:\n\n"
        confirmation += f"Nombre: {prospect.first_name} {prospect.last_name}\n"
        confirmation += f"Email: {prospect.email}\n"
        confirmation += f"Teléfono: {prospect.phone}\n\n"
        confirmation += "¿Los datos son correctos? (Sí/No)"
        
        state["messages"] = list(state.get("messages", [])) + [AIMessage(content=confirmation)]
        state["workflow_stage"] = "awaiting_confirmation"
        
        return state
    
    async def _process_confirmation(self, state: EvaluationState) -> EvaluationState:
        user_msg = self._extract_user_message(state).lower()
        
        if "si" in user_msg or "correcto" in user_msg or "sí" in user_msg:
            state["data_confirmed"] = True
            state["workflow_stage"] = "data_confirmed"
            
            state["messages"] = list(state.get("messages", [])) + [AIMessage(
                content="Perfecto. Ahora crearemos tu evaluación."
            )]
        elif "no" in user_msg:
            state["messages"] = list(state.get("messages", [])) + [AIMessage(
                content="Corrige los datos y vuelve a subir tu CV."
            )]
            state["cv_uploaded"] = False
            state["data_confirmed"] = False
            state["workflow_stage"] = "awaiting_cv"
        else:
            state["messages"] = list(state.get("messages", [])) + [AIMessage(
                content="No entendí. Por favor responde 'Sí' o 'No'."
            )]
        
        return state

    async def _initialize_evaluation(self, state: EvaluationState) -> EvaluationState:
        if not state.get("data_confirmed"):
            state["messages"] = list(state.get("messages", [])) + [AIMessage(content="Error: Datos no confirmados.")]
            return state
        
        if not state.get("prospect_id"):
            state["messages"] = list(state.get("messages", [])) + [AIMessage(content="Error: No hay prospecto.")]
            return state
        
        if not state.get("position_id"):
            state["messages"] = list(state.get("messages", [])) + [AIMessage(content="Error: No hay posición.")]
            return state
        
        prospect_id = UUID(state["prospect_id"])
        position_id = UUID(state["position_id"])
        
        await self._cleanup_orphaned_evaluation(prospect_id, position_id)
        
        existing_eval = await self._check_for_recent_evaluation(prospect_id, position_id)
        
        if existing_eval:
            if existing_eval['can_continue']:
                state["evaluation_id"] = str(existing_eval['id'])
                state["current_test"] = existing_eval['current_test']
                state["current_question"] = existing_eval['current_question']
                
                questions_test_1 = await self._load_questions(position_id, 1)
                questions_test_2 = await self._load_questions(position_id, 2)
                
                state["total_questions_test_1"] = len(questions_test_1)
                state["total_questions_test_2"] = len(questions_test_2)
                
                state["workflow_stage"] = "in_progress"
                state["waiting_for_start"] = False
                
                state["messages"] = list(state.get("messages", [])) + [AIMessage(
                    content=f"Continuando evaluación en Test {state['current_test']}, Pregunta {state['current_question']}."
                )]
                
                return state
            else:
                state["should_close"] = True
                state["messages"] = list(state.get("messages", [])) + [AIMessage(content=existing_eval['reason'])]
                return state
        
        evaluation = Evaluation(
            prospect_id=prospect_id,
            position_id=position_id,
            session_token=state["session_token"],
            status="in_progress",
            current_test=1,
            current_question=1
        )
        
        self.db.add(evaluation)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(evaluation)
        
        state["evaluation_id"] = str(evaluation.id)
        
        questions_test_1 = await self._load_questions(position_id, 1)
        questions_test_2 = await self._load_questions(position_id, 2)
        
        if not questions_test_1:
            state["messages"] = list(state.get("messages", [])) + [AIMessage(
                content="Error: No hay preguntas configuradas."
            )]
            state["should_close"] = True
            return state

        state["total_questions_test_1"] = len(questions_test_1)
        state["total_questions_test_2"] = len(questions_test_2)
        
        state["current_test"] = 1
        state["current_question"] = 1
        
        state["workflow_stage"] = "evaluation_initialized"
        
        return state
    
    async def _cleanup_orphaned_evaluation(self, prospect_id: UUID, position_id: UUID):
        result = await self.db.execute(
            text("""
                UPDATE evaluations
                SET 
                    status = 'abandoned',
                    completed_at = CURRENT_TIMESTAMP
                WHERE prospect_id = :prospect_id
                AND position_id = :position_id
                AND status = 'in_progress'
                AND (
                    NOT EXISTS (
                        SELECT 1 FROM evaluation_answers 
                        WHERE evaluation_id = evaluations.id
                    )
                    OR
                    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - started_at))/60 > 5
                )
                RETURNING id
            """),
            {
                "prospect_id": str(prospect_id),
                "position_id": str(position_id)
            }
        )
        
        abandoned_evals = result.fetchall()
        
        if abandoned_evals:
            await self.db.commit()
    
    async def _check_for_recent_evaluation(self, prospect_id: UUID, position_id: UUID) -> Dict[str, Any]:
        result = await self.db.execute(
            text("""
                SELECT 
                    e.id,
                    e.current_test,
                    e.current_question,
                    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - e.started_at))/60 as minutes_ago
                FROM evaluations e
                WHERE e.prospect_id = :prospect_id
                AND e.position_id = :position_id
                AND e.status = 'in_progress'
                ORDER BY e.started_at DESC
                LIMIT 1
            """),
            {
                "prospect_id": str(prospect_id),
                "position_id": str(position_id)
            }
        )
        
        row = result.fetchone()
        
        if not row:
            return None
        
        eval_id, current_test, current_question, minutes_ago = row
        
        if minutes_ago <= 5:
            return {
                "id": eval_id,
                "current_test": current_test,
                "current_question": current_question,
                "can_continue": True
            }
        else:
            return {
                "can_continue": False,
                "reason": f"Evaluación abandonada ({int(minutes_ago)} min de inactividad)"
            }
    
    async def _await_start_confirmation(self, state: EvaluationState) -> EvaluationState:
        current_stage = state.get("workflow_stage")
        
        if current_stage == "evaluation_initialized":
            current_test = state.get("current_test", 1)
            current_question = state.get("current_question", 1)
            
            if current_test == 1 and current_question == 1:
                message = "Perfecto. Iniciemos con el Test 1.\n\nEscribe 'Listo' para comenzar."
            else:
                message = f"Continuando Test {current_test}, Pregunta {current_question}.\n\nEscribe 'Listo' para continuar."
            
            state["messages"] = list(state.get("messages", [])) + [AIMessage(content=message)]
            
            state["workflow_stage"] = "awaiting_start"
            state["waiting_for_start"] = True
            
            return state
        
        if current_stage == "awaiting_start":
            messages = state.get("messages", [])
            if not messages or not isinstance(messages[-1], HumanMessage):
                return state
            
            user_msg = self._extract_user_message(state).lower()
            
            if "listo" in user_msg or "empezar" in user_msg or "comenzar" in user_msg or "continuar" in user_msg:
                state["waiting_for_start"] = False
                state["workflow_stage"] = "in_progress"
                
                return state
            else:
                state["messages"] = list(state.get("messages", [])) + [AIMessage(
                    content="Escribe 'Listo' cuando estés preparado."
                )]
                return state
        
        return state

    async def _load_active_positions(self) -> List[Dict[str, Any]]:
        result = await self.db.execute(
            select(JobPosition).where(JobPosition.is_active == True)
        )
        positions = result.scalars().all()
        
        return [
            {
                "id": str(pos.id),
                "title": pos.title,
                "description": pos.description,
                "salary": float(pos.salary) if pos.salary else 0.0,
                "currency": pos.currency
            }
            for pos in positions
        ]

    async def _load_prospect(self, prospect_id: UUID):
        result = await self.db.execute(
            select(Prospect).where(Prospect.id == prospect_id)
        )
        return result.scalar_one_or_none()

    async def _load_questions(self, position_id: UUID, test_number: int):
        result = await self.db.execute(
            select(QuestionTemplate)
            .where(
                QuestionTemplate.position_id == position_id,
                QuestionTemplate.test_number == test_number,
                QuestionTemplate.is_active == True
            )
            .order_by(QuestionTemplate.question_order)
        )
        return result.scalars().all()

    async def _fetch_current_question(self, state: EvaluationState) -> EvaluationState:
        current_test = state.get("current_test", 0)
        current_question = state.get("current_question", 0)

        if current_test == 0 or current_question == 0:
            state["is_complete"] = True
            state["current_question_data"] = {}
            return state

        position_id = UUID(state["position_id"])
        questions = await self._load_questions(position_id, current_test)

        if not questions:
            state["is_complete"] = True
            state["current_question_data"] = {}
            return state

        question_index = current_question - 1
        
        if 0 <= question_index < len(questions):
            q = questions[question_index]
            state["current_question_data"] = {
                "id": str(q.id),
                "text": q.question_text,
                "validation_type": q.validation_type,
                "ideal_answer": q.ideal_answer,
                "expected_keywords": q.expected_keywords,
                "min_similarity": float(q.min_similarity),
                "weight": float(q.weight)
            }
            state["is_complete"] = False
        else:
            state["is_complete"] = True
            state["current_question_data"] = {}
        
        return state

    async def _send_question(self, state: EvaluationState) -> EvaluationState:
        if state.get("is_complete"):
            return state

        message = self._format_question_message(state)
        state["messages"] = list(state.get("messages", [])) + [AIMessage(content=message)]

        return state

    def _format_question_message(self, state: EvaluationState) -> str:
        question_data = state.get("current_question_data", {})
        
        if not question_data:
            return "Error: No se encontró la pregunta"
        
        question_text = question_data.get("text", "")
        current_test = state.get("current_test", 1)
        current_question = state.get("current_question", 1)
        total_questions = state.get("total_questions_test_1", 0) if current_test == 1 else state.get("total_questions_test_2", 0)
        prospect_name = state.get("prospect_name", "")

        if current_test == 1 and current_question == 1:
            return f"Hola {prospect_name}, comenzaremos con el Test 1.\n\nPregunta {current_question}/{total_questions}: {question_text}"
        elif current_test == 2 and current_question == 1:
            return f"Excelente. Ahora el Test 2.\n\nPregunta {current_question}/{total_questions}: {question_text}"
        else:
            return f"Pregunta {current_question}/{total_questions}: {question_text}"

    async def _score_answer(self, state: EvaluationState) -> EvaluationState:
        user_answer = self._extract_user_message(state)
        question_data = state.get("current_question_data", {})
        
        if not question_data or "id" not in question_data:
            state["messages"] = list(state.get("messages", [])) + [AIMessage(content="Error: No se pudo cargar la pregunta.")]
            state["should_close"] = True
            return state

        validation_type = question_data.get("validation_type", "semantic")
        
        answer_embedding = None
        if validation_type == "semantic":
            answer_embedding = embedding_service.encode_single(user_answer)
        
        score, similarity_score, matched_keywords, feedback = await self._compute_score(
            user_answer, question_data, answer_embedding
        )

        await self._persist_answer(
            state["evaluation_id"],
            question_data["id"],
            user_answer,
            answer_embedding,
            score,
            similarity_score,
            matched_keywords,
            feedback
        )

        await self._advance_progress(state)
        
        return state

    async def _compute_score(self, user_answer: str, question_data: Dict, answer_embedding):
        score = 0.0
        similarity_score = None
        matched_keywords = []
        feedback = {}

        validation_type = question_data.get("validation_type", "semantic")

        if validation_type == "semantic":
            if answer_embedding is None:
                answer_embedding = embedding_service.encode_single(user_answer)
            score, similarity_score, feedback = await self._apply_semantic_validation(
                question_data, answer_embedding
            )
        elif validation_type == "keyword":
            score, matched_keywords, feedback = self._apply_keyword_validation(
                user_answer, question_data
            )
        elif validation_type == "boolean":
            score, feedback = self._apply_boolean_validation(user_answer)
        elif validation_type == "numeric":
            score = 70
            feedback["type"] = "numeric_answer_detected"

        return score, similarity_score, matched_keywords, feedback

    async def _apply_semantic_validation(self, question_data: Dict, answer_embedding):
        feedback = {}

        if not question_data.get("ideal_answer"):
            return 0.0, None, feedback

        ideal_embedding_result = await self.db.execute(
            text("SELECT ideal_embedding FROM question_templates WHERE id = :question_id"),
            {"question_id": question_data["id"]}
        )
        ideal_embedding_row = ideal_embedding_result.fetchone()

        if not ideal_embedding_row or not ideal_embedding_row[0]:
            return 0.0, None, feedback

        similarity = embedding_service.cosine_similarity(
            answer_embedding,
            ideal_embedding_row[0]
        )

        min_similarity = question_data.get("min_similarity", 0.65)

        if similarity >= min_similarity:
            score = min(100, (similarity / min_similarity) * 100)
        else:
            score = (similarity / min_similarity) * 70

        feedback["similarity"] = round(similarity, 4)
        feedback["threshold"] = min_similarity

        return score, similarity, feedback

    def _apply_keyword_validation(self, user_answer: str, question_data: Dict):
        keywords = question_data.get("expected_keywords", [])
        user_answer_lower = user_answer.lower()
        matched_keywords = []

        for keyword in keywords:
            if keyword.lower() in user_answer_lower:
                matched_keywords.append(keyword)

        score = (len(matched_keywords) / len(keywords)) * 100 if keywords else 0

        feedback = {
            "matched": len(matched_keywords),
            "total": len(keywords)
        }

        return score, matched_keywords, feedback

    def _apply_boolean_validation(self, user_answer: str):
        affirmative = ["si", "yes", "afirmativo", "correcto", "de acuerdo", "acepto"]
        negative = ["no", "negativo", "incorrecto", "desacuerdo", "rechazo"]

        user_lower = user_answer.lower()

        if any(word in user_lower for word in affirmative):
            return 100, {"response": "affirmative"}
        elif any(word in user_lower for word in negative):
            return 0, {"response": "negative"}
        else:
            return 50, {"response": "unclear"}

    async def _persist_answer(self, evaluation_id, question_id, answer_text,
                          answer_embedding, score, similarity_score,
                          matched_keywords, feedback):
        
        if not answer_embedding or len(answer_embedding) == 0:
            answer_embedding = None
        
        answer_record = EvaluationAnswer(
            evaluation_id=UUID(evaluation_id),
            question_id=UUID(question_id),
            answer_text=answer_text,
            answer_embedding=answer_embedding,
            score=score,
            similarity_score=similarity_score,
            matched_keywords=matched_keywords,
            feedback_points=feedback
        )

        self.db.add(answer_record)
        await self.db.flush()
        await self.db.commit()

    async def _advance_progress(self, state: EvaluationState):
        current_test = state["current_test"]
        current_question = state["current_question"]
        total_questions_current = state["total_questions_test_1"] if current_test == 1 else state["total_questions_test_2"]

        if current_test == 1 and current_question >= total_questions_current:
            await self.db.execute(
                text("UPDATE evaluations SET current_test = 2, current_question = 1 WHERE id = :eval_id"),
                {"eval_id": state["evaluation_id"]}
            )
            await self.db.commit()
            state["current_test"] = 2
            state["current_question"] = 1
        elif current_test == 2 and current_question >= total_questions_current:
            state["is_complete"] = True
        else:
            await self.db.execute(
                text("UPDATE evaluations SET current_question = current_question + 1 WHERE id = :eval_id"),
                {"eval_id": state["evaluation_id"]}
            )
            await self.db.commit()
            state["current_question"] += 1

    async def _complete_evaluation(self, state: EvaluationState) -> EvaluationState:
        eval_id = state.get("evaluation_id", "")
        
        if not eval_id:
            state["messages"] = list(state.get("messages", [])) + [AIMessage(content="Error: No se pudo recuperar el ID de evaluación.")]
            state["should_close"] = True
            return state
        
        await self._compute_final_scores(eval_id)

        evaluation = await self._load_evaluation_by_id(eval_id)
        prospect = await self._load_prospect(UUID(state["prospect_id"]))
        position_title = await self._load_position_title(UUID(state["position_id"]))

        if prospect.email:
            await self._dispatch_notification_emails(
                evaluation, prospect, position_title
            )

        final_message = self._construct_final_message(state, evaluation)
        state["messages"] = list(state.get("messages", [])) + [AIMessage(content=final_message)]
        state["should_close"] = True
        state["workflow_stage"] = "completed"

        return state

    async def _compute_final_scores(self, evaluation_id: str):
        await self.db.execute(
            text("SELECT calculate_evaluation_scores(:eval_id)"),
            {"eval_id": evaluation_id}
        )
        await self.db.commit()

    async def _load_evaluation_by_id(self, evaluation_id: str):
        result = await self.db.execute(
            select(Evaluation).where(Evaluation.id == UUID(evaluation_id))
        )
        return result.scalar_one()

    async def _load_position_title(self, position_id: UUID) -> str:
        result = await self.db.execute(
            text("SELECT title FROM job_positions WHERE id = :pos_id"),
            {"pos_id": str(position_id)}
        )
        row = result.fetchone()
        return row[0] if row else "Posición"

    async def _dispatch_notification_emails(self, evaluation, prospect, position_title):
        test_1_score = float(evaluation.test_1_score) if evaluation.test_1_score is not None else 0.0
        test_2_score = float(evaluation.test_2_score) if evaluation.test_2_score is not None else 0.0
        total_score = float(evaluation.total_score) if evaluation.total_score is not None else 0.0
        
        await send_evaluation_result_email(
            prospect_email=prospect.email,
            prospect_name=f"{prospect.first_name} {prospect.last_name}",
            total_score=total_score,
            test_1_score=test_1_score,
            test_2_score=test_2_score,
            passed=evaluation.passed_ai
        )

        if evaluation.passed_ai:
            await send_hr_notification(
                evaluation_id=str(evaluation.id),
                prospect_name=f"{prospect.first_name} {prospect.last_name}",
                position_title=position_title,
                total_score=total_score,
                test_1_score=test_1_score,
                test_2_score=test_2_score
            )

        await self.db.execute(
            text("UPDATE evaluations SET email_sent = true WHERE id = :eval_id"),
            {"eval_id": str(evaluation.id)}
        )
        await self.db.commit()

    def _construct_final_message(self, state: EvaluationState, evaluation) -> str:
        test_1 = float(evaluation.test_1_score) if evaluation.test_1_score is not None else 0.0
        test_2 = float(evaluation.test_2_score) if evaluation.test_2_score is not None else 0.0
        total = float(evaluation.total_score) if evaluation.total_score is not None else 0.0
        
        return f"""Evaluación completada.

Test 1: {test_1:.2f}/100
Test 2: {test_2:.2f}/100
Total: {total:.2f}/100

Resultado: {"APROBADO" if evaluation.passed_ai else "NO APROBADO"}

Recibirás un email con los detalles.
Gracias."""

    async def process_message(
        self,
        session_token: str,
        message: str = None,
        initial_state: dict = None,
        event_type: str = "user_message"
    ) -> dict:
        config = {"configurable": {"thread_id": session_token}}
        
        checkpoint = await self.checkpointer.aget_tuple(config)
        
        if checkpoint and checkpoint.checkpoint.get("channel_values"):
            existing_state = checkpoint.checkpoint["channel_values"]
            
            if message:
                input_state = existing_state.copy()
                input_state["messages"] = list(existing_state.get("messages", [])) + [
                    HumanMessage(content=message)
                ]
            elif initial_state:
                input_state = existing_state.copy()
                for key, value in initial_state.items():
                    if key != "messages":
                        input_state[key] = value
                
                if event_type == "cv_uploaded":
                    input_state["messages"] = list(existing_state.get("messages", [])) + [
                        HumanMessage(content="[SYSTEM_EVENT:CV_UPLOADED]")
                    ]
                    input_state["workflow_stage"] = "cv_just_uploaded"
            else:
                input_state = existing_state
        else:
            if message:
                input_state = self._create_initial_state(session_token)
                input_state["messages"] = [HumanMessage(content=message)]
            elif initial_state:
                input_state = self._create_initial_state(session_token)
                for key, value in initial_state.items():
                    if key != "messages":
                        input_state[key] = value
                
                if event_type == "cv_uploaded":
                    input_state["messages"] = [
                        HumanMessage(content="[SYSTEM_EVENT:CV_UPLOADED]")
                    ]
                    input_state["workflow_stage"] = "cv_just_uploaded"
            else:
                input_state = self._create_initial_state(session_token)
        
        final_state = await self.graph.ainvoke(input_state, config)

        last_ai_message = self._extract_last_ai_message(final_state["messages"])

        return {
            "response": last_ai_message or "Error",
            "state": final_state,
            "current_test": final_state.get("current_test", 0),
            "current_question": final_state.get("current_question", 0),
            "is_complete": final_state.get("is_complete", False),
            "should_close": final_state.get("should_close", False),
            "workflow_stage": final_state.get("workflow_stage", "initial")
        }

    def _create_initial_state(self, session_token: str) -> dict:
        return {
            "messages": [],
            "session_token": session_token,
            "workflow_stage": "initial",
            "selected_position": None,
            "cv_uploaded": False,
            "data_confirmed": False,
            "evaluation_id": "",
            "position_id": "",
            "current_test": 0,
            "current_question": 0,
            "total_questions_test_1": 0,
            "total_questions_test_2": 0,
            "current_question_data": {},
            "prospect_id": "",
            "prospect_name": "",
            "prospect_email": "",
            "should_close": False,
            "is_complete": False,
            "available_positions": [],
            "waiting_for_start": False
        }

    def _extract_last_ai_message(self, messages):
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                return msg.content
        return None


async def initialize_graph_system(
    db: AsyncSession,
    openai_key: str,
    checkpointer=None
) -> EvaluationAgent:
    return EvaluationAgent(db, openai_key, checkpointer)