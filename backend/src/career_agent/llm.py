"""Amazon Bedrock (Nova 2 Lite) access through the Converse API.

All model output is treated as untrusted data: JSON is parsed defensively and
validated by callers; nothing here grants permissions or performs side effects.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from .config import settings
from .util import get_logger, log

logger = get_logger("llm")

_client = None


class ModelUnavailable(Exception):
    pass


def client():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config

        _client = boto3.client("bedrock-runtime", region_name=settings().region,
                               config=Config(retries={"max_attempts": 3, "mode": "adaptive"}, read_timeout=120))
    return _client


def converse(system: str, content: list[dict], *, max_tokens: int = 1500, temperature: float = 0.2,
             correlation_id: str | None = None) -> tuple[str, dict]:
    started = time.time()
    try:
        res = client().converse(
            modelId=settings().model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": content}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )
    except Exception as exc:  # botocore ClientError, throttling, access denied
        log(logger, "model.error", error=type(exc).__name__, detail=str(exc)[:300], correlation_id=correlation_id)
        raise ModelUnavailable(str(exc)) from exc
    parts = res.get("output", {}).get("message", {}).get("content", [])
    text = "".join(p.get("text", "") for p in parts if "text" in p)
    usage = res.get("usage", {})
    log(logger, "model.call", model=settings().model_id, input_tokens=usage.get("inputTokens"),
        output_tokens=usage.get("outputTokens"), ms=int((time.time() - started) * 1000), correlation_id=correlation_id)
    return text, usage


def extract_json(text: str) -> Any:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("model did not return JSON")


def json_call(system: str, prompt: str, *, documents: list[dict] | None = None, max_tokens: int = 2000,
              correlation_id: str | None = None) -> Any:
    content: list[dict] = []
    for doc in documents or []:
        content.append({"document": doc})
    content.append({"text": prompt + "\n\nRespond with JSON only."})
    text, _ = converse(system, content, max_tokens=max_tokens, temperature=0.1, correlation_id=correlation_id)
    try:
        return extract_json(text)
    except ValueError:
        text2, _ = converse(system, [{"text": f"Convert this into valid JSON only, no prose:\n{text[:6000]}"}],
                            max_tokens=max_tokens, temperature=0, correlation_id=correlation_id)
        return extract_json(text2)
