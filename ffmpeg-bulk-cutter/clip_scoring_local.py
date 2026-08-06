"""Free local scoring provider for dev/testing - e.g. Ollama running on a
Mac mini reachable over Tailscale, so prompt iteration costs nothing while
developing. Same ClipScoringProvider shape as clip_scoring_openrouter.py,
and the template for wiring in a self-hosted fine-tuned model later
(Phase 2): same OpenAI-compatible HTTP endpoint, just a different
base_url/model.
"""
import os

from clip_scoring import ClipCandidateRaw, ScoringConfig, score_with_repair
from clip_scoring_prompt import build_prompt
from transcript_chunking import TranscriptChunk

DEFAULT_MODEL = "llama3.1"
DEFAULT_BASE_URL = "http://localhost:11434/v1"


class LocalProvider:
    def __init__(self, model: str = DEFAULT_MODEL, base_url: str | None = None, api_key: str | None = None):
        self.model = model
        self.base_url = base_url or os.environ.get("LOCAL_LLM_BASE_URL", DEFAULT_BASE_URL)
        # Ollama's OpenAI-compatible endpoint ignores the key's value but
        # still expects the Authorization header to be present.
        self.api_key = api_key or os.environ.get("LOCAL_LLM_API_KEY", "ollama")

    def score_candidates(self, chunks: list[TranscriptChunk], config: ScoringConfig) -> list[ClipCandidateRaw]:
        if not chunks:
            return []
        system_prompt, user_prompt = build_prompt(chunks, config)
        return score_with_repair(self.base_url, self.api_key, self.model, system_prompt, user_prompt)
