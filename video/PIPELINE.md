# Daily EXT 2 launch video pipeline

## Creative direction

Make a polished product launch video in a Google product style: generous white space, simple typography, one blue accent colour, soft geometric background shapes, a floating interface card, visible cursor movement, deliberate click feedback, direct section captions, and smooth morphing transitions. The video is for a general audience, so every caption must be plain and factual. Do not use buzzwords, hype, emojis, or narration.

The video must show the real app, not a mockup. The app is served locally with its actual CSS files and self-hosted fonts loaded before capture begins.

## Runtime format

- Canvas: 1920 x 1080 landscape
- Frame rate: 30 fps
- Duration target: 42 to 48 seconds
- Export: H.264 MP4, high quality, silent
- Gameplay capture: Playwright-driven real Chrome recording at 1280 x 800
- Final composition: frame-by-frame Python rendering with Pillow, encoded with FFmpeg
- Type: Roboto, using the same font files loaded by the app

## Storyboard

1. Opening title, 3.4 seconds
   - `Daily EXT 2 Question`
   - `One problem. Every day.`
   - Show the four unlock stages: Hint 1, Hint 2, Walkthrough, Formal solution.
2. Today section
   - Caption: `A new problem every day.`
   - The real loading state resolves into the daily question.
3. Attempt section
   - Caption: `Start with your own reasoning.`
   - A visible cursor enters a short student attempt and saves it.
4. Hints section
   - Caption: `Reveal only the help you need.`
   - The cursor reveals Hint 1 and then Hint 2 in order.
5. Solution section
   - Caption: `Study the complete solution.`
   - The cursor reveals the walkthrough and formal solution, then the page scrolls through them.
6. Progress section
   - Caption: `Finish the day solved.`
   - The cursor marks the question solved and the streak/archive state updates.
7. End card, 4.8 seconds
   - `Daily EXT 2 Question`
   - `A new HSC Extension 2 problem every day.`

## Production steps

1. Serve the repository root locally with a static file server.
2. Open the app in Chrome at 1280 x 800 and use a controlled browser clock so the question date and displayed date agree.
3. Before recording, verify in the browser that:
   - `google-product-tokens.css` returns HTTP 200.
   - `google-product-components.css` returns HTTP 200.
   - `styles.css` returns HTTP 200.
   - Each Roboto font file returns HTTP 200.
   - `document.fonts` reports the required Roboto faces as loaded.
   - No browser console errors block rendering.
4. Inject a cursor layer into the real page so pointer movement and click rings are visible in the capture.
5. Record one continuous browser video while timestamping each gameplay scene boundary.
6. Extract the capture to a 30 fps image sequence.
7. Composite every output frame at 1920 x 1080:
   - geometric light background
   - floating rounded interface card with a soft shadow
   - animated crop, scale, and position morphs between sections
   - animated captions with numbered section labels
   - opening progression strip and closing title card
8. Encode the rendered frames as H.264 MP4 with FFmpeg.
9. Review the exported MP4 at the opening, every section transition, every click moment, the formal solution, the solved state, and the end card.
10. Attach the final MP4 and keep the reproducible scripts in `video/`.

Run the reproducible capture and assembly from the repository root:

```sh
python3 -m venv /tmp/daily-ext2-video
/tmp/daily-ext2-video/bin/pip install -r video/requirements.txt
/tmp/daily-ext2-video/bin/playwright install ffmpeg
/tmp/daily-ext2-video/bin/python video/make_launch_video.py
```

Use `--skip-capture` to reuse the existing gameplay capture while iterating on composition:

```sh
/tmp/daily-ext2-video/bin/python video/make_launch_video.py --skip-capture
```

The final file is written to `video/dist/daily-ext2-launch.mp4` and committed as the reviewable launch asset. Intermediate files in `video/build/` are not committed.

## Acceptance criteria

- The final video is 42 to 48 seconds.
- Every visible caption is plain English and factual.
- The video contains real gameplay footage from the current app.
- The cursor visibly moves to controls and click feedback is visible.
- Scene transitions are smooth and do not overlap captions or duplicate interface cards.
- Roboto renders in both the app footage and the title cards.
- The interface uses the intended Google product CSS, not browser fallback styling.
- The displayed browser date and question date agree.
- No emojis, em dashes, developer notes, test copy, or buzzwords appear.
- The hint progression is understandable without narration.
- The walkthrough, formal solution, solved state, streak, and archive state are all visible.
- The final MP4 plays from the first frame with correct aspect ratio and no black video-only intro.
