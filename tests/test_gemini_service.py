import pytest
from types import SimpleNamespace

from app.gemini_service import GeminiChatService, MissingApiKeyError


class TextResponse:
    text = "Modemler geleceğin kapısını açıyor!"


class FakeModels:
    def generate_content(self, **kwargs):
        return TextResponse()

    def generate_content_stream(self, **kwargs):
        yield type("Part", (), {"text": "Parça "})()
        yield type("Part", (), {"text": "iki"})()


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
        text = "2058 kanalından bağlandım." if "2058" in instruction else "1998 kanalından bağlandım."
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


def test_service_adopts_the_requested_2058_persona():
    service = GeminiChatService(api_key="test-key", client=EraAwareClient())

    result = service.reply("Hangi yıldayız?", [], era="2058")

    assert result == "2058 kanalından bağlandım."


def test_historical_reality_check_uses_search_grounding_and_returns_sources():
    class GroundedModels:
        config = None

        def generate_content(self, **kwargs):
            self.config = kwargs["config"]
            metadata = SimpleNamespace(grounding_chunks=[
                SimpleNamespace(web=SimpleNamespace(uri="https://example.com/irc", title="IRC tarihi")),
                SimpleNamespace(web=SimpleNamespace(uri="https://example.com/irc", title="IRC tarihi")),
                SimpleNamespace(web=SimpleNamespace(uri="https://example.com/email", title="E-posta tarihi")),
            ])
            return SimpleNamespace(
                text="IRC ve e-posta iddiaları tarihsel kayıtlarla uyumlu.",
                candidates=[SimpleNamespace(grounding_metadata=metadata)],
            )

    class GroundedClient:
        models = GroundedModels()

    service = GeminiChatService(api_key="test-key", client=GroundedClient())
    result = service.verify_historical_claims(
        "İnsanlar nasıl iletişim kuruyordu?",
        "IRC kanalları ve e-posta kullanıyorduk.",
    )

    assert GroundedClient.models.config.tools[0].google_search is not None
    assert result == {
        "summary": "IRC ve e-posta iddiaları tarihsel kayıtlarla uyumlu.",
        "sources": [
            {"title": "IRC tarihi", "url": "https://example.com/irc"},
            {"title": "E-posta tarihi", "url": "https://example.com/email"},
        ],
    }


@pytest.mark.parametrize(
    ("era", "prompt", "response", "expected_issue"),
    [
        ("1998", "TikTok'ta nasıl video paylaşırım?", "TikTok'ta paylaş düğmesine bas.", "post_1998_certainty"),
        ("2058", "2058'te ulaşım nasıl?", "Uçan taksiler kesin olarak her şehirde olacak.", "future_certainty"),
        ("1998", "Kısa anlat", "kelime " * 181, "too_long"),
    ],
)
def test_persona_evaluation_flags_contract_violations(era, prompt, response, expected_issue):
    result = GeminiChatService.evaluate_persona_response(era, prompt, response)

    assert not result["passed"]
    assert expected_issue in result["issues"]


@pytest.mark.parametrize(
    ("era", "prompt", "response"),
    [
        ("1998", "TikTok nedir?", "Bunu bilmiyorum; geleceğe ait bir fikir ya da tahmin olabilir."),
        ("2058", "2058'te ulaşım nasıl?", "Yaratıcı bir gelecek kurgusunda otonom araçlar yaygın olabilir."),
    ],
)
def test_persona_evaluation_accepts_period_aware_uncertainty(era, prompt, response):
    result = GeminiChatService.evaluate_persona_response(era, prompt, response)

    assert result == {"passed": True, "issues": []}


def test_stream_continues_when_the_model_hits_its_token_limit():
    class TruncatedModels:
        calls = 0

        def generate_content_stream(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                yield type("Part", (), {"text": "Bilgisayar başındaysanız en güzeli ", "candidates": []})()
                yield type("Part", (), {"text": "", "candidates": [type("Candidate", (), {"finish_reason": "MAX_TOKENS"})()]})()
            else:
                yield type("Part", (), {"text": "IRC üzerinden sohbet etmektir.", "candidates": [type("Candidate", (), {"finish_reason": "STOP"})()]})()

    class TruncatedClient:
        models = TruncatedModels()

    service = GeminiChatService(api_key="test-key", client=TruncatedClient())

    assert "".join(service.stream_reply("Nasıl konuşuruz?", [])) == "Bilgisayar başındaysanız en güzeli IRC üzerinden sohbet etmektir."
    assert TruncatedClient.models.calls == 2


def test_stream_never_reports_a_repeatedly_truncated_answer_as_complete():
    class TruncatedModels:
        def generate_content_stream(self, **kwargs):
            yield type("Part", (), {"text": "Yarım cevap", "candidates": [type("Candidate", (), {"finish_reason": "MAX_TOKENS"})()]})()

    class TruncatedClient:
        models = TruncatedModels()

    service = GeminiChatService(api_key="test-key", client=TruncatedClient())

    with pytest.raises(RuntimeError, match="tamamlanamadı"):
        list(service.stream_reply("Merhaba", []))


def test_nonstreaming_reply_retries_a_truncated_response():
    class TruncatedModels:
        calls = 0

        def generate_content(self, **kwargs):
            self.calls += 1
            finish = "MAX_TOKENS" if self.calls == 1 else "STOP"
            text = "Yarım cevap" if self.calls == 1 else "Tamamlanmış cevap."
            return type("Response", (), {"text": text, "candidates": [type("Candidate", (), {"finish_reason": finish})()]})()

    class TruncatedClient:
        models = TruncatedModels()

    service = GeminiChatService(api_key="test-key", client=TruncatedClient())

    assert service.reply("Merhaba", []) == "Tamamlanmış cevap."
    assert TruncatedClient.models.calls == 2


def test_nonstreaming_retry_stays_on_fallback_model_after_a_503():
    class FallbackThenTruncatedModels:
        calls = []

        def generate_content(self, **kwargs):
            self.calls.append(kwargs["model"])
            if kwargs["model"] == "gemini-flash-latest":
                raise TemporarilyUnavailableError("Model yoğunluğu")
            finish = "MAX_TOKENS" if len(self.calls) == 2 else "STOP"
            return type("Response", (), {"text": "Tam yanıt" if finish == "STOP" else "Yarım", "candidates": [type("Candidate", (), {"finish_reason": finish})()]})()

    class FallbackThenTruncatedClient:
        models = FallbackThenTruncatedModels()

    service = GeminiChatService(api_key="test-key", client=FallbackThenTruncatedClient(), model="gemini-flash-latest")

    assert service.reply("Merhaba", []) == "Tam yanıt"
    assert FallbackThenTruncatedClient.models.calls == ["gemini-flash-latest", "gemini-3.6-flash", "gemini-3.6-flash"]


def test_service_streams_only_nonempty_text():
    service = GeminiChatService(api_key="test-key", client=FakeClient())
    assert list(service.stream_reply("Merhaba", [], era="1998")) == ["Parça ", "iki"]


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_model_environment_uses_working_defaults(monkeypatch, blank):
    monkeypatch.setenv("GEMINI_MODEL", blank)
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", blank)
    service = GeminiChatService(api_key="test-key", client=FakeClient())

    assert service.model == "gemini-flash-latest"
    assert service.fallback_model == "gemini-3.6-flash"
    assert list(service.stream_reply("Merhaba", [], era="1998")) == ["Parça ", "iki"]
