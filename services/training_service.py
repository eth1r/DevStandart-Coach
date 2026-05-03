from database.models import TrainingResult
from database.repository import TrainingResultRepository
from schemas import QuizEvaluation, TrainingAssistantTurn, TrainingResultCreate, TrainingSessionDraft
from services.quiz import QUIZ_QUESTIONS

TOTAL_LEARNING_STEPS = 5  # количество ключевых правил в учебном материале


class TrainingService:
    @staticmethod
    def validate_employee_name(value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if len(cleaned) < 2:
            raise ValueError("Укажите имя сотрудника хотя бы из двух символов.")
        return cleaned

    def start_session(self, total_questions: int) -> TrainingSessionDraft:
        return TrainingSessionDraft(total_questions=total_questions)

    def register_employee_name(self, draft: TrainingSessionDraft, employee_name: str) -> TrainingSessionDraft:
        updated = TrainingSessionDraft.model_validate(draft.model_dump())
        updated.employee_name = self.validate_employee_name(employee_name)
        updated.phase = "learning"
        return updated

    def apply_ai_turn(
        self,
        current: TrainingSessionDraft,
        ai_turn: TrainingAssistantTurn,
    ) -> TrainingSessionDraft:
        updated = TrainingSessionDraft.model_validate(current.model_dump())
        updated.phase = ai_turn.phase

        if ai_turn.phase == "learning" and updated.learning_step < TOTAL_LEARNING_STEPS:
            updated.learning_step += 1

        if ai_turn.latest_answer_evaluated and current.phase == "testing" and current.current_question:
            updated.questions_answered += 1
            if ai_turn.answer_is_correct:
                updated.correct_answers += 1
        elif (
            current.phase == "testing"
            and current.current_question is not None
            and not ai_turn.latest_answer_evaluated
            and ai_turn.phase != "completed"
        ):
            # Safety-net: модель не оценила ответ при активном вопросе;
            # принудительно засчитываем как неверный ответ и движемся дальше
            updated.questions_answered = current.questions_answered + 1
            # correct_answers не изменяем (ответ считается неверным)

        if ai_turn.answer_feedback is not None:
            updated.last_answer_feedback = ai_turn.answer_feedback

        updated.current_question = ai_turn.next_question

        if ai_turn.final_summary is not None:
            updated.final_summary = ai_turn.final_summary

        updated.last_bot_reply = ai_turn.reply

        return updated

    def apply_quiz_evaluation(
        self,
        draft: TrainingSessionDraft,
        evaluation: QuizEvaluation,
    ) -> tuple[TrainingSessionDraft, str]:
        """Apply a pre-computed quiz evaluation to the draft state.

        Оценка (верно/неверно) уже вычислена вне этого метода —
        здесь только обновление счётчиков и переход к следующему вопросу или завершению.
        Returns (updated_draft, reply_text).
        """
        updated = TrainingSessionDraft.model_validate(draft.model_dump())
        updated.questions_answered = draft.questions_answered + 1
        if evaluation.is_correct:
            updated.correct_answers = draft.correct_answers + 1

        prefix = "✅" if evaluation.is_correct else "❌"
        feedback_line = f"{prefix} {evaluation.feedback}"

        next_index = updated.questions_answered
        is_last = next_index >= updated.total_questions or next_index >= len(QUIZ_QUESTIONS)

        if is_last:
            updated.phase = "completed"
            updated.current_question = None
            updated.final_summary = self._build_final_summary(updated)
            reply = f"{feedback_line}\n\n{updated.final_summary}"
        else:
            next_q = QUIZ_QUESTIONS[next_index]
            updated.current_question = next_q.text
            reply = (
                f"{feedback_line}\n\n"
                f"Вопрос {next_index + 1} из {updated.total_questions}:\n{next_q.text}"
            )

        return updated, reply

    @staticmethod
    def _build_final_summary(draft: TrainingSessionDraft) -> str:
        score = draft.score_percent()
        correct = draft.correct_answers
        total = draft.total_questions
        if score == 100:
            return f"Отлично! Все {total} правил усвоены."
        if score >= 80:
            return f"Хорошо! {correct} из {total} ответов верны. Повторите пропущенные правила."
        if score >= 60:
            return f"Удовлетворительно. {correct} из {total}. Рекомендуется повторить материал."
        return f"Результат: {correct} из {total}. Необходимо повторить стандарты качества разработки."

    async def create_result(
        self,
        repository: TrainingResultRepository,
        draft: TrainingSessionDraft,
        topic: str,
        telegram_user_id: int,
        telegram_chat_id: int,
    ) -> TrainingResult:
        result_in = TrainingResultCreate(
            employee_name=draft.employee_name or "Неизвестный сотрудник",
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            topic=topic,
            total_questions=draft.total_questions,
            correct_answers=draft.correct_answers,
            score_percent=draft.score_percent(),
            final_summary=draft.final_summary,
        )
        return await repository.create(result_in)
