import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards import cancel_keyboard, learning_keyboard, remove_keyboard
from config import Settings
from database import TrainingResultRepository
from schemas import QuizEvaluation, TrainingSessionDraft
from services import AITrainingService, TrainingService
from services.quiz import QUIZ_QUESTIONS, check_answer

logger = logging.getLogger(__name__)
router = Router()


class TrainingStates(StatesGroup):
    active = State()


@router.message(Command("start"))
async def handle_start(message: Message, state: FSMContext, settings: Settings, training_service: TrainingService) -> None:
    await state.clear()
    await state.set_state(TrainingStates.active)
    await state.update_data(
        draft=training_service.start_session(settings.quiz_question_count).model_dump(),
        result_id=None,
        name_collected=False,
    )
    await message.answer(
        "Здравствуйте! Я помогу изучить новый материал, а затем проведу тестирование.\n\n"
        "Напишите имя сотрудника, которого нужно обучить.",
        reply_markup=cancel_keyboard(),
    )


@router.message(Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Сейчас нет активной сессии обучения.", reply_markup=remove_keyboard())
        return

    await state.clear()
    await message.answer(
        "Сессия обучения отменена. Чтобы начать заново, отправьте /start.",
        reply_markup=remove_keyboard(),
    )


@router.message(TrainingStates.active, F.text)
async def process_ai_training(
    message: Message,
    state: FSMContext,
    settings: Settings,
    training_service: TrainingService,
    ai_training_service: AITrainingService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    state_data = await state.get_data()
    draft = TrainingSessionDraft.model_validate(state_data.get("draft", {}))
    name_collected = bool(state_data.get("name_collected"))
    user_text = message.text or ""

    try:
        # ── 1. Сбор имени ────────────────────────────────────────────────────────────────
        if not name_collected:
            updated_draft = training_service.register_employee_name(draft=draft, employee_name=user_text)
            await state.update_data(draft=updated_draft.model_dump(), name_collected=True)
            ai_turn = await ai_training_service.generate_turn(
                draft=updated_draft,
                user_message="Сотрудник готов начать обучение.",
                is_new_dialogue=True,
            )
            updated_draft = training_service.apply_ai_turn(updated_draft, ai_turn)
            await state.update_data(draft=updated_draft.model_dump())
            await message.answer(ai_turn.reply, reply_markup=learning_keyboard())
            return

        # ── 2. Тестирование (поток управляется кодом, оценка — LLM-судья с keyword-fallback) ──
        if draft.phase == "testing":
            question_index = draft.questions_answered
            current_q = QUIZ_QUESTIONS[question_index] if question_index < len(QUIZ_QUESTIONS) else None

            if current_q is not None:
                try:
                    evaluation = await ai_training_service.evaluate_quiz_answer(
                        question=current_q.text,
                        expected_answer=current_q.expected_answer,
                        user_answer=user_text,
                    )
                except Exception:
                    logger.warning("LLM quiz evaluation failed, switching to keyword fallback")
                    is_correct = check_answer(user_text, current_q)
                    evaluation = QuizEvaluation(
                        is_correct=is_correct,
                        feedback="Верно." if is_correct else current_q.wrong_answer_hint,
                    )
            else:
                # Индекс вышел за границы: завершаем тест
                evaluation = QuizEvaluation(is_correct=False, feedback="")

            updated_draft, reply = training_service.apply_quiz_evaluation(draft, evaluation)
            await state.update_data(draft=updated_draft.model_dump())

            if updated_draft.phase == "completed":
                async with session_factory() as session:
                    repository = TrainingResultRepository(session)
                    await training_service.create_result(
                        repository=repository,
                        draft=updated_draft,
                        topic=settings.training_topic,
                        telegram_user_id=message.from_user.id if message.from_user else 0,
                        telegram_chat_id=message.chat.id,
                    )
                await state.clear()
                await message.answer(
                    f"{reply}\n\n"
                    f"Результат сохранён в Postgres.\n"
                    f"Итог: {updated_draft.correct_answers}/{updated_draft.total_questions} "
                    f"({updated_draft.score_percent()}%).",
                    reply_markup=remove_keyboard(),
                )
            else:
                await message.answer(reply, reply_markup=cancel_keyboard())
            return

        # ── 3. Обучение (LLM) ─────────────────────────────────────────────────────
        ai_turn = await ai_training_service.generate_turn(
            draft=draft,
            user_message=user_text,
            is_new_dialogue=False,
        )
        updated_draft = training_service.apply_ai_turn(draft, ai_turn)

        # Переход к тестированию: заменяем вопрос LLM на первый фиксированный вопрос
        if updated_draft.phase == "testing" and draft.phase != "testing":
            first_q = QUIZ_QUESTIONS[0]
            updated_draft.current_question = first_q.text

        await state.update_data(draft=updated_draft.model_dump())

        if updated_draft.phase == "testing":
            # Первое сообщение теста
            await message.answer(
                f"{ai_turn.reply}\n\n"
                f"Вопрос 1 из {updated_draft.total_questions}:\n{updated_draft.current_question}",
                reply_markup=cancel_keyboard(),
            )
        else:
            markup = learning_keyboard() if ai_turn.phase == "learning" else cancel_keyboard()
            await message.answer(ai_turn.reply, reply_markup=markup)
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=cancel_keyboard())
    except Exception:
        logger.exception("Failed to process AI training")
        await message.answer(
            "Не удалось обработать сообщение. Попробуйте еще раз или отправьте /cancel.",
            reply_markup=cancel_keyboard(),
        )


@router.message(TrainingStates.active)
async def handle_invalid_collecting_input(message: Message) -> None:
    await message.answer("Пожалуйста, отправьте ответ текстом.", reply_markup=cancel_keyboard())


@router.message(F.text)
async def handle_text_without_flow(message: Message) -> None:
    await message.answer("Чтобы начать обучение и тестирование, отправьте /start.")


@router.message()
async def handle_unsupported_input(message: Message) -> None:
    await message.answer("Пожалуйста, используйте текстовые сообщения или команду /start.")
