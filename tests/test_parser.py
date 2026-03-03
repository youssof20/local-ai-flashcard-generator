"""Tests for parser module."""

import pytest

from parser import ParseError, parse_cards


def test_parse_valid_basic_cards():
    raw = '''{"cards": [
        {"type": "basic", "front": "What is mitosis?", "back": "Cell division.", "tags": []},
        {"type": "basic", "front": "What is the capital of France?", "back": "Paris."}
    ]}'''
    result = parse_cards(raw)
    assert len(result) == 2
    assert result[0]["type"] == "basic"
    assert result[0]["front"] == "What is mitosis?"
    assert result[0]["back"] == "Cell division."
    assert result[1]["front"] == "What is the capital of France?"


def test_parse_strips_markdown_fences():
    raw = """```json
{"cards": [{"type": "basic", "front": "Q?", "back": "A.", "tags": []}]}
```"""
    result = parse_cards(raw)
    assert len(result) == 1
    assert result[0]["front"] == "Q?"


def test_parse_valid_cloze():
    raw = '''{"cards": [{"type": "cloze", "text": "The {{c1::term}} is defined as.", "tags": []}]}'''
    result = parse_cards(raw)
    assert len(result) == 1
    assert result[0]["type"] == "cloze"
    assert "{{c1::" in result[0]["text"]


def test_parse_filters_administrative():
    raw = '''{"cards": [
        {"type": "basic", "front": "What is the name of the course?", "back": "Bio 101.", "tags": []}
    ]}'''
    result = parse_cards(raw)
    assert len(result) == 0


def test_parse_dedupes_similar_fronts():
    raw = '''{"cards": [
        {"type": "basic", "front": "What is mitosis?", "back": "Cell division.", "tags": []},
        {"type": "basic", "front": "What is mitosis?", "back": "Division of cells.", "tags": []}
    ]}'''
    result = parse_cards(raw)
    assert len(result) == 1


def test_parse_rejects_invalid_json():
    with pytest.raises(ParseError) as exc_info:
        parse_cards("not json at all")
    assert "Invalid JSON" in str(exc_info.value)


def test_parse_rejects_empty_front_or_back():
    raw = '''{"cards": [
        {"type": "basic", "front": "", "back": "Something.", "tags": []},
        {"type": "basic", "front": "Q?", "back": "", "tags": []}
    ]}'''
    result = parse_cards(raw)
    assert len(result) == 0


def test_parse_rejects_front_equals_back():
    raw = '''{"cards": [{"type": "basic", "front": "Same", "back": "Same", "tags": []}]}'''
    result = parse_cards(raw)
    assert len(result) == 0


def test_parse_rejects_answer_too_long():
    raw = '''{"cards": [{"type": "basic", "front": "Q?", "back": "First. Second. Third. Fourth.", "tags": []}]}'''
    result = parse_cards(raw)
    assert len(result) == 0
