import json
import socket
import subprocess
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="module")
def server():
    process = subprocess.Popen(
        [".venv/Scripts/python.exe", "-m", "uvicorn", "app.main:app", "--port", "8765"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", 8765), timeout=0.1):
                break
        except OSError:
            time.sleep(0.1)
    else:
        process.terminate()
        raise RuntimeError("Test sunucusu başlamadı")
    yield "http://127.0.0.1:8765"
    process.terminate()
    process.wait(timeout=5)


@pytest.fixture
def page(server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        yield page
        page.unroute_all(behavior="ignoreErrors")
        browser.close()


def stream_response(route, text="Yanıt geldi"):
    route.fulfill(
        status=200,
        content_type="text/event-stream",
        body=f'event: chunk\ndata: {{"text":"{text}"}}\n\nevent: done\ndata: {{}}\n\n',
    )


def test_chat_persists_after_reload_and_new_chat_clears_visible_log(page, server):
    page.route("**/api/chat/stream", lambda route: stream_response(route))
    page.goto(server)
    page.locator("#message-input").fill("İlk soru")
    page.locator("#send-button").click()
    page.locator("#chat-log").get_by_text("Yanıt geldi", exact=True).wait_for()
    page.reload()
    assert page.locator("#chat-log").get_by_text("İlk soru", exact=True).is_visible()
    assert page.locator("#chat-log").get_by_text("Yanıt geldi", exact=True).is_visible()
    page.get_by_role("button", name="Yeni sohbet").click()
    assert page.locator("#chat-log").get_by_text("İlk soru", exact=True).count() == 0


def test_failed_message_can_be_retried_without_retyping(page, server):
    attempts = []

    def answer(route):
        attempts.append(route.request.post_data_json["message"])
        if len(attempts) == 1:
            route.fulfill(status=503, content_type="application/json", body='{"detail":{"code":"upstream_busy","message":"Meşgul"}}')
        else:
            stream_response(route)

    page.route("**/api/chat/stream", answer)
    page.goto(server)
    page.locator("#message-input").fill("Tekrar gönder")
    page.locator("#send-button").click()
    page.get_by_role("button", name="Tekrar dene").click()
    page.locator("#chat-log").get_by_text("Yanıt geldi", exact=True).wait_for()
    assert attempts == ["Tekrar gönder", "Tekrar gönder"]
    assert page.locator(".user-message").count() == 1


def test_compare_asks_both_eras_without_adding_to_chat(page, server):
    eras = []

    def answer(route):
        era = route.request.post_data_json["era"]
        eras.append(era)
        stream_response(route, f"{era} yanıtı")

    page.route("**/api/chat/stream", answer)
    page.goto(server)
    page.get_by_role("button", name="İki dönemi karşılaştır").click()
    page.locator("#compare-input").fill("İletişim nasıl?")
    page.get_by_role("button", name="Karşılaştır", exact=True).click()
    page.locator("#compare-1998").get_by_text("1998 yanıtı", exact=True).wait_for()
    page.locator("#compare-2058").get_by_text("2058 yanıtı", exact=True).wait_for()
    assert set(eras) == {"1998", "2058"}
    assert page.locator(".user-message").count() == 0


def test_time_capsule_uses_completed_comparison_and_stays_out_of_chat(page, server):
    requests = []

    def answer(route):
        payload = route.request.post_data_json
        requests.append(payload)
        if "üç dönüm noktası" in payload["message"].lower():
            stream_response(route, "2035: Yeni ağlar kuruldu.")
        else:
            stream_response(route, f'{payload["era"]} yanıtı')

    page.route("**/api/chat/stream", answer)
    page.goto(server)
    page.locator("#compare-toggle").click()
    page.get_by_role("button", name="İletişim", exact=True).click()
    assert page.locator("#compare-input").input_value() == "İnsanlar birbirleriyle nasıl iletişim kuruyor?"
    page.locator('#compare-form button[type="submit"]').click()
    page.get_by_role("button", name="Zaman kapsülünü aç").click()
    page.locator("#capsule-result").get_by_text("2035: Yeni ağlar kuruldu.", exact=False).wait_for()
    assert requests[-1]["era"] == "2058"
    assert "1998 yanıtı" in requests[-1]["message"]
    assert "2058 yanıtı" in requests[-1]["message"]
    assert page.locator(".user-message").count() == 0


def test_new_comparison_clears_old_capsule_and_waits_for_both_answers(page, server):
    page.route("**/api/chat/stream", lambda route: stream_response(route, "Dönem yanıtı"))
    page.goto(server)
    page.locator("#compare-toggle").click()
    page.locator("#compare-input").fill("İlk soru")
    page.locator('#compare-form button[type="submit"]').click()
    page.get_by_role("button", name="Zaman kapsülünü aç").wait_for(state="visible")
    page.get_by_role("button", name="Zaman kapsülünü aç").click()
    page.locator("#capsule-result").get_by_text("Dönem yanıtı").wait_for()
    page.locator("#compare-input").fill("Yeni soru")
    page.locator('#compare-form button[type="submit"]').click()
    assert page.locator("#capsule-result").is_hidden()


def test_completed_comparison_can_be_shared_or_downloaded(page, server):
    page.add_init_script("""window.sharedData = null; navigator.share = async (data) => { window.sharedData = data; };""")
    page.route("**/api/chat/stream", lambda route: stream_response(route, f'{route.request.post_data_json["era"]} yanıtı'))
    page.goto(server)
    page.locator("#compare-toggle").click()
    page.locator("#compare-input").fill("Nasıl iletişim kuracağız?")
    page.locator('#compare-form button[type="submit"]').click()
    page.get_by_role("button", name="Paylaş").wait_for(state="visible")
    page.get_by_role("button", name="Paylaş").click()
    shared = page.evaluate("window.sharedData")
    assert "Nasıl iletişim kuracağız?" in shared["text"]
    assert "1998 yanıtı" in shared["text"]
    assert "2058 yanıtı" in shared["text"]
    with page.expect_download() as text_download:
        page.get_by_role("button", name="Metin indir").click()
    assert text_download.value.suggested_filename.endswith(".txt")
    assert "2058 yanıtı" in Path(text_download.value.path()).read_text(encoding="utf-8")
    with page.expect_download() as image_download:
        page.get_by_role("button", name="Görsel indir").click()
    assert image_download.value.suggested_filename.endswith(".png")
    assert Path(image_download.value.path()).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_share_falls_back_to_copy_when_native_share_is_missing(page, server):
    page.add_init_script("""window.copiedText = null;
      Object.defineProperty(navigator, 'share', {value: undefined, configurable: true});
      Object.defineProperty(navigator, 'clipboard', {value: {writeText: async text => {window.copiedText = text;}}});
    """)
    page.route("**/api/chat/stream", lambda route: stream_response(route, "Kısa yanıt"))
    page.goto(server)
    page.locator("#compare-toggle").click()
    page.locator("#compare-input").fill("Örnek soru")
    page.locator('#compare-form button[type="submit"]').click()
    page.get_by_role("button", name="Paylaş").click()
    assert "Örnek soru" in page.evaluate("window.copiedText")
    assert page.locator("#share-status").get_by_text("Karşılaştırma kopyalandı.").is_visible()


def test_saved_chats_are_searchable_by_message_and_exportable(page, server):
    page.add_init_script("""localStorage.setItem('retrochat-sessions-v1', JSON.stringify([
      {id:'one',era:'1998',title:'İlk sohbet',updated:2,messages:[
        {role:'user',content:'Modem nasıl çalışır?'},{role:'assistant',content:'Telefon hattıyla.'}]},
      {id:'two',era:'2058',title:'İkinci sohbet',updated:1,messages:[
        {role:'user',content:'Gelecekte ulaşım?'},{role:'assistant',content:'Yeni araçlarla.'}]}
    ]));""")
    page.goto(server)
    page.get_by_role("searchbox", name="Sohbetlerde ara").fill("ulaşım")
    assert page.get_by_role("button", name="2058 · İkinci sohbet").is_visible()
    assert page.get_by_role("button", name="1998 · İlk sohbet").count() == 0
    with page.expect_download() as json_download:
        page.get_by_role("button", name="JSON indir").click()
    exported = json.loads(Path(json_download.value.path()).read_text(encoding="utf-8"))
    assert len(exported) == 2
    assert exported[0]["messages"][0]["content"] == "Modem nasıl çalışır?"
    with page.expect_download() as text_download:
        page.get_by_role("button", name="Sohbet metni indir").click()
    text = Path(text_download.value.path()).read_text(encoding="utf-8")
    assert "Modem nasıl çalışır?" in text
    assert "Gelecekte ulaşım?" in text


def test_reading_preferences_persist_and_split_long_answer(page, server):
    long_answer = "Bu bir deneme cümlesidir. " * 55
    page.route("**/api/chat/stream", lambda route: stream_response(route, long_answer))
    page.goto(server)
    assert page.get_by_label("Yazı boyutu").is_visible()
    page.get_by_label("Yazı boyutu").select_option("large")
    page.get_by_label("Hareket").select_option("reduced")
    page.get_by_label("Uzun yanıtları bölümle").check()
    page.locator("#message-input").fill("Uzun anlat")
    page.locator("#send-button").click()
    page.locator(".bot-message .answer-part").nth(1).wait_for()
    assert page.locator("body").get_attribute("data-text-size") == "large"
    assert page.locator("body").get_attribute("data-motion") == "reduced"
    assert page.locator(".bot-message .answer-part").first.evaluate("element => getComputedStyle(element).fontSize") == "18px"
    assert page.locator("#marquee-track").evaluate("element => getComputedStyle(element).animationName") == "none"
    assert page.locator("#announcement").text_content() == "RetroChat98 yanıtı tamamlandı."
    page.reload()
    assert page.get_by_label("Yazı boyutu").input_value() == "large"
    assert page.get_by_label("Hareket").input_value() == "reduced"
    assert page.get_by_label("Uzun yanıtları bölümle").is_checked()
    assert page.locator(".bot-message .answer-part").count() > 1


def test_answer_feedback_is_saved_and_sends_only_selected_reason(page, server):
    events = []
    page.route("**/api/events", lambda route: (events.append(route.request.post_data_json), route.fulfill(status=204)))
    page.route("**/api/chat/stream", lambda route: stream_response(route, "Özel yanıt metni"))
    page.goto(server)
    page.locator("#message-input").fill("Özel soru metni")
    page.locator("#send-button").click()
    page.locator("#chat-log").get_by_text("Özel yanıt metni", exact=True).wait_for()
    assert page.get_by_role("button", name="Yarım kaldı").is_visible()
    page.get_by_role("button", name="Yarım kaldı").click()
    assert page.locator("#chat-log").get_by_text("Geri bildirim alındı: Yarım kaldı").is_visible()
    page.reload()
    assert page.locator("#chat-log").get_by_text("Geri bildirim alındı: Yarım kaldı").is_visible()
    assert [event for event in events if event["event"] == "feedback_incomplete"] == [{"event": "feedback_incomplete"}]
    assert "Özel soru metni" not in str(events)
    assert "Özel yanıt metni" not in str(events)


def test_compare_error_clears_waiting_labels(page, server):
    page.route(
        "**/api/chat/stream",
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body='{"detail":{"code":"invalid_api_key","message":"API anahtarı geçersiz"}}',
        ),
    )
    page.goto(server)
    page.locator("#compare-toggle").click()
    page.locator("#compare-input").fill("İletişim nasıl?")
    page.locator('#compare-form button[type="submit"]').click()
    page.locator("#compare-error").wait_for(state="visible")
    assert "Yanıt bekleniyor..." not in page.locator("#compare-1998").text_content()
    assert "Yanıt bekleniyor..." not in page.locator("#compare-2058").text_content()


def test_era_change_discards_old_pending_reply(page, server):
    pending = []
    page.route("**/api/chat/stream", lambda route: pending.append(route))
    page.goto(server)
    page.locator("#message-input").fill("Eski soru")
    page.locator("#send-button").click()
    page.wait_for_function("() => document.querySelector('#cancel-button').hidden === false")
    page.get_by_role("button", name="Modernleştir").click()
    assert page.locator("body").get_attribute("data-era") == "2058"
    assert page.get_by_role("heading", name="FutureChat 2058 — İletişim Merkezi").is_visible()
    assert page.locator("#chat-log").get_by_text("Eski soru", exact=True).count() == 0


def test_old_2030_chats_remain_visible_without_becoming_2058_context(page, server):
    page.add_init_script("""localStorage.setItem('retrochat-sessions-v1', JSON.stringify([{
      id: 'old-chat', era: '2030', title: 'Eski soru', updated: 1,
      messages: [{role: 'user', content: '2030 sorusu'}, {role: 'assistant', content: '2030 yanıtı'}]
    }]));""")
    histories = []

    def answer(route):
        histories.append(route.request.post_data_json["history"])
        stream_response(route, "2058 yanıtı")

    page.route("**/api/chat/stream", answer)
    page.goto(server)
    assert page.locator("body").get_attribute("data-era") == "2058"
    assert page.get_by_role("button", name="2058 · 2030 arşivi · Eski soru").is_visible()
    assert page.locator("#chat-log").get_by_text("2030 yanıtı", exact=True).is_visible()
    page.locator("#message-input").fill("Yeni soru")
    page.locator("#send-button").click()
    page.locator("#chat-log").get_by_text("2058 yanıtı", exact=True).wait_for()
    assert histories == [[]]
    assert page.get_by_role("button", name="2058 · 2030 arşivi · Yeni soru").is_visible()


def test_saved_chat_is_a_keyboard_accessible_button(page, server):
    page.route("**/api/chat/stream", lambda route: stream_response(route))
    page.goto(server)
    page.locator("#message-input").fill("Kaydedilen soru")
    page.locator("#send-button").click()
    page.locator("#chat-log").get_by_text("Yanıt geldi", exact=True).wait_for()
    assert page.get_by_role("button", name="1998 · Kaydedilen soru").is_visible()


def test_prompt_fills_composer_and_deleting_chat_removes_saved_message(page, server):
    page.route("**/api/chat/stream", lambda route: stream_response(route))
    page.goto(server)
    page.get_by_role("button", name="İnternete nasıl bağlanılıyor?").click()
    assert page.locator("#message-input").input_value() == "İnsanlar internete nasıl bağlanıyor?"
    page.locator("#send-button").click()
    page.locator("#chat-log").get_by_text("Yanıt geldi", exact=True).wait_for()
    page.get_by_role("button", name="Bu sohbeti sil").click()
    page.reload()
    assert page.locator("#chat-log").get_by_text("İnsanlar internete nasıl bağlanıyor?", exact=True).count() == 0


def test_mobile_page_has_no_horizontal_overflow_or_script_error(page, server):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(server)
    assert page.get_by_role("heading", name="RetroChat 98 — Sohbet Odası").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not errors


def test_product_events_have_names_but_no_chat_text(page, server):
    events = []
    page.route("**/api/events", lambda route: (events.append(route.request.post_data_json), route.fulfill(status=204)))
    page.route("**/api/chat/stream", lambda route: stream_response(route))
    page.goto(server)
    page.locator("#message-input").fill("Gizli soru metni")
    page.locator("#send-button").click()
    page.locator("#chat-log").get_by_text("Yanıt geldi", exact=True).wait_for()
    page.wait_for_timeout(100)
    assert {item["event"] for item in events} >= {"page_view", "chat_started"}
    assert "Gizli soru metni" not in str(events)


def test_unanswered_message_can_be_retried_after_reload(page, server):
    attempts = []

    def answer(route):
        attempts.append(route.request.post_data_json["message"])
        if len(attempts) == 1:
            route.fulfill(status=503, content_type="application/json", body='{"detail":{"code":"upstream_busy","message":"Meşgul"}}')
        else:
            stream_response(route)

    page.route("**/api/chat/stream", answer)
    page.goto(server)
    page.locator("#message-input").fill("Yarım kalan soru")
    page.locator("#send-button").click()
    page.get_by_role("button", name="Tekrar dene").wait_for()
    page.reload()
    page.get_by_role("button", name="Tekrar dene").click()
    page.locator("#chat-log").get_by_text("Yanıt geldi", exact=True).wait_for()
    assert attempts == ["Yarım kalan soru", "Yarım kalan soru"]
