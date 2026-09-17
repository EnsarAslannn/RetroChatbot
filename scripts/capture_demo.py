"""Create repeatable portfolio media with scripted, clearly labeled sample replies."""

import json
import shutil
import socket
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "demo"
PORT = 8766


def wait_for_server():
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.1):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Demo sunucusu başlamadı")


def answer(route):
    request = route.request.post_data_json
    era = request["era"]
    if era == "1998":
        reply = "1998'de sohbet için IRC kanallarına bağlanır, e-posta gönderir ya da telefonda konuşurduk."
    else:
        reply = "2058 kurgusunda uzamsal arayüzler ve akıllı yardımcılar iletişimin parçası olabilir."
    body = f"event: chunk\ndata: {json.dumps({'text': reply}, ensure_ascii=False)}\n\nevent: done\ndata: {{}}\n\n"
    route.fulfill(status=200, content_type="text/event-stream", body=body)


def main():
    OUTPUT.mkdir(exist_ok=True)
    server = subprocess.Popen(
        [str(ROOT / ".venv" / "Scripts" / "python.exe"), "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_server()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                record_video_dir=str(OUTPUT), record_video_size={"width": 1280, "height": 900},
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route("**/api/chat/stream", answer)
            page.goto(f"http://127.0.0.1:{PORT}")
            page.wait_for_load_state("networkidle")
            assert page.get_by_role("heading", name="RetroChat 98 — Sohbet Odası").is_visible()
            page.wait_for_timeout(900)
            page.get_by_role("button", name="İki dönemi karşılaştır").click()
            page.locator("#compare-input").fill("Arkadaşlarınla nasıl iletişim kurarsın?")
            page.get_by_role("button", name="Karşılaştır", exact=True).click()
            page.locator("#compare-2058").get_by_text("2058 kurgusunda", exact=False).wait_for()
            page.evaluate("document.activeElement.blur(); window.scrollTo(0, 0)")
            page.screenshot(path=str(OUTPUT / "desktop.png"), full_page=True)
            page.wait_for_timeout(1800)
            page.get_by_role("button", name="Karşılaştırmayı kapat").click()
            page.locator("#message-input").fill("Arkadaşlarınla nasıl iletişim kurarsın?")
            page.locator("#send-button").click()
            page.locator("#chat-log").get_by_text("1998'de sohbet", exact=False).wait_for()
            page.wait_for_timeout(1500)
            page.get_by_role("button", name="Modernleştir").click()
            page.wait_for_timeout(1200)
            page.evaluate("document.activeElement.blur(); window.scrollTo(0, 0)")
            page.screenshot(path=str(OUTPUT / "future.png"), full_page=True)
            video = page.video
            context.close()
            shutil.move(video.path(), OUTPUT / "retrochat-demo.webm")

            mobile = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
            mobile_page = mobile.new_page()
            mobile_page.route("**/api/chat/stream", answer)
            mobile_page.goto(f"http://127.0.0.1:{PORT}")
            mobile_page.get_by_role("button", name="İki dönemi karşılaştır").click()
            mobile_page.locator("#compare-input").fill("İletişim nasıl değişir?")
            mobile_page.get_by_role("button", name="Karşılaştır", exact=True).click()
            mobile_page.locator("#compare-2058").get_by_text("2058 kurgusunda", exact=False).wait_for()
            mobile_page.evaluate("document.activeElement.blur(); window.scrollTo(0, 0)")
            mobile_page.screenshot(path=str(OUTPUT / "mobile.png"), full_page=True)
            assert mobile_page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors, errors
            mobile.close()
            browser.close()
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(OUTPUT / "retrochat-demo.webm"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(OUTPUT / "retrochat-demo.mp4")],
            check=True,
        )
        print("Demo video ve ekran görüntüleri demo/ klasörüne kaydedildi.")
    finally:
        server.terminate()
        server.wait(timeout=5)


if __name__ == "__main__":
    main()
