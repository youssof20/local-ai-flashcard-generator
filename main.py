#!/usr/bin/env python3
"""CLI: convert PPTX/PDF lecture slides into Anki .apkg decks using Ollama or Gemini."""

import argparse
import re
import sys
from pathlib import Path
from typing import Callable

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from chunker import chunk
from config import GEMINI_API_KEY, MAX_RETRIES
from exporter import build_deck, write_apkg
from extractor import extract
from generator import generate
from parser import parse_cards

console = Console()

# Supported extensions
SLIDE_EXTENSIONS = {".pptx", ".pdf"}


def sanitize_deck_name(name: str) -> str:
    """Sanitize for use in filenames."""
    s = re.sub(r'[<>:"/\\|?*]', "-", name)
    return re.sub(r"\s+", "_", s).strip("_") or "deck"


def get_unit_name(path: Path) -> str:
    """Return 'slides' for .pptx, 'pages' for .pdf."""
    return "pages" if path.suffix.lower() == ".pdf" else "slides"


def process_file(
    input_path: Path,
    deck_name: str,
    output_path: Path | None,
    provider: str,
    progress_callback: Callable[..., None] | None = None,
) -> Path:
    """
    Extract, chunk, generate, parse, export for one file.
    progress_callback(phase, message=None, current=None, total=None) is called for UI updates.
    phase: "extracting" | "chunking" | "generating" | "exporting" | "done" | "error"
    Returns the path to the written .apkg file.
    """
    def report(phase: str, message: str | None = None, current: int | None = None, total: int | None = None, error: str | None = None):
        if progress_callback:
            progress_callback(phase=phase, message=message, current=current, total=total, error=error)

    report("extracting", "Reading slides...")
    items = extract(input_path)
    if not items:
        console.print(f"[yellow]No text extracted from {input_path}. Skipping.[/yellow]")
        raise ValueError("No content")

    report("chunking", "Preparing content...")
    unit_name = get_unit_name(input_path)
    chunks_list = chunk(items, deck_name, unit_name=unit_name)
    if not chunks_list:
        raise ValueError("No chunks")

    all_cards: list[dict] = []
    num_chunks = len(chunks_list)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating cards...", total=num_chunks)
        for i, chunk_text in enumerate(chunks_list):
            report("generating", f"Chunk {i + 1}/{num_chunks}", current=i + 1, total=num_chunks)
            progress.update(task, description=f"Chunk {i + 1}/{num_chunks}")
            raw = None
            last_error = None
            for attempt in range(MAX_RETRIES):
                try:
                    raw = generate(chunk_text, provider=provider)
                    break
                except Exception as e:
                    last_error = e
                    if provider == "ollama" and "connection" in str(e).lower():
                        console.print("[red]Ollama is not running. Start it with: ollama serve[/red]")
                    if attempt < MAX_RETRIES - 1:
                        progress.update(task, description=f"Chunk {i + 1}/{num_chunks} (retry {attempt + 2})")
            if raw is None:
                err_msg = str(last_error)
                report("error", error=err_msg)
                console.print(f"[red]Chunk {i + 1} failed after {MAX_RETRIES} attempts: {last_error}[/red]")
                raise RuntimeError(f"Generation failed: {last_error}") from last_error
            cards = parse_cards(raw)
            for c in cards:
                c["chunk_index"] = i
            all_cards.extend(cards)
        progress.update(task, completed=num_chunks)

    if not all_cards:
        console.print("[yellow]No valid cards produced. Writing empty deck.[/yellow]")

    report("exporting", "Building deck...")
    deck = build_deck(all_cards, deck_name)
    out = output_path or Path(sanitize_deck_name(deck_name) + ".apkg")
    write_apkg(deck, str(out))
    report("done", message=str(out))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert lecture slides (PPTX/PDF) into Anki flashcard decks using a local or cloud LLM.",
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to a .pptx/.pdf file or a directory containing such files",
    )
    parser.add_argument(
        "--deck",
        "-d",
        default="",
        help="Deck name (default: derived from filename). For directories, used as prefix.",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output .apkg path (single-file mode only). Default: <deck_name>.apkg",
    )
    parser.add_argument(
        "--provider",
        "-p",
        choices=["ollama", "gemini"],
        default="ollama",
        help="LLM provider: ollama (local, free) or gemini (requires GEMINI_API_KEY)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        console.print(f"[red]Error: path does not exist: {input_path}[/red]")
        return 1

    if args.provider == "gemini" and not GEMINI_API_KEY:
        console.print("[red]Error: GEMINI_API_KEY is not set. Set it or use --provider ollama.[/red]")
        return 1

    try:
        if input_path.is_file():
            if input_path.suffix.lower() not in SLIDE_EXTENSIONS:
                console.print(f"[red]Error: unsupported format. Use .pptx or .pdf[/red]")
                return 1
            deck_name = args.deck or input_path.stem
            out_path = Path(args.output) if args.output else None
            out = process_file(input_path, deck_name, out_path, args.provider)
            console.print(f"[green]Done. Deck written to: {out}[/green]")
            return 0

        # Directory
        if args.output:
            console.print("[yellow]--output is ignored in directory mode.[/yellow]")
        files = sorted(
            f for f in input_path.iterdir()
            if f.is_file() and f.suffix.lower() in SLIDE_EXTENSIONS
        )
        if not files:
            console.print(f"[red]No .pptx or .pdf files found in {input_path}[/red]")
            return 1
        prefix = (args.deck + " - ") if args.deck else ""
        for f in files:
            deck_name = prefix + f.stem
            out = process_file(f, deck_name, None, args.provider)
            console.print(f"[green]{f.name} -> {out}[/green]")
        return 0
    except (ValueError, RuntimeError, OSError) as e:
        console.print(f"[red]{e}[/red]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
