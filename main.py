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
from config import CHUNK_OVERLAP, CHUNK_SIZE, GEMINI_API_KEY, MAX_RETRIES
from exporter import build_deck, build_decks_by_chapter, write_apkg, write_apkg_multi, write_csv
from extractor import extract, extract_pptx_with_chapters
from generator import generate
from parser import ParseError, parse_cards

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
    output_csv_path: Path | None = None,
    use_chapters: bool = False,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[Path, Path | None]:
    """
    Extract, chunk, generate, parse, export for one file.
    progress_callback(phase, message=None, current=None, total=None) is called for UI updates.
    phase: "extracting" | "chunking" | "generating" | "exporting" | "done" | "error"
    use_chapters: if True and file is PPTX, detect chapters and build subdecks (Deck::Chapter).
    Returns (apkg_path, csv_path or None).
    """
    def report(phase: str, message: str | None = None, current: int | None = None, total: int | None = None, error: str | None = None):
        if progress_callback:
            progress_callback(phase=phase, message=message, current=current, total=total, error=error)

    is_pptx = input_path.suffix.lower() == ".pptx"
    unit_name = get_unit_name(input_path)

    if use_chapters and is_pptx:
        report("extracting", "Reading slides and detecting chapters...")
        chapters = extract_pptx_with_chapters(input_path)
        if not chapters:
            console.print(f"[yellow]No content from {input_path}. Skipping.[/yellow]")
            raise ValueError("No content")
        all_cards: list[dict] = []
        total_chunks = sum(
            len(chunk(items, deck_name, unit_name=unit_name, chunk_size=chunk_size, overlap=overlap))
            for _, items in chapters
        )
        chunk_count = 0
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Generating cards...", total=total_chunks)
            for chapter_name, items in chapters:
                chunks_list = chunk(items, deck_name, unit_name=unit_name, chunk_size=chunk_size, overlap=overlap)
                if not chunks_list:
                    continue
                for i, (chunk_text, first_idx, last_idx) in enumerate(chunks_list):
                    if cancel_check and cancel_check():
                        report("error", error="Cancelled")
                        raise RuntimeError("Job cancelled") from None
                    chunk_count += 1
                    report("generating", f"Chunk {chunk_count}/{total_chunks}", current=chunk_count, total=total_chunks)
                    progress.update(task, description=f"Chunk {chunk_count}/{total_chunks}")
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
                                progress.update(task, description=f"Chunk {chunk_count}/{total_chunks} (retry {attempt + 2})")
                    if raw is None:
                        err_msg = str(last_error)
                        report("error", error=err_msg)
                        raise RuntimeError(f"Generation failed: {last_error}") from last_error
                    cards = parse_cards(raw)
                    source_label = f"Source: {unit_name.capitalize()}s {first_idx}–{last_idx}"
                    for c in cards:
                        c["chunk_index"] = chunk_count - 1
                        c["source"] = source_label
                        c["chapter"] = chapter_name
                    all_cards.extend(cards)
            progress.update(task, completed=total_chunks)

        if not all_cards:
            console.print("[yellow]No valid cards produced. Writing empty deck.[/yellow]")

        report("exporting_subdecks", "Building subdecks...")
        decks = build_decks_by_chapter(all_cards, deck_name)
        out = output_path or Path(sanitize_deck_name(deck_name) + ".apkg")
        write_apkg_multi(decks, str(out))
        csv_out = None
        if output_csv_path is not None:
            write_csv(all_cards, str(output_csv_path))
            csv_out = output_csv_path
        report("done", message=str(out))
        return (out, csv_out)

    # Flat flow (no chapters or PDF)
    report("extracting", "Reading slides...")
    items = extract(input_path)
    if not items:
        console.print(f"[yellow]No text extracted from {input_path}. Skipping.[/yellow]")
        raise ValueError("No content")

    report("chunking", "Preparing content...")
    chunks_list = chunk(items, deck_name, unit_name=unit_name, chunk_size=chunk_size, overlap=overlap)
    if not chunks_list:
        raise ValueError("No chunks")

    all_cards = []
    num_chunks = len(chunks_list)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating cards...", total=num_chunks)
        for i, (chunk_text, first_idx, last_idx) in enumerate(chunks_list):
            if cancel_check and cancel_check():
                report("error", error="Cancelled")
                raise RuntimeError("Job cancelled") from None
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
            source_label = f"Source: {unit_name.capitalize()}s {first_idx}–{last_idx}"
            for c in cards:
                c["chunk_index"] = i
                c["source"] = source_label
            all_cards.extend(cards)
        progress.update(task, completed=num_chunks)

    if not all_cards:
        console.print("[yellow]No valid cards produced. Writing empty deck.[/yellow]")

    report("exporting", "Building deck...")
    deck = build_deck(all_cards, deck_name)
    out = output_path or Path(sanitize_deck_name(deck_name) + ".apkg")
    write_apkg(deck, str(out))
    csv_out = None
    if output_csv_path is not None:
        write_csv(all_cards, str(output_csv_path))
        csv_out = output_csv_path
    report("done", message=str(out))
    return (out, csv_out)


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
    parser.add_argument(
        "--chapters",
        action="store_true",
        help="Detect chapters in PPTX (sections/headings) and create subdecks (Deck::Chapter). Ignored for PDF.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=CHUNK_SIZE,
        metavar="N",
        help=f"Slides/pages per chunk (default: {CHUNK_SIZE})",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=CHUNK_OVERLAP,
        metavar="N",
        help=f"Overlap between consecutive chunks (default: {CHUNK_OVERLAP})",
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
            csv_path = out_path.with_suffix(".csv") if out_path else Path(sanitize_deck_name(deck_name) + ".csv")
            out, csv_out = process_file(
                input_path, deck_name, out_path, args.provider,
                output_csv_path=csv_path, use_chapters=args.chapters,
                chunk_size=args.chunk_size, overlap=args.overlap,
            )
            console.print(f"[green]Done. Deck written to: {out}[/green]")
            if csv_out:
                console.print(f"[green]Knowt/Quizlet CSV: {csv_out}[/green]")
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
            csv_path = Path(sanitize_deck_name(deck_name) + ".csv")
            out, csv_out = process_file(
                f, deck_name, None, args.provider,
                output_csv_path=csv_path,
                use_chapters=args.chapters,
                chunk_size=args.chunk_size, overlap=args.overlap,
            )
            console.print(f"[green]{f.name} -> {out}[/green]")
            if csv_out:
                console.print(f"[green]  CSV: {csv_out}[/green]")
        return 0
    except (ValueError, RuntimeError, OSError, ParseError) as e:
        console.print(f"[red]{e}[/red]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
