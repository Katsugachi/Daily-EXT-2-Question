#!/usr/bin/env python3
"""Generate and cache a Daily EXT 2 question with the Gemini Interactions API.

The script is dependency-free so the GitHub Actions workflow stays small. It
never prints the API key or model reasoning. Model-supplied JavaScript is run
only inside a locked-down Docker container with no network or mounted files.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_PATH = ROOT / "data" / "questions.json"
TIME_ZONE = ZoneInfo("Australia/Sydney")
DEFAULT_MODEL = "gemini-4-hydrogen"
API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
API_REVISION = "2026-05-20"
JAVASCRIPT_IMAGE = os.environ.get("JAVASCRIPT_SANDBOX_IMAGE", "node:22-alpine")

SYSTEM_PROMPT = """You are the question writer for Daily EXT 2 Question, a daily HSC Mathematics Extension 2 puzzle game.

Audience and progression:
- The student starts in late Year 8 on 26 November 2026 and progresses toward the NSW HSC Mathematics Extension 2 examination in 2030.
- Phase 1 (late 2026-2027): proof, inequalities, combinatorics, pigeonhole principle, polynomials, introductory complex numbers; no calculus.
- Phase 2 (2028): induction, harder complex numbers, 3D vectors, harder polynomials, introductory calculus.
- Phase 3 (2029-2030): full NESA Extension 2 synthesis including integration, mechanics, complex loci, roots of unity, vectors, and Q16-style problems.

Daily rules:
- Monday-Saturday: authentic HSC Extension 2 or Extension 1/2 crossover standard problem calibrated to the current phase.
- Sunday: Sunday Curveball. Use one concept, symbol, or technique likely to be new, while keeping the problem genuinely HSC Extension 2 in character.
- Never repeat or trivially restate an archived question.
- Write clean, rigorous mathematics in LaTeX. Do not use emojis.
- Use web search for syllabus/date/context verification. Use private reasoning or chain-of-thought to construct and check the problem, but never reveal hidden reasoning. Use the JavaScript tool for numerical or algebraic verification where useful.
- The public walkthrough must be a clear line-by-line learning solution, not private chain-of-thought.
- The formal solution must read like a concise HSC marking-guideline solution.
"""

USER_PROMPT_TEMPLATE = """Create one original Daily EXT 2 question for {date_long} ({date_iso}).

Date-driven difficulty:
- Day of week: {weekday}
- Mode: {mode}
- Curriculum phase: {phase}
- Target style: {target}

Archive collision avoidance:
{archive_summary}

Output requirements:
Return exactly one valid JSON object and no Markdown fences. Required keys:
- "topic": concise syllabus topic
- "target": for example "Q12 Style", "Q14 Style", or "Q16 Boss Fight"
- "statement": rigorous problem statement in LaTeX, self-contained and unambiguous
- "hint1": 1-2 sentence conceptual nudge, no algebra steps
- "hint2": exact first line, substitution, or construction, then stop
- "walkthrough": array of 4-8 student-facing steps
- "formalSolution": array of 3-8 concise marking-guideline steps
- "knowledgeGap": first-principles explanation of unfamiliar symbols or techniques; required and non-empty on Sundays, empty string allowed on other days when truly unnecessary
- "finalAnswer": final result or proof conclusion
- "verification": object with key "javascript", whose value is JavaScript code that numerically or algebraically checks representative cases and evaluates to the exact string "ok" when the check passes

Quality constraints:
- The problem must be original, correct, interesting, and solvable with the phase toolkit plus the curveball concept on Sundays.
- The hints must be strictly progressive: hint 1 concept, hint 2 first line, walkthrough guided steps, formal solution polished proof.
- Do not include the solution or hints inside the statement.
- Do not use emojis.
- Before finalizing, use the JavaScript tool to sanity-check algebra or representative cases, then include a compact verification script in the JSON.
"""

JAVASCRIPT_TOOL = {
    "type": "function",
    "name": "javascript_eval",
    "description": "Evaluate a small JavaScript program in an isolated Docker container with no network, files, process access, or require. Use it for representative numerical checks, algebra spot-checks, combinatorial enumeration, and sanity checks. Return a concise value.",
    "parameters": {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "JavaScript source to evaluate. The final completion value should be concise."
            }
        },
        "required": ["source"]
    }
}

QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "target": {"type": "string"},
        "statement": {"type": "string"},
        "hint1": {"type": "string"},
        "hint2": {"type": "string"},
        "walkthrough": {"type": "array", "items": {"type": "string"}},
        "formalSolution": {"type": "array", "items": {"type": "string"}},
        "knowledgeGap": {"type": "string"},
        "finalAnswer": {"type": "string"},
        "verification": {
            "type": "object",
            "properties": {
                "javascript": {"type": "string"}
            },
            "required": ["javascript"]
        }
    },
    "required": [
        "topic",
        "target",
        "statement",
        "hint1",
        "hint2",
        "walkthrough",
        "formalSolution",
        "knowledgeGap",
        "finalAnswer",
        "verification"
    ]
}

REQUIRED_STRING_FIELDS = ["topic", "target", "statement", "hint1", "hint2", "finalAnswer"]
REQUIRED_LIST_FIELDS = ["walkthrough", "formalSolution"]
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U00002700-\U000027BF]")


class GeminiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def read_archive() -> dict[str, Any]:
    if not ARCHIVE_PATH.exists():
        return {"schemaVersion": 1, "questions": []}
    return json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))


def write_archive(payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    ARCHIVE_PATH.write_text(text, encoding="utf-8")


def parse_target_date() -> datetime:
    override = os.environ.get("TARGET_DATE", "").strip()
    if override:
        return datetime.strptime(override, "%Y-%m-%d").replace(tzinfo=TIME_ZONE)
    return datetime.now(TIME_ZONE)


def phase_for_date(date: datetime) -> tuple[str, str]:
    if date.year <= 2027:
        return "Phase 1", "Q12 Style"
    if date.year == 2028:
        return "Phase 2", "Q14 Style"
    return "Phase 3", "Q16 Boss Fight"


def compact_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def fingerprint_for(question: dict[str, Any]) -> str:
    basis = compact_text(str(question.get("statement", ""))) + ":" + compact_text(str(question.get("finalAnswer", "")))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def existing_fingerprints(questions: list[dict[str, Any]]) -> set[str]:
    fingerprints = set()
    for question in questions:
        fingerprint = question.get("fingerprint")
        if fingerprint:
            fingerprints.add(str(fingerprint))
        else:
            fingerprints.add(fingerprint_for(question))
    return fingerprints


def archive_summary(questions: list[dict[str, Any]]) -> str:
    if not questions:
        return "- The archive is currently empty."
    lines = []
    for question in sorted(questions, key=lambda item: item.get("date", ""), reverse=True)[:24]:
        statement = re.sub(r"\s+", " ", str(question.get("statement", ""))).strip()
        lines.append(
            f"- {question.get('date', 'unknown date')}: {question.get('topic', 'unknown topic')} — {statement[:160]}"
        )
    return "\n".join(lines)


def post_interaction(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
            "Api-Revision": os.environ.get("GEMINI_API_REVISION", API_REVISION)
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:1200]
        raise GeminiError(f"Gemini API HTTP {error.code}: {detail}", error.code) from error
    except urllib.error.URLError as error:
        raise GeminiError(f"Gemini API request failed: {error}") from error


def sandbox_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"))[:3000]


def run_javascript(source: str) -> str:
    runner = r"""
const vm = require('vm');
const source = process.env.JS_SOURCE || '';
const logs = [];
const sandbox = {
  console: { log: (...args) => logs.push(args.map(String).join(' ')) },
  Math, JSON, Number, String, Boolean, Array, Object, Date, Set, Map, BigInt
};
try {
  const result = vm.runInNewContext(source, sandbox, { timeout: 1500, displayErrors: true });
  process.stdout.write(JSON.stringify({ ok: true, result: String(result), logs: logs.slice(0, 12) }));
} catch (error) {
  process.stdout.write(JSON.stringify({ ok: false, error: String(error && error.message || error), logs: logs.slice(0, 12) }));
}
"""
    command = [
        "docker", "run", "--rm",
        "--network", "none",
        "--read-only",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", "64",
        "--memory", "128m",
        "--cpus", "0.5",
        "--user", "65534:65534",
        "-e", f"JS_SOURCE={source[:12000].replace(chr(0), '')}",
        JAVASCRIPT_IMAGE,
        "node", "-e", runner
    ]
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=20,
            env={"PATH": os.environ.get("PATH", "")},
            check=False
        )
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        return sandbox_json({"ok": False, "error": f"JavaScript sandbox unavailable or timed out: {error}"})

    stdout = completed.stdout.strip()
    if completed.returncode == 0 and stdout.startswith("{"):
        return stdout[:3000]
    detail = (completed.stderr or stdout or "JavaScript sandbox produced no output").strip()
    return sandbox_json({"ok": False, "error": detail[:1200]})


def generation_config() -> dict[str, Any]:
    config: dict[str, Any] = {
        "temperature": float(os.environ.get("GEMINI_TEMPERATURE", "0.75")),
        "thinking_level": os.environ.get("GEMINI_THINKING_LEVEL", "high")
    }
    max_output = os.environ.get("GEMINI_MAX_OUTPUT_TOKENS", "32768").strip()
    if max_output and max_output != "0":
        config["max_output_tokens"] = int(max_output)
    return config


def interaction_tools() -> list[dict[str, Any]]:
    return [
        {"type": "google_search"},
        {"type": "code_execution"},
        JAVASCRIPT_TOOL
    ]


def interaction_payload(
    input_value: str | list[dict[str, Any]],
    model: str,
    previous_interaction_id: str | None,
    structured: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "system_instruction": SYSTEM_PROMPT,
        "input": input_value,
        "generation_config": generation_config(),
        "tools": interaction_tools(),
        "store": True
    }
    if structured:
        payload["response_format"] = {
            "type": "text",
            "mime_type": "application/json",
            "schema": QUESTION_SCHEMA
        }
    if previous_interaction_id:
        payload["previous_interaction_id"] = previous_interaction_id
    return payload


def output_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text") or response.get("outputText")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    texts: list[str] = []
    for step in reversed(response.get("steps") or []):
        if step.get("type") != "model_output":
            if texts:
                break
            continue
        parts = []
        for content in step.get("content") or []:
            if content.get("type") == "text" and content.get("text"):
                parts.append(str(content["text"]))
        if parts:
            texts.insert(0, "".join(parts))
    return "\n".join(texts).strip()


def function_call_steps(response: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for step in response.get("steps") or [] if step.get("type") == "function_call"]


def function_arguments(step: dict[str, Any]) -> dict[str, Any]:
    arguments = step.get("arguments") or {}
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
            return parsed if isinstance(parsed, dict) else {"source": arguments}
        except json.JSONDecodeError:
            return {"source": arguments}
    return arguments if isinstance(arguments, dict) else {}


def tool_result_step(step: dict[str, Any]) -> dict[str, Any]:
    name = str(step.get("name") or "")
    arguments = function_arguments(step)
    if name == "javascript_eval":
        result = run_javascript(str(arguments.get("source", "")))
    else:
        result = sandbox_json({"ok": False, "error": f"Unknown tool: {name}"})

    result_step: dict[str, Any] = {
        "type": "function_result",
        "name": name,
        "result": [{"type": "text", "text": result}]
    }
    if step.get("id"):
        result_step["call_id"] = step["id"]
    return result_step


def call_interactions_once(prompt: str, api_key: str, model: str, structured: bool) -> str:
    input_value: str | list[dict[str, Any]] = prompt
    previous_interaction_id: str | None = None

    for _round in range(8):
        payload = interaction_payload(input_value, model, previous_interaction_id, structured)
        response = post_interaction(payload, api_key)
        previous_interaction_id = str(response.get("id") or previous_interaction_id or "") or None

        calls = function_call_steps(response)
        if calls:
            input_value = [tool_result_step(step) for step in calls]
            continue

        text = output_text(response)
        if text:
            return text
        status = response.get("status", "unknown")
        raise GeminiError(f"Gemini returned no final text (status: {status})")

    raise GeminiError("Gemini did not finish after the tool-use round limit")


def call_gemini(prompt: str, api_key: str, model: str) -> str:
    errors = []
    for structured in (True, False):
        try:
            return call_interactions_once(prompt, api_key, model, structured)
        except GeminiError as error:
            errors.append(str(error))
            if error.status not in {400, 404}:
                break
    raise GeminiError("Gemini request failed. " + " | ".join(errors[-2:]))


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Model output did not contain a JSON object")
    return json.loads(cleaned[start:end + 1])


def validate_candidate(candidate: dict[str, Any], require_knowledge_gap: bool) -> list[str]:
    errors = []
    for field in REQUIRED_STRING_FIELDS:
        if not isinstance(candidate.get(field), str) or not candidate[field].strip():
            errors.append(f"missing or empty string field: {field}")
    knowledge_gap = candidate.get("knowledgeGap")
    if not isinstance(knowledge_gap, str):
        errors.append("missing or invalid string field: knowledgeGap")
    elif require_knowledge_gap and not knowledge_gap.strip():
        errors.append("missing or empty string field: knowledgeGap")
    for field in REQUIRED_LIST_FIELDS:
        value = candidate.get(field)
        if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
            errors.append(f"missing or invalid array field: {field}")
    verification = candidate.get("verification")
    if not isinstance(verification, dict) or not isinstance(verification.get("javascript"), str) or not verification["javascript"].strip():
        errors.append("missing verification.javascript")
    joined = json.dumps(candidate, ensure_ascii=False)
    if EMOJI_RE.search(joined):
        errors.append("contains emoji")
    statement = candidate.get("statement")
    if isinstance(statement, str) and len(statement) < 30:
        errors.append("statement is too short")
    return errors


def verification_passes(source: str) -> bool:
    output = run_javascript(source)
    try:
        result = json.loads(output)
    except json.JSONDecodeError:
        return False
    return bool(result.get("ok")) and str(result.get("result", "")).strip() == "ok"


def build_prompt(date: datetime, questions: list[dict[str, Any]]) -> str:
    weekday = date.strftime("%A")
    phase, target = phase_for_date(date)
    mode = "Sunday Curveball" if weekday == "Sunday" else "Standard"
    return USER_PROMPT_TEMPLATE.format(
        date_long=f"{weekday}, {date.day} {date.strftime('%B %Y')}",
        date_iso=date.strftime("%Y-%m-%d"),
        weekday=weekday,
        mode=mode,
        phase=phase,
        target=target,
        archive_summary=archive_summary(questions)
    )


def generate_question(date: datetime, questions: list[dict[str, Any]], api_key: str, model: str) -> dict[str, Any]:
    fingerprints = existing_fingerprints(questions)
    errors: list[str] = []
    weekday = date.strftime("%A")
    phase, default_target = phase_for_date(date)
    mode = "Sunday Curveball" if weekday == "Sunday" else "Standard"

    for attempt in range(1, 6):
        prompt = build_prompt(date, questions)
        if errors:
            prompt += "\nPrevious invalid attempts were rejected for these reasons; correct them:\n" + "\n".join(f"- {item}" for item in errors[-8:])
        raw = call_gemini(prompt, api_key, model)
        try:
            candidate = extract_json_object(raw)
        except (ValueError, json.JSONDecodeError) as error:
            errors.append(f"attempt {attempt}: invalid JSON: {error}")
            continue

        validation_errors = validate_candidate(candidate, require_knowledge_gap=mode == "Sunday Curveball")
        if validation_errors:
            errors.extend(f"attempt {attempt}: {item}" for item in validation_errors)
            continue

        fingerprint = fingerprint_for(candidate)
        if fingerprint in fingerprints:
            errors.append(f"attempt {attempt}: duplicate fingerprint")
            continue

        verification_source = candidate["verification"]["javascript"]
        if not verification_passes(verification_source):
            errors.append(f"attempt {attempt}: verification.javascript did not evaluate to the exact string 'ok' in the isolated JavaScript sandbox")
            continue

        candidate["verification"]["status"] = "passed"
        candidate["id"] = f"{date:%Y-%m-%d}-{compact_text(str(candidate.get('topic', 'question')))[:36] or 'question'}"
        candidate["date"] = date.strftime("%Y-%m-%d")
        candidate["weekday"] = weekday
        candidate["phase"] = phase
        candidate["mode"] = mode
        candidate["target"] = candidate.get("target") or default_target
        candidate["fingerprint"] = fingerprint
        candidate["source"] = "gemini"
        candidate["generation"] = {
            "model": model,
            "generatedAt": datetime.now(TIME_ZONE).isoformat(),
            "api": "interactions",
            "tools": ["web_search", "private_reasoning", "javascript_eval", "code_execution"]
        }
        return candidate

    raise RuntimeError("Unable to generate a valid non-duplicate question. " + " | ".join(errors[-10:]))


def main() -> int:
    api_key = os.environ.get("AI_STUDIO_API_KEY", "").strip()
    if not api_key:
        print("AI_STUDIO_API_KEY is not set; skipping generation.", file=sys.stderr)
        return 2

    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    target_date = parse_target_date()
    archive = read_archive()
    questions = archive.setdefault("questions", [])
    target_key = target_date.strftime("%Y-%m-%d")

    if any(question.get("date") == target_key for question in questions):
        print(f"Question for {target_key} already exists; nothing to do.")
        return 0

    question = generate_question(target_date, questions, api_key, model)
    questions.append(question)
    questions.sort(key=lambda item: item.get("date", ""))
    write_archive(archive)
    print(f"Generated {target_key}: {question.get('topic')} ({question.get('mode')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
