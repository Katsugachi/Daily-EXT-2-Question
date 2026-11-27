# Daily EXT 2 launch video pipeline

## Creative direction

Make a concise product launch video in a Google product style: white space, simple typography, one blue accent colour, direct cuts, calm pacing, and no decorative effects. The video is for a general audience, so every caption must be plain and factual. Do not use buzzwords, hype, emojis, or narration.

The video must show the real app, not a mockup. The app must be served locally with its actual CSS files and self-hosted fonts loaded before capture begins.

## Runtime format

- Canvas: 1920 x 1080 landscape
- Frame rate: 30 fps
- Duration target: 40 to 48 seconds
- Export: H.264 MP4, high quality, silent
- Capture: Playwright-driven real Chromium/Chrome browser recording at 1920 x 1080
- Assembly: FFmpeg concat with simple cuts
- Type: Roboto, using the same font files loaded by the app

## Storyboard

1. Title card, 2.5 seconds
   - `Daily EXT 2 Question`
   - `One problem. Every day.`
2. Gameplay capture, about 4 seconds
   - Loading screen resolves into the daily question.
   - Confirm the product CSS and Roboto are visibly loaded before recording.
3. Caption card, 1.5 seconds
   - `Write your attempt first.`
4. Gameplay capture, about 7 seconds
   - Type a short student attempt into the attempt box.
5. Caption card, 1.5 seconds
   - `Use one hint at a time.`
6. Gameplay capture, about 6 seconds
   - Reveal Hint 1, pause, then Hint 2.
   - Keep movement deliberate enough to read the progression.
7. Caption card, 1.5 seconds
   - `Then study the full solution.`
8. Gameplay capture, about 9 seconds
   - Reveal the walkthrough and formal solution.
   - Scroll only enough to show that the full ladder is available.
9. Caption card, 1.5 seconds
   - `Mark it solved.`
10. Gameplay capture, about 4 seconds
    - Mark the question solved and show the streak and archive state.
11. End card, 4 seconds
    - `Daily EXT 2 Question`
    - `A new HSC Extension 2 problem every day.`

## Production steps

1. Serve the repository root locally with a static file server.
2. Open the app in Chromium or Chrome at exactly 1920 x 1080.
3. Before recording, verify in the browser that:
   - `google-product-tokens.css` returns HTTP 200.
   - `google-product-components.css` returns HTTP 200.
   - `styles.css` returns HTTP 200.
   - Each Roboto font file returns HTTP 200.
   - `document.fonts` reports the required Roboto faces as loaded.
   - No browser console errors block rendering.
4. Use a fresh browser profile, or reset local storage before the first take, so the opening state is clean.
5. Record one continuous browser video while timestamping each gameplay scene boundary.
6. Generate title and caption cards as PNG frames with the same Roboto font files.
7. Convert card PNGs to timed MP4 segments with FFmpeg.
8. Normalize every gameplay segment to 1920 x 1080, 30 fps, yuv420p.
9. Concatenate the card and gameplay segments in storyboard order.
10. Review the exported MP4 frame by frame at the start, middle, and end for font rendering, clipping, stale UI state, unreadable text, accidental spoilers, and unwanted developer copy.
11. Attach the final MP4 and keep the reproducible scripts in `video/`.

Run the reproducible capture and assembly from the repository root:

```sh
python3 -m venv /tmp/daily-ext2-video
/tmp/daily-ext2-video/bin/pip install -r video/requirements.txt
/tmp/daily-ext2-video/bin/playwright install ffmpeg
/tmp/daily-ext2-video/bin/python video/make_launch_video.py
```

The final file is written to `video/dist/daily-ext2-launch.mp4` and committed as the reviewable launch asset. Intermediate files in `video/build/` are not committed.

## Acceptance criteria

- The final video is under 50 seconds.
- Every visible caption is plain English and factual.
- The video contains real gameplay footage from the current app.
- Roboto renders in both the app footage and the title cards.
- The interface uses the intended Google product CSS, not browser fallback styling.
- No emojis, em dashes, developer notes, test copy, or buzzwords appear.
- The hint progression is understandable without narration.
- The final MP4 plays from the first frame with correct aspect ratio and no black video-only intro.
