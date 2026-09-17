import os
import asyncio
import json
import logging
import queue
import threading
import time
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
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
    era: Literal["1998", "2030"] = "1998"

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
    event: Literal["page_view", "chat_started", "retry", "comparison_started"]


def get_chat_service(request: ChatRequest) -> GeminiChatService:
    try:
        return GeminiChatService(api_key=os.getenv("GEMINI_API_KEY", ""))
    except MissingApiKeyError as exc:
        raise service_error(exc) from exc


@app.get("/", include_in_schema=False)
def homepage() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
