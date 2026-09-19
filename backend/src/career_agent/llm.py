"""Model access. Amazon Bedrock by default, with a selectable fallback.

All model output is treated as untrusted data: JSON is parsed defensively and
validated by callers; nothing here grants permissions or performs side effects.
"""

from __future__ import annotations

import json
import os
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
    """A single user turn. Returns (text, usage)."""
    res = chat(system, [{"role": "user", "content": content}], max_tokens=max_tokens,
               temperature=temperature, correlation_id=correlation_id)
    return response_text(res), res.get("usage", {})


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


# ---------------------------------------------------------------------------
# Providers
#
# Bedrock is the model this project is built on and stays the default. This
# account cannot reach it: every runtime call returns ValidationException
# "Operation not allowed", for every model family and both APIs, while the
# control plane answers normally - an account-level hold, not a permissions or
# model-access problem. SageMaker is not a way round it either; endpoint quota
# on this account is 0 for every instance type except ml.t2.medium, which has
# no GPU.
#
# So the provider is selectable. A second provider speaks the OpenAI chat
# completions shape, which most hosted models offer, and its response is
# translated into Bedrock's Converse shape so that every caller - including the
# agent's tool loop - stays written against one format. Switching back when AWS
# lifts the hold is one environment variable, not a code change.
#
# Which engine answered is reported, never hidden: the reply already carries a
# runtime label to the UI, and a demo that quietly swaps its model out is a
# demo that lies.
# ---------------------------------------------------------------------------

_api_key: str | None = None


def openai_key() -> str:
    """Read the key from SSM once per execution environment, never from the repo."""
    global _api_key
    if _api_key is None:
        param = settings().model_api_key_param
        if param:
            import boto3

            try:
                _api_key = boto3.client("ssm").get_parameter(Name=param, WithDecryption=True)["Parameter"]["Value"].strip()
            except Exception as exc:
                raise ModelUnavailable(f"could not read the model API key: {type(exc).__name__}") from exc
        else:
            _api_key = os.environ.get("MODEL_API_KEY", "")
    if not _api_key:
        raise ModelUnavailable("no API key configured for the fallback model provider")
    return _api_key


def _blocks_to_text(content: list[dict]) -> str:
    """Flatten Bedrock content blocks. Documents become their text, not a file."""
    parts = []
    for block in content or []:
        if "text" in block:
            parts.append(block["text"])
        elif "document" in block:
            doc = block["document"]
            raw = (doc.get("source") or {}).get("bytes") or b""
            if isinstance(raw, bytes):
                raw = raw.decode("utf8", "ignore")
            parts.append(f"[{doc.get('name', 'document')}]\n{raw}")
    return "\n\n".join(p for p in parts if p)


def _to_openai_messages(system: str, messages: list[dict]) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}] if system else []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content") or []
        tool_results = [b["toolResult"] for b in content if isinstance(b, dict) and "toolResult" in b]
        tool_uses = [b["toolUse"] for b in content if isinstance(b, dict) and "toolUse" in b]
        if tool_results:
            # Each result is its own message in the OpenAI shape.
            for result in tool_results:
                out.append({"role": "tool", "tool_call_id": result.get("toolUseId", ""),
                            "content": _blocks_to_text(result.get("content") or [])})
            continue
        entry: dict[str, Any] = {"role": "assistant" if role == "assistant" else "user",
                                 "content": _blocks_to_text(content)}
        if tool_uses:
            entry["tool_calls"] = [{"id": u.get("toolUseId", ""), "type": "function",
                                    "function": {"name": u.get("name", ""),
                                                 "arguments": json.dumps(u.get("input") or {})}}
                                   for u in tool_uses]
            entry["content"] = entry["content"] or None
        out.append(entry)
    return out


def _to_bedrock_response(data: dict) -> dict:
    """Translate an OpenAI completion into the Converse response shape."""
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    blocks: list[dict] = []
    text = message.get("content")
    if text:
        blocks.append({"text": text})
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        try:
            arguments = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {}
        blocks.append({"toolUse": {"toolUseId": call.get("id") or fn.get("name", ""),
                                   "name": fn.get("name", ""), "input": arguments}})
    finish = choice.get("finish_reason") or ""
    usage = data.get("usage") or {}
    return {
        "output": {"message": {"role": "assistant", "content": blocks or [{"text": ""}]}},
        "stopReason": {"tool_calls": "tool_use", "length": "max_tokens"}.get(finish, "end_turn"),
        "usage": {"inputTokens": usage.get("prompt_tokens"), "outputTokens": usage.get("completion_tokens")},
    }


def _openai_chat(system: str, messages: list[dict], tools: list[dict] | None,
                 max_tokens: int, temperature: float) -> dict:
    import urllib.error
    import urllib.request

    s = settings()
    payload: dict[str, Any] = {
        "model": s.fallback_model_id,
        "messages": _to_openai_messages(system, messages),
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = [{"type": "function",
                             "function": {"name": t["toolSpec"]["name"],
                                          "description": t["toolSpec"]["description"],
                                          "parameters": t["toolSpec"]["inputSchema"]["json"]}}
                            for t in tools]
    request = urllib.request.Request(
        s.model_api_base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + openai_key()},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=170) as response:  # noqa: S310 - fixed https base from config
            return _to_bedrock_response(json.loads(response.read().decode()))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf8", "ignore")[:300]
        raise ModelUnavailable(f"model provider returned {exc.code}: {detail}") from exc
    except Exception as exc:
        raise ModelUnavailable(f"model provider unreachable: {type(exc).__name__}") from exc


def provider() -> str:
    """Bedrock unless explicitly told otherwise; an unknown value never switches."""
    want = settings().model_provider
    return want if want in ("openai", "anthropic") else "bedrock"


def chat(system: str, messages: list[dict], *, tools: list[dict] | None = None, max_tokens: int = 1500,
         temperature: float = 0.2, correlation_id: str | None = None) -> dict:
    """One call, in Bedrock's Converse response shape, whichever provider answered."""
    started = time.time()
    which = provider()
    try:
        if which == "openai":
            res = _openai_chat(system, messages, tools, max_tokens, temperature)
        elif which == "anthropic":
            res = _anthropic_chat(system, messages, tools, max_tokens, temperature)
        else:
            kwargs: dict[str, Any] = {
                "modelId": settings().model_id,
                "messages": messages,
                "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
            }
            if system:
                kwargs["system"] = [{"text": system}]
            if tools:
                kwargs["toolConfig"] = {"tools": tools}
            res = client().converse(**kwargs)
    except Exception as exc:
        log(logger, "model.error", provider=which, error=type(exc).__name__,
            detail=str(exc)[:300], correlation_id=correlation_id)
        raise ModelUnavailable(str(exc)) from exc
    usage = res.get("usage") or {}
    log(logger, "model.call", provider=which,
        model=settings().model_id if which == "bedrock" else settings().fallback_model_id,
        input_tokens=usage.get("inputTokens"), output_tokens=usage.get("outputTokens"),
        stop_reason=res.get("stopReason"), ms=int((time.time() - started) * 1000),
        correlation_id=correlation_id)
    return res


def response_text(res: dict) -> str:
    parts = ((res.get("output") or {}).get("message") or {}).get("content") or []
    return "".join(p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p)


# ---------------------------------------------------------------------------
# Anthropic Messages, as served by the Bedrock mantle endpoint.
#
# Mantle routes by model: Anthropic models answer on /v1/messages and refuse
# /v1/chat/completions ("does not support the '/v1/chat/completions' API"), and
# OpenAI-shaped models do the reverse. So the wire format has to follow the
# model, not the other way round.
#
# This is still Amazon Bedrock - same account, same key, same endpoint. It is
# only a different route on it.
# ---------------------------------------------------------------------------


def _to_anthropic(system: str, messages: list[dict]) -> dict:
    """Bedrock Converse blocks -> Anthropic content blocks.

    The two are close relatives, which is why this is a rename rather than a
    rewrite: toolUse/toolResult become tool_use/tool_result and text stays text.
    """
    out: list[dict] = []
    for msg in messages:
        blocks: list[dict] = []
        for block in msg.get("content") or []:
            if not isinstance(block, dict):
                continue
            if "text" in block:
                if block["text"]:
                    blocks.append({"type": "text", "text": block["text"]})
            elif "document" in block:
                blocks.append({"type": "text", "text": _blocks_to_text([block])})
            elif "toolUse" in block:
                use = block["toolUse"]
                blocks.append({"type": "tool_use", "id": use.get("toolUseId", ""),
                               "name": use.get("name", ""), "input": use.get("input") or {}})
            elif "toolResult" in block:
                result = block["toolResult"]
                blocks.append({"type": "tool_result", "tool_use_id": result.get("toolUseId", ""),
                               "content": _blocks_to_text(result.get("content") or [])})
        if blocks:
            out.append({"role": "assistant" if msg.get("role") == "assistant" else "user", "content": blocks})
    payload: dict[str, Any] = {"messages": out}
    if system:
        payload["system"] = system
    return payload


def _from_anthropic(data: dict) -> dict:
    """Anthropic response -> the Converse response shape every caller expects."""
    blocks: list[dict] = []
    for block in data.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and block.get("text"):
            blocks.append({"text": block["text"]})
        elif block.get("type") == "tool_use":
            blocks.append({"toolUse": {"toolUseId": block.get("id", ""), "name": block.get("name", ""),
                                       "input": block.get("input") or {}}})
    stop = data.get("stop_reason") or ""
    usage = data.get("usage") or {}
    return {
        "output": {"message": {"role": "assistant", "content": blocks or [{"text": ""}]}},
        "stopReason": {"tool_use": "tool_use", "max_tokens": "max_tokens"}.get(stop, "end_turn"),
        "usage": {"inputTokens": usage.get("input_tokens"), "outputTokens": usage.get("output_tokens")},
    }


def _anthropic_chat(system: str, messages: list[dict], tools: list[dict] | None,
                    max_tokens: int, temperature: float) -> dict:
    import urllib.error
    import urllib.request

    s = settings()
    payload = _to_anthropic(system, messages)
    payload.update({"model": s.fallback_model_id, "max_tokens": max_tokens, "temperature": temperature})
    if tools:
        payload["tools"] = [{"name": t["toolSpec"]["name"], "description": t["toolSpec"]["description"],
                             "input_schema": t["toolSpec"]["inputSchema"]["json"]} for t in tools]
    request = urllib.request.Request(
        s.model_api_base.rstrip("/") + "/v1/messages",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-api-key": openai_key(),
                 "anthropic-version": "2023-06-01"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=170) as response:  # noqa: S310 - fixed https base from config
            return _from_anthropic(json.loads(response.read().decode()))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf8", "ignore")[:300]
        raise ModelUnavailable(f"model provider returned {exc.code}: {detail}") from exc
    except Exception as exc:
        raise ModelUnavailable(f"model provider unreachable: {type(exc).__name__}") from exc
