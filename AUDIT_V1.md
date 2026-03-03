# Flashcard Generator — V1 Completion Audit

**Date:** March 2026  
**Scope:** Readiness for a solid, shippable v1 release.

---

## V1 Completion: **~95%**

The project is in very good shape for v1. All core features, security/resource fixes, QoL, and tests from the previous audit plan are implemented. Remaining gaps are minor and optional for launch.

---

## What V1 Includes (Done)

| Area | Status | Notes |
|------|--------|------|
| **Core pipeline** | Done | Extract → chunk → generate → parse → export (PPTX + PDF). |
| **Ollama (default)** | Done | 127.0.0.1, path fallbacks (/api/chat → /api/generate → /v1/chat/completions). |
| **Gemini (optional)** | Done | With blocked/empty response handling. |
| **Cognitive prompt** | Done | Min information, active recall, no orphans, admin/syllabus exclusion. |
| **Admin filter** | Done | Prompt + post-parse regex in `parser.py` (course name, office hours, etc.). |
| **Chapter detection** | Done | Optional: native PPTX sections + heuristic (Chapter/Week/Unit headings). Subdecks `Deck::Chapter`. |
| **Anki export** | Done | .apkg with Basic (reversed) + Cloze, source on back, stable GUIDs. |
| **Knowt/CSV export** | Done | Term,Definition CSV; UI + CLI both produce it. |
| **Web UI** | Done | Upload, deck name, provider, chapter checkbox, progress, ETA, Cancel, two download links. |
| **CLI** | Done | Single file, directory batch, `--chapters`, `--chunk-size`/`--overlap`, `--provider`. |
| **Directory CSV** | Done | Batch mode writes a CSV per deck. |
| **Security** | Done | `secure_filename()` for upload path. |
| **Temp cleanup** | Done | 10‑minute retention then `_cleanup_job` (rmtree + remove from `jobs`). |
| **Phase labels** | Done | “Building subdecks” for chapter export in UI. |
| **Cancel job** | Done | UI button + `POST /cancel/<id>`, `cancel_check` in pipeline. |
| **Parser robustness** | Done | `ParseError` on invalid JSON; CLI catches it. |
| **Gemini robustness** | Done | SAFETY/blocked and empty response handling. |
| **Tests** | Done | 21 tests: parser, chunker, exporter, extractor (no LLM/network). |
| **README** | Done | Setup, UI + CLI usage, chapter detection, OLLAMA_MODEL, chunk flags, Anki/Knowt import, Testing, Troubleshooting. |

---

## Optional / Not Blocking V1

- **Model selector in UI** — Config/env (`OLLAMA_MODEL`) is documented; dropdown would be nice later.
- **PDF chapter detection** — PDF is single-chapter; outline-based chapters could be a v1.1 feature.
- **Structured logging** — Rich + callback are enough for v1.
- **Rate limiting** — Only relevant if the app is exposed beyond localhost.

---

## Suggested V1 Checklist Before Tagging

1. **Run tests:** `python -m pytest tests/ -v` → all pass (verified).
2. **Smoke test:** Web UI → upload a small PPTX/PDF → generate → download .apkg and .csv.
3. **CLI smoke test:** `python main.py -i <file> -d "Test"` and directory mode with 2 files.
4. **Tag:** e.g. `v1.0.0` when you’re happy.

---

## Summary

| Category        | V1 status   |
|----------------|-------------|
| Core pipeline  | Complete    |
| Chapter detection | Complete (optional) |
| Web UI         | Complete    |
| CLI            | Complete    |
| Security       | Addressed   |
| Resources      | Addressed (temp cleanup) |
| Robustness     | Addressed   |
| Tests          | 21 passing  |
| Documentation  | Complete    |

**V1 completion: ~95%.** The remaining 5% is optional polish (e.g. model dropdown, PDF chapters). The project is ready to ship as v1.
