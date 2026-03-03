"""Tests for exporter module."""

import genanki

from exporter import build_deck, build_decks_by_chapter, write_apkg, write_apkg_multi


def test_build_deck_basic_cards():
    cards = [
        {"type": "basic", "front": "Q1?", "back": "A1.", "tags": []},
        {"type": "basic", "front": "Q2?", "back": "A2.", "tags": ["t1"]},
    ]
    deck = build_deck(cards, "TestDeck")
    assert isinstance(deck, genanki.Deck)
    assert deck.name == "TestDeck"
    assert len(deck.notes) == 2


def test_build_deck_cloze():
    cards = [
        {"type": "cloze", "text": "The {{c1::key}} term.", "tags": []},
    ]
    deck = build_deck(cards, "TestDeck")
    assert len(deck.notes) == 1


def test_build_deck_with_source():
    cards = [
        {"type": "basic", "front": "Q?", "back": "A.", "source": "Source: Slides 1–3", "tags": []},
    ]
    deck = build_deck(cards, "TestDeck")
    assert len(deck.notes) == 1
    assert deck.notes[0].fields[2] == "Source: Slides 1–3"


def test_build_decks_by_chapter():
    cards = [
        {"type": "basic", "front": "Q1?", "back": "A1.", "chapter": "Ch1", "tags": []},
        {"type": "basic", "front": "Q2?", "back": "A2.", "chapter": "Ch1", "tags": []},
        {"type": "basic", "front": "Q3?", "back": "A3.", "chapter": "Ch2", "tags": []},
    ]
    decks = build_decks_by_chapter(cards, "Base")
    assert len(decks) == 2
    names = {d.name for d in decks}
    assert "Base::Ch1" in names
    assert "Base::Ch2" in names
    deck_ch1 = next(d for d in decks if d.name == "Base::Ch1")
    deck_ch2 = next(d for d in decks if d.name == "Base::Ch2")
    assert len(deck_ch1.notes) == 2
    assert len(deck_ch2.notes) == 1


def test_build_decks_by_chapter_no_chapter_goes_to_other():
    cards = [
        {"type": "basic", "front": "Q?", "back": "A.", "tags": []},
    ]
    decks = build_decks_by_chapter(cards, "Base")
    assert len(decks) == 1
    assert decks[0].name == "Base::Other"
    assert len(decks[0].notes) == 1


def test_write_apkg_multi(tmp_path):
    cards1 = [{"type": "basic", "front": "Q?", "back": "A.", "chapter": "A", "tags": []}]
    cards2 = [{"type": "basic", "front": "Q2?", "back": "A2.", "chapter": "B", "tags": []}]
    decks = build_decks_by_chapter(cards1 + cards2, "Test")
    out = tmp_path / "out.apkg"
    write_apkg_multi(decks, str(out))
    assert out.exists()
