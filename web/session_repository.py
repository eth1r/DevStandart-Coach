"""In-memory session repository for web demo mode."""

from schemas import TrainingSessionDraft


class WebSessionRepository:
    """Хранилище web-сессий для demo mode.
    
    Web-сессии живут отдельно от Telegram-сессий и не пишутся в БД по умолчанию.
    """

    def __init__(self) -> None:
        self._web_sessions: dict[str, TrainingSessionDraft] = {}

    def get_or_create(
        self,
        session_id: str,
        total_questions: int,
    ) -> TrainingSessionDraft:
        """Получить или создать web-сессию."""
        session = self._web_sessions.get(session_id)
        if session is None:
            session = TrainingSessionDraft(total_questions=total_questions)
            self._web_sessions[session_id] = session
        return session

    def update(self, session_id: str, draft: TrainingSessionDraft) -> None:
        """Обновить состояние сессии."""
        self._web_sessions[session_id] = draft

    def delete(self, session_id: str) -> None:
        """Удалить web-сессию (reset)."""
        self._web_sessions.pop(session_id, None)

    def exists(self, session_id: str) -> bool:
        """Проверить существование сессии."""
        return session_id in self._web_sessions
