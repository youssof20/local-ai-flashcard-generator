"""Tests for chunker module."""

from chunker import chunk


def test_chunk_returns_tuples_with_first_last_index():
    items = [(1, "a"), (2, "b"), (3, "c"), (4, "d"), (5, "e"), (6, "f"), (7, "g")]
    result = chunk(items, "TestDeck", chunk_size=6, overlap=1)
    assert len(result) >= 1
    text, first, last = result[0]
    assert first == 1
    assert last == 6
    assert "CONTEXT" in text
    assert "Slide 1" in text


def test_chunk_size_and_overlap():
    items = [(i, f"text{i}") for i in range(1, 15)]
    result = chunk(items, "Deck", chunk_size=6, overlap=1)
    assert len(result) == 3
    assert result[0][1] == 1 and result[0][2] == 6
    assert result[1][1] == 6 and result[1][2] == 11
    assert result[2][1] == 11 and result[2][2] == 14


def test_chunk_empty_returns_empty():
    assert chunk([], "Deck") == []


def test_chunk_single_slide():
    items = [(1, "only one")]
    result = chunk(items, "Deck", chunk_size=6, overlap=1)
    assert len(result) == 1
    assert result[0][1] == 1 and result[0][2] == 1
