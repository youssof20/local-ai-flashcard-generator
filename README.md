# Flashcard Generator from Slides

Convert university lecture slides (PPTX or PDF) into Anki flashcard decks. Uses a **local LLM (Ollama)** by default so it's free and unlimited; optional **Gemini** for higher quality when you need it.

Decks are built with cognitive-science principles: one fact per card, active recall, no orphan cards, and the right card type (Basic or Cloze) for each concept.

## Requirements

- Python 3.11+
- [Ollama](https://ollama.ai) (for local, free generation)
- Optional: `GEMINI_API_KEY` (only if using `--provider gemini`)

## Setup

### 1. Install Ollama (one-time)

- **Windows:** Download the installer from [ollama.ai](https://ollama.ai)
- **macOS / Linux:** `curl -fsSL https://ollama.ai/install.sh | sh`

### 2. Pull a model (one-time)

The app uses `llama3.2:latest` by default. Pull it (or another model):

```bash
ollama pull llama3.2:latest
```

For better quality use `ollama pull qwen2.5:14b`. Use `mistral:7b` or `llama3.2:3b` if you have less RAM. To use a different model without changing code, set `OLLAMA_MODEL` (e.g. `set OLLAMA_MODEL=qwen2.5:14b`).

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Optional: Gemini

To use Google Gemini instead of Ollama (e.g. for a single high-stakes deck):

```bash
# Get a key from https://aistudio.google.com/
set GEMINI_API_KEY=your_key_here
```

## Usage

### Web UI (recommended)

Run the local web interface, then open a browser:

```bash
python app.py
```

Open **http://127.0.0.1:5000** in your browser. **Start Ollama first** (open the Ollama app or run `ollama serve`) so generation works. Upload a PPTX or PDF, enter a deck name (or leave blank to use the filename), choose Ollama or Gemini, pick an Ollama model if you have several installed, optionally check **Use chapter detection** (PPTX only), and click **Generate deck**. Progress and ETA are shown; when done, download the `.apkg` (Anki) or `.csv` (Knowt).

### Command line

**Single file (one deck):**

```bash
python main.py --input "Lecture1.pptx" --deck "Biochemistry Week 1"
# Output: Biochemistry_Week_1.apkg
```

**Custom output path:**

```bash
python main.py --input "Lecture1.pptx" --deck "Biochem Week 1" --output "biochem_w1.apkg"
```

**Whole folder (one deck per file):**

```bash
python main.py --input ./week1_slides/ --deck "Biochemistry Module 1"
# Creates: Biochemistry_Module_1_-_Lecture1.apkg, ... (one per .pptx/.pdf)
```

**Use Gemini instead of Ollama:**

```bash
python main.py --input "Lecture1.pptx" --deck "Biochem Week 1" --provider gemini
```

**Chapter detection (PPTX only):** Create subdecks (e.g. `DeckName::Chapter 1`) from PowerPoint sections or from slides titled "Chapter N", "Week N", etc.:

```bash
python main.py --input "Lecture1.pptx" --deck "Biochem Week 1" --chapters
```

**Chunk size (advanced):** Control how many slides/pages are sent to the LLM per request (default 6, overlap 1):

```bash
python main.py --input "Lecture1.pptx" --deck "Biochem" --chunk-size 8 --overlap 2
```

**Faster processing (parallel chunks):** By default the app runs 2 chunks at a time. To use one at a time (sequential) or more parallelism:

```bash
python main.py --input "Lecture1.pptx" --deck "Biochem" --workers 1   # sequential
python main.py --input "Lecture1.pptx" --deck "Biochem" --workers 3 # 3 chunks in parallel
```

The Web UI uses 2 parallel chunks by default. If your PC struggles (e.g. Ollama runs out of memory), set `CONCURRENT_CHUNKS=1` in the environment before starting the app.

## Import into Anki

1. Open [Anki](https://apps.ankiweb.net/) (free, cross-platform).
2. **File → Import** and select the `.apkg` file.
3. The deck appears with Basic and Cloze cards; each card back shows **Source: Slides X–Y** (or Pages) for reference.

## Import into Knowt

[Knowt](https://knowt.com) offers free learn mode, spaced repetition, and practice tests. Use the **CSV** download (or the `.csv` file from the CLI):

1. In the web UI, click **Download for Knowt (.csv)**. From the CLI, a `DeckName.csv` is written next to the `.apkg`.
2. In Knowt, create a new set → **Import manually** (or **Import from Quizlet** if you prefer).
3. Paste the CSV contents or upload the file. Set separators: comma between term/definition, newline between rows.
4. Cloze cards appear as term + “(cloze — best viewed in Anki)”; for full cloze support use the Anki deck.

## What gets excluded

Cards are not created for **course or syllabus metadata**: course name, instructor name, office hours, course learning objectives (as a list to recite), grading policy, exam dates/locations, "see textbook page X", and similar. Only exam-relevant or conceptually testable content becomes cards. The prompt and a post-parse filter both enforce this so you get decks focused on what you’re actually tested on.

## How it works

1. **Extract** — Text is read from each slide (PPTX) or page (PDF).
2. **Chunk** — Content is split into chunks of 6 slides/pages with 1 overlap so concepts aren’t cut mid-explanation.
3. **Generate** — Each chunk is sent to the LLM with a fixed system prompt (minimum information, active recall, no lists, etc.).
4. **Parse** — JSON is stripped of markdown, validated, and deduplicated.
5. **Export** — Cards are written to an Anki deck (Basic with reverse + Cloze) with stable GUIDs so re-running updates existing cards instead of duplicating them.

## Testing

From the project root:

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

## Troubleshooting

- **"Ollama is not running"** — Start Ollama (it often runs in the background after install), or run `ollama serve`. On Windows, open the Ollama app from the Start menu (don’t run `ollama serve` if the app is already open).
- **Ollama not reachable on Windows** — The app uses `127.0.0.1` by default. If it still fails, in PowerShell run `Invoke-WebRequest -Uri http://127.0.0.1:11434/api/tags -Method GET` to confirm Ollama is responding. If that works, try generating again.
- **"GEMINI_API_KEY is not set"** — Only needed for `--provider gemini`. Use Ollama without a key.
- **No cards / few cards** — Check that the slides contain real text (not only images). Try `--provider gemini` for trickier material.
