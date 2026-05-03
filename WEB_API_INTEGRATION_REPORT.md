# Отчёт: Web API интеграция DevStandart-Coach

**Дата:** 4 мая 2026  
**Статус:** ✅ ГОТОВО К ТЕСТИРОВАНИЮ

---

## 1. СТАТУС

**ГОТОВО ЧАСТИЧНО** — backend готов к локальному тестированию и деплою.

### Что сделано:
✅ Web API endpoints реализованы  
✅ Demo mode безопасный (не пишет в БД)  
✅ Rate limiting добавлен  
✅ Session management реализован  
✅ Docker конфигурация готова  
✅ Документация написана  

### Что осталось:
⏳ Локальное тестирование  
⏳ Production deploy на сервер  
⏳ Проверка интеграции с фронтендом  

---

## 2. КАКИЕ ФАЙЛЫ ИЗМЕНЕНЫ/ДОБАВЛЕНЫ

### Новые файлы:

1. **`web/__init__.py`**
   - Инициализация web модуля

2. **`web/session_repository.py`**
   - In-memory хранилище web-сессий
   - Отдельное от Telegram-сессий
   - Методы: `get_or_create`, `update`, `delete`, `exists`

3. **`web/api.py`** (основной файл)
   - FastAPI приложение
   - 3 endpoint'а: health, chat, reset
   - IP rate limiting (40 req/hour)
   - Session rate limiting (30 msg/hour)
   - CORS настройка
   - Demo mode логика

4. **`web_main.py`**
   - Entrypoint для запуска web API
   - Uvicorn конфигурация

5. **`Dockerfile.web`**
   - Docker образ для web API
   - Expose port 8000

6. **`docker-compose.web.yml`**
   - Compose конфигурация для web API
   - Healthcheck настроен

7. **`WEB_API_README.md`**
   - Полная документация web API
   - Примеры запросов/ответов
   - Инструкции по деплою
   - Troubleshooting

8. **`test_web_api.py`**
   - Тестовый скрипт для локальной проверки
   - Тесты: health, chat flow, reset, rate limit

9. **`WEB_API_INTEGRATION_REPORT.md`** (этот файл)
   - Отчёт о проделанной работе

### Изменённые файлы:

1. **`requirements.txt`**
   - Добавлено: `fastapi>=0.115.0`
   - Добавлено: `uvicorn[standard]>=0.32.0`

2. **`.env.example`**
   - Добавлено: `WEB_DEMO_WRITE_TO_DB=false`
   - Добавлено: `WEB_API_PORT=8000`

3. **`README.md`**
   - Добавлена секция "Режимы работы"
   - Ссылка на WEB_API_README.md

---

## 3. КАКИЕ ENDPOINT'Ы ДОБАВЛЕНЫ

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

**Response (в процессе):**
```json
{
  "reply": "Напишите ваше имя, чтобы начать обучение.",
  "done": false,
  "collected_data": null,
  "result_preview": null,
  "submitted_to_db": false
}
```

**Response (завершено):**
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

---

## 4. КАК РЕАЛИЗОВАН DEMO MODE

### Где блокируется запись в БД:

1. **В `web/api.py`:**
   - Все response содержат `submitted_to_db: false`
   - Метод `create_result` из `TrainingService` НЕ вызывается
   - Web-сессии живут только в памяти (`WebSessionRepository`)

2. **Отделение web-сессий:**
   - `WebSessionRepository` — отдельное хранилище
   - Не использует БД вообще
   - Сессии хранятся в `dict[str, TrainingSessionDraft]`
   - При reset сессия удаляется из памяти

3. **Env-флаг:**
   - `WEB_DEMO_WRITE_TO_DB=false` (по умолчанию)
   - Пока не используется в коде, но зарезервирован
   - Можно добавить проверку если понадобится включить запись

### Как отделены web-сессии:

```python
# Telegram сессии (в bot/handlers)
session = telegram_session_repository.get_or_create(user_id, chat_id, ...)
# → Пишутся в БД через TrainingResultRepository

# Web сессии (в web/api.py)
draft = web_session_repository.get_or_create(session_id, total_questions)
# → Живут только в памяти, НЕ пишутся в БД
```

---

## 5. КАКОЙ RESPONSE ВОЗВРАЩАЕТ CHAT ENDPOINT

### Пример 1: Начало сессии
```json
{
  "reply": "Напишите ваше имя, чтобы начать обучение.",
  "done": false,
  "collected_data": null,
  "result_preview": null,
  "submitted_to_db": false
}
```

### Пример 2: Обучение
```json
{
  "reply": "Отлично, Андрей! Сегодня мы разберём тему: Регламент работы команды.\n\nГотовы начать обучение?",
  "done": false,
  "collected_data": null,
  "result_preview": null,
  "submitted_to_db": false
}
```

### Пример 3: Тестирование
```json
{
  "reply": "✅ Верно.\n\nВопрос 2 из 5:\nКогда нужно эскалировать блокеры?",
  "done": false,
  "collected_data": null,
  "result_preview": null,
  "submitted_to_db": false
}
```

### Пример 4: Завершение (done=true)
```json
{
  "reply": "❌ Неверно. Блокеры нужно эскалировать в течение 30 минут.\n\nТест завершён! Результат: 3 из 5 правильных ответов (60%).\n\nУдовлетворительно. 3 из 5. Рекомендуется повторить материал.",
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

---

## 6. КАК ПОДГОТОВЛЕН DEPLOY

### Docker:

1. **Dockerfile.web**
   - Python 3.11-slim
   - Устанавливает зависимости
   - Expose port 8000
   - CMD: `python web_main.py`

2. **docker-compose.web.yml**
   - Сервис: `onboarding-coach-web`
   - Port mapping: `8001:8000`
   - Healthcheck настроен
   - Network: `app-network` (external)

### Compose для портфолио-сайта:

Добавить в `fresh-portfolio/docker-compose.yml`:

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

### Nginx/Proxy:

Добавить в nginx конфигурацию:

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

---

## 7. ЧТО ОСТАЛОСЬ СДЕЛАТЬ ДЛЯ PROD

### Локальное тестирование:

1. **Установить зависимости:**
   ```bash
   cd DevStandart-Coach
   pip install -r requirements.txt
   ```

2. **Создать .env:**
   ```bash
   cp .env.example .env
   # Заполнить OPENAI_API_KEY
   ```

3. **Запустить web API:**
   ```bash
   python web_main.py
   ```

4. **Запустить тесты:**
   ```bash
   python test_web_api.py
   ```

5. **Проверить endpoints вручную:**
   ```bash
   # Health
   curl http://localhost:8000/api/onboarding-coach/health
   
   # Chat
   curl -X POST http://localhost:8000/api/onboarding-coach/chat \
     -H "Content-Type: application/json" \
     -d '{"session_id": "test_123", "message": "Хочу пройти обучение"}'
   
   # Reset
   curl -X DELETE http://localhost:8000/api/onboarding-coach/session/test_123
   ```

### Production deploy:

1. **На сервере:**
   ```bash
   cd /opt/apps
   git clone https://github.com/eth1r/DevStandart-Coach.git
   cd DevStandart-Coach
   ```

2. **Создать .env:**
   ```bash
   cp .env.example .env
   nano .env
   # Заполнить реальные значения
   ```

3. **Добавить в docker-compose сайта:**
   ```bash
   cd /opt/apps/ai_portfolio
   nano docker-compose.yml
   # Добавить сервис onboarding-coach
   ```

4. **Обновить nginx:**
   ```bash
   nano /etc/nginx/sites-available/portfolio
   # Добавить location /api/onboarding-coach/
   nginx -t
   systemctl reload nginx
   ```

5. **Запустить:**
   ```bash
   docker compose up -d --build onboarding-coach
   ```

6. **Проверить:**
   ```bash
   curl https://portfolio.aiworker43.ru/api/onboarding-coach/health
   ```

### Проверка интеграции с фронтендом:

1. Открыть страницу кейса на сайте
2. Нажать "Попробовать демо"
3. Пройти полный сценарий обучения
4. Проверить, что итоговый результат отображается
5. Проверить, что reset работает

---

## 8. ACCEPTANCE CRITERIA

### ✅ Выполнено:

- ✅ У DevStandart-Coach есть web API
- ✅ Сайт сможет ходить в `/api/onboarding-coach/*`
- ✅ Demo mode безопасный и не пишет в боевую БД по умолчанию
- ✅ Есть reset session
- ✅ Есть итоговый preview результата
- ✅ Telegram-бот не сломан (используется отдельный Dockerfile)
- ✅ Backend готов к следующему этапу — production deploy

### ⏳ Осталось проверить:

- ⏳ Локальное тестирование работает
- ⏳ Production deploy успешен
- ⏳ Интеграция с фронтендом работает
- ⏳ Rate limiting работает корректно
- ⏳ CORS настроен правильно

---

## 9. АРХИТЕКТУРА

### Общая схема:

```
┌─────────────────────────────────────────────────────────────┐
│                    Пользователь на сайте                     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              ProjectBotDemoWidget (React)                    │
│  - Отправляет POST /api/onboarding-coach/chat               │
│  - Получает reply, done, collected_data, result_preview     │
│  - Отображает итоговый результат                            │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Nginx (portfolio site)                    │
│  location /api/onboarding-coach/ {                          │
│    proxy_pass http://onboarding-coach:8000/...;             │
│  }                                                           │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│           onboarding-coach service (FastAPI)                 │
│  - web/api.py                                               │
│  - IP rate limiting (40 req/hour)                           │
│  - Session rate limiting (30 msg/hour)                      │
│  - WebSessionRepository (in-memory)                         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│         Общая бизнес-логика DevStandart-Coach               │
│  - TrainingService                                          │
│  - AITrainingService                                        │
│  - QuizEvaluation                                           │
│  - TrainingSessionDraft                                     │
└─────────────────────────────────────────────────────────────┘
```

### Отличия web от Telegram:

| Аспект | Telegram Bot | Web API |
|--------|-------------|---------|
| Transport | aiogram | FastAPI |
| Session storage | In-memory (bot) | WebSessionRepository |
| БД запись | ✅ Да | ❌ Нет (demo mode) |
| Rate limiting | Нет | ✅ IP + Session |
| CORS | Не нужен | ✅ Настроен |
| Бизнес-логика | ✅ Общая | ✅ Общая |

---

## 10. БЕЗОПАСНОСТЬ

### Реализованные меры:

1. **IP Rate Limiting:**
   - 40 запросов с одного IP за 1 час
   - Защита от спама на уровне адреса

2. **Session Rate Limiting:**
   - 30 сообщений в одной сессии за 1 час
   - Защита от злоупотребления одной сессией

3. **CORS:**
   - Разрешены только домены портфолио
   - `localhost` для разработки

4. **Валидация:**
   - `session_id`: max 100 символов
   - `message`: max 2000 символов
   - Pydantic валидация всех полей

5. **Demo Mode:**
   - Не пишет в production БД
   - `submitted_to_db: false` всегда

6. **Таймауты:**
   - httpx timeout: 120s
   - nginx timeout: 120s

### Рекомендации:

- ✅ Использовать HTTPS (nginx с SSL)
- ✅ Настроить firewall на сервере
- ✅ Мониторить логи
- ✅ Регулярно обновлять зависимости

---

## 11. СЛЕДУЮЩИЕ ШАГИ

### 1. Локальное тестирование (сегодня):
```bash
cd DevStandart-Coach
pip install -r requirements.txt
cp .env.example .env
# Заполнить OPENAI_API_KEY
python web_main.py
# В другом терминале:
python test_web_api.py
```

### 2. Production deploy (после тестирования):
```bash
# На сервере
cd /opt/apps
git clone https://github.com/eth1r/DevStandart-Coach.git
cd DevStandart-Coach
cp .env.example .env
nano .env  # Заполнить

# Добавить в docker-compose сайта
cd /opt/apps/ai_portfolio
nano docker-compose.yml
docker compose up -d --build onboarding-coach

# Проверить
curl https://portfolio.aiworker43.ru/api/onboarding-coach/health
```

### 3. Проверка интеграции:
- Открыть https://portfolio.aiworker43.ru/cases/ai-onboarding-coach
- Нажать "Попробовать демо"
- Пройти полный сценарий
- Проверить итоговый результат

---

## 12. КОНТАКТЫ И ССЫЛКИ

- **GitHub:** https://github.com/eth1r/DevStandart-Coach
- **Портфолио:** https://portfolio.aiworker43.ru
- **Telegram:** https://t.me/eth1r

---

**Итог:** Backend готов к тестированию и деплою. Все endpoint'ы реализованы, demo mode безопасный, документация написана.
