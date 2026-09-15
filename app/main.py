import os
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app.gemini_service import GeminiChatService, MissingApiKeyError


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


app = FastAPI(title="RetroChat 98", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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


def get_chat_service(request: ChatRequest) -> GeminiChatService:
    try:
        return GeminiChatService(api_key=os.getenv("GEMINI_API_KEY", ""))
    except MissingApiKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/", include_in_schema=False)
def homepage() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    service: Annotated[GeminiChatService, Depends(get_chat_service)],
) -> ChatResponse:
    try:
        return ChatResponse(
            reply=service.reply(request.message, request.history, request.era)
        )
    except MissingApiKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        if getattr(exc, "code", None) == 503:
            raise HTTPException(
                status_code=503,
                detail="Gemini hatları şu an meşgul. Birkaç saniye sonra tekrar dene.",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail="Gemini bağlantısı kurulamadı. API anahtarını ve bağlantıyı kontrol et.",
        ) from exc
