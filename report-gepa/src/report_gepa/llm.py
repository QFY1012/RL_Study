"""OpenAI-compatible chat calls, configured from ~/.config/report-gepa/llm.env.

Responses are streamed: long generations through the relay can be cut off when
the whole reply is held until the end. A reply with no finish reason, or one cut
by the length limit, is reported as incomplete so callers do not score half a page.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

ENV_FILE = Path.home() / ".config" / "report-gepa" / "llm.env"


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    # an exported variable wins over the file, so a run can switch endpoints without editing it
    for key in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


@dataclass
class Reply:
    text: str
    reasoning: str
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    seconds: float

    @property
    def complete(self) -> bool:
        return self.finish_reason == "stop"


class LLM:
    def __init__(self, model: str | None = None, env: dict[str, str] | None = None):
        env = env if env is not None else load_env()
        missing = [k for k in ("LLM_API_KEY", "LLM_BASE_URL") if not env.get(k)]
        if missing:
            raise RuntimeError(f"{ENV_FILE} is missing {', '.join(missing)}")
        self.model = model or env.get("LLM_MODEL")
        if not self.model:
            raise RuntimeError("no model given and LLM_MODEL is not set")
        self.client = OpenAI(api_key=env["LLM_API_KEY"], base_url=env["LLM_BASE_URL"], timeout=900, max_retries=0)

    def chat(self, messages: list[dict], *, retries: int = 3, **params) -> Reply:
        """One chat completion; retries on transport errors and on replies that stop early."""
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            start = time.monotonic()
            try:
                reply = self._stream(messages, start, **params)
            except Exception as e:  # noqa: BLE001 - any transport failure is retried the same way
                last_error = e
            else:
                if reply.complete or attempt == retries:
                    return reply
                last_error = RuntimeError(f"reply incomplete (finish_reason={reply.finish_reason})")
            time.sleep(min(2 ** attempt * 2, 30))
        raise RuntimeError(f"chat failed after {retries + 1} attempts: {last_error}")

    def _stream(self, messages: list[dict], start: float, **params) -> Reply:
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            **params,
        )
        text, reasoning = [], []
        finish_reason = None
        usage = None
        for chunk in stream:
            if chunk.usage is not None:
                usage = chunk.usage
            for choice in chunk.choices:
                delta = choice.delta
                if delta.content:
                    text.append(delta.content)
                extra = getattr(delta, "reasoning_content", None)
                if extra:
                    reasoning.append(extra)
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
        return Reply(
            text="".join(text),
            reasoning="".join(reasoning),
            finish_reason=finish_reason,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            seconds=round(time.monotonic() - start, 1),
        )


if __name__ == "__main__":
    import sys

    prompt = sys.argv[1] if len(sys.argv) > 1 else "只回复两个字:收到"
    r = LLM().chat([{"role": "user", "content": prompt}])
    print(f"model={LLM().model} finish={r.finish_reason} prompt_tokens={r.prompt_tokens} "
          f"completion_tokens={r.completion_tokens} seconds={r.seconds} reasoning_chars={len(r.reasoning)}")
    print(r.text)
