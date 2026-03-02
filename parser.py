"""Parse LLM JSON output into validated card list; strip fences, validate, filter, dedupe."""

import json
import re
from difflib import SequenceMatcher

# Patterns that indicate administrative/syllabus content (not exam material). Case-insensitive.
_ADMIN_PATTERNS = [
    r"\b(what is the )?name of the course\b",
    r"\b(what is )?this course (called|named)\b",
    r"\bcourse (title|name|code|number)\b",
    r"\boffice hours?\b",
    r"\b(when are |what are )?office hours\b",
    r"\b(professor|instructor|teacher)(\'s)? (name|office)\b",
    r"\b(professor|instructor)(\'s)? office (hours|location)\b",
    r"\blearning objectives?\b.*\b(course|syllabus)\b",
    r"\b(course|syllabus) (learning )?objectives?\b",
    r"\bwhat are the (course )?learning objectives\b",
    r"\bgrading (policy|scheme|criteria)\b",
    r"\bexam (date|time|location|room)\b",
    r"\bassignment (deadline|due date)\b",
    r"\b(class|lecture) (time|schedule|room)\b",
    r"\bsee (textbook|readings?|page)\b",
    r"\brefer to (the )?(textbook|readings?)\b",
    r"\bcontact (the )?(instructor|professor)\b",
    r"\broom (number|location)\b",
    r"\b(syllabus|course) (overview|outline|structure)\b",
]
_ADMIN_RE = re.compile("|".join(f"({p})" for p in _ADMIN_PATTERNS), re.IGNORECASE)


def _is_administrative(front: str, back: str = "", text: str = "") -> bool:
    """True if the card tests course/syllabus/instructor metadata rather than subject matter."""
    combined = " ".join([front, back, text])
    return bool(_ADMIN_RE.search(combined))


def _strip_json_fences(raw: str) -> str:
    """Remove markdown code fences (e.g. ```json ... ```) if present."""
    raw = raw.strip()
    match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    return raw


def _similarity(a: str, b: str) -> float:
    """Return similarity ratio in [0, 1]."""
    return SequenceMatcher(None, a, b).ratio()


def _is_answer_too_long(back: str) -> bool:
    """Heuristic: more than 2 sentences."""
    if not back:
        return True
    sentences = [s.strip() for s in re.split(r"[.!?]+", back) if s.strip()]
    return len(sentences) > 2


def _valid_cloze(text: str) -> bool:
    """Check that cloze text contains at least one {{c1::...}} (or c2, c3)."""
    return bool(re.search(r"\{\{c\d+::[^}]+\}\}", text))


def parse_cards(raw: str) -> list[dict]:
    """
    Parse raw LLM response into list of card dicts.
    Strips markdown fences, validates each card, filters bad ones, deduplicates by front similarity.
    Returns list of {type, front?, back?, text?, tags}.
    """
    raw = _strip_json_fences(raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    cards = data.get("cards") if isinstance(data, dict) else []
    if not isinstance(cards, list):
        return []

    result: list[dict] = []
    seen_fronts: list[str] = []

    for card in cards:
        if not isinstance(card, dict):
            continue
        card_type = (card.get("type") or "").strip().lower()

        if card_type == "basic":
            front = (card.get("front") or "").strip()
            back = (card.get("back") or "").strip()
            if not front or not back:
                continue
            if front == back:
                continue
            if _is_answer_too_long(back):
                continue
            if _is_administrative(front, back):
                continue
            # Dedupe: skip if very similar to an existing front
            if any(_similarity(front, s) >= 0.85 for s in seen_fronts):
                continue
            seen_fronts.append(front)
            result.append({
                "type": "basic",
                "front": front,
                "back": back,
                "tags": card.get("tags") or [],
            })
        elif card_type == "cloze":
            text = (card.get("text") or "").strip()
            if not text or not _valid_cloze(text):
                continue
            if _is_administrative("", "", text):
                continue
            # Use full text for dedupe key
            if any(_similarity(text, s) >= 0.85 for s in seen_fronts):
                continue
            seen_fronts.append(text)
            result.append({
                "type": "cloze",
                "text": text,
                "tags": card.get("tags") or [],
            })

    return result
