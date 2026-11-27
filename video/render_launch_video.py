#!/usr/bin/env python3
"""Render the polished Daily EXT 2 launch video from captured gameplay."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIR = ROOT / "video"
BUILD_DIR = VIDEO_DIR / "build"
CAPTURE_DIR = BUILD_DIR / "capture"
FRAMES_DIR = BUILD_DIR / "capture-frames"
DIST_DIR = VIDEO_DIR / "dist"
OUTPUT = DIST_DIR / "daily-ext2-launch.mp4"

OUT_W = 1920
OUT_H = 1080
FPS = 30
OPENING_DURATION = 3.4
END_DURATION = 4.8
TRANSITION = 0.45
SCENE_PAD = 1.2

TEXT = "#202124"
SECONDARY = "#5f6368"
BLUE = "#0b57d0"
BLUE_SOFT = "#e8f0fe"
SURFACE = "#f8f9fa"
LINE = "#dadce0"

FONT_REGULAR = ROOT / "fonts" / "roboto-latin-400-normal.woff2"
FONT_MEDIUM = ROOT / "fonts" / "roboto-latin-500-normal.woff2"
FONT_BOLD = ROOT / "fonts" / "roboto-latin-700-normal.woff2"


@lru_cache(maxsize=None)
def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def text_size(draw: ImageDraw.ImageDraw, text: str, used_font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=used_font)
    return box[2] - box[0], box[3] - box[1]


def wrap_lines(draw: ImageDraw.ImageDraw, text: str, used_font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if text_size(draw, candidate, used_font)[0] <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def opacity_layer(layer: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 0.999:
        return layer
    result = layer.copy()
    alpha = result.getchannel("A").point(lambda value: int(value * clamp(opacity)))
    result.putalpha(alpha)
    return result


def paste_layer(base: Image.Image, layer: Image.Image, xy: tuple[int, int], opacity: float = 1.0) -> None:
    if opacity <= 0:
        return
    base.alpha_composite(opacity_layer(layer, opacity), xy)


def make_background() -> Image.Image:
    image = Image.new("RGBA", (OUT_W, OUT_H), SURFACE)
    draw = ImageDraw.Draw(image)

    draw.ellipse((1430, -310, 2050, 310), fill="#eef4fd")
    draw.ellipse((-280, 790, 390, 1260), fill="#f1f3f4")
    draw.rounded_rectangle((1540, 760, 1970, 1150), radius=54, fill="#f1f3f4")

    for x in range(1470, 1900, 34):
        for y in range(112, 385, 34):
            if (x - 1660) ** 2 / 260**2 + (y - 230) ** 2 / 155**2 < 1:
                draw.ellipse((x, y, x + 4, y + 4), fill="#d2dbe8")

    for x in range(80, 430, 34):
        for y in range(780, 1030, 34):
            if (x - 230) ** 2 / 180**2 + (y - 910) ** 2 / 130**2 < 1:
                draw.ellipse((x, y, x + 4, y + 4), fill="#dde0e4")

    draw.rounded_rectangle((96, 96, 178, 102), radius=3, fill=BLUE)
    return image


BACKGROUND = make_background()


@lru_cache(maxsize=64)
def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


@lru_cache(maxsize=32)
def window_shadow(size: tuple[int, int], radius: int) -> tuple[Image.Image, int]:
    width, height = size
    pad = 54
    layer = Image.new("RGBA", (width + pad * 2, height + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(
        (pad, pad - 8, pad + width, pad + height - 8),
        radius=radius,
        fill=(32, 33, 36, 54)
    )
    return layer.filter(ImageFilter.GaussianBlur(24)), pad


def paste_window(
    base: Image.Image,
    frame: Image.Image,
    crop: tuple[int, int, int, int],
    target_width: int,
    x: int,
    y: int,
    opacity: float = 1.0
) -> None:
    cropped = frame.crop(crop)
    ratio = cropped.height / cropped.width
    width = int(round(target_width))
    height = int(round(width * ratio))
    resized = cropped.resize((width, height), Image.Resampling.LANCZOS).convert("RGBA")
    radius = 28
    mask = rounded_mask((width, height), radius)
    resized.putalpha(mask)
    if opacity < 1:
        resized = opacity_layer(resized, opacity)

    shadow, pad = window_shadow((width, height), radius)
    base.alpha_composite(shadow, (x - pad, y - pad + 16))
    base.alpha_composite(resized, (x, y))


def draw_tracked(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    used_font: ImageFont.FreeTypeFont,
    fill: str,
    tracking: int = 2
) -> int:
    x, y = xy
    for character in text:
        draw.text((x, y), character, font=used_font, fill=fill)
        x += text_size(draw, character, used_font)[0] + tracking
    return x


def make_side_caption(label: str, heading: str, subheading: str) -> Image.Image:
    layer = Image.new("RGBA", (650, 460), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    label_font = font(str(FONT_MEDIUM), 22)
    heading_font = font(str(FONT_MEDIUM), 62)
    body_font = font(str(FONT_REGULAR), 29)

    draw.rounded_rectangle((0, 0, 58, 7), radius=3, fill=BLUE)
    draw_tracked(draw, (0, 30), label.upper(), label_font, BLUE, tracking=3)

    y = 86
    for line in wrap_lines(draw, heading, heading_font, 585):
        draw.text((0, y), line, font=heading_font, fill=TEXT)
        y += 68

    y += 18
    for line in wrap_lines(draw, subheading, body_font, 520):
        draw.text((0, y), line, font=body_font, fill=SECONDARY)
        y += 40
    return layer


def make_center_text(title: str, subtitle: str, large: bool = True) -> Image.Image:
    layer = Image.new("RGBA", (OUT_W, 330), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    title_font = font(str(FONT_MEDIUM), 92 if large else 82)
    subtitle_font = font(str(FONT_REGULAR), 39)
    title_width, _ = text_size(draw, title, title_font)
    subtitle_width, _ = text_size(draw, subtitle, subtitle_font)
    draw.text(((OUT_W - title_width) / 2, 34), title, font=title_font, fill=TEXT)
    draw.text(((OUT_W - subtitle_width) / 2, 164), subtitle, font=subtitle_font, fill=SECONDARY)
    return layer


def make_progression_strip() -> Image.Image:
    labels = ["Hint 1", "Hint 2", "Walkthrough", "Formal solution"]
    layer = Image.new("RGBA", (900, 82), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    label_font = font(str(FONT_REGULAR), 21)
    centers = [80, 270, 490, 760]
    for index in range(len(centers) - 1):
        draw.line((centers[index] + 8, 18, centers[index + 1] - 8, 18), fill=LINE, width=2)
    for index, (center, label) in enumerate(zip(centers, labels)):
        fill = BLUE if index == 0 else "#9aa0a6"
        draw.ellipse((center - 7, 11, center + 7, 25), fill=fill)
        width, _ = text_size(draw, label, label_font)
        draw.text((center - width / 2, 42), label, font=label_font, fill=SECONDARY)
    return layer


PROGRESSION = make_progression_strip()


class SourceVideo:
    def __init__(self) -> None:
        self.video = CAPTURE_DIR / "gameplay.webm"
        if not self.video.exists():
            raise RuntimeError("Captured gameplay does not exist. Run video/capture_gameplay.py first.")
        self.extract_frames()
        self.frames = sorted(FRAMES_DIR.glob("frame-*.jpg"))
        if not self.frames:
            raise RuntimeError("No capture frames were extracted")
        self.duration = len(self.frames) / FPS
        self._cache: dict[int, Image.Image] = {}

    def extract_frames(self) -> None:
        marker = FRAMES_DIR / ".source-mtime"
        current_mtime = str(self.video.stat().st_mtime)
        if marker.exists() and marker.read_text(encoding="utf-8") == current_mtime:
            return
        if FRAMES_DIR.exists():
            shutil.rmtree(FRAMES_DIR)
        FRAMES_DIR.mkdir(parents=True)
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(self.video),
            "-vf", f"fps={FPS}",
            "-q:v", "2",
            str(FRAMES_DIR / "frame-%05d.jpg")
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        marker.write_text(current_mtime, encoding="utf-8")

    def frame_at(self, seconds: float) -> Image.Image:
        index = int(round(seconds * FPS)) + 1
        index = max(1, min(len(self.frames), index))
        if index not in self._cache:
            if len(self._cache) > 90:
                self._cache.clear()
            self._cache[index] = Image.open(self.frames[index - 1]).convert("RGB")
        return self._cache[index]


SCENE_ORDER = ["overview", "attempt", "hints", "solutions", "solved"]

SCENE_COPY = {
    "overview": ("01 / Today", "A new problem every day.", "The question loads before the page appears."),
    "attempt": ("02 / Attempt", "Start with your own reasoning.", "Save it before opening the hints."),
    "hints": ("03 / Hints", "Reveal only the help you need.", "Each step unlocks in order."),
    "solutions": ("04 / Solution", "Study the complete solution.", "Follow the walkthrough, then read the formal proof."),
    "solved": ("05 / Progress", "Finish the day solved.", "The streak and archive update immediately."),
}

SCENE_CROPS = {
    "overview": (0, 0, 1280, 800),
    "attempt": (0, 30, 900, 800),
    "hints": (0, 330, 900, 800),
    "solutions": (0, 110, 900, 800),
    "solved": (0, 0, 1280, 800),
}

SCENE_LAYOUTS = {
    "overview": {"width": 1380, "x": 270, "y": 130, "caption": (110, 58), "side": False},
    "attempt": {"width": 1080, "x": 780, "y": 70, "caption": (120, 260), "side": True},
    "hints": {"width": 1080, "x": 780, "y": 250, "caption": (120, 300), "side": True},
    "solutions": {"width": 1080, "x": 780, "y": 120, "caption": (120, 270), "side": True},
    "solved": {"width": 1180, "x": 680, "y": 170, "caption": (120, 300), "side": True},
}


def build_scenes(scene_times: dict[str, list[float]], source_duration: float) -> tuple[list[dict], float]:
    scenes: list[dict] = []
    output_start = OPENING_DURATION
    for key in SCENE_ORDER:
        source_start, source_end = scene_times[key]
        if key == "overview":
            source_start = max(source_start, 0.5)
        source_end = min(source_end, source_duration - 0.04)
        source_length = max(0.2, source_end - source_start)
        duration = source_length + SCENE_PAD
        scenes.append({
            "key": key,
            "source_start": source_start,
            "source_end": source_end,
            "source_length": source_length,
            "duration": duration,
            "output_start": output_start,
            "output_end": output_start + duration,
        })
        output_start += duration
    return scenes, output_start


class LaunchRenderer:
    def __init__(self) -> None:
        self.source = SourceVideo()
        scene_times = json.loads((CAPTURE_DIR / "scene-times.json").read_text(encoding="utf-8"))
        self.scenes, self.end_start = build_scenes(scene_times, self.source.duration)
        self.total_duration = self.end_start + END_DURATION
        self.caption_layers = {
            key: make_side_caption(*SCENE_COPY[key])
            for key in SCENE_ORDER
        }
        self.opening_title = make_center_text("Daily EXT 2 Question", "One problem. Every day.")
        self.end_title = make_center_text("Daily EXT 2 Question", "A new HSC Extension 2 problem every day.")

    def scene_source_time(self, scene: dict, local_time: float) -> float:
        intro = 0.55
        outro = 0.3
        movable = max(0.1, scene["duration"] - intro - outro)
        progress = clamp((local_time - intro) / movable)
        return scene["source_start"] + progress * scene["source_length"]

    def paste_caption(self, base: Image.Image, key: str, opacity: float, y_offset: int = 0) -> None:
        layer = self.caption_layers[key]
        layout = SCENE_LAYOUTS[key]
        x, y = layout["caption"]
        if layout["side"]:
            paste_layer(base, layer, (x, y + y_offset), opacity)
        else:
            small = layer.crop((0, 0, 650, 66))
            paste_layer(base, small, (x, y + y_offset), opacity)

    def render_caption(self, base: Image.Image, scene: dict, local_time: float) -> None:
        enter = ease(local_time / 0.72)
        exit_alpha = clamp((scene["duration"] - local_time) / 0.3)
        opacity = enter * exit_alpha
        y_offset = int((1 - enter) * 28)
        self.paste_caption(base, scene["key"], opacity, y_offset)

    def window_state(self, key: str, push: float) -> tuple[tuple[int, int, int, int], float, float, float]:
        layout = SCENE_LAYOUTS[key]
        width = layout["width"] * push
        x = layout["x"] - (width - layout["width"]) / 2
        return SCENE_CROPS[key], width, x, float(layout["y"])

    def render_scene_only(self, scene_index: int, local_time: float, morph: bool = False) -> Image.Image:
        scene = self.scenes[scene_index]
        key = scene["key"]
        base = BACKGROUND.copy()

        progress = ease(local_time / scene["duration"])
        enter = ease(local_time / 0.65)
        push = 1.0 + 0.018 * progress
        crop, target_width, x, y = self.window_state(key, push)
        caption_opacity: float | None = None
        previous_key: str | None = None
        previous_opacity = 0.0

        if morph and scene_index > 0:
            morph_progress = ease(local_time / TRANSITION)
            previous = self.scenes[scene_index - 1]
            previous_key = previous["key"]
            previous_crop, previous_width, previous_x, previous_y = self.window_state(previous_key, 1.018)
            crop = tuple(int(round(previous_crop[index] + (crop[index] - previous_crop[index]) * morph_progress)) for index in range(4))
            target_width = previous_width + (target_width - previous_width) * morph_progress
            x = previous_x + (x - previous_x) * morph_progress
            y = previous_y + (y - previous_y) * morph_progress
            previous_opacity = 1.0 - clamp(morph_progress / 0.35)
            caption_opacity = clamp((morph_progress - 0.38) / 0.62) * ease(local_time / 0.72)
        else:
            x += (1 - enter) * 34

        frame = self.source.frame_at(self.scene_source_time(scene, local_time))
        paste_window(base, frame, crop, int(round(target_width)), int(round(x)), int(round(y)))

        if previous_key:
            morph_progress = ease(local_time / TRANSITION)
            self.paste_caption(base, previous_key, previous_opacity, -int(morph_progress * 34))
        if caption_opacity is None:
            self.render_caption(base, scene, local_time)
        else:
            morph_progress = ease(local_time / TRANSITION)
            self.paste_caption(base, key, caption_opacity, int((1 - morph_progress) * 34))
        return base

    def render_gameplay(self, seconds: float) -> Image.Image:
        scene_index = 0
        for index, scene in enumerate(self.scenes):
            if scene["output_start"] <= seconds < scene["output_end"]:
                scene_index = index
                break
        else:
            scene_index = len(self.scenes) - 1

        scene = self.scenes[scene_index]
        local_time = seconds - scene["output_start"]
        return self.render_scene_only(scene_index, local_time, morph=scene_index > 0 and local_time < TRANSITION)

    def render_opening(self, seconds: float) -> Image.Image:
        base = BACKGROUND.copy()
        draw = ImageDraw.Draw(base)

        line_progress = ease(seconds / 0.75)
        line_width = int(112 * line_progress)
        draw.rounded_rectangle(
            ((OUT_W - 112) / 2, 315, (OUT_W - 112) / 2 + line_width, 325),
            radius=5,
            fill=BLUE
        )

        title_alpha = ease((seconds - 0.38) / 0.85)
        title_y = 365 + int((1 - title_alpha) * 28)
        paste_layer(base, self.opening_title, (0, title_y), title_alpha)

        strip_alpha = ease((seconds - 1.55) / 0.8)
        strip_y = 780 + int((1 - strip_alpha) * 20)
        paste_layer(base, PROGRESSION, ((OUT_W - PROGRESSION.width) // 2, strip_y), strip_alpha)
        return base

    def render_end(self, seconds: float) -> Image.Image:
        base = BACKGROUND.copy()
        draw = ImageDraw.Draw(base)
        alpha = ease(seconds / 0.7)
        line_width = int(112 * alpha)
        draw.rounded_rectangle(
            ((OUT_W - 112) / 2, 352, (OUT_W - 112) / 2 + line_width, 362),
            radius=5,
            fill=BLUE
        )
        paste_layer(base, self.end_title, (0, 392 + int((1 - alpha) * 20)), alpha)
        return base

    def render(self, seconds: float) -> Image.Image:
        if seconds < OPENING_DURATION:
            return self.render_opening(seconds)

        if seconds < self.end_start:
            image = self.render_gameplay(seconds)
            opening_elapsed = seconds - OPENING_DURATION
            if opening_elapsed < 0.24:
                opening = self.render_opening(OPENING_DURATION)
                return Image.blend(opening, BACKGROUND, ease(opening_elapsed / 0.24))
            if opening_elapsed < 0.58:
                alpha = ease((opening_elapsed - 0.24) / 0.34)
                return Image.blend(BACKGROUND, image, alpha)
            return image

        end_seconds = seconds - self.end_start
        end_image = self.render_end(end_seconds)
        if end_seconds < 0.24:
            last_scene = self.scenes[-1]
            last_image = self.render_scene_only(len(self.scenes) - 1, last_scene["duration"] - 0.02)
            return Image.blend(last_image, BACKGROUND, ease(end_seconds / 0.24))
        if end_seconds < 0.58:
            alpha = ease((end_seconds - 0.24) / 0.34)
            return Image.blend(BACKGROUND, end_image, alpha)
        return end_image


def render_preview(renderer: LaunchRenderer, path: Path) -> None:
    fractions = [0.03, 0.11, 0.2, 0.3, 0.42, 0.55, 0.68, 0.82, 0.95]
    tiles = []
    for fraction in fractions:
        frame = renderer.render(renderer.total_duration * fraction).convert("RGB")
        frame.thumbnail((640, 360), Image.Resampling.LANCZOS)
        tiles.append(frame.copy())
    preview = Image.new("RGB", (1920, 1080), "white")
    for index, tile in enumerate(tiles):
        preview.paste(tile, ((index % 3) * 640, (index // 3) * 360))
    preview.save(path)


def encode_video(renderer: LaunchRenderer, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{OUT_W}x{OUT_H}",
        "-r", str(FPS),
        "-i", "-",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "17",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-an",
        str(output)
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    assert process.stdin is not None
    frame_count = int(math.ceil(renderer.total_duration * FPS))
    try:
        for frame_index in range(frame_count):
            seconds = frame_index / FPS
            frame = renderer.render(seconds).convert("RGB")
            process.stdin.write(frame.tobytes())
            if frame_index % 150 == 0:
                print(f"rendered {frame_index}/{frame_count}", flush=True)
        process.stdin.close()
        return_code = process.wait()
    except BrokenPipeError as error:
        raise RuntimeError("FFmpeg stopped while frames were being written") from error
    if return_code != 0:
        raise RuntimeError(f"FFmpeg failed with exit code {return_code}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", type=Path, help="write a 3x3 preview contact sheet instead of encoding")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    renderer = LaunchRenderer()
    if args.preview:
        render_preview(renderer, args.preview)
        print(args.preview)
    else:
        encode_video(renderer, args.output)
        print(args.output)
    print(json.dumps({"duration": renderer.total_duration, "fps": FPS, "width": OUT_W, "height": OUT_H}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
