from fastapi.testclient import TestClient
from httpx import ConnectError
from pathlib import Path
import pytest
import time
import uuid

from app.main import app, get_chat_service, SlidingWindowLimiter, metrics


@pytest.fixture(autouse=True)
def isolated_application_database(monkeypatch):
    database = Path(f".test-app-{uuid.uuid4().hex}.db")
    monkeypatch.setenv("COMPARISON_DB_PATH", str(database))
    yield
    database.unlink(missing_ok=True)


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


class RealityCheckService:
    def verify_historical_claims(self, question, retro):
        return {
            "summary": f"Doğrulandı: {question} / {retro}",
            "sources": [{"title": "Kaynak", "url": "https://example.com/history"}],
        }


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


class DisconnectedStreamingService:
    def stream_reply(self, message, history, era="1998"):
        raise ConnectError("connection failed")
        yield ""


class RejectedKeyStreamingService:
    def stream_reply(self, message, history, era="1998"):
        error = RuntimeError("Gemini rejected the credential")
        error.code = 400
        error.message = "API key not valid. Please pass a valid API key."
        raise error
        yield ""


class RestrictedKeyStreamingService:
    def stream_reply(self, message, history, era="1998"):
        error = RuntimeError("permission denied")
        error.code = 403
        raise error
        yield ""


class UnclassifiedStreamingService:
    def stream_reply(self, message, history, era="1998"):
        error = RuntimeError("secret-provider-detail")
        error.code = 429
        raise error
        yield ""


class UnclassifiedValueErrorStreamingService:
    def stream_reply(self, message, history, era="1998"):
        raise ValueError("private-provider-detail")
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


def test_pwa_manifest_and_root_scoped_service_worker_are_served():
    with TestClient(app) as client:
        manifest = client.get("/manifest.webmanifest")
        service_worker = client.get("/service-worker.js")

    assert manifest.status_code == 200
    assert manifest.json()["name"] == "RetroChat 98 / FutureChat 2058"
    assert {icon["sizes"] for icon in manifest.json()["icons"]} >= {"192x192", "512x512"}
    assert service_worker.status_code == 200
    assert service_worker.headers["content-type"].startswith("application/javascript")


def test_browser_responses_include_baseline_security_headers():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "no-referrer"


def test_completed_comparison_gets_a_shareable_url_and_can_be_reopened(monkeypatch):
    database = Path(f".test-comparisons-{uuid.uuid4().hex}.db")
    monkeypatch.setenv("COMPARISON_DB_PATH", str(database))
    comparison = {
        "question": "İnsanlar nasıl iletişim kuruyor?",
        "retro": "1998'de IRC ve e-posta kullanılıyor.",
        "future": "2058'de uzamsal arayüzler kullanılabilir.",
        "expires_in_days": 7,
    }

    try:
        with TestClient(app) as client:
            created = client.post("/api/comparisons", json=comparison)
            assert created.status_code == 201
            share_path = created.json()["share_path"]
            reopened = client.get(share_path.replace("/c/", "/api/comparisons/"))
            page = client.get(share_path)
    finally:
        database.unlink(missing_ok=True)

    assert share_path.startswith("/c/")
    assert reopened.status_code == 200
    assert reopened.json() == {
        "question": comparison["question"],
        "retro": comparison["retro"],
        "future": comparison["future"],
    }
    assert page.status_code == 200
    assert "RetroChat 98" in page.text


def test_reality_check_returns_grounded_1998_summary_and_sources():
    app.dependency_overrides[get_chat_service] = lambda: RealityCheckService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/reality-check", json={
                "question": "İletişim nasıldı?",
                "retro": "IRC kullanılıyordu.",
            })
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "summary": "Doğrulandı: İletişim nasıldı? / IRC kullanılıyordu.",
        "sources": [{"title": "Kaynak", "url": "https://example.com/history"}],
    }


def test_account_registration_login_and_logout_use_an_http_only_session(monkeypatch):
    database = Path(f".test-accounts-{uuid.uuid4().hex}.db")
    monkeypatch.setenv("COMPARISON_DB_PATH", str(database))
    credentials = {"username": "netgezgini", "password": "guclu-parola-98"}
    try:
        with TestClient(app) as client:
            registered = client.post("/api/auth/register", json=credentials)
            me = client.get("/api/auth/me")
            logged_out = client.post("/api/auth/logout")
            anonymous = client.get("/api/auth/me")
            logged_in = client.post("/api/auth/login", json=credentials)
            me_again = client.get("/api/auth/me")
    finally:
        database.unlink(missing_ok=True)

    assert registered.status_code == 201
    assert "HttpOnly" in registered.headers["set-cookie"]
    assert "SameSite=lax" in registered.headers["set-cookie"]
    assert me.json() == {"username": "netgezgini"}
    assert logged_out.status_code == 204
    assert anonymous.status_code == 401
    assert logged_in.status_code == 204
    assert me_again.json() == {"username": "netgezgini"}


def test_signed_in_account_can_sync_chats_between_clients(monkeypatch):
    database = Path(f".test-sync-{uuid.uuid4().hex}.db")
    monkeypatch.setenv("COMPARISON_DB_PATH", str(database))
    credentials = {"username": "gezgin98", "password": "baska-guclu-parola"}
    sessions = [{
        "id": "chat-1", "era": "1998", "title": "Modem sohbeti", "updated": 42,
        "messages": [
            {"role": "user", "content": "Modem nedir?", "time": "10:00"},
            {"role": "assistant", "content": "Telefon hattıyla bağlanır.", "time": "10:01"},
        ],
    }]
    try:
        with TestClient(app) as first_client:
            first_client.post("/api/auth/register", json=credentials)
            saved = first_client.put("/api/sync/chats", json={"sessions": sessions})
        with TestClient(app) as second_client:
            second_client.post("/api/auth/login", json=credentials)
            loaded = second_client.get("/api/sync/chats")
    finally:
        database.unlink(missing_ok=True)

    assert saved.status_code == 204
    assert loaded.status_code == 200
    assert loaded.json()["sessions"] == sessions


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
                json={"message": "Hangi yıldayız?", "era": "2058"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"reply": "2058 bağlantısından: Hangi yıldayız?"}


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


def test_metrics_require_a_bearer_token_and_never_include_message_content(monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "test-metrics-token")
    with TestClient(app) as client:
        unauthorized = client.get("/api/metrics")
        response = client.get("/api/metrics", headers={"Authorization": "Bearer test-metrics-token"})
    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert "requests" in response.json()
    assert "message" not in response.text


def test_signed_in_user_has_a_daily_chat_quota(monkeypatch):
    database = Path(f".test-quota-{uuid.uuid4().hex}.db")
    monkeypatch.setenv("COMPARISON_DB_PATH", str(database))
    monkeypatch.setenv("USER_DAILY_CHAT_LIMIT", "1")
    app.dependency_overrides[get_chat_service] = lambda: FakeChatService()
    try:
        with TestClient(app) as client:
            client.post("/api/auth/register", json={"username": "kotali", "password": "guclu-kota-parolasi"})
            first = client.post("/api/chat", json={"message": "İlk soru"})
            second = client.post("/api/chat", json={"message": "İkinci soru"})
    finally:
        app.dependency_overrides.clear()
        database.unlink(missing_ok=True)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"]["code"] == "daily_quota_reached"


def test_metrics_survive_in_memory_counter_loss(monkeypatch):
    database = Path(f".test-metrics-{uuid.uuid4().hex}.db")
    monkeypatch.setenv("COMPARISON_DB_PATH", str(database))
    monkeypatch.setenv("METRICS_TOKEN", "persistent-token")
    metrics.clear()
    try:
        with TestClient(app) as client:
            client.post("/api/events", json={"event": "retry"})
            metrics.clear()
            response = client.get("/api/metrics", headers={"Authorization": "Bearer persistent-token"})
    finally:
        database.unlink(missing_ok=True)

    assert response.status_code == 200
    assert response.json()["retries"] == 1


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


def test_stream_explains_and_logs_provider_connection_failures(caplog):
    app.dependency_overrides[get_chat_service] = lambda: DisconnectedStreamingService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/chat/stream", json={"message": "Merhaba"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert '"code":"upstream_unreachable"' in response.text
    assert "Model hizmetine bağlanılamıyor" in response.text
    assert "chat upstream failure type=ConnectError" in caplog.text


def test_stream_identifies_rejected_api_key_without_exposing_it():
    app.dependency_overrides[get_chat_service] = lambda: RejectedKeyStreamingService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/chat/stream", json={"message": "Merhaba"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert '"code":"invalid_api_key"' in response.text
    assert "API anahtarı geçersiz" in response.text
    assert "Please pass a valid API key" not in response.text


def test_stream_explains_provider_permission_denial():
    app.dependency_overrides[get_chat_service] = lambda: RestrictedKeyStreamingService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/chat/stream", json={"message": "Merhaba"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert '"code":"upstream_forbidden"' in response.text
    assert "erişimi reddedildi" in response.text


def test_stream_generic_error_exposes_only_safe_diagnostic_fields():
    app.dependency_overrides[get_chat_service] = lambda: UnclassifiedStreamingService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/chat/stream", json={"message": "Merhaba"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert '"code":"upstream_error"' in response.text
    assert '"provider_code":429' in response.text
    assert '"error_type":"RuntimeError"' in response.text
    assert "secret-provider-detail" not in response.text


def test_stream_value_error_reports_safe_failure_origin():
    app.dependency_overrides[get_chat_service] = lambda: UnclassifiedValueErrorStreamingService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/chat/stream", json={"message": "Merhaba"})
    finally:
        app.dependency_overrides.clear()
    assert '"error_type":"ValueError"' in response.text
    assert '"error_origin":"test_app.py:stream_reply:' in response.text
    assert "private-provider-detail" not in response.text


def test_missing_api_key_uses_structured_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "Merhaba"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "not_configured"


def test_product_events_count_without_accepting_message_content(monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "test-metrics-token")
    headers = {"Authorization": "Bearer test-metrics-token"}
    with TestClient(app) as client:
        before = client.get("/api/metrics", headers=headers).json()["retries"]
        response = client.post("/api/events", json={"event": "retry"})
        after = client.get("/api/metrics", headers=headers).json()["retries"]
        unsafe = client.post("/api/events", json={"event": "retry", "message": "özel soru"})
    assert response.status_code == 204
    assert after == before + 1
    assert unsafe.status_code == 422


def test_feedback_event_counts_without_accepting_chat_text(monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "test-metrics-token")
    headers = {"Authorization": "Bearer test-metrics-token"}
    with TestClient(app) as client:
        before = client.get("/api/metrics", headers=headers).json()["feedback_incomplete"]
        response = client.post("/api/events", json={"event": "feedback_incomplete"})
        after = client.get("/api/metrics", headers=headers).json()["feedback_incomplete"]
        unsafe = client.post("/api/events", json={"event": "feedback_incomplete", "message": "özel soru"})
    assert response.status_code == 204
    assert after == before + 1
    assert unsafe.status_code == 422
