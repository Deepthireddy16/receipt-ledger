"""Everything that talks to a language model lives in this file.

The rest of the code only knows about `LLMClient.generate_json(prompt)`.
That gives us three things:
  1. Tests can use a fake client, so they need no API key and cost nothing.
  2. We can change the model provider later by editing one file.
  3. Every call is timed and its tokens are counted in one place.
"""

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


@dataclass
class LLMResult:
    text: str
    latency_s: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached: bool = False


class LLMClient(Protocol):
    name: str

    def generate_json(self, prompt: str, schema: type[BaseModel]) -> LLMResult: ...


class GeminiClient:
    """Calls the Gemini API and asks for JSON that follows `schema`."""

    def __init__(self, model: str, api_key: str, seconds_between_calls: float = 6.0, max_retries: int = 4):
        from google import genai  # imported here so tests do not need the package

        self.name = model
        self._client = genai.Client(api_key=api_key)
        self._seconds_between_calls = seconds_between_calls
        self._max_retries = max_retries
        self._last_call = 0.0

    def generate_json(self, prompt: str, schema: type[BaseModel]) -> LLMResult:
        from google.genai import errors

        for attempt in range(self._max_retries + 1):
            # The free tier allows only a few requests per minute, so we space calls out.
            wait = self._seconds_between_calls - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

            start = time.perf_counter()
            try:
                response = self._client.models.generate_content(
                    model=self.name,
                    contents=prompt,
                    config={
                        "temperature": 0,  # same input should give the same output
                        "response_mime_type": "application/json",
                        "response_schema": schema,
                    },
                )
            except errors.APIError as error:
                # 429 = rate limit, 5xx = server problem. Both are worth retrying.
                retryable = error.code == 429 or error.code >= 500
                if not retryable or attempt == self._max_retries:
                    raise
                time.sleep(15 * (attempt + 1))
                continue

            usage = response.usage_metadata
            return LLMResult(
                text=response.text or "",
                latency_s=time.perf_counter() - start,
                input_tokens=usage.prompt_token_count if usage else None,
                output_tokens=usage.candidates_token_count if usage else None,
            )
        raise RuntimeError("unreachable")


class CachedClient:
    """Saves each answer to disk so the same prompt is never sent twice.

    The file name is a hash of (model name + prompt). If the prompt or the
    model changes, the hash changes, so old answers are never reused by mistake.
    """

    def __init__(self, inner: LLMClient, cache_dir: str | Path):
        self.inner = inner
        self.name = inner.name
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def generate_json(self, prompt: str, schema: type[BaseModel]) -> LLMResult:
        key = hashlib.sha256(f"{self.name}\n{prompt}".encode()).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            return LLMResult(**{**saved, "cached": True})
        result = self.inner.generate_json(prompt, schema)
        path.write_text(json.dumps(asdict(result)), encoding="utf-8")
        return result


def gemini_from_env() -> GeminiClient:
    """Builds a GeminiClient from the values in the .env file."""
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    model = os.environ.get("GEMINI_MODEL")
    if not api_key or not model:
        raise SystemExit("Set GEMINI_API_KEY and GEMINI_MODEL in the .env file (see .env.example).")
    seconds = float(os.environ.get("SECONDS_BETWEEN_CALLS", "6"))
    return GeminiClient(model=model, api_key=api_key, seconds_between_calls=seconds)
