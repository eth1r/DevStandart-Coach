"""Скрипт для тестирования web API локально."""

import asyncio
import httpx


BASE_URL = "http://localhost:8000"
SESSION_ID = "test_session_local_123"


async def test_health():
    """Тест health check"""
    print("\n=== Testing Health Check ===")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/onboarding-coach/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    print("✅ Health check passed")


async def test_chat_flow():
    """Тест полного сценария обучения"""
    print("\n=== Testing Full Chat Flow ===")
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        # 1. Первое сообщение - бот просит имя
        print("\n1. Отправляем первое сообщение...")
        response = await client.post(
            f"{BASE_URL}/api/onboarding-coach/chat",
            json={
                "session_id": SESSION_ID,
                "message": "Хочу пройти обучение"
            }
        )
        print(f"Status: {response.status_code}")
        data = response.json()
        print(f"Reply: {data['reply']}")
        print(f"Done: {data['done']}")
        assert response.status_code == 200
        assert not data['done']
        
        # 2. Отправляем имя
        print("\n2. Отправляем имя...")
        response = await client.post(
            f"{BASE_URL}/api/onboarding-coach/chat",
            json={
                "session_id": SESSION_ID,
                "message": "Андрей"
            }
        )
        data = response.json()
        print(f"Reply: {data['reply'][:200]}...")
        print(f"Done: {data['done']}")
        assert response.status_code == 200
        assert not data['done']
        
        # 3. Начинаем обучение
        print("\n3. Начинаем обучение...")
        response = await client.post(
            f"{BASE_URL}/api/onboarding-coach/chat",
            json={
                "session_id": SESSION_ID,
                "message": "Да, готов начать"
            }
        )
        data = response.json()
        print(f"Reply: {data['reply'][:200]}...")
        print(f"Done: {data['done']}")
        assert response.status_code == 200
        
        # 4. Задаём вопрос по материалу
        print("\n4. Задаём вопрос...")
        response = await client.post(
            f"{BASE_URL}/api/onboarding-coach/chat",
            json={
                "session_id": SESSION_ID,
                "message": "Когда нужно эскалировать блокер?"
            }
        )
        data = response.json()
        print(f"Reply: {data['reply'][:200]}...")
        print(f"Done: {data['done']}")
        assert response.status_code == 200
        
        # 5. Переходим к тесту
        print("\n5. Переходим к тесту...")
        response = await client.post(
            f"{BASE_URL}/api/onboarding-coach/chat",
            json={
                "session_id": SESSION_ID,
                "message": "Готов перейти к тесту"
            }
        )
        data = response.json()
        print(f"Reply: {data['reply'][:200]}...")
        print(f"Done: {data['done']}")
        assert response.status_code == 200
        
        # 6. Отвечаем на вопросы теста (упрощённо - даём несколько ответов)
        print("\n6. Отвечаем на вопросы теста...")
        for i in range(5):
            response = await client.post(
                f"{BASE_URL}/api/onboarding-coach/chat",
                json={
                    "session_id": SESSION_ID,
                    "message": "В трекере" if i == 0 else "Не знаю"
                }
            )
            data = response.json()
            print(f"\nВопрос {i+1}:")
            print(f"Reply: {data['reply'][:200]}...")
            print(f"Done: {data['done']}")
            
            if data['done']:
                print("\n=== Обучение завершено ===")
                print(f"Collected data: {data.get('collected_data')}")
                print(f"Result preview:\n{data.get('result_preview')}")
                print(f"Submitted to DB: {data.get('submitted_to_db')}")
                assert data['submitted_to_db'] is False  # demo mode
                break
        
    print("\n✅ Full chat flow test passed")


async def test_reset_session():
    """Тест сброса сессии"""
    print("\n=== Testing Session Reset ===")
    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"{BASE_URL}/api/onboarding-coach/session/{SESSION_ID}"
        )
        print(f"Status: {response.status_code}")
        assert response.status_code == 204
    print("✅ Session reset passed")


async def test_rate_limit():
    """Тест rate limiting"""
    print("\n=== Testing Rate Limit ===")
    print("Отправляем 35 запросов подряд...")
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        for i in range(35):
            try:
                response = await client.post(
                    f"{BASE_URL}/api/onboarding-coach/chat",
                    json={
                        "session_id": f"rate_limit_test_{i}",
                        "message": "test"
                    }
                )
                if response.status_code == 429:
                    print(f"✅ Rate limit triggered at request {i+1}")
                    return
            except Exception as e:
                print(f"Request {i+1} failed: {e}")
                continue
    
    print("⚠️ Rate limit not triggered (это нормально если лимит > 35)")


async def main():
    """Запуск всех тестов"""
    print("=" * 60)
    print("DevStandart-Coach Web API Tests")
    print("=" * 60)
    
    try:
        await test_health()
        await test_chat_flow()
        await test_reset_session()
        # await test_rate_limit()  # Закомментировано чтобы не спамить
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
