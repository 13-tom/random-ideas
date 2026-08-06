"""Clip-scoring swap point: Phase 1 calls a cheap LLM via OpenRouter
(clip_scoring_openrouter.py) or a local model for free dev/testing
(clip_scoring_local.py). Phase 2 - a self-trained/fine-tuned model on real
usage data - drops in later as another module implementing the same
ClipScoringProvider protocol, with zero changes to generate_timestamps.py,
clip_postprocess.py, or either existing provider. See get_provider().
"""
import json
import re
from dataclasses import dataclass
from typing import Protocol

from transcript_chunking import TranscriptChunk


@dataclass
class ScoringConfig:
    min_duration_s: float = 20.0
    max_duration_s: float = 90.0
    target_clip_count: int = 10
    min_score: float = 0.0


@dataclass
class ClipCandidateRaw:
    start_chunk_id: int
    end_chunk_id: int
    score: float
    title: str
    reason: str


class ClipScoringProvider(Protocol):
    def score_candidates(self, chunks: list[TranscriptChunk], config: ScoringConfig) -> list[ClipCandidateRaw]:
        ...


def get_provider(name: str, **kwargs) -> ClipScoringProvider:
    """Factory keyed by provider name (generate_timestamps.py's --provider
    flag). Imports the concrete provider lazily so e.g. missing the
    'requests' dependency doesn't break --provider local, and vice versa."""
    if name == "openrouter":
        from clip_scoring_openrouter import OpenRouterProvider
        return OpenRouterProvider(**kwargs)
    if name == "local":
        from clip_scoring_local import LocalProvider
        return LocalProvider(**kwargs)
    raise ValueError(f"Unknown scoring provider: {name!r} (choices: openrouter, local)")


def call_chat_completion(base_url: str, api_key: str | None, model: str, system_prompt: str, user_prompt: str, timeout: float = 180) -> str:
    """Shared OpenAI-compatible chat-completions call. OpenRouter and a
    local Ollama server both speak this same request/response shape, so
    every provider (including a future self-hosted fine-tuned one) can
    reuse this instead of each rolling its own HTTP client."""
    import requests

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers=headers,
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def parse_candidates_response(raw_text: str) -> list[ClipCandidateRaw]:
    """Parses the LLM's JSON array response, skipping individual malformed
    entries rather than failing the whole batch over one bad object."""
    text = raw_text.strip()
    # Some models wrap JSON in a ```json ... ``` fence despite being told not to.
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    data = json.loads(text)  # raises on totally invalid JSON - caller retries/repairs
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array, got {type(data).__name__}")

    candidates = []
    for entry in data:
        try:
            candidates.append(ClipCandidateRaw(
                start_chunk_id=int(entry["start_chunk"]),
                end_chunk_id=int(entry["end_chunk"]),
                score=float(entry["score"]),
                title=str(entry.get("title", "")).strip(),
                reason=str(entry.get("reason", "")).strip(),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return candidates


def score_with_repair(base_url: str, api_key: str | None, model: str, system_prompt: str, user_prompt: str) -> list[ClipCandidateRaw]:
    """Call + parse, with one repair retry if the response wasn't valid
    JSON - shared by every OpenAI-compatible-endpoint provider."""
    raw = call_chat_completion(base_url, api_key, model, system_prompt, user_prompt)
    try:
        return parse_candidates_response(raw)
    except (ValueError, KeyError) as e:
        print(f"  LLM response wasn't valid JSON ({e}); retrying with a repair prompt...")
        repair_prompt = f"{user_prompt}\n\nYour previous response could not be parsed as JSON: {e}\nRespond again with ONLY a valid JSON array, no other text."
        raw = call_chat_completion(base_url, api_key, model, system_prompt, repair_prompt)
        return parse_candidates_response(raw)
