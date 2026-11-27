# Daily EXT 2 Question

A static, GitHub Pages-deployable daily HSC Mathematics Extension 2 puzzle. The interface follows the Google product visual language and keeps the solution behind a strict progression: Hint 1, Hint 2, Walkthrough, Formal solution.

## How it works

- `index.html`, `app.js`, and the CSS files are the complete static site; there is no build step.
- `data/questions.json` is the generated question archive. Each question has a stable fingerprint, metadata, statement, progressive hints, walkthrough, formal solution, and JavaScript verification metadata.
- The browser caches solved question IDs and fingerprints in `localStorage`, tracks streaks, saves attempts locally, and uses the archive to avoid showing repeated solved variants.
- `.github/workflows/generate-daily-question.yml` runs shortly after midnight Australia/Sydney and commits a new generated question when one does not already exist.
- `.github/workflows/pages.yml` deploys the repository root to GitHub Pages.

## Gemini generation setup

1. Create an AI Studio API key.
2. In the GitHub repository, open **Settings → Secrets and variables → Actions**.
3. Add the repository secret `AI_STUDIO_API_KEY`.
4. Optionally add the repository variable `GEMINI_MODEL` if the exact Gemini 4 Hydrogen API model identifier differs from the default `gemini-4-hydrogen`.
5. Run **Actions → Generate daily question → Run workflow** once to verify the setup.

The generator prompt is date-aware and implements the progressive curriculum rules:

- Phase 1 through 2027: proof, inequalities, combinatorics, polynomials, introductory complex numbers.
- Phase 2 in 2028: induction, harder complex numbers, 3D vectors, harder polynomials, introductory calculus.
- Phase 3 in 2029-2030: full Extension 2 synthesis and Q16-style problems.
- Sundays use the Sunday Curveball mode and introduce one unfamiliar concept with a knowledge-gap explanation.

The generator uses the Gemini Interactions API with web search, high private reasoning/thinking, code execution, and a custom `javascript_eval` tool. Candidate output must be valid JSON, pass verification in a networkless read-only Docker JavaScript sandbox, and have a fingerprint absent from the archive before it is committed. Generated-question commits deploy Pages within the same workflow because token-pushed commits do not trigger the separate push-based Pages workflow.

## Local preview

Serve the repository root with any static server, for example:

```sh
python3 -m http.server 8000
```

Then open `http://localhost:8000`.
