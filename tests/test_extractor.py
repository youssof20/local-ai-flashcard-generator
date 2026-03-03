"""Tests for extractor module."""

from pathlib import Path

import pytest

from extractor import extract, extract_pptx_with_chapters


def test_extract_unsupported_extension_raises():
    with pytest.raises(ValueError, match="Unsupported format"):
        extract(Path("file.xyz"))


def test_extract_pptx_with_chapters_non_pptx_raises():
    with pytest.raises(ValueError, match="Expected .pptx"):
        extract_pptx_with_chapters(Path("file.pdf"))
