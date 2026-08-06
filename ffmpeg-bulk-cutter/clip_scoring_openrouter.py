"""Phase 1 scoring provider: a cheap LLM via OpenRouter. Default model is
Gemini 2.5 Flash (cheap, huge context window, reliable structured JSON
output - see project planning notes); swap models with --llm-model, or
swap providers entirely with --provider local, without touching
generate_timestamps.py or clip_postprocess.py.
"""
import os

from clip_scoring import ClipCandidateRaw, ScoringConfig, score_with_repair
from clip_scoring_prompt import build_prompt
from transcript_chunking import TranscriptChunk

DEFAULT_MODEL = "google/gemini-2.5-flash"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider:
    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None, base_url: str = DEFAULT_BASE_URL):
        self.model = model
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouter API key required: pass --llm-api-key or set the OPENROUTER_API_KEY environment variable")
        self.base_url = base_url

    def score_candidates(self, chunks: list[TranscriptChunk], config: ScoringConfig) -> list[ClipCandidateRaw]:
        if not chunks:
            return []
        system_prompt, user_prompt = build_prompt(chunks, config)
        return score_with_repair(self.base_url, self.api_key, self.model, system_prompt, user_prompt)
