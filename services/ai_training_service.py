import json

import httpx

from config import Settings
from schemas import QuizEvaluation, TrainingAssistantTurn, TrainingSessionDraft
from services.ai_training_prompts import AI_TRAINING_RESPONSE_SCHEMA, build_training_system_prompt

QUIZ_EVALUATION_SCHEMA = {
    "name": "quiz_evaluation",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "is_correct": {"type": "boolean"},
            "feedback": {"type": "string"},
        },
        "required": ["is_correct", "feedback"],
        "additionalProperties": False,
    },
}


class AITrainingService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._training_material = settings.get_training_material()
        self._client = httpx.AsyncClient(
            base_url=settings.openai_base_url,
            proxy=settings.openai_proxy,
            timeout=httpx.Timeout(120.0, connect=30.0),
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
        )

    async def generate_turn(
        self,
        draft: TrainingSessionDraft,
        user_message: str,
        is_new_dialogue: bool,
    ) -> TrainingAssistantTurn:
        payload = {
            "model": self._settings.openai_model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": build_training_system_prompt(
                        topic=self._settings.training_topic,
                        material=self._training_material,
                        total_questions=draft.total_questions,
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_prompt(
                        draft=draft,
                        user_message=user_message,
                        is_new_dialogue=is_new_dialogue,
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": AI_TRAINING_RESPONSE_SCHEMA,
            },
        }

        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return TrainingAssistantTurn.model_validate(json.loads(content))

    async def evaluate_quiz_answer(
        self,
        question: str,
        expected_answer: str,
        user_answer: str,
    ) -> QuizEvaluation:
        """LLM-судья: оценить ответ сотрудника на конкретный вопрос теста.

        Модель НЕ управляет тестом, не задаёт вопросы и не меняет счётчики —
        только возвращает {is_correct, feedback}.
        """
        payload = {
            "model": self._settings.openai_model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ты — судья теста. Оцени ответ сотрудника на вопрос теста и верни JSON.\n\n"
                        "Правила оценки:\n"
                        "1. ГЛАВНОЕ — СМЫСЛ, НЕ ФОРМА:\n"
                        "   - оценивай смысл ответа, а не грамотность, стиль или формулировку;\n"
                        "   - допускай разговорные, неполные, неидеальные фразы;\n"
                        "   - допускай опечатки, грамматические ошибки, неправильный порядок слов;\n"
                        "   - принимай синонимы и перефразировки, если смысл совпадает с expected_answer.\n\n"
                        "2. ОТРИЦАТЕЛЬНЫЕ ОТВЕТЫ:\n"
                        "   - если вопрос требует ответа «нет/нельзя/не должен», то ЛЮБАЯ явно отрицательная по смыслу формулировка считается правильной;\n"
                        "   - примеры верных отрицаний: «нет», «нельзя», «не можно», «не надо», «не стоит», «запрещено», «недопустимо» и т.п.;\n"
                        "   - даже если формулировка неграмотная — если смысл отрицательный и соответствует вопросу, ответ верен.\n\n"
                        "3. СООТВЕТСТВИЕ ВОПРОСУ:\n"
                        "   - сравнивай ответ только с текущим вопросом и ожидаемым смыслом;\n"
                        "   - если ответ относится к другому правилу или другому вопросу — is_correct = false;\n"
                        "   - если ответ абсурдный, не по теме или пустой — is_correct = false.\n\n"
                        "4. ФОРМАТ ОБРАТНОЙ СВЯЗИ:\n"
                        "   - feedback: если верно — «Верно.»; если неверно — одно предложение с правильным смыслом;\n"
                        "   - не проси повторить, не задавай следующий вопрос, не давай лишних комментариев."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Вопрос: {question}\n"
                        f"Ожидаемый смысл правильного ответа: {expected_answer}\n"
                        f"Ответ сотрудника: {user_answer}"
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": QUIZ_EVALUATION_SCHEMA,
            },
        }
        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return QuizEvaluation.model_validate(json.loads(content))

    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _build_prompt(
        draft: TrainingSessionDraft,
        user_message: str,
        is_new_dialogue: bool,
    ) -> str:
        serialized_draft = json.dumps(draft.model_dump(), ensure_ascii=False, indent=2)

        # Детектируем последний вопрос: после его оценки questions_answered + 1 == total_questions
        is_last_question = (
            draft.phase == "testing"
            and draft.current_question is not None
            and (draft.questions_answered + 1) >= draft.total_questions
        )
        # Если последний вопрос был оценён, но модель всё ещё в testing без нового вопроса
        is_overdue_completion = (
            draft.phase == "testing"
            and draft.current_question is None
            and draft.questions_answered >= draft.total_questions
        )

        if is_last_question:
            completion_note = (
                f"- ЭТО ПОСЛЕДНИЙ ВОПРОС ТЕСТА ({draft.questions_answered + 1} из {draft.total_questions}): "
                "оцени ответ (latest_answer_evaluated = true), затем ОБЯЗАТЕЛЬНО "
                'установи phase = "completed", заполни final_summary, next_question = null.'
            )
        elif is_overdue_completion:
            completion_note = (
                f"- ВСЕ {draft.total_questions} ВОПРОСОВ УЖЕ ОЦЕНЕНЫ: "
                'НЕМЕДЛЕННО phase = "completed", заполни final_summary, next_question = null.'
            )
        else:
            completion_note = (
                "- после оценки последнего ответа (questions_answered + 1 == total_questions) "
                'установи phase = "completed" и заполни final_summary.'
            )

        # Мандат оценки: пользователь дал ответ на вопрос теста — оценка обязательна
        must_evaluate = (
            draft.phase == "testing"
            and draft.current_question is not None
            and not is_new_dialogue
        )
        evaluate_note = (
            "- ПОЛЬЗОВАТЕЛЬ ОТВЕТИЛ НА ВОПРОС ТЕСТА: latest_answer_evaluated = true ОБЯЗАТЕЛЬНО; "
            "answer_is_correct = true/false; НЕ ПРОСИ повторить ответ.\n"
            if must_evaluate else ""
        )

        return (
            f"Новая сессия: {str(is_new_dialogue).lower()}\n"
            f"Текущее состояние сессии:\n{serialized_draft}\n\n"
            f"Последнее сообщение сотрудника:\n{user_message}\n\n"
            "Важно:\n"
            "- если phase сейчас learning, сначала обучай и только потом переходи в testing;\n"
            "- если phase сейчас testing и current_question заполнен, оцени ТОЛЬКО ответ на current_question;\n"
            "- ответ верен исключительно если он соответствует current_question; ответ на другое правило материала = неверный;\n"
            "- questions_answered содержит число уже оценённых ответов;\n"
            f"{evaluate_note}"
            f"{completion_note}"
        )
