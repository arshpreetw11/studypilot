"""Thin async client for the Google Gemini REST API (free tier friendly).

Every AI feature in StudyPilot goes through `generate()`. If no key is set, or the
call fails, callers fall back to offline logic so the app never hard-breaks in a
demo.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import httpx

log = logging.getLogger("studypilot.llm")

GEMINI_BASE = os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com").rstrip("/")
GEMINI_URL = GEMINI_BASE + "/v1beta/models/{model}:generateContent"


class LLMError(RuntimeError):
    pass


def api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or None


def model_name() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def enabled() -> bool:
    return api_key() is not None


def _extract_json(text: str) -> Any:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # last resort: grab the outermost JSON object/array
        m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
        if not m:
            raise LLMError("Model did not return JSON")
        return json.loads(m.group(1))


async def generate(
    prompt: str,
    *,
    system: str | None = None,
    json_mode: bool = False,
    temperature: float = 0.4,
    timeout: float = 45.0,
) -> Any:
    """Call Gemini and return text (or parsed JSON when json_mode=True)."""
    key = api_key()
    if not key:
        raise LLMError("GEMINI_API_KEY is not set")

    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    if "2.5-flash" in model_name():
        # skip "thinking" on Flash: these tasks don't need it and it roughly halves latency
        body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                GEMINI_URL.format(model=model_name()),
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=body,
            )
    except httpx.HTTPError as e:
        raise LLMError(f"Network error calling Gemini: {e}") from e

    if r.status_code != 200:
        log.warning("Gemini error %s: %s", r.status_code, r.text[:300])
        raise LLMError(f"Gemini returned HTTP {r.status_code}")

    data = r.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError) as e:
        raise LLMError("Unexpected Gemini response shape") from e

    return _extract_json(text) if json_mode else text.strip()
