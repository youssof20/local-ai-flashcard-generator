"""Build Anki deck from card list and write .apkg using genanki."""

import re

import genanki

# Basic (and reversed card) — two templates: Front→Back and Back→Front
BASIC_MODEL = genanki.Model(
    1485830180,
    "Basic (and reversed card)",
    fields=[
        {"name": "Front", "font": "Arial"},
        {"name": "Back", "font": "Arial"},
    ],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "{{Front}}",
            "afmt": "{{FrontSide}}\n\n<hr id=answer>\n\n{{Back}}",
        },
        {
            "name": "Card 2",
            "qfmt": "{{Back}}",
            "afmt": "{{FrontSide}}\n\n<hr id=answer>\n\n{{Front}}",
        },
    ],
    css=".card {\n font-family: arial;\n font-size: 20px;\n text-align: center;\n color: black;\n background-color: white;\n}\n",
)

# Cloze — Anki-compatible cloze model (standard ID used by many exporters)
CLOZE_MODEL = genanki.Model(
    1480089192,
    "Cloze",
    model_type=genanki.Model.CLOZE,
    fields=[
        {"name": "Text", "font": "Arial"},
        {"name": "Back Extra", "font": "Arial"},
    ],
    templates=[
        {
            "name": "Cloze",
            "qfmt": "{{cloze:Text}}",
            "afmt": "{{cloze:Text}}<br>\n{{Back Extra}}",
        },
    ],
    css=".card {\n font-family: arial;\n font-size: 20px;\n text-align: center;\n color: black;\n background-color: white;\n}\n\n"
    ".cloze {\n font-weight: bold;\n color: blue;\n}\n.nightMode .cloze {\n color: lightblue;\n}",
)


def _sanitize_tag(tag: str) -> str:
    """Anki tags must not contain spaces."""
    s = (tag or "").strip()
    return re.sub(r"\s+", "-", s) if s else "untagged"


def _tags_list(card: dict, deck_name: str) -> list[str]:
    """Build tag list: deck name, optional chunk (from card), and card tags (sanitized)."""
    tags = [deck_name.replace(" ", "-")]
    chunk_index = card.get("chunk_index")
    if chunk_index is not None:
        tags.append(f"chunk-{chunk_index}")
    for t in card.get("tags") or []:
        st = _sanitize_tag(str(t))
        if st and st not in tags:
            tags.append(st)
    return tags


def build_deck(
    cards: list[dict],
    deck_name: str,
    deck_id: int | None = None,
) -> genanki.Deck:
    """
    Build a genanki Deck from a list of card dicts (from parser).
    Each card has type ('basic' | 'cloze'), and either front/back or text, plus optional tags.
    Cards may include 'chunk_index' for tagging. Uses stable GUIDs (genanki.guid_for).
    """
    if deck_id is None:
        deck_id = abs(hash(deck_name)) % (2**31)
    deck = genanki.Deck(deck_id, deck_name)

    for card in cards:
        card_type = (card.get("type") or "basic").lower()
        tags = _tags_list(card, deck_name)

        if card_type == "basic":
            front = card.get("front") or ""
            back = card.get("back") or ""
            guid = genanki.guid_for(front, back)
            note = genanki.Note(
                model=BASIC_MODEL,
                fields=[front, back],
                tags=tags,
                guid=guid,
            )
            deck.add_note(note)
        elif card_type == "cloze":
            text = card.get("text") or ""
            guid = genanki.guid_for(text)
            # Cloze model has Text and Back Extra; we only use Text
            note = genanki.Note(
                model=CLOZE_MODEL,
                fields=[text, ""],
                tags=tags,
                guid=guid,
            )
            deck.add_note(note)

    return deck


def write_apkg(deck: genanki.Deck, path: str) -> None:
    """Write deck to a .apkg file."""
    genanki.Package(deck).write_to_file(path)
