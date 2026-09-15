import pytest

from app.gemini_service import GeminiChatService, MissingApiKeyError


class TextResponse:
    text = "Modemler geleceğin kapısını açıyor!"


class FakeModels:
    def generate_content(self, **kwargs):
        return TextResponse()


class FakeClient:
    models = FakeModels()


class TemporarilyUnavailableError(RuntimeError):
    code = 503


class FallbackModels:
    def generate_content(self, **kwargs):
        if kwargs["model"] == "gemini-flash-latest":
            raise TemporarilyUnavailableError("Model yoğunluğu")
        if kwargs["model"] == "gemini-3.6-flash":
            return TextResponse()
        raise AssertionError("Beklenmeyen model kullanıldı")


class FallbackClient:
    models = FallbackModels()


class EraAwareModels:
    def generate_content(self, **kwargs):
        instruction = kwargs["config"].system_instruction
        text = "2030 kanalından bağlandım." if "2030" in instruction else "1998 kanalından bağlandım."
        return type("EraResponse", (), {"text": text})()


class EraAwareClient:
    models = EraAwareModels()


def test_service_returns_generated_text():
    service = GeminiChatService(api_key="test-key", client=FakeClient())

    result = service.reply("Gelecek nasıl olacak?", [])

    assert result == "Modemler geleceğin kapısını açıyor!"


def test_service_requires_an_api_key():
    with pytest.raises(MissingApiKeyError):
        GeminiChatService(api_key="")


def test_service_rejects_an_empty_model_response():
    class EmptyModels:
        def generate_content(self, **kwargs):
            return type("EmptyResponse", (), {"text": None})()

    class EmptyClient:
        models = EmptyModels()

    service = GeminiChatService(api_key="test-key", client=EmptyClient())

    with pytest.raises(RuntimeError, match="boş yanıt"):
        service.reply("Orada mısın?", [])


def test_service_uses_fallback_when_latest_model_is_temporarily_unavailable():
    service = GeminiChatService(
        api_key="test-key",
        client=FallbackClient(),
        model="gemini-flash-latest",
    )

    result = service.reply("Gelecek nasıl olacak?", [])

    assert result == "Modemler geleceğin kapısını açıyor!"


def test_service_adopts_the_requested_2030_persona():
    service = GeminiChatService(api_key="test-key", client=EraAwareClient())

    result = service.reply("Hangi yıldayız?", [], era="2030")

    assert result == "2030 kanalından bağlandım."
