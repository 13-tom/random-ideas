"""Groups Whisper's flat word-level transcript into sentence-ish, timestamped
chunks - what gets shown to the scoring LLM (clip_scoring_prompt.py) and what
clip boundaries get snapped to afterward (clip_postprocess.py), instead of
either giving the LLM a wall of unstructured text or trusting it to invent
exact timestamps of its own.
"""
from dataclasses import dataclass

from captions import Word

# '.', '!', '?' for English; the Devanagari danda/double-danda for Hindi.
SENTENCE_END_CHARS = (".", "!", "?", "।", "॥")


@dataclass
class TranscriptChunk:
    id: int
    start: float
    end: float
    text: str


def chunk_transcript(words: list[Word], pause_gap_s: float = 0.6, max_chunk_chars: int = 280) -> list[TranscriptChunk]:
    """Breaks after sentence-ending punctuation or a pause of at least
    pause_gap_s between words, with a max_chunk_chars fallback so one
    long run-on sentence doesn't become a single giant, unscoreable chunk."""
    chunks: list[TranscriptChunk] = []
    current: list[Word] = []

    def flush():
        if not current:
            return
        text = " ".join(w.text for w in current).strip()
        if text:
            chunks.append(TranscriptChunk(id=len(chunks) + 1, start=current[0].start, end=current[-1].end, text=text))
        current.clear()

    for i, word in enumerate(words):
        current.append(word)
        chunk_len = sum(len(w.text) + 1 for w in current)
        ends_sentence = word.text.rstrip().endswith(SENTENCE_END_CHARS)
        next_gap = words[i + 1].start - word.end if i + 1 < len(words) else None
        long_pause = next_gap is not None and next_gap >= pause_gap_s
        too_long = chunk_len >= max_chunk_chars
        if ends_sentence or long_pause or too_long:
            flush()
    flush()

    return chunks
