from __future__ import annotations

import json
import os
from pathlib import Path
import ssl
import urllib.error
import urllib.request

import certifi


# What: OpenAI Responses API adapter for the AIPM agent.
# Purpose: Lets PlanningSchedulingAgent use GPT reasoning without hardcoding credentials.

# What: Default OpenAI API base URL.
# Purpose: Keeps the endpoint configurable for testing or compatible gateways.
DEFAULT_BASE_URL = "https://api.openai.com/v1"


# What: Lightweight environment-file loader.
# Purpose: Lets the AIPM backend read OPENAI_API_KEY from a local .env file without extra packages.
def load_env_file(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# What: OpenAI-backed implementation of the agent ReasoningClient protocol.
# Purpose: Sends compact scheduling-analysis prompts to GPT and returns text findings.
class OpenAIReasoningClient:
    # What: Client constructor.
    # Purpose: Reads API configuration from arguments or environment variables.
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int = 60,
        max_output_tokens: int = 900,
    ) -> None:
        load_env_file(os.environ.get("AIPM_ENV_FILE", ".env"))
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Export it before running with --use-openai."
            )
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.ssl_context = ssl.create_default_context(cafile=certifi.where())

    # What: GPT reasoning call.
    # Purpose: Implements the agent protocol using the OpenAI Responses API.
    def reason(self, prompt: str, model: str) -> str:
        payload = {
            "model": model,
            "instructions": (
                "You are the AI reasoning layer for an engineering process-planning "
                "and scheduling agent. Be concise, technical, and action-oriented. "
                "Do not invent data that is not present in the prompt."
            ),
            "input": prompt,
            "max_output_tokens": self.max_output_tokens,
        }
        response = self._post_json("/responses", payload)
        return extract_response_text(response)

    # What: JSON POST helper.
    # Purpose: Performs the HTTPS request with standard-library tooling to avoid extra dependencies.
    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
                context=self.ssl_context,
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API request failed with HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenAI API request failed: {exc}") from exc


# What: Responses API text extractor.
# Purpose: Handles both convenience and structured response shapes returned by the API.
def extract_response_text(response: dict[str, object]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    chunks: list[str] = []
    output = response.get("output", [])
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                text = block.get("text")
                if isinstance(text, str):
                    chunks.append(text)

    if chunks:
        return "\n".join(chunks).strip()
    return json.dumps(response, ensure_ascii=False, indent=2)
