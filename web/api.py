"""Web API для интеграции DevStandart-Coach с портфолио-сайтом."""

import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import get_settings
from services.ai_training_service import AITrainingService
from services.quiz import QUIZ_QUESTIONS
from services.training_service import TrainingService
from web.session_repository import WebSessionRepository

logger = logging.getLogger(__name__)

# Глобальные зависимости
session_repository: WebSessionRepository | None = None
training_service: TrainingService | None = None
ai_service: AITrainingService | None = None


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)


class CollectedData(BaseModel):
    """Собранные данные обучения для preview."""
    employee_name: str | None = None
    topic: str | None = None
    questions_total: int = 0
    correct_answers: int = 0
    score_percent: int = 0
    final_summary: str | None = None


class ChatResponse(BaseModel):
    reply: str
    done: bool = False
    collected_data: CollectedData | None = None
    result_preview: str | None = None
    submitted_to_db: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация и очистка ресурсов"""
    global session_repository, training_service, ai_service

    settings = get_settings()
    logger.info("Initializing onboarding-coach web API services...")

    session_repository = WebSessionRepository()
    training_service = TrainingService()
    ai_service = AITrainingService(settings=settings)

    logger.info("Onboarding-coach web API services initialized")

    yield

    logger.info("Shutting down onboarding-coach web API services...")
    if ai_service:
        await ai_service.close()
    logger.info("Onboarding-coach web API services shut down")


app = FastAPI(
    title="Onboarding Coach Web API",
    description="Web API для AI-наставника по онбордингу сотрудников",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — разрешаем только нужные origins
allowed_origins = [
    "https://portfolio.aiworker43.ru",
    "http://portfolio.aiworker43.ru",
    "http://localhost:3000",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# ── IP-based rate limiting ────────────────────────────────────────────────

_ip_requests: dict[str, list[float]] = defaultdict(list)

WEB_IP_RATE_LIMIT = 40       # максимум запросов с одного IP
WEB_IP_RATE_WINDOW = 3600    # за 1 час (секунды)


def _check_ip_rate_limit(ip: str) -> bool:
    """Возвращает True если лимит НЕ превышен и запрос можно обработать."""
    now = time.time()
    window_start = now - WEB_IP_RATE_WINDOW

    # Убираем устаревшие записи
    _ip_requests[ip] = [t for t in _ip_requests[ip] if t > window_start]

    if len(_ip_requests[ip]) >= WEB_IP_RATE_LIMIT:
        logger.warning("IP rate limit exceeded: ip=%s count=%d", ip, len(_ip_requests[ip]))
        return False

    _ip_requests[ip].append(now)
    return True


def _get_client_ip(request: Request) -> str:
    """Берём реальный IP с учётом nginx X-Forwarded-For."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Session-level rate limiting ───────────────────────────────────────────

_session_messages: dict[str, list[float]] = defaultdict(list)

SESSION_RATE_LIMIT = 30      # максимум сообщений в одной сессии
SESSION_RATE_WINDOW = 3600   # за 1 час


def _check_session_rate_limit(session_id: str) -> bool:
    """Проверка лимита сообщений для одной сессии."""
    now = time.time()
    window_start = now - SESSION_RATE_WINDOW

    _session_messages[session_id] = [t for t in _session_messages[session_id] if t > window_start]

    if len(_session_messages[session_id]) >= SESSION_RATE_LIMIT:
        logger.warning("Session rate limit exceeded: session_id=%s count=%d", 
                      session_id, len(_session_messages[session_id]))
        return False

    _session_messages[session_id].append(now)
    return True


# ── Вспомогательные функции ───────────────────────────────────────────────

def _build_result_preview(draft, topic: str) -> str:
    """Формирует preview итогового результата для отображения на сайте."""
    if draft.phase != "completed" or not draft.final_summary:
        return ""

    return (
        f"📊 Итог прохождения обучения\n\n"
        f"Сотрудник: {draft.employee_name or 'Не указано'}\n"
        f"Тема: {topic}\n"
        f"Вопросов: {draft.total_questions}\n"
        f"Правильных ответов: {draft.correct_answers}\n"
        f"Результат: {draft.score_percent()}%\n\n"
        f"Итог: {draft.final_summary}\n\n"
        f"⚠️ В рабочем режиме такой результат сохраняется в системе обучения."
    )


async def _process_chat(request: ChatRequest, settings) -> ChatResponse:
    """Общая логика обработки сообщения."""
    if not session_repository or not training_service or not ai_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        # Проверка session rate limit
        if not _check_session_rate_limit(request.session_id):
            return ChatResponse(
                reply="Вы отправили слишком много сообщений. Пожалуйста, подождите.",
                done=False,
            )

        # Получаем или создаём сессию
        draft = session_repository.get_or_create(
            session_id=request.session_id,
            total_questions=settings.quiz_question_count,
        )

        is_new_dialogue = draft.phase == "collecting_name" and draft.employee_name is None

        # Обработка фазы сбора имени
        if draft.phase == "collecting_name":
            try:
                draft = training_service.register_employee_name(draft, request.message)
                session_repository.update(request.session_id, draft)
                
                reply = (
                    f"Отлично, {draft.employee_name}! "
                    f"Сегодня мы разберём тему: {settings.training_topic}.\n\n"
                    "Готовы начать обучение?"
                )
                
                return ChatResponse(reply=reply, done=False)
            except ValueError as e:
                return ChatResponse(reply=str(e), done=False)

        # Обработка фазы обучения и тестирования через AI
        if draft.phase in ("learning", "testing"):
            # Если в testing и есть текущий вопрос — используем quiz evaluator
            if draft.phase == "testing" and draft.current_question:
                # Находим текущий вопрос в списке
                question_index = draft.questions_answered
                if question_index < len(QUIZ_QUESTIONS):
                    quiz_q = QUIZ_QUESTIONS[question_index]
                    
                    # Оцениваем ответ через LLM-судью
                    evaluation = await ai_service.evaluate_quiz_answer(
                        question=quiz_q.text,
                        expected_answer=quiz_q.expected_answer,
                        user_answer=request.message,
                    )
                    
                    # Применяем оценку
                    draft, reply = training_service.apply_quiz_evaluation(draft, evaluation)
                    session_repository.update(request.session_id, draft)
                    
                    # Если завершено — формируем preview
                    if draft.phase == "completed":
                        collected = CollectedData(
                            employee_name=draft.employee_name,
                            topic=settings.training_topic,
                            questions_total=draft.total_questions,
                            correct_answers=draft.correct_answers,
                            score_percent=draft.score_percent(),
                            final_summary=draft.final_summary,
                        )
                        preview = _build_result_preview(draft, settings.training_topic)
                        
                        return ChatResponse(
                            reply=reply,
                            done=True,
                            collected_data=collected,
                            result_preview=preview,
                            submitted_to_db=False,  # demo mode не пишет в БД
                        )
                    
                    return ChatResponse(reply=reply, done=False)
            
            # Иначе используем AI для управления обучением
            ai_turn = await ai_service.generate_turn(
                draft=draft,
                user_message=request.message,
                is_new_dialogue=is_new_dialogue,
            )
            
            draft = training_service.apply_ai_turn(draft, ai_turn)
            session_repository.update(request.session_id, draft)
            
            # Если завершено — формируем preview
            if draft.phase == "completed":
                collected = CollectedData(
                    employee_name=draft.employee_name,
                    topic=settings.training_topic,
                    questions_total=draft.total_questions,
                    correct_answers=draft.correct_answers,
                    score_percent=draft.score_percent(),
                    final_summary=draft.final_summary,
                )
                preview = _build_result_preview(draft, settings.training_topic)
                
                return ChatResponse(
                    reply=ai_turn.reply,
                    done=True,
                    collected_data=collected,
                    result_preview=preview,
                    submitted_to_db=False,  # demo mode не пишет в БД
                )
            
            return ChatResponse(reply=ai_turn.reply, done=False)

        # Фаза completed — сессия завершена
        if draft.phase == "completed":
            return ChatResponse(
                reply="Обучение завершено. Нажмите «Начать заново» для нового прохождения.",
                done=True,
            )

        # Неизвестная фаза
        return ChatResponse(
            reply="Произошла ошибка. Пожалуйста, начните заново.",
            done=False,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to process web chat message")
        raise HTTPException(
            status_code=500,
            detail="Не удалось обработать сообщение. Попробуйте позже.",
        )


# ── API Endpoints ──────────────────────────────────────────────────────────

@app.get("/api/onboarding-coach/health")
async def health_check():
    """Health check для портфолио-виджета"""
    return {"status": "ok", "service": "onboarding-coach-web-api"}


@app.post("/api/onboarding-coach/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    """
    Chat endpoint для портфолио-виджета.
    Вызывается через nginx-прокси с портфолио-сайта.
    """
    settings = get_settings()
    
    # IP rate limit
    ip = _get_client_ip(request)
    if not _check_ip_rate_limit(ip):
        raise HTTPException(
            status_code=429,
            detail="Слишком много запросов. Попробуйте позже.",
        )
    
    return await _process_chat(body, settings)


@app.delete("/api/onboarding-coach/session/{session_id}", status_code=204)
async def reset_session(session_id: str):
    """
    Сброс web-сессии — пользователь нажал «Начать заново».
    Удаляет сессию из репозитория, следующее сообщение создаст новую.
    """
    if not session_repository:
        raise HTTPException(status_code=503, detail="Service not initialized")

    session_repository.delete(session_id)
    # Очищаем также rate limit для этой сессии
    _session_messages.pop(session_id, None)
    return  # 204 No Content


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
