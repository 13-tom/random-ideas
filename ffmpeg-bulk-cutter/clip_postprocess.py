"""Turns the LLM's raw chunk-range picks into final, non-overlapping clip
timestamps, and writes them out in the exact CSV format cut_clips.py /
run_pipeline.py already read (start,end,label - no header) - so
generate_timestamps.py's output slots in as their input with zero changes
to that existing, tested pipeline code.
"""
import csv
from dataclasses import dataclass
from pathlib import Path

from clip_scoring import ClipCandidateRaw, ScoringConfig
from cut_clips import format_timestamp
from transcript_chunking import TranscriptChunk

# Small breathing room around the LLM's chosen chunk range - chunk
# boundaries are already word-timestamp-accurate (see transcript_chunking.py),
# this just avoids the clip feeling clipped right up against the first/last
# word with no air.
START_PAD_S = 0.1
END_PAD_S = 0.2

# Two candidates are treated as duplicates if they overlap by more than
# this fraction of the shorter one's length - keeps the higher-scored one.
MAX_OVERLAP_RATIO = 0.3


@dataclass
class ClipCandidate:
    start: float
    end: float
    label: str
    score: float
    title: str
    reason: str


def resolve_and_postprocess(raw_candidates: list[ClipCandidateRaw], chunks: list[TranscriptChunk], video_duration: float, config: ScoringConfig) -> list[ClipCandidate]:
    by_id = {c.id: c for c in chunks}

    resolved = []
    for raw in raw_candidates:
        start_chunk = by_id.get(raw.start_chunk_id)
        end_chunk = by_id.get(raw.end_chunk_id)
        if start_chunk is None or end_chunk is None or end_chunk.id < start_chunk.id:
            continue  # LLM referenced a chunk id that doesn't exist, or gave an inverted range
        start = max(0.0, start_chunk.start - START_PAD_S)
        end = min(video_duration, end_chunk.end + END_PAD_S)
        if end <= start:
            continue
        resolved.append(ClipCandidate(start=start, end=end, label="", score=raw.score, title=raw.title, reason=raw.reason))

    resolved = [c for c in resolved if config.min_duration_s <= (c.end - c.start) <= config.max_duration_s]
    resolved = [c for c in resolved if c.score >= config.min_score]
    resolved.sort(key=lambda c: c.score, reverse=True)

    kept: list[ClipCandidate] = []
    for candidate in resolved:
        if not _overlaps_kept(candidate, kept):
            kept.append(candidate)
        if len(kept) >= config.target_clip_count:
            break

    kept.sort(key=lambda c: c.start)
    return _label(kept)


def _overlaps_kept(candidate: ClipCandidate, kept: list[ClipCandidate]) -> bool:
    for other in kept:
        overlap = min(candidate.end, other.end) - max(candidate.start, other.start)
        if overlap <= 0:
            continue
        shorter = min(candidate.end - candidate.start, other.end - other.start)
        if overlap / shorter > MAX_OVERLAP_RATIO:
            return True
    return False


def _label(candidates: list[ClipCandidate]) -> list[ClipCandidate]:
    for i, c in enumerate(candidates, start=1):
        slug = "".join(ch if ch.isalnum() else "_" for ch in c.title.lower()).strip("_")[:40]
        c.label = f"{i:03d}_{slug}" if slug else f"clip_{i:03d}"
    return candidates


def fallback_candidates(chunks: list[TranscriptChunk], video_duration: float, config: ScoringConfig) -> list[ClipCandidate]:
    """Used when the LLM call fails outright (no API key, provider outage,
    unparseable response) so a job degrades to evenly-spaced, unscored
    windows instead of failing the whole job."""
    if not chunks:
        return []
    target_len = (config.min_duration_s + config.max_duration_s) / 2

    candidates = []
    i = 0
    while i < len(chunks) and len(candidates) < config.target_clip_count:
        start_chunk = chunks[i]
        end_idx = i
        while end_idx + 1 < len(chunks) and (chunks[end_idx].end - start_chunk.start) < target_len:
            end_idx += 1
        end_chunk = chunks[end_idx]

        start = max(0.0, start_chunk.start - START_PAD_S)
        end = min(video_duration, end_chunk.end + END_PAD_S, start + config.max_duration_s)
        if config.min_duration_s <= (end - start) <= config.max_duration_s:
            candidates.append(ClipCandidate(start=start, end=end, label="", score=0.0, title="", reason="fallback: evenly spaced (no LLM scoring available)"))
        i = end_idx + 1

    return _label(candidates)


def write_csv(candidates: list[ClipCandidate], csv_path: Path):
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for c in candidates:
            writer.writerow([format_timestamp(c.start), format_timestamp(c.end), c.label])


def write_metadata_json(candidates: list[ClipCandidate], json_path: Path):
    """Optional sidecar next to the CSV: cut_clips.py/run_pipeline.py only
    ever read the CSV (label/start/end), but a caller that wants the score/
    title/reason too (e.g. the website's results page) can read this
    instead of re-deriving it - keeps the CSV's format exactly what the
    existing pipeline already expects, with nothing added to it."""
    import json

    json_path.write_text(json.dumps([
        {"label": c.label, "start": c.start, "end": c.end, "score": c.score, "title": c.title, "reason": c.reason}
        for c in candidates
    ], indent=2), encoding="utf-8")
