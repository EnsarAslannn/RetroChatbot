from fastapi.testclient import TestClient
import time

from app.main import app, get_chat_service, SlidingWindowLimiter


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


class StreamingChatService:
    def stream_reply(self, message, history, era="1998"):
        yield "Merhaba "
        yield "dünya"


class SlowChatService:
    def reply(self, message, history, era="1998"):
        time.sleep(0.1)
        return "geç yanıt"


class BrokenStreamingService:
    def stream_reply(self, message, history, era="1998"):
        error = RuntimeError("Model dolu")
        error.code = 503
        raise error
        yield ""


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
    assert response.json()["detail"] == {
        "code": "upstream_busy",
        "message": "Gemini hatları şu an meşgul. Birkaç saniye sonra tekrar dene.",
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


def test_stream_endpoint_delivers_chunks_and_completion():
    app.dependency_overrides[get_chat_service] = lambda: StreamingChatService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/chat/stream", json={"message": "Merhaba"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert '"text":"Merhaba "' in response.text
    assert '"text":"dünya"' in response.text
    assert 'event: done' in response.text


def test_chat_timeout_returns_a_machine_readable_code(monkeypatch):
    monkeypatch.setenv("CHAT_TIMEOUT_SECONDS", "0.01")
    app.dependency_overrides[get_chat_service] = lambda: SlowChatService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/chat", json={"message": "Merhaba"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 504
    assert response.json()["detail"]["code"] == "upstream_timeout"


def test_public_metrics_have_counts_without_message_content():
    with TestClient(app) as client:
        response = client.get("/api/metrics")
    assert response.status_code == 200
    assert "requests" in response.json()
    assert "message" not in response.text


def test_rate_limit_is_scoped_to_each_client():
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
    assert limiter.allow("client-a")
    assert limiter.allow("client-a")
    assert not limiter.allow("client-a")
    assert limiter.allow("client-b")


def test_stream_reports_upstream_error_as_event():
    app.dependency_overrides[get_chat_service] = lambda: BrokenStreamingService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/chat/stream", json={"message": "Merhaba"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert 'event: error' in response.text
    assert '"code":"upstream_busy"' in response.text


def test_missing_api_key_uses_structured_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "Merhaba"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "not_configured"


def test_product_events_count_without_accepting_message_content():
    with TestClient(app) as client:
        before = client.get("/api/metrics").json()["retries"]
        response = client.post("/api/events", json={"event": "retry"})
        after = client.get("/api/metrics").json()["retries"]
        unsafe = client.post("/api/events", json={"event": "retry", "message": "özel soru"})
    assert response.status_code == 204
    assert after == before + 1
    assert unsafe.status_code == 422
