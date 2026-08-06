"""The scoring rubric sent to the LLM. This is "our AI" in the sense that
actually matters: the judgment criteria for what makes a good clip are ours
and are what gets iterated on; the LLM underneath is a swappable, borrowed
reasoning engine (see clip_scoring.get_provider()). No dependency on
clip_scoring.py here on purpose, to keep the import graph a one-way DAG:
clip_scoring_openrouter.py / clip_scoring_local.py import both this module
and clip_scoring.py, but this module imports neither of them.
"""
from cut_clips import format_timestamp
from transcript_chunking import TranscriptChunk

PROMPT_VERSION = "v1"

SYSTEM_PROMPT_TEMPLATE = """You are selecting the most engaging short-form clips from a longer video's transcript, for posting as standalone social media clips (Reels/Shorts/TikTok style).

You will be given the transcript as a numbered list of timestamped chunks. Pick up to {target_clip_count} candidate clips.

Rules for a good clip:
- Self-contained: understandable without context from earlier in the video.
- Strong hook in the first line: a question, a bold claim, a surprising fact, or an emotional beat.
- A clear ending: doesn't cut off mid-thought; ideally lands on a punchline, conclusion, or payoff.
- Target length: {min_duration:.0f} to {max_duration:.0f} seconds.
- Prefer clips with a setup-and-payoff structure, a surprising or controversial statement, useful/actionable advice, or genuine humor or emotion over flat, low-energy exposition.

Respond with ONLY a JSON array (no markdown fences, no commentary), one object per candidate clip:
[{{"start_chunk": <chunk id>, "end_chunk": <chunk id>, "score": <0-100>, "title": "<short catchy title>", "reason": "<one sentence, why this works>"}}]

start_chunk and end_chunk must be chunk id numbers from the transcript below (end_chunk >= start_chunk). Score higher for clips more likely to perform well as a standalone short. Return an empty array if nothing in the transcript is clip-worthy."""


def build_prompt(chunks: list[TranscriptChunk], config) -> tuple[str, str]:
    """config just needs .target_clip_count / .min_duration_s / .max_duration_s -
    duck-typed (normally a clip_scoring.ScoringConfig) rather than imported,
    to avoid a circular import with clip_scoring.py."""
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        target_clip_count=config.target_clip_count,
        min_duration=config.min_duration_s,
        max_duration=config.max_duration_s,
    )
    lines = [f'[{c.id}] {format_timestamp(c.start)}-{format_timestamp(c.end)}: "{c.text}"' for c in chunks]
    user_prompt = "Transcript:\n" + "\n".join(lines)
    return system_prompt, user_prompt
