from fastapi.testclient import TestClient

from app.main import app, get_chat_service


class FakeChatService:
    def reply(self, message, history, era="1998"):
        return f"1998 bağlantısından: {message}"


class BusyChatService:
    def reply(self, message, history, era="1998"):
        error = RuntimeError("Model yoğunluğu")
        error.code = 503
        raise error


class EraAwareChatService:
    def reply(self, message, history, era):
        return f"{era} bağlantısından: {message}"


def test_health_endpoint_reports_ready():
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_endpoint_returns_the_service_reply():
    app.dependency_overrides[get_chat_service] = lambda: FakeChatService()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/chat",
                json={"message": "İnternet nedir?", "history": []},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "reply": "1998 bağlantısından: İnternet nedir?"
    }


def test_chat_endpoint_rejects_a_blank_message():
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "   "})

    assert response.status_code == 422


def test_homepage_is_served():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "RetroChat 98" in response.text


def test_chat_endpoint_explains_temporary_model_capacity_errors():
    app.dependency_overrides[get_chat_service] = lambda: BusyChatService()

    try:
        with TestClient(app) as client:
            response = client.post("/api/chat", json={"message": "Merhaba"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Gemini hatları şu an meşgul. Birkaç saniye sonra tekrar dene."
    }


def test_chat_endpoint_forwards_the_selected_era():
    app.dependency_overrides[get_chat_service] = lambda: EraAwareChatService()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/chat",
                json={"message": "Hangi yıldayız?", "era": "2030"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"reply": "2030 bağlantısından: Hangi yıldayız?"}


def test_chat_endpoint_rejects_an_unknown_era():
    app.dependency_overrides[get_chat_service] = lambda: FakeChatService()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/chat",
                json={"message": "Hangi yıldayız?", "era": "2050"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
