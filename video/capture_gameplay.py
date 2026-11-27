#!/usr/bin/env python3
"""Capture cursor-led gameplay footage for the launch video."""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIR = ROOT / "video"
BUILD_DIR = VIDEO_DIR / "build"
CAPTURE_DIR = BUILD_DIR / "capture"
WIDTH = 1280
HEIGHT = 800
ZOOM = "1.1"

CURSOR_SCRIPT = """
() => {
    if (document.getElementById('launchCursor')) return;
    const style = document.createElement('style');
    style.textContent = `
        #launchCursor {
            position: fixed;
            left: 0;
            top: 0;
            z-index: 2147483647;
            pointer-events: none;
            transform: translate(640px, 420px);
            filter: drop-shadow(0 2px 3px rgb(0 0 0 / 0.24));
        }
        .launch-click-ring {
            position: fixed;
            width: 14px;
            height: 14px;
            margin: -7px 0 0 -7px;
            border: 2px solid #0b57d0;
            border-radius: 999px;
            z-index: 2147483646;
            pointer-events: none;
            animation: launchClickRing 480ms ease-out forwards;
        }
        @keyframes launchClickRing {
            from { opacity: 0.82; transform: scale(0.35); }
            to { opacity: 0; transform: scale(2.8); }
        }
    `;
    document.head.appendChild(style);
    const cursor = document.createElement('div');
    cursor.id = 'launchCursor';
    cursor.innerHTML = `
        <svg width="28" height="36" viewBox="0 0 28 36" aria-hidden="true">
            <path d="M4 2 L4 29 L10.8 23.4 L15.7 34 L19.8 31.8 L14.9 21.4 L23.8 20.2 Z"
                  fill="#202124" stroke="#ffffff" stroke-width="2" stroke-linejoin="round"/>
        </svg>`;
    document.body.appendChild(cursor);
    document.addEventListener('mousemove', (event) => {
        cursor.style.transform = `translate(${event.clientX}px, ${event.clientY}px)`;
    }, { passive: true });
    document.addEventListener('mousedown', (event) => {
        const ring = document.createElement('span');
        ring.className = 'launch-click-ring';
        ring.style.left = `${event.clientX}px`;
        ring.style.top = `${event.clientY}px`;
        document.body.appendChild(ring);
        window.setTimeout(() => ring.remove(), 520);
    }, { passive: true });
}
"""


def serve_repository() -> tuple[ThreadingHTTPServer, threading.Thread, int]:
    handler = partial(SimpleHTTPRequestHandler, directory=str(ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, server.server_address[1]


def chrome_executable() -> str:
    candidates = [
        os.environ.get("CHROME_PATH", ""),
        shutil.which("google-chrome") or "",
        shutil.which("chromium") or "",
        shutil.which("chromium-browser") or "",
        "/home/ubuntu/.local/bin/google-chrome",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError("Chrome or Chromium was not found")


class CaptureDriver:
    def __init__(self, page):
        self.page = page
        self.x = 640.0
        self.y = 420.0
        page.mouse.move(self.x, self.y)

    def wait(self, milliseconds: int) -> None:
        self.page.wait_for_timeout(milliseconds)

    def smooth_move(self, x: float, y: float, duration: float = 0.48) -> None:
        start_x, start_y = self.x, self.y
        steps = max(8, int(duration * 60))
        for index in range(1, steps + 1):
            t = index / steps
            eased = t * t * (3 - 2 * t)
            nx = start_x + (x - start_x) * eased
            ny = start_y + (y - start_y) * eased
            self.page.mouse.move(nx, ny)
            self.page.wait_for_timeout(max(1, int(duration * 1000 / steps)))
        self.x, self.y = x, y

    def move_to(self, selector: str, dx: float = 0.5, dy: float = 0.5, duration: float = 0.48) -> tuple[float, float]:
        locator = self.page.locator(selector)
        locator.scroll_into_view_if_needed()
        self.wait(180)
        box = locator.bounding_box()
        if not box:
            raise RuntimeError(f"Could not measure {selector}")
        x = box["x"] + box["width"] * dx
        y = box["y"] + box["height"] * dy
        self.smooth_move(x, y, duration)
        return x, y

    def click(self, selector: str, duration: float = 0.48) -> None:
        x, y = self.move_to(selector, duration=duration)
        self.wait(140)
        self.page.mouse.down()
        self.wait(80)
        self.page.mouse.up()
        self.wait(180)

    def wheel_down(self, amount: int, steps: int = 22) -> None:
        for _ in range(steps):
            self.page.mouse.wheel(0, amount / steps)
            self.page.wait_for_timeout(28)


def capture() -> dict:
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    for old in CAPTURE_DIR.glob("*.webm"):
        old.unlink()

    server, thread, port = serve_repository()
    scene_times: dict[str, list[float]] = {}
    console_errors: list[str] = []
    started = 0.0

    def elapsed() -> float:
        return time.monotonic() - started

    def start_scene(name: str) -> None:
        scene_times[name] = [elapsed(), 0.0]

    def end_scene(name: str) -> None:
        scene_times[name][1] = elapsed()

    raw_video: Path | None = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chrome_executable(),
                headless=True,
                args=["--disable-dev-shm-usage", "--hide-scrollbars"]
            )
            context = browser.new_context(
                viewport={"width": WIDTH, "height": HEIGHT},
                device_scale_factor=1,
                record_video_dir=str(CAPTURE_DIR),
                record_video_size={"width": WIDTH, "height": HEIGHT}
            )
            page = context.new_page()
            page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)

            started = time.monotonic()
            start_scene("overview")
            page.clock.set_fixed_time("2026-11-27T10:00:00")
            page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            page.evaluate(f"document.documentElement.style.zoom = '{ZOOM}'")
            page.evaluate(CURSOR_SCRIPT)
            page.wait_for_selector("#appLoading", state="hidden", timeout=15000)

            asset_urls = [
                "fonts.css",
                "google-product-tokens.css",
                "google-product-components.css",
                "styles.css",
                "fonts/roboto-latin-400-normal.woff2",
                "fonts/roboto-latin-500-normal.woff2",
                "fonts/roboto-latin-700-normal.woff2",
            ]
            asset_checks = page.evaluate(
                """async (urls) => Promise.all(urls.map(async (url) => {
                    const response = await fetch(url, { cache: 'no-store' });
                    return { url, status: response.status };
                }))""",
                asset_urls
            )
            font_report = page.evaluate(
                """async () => {
                    await document.fonts.ready;
                    return {
                        status: document.fonts.status,
                        roboto400: document.fonts.check('16px Roboto'),
                        roboto500: document.fonts.check('500 16px Roboto'),
                        roboto700: document.fonts.check('700 16px Roboto')
                    };
                }"""
            )
            verification = {
                "assets": asset_checks,
                "fonts": font_report,
                "consoleErrors": console_errors,
                "viewport": {"width": WIDTH, "height": HEIGHT},
                "zoom": ZOOM,
            }
            bad_assets = [item for item in asset_checks if item["status"] != 200]
            missing_fonts = [key for key in ("roboto400", "roboto500", "roboto700") if not font_report.get(key)]
            if bad_assets or missing_fonts or console_errors:
                raise RuntimeError(f"Capture preflight failed: {verification}")

            driver = CaptureDriver(page)
            driver.smooth_move(560, 250, 0.6)
            driver.wait(900)
            driver.smooth_move(705, 360, 0.55)
            driver.wait(900)
            end_scene("overview")

            start_scene("attempt")
            driver.click("#attemptInput", duration=0.55)
            page.keyboard.type("I will expand the left side and compare it with the right side.", delay=64)
            driver.click("#saveAttemptButton", duration=0.55)
            driver.wait(900)
            end_scene("attempt")

            start_scene("hints")
            driver.click("#nextHintButton", duration=0.52)
            driver.wait(1700)
            driver.click("#nextHintButton", duration=0.52)
            driver.wait(2100)
            end_scene("hints")

            start_scene("solutions")
            driver.click("#nextHintButton", duration=0.52)
            driver.wait(1600)
            driver.click("#nextHintButton", duration=0.52)
            driver.wait(900)
            driver.wheel_down(430, steps=24)
            driver.wait(1000)
            driver.wheel_down(520, steps=26)
            driver.wait(1500)
            end_scene("solutions")

            start_scene("solved")
            page.evaluate("window.scrollTo({ top: 0, behavior: 'smooth' })")
            driver.wait(1100)
            driver.click("#markSolvedButton", duration=0.58)
            driver.wait(1800)
            end_scene("solved")

            video_path = Path(page.video.path())
            context.close()
            browser.close()
            if video_path.exists():
                raw_video = video_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    recorded = sorted(CAPTURE_DIR.glob("*.webm"), key=lambda path: path.stat().st_mtime, reverse=True)
    if raw_video is None or not raw_video.exists():
        if not recorded:
            raise RuntimeError("Playwright did not produce a gameplay recording")
        raw_video = recorded[0]

    capture_video = CAPTURE_DIR / "gameplay.webm"
    if raw_video != capture_video:
        shutil.copy2(raw_video, capture_video)

    (CAPTURE_DIR / "scene-times.json").write_text(json.dumps(scene_times, indent=2), encoding="utf-8")
    (CAPTURE_DIR / "capture-verification.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")
    return {
        "video": str(capture_video),
        "sceneTimes": scene_times,
        "verification": verification,
    }


def main() -> int:
    result = capture()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
