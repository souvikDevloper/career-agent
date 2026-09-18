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


# Strands calls Bedrock on its own client, so a blocked model arrives as a raw
# botocore error rather than ModelUnavailable. Both doors have to recognise it.
MODEL_DOWN_SIGNS = ("Operation not allowed", "account is currently being verified",
                    "AccessDeniedException", "ThrottlingException", "ServiceUnavailable",
                    "ModelNotReady", "don't have access to the model")


def is_unavailable(exc: BaseException) -> bool:
    """True when the failure is the model being unreachable, not a bug in our request."""
    return isinstance(exc, ModelUnavailable) or any(sign in str(exc) for sign in MODEL_DOWN_SIGNS)


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
        output_tokens=usage.get("outputTokens"), stop_reason=res.get("stopReason"),
        ms=int((time.time() - started) * 1000), correlation_id=correlation_id)
    return text, usage


def _close_truncated(fragment: str) -> str | None:
    """Rebuild JSON that the output token limit cut off mid-value.

    Running out of maxTokens is the ordinary way a good response fails, and the
    damage is always at the tail: a half-written value inside some still-open
    containers. Walking the containers finds the last point that was complete at
    every level, so the fields the model did finish survive without paying for a
    second call to ask for them again.

    Returns None when nothing complete was found - an empty object here would be
    a guess, and the caller's fallback is better than a fabricated answer.
    """
    # frame: [closer, index after the last complete member, seen a member, reading a value]
    frames: list[list] = []
    in_string = escaped = False
    literal = -1  # start of a bare number/true/false/null, or -1

    def end_literal(at: int) -> None:
        nonlocal literal
        if literal >= 0:
            if frames and frames[-1][3]:
                frames[-1][1], frames[-1][2] = at, True
            literal = -1

    for i, ch in enumerate(fragment):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
                if frames and frames[-1][3]:  # a value, not an object key
                    frames[-1][1], frames[-1][2] = i + 1, True
            continue
        if ch == '"':
            end_literal(i)
            in_string = True
        elif ch in "{[":
            end_literal(i)
            # an array's members are always values; an object starts on a key
            frames.append(["}" if ch == "{" else "]", i + 1, False, ch == "["])
        elif ch in "}]":
            end_literal(i)
            if not frames or frames[-1][0] != ch:
                return None  # not truncation - the text is malformed
            frames.pop()
            if frames:
                frames[-1][1], frames[-1][2] = i + 1, True
        elif ch == ":":
            if frames:
                frames[-1][3] = True
        elif ch == ",":
            end_literal(i)
            if frames and frames[-1][0] == "}":
                frames[-1][3] = False  # back to expecting a key
        elif ch not in " \t\r\n" and literal < 0:
            literal = i
    if not frames:
        return None  # balanced already, so truncation is not what broke it
    # The innermost container that finished a member is the furthest point that
    # is clean at every level above it too.
    for depth in range(len(frames) - 1, -1, -1):
        if frames[depth][2]:
            head = fragment[:frames[depth][1]].rstrip().rstrip(",")
            return head + "".join(f[0] for f in reversed(frames[:depth + 1]))
    return None


def extract_json(text: str) -> Any:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    # Take whichever container the text actually opens with, and finish with it
    # before considering the other. Always preferring "{" turns a one-element
    # array into its first element, so a caller that asked for a list silently
    # receives a single object instead.
    pairs = [("{", "}"), ("[", "]")]
    pairs.sort(key=lambda pair: text.find(pair[0]) if pair[0] in text else len(text) + 1)
    for opener, closer in pairs:
        start = text.find(opener)
        if start == -1:
            continue
        fragment = text[start:]
        end = text.rfind(closer)
        if end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        repaired = _close_truncated(fragment)
        if repaired:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass
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
        # Last resort: a second billed call the caller's usage reservation did
        # not account for, so it is logged to keep that cost visible.
        log(logger, "model.json_repair", chars=len(text), correlation_id=correlation_id)
        text2, _ = converse(system, [{"text": f"Convert this into valid JSON only, no prose:\n{text[:6000]}"}],
                            max_tokens=max_tokens, temperature=0, correlation_id=correlation_id)
        return extract_json(text2)
