"""Provider-agnostic LLM adapter.

One small interface -- `LLMClient.chat()` -- with two implementations:
  - AnthropicClient : closed-source Claude, via the `anthropic` SDK
  - GroqClient      : open-source Llama/Qwen, via Groq's OpenAI-compatible API

Both accept the SAME normalized conversation format and the SAME tool schemas
(agents/tools.py:TOOL_SCHEMAS) and return the SAME `LLMResponse`. That symmetry
is what makes the head-to-head evaluation fair: the graph, prompts, tools, and
policy are identical; only this client is swapped.

Normalized conversation = list of turns:
  {"role": "user", "text": str}
  {"role": "assistant", "text": str|None, "tool_calls": [ToolCall...]}
  {"role": "tool", "tool_call_id": str, "name": str, "content": str}
"""
from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional

# --- Token-bucket rate limiter (Groq free tier = 6000 TPM/org) ----------------
# A leaky/token bucket paces requests *smoothly under* the per-minute token budget
# so we essentially never trip a 429 (far more stable than reacting to 429s after
# the fact). The bucket is module-global because the TPM limit is per-organization
# (shared across models). Set GROQ_TPM_LIMIT to raise it on a paid tier.
_TPM_LIMIT = int(os.environ.get("GROQ_TPM_LIMIT", "5000"))
_RATE = _TPM_LIMIT / 60.0  # tokens refilled per second
_bucket = {"tokens": float(_TPM_LIMIT), "last": time.time()}


def _bucket_refill() -> None:
    now = time.time()
    _bucket["tokens"] = min(_TPM_LIMIT, _bucket["tokens"] + (now - _bucket["last"]) * _RATE)
    _bucket["last"] = now


def _tpm_acquire(estimated_tokens: int) -> None:
    """Reserve `estimated_tokens`, sleeping just enough to stay under budget."""
    est = min(estimated_tokens, _TPM_LIMIT)
    _bucket_refill()
    if _bucket["tokens"] < est:
        time.sleep((est - _bucket["tokens"]) / _RATE)
        _bucket_refill()
    _bucket["tokens"] -= est


def _tpm_reconcile(estimated_tokens: int, actual_tokens: int) -> None:
    """Return over-reserved credit (or debit the extra) once true usage is known."""
    _bucket["tokens"] = max(-_TPM_LIMIT, min(_TPM_LIMIT,
                            _bucket["tokens"] + (estimated_tokens - actual_tokens)))


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""


class LLMClient:
    """Interface. `label` is the short name used in trajectory logs/tables."""

    label: str = "llm"
    provider: str = "?"
    model_id: str = "?"

    def chat(
        self,
        system: str,
        conversation: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Anthropic (closed-source) -- Claude
# ---------------------------------------------------------------------------
class AnthropicClient(LLMClient):
    provider = "anthropic"

    def __init__(self, model_id: Optional[str] = None, label: Optional[str] = None):
        from anthropic import Anthropic

        self.model_id = model_id or os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
        self.label = label or f"claude:{self.model_id}"
        self._client = Anthropic()  # reads ANTHROPIC_API_KEY

    @staticmethod
    def _to_anthropic_tools(tools):
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["parameters"],
            }
            for t in tools
        ]

    @staticmethod
    def _to_anthropic_messages(conversation):
        msgs = []
        for turn in conversation:
            role = turn["role"]
            if role == "user":
                msgs.append({"role": "user", "content": [{"type": "text", "text": turn["text"]}]})
            elif role == "assistant":
                content = []
                if turn.get("text"):
                    content.append({"type": "text", "text": turn["text"]})
                for tc in turn.get("tool_calls", []):
                    content.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                msgs.append({"role": "assistant", "content": content})
            elif role == "tool":
                msgs.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": turn["tool_call_id"],
                        "content": turn["content"],
                    }],
                })
        return msgs

    def chat(self, system, conversation, tools=None, temperature=0.0, max_tokens=1024):
        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "system": system,
            "messages": self._to_anthropic_messages(conversation),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = self._to_anthropic_tools(tools)
        t0 = time.time()
        resp = self._client.messages.create(**kwargs)
        latency = time.time() - t0

        text_parts, tool_calls = [], []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input)))
        return LLMResponse(
            text="\n".join(text_parts).strip(),
            tool_calls=tool_calls,
            latency_s=latency,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            stop_reason=resp.stop_reason or "",
        )


# ---------------------------------------------------------------------------
# Groq (open-source models) -- Llama 3.1/3.3, Qwen2.5, via OpenAI-compatible API
# ---------------------------------------------------------------------------
class GroqClient(LLMClient):
    provider = "groq"

    def __init__(self, model_id: Optional[str] = None, label: Optional[str] = None):
        from openai import OpenAI

        self.model_id = model_id or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.label = label or f"groq:{self.model_id}"
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set -- cannot run the open-source model.")
        self._client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

    @staticmethod
    def _to_openai_tools(tools):
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
            for t in tools
        ]

    @staticmethod
    def _to_openai_messages(system, conversation):
        msgs = [{"role": "system", "content": system}]
        for turn in conversation:
            role = turn["role"]
            if role == "user":
                msgs.append({"role": "user", "content": turn["text"]})
            elif role == "assistant":
                m: dict[str, Any] = {"role": "assistant", "content": turn.get("text") or ""}
                if turn.get("tool_calls"):
                    m["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        }
                        for tc in turn["tool_calls"]
                    ]
                msgs.append(m)
            elif role == "tool":
                msgs.append({
                    "role": "tool",
                    "tool_call_id": turn["tool_call_id"],
                    "content": turn["content"],
                })
        return msgs

    def chat(self, system, conversation, tools=None, temperature=0.0, max_tokens=1024):
        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "messages": self._to_openai_messages(system, conversation),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = self._to_openai_tools(tools)
            kwargs["tool_choice"] = "auto"
        from openai import RateLimitError

        # Proactive pacing: reserve an estimate up front (output cap + rough
        # prompt allowance); 429 backoff remains as a safety net.
        est = max_tokens + 800
        latency = 0.0
        resp = None
        for attempt in range(6):
            _tpm_acquire(est)
            t0 = time.time()  # time ONLY the successful API call (excludes sleeps)
            try:
                resp = self._client.chat.completions.create(**kwargs)
                latency = time.time() - t0
                break
            except RateLimitError:
                if attempt == 5:
                    raise
                time.sleep(min(30.0, 2.0 ** attempt) + random.random())
        actual = (resp.usage.prompt_tokens or 0) + (resp.usage.completion_tokens or 0)
        _tpm_reconcile(est, actual)

        choice = resp.choices[0]
        msg = choice.message
        tool_calls = []
        for tc in (msg.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        usage = resp.usage
        return LLMResponse(
            text=(msg.content or "").strip(),
            tool_calls=tool_calls,
            latency_s=latency,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            stop_reason=choice.finish_reason or "",
        )


def build_client(kind: str, model_id: Optional[str] = None,
                 label: Optional[str] = None) -> LLMClient:
    """Factory used by the runner. kind in {'claude','groq'}."""
    kind = kind.lower()
    if kind in ("claude", "anthropic"):
        return AnthropicClient(model_id=model_id, label=label)
    if kind in ("groq", "llama", "qwen", "oss"):
        return GroqClient(model_id=model_id, label=label)
    raise ValueError(f"unknown model kind: {kind}")
