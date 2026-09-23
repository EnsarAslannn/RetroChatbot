import os
import asyncio
import hashlib
import json
import logging
import queue
import secrets
import sqlite3
import threading
import time
import traceback
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from httpx import ConnectError, ConnectTimeout
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.gemini_service import GeminiChatService, MissingApiKeyError


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


app = FastAPI(title="RetroChat 98", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
logger = logging.getLogger("retrochat")


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self.clients: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, client: str) -> bool:
        now = time.monotonic()
        with self.lock:
            attempts = self.clients[client]
            while attempts and attempts[0] <= now - self.window_seconds:
                attempts.popleft()
            if len(attempts) >= self.limit:
                return False
            attempts.append(now)
            return True


limiter = SlidingWindowLimiter(limit=int(os.getenv("CHAT_RATE_LIMIT", "20")), window_seconds=60)
event_limiter = SlidingWindowLimiter(limit=120, window_seconds=60)
metrics = Counter()
metrics_lock = threading.Lock()


def record(result: str, started: float) -> None:
    elapsed_ms = round((time.monotonic() - started) * 1000)
    with metrics_lock:
        metrics["requests"] += 1
        metrics[result] += 1
        metrics["total_latency_ms"] += elapsed_ms
    logger.info("chat result=%s duration_ms=%s", result, elapsed_ms)


def enforce_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    if not limiter.allow(client):
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "message": "Çok fazla istek gönderildi. Bir dakika sonra tekrar dene."},
        )


def enforce_event_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    if not event_limiter.allow(client):
        raise HTTPException(429, detail={"code": "rate_limited", "message": "Çok fazla olay gönderildi."})


def timeout_seconds() -> float:
    return max(0.001, float(os.getenv("CHAT_TIMEOUT_SECONDS", "30")))


def service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MissingApiKeyError):
        return HTTPException(503, detail={"code": "not_configured", "message": str(exc)})
    provider_message = str(getattr(exc, "message", "")).lower()
    if getattr(exc, "code", None) == 400 and ("api key not valid" in provider_message or "api_key_invalid" in provider_message):
        return HTTPException(502, detail={"code": "invalid_api_key", "message": "Sunucudaki Gemini API anahtarı geçersiz. Anahtarı ve erişim kısıtlarını kontrol edin."})
    if getattr(exc, "code", None) in (401, 403):
        return HTTPException(502, detail={"code": "upstream_forbidden", "message": "Gemini erişimi reddedildi. Sunucudaki API anahtarını ve erişim kısıtlarını kontrol edin."})
    if getattr(exc, "code", None) == 503:
        return HTTPException(503, detail={"code": "upstream_busy", "message": "Gemini hatları şu an meşgul. Birkaç saniye sonra tekrar dene."})
    if isinstance(exc, (ConnectError, ConnectTimeout)):
        return HTTPException(503, detail={"code": "upstream_unreachable", "message": "Model hizmetine bağlanılamıyor. Sunucunun internet bağlantısını kontrol edip tekrar dene."})
    detail = {"code": "upstream_error", "message": "Sohbet hizmetine bağlanılamadı. Tekrar dene.", "error_type": type(exc).__name__}
    if exc.__traceback__:
        origin = traceback.extract_tb(exc.__traceback__)[-1]
        detail["error_origin"] = f"{Path(origin.filename).name}:{origin.name}:{origin.lineno}"
    provider_code = getattr(exc, "code", None)
    if isinstance(provider_code, int) and 400 <= provider_code <= 599:
        detail["provider_code"] = provider_code
    return HTTPException(502, detail=detail)


def log_service_failure(exc: Exception) -> None:
    logger.error("chat upstream failure type=%s code=%s", type(exc).__name__, getattr(exc, "code", None))


class HistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryItem] = Field(default_factory=list, max_length=12)
    era: Literal["1998", "2058"] = "1998"

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Mesaj boş olamaz.")
        return value


class ChatResponse(BaseModel):
    reply: str


class ProductEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: Literal["page_view", "chat_started", "retry", "comparison_started", "feedback_period_fit", "feedback_incomplete", "feedback_repetitive"]


class SharedComparisonRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    retro: str = Field(min_length=1, max_length=20000)
    future: str = Field(min_length=1, max_length=20000)
    expires_in_days: Literal[7, 30] = 7


class SharedComparison(BaseModel):
    question: str
    retro: str
    future: str


class RealityCheckRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    retro: str = Field(min_length=1, max_length=20000)


class RealitySource(BaseModel):
    title: str
    url: str


class RealityCheckResponse(BaseModel):
    summary: str
    sources: list[RealitySource]


class AuthCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.lower()


class SyncedMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)
    time: str | None = Field(default=None, max_length=30)
    feedback: Literal["period_fit", "incomplete", "repetitive"] | None = None


class SyncedChat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=100)
    era: Literal["1998", "2058"]
    title: str = Field(min_length=1, max_length=200)
    updated: float
    messages: list[SyncedMessage] = Field(max_length=100)


class SyncPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sessions: list[SyncedChat] = Field(max_length=30)


def comparison_database_path() -> Path:
    return Path(os.getenv("COMPARISON_DB_PATH", str(BASE_DIR / "retrochat.db")))


def comparison_connection() -> sqlite3.Connection:
    database = comparison_database_path()
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.execute(
        """CREATE TABLE IF NOT EXISTS shared_comparisons (
        slug TEXT PRIMARY KEY, question TEXT NOT NULL, retro TEXT NOT NULL,
        future TEXT NOT NULL, expires_at INTEGER NOT NULL
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_salt TEXT NOT NULL, password_hash TEXT NOT NULL, created_at INTEGER NOT NULL
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS auth_sessions (
        token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires_at INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS synced_chats (
        user_id INTEGER PRIMARY KEY, payload TEXT NOT NULL, updated_at INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )"""
    )
    return connection


AUTH_COOKIE = "retrochat_session"
AUTH_MAX_AGE = 30 * 86400


def password_digest(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32).hex()


def session_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def secure_cookie_enabled() -> bool:
    return os.getenv("AUTH_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        AUTH_COOKIE, token, max_age=AUTH_MAX_AGE, httponly=True,
        secure=secure_cookie_enabled(), samesite="lax", path="/",
    )


def create_auth_session(connection: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    connection.execute(
        "INSERT INTO auth_sessions VALUES (?, ?, ?)",
        (session_hash(token), user_id, int(time.time()) + AUTH_MAX_AGE),
    )
    return token


def require_user(request: Request) -> tuple[int, str]:
    token = request.cookies.get(AUTH_COOKIE)
    if not token:
        raise HTTPException(401, detail={"code": "authentication_required", "message": "Eşitlemek için giriş yap."})
    connection = comparison_connection()
    try:
        row = connection.execute(
            """SELECT users.id, users.username FROM auth_sessions
            JOIN users ON users.id = auth_sessions.user_id
            WHERE auth_sessions.token_hash = ? AND auth_sessions.expires_at > ?""",
            (session_hash(token), int(time.time())),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise HTTPException(401, detail={"code": "authentication_required", "message": "Oturumun sona erdi. Yeniden giriş yap."})
    return int(row[0]), str(row[1])


def get_chat_service(request: ChatRequest) -> GeminiChatService:
    try:
        return GeminiChatService(api_key=os.getenv("GEMINI_API_KEY", ""))
    except MissingApiKeyError as exc:
        raise service_error(exc) from exc


@app.get("/", include_in_schema=False)
def homepage() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/manifest.webmanifest", include_in_schema=False)
def pwa_manifest() -> FileResponse:
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/service-worker.js", include_in_schema=False)
def service_worker() -> FileResponse:
    return FileResponse(STATIC_DIR / "service-worker.js", media_type="application/javascript")


@app.get("/c/{slug}", include_in_schema=False)
def shared_comparison_page(slug: str) -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/comparisons", status_code=201)
def create_shared_comparison(item: SharedComparisonRequest) -> dict[str, str]:
    slug = secrets.token_urlsafe(9)
    expires_at = int(time.time()) + item.expires_in_days * 86400
    connection = comparison_connection()
    try:
        connection.execute(
            "INSERT INTO shared_comparisons VALUES (?, ?, ?, ?, ?)",
            (slug, item.question.strip(), item.retro.strip(), item.future.strip(), expires_at),
        )
        connection.commit()
    finally:
        connection.close()
    return {"share_path": f"/c/{slug}"}


@app.get("/api/comparisons/{slug}", response_model=SharedComparison)
def get_shared_comparison(slug: str) -> SharedComparison:
    connection = comparison_connection()
    try:
        row = connection.execute(
            "SELECT question, retro, future FROM shared_comparisons WHERE slug = ? AND expires_at > ?",
            (slug, int(time.time())),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise HTTPException(404, detail={"code": "comparison_not_found", "message": "Paylaşılan karşılaştırma bulunamadı veya süresi doldu."})
    return SharedComparison(question=row[0], retro=row[1], future=row[2])


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/register", status_code=201, dependencies=[Depends(enforce_event_limit)])
def register(credentials: AuthCredentials, response: Response) -> dict[str, str]:
    salt = os.urandom(16)
    connection = comparison_connection()
    try:
        cursor = connection.execute(
            "INSERT INTO users (username, password_salt, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (credentials.username, salt.hex(), password_digest(credentials.password, salt), int(time.time())),
        )
        token = create_auth_session(connection, int(cursor.lastrowid))
        connection.commit()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, detail={"code": "username_taken", "message": "Bu kullanıcı adı zaten alınmış."}) from exc
    finally:
        connection.close()
    set_auth_cookie(response, token)
    return {"username": credentials.username}


@app.post("/api/auth/login", status_code=204, dependencies=[Depends(enforce_event_limit)])
def login(credentials: AuthCredentials) -> Response:
    connection = comparison_connection()
    try:
        row = connection.execute(
            "SELECT id, password_salt, password_hash FROM users WHERE username = ?",
            (credentials.username,),
        ).fetchone()
        if row is None:
            password_digest(credentials.password, bytes(16))
            raise HTTPException(401, detail={"code": "invalid_credentials", "message": "Kullanıcı adı veya parola hatalı."})
        actual = password_digest(credentials.password, bytes.fromhex(row[1]))
        if not secrets.compare_digest(actual, row[2]):
            raise HTTPException(401, detail={"code": "invalid_credentials", "message": "Kullanıcı adı veya parola hatalı."})
        token = create_auth_session(connection, int(row[0]))
        connection.commit()
    finally:
        connection.close()
    response = Response(status_code=204)
    set_auth_cookie(response, token)
    return response


@app.post("/api/auth/logout", status_code=204)
def logout(request: Request) -> Response:
    token = request.cookies.get(AUTH_COOKIE)
    if token:
        connection = comparison_connection()
        try:
            connection.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (session_hash(token),))
            connection.commit()
        finally:
            connection.close()
    response = Response(status_code=204)
    response.delete_cookie(AUTH_COOKIE, path="/", secure=secure_cookie_enabled(), httponly=True, samesite="lax")
    return response


@app.get("/api/auth/me")
def current_account(user: Annotated[tuple[int, str], Depends(require_user)]) -> dict[str, str]:
    return {"username": user[1]}


@app.get("/api/sync/chats", response_model=SyncPayload, response_model_exclude_none=True)
def load_synced_chats(user: Annotated[tuple[int, str], Depends(require_user)]) -> SyncPayload:
    connection = comparison_connection()
    try:
        row = connection.execute("SELECT payload FROM synced_chats WHERE user_id = ?", (user[0],)).fetchone()
    finally:
        connection.close()
    return SyncPayload.model_validate_json(row[0]) if row else SyncPayload(sessions=[])


@app.put("/api/sync/chats", status_code=204)
def save_synced_chats(payload: SyncPayload, user: Annotated[tuple[int, str], Depends(require_user)]) -> Response:
    connection = comparison_connection()
    try:
        connection.execute(
            """INSERT INTO synced_chats (user_id, payload, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at""",
            (user[0], payload.model_dump_json(exclude_none=True), int(time.time())),
        )
        connection.commit()
    finally:
        connection.close()
    return Response(status_code=204)


@app.post("/api/reality-check", response_model=RealityCheckResponse, dependencies=[Depends(enforce_limit)])
async def reality_check(
    request: RealityCheckRequest,
    service: Annotated[GeminiChatService, Depends(get_chat_service)],
) -> RealityCheckResponse:
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(service.verify_historical_claims, request.question, request.retro),
            timeout=timeout_seconds(),
        )
        return RealityCheckResponse(**result)
    except TimeoutError as exc:
        raise HTTPException(504, detail={"code": "upstream_timeout", "message": "Doğrulama süresi doldu. Tekrar dene."}) from exc
    except Exception as exc:
        log_service_failure(exc)
        raise service_error(exc) from exc


@app.get("/api/metrics")
def public_metrics() -> dict[str, int | float]:
    with metrics_lock:
        requests = metrics["requests"]
        return {
            "requests": requests,
            "successes": metrics["success"],
            "errors": metrics["error"],
            "timeouts": metrics["timeout"],
            "average_latency_ms": round(metrics["total_latency_ms"] / requests) if requests else 0,
            "page_views": metrics["page_view"],
            "chat_starts": metrics["chat_started"],
            "retries": metrics["retry"],
            "comparisons": metrics["comparison_started"],
            "feedback_period_fit": metrics["feedback_period_fit"],
            "feedback_incomplete": metrics["feedback_incomplete"],
            "feedback_repetitive": metrics["feedback_repetitive"],
            "chat_start_rate": round(metrics["chat_started"] / metrics["page_view"], 3) if metrics["page_view"] else 0,
            "retry_rate": round(metrics["retry"] / requests, 3) if requests else 0,
        }


@app.post("/api/events", status_code=204, dependencies=[Depends(enforce_event_limit)])
def product_event(item: ProductEvent) -> None:
    with metrics_lock:
        metrics[item.event] += 1


@app.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(enforce_limit)])
async def chat(
    request: ChatRequest,
    service: Annotated[GeminiChatService, Depends(get_chat_service)],
) -> ChatResponse:
    started = time.monotonic()
    try:
        reply = await asyncio.wait_for(
            asyncio.to_thread(service.reply, request.message, request.history, request.era),
            timeout=timeout_seconds(),
        )
        record("success", started)
        return ChatResponse(reply=reply)
    except TimeoutError as exc:
        record("timeout", started)
        raise HTTPException(504, detail={"code": "upstream_timeout", "message": "Yanıt süresi doldu. Tekrar dene."}) from exc
    except Exception as exc:
        record("error", started)
        log_service_failure(exc)
        raise service_error(exc) from exc


def event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"


@app.post("/api/chat/stream", dependencies=[Depends(enforce_limit)])
def stream_chat(
    request: ChatRequest,
    service: Annotated[GeminiChatService, Depends(get_chat_service)],
) -> StreamingResponse:
    def generate():
        started = time.monotonic()
        chunks: queue.Queue[tuple[str, object]] = queue.Queue()
        stopped = threading.Event()

        def produce():
            try:
                for text in service.stream_reply(request.message, request.history, request.era):
                    if stopped.is_set():
                        break
                    chunks.put(("chunk", text))
                chunks.put(("done", None))
            except Exception as exc:
                chunks.put(("error", exc))

        threading.Thread(target=produce, daemon=True).start()
        try:
            while True:
                remaining = timeout_seconds() - (time.monotonic() - started)
                if remaining <= 0:
                    record("timeout", started)
                    yield event("error", {"code": "upstream_timeout", "message": "Yanıt süresi doldu. Tekrar dene."})
                    break
                try:
                    kind, value = chunks.get(timeout=remaining)
                except queue.Empty:
                    record("timeout", started)
                    yield event("error", {"code": "upstream_timeout", "message": "Yanıt süresi doldu. Tekrar dene."})
                    break
                if kind == "chunk":
                    yield event("chunk", {"text": value})
                elif kind == "done":
                    record("success", started)
                    yield event("done", {})
                    break
                else:
                    record("error", started)
                    log_service_failure(value)
                    error = service_error(value)
                    yield event("error", error.detail)
                    break
        finally:
            stopped.set()

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
