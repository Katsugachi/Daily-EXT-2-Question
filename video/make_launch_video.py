#!/usr/bin/env python3
"""Run the complete launch-video capture and render pipeline."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURE_VIDEO = ROOT / "video" / "build" / "capture" / "gameplay.webm"


def run(script: str) -> None:
    subprocess.run([sys.executable, str(ROOT / "video" / script)], check=True, cwd=ROOT)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-capture", action="store_true", help="reuse the existing gameplay capture")
    args = parser.parse_args()

    if not args.skip_capture or not CAPTURE_VIDEO.exists():
        run("capture_gameplay.py")
    run("render_launch_video.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
