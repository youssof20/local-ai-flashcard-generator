"""Lightweight web UI for the flashcard generator."""

import os
import tempfile
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request, send_file

from config import GEMINI_API_KEY
from main import process_file, sanitize_deck_name, SLIDE_EXTENSIONS

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB

# In-memory job state: job_id -> { phase, message, current, total, path, csv_path, error, filename, csv_filename }
jobs: dict = {}
_jobs_lock = threading.Lock()

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Flashcard Generator</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui, -apple-system, sans-serif; max-width: 520px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
    h1 { font-size: 1.35rem; font-weight: 600; margin-bottom: 0.5rem; }
    .sub { color: #666; font-size: 0.9rem; margin-bottom: 1.5rem; }
    label { display: block; font-weight: 500; margin-bottom: 0.35rem; font-size: 0.9rem; }
    input[type="text"], select { width: 100%; padding: 0.5rem 0.6rem; margin-bottom: 1rem; border: 1px solid #ccc; border-radius: 6px; font-size: 1rem; }
    input[type="file"] { width: 100%; margin-bottom: 1rem; font-size: 0.9rem; }
    button { width: 100%; padding: 0.65rem 1rem; font-size: 1rem; font-weight: 500; border: none; border-radius: 6px; background: #2563eb; color: white; cursor: pointer; }
    button:hover { background: #1d4ed8; }
    button:disabled { background: #94a3b8; cursor: not-allowed; }
    .progress { margin-top: 1.25rem; padding: 1rem; background: #f1f5f9; border-radius: 8px; font-size: 0.9rem; display: none; }
    .progress.visible { display: block; }
    .progress .phase { font-weight: 500; color: #334155; }
    .progress .detail { color: #64748b; margin-top: 0.25rem; }
    .progress .eta { font-size: 0.85rem; color: #64748b; margin-top: 0.2rem; }
    .progress .bar { margin-top: 0.5rem; height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden; }
    .progress .bar-fill { height: 100%; background: #2563eb; border-radius: 3px; transition: width 0.2s; }
    .progress.error .phase { color: #b91c1c; }
    .progress.error .detail { color: #991b1b; }
    .download { margin-top: 1rem; display: none; }
    .download.visible { display: block; }
    .download a { display: inline-block; padding: 0.5rem 1rem; background: #059669; color: white; text-decoration: none; border-radius: 6px; font-weight: 500; }
    .download a:hover { background: #047857; }
    .status { margin-top: 0.5rem; font-size: 0.85rem; color: #64748b; }
    .hint code { background: #e2e8f0; padding: 0.1rem 0.35rem; border-radius: 4px; font-size: 0.85em; }
  </style>
</head>
<body>
  <h1>Flashcard Generator</h1>
  <p class="sub">Upload slides (PPTX or PDF) and get a flashcard deck. Use with Anki or <a href="https://knowt.com" target="_blank" rel="noopener">Knowt</a> (free learn mode).</p>

  <form id="form">
    <label for="file">Slide deck</label>
    <input type="file" id="file" name="file" accept=".pptx,.pdf" required>
    <p class="hint" style="margin: -0.5rem 0 1rem 0; font-size: 0.85rem; color: #64748b;">PPTX or PDF only.</p>

    <label for="deck">Deck name <span style="font-weight: normal; color: #64748b;">(optional)</span></label>
    <input type="text" id="deck" name="deck" placeholder="Leave blank to use file name">

    <label for="provider">AI provider</label>
    <select id="provider" name="provider">
      <option value="ollama" selected>Ollama — free, runs on your PC</option>
      <option value="gemini">Gemini — needs API key</option>
    </select>
    <p class="hint" style="margin: -0.5rem 0 1rem 0; font-size: 0.85rem; color: #64748b;">Default: Ollama. Start the Ollama app first if you use it.</p>

    <button type="submit" id="submit">Generate deck</button>
  </form>

  <div id="progress" class="progress">
    <div class="phase" id="phase">—</div>
    <div class="detail" id="detail"></div>
    <div class="eta" id="eta"></div>
    <div class="bar"><div class="bar-fill" id="barFill" style="width: 0%"></div></div>
  </div>

  <div id="download" class="download">
    <p style="margin-bottom: 0.5rem; font-weight: 500;">Your deck is ready.</p>
    <a id="downloadAnki" href="#">Download for Anki (.apkg)</a>
    <a id="downloadKnowt" href="#" style="margin-left: 0.5rem;">Download for Knowt (.csv)</a>
  </div>

  <script>
    const form = document.getElementById('form');
    const submitBtn = document.getElementById('submit');
    const progressEl = document.getElementById('progress');
    const phaseEl = document.getElementById('phase');
    const detailEl = document.getElementById('detail');
    const barFill = document.getElementById('barFill');
    const downloadEl = document.getElementById('download');

    const etaEl = document.getElementById('eta');
    const phaseLabels = { extracting: 'Reading slides', chunking: 'Preparing content', generating: 'Generating cards', exporting: 'Building deck', done: 'Done', error: 'Error', starting: 'Starting...' };
    let etaStartTime = null;

    function showProgress(phase, message, current, total, isError) {
      progressEl.classList.add('visible');
      if (isError) progressEl.classList.add('error');
      else progressEl.classList.remove('error');
      phaseEl.textContent = phaseLabels[phase] || phase || 'Processing...';
      detailEl.textContent = message || '';
      if (total && total > 0 && current != null && phase === 'generating') {
        if (!etaStartTime) etaStartTime = Date.now();
        const elapsed = (Date.now() - etaStartTime) / 1000;
        const remaining = current > 0 ? (elapsed / current) * (total - current) : 0;
        if (remaining > 60) etaEl.textContent = 'About ' + Math.ceil(remaining / 60) + ' min left';
        else if (remaining > 5) etaEl.textContent = 'About ' + Math.ceil(remaining) + ' sec left';
        else etaEl.textContent = '';
      } else if (phase === 'done' || phase === 'error') {
        etaEl.textContent = '';
        etaStartTime = null;
      } else {
        etaEl.textContent = '';
      }
      let pct = 0;
      if (total && total > 0 && current != null) pct = Math.round((current / total) * 100);
      else if (phase === 'done') pct = 100;
      barFill.style.width = pct + '%';
    }

    let currentJobId = null;
    function showDownload(filename, csvFilename) {
      downloadEl.classList.add('visible');
      if (currentJobId) {
        document.getElementById('downloadAnki').href = '/download/' + currentJobId;
        document.getElementById('downloadKnowt').href = '/download/' + currentJobId + '?format=csv';
      }
      document.getElementById('downloadAnki').download = filename || 'deck.apkg';
      document.getElementById('downloadKnowt').download = csvFilename || 'deck.csv';
    }

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fileInput = document.getElementById('file');
      const deck = document.getElementById('deck').value.trim() || fileInput.files[0].name.replace(/\\.(pptx|pdf)$/i, '');
      const provider = document.getElementById('provider').value;
      const formData = new FormData();
      formData.append('file', fileInput.files[0]);
      formData.append('deck', deck);
      formData.append('provider', provider);

      submitBtn.disabled = true;
      progressEl.classList.remove('visible');
      downloadEl.classList.remove('visible');
      showProgress('Uploading...', '', 0, 0);

      const r = await fetch('/generate', { method: 'POST', body: formData });
      const data = await r.json();
      if (!r.ok) {
        showProgress('Error', data.error || 'Upload failed', null, null, true);
        submitBtn.disabled = false;
        return;
      }

      currentJobId = data.job_id;

      const poll = setInterval(async () => {
        const s = await fetch('/status/' + currentJobId);
        const sdata = await s.json();
        const phase = sdata.phase || 'Processing...';
        const message = sdata.message || '';
        const current = sdata.current;
        const total = sdata.total;
        const isError = sdata.phase === 'error';
        showProgress(phase, message, current, total, isError);

        if (sdata.phase === 'done') {
          clearInterval(poll);
          submitBtn.disabled = false;
          showDownload(sdata.filename || 'deck.apkg', sdata.csv_filename || 'deck.csv');
        } else if (sdata.phase === 'error') {
          clearInterval(poll);
          submitBtn.disabled = false;
        }
      }, 600);
    });
  </script>
</body>
</html>
"""


def run_job(job_id: str, input_path: Path, deck_name: str, provider: str, out_path: Path, out_csv_path: Path):
    def callback(phase=None, message=None, current=None, total=None, error=None, **kwargs):
        with _jobs_lock:
            if job_id not in jobs:
                return
            jobs[job_id]["phase"] = phase or "processing"
            jobs[job_id]["message"] = message or ""
            jobs[job_id]["current"] = current
            jobs[job_id]["total"] = total
            if error:
                jobs[job_id]["phase"] = "error"
                jobs[job_id]["message"] = error

    try:
        _, csv_path = process_file(
            input_path, deck_name, out_path, provider,
            progress_callback=callback,
            output_csv_path=out_csv_path,
        )
        with _jobs_lock:
            if job_id in jobs:
                jobs[job_id]["phase"] = "done"
                jobs[job_id]["path"] = str(out_path)
                jobs[job_id]["filename"] = out_path.name
                jobs[job_id]["csv_path"] = str(csv_path) if csv_path else None
                jobs[job_id]["csv_filename"] = csv_path.name if csv_path else None
    except Exception as e:
        with _jobs_lock:
            if job_id in jobs:
                jobs[job_id]["phase"] = "error"
                jobs[job_id]["message"] = str(e)


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/generate", methods=["POST"])
def generate():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No file selected"}), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in SLIDE_EXTENSIONS:
        return jsonify({"error": "Use a .pptx or .pdf file"}), 400
    deck_name = (request.form.get("deck") or "").strip() or Path(f.filename).stem
    provider = request.form.get("provider") or "ollama"
    if provider == "gemini" and not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY not set. Use Ollama or set the key."}), 400

    job_id = str(uuid.uuid4())
    tmp = tempfile.mkdtemp()
    input_path = Path(tmp) / f.filename
    f.save(str(input_path))
    out_name = sanitize_deck_name(deck_name) + ".apkg"
    out_path = Path(tmp) / out_name
    out_csv_path = Path(tmp) / (sanitize_deck_name(deck_name) + ".csv")

    with _jobs_lock:
        jobs[job_id] = {
            "phase": "starting",
            "message": "",
            "current": None,
            "total": None,
            "path": None,
            "csv_path": None,
            "filename": out_name,
            "csv_filename": None,
            "error": None,
            "tmp": tmp,
        }
    t = threading.Thread(target=run_job, args=(job_id, input_path, deck_name, provider, out_path, out_csv_path))
    t.daemon = True
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    with _jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"phase": "error", "message": "Unknown job"}), 404
    return jsonify({
        "phase": job["phase"],
        "message": job.get("message") or "",
        "current": job.get("current"),
        "total": job.get("total"),
        "filename": job.get("filename"),
        "csv_filename": job.get("csv_filename"),
    })


@app.route("/download/<job_id>")
def download(job_id):
    fmt = request.args.get("format", "apkg")
    with _jobs_lock:
        job = jobs.get(job_id)
    if not job or job.get("phase") != "done":
        return "Not found", 404
    if fmt == "csv":
        path = Path(job.get("csv_path") or "")
        name = job.get("csv_filename") or "deck.csv"
        mimetype = "text/csv"
    else:
        path = Path(job.get("path") or "")
        name = job.get("filename") or "deck.apkg"
        mimetype = "application/octet-stream"
    if not path or not path.exists():
        return "File expired", 404
    return send_file(path, as_attachment=True, download_name=name, mimetype=mimetype)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
