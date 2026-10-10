"""浏览器集成检查：python test_browser.py（需playwright和Edge）。"""
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen
import time
import json
import os
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent


def check_viewer(page, base, expected):
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(base)
    page.wait_for_load_state("networkidle")
    page.locator("#total").filter(has_text=f"{expected:,}").wait_for()
    page.locator("[data-open]").first.click()
    page.locator("#replay").wait_for(state="visible")
    assert page.locator("#board .player").count() == 2
    before = page.locator("#stepLabel").inner_text()
    page.locator("#stepNext").click()
    assert page.locator("#stepLabel").inner_text() != before
    page.locator("#play").click()
    page.wait_for_timeout(850)
    assert page.locator("#play").inner_text() == "暂停播放"
    page.locator("#play").click()
    page.locator("#logSearch").fill("伤害")
    for text in page.locator("#events button").all_inner_texts(): assert "伤害" in text
    page.locator("#logSearch").fill("")
    with page.expect_download() as download:
        page.locator("#downloadDetail").click()
    assert json.loads(Path(download.value.path()).read_text(encoding="utf-8"))["events"]
    page.locator("#winner").select_option("1")
    page.wait_for_load_state("networkidle")
    page.wait_for_function("[...document.querySelectorAll('#gameRows tr td:nth-child(2)')].length > 0 && [...document.querySelectorAll('#gameRows tr td:nth-child(2)')].every(el=>el.textContent.includes('右'))")
    page.locator("#winner").select_option("")
    page.locator("#gameFilter").fill(str(expected))
    page.locator("#filterButton").click()
    page.locator(f'[data-open="{expected}"]').wait_for()
    page.locator(f'[data-open="{expected}"]').click()
    page.locator("#detailTitle").filter(has_text=f"第 {expected} 局").wait_for()
    with page.expect_download() as download:
        page.locator("#export").click()
    csv = Path(download.value.path()).read_text(encoding="utf-8-sig")
    assert len(csv.splitlines()) == expected+1
    page.set_viewport_size({"width":390,"height":844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.set_viewport_size({"width":1440,"height":1000})
    assert not errors, errors
    return errors


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width":1440,"height":1000})
        with urlopen("http://127.0.0.1:8765/api/status") as response:
            latest = json.load(response)["run"]
        check_viewer(page, f"http://127.0.0.1:8765/?run={latest['id']}", latest['params']['games'])
        page.screenshot(path=str(ROOT / "reports" / "界面预览.png"), full_page=True)
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory)/"test.sqlite3"
            process = subprocess.Popen([sys.executable,str(ROOT/"server.py"),"--port","8766","--db",str(db)],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
            try:
                for _ in range(100):
                    try:
                        with urlopen("http://127.0.0.1:8766/api/status",timeout=.3): break
                    except Exception: time.sleep(.1)
                page.goto("http://127.0.0.1:8766")
                page.wait_for_load_state("networkidle")
                page.locator("#left_ai").select_option("v3")
                page.locator("#right_ai").select_option("v2")
                page.locator("#games").fill("6")
                page.locator("#runButton").click()
                page.locator("#total").filter(has_text="6 局").wait_for(timeout=20000)
                page.wait_for_function("!document.querySelector('#runButton').disabled")
                check_viewer(page,"http://127.0.0.1:8766",6)
                with urlopen("http://127.0.0.1:8766/api/status") as response:
                    saved=json.load(response)['run']['params']
                assert saved['left_ai']=='v3' and saved['right_ai']=='v2'
                with urlopen(Request('http://127.0.0.1:8766/api/shutdown',data=b'{}',headers={'Content-Type':'application/json'})) as response:
                    assert json.load(response)['stopping']
                process.wait(timeout=10)
            finally:
                if process.poll() is None: process.terminate()
                process.wait(timeout=10)
        browser.close()
    print("Browser OK: summary, filters, game 10000, replay, search, downloads, mobile, rerun")


if __name__ == "__main__": main()
