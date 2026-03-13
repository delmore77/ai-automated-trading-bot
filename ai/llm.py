"""
Generic LLM client (OpenAI-compatible API).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import httpx

from config import settings

logger = logging.getLogger(__name__)


def llm_chat(
    messages: List[Dict[str, str]],
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
) -> str:
    """
    Call OpenAI-compatible chat API. Returns assistant content or raises on error.
    """
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY not set")
    model = model or settings.llm_model
    url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    return (choice.get("message") or {}).get("content") or ""


def llm_json(messages: List[Dict[str, str]], **kwargs: Any) -> Dict[str, Any]:
    """Call LLM and parse first message as JSON. Returns dict or empty dict on parse error."""
    content = llm_chat(messages, **kwargs)
    content = content.strip()
    if content.startswith("```"):
        for sep in ("```json", "```"):
            if content.startswith(sep):
                content = content[len(sep):].strip()
        if content.endswith("```"):
            content = content[:-3].strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning("LLM response not valid JSON: %s", content[:200])
        return {}
