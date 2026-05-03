# DevStandart-Coach Web API

Web API для интеграции AI-наставника по онбордингу с портфолио-сайтом.

## Архитектура

```
Пользователь на сайте
    ↓
ProjectBotDemoWidget (React)
    ↓
/api/onboarding-coach/* (nginx proxy)
    ↓
onboarding-coach-web service (FastAPI)
    ↓
Общая бизнес-логика DevStandart-Coach
```

## Endpoints

### 1. Health Check
```
GET /api/onboarding-coach/health
```

**Response:**
```json
{
  "status": "ok",
  "service": "onboarding-coach-web-api"
}
```

### 2. Chat
```
POST /api/onboarding-coach/chat
```

**Request:**
```json
{
  "session_id": "demo_onboarding-coach_1234567890_abc123",
  "message": "Хочу пройти обучение"
}
```

**Response:**
```json
{
  "reply": "Напишите ваше имя, чтобы начать обучение.",
  "done": false,
  "collected_data": null,
  "result_preview": null,
  "submitted_to_db": false
}
```

**Response (completed):**
```json
{
  "reply": "Тест завершён! Результат: 3 из 5 правильных ответов (60%).",
  "done": true,
  "collected_data": {
    "employee_name": "Андрей",
    "topic": "Регламент работы команды",
    "questions_total": 5,
    "correct_answers": 3,
    "score_percent": 60,
    "final_summary": "Удовлетворительно. 3 из 5. Рекомендуется повторить материал."
  },
  "result_preview": "📊 Итог прохождения обучения\n\nСотрудник: Андрей\nТема: Регламент работы команды\nВопросов: 5\nПравильных ответов: 3\nРезультат: 60%\n\nИтог: Удовлетворительно. 3 из 5. Рекомендуется повторить материал.\n\n⚠️ В рабочем режиме такой результат сохраняется в системе обучения.",
  "submitted_to_db": false
}
```

### 3. Reset Session
```
DELETE /api/onboarding-coach/session/{session_id}
```

**Response:** `204 No Content`

## Demo Mode

Web API работает в **demo mode** по умолчанию:

- ✅ Использует реальную бизнес-логику обучения и тестирования
- ✅ Проводит сотрудника через полный сценарий
- ✅ Оценивает ответы через LLM-судью
- ✅ Формирует итоговый результат
- ❌ **НЕ пишет результаты в production БД** (`submitted_to_db: false`)
- ❌ НЕ смешивает web-сессии с Telegram-сессиями

## Rate Limiting

### IP-level rate limit:
- **40 запросов** с одного IP за 1 час
- Защита от спама на уровне адреса

### Session-level rate limit:
- **30 сообщений** в одной сессии за 1 час
- Защита от злоупотребления одной сессией

## Локальный запуск

### 1. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 2. Настройка .env
```bash
cp .env.example .env
# Заполните OPENAI_API_KEY и другие переменные
```

### 3. Запуск web API
```bash
python web_main.py
```

API будет доступен на `http://localhost:8000`

### 4. Проверка health
```bash
curl http://localhost:8000/api/onboarding-coach/health
```

### 5. Тестовый запрос
```bash
curl -X POST http://localhost:8000/api/onboarding-coach/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test_session_123",
    "message": "Хочу пройти обучение"
  }'
```

## Docker запуск

### 1. Сборка образа
```bash
docker build -f Dockerfile.web -t onboarding-coach-web .
```

### 2. Запуск контейнера
```bash
docker run -d \
  --name onboarding-coach-web \
  -p 8001:8000 \
  --env-file .env \
  onboarding-coach-web
```

### 3. Через docker-compose
```bash
docker compose -f docker-compose.web.yml up -d
```

## Production Deploy

### 1. На сервере с портфолио-сайтом

Добавить в `docker-compose.yml` сайта:

```yaml
services:
  onboarding-coach:
    build:
      context: ../DevStandart-Coach
      dockerfile: Dockerfile.web
    container_name: onboarding-coach
    restart: unless-stopped
    env_file:
      - ../DevStandart-Coach/.env
    networks:
      - app-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/onboarding-coach/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### 2. Nginx proxy

Добавить в nginx конфигурацию сайта:

```nginx
location /api/onboarding-coach/ {
    proxy_pass http://onboarding-coach:8000/api/onboarding-coach/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # Таймауты для LLM-запросов
    proxy_connect_timeout 60s;
    proxy_send_timeout 120s;
    proxy_read_timeout 120s;
}
```

### 3. Переменные окружения

Создать `.env` на сервере:

```env
BOT_TOKEN=not_needed_for_web_api
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/onboarding
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini
TRAINING_TOPIC=Регламент работы команды
TRAINING_MATERIAL=Команда использует асинхронную коммуникацию...
QUIZ_QUESTION_COUNT=5
LOG_LEVEL=INFO
WEB_DEMO_WRITE_TO_DB=false
```

### 4. Деплой

```bash
cd /opt/apps/ai_portfolio
docker compose up -d --build onboarding-coach
```

### 5. Проверка

```bash
# Health check
curl https://portfolio.aiworker43.ru/api/onboarding-coach/health

# Test chat
curl -X POST https://portfolio.aiworker43.ru/api/onboarding-coach/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test_123",
    "message": "Хочу пройти обучение"
  }'
```

## Telegram Bot + Web API

Можно запускать оба режима одновременно:

### Вариант 1: Разные контейнеры
```yaml
services:
  # Telegram bot
  onboarding-coach-bot:
    build:
      context: .
      dockerfile: Dockerfile
    command: ["python", "main.py"]
    
  # Web API
  onboarding-coach-web:
    build:
      context: .
      dockerfile: Dockerfile.web
    command: ["python", "web_main.py"]
```

### Вариант 2: Один контейнер с supervisor
Использовать supervisor для запуска обоих процессов в одном контейнере.

## Безопасность

### ✅ Реализовано:
- IP rate limiting (40 req/hour)
- Session rate limiting (30 msg/hour)
- CORS ограничение на домены
- Валидация длины сообщений (max 2000 символов)
- Валидация session_id (max 100 символов)
- Demo mode не пишет в БД

### ⚠️ Рекомендации:
- Использовать HTTPS (nginx с SSL)
- Настроить firewall на сервере
- Мониторить логи на подозрительную активность
- Регулярно обновлять зависимости

## Troubleshooting

### Проблема: 503 Service Unavailable
**Причина:** Сервис не инициализирован или упал  
**Решение:** Проверить логи контейнера

```bash
docker logs onboarding-coach
```

### Проблема: 429 Too Many Requests
**Причина:** Превышен rate limit  
**Решение:** Подождать 1 час или увеличить лимиты в коде

### Проблема: 500 Internal Server Error
**Причина:** Ошибка в обработке сообщения  
**Решение:** Проверить логи, проверить OPENAI_API_KEY

### Проблема: CORS error
**Причина:** Запрос с неразрешённого домена  
**Решение:** Добавить домен в `allowed_origins` в `web/api.py`

## Мониторинг

### Health check
```bash
watch -n 5 'curl -s http://localhost:8000/api/onboarding-coach/health | jq'
```

### Логи
```bash
docker logs -f onboarding-coach
```

### Метрики
Можно добавить Prometheus metrics через `prometheus-fastapi-instrumentator`

## Дальнейшее развитие

### Возможные улучшения:
- [ ] Добавить Prometheus metrics
- [ ] Добавить Sentry для error tracking
- [ ] Добавить Redis для session storage (вместо in-memory)
- [ ] Добавить admin panel для просмотра demo-сессий
- [ ] Добавить A/B тестирование разных промптов
- [ ] Добавить экспорт результатов в CSV
- [ ] Добавить webhook для уведомлений о завершении обучения

## Лицензия

MIT
