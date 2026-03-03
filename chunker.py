"""Chunk slide/page content for LLM API calls with overlap."""

from config import CHUNK_OVERLAP, CHUNK_SIZE


def chunk(
    items: list[tuple[int, str]],
    deck_name: str,
    *,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
    unit_name: str = "slides",
) -> list[tuple[str, int, int]]:
    """
    Group items into chunks of chunk_size with overlap between consecutive chunks.
    Prepend a CONTEXT line to each chunk.
    Returns list of (chunk_text, first_index, last_index) for source tagging.
    """
    if not items:
        return []

    result: list[tuple[str, int, int]] = []
    step = max(1, chunk_size - overlap)
    i = 0
    while i < len(items):
        window = items[i : i + chunk_size]
        if not window:
            break
        first_idx, _ = window[0]
        last_idx, _ = window[-1]
        context = (
            f"CONTEXT: This content is from a university lecture on {deck_name}. "
            f"The following is {unit_name} {first_idx} through {last_idx}.\n\n"
        )
        label = unit_name.rstrip("s").capitalize()  # "slides" -> "Slide", "pages" -> "Page"
        body = "\n\n".join(f"{label} {idx}:\n{text}" for idx, text in window)
        result.append((context + body, first_idx, last_idx))
        i += step

    return result
