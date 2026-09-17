import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent


def verify_page(page, screenshot_name):
    console_errors = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)

    def answer_chat(route):
        request = route.request.post_data_json
        reply = (
            "2030 bağlantısı aktif. Geleceğe hoş geldin."
            if request["era"] == "2030"
            else "1998 bağlantısı aktif. IRC dostları burada."
        )
        route.fulfill(
            status=200,
            content_type="text/event-stream",
            body=f"event: chunk\ndata: {json.dumps({'text': reply}, ensure_ascii=False)}\n\nevent: done\ndata: {{}}\n\n",
        )

    page.route(
        "**/api/chat/stream",
        answer_chat,
    )
    page.goto("http://127.0.0.1:8000")
    page.wait_for_load_state("networkidle")

    assert page.get_by_role("heading", name="RetroChat 98 — Sohbet Odası").is_visible()

    page.get_by_role("button", name="Modernleştir").click()
    assert page.locator("body").get_attribute("data-era") == "2030"
    assert page.get_by_role("heading", name="NovaChat 30 — İletişim Merkezi").is_visible()
    assert page.get_by_role("button", name="1998'e dön").is_visible()

    page.locator("#message-input").fill("İnternetin geleceği nasıl?")
    page.get_by_role("button", name="GÖNDER").click()
    page.locator("#chat-log").get_by_text("2030 bağlantısı aktif. Geleceğe hoş geldin.", exact=True).wait_for()
    assert page.locator(".message").count() == 2
    assert not console_errors

    page.wait_for_timeout(800)
    page.evaluate("window.scrollTo(0, 0)")
    page.screenshot(path=ROOT / screenshot_name, full_page=True)

    page.get_by_role("button", name="1998'e dön").click()
    assert page.locator("body").get_attribute("data-era") == "1998"
    assert page.get_by_role("heading", name="RetroChat 98 — Sohbet Odası").is_visible()


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    desktop = browser.new_page(viewport={"width": 1440, "height": 1000})
    verify_page(desktop, "retrochat-desktop.png")

    mobile = browser.new_page(viewport={"width": 375, "height": 812})
    verify_page(mobile, "retrochat-mobile.png")
    browser.close()
