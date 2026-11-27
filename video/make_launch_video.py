#!/usr/bin/env python3
"""Capture and assemble the Daily EXT 2 launch video.

Requires the packages in video/requirements.txt, a Chrome/Chromium executable,
and FFmpeg. The script intentionally uses the real static app rather than a
mockup.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIR = ROOT / "video"
BUILD_DIR = VIDEO_DIR / "build"
DIST_DIR = VIDEO_DIR / "dist"
RAW_DIR = BUILD_DIR / "raw"
CARD_DIR = BUILD_DIR / "cards"
SEGMENT_DIR = BUILD_DIR / "segments"
OUTPUT = DIST_DIR / "daily-ext2-launch.mp4"
WIDTH = 1920
HEIGHT = 1080
FPS = 30

TEXT = "#1f1f1f"
SECONDARY = "#5f6368"
BLUE = "#0b57d0"
BACKGROUND = "#ffffff"

FONT_REGULAR = ROOT / "fonts" / "roboto-latin-400-normal.woff2"
FONT_MEDIUM = ROOT / "fonts" / "roboto-latin-500-normal.woff2"
FONT_BOLD = ROOT / "fonts" / "roboto-latin-700-normal.woff2"

CARDS = [
    ("01-title", "Daily EXT 2 Question", "One problem. Every day.", 2.5, True),
    ("02-attempt", "Write your attempt first.", "", 1.5, False),
    ("03-hints", "Use one hint at a time.", "", 1.5, False),
    ("04-solution", "Then study the full solution.", "", 1.5, False),
    ("05-solved", "Mark it solved.", "", 1.5, False),
    ("06-end", "Daily EXT 2 Question", "A new HSC Extension 2 problem every day.", 4.0, True),
]

ASSEMBLY = [
    ("card", "01-title"),
    ("scene", "question"),
    ("card", "02-attempt"),
    ("scene", "attempt"),
    ("card", "03-hints"),
    ("scene", "hints"),
    ("card", "04-solution"),
    ("scene", "solutions"),
    ("card", "05-solved"),
    ("scene", "solved"),
    ("card", "06-end"),
]


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


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


def capture_gameplay() -> tuple[Path, dict[str, list[float]], Path]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for old in RAW_DIR.glob("*.webm"):
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
                record_video_dir=str(RAW_DIR),
                record_video_size={"width": WIDTH, "height": HEIGHT}
            )
            page = context.new_page()
            page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)

            started = time.monotonic()
            start_scene("question")
            page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            page.evaluate("document.documentElement.style.zoom = '1.2'")
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
                        roboto700: document.fonts.check('700 16px Roboto'),
                        faces: Array.from(document.fonts).map((face) => ({
                            family: face.family,
                            weight: face.weight,
                            status: face.status
                        }))
                    };
                }"""
            )
            verification = {
                "assets": asset_checks,
                "fonts": font_report,
                "consoleErrors": console_errors,
            }
            (BUILD_DIR / "asset-verification.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")
            bad_assets = [item for item in asset_checks if item["status"] != 200]
            missing_fonts = [key for key in ("roboto400", "roboto500", "roboto700") if not font_report.get(key)]
            if bad_assets or missing_fonts or console_errors:
                raise RuntimeError(
                    "Capture preflight failed: "
                    f"bad_assets={bad_assets}, missing_fonts={missing_fonts}, console_errors={console_errors}"
                )

            page.wait_for_timeout(3200)
            end_scene("question")

            start_scene("attempt")
            page.locator("#attemptInput").click()
            page.keyboard.type("I will expand the left side and compare it with the right side.", delay=95)
            page.locator("#saveAttemptButton").click()
            page.wait_for_timeout(1000)
            end_scene("attempt")

            start_scene("hints")
            page.locator("#nextHintButton").click()
            page.wait_for_timeout(2600)
            page.locator("#nextHintButton").click()
            page.wait_for_timeout(3000)
            end_scene("hints")

            start_scene("solutions")
            page.locator("#nextHintButton").click()
            page.wait_for_timeout(2200)
            page.locator("#nextHintButton").click()
            page.wait_for_timeout(1500)
            page.evaluate("window.scrollTo({ top: 520, behavior: 'smooth' })")
            page.wait_for_timeout(1600)
            page.evaluate("window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })")
            page.wait_for_timeout(2200)
            end_scene("solutions")

            start_scene("solved")
            page.evaluate("window.scrollTo({ top: 0, behavior: 'smooth' })")
            page.wait_for_timeout(1200)
            page.locator("#markSolvedButton").click()
            page.wait_for_timeout(2600)
            end_scene("solved")

            video_path = Path(page.video.path())
            context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    recorded = sorted(RAW_DIR.glob("*.webm"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not recorded:
        raise RuntimeError("Playwright did not produce a gameplay recording")
    raw_video = recorded[0]
    if video_path.exists() and video_path != raw_video:
        raw_video = video_path

    timing_path = BUILD_DIR / "scene-times.json"
    timing_path.write_text(json.dumps(scene_times, indent=2), encoding="utf-8")
    return raw_video, scene_times, timing_path


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def create_card(filename: str, title: str, subtitle: str, duration: float, large: bool) -> Path:
    CARD_DIR.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(str(FONT_MEDIUM), 88 if large else 68)
    subtitle_font = ImageFont.truetype(str(FONT_REGULAR), 40 if large else 34)

    title_width, title_height = text_size(draw, title, title_font)
    x = (WIDTH - title_width) / 2
    y = 440 if large else 480
    draw.text((x, y), title, font=title_font, fill=TEXT)

    if subtitle:
        subtitle_width, _ = text_size(draw, subtitle, subtitle_font)
        draw.text(((WIDTH - subtitle_width) / 2, y + 126), subtitle, font=subtitle_font, fill=SECONDARY)

    accent_width = 96 if large else 72
    accent_x = (WIDTH - accent_width) / 2
    accent_y = y - 74 if large else y - 62
    draw.rounded_rectangle(
        (accent_x, accent_y, accent_x + accent_width, accent_y + 10),
        radius=5,
        fill=BLUE
    )

    path = CARD_DIR / f"{filename}.png"
    image.save(path)
    return path


def make_card_video(card: Path, duration: float) -> Path:
    output = SEGMENT_DIR / f"{card.stem}.mp4"
    run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-framerate", str(FPS),
        "-t", f"{duration:.2f}",
        "-i", str(card),
        "-vf", f"scale={WIDTH}:{HEIGHT},fps={FPS},format=yuv420p",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-an",
        str(output)
    ])
    return output


def make_gameplay_segment(raw_video: Path, name: str, start: float, end: float) -> Path:
    output = SEGMENT_DIR / f"scene-{name}.mp4"
    duration = max(0.1, end - start)
    run([
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-t", f"{duration:.3f}",
        "-i", str(raw_video),
        "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},fps={FPS},format=yuv420p",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-an",
        str(output)
    ])
    return output


def assemble(raw_video: Path, scene_times: dict[str, list[float]]) -> Path:
    SEGMENT_DIR.mkdir(parents=True, exist_ok=True)
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    for old in SEGMENT_DIR.glob("*.mp4"):
        old.unlink()

    card_paths = {
        filename: create_card(filename, title, subtitle, duration, large)
        for filename, title, subtitle, duration, large in CARDS
    }
    card_durations = {filename: duration for filename, _title, _subtitle, duration, _large in CARDS}
    segments: list[Path] = []

    for kind, name in ASSEMBLY:
        if kind == "card":
            segments.append(make_card_video(card_paths[name], card_durations[name]))
        else:
            start, end = scene_times[name]
            segments.append(make_gameplay_segment(raw_video, name, start, end))

    concat_file = BUILD_DIR / "concat.txt"
    concat_file.write_text("".join(f"file '{segment}'\n" for segment in segments), encoding="utf-8")
    run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-an",
        str(OUTPUT)
    ])
    return OUTPUT


def main() -> int:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    raw_video, scene_times, timing_path = capture_gameplay()
    output = assemble(raw_video, scene_times)
    print(json.dumps({
        "output": str(output),
        "rawVideo": str(raw_video),
        "sceneTimes": str(timing_path),
        "verification": str(BUILD_DIR / "asset-verification.json")
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
