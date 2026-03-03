"""Lightweight web UI for the flashcard generator."""

import os
import shutil
import tempfile
import threading
import uuid
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template_string, request, send_file
from werkzeug.utils import secure_filename

from config import CONCURRENT_CHUNKS, GEMINI_API_KEY, OLLAMA_MODEL, OLLAMA_URL
from main import process_file, sanitize_deck_name, SLIDE_EXTENSIONS

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB

# In-memory job state: job_id -> { phase, message, current, total, path, csv_path, error, filename, csv_filename, tmp, cancelled }
# Temp files are kept for JOB_RETENTION_MINUTES so users can download; then job and tmp dir are removed.
JOB_RETENTION_MINUTES = 10
jobs: dict = {}
_jobs_lock = threading.Lock()


def _is_cancelled(job_id: str) -> bool:
    with _jobs_lock:
        return bool(jobs.get(job_id, {}).get("cancelled"))


def _cleanup_job(job_id: str) -> None:
    """Remove job from memory and delete its temp directory."""
    with _jobs_lock:
        job = jobs.pop(job_id, None)
    if job and job.get("tmp"):
        try:
            shutil.rmtree(job["tmp"], ignore_errors=True)
        except OSError:
            pass

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Flashcard Generator</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      max-width: 560px;
      margin: 0 auto;
      padding: 2rem 1.25rem 3rem;
      color: #1e293b;
      background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
      min-height: 100vh;
    }
    .card {
      background: #fff;
      border-radius: 12px;
      padding: 1.5rem 1.75rem;
      margin-bottom: 1.25rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.06);
      border: 1px solid #e2e8f0;
    }
    h1 {
      font-size: 1.5rem;
      font-weight: 700;
      margin: 0 0 0.25rem 0;
      color: #0f172a;
      letter-spacing: -0.02em;
    }
    .sub {
      color: #64748b;
      font-size: 0.9rem;
      margin: 0 0 1.5rem 0;
      line-height: 1.5;
    }
    .sub a { color: #2563eb; text-decoration: none; }
    .sub a:hover { text-decoration: underline; }
    label {
      display: block;
      font-weight: 600;
      margin-bottom: 0.4rem;
      font-size: 0.875rem;
      color: #334155;
    }
    input[type="text"], select {
      width: 100%;
      padding: 0.55rem 0.75rem;
      margin-bottom: 1rem;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      font-size: 0.95rem;
      background: #fff;
      color: #1e293b;
    }
    input[type="text"]:focus, select:focus {
      outline: none;
      border-color: #2563eb;
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
    }
    input[type="file"] {
      width: 100%;
      margin-bottom: 0.5rem;
      font-size: 0.9rem;
      padding: 0.5rem 0;
    }
    .hint {
      margin: -0.5rem 0 1rem 0;
      font-size: 0.8rem;
      color: #64748b;
    }
    .row { display: flex; gap: 1rem; align-items: flex-start; flex-wrap: wrap; }
    .row > * { flex: 1 1 auto; min-width: 0; }
    .checkbox-row {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      margin-bottom: 1rem;
    }
    .checkbox-row input { width: auto; margin: 0; }
    .checkbox-row span { font-weight: 500; font-size: 0.9rem; color: #334155; }
    button[type="submit"] {
      width: 100%;
      padding: 0.75rem 1.25rem;
      font-size: 1rem;
      font-weight: 600;
      border: none;
      border-radius: 8px;
      background: linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%);
      color: white;
      cursor: pointer;
      box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    button[type="submit"]:hover { background: linear-gradient(180deg, #1d4ed8 0%, #1e40af 100%); }
    button[type="submit"]:disabled { background: #94a3b8; cursor: not-allowed; box-shadow: none; }
    .progress {
      margin-top: 0;
      padding: 1.25rem;
      background: #f8fafc;
      border-radius: 10px;
      font-size: 0.9rem;
      display: none;
      border: 1px solid #e2e8f0;
    }
    .progress.visible { display: block; }
    .progress .phase { font-weight: 600; color: #334155; font-size: 0.95rem; }
    .progress .detail { color: #64748b; margin-top: 0.2rem; }
    .progress .eta { font-size: 0.82rem; color: #64748b; margin-top: 0.25rem; }
    .progress .bar {
      margin-top: 0.75rem;
      height: 8px;
      background: #e2e8f0;
      border-radius: 4px;
      overflow: hidden;
    }
    .progress .bar-fill {
      height: 100%;
      background: linear-gradient(90deg, #2563eb, #3b82f6);
      border-radius: 4px;
      transition: width 0.25s ease;
    }
    .progress.error .phase { color: #dc2626; }
    .progress.error .detail { color: #b91c1c; }
    .cancel-btn {
      width: auto;
      padding: 0.45rem 1rem;
      font-size: 0.875rem;
      font-weight: 500;
      margin-top: 0.75rem;
      background: #64748b;
      color: #fff;
      border: none;
      border-radius: 6px;
      cursor: pointer;
    }
    .cancel-btn:hover { background: #475569; }
    .download {
      margin-top: 0;
      display: none;
      padding: 1.25rem;
      background: #f0fdf4;
      border-radius: 10px;
      border: 1px solid #bbf7d0;
    }
    .download.visible { display: block; }
    .download p:first-child { font-weight: 600; color: #166534; margin: 0 0 0.75rem 0; }
    .download a {
      display: inline-block;
      padding: 0.5rem 1rem;
      background: #16a34a;
      color: white;
      text-decoration: none;
      border-radius: 6px;
      font-weight: 500;
      font-size: 0.9rem;
      margin-right: 0.5rem;
      margin-bottom: 0.5rem;
    }
    .download a:hover { background: #15803d; }
    .download .hint { margin-top: 0.75rem; margin-bottom: 0; }
    .log-section {
      margin-top: 1.5rem;
      background: #1e293b;
      border-radius: 10px;
      overflow: hidden;
      border: 1px solid #334155;
    }
    .log-header {
      padding: 0.5rem 0.75rem;
      font-size: 0.75rem;
      font-weight: 600;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      background: #0f172a;
      border-bottom: 1px solid #334155;
    }
    .log-content {
      padding: 0.75rem 1rem;
      font-family: 'Consolas', 'Monaco', monospace;
      font-size: 0.8rem;
      line-height: 1.5;
      color: #e2e8f0;
      max-height: 200px;
      overflow-y: auto;
    }
    .log-line { margin-bottom: 0.2rem; }
    .log-line.time { color: #64748b; font-size: 0.75rem; }
    .log-line.msg { color: #cbd5e1; }
    .log-line.err { color: #fca5a5; }
    .log-line.done { color: #86efac; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Flashcard Generator</h1>
    <p class="sub">Upload slides (PPTX or PDF) and get an Anki or <a href="https://knowt.com" target="_blank" rel="noopener">Knowt</a> deck. Uses cognitive principles for better recall.</p>

    <form id="form">
      <label for="file">Slide deck</label>
      <input type="file" id="file" name="file" accept=".pptx,.pdf" required>
      <p class="hint">PPTX or PDF only.</p>

      <label for="deck">Deck name</label>
      <input type="text" id="deck" name="deck" placeholder="Leave blank to use file name">

      <label for="provider">AI provider</label>
      <select id="provider" name="provider">
        <option value="ollama" selected>Ollama — free, local</option>
        <option value="gemini">Gemini — API key</option>
      </select>
      <p class="hint">Start the Ollama app first if you use it.</p>

      <label for="ollamaModel" id="ollamaModelLabel">Ollama model</label>
      <select id="ollamaModel" name="ollama_model">
        <option value="">Loading…</option>
      </select>
      <p class="hint" id="ollamaModelHint">Only when provider is Ollama.</p>

      <label for="workers">Parallel chunks</label>
      <select id="workers" name="workers">
        <option value="1">1 (sequential)</option>
        <option value="2" selected>2 (faster)</option>
        <option value="3">3</option>
      </select>
      <p class="hint">More chunks in parallel = faster, but more load on your PC.</p>

      <div class="checkbox-row">
        <input type="checkbox" id="useChapters" name="use_chapters" value="1">
        <span>Use chapter detection (PPTX only → subdecks)</span>
      </div>

      <button type="submit" id="submit">Generate deck</button>
    </form>

    <div id="progress" class="progress">
      <div class="phase" id="phase">—</div>
      <div class="detail" id="detail"></div>
      <div class="eta" id="eta"></div>
      <div class="bar"><div class="bar-fill" id="barFill" style="width: 0%"></div></div>
      <button type="button" id="cancelBtn" class="cancel-btn">Cancel</button>
    </div>

    <div id="download" class="download">
      <p>Your deck is ready.</p>
      <a id="downloadAnki" href="#">Download for Anki (.apkg)</a>
      <a id="downloadKnowt" href="#">Download for Knowt (.csv)</a>
      <p class="hint">Downloads are kept for 10 minutes; save the files locally.</p>
    </div>
  </div>

  <div class="log-section">
    <div class="log-header">Log</div>
    <div id="logContent" class="log-content"></div>
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
    const cancelBtn = document.getElementById('cancelBtn');
    const providerEl = document.getElementById('provider');
    const ollamaModelEl = document.getElementById('ollamaModel');
    const ollamaModelLabel = document.getElementById('ollamaModelLabel');
    const ollamaModelHint = document.getElementById('ollamaModelHint');
    const phaseLabels = { extracting: 'Reading slides', chunking: 'Preparing content', generating: 'Generating cards', exporting: 'Building deck', exporting_subdecks: 'Building subdecks', done: 'Done', error: 'Error', starting: 'Starting...' };
    let etaStartTime = null;
    const logContent = document.getElementById('logContent');
    let lastLogKey = '';

    function logMsg(text, type) {
      const line = document.createElement('div');
      line.className = 'log-line ' + (type || 'msg');
      const time = new Date().toLocaleTimeString('en-GB', { hour12: false });
      line.innerHTML = '<span class="time">[' + time + ']</span> ' + (text || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      logContent.appendChild(line);
      logContent.scrollTop = logContent.scrollHeight;
    }
    function logClear() {
      logContent.innerHTML = '';
      lastLogKey = '';
    }

    function setOllamaModelVisible(visible) {
      ollamaModelLabel.style.display = visible ? 'block' : 'none';
      ollamaModelEl.style.display = visible ? 'block' : 'none';
      ollamaModelHint.style.display = visible ? 'block' : 'none';
    }
    function setCancelVisible(visible) {
      cancelBtn.style.display = visible ? 'block' : 'none';
    }
    cancelBtn.style.display = 'none';

    function showProgress(phase, message, current, total, isError) {
      progressEl.classList.add('visible');
      if (isError) progressEl.classList.add('error');
      else progressEl.classList.remove('error');
      phaseEl.textContent = phaseLabels[phase] || phase || 'Processing...';
      detailEl.textContent = message || '';
      if (total && total > 0 && current != null && phase === 'generating') {
        if (!etaStartTime) etaStartTime = Date.now();
        // Only show ETA after at least 2 chunks done (else estimate climbs then drops per chunk)
        if (current >= 2) {
          const elapsed = (Date.now() - etaStartTime) / 1000;
          const remaining = (elapsed / current) * (total - current);
          if (remaining > 60) etaEl.textContent = 'About ' + Math.ceil(remaining / 60) + ' min left';
          else if (remaining > 5) etaEl.textContent = 'About ' + Math.ceil(remaining) + ' sec left';
          else etaEl.textContent = '';
        } else {
          etaEl.textContent = '';
        }
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
      const useChapters = document.getElementById('useChapters').checked;
      const ollamaModel = document.getElementById('ollamaModel').value || '';
      const formData = new FormData();
      formData.append('file', fileInput.files[0]);
      formData.append('deck', deck);
      formData.append('provider', provider);
      formData.append('use_chapters', useChapters ? '1' : '0');
      formData.append('ollama_model', ollamaModel);

      submitBtn.disabled = true;
      progressEl.classList.remove('visible');
      downloadEl.classList.remove('visible');
      setCancelVisible(true);
      logClear();
      logMsg('Uploading...', 'msg');
      showProgress('Uploading...', '', 0, 0);

      const workers = document.getElementById('workers').value || '2';
      formData.append('workers', workers);

      const r = await fetch('/generate', { method: 'POST', body: formData });
      const data = await r.json();
      if (!r.ok) {
        logMsg('Error: ' + (data.error || 'Upload failed'), 'err');
        showProgress('Error', data.error || 'Upload failed', null, null, true);
        submitBtn.disabled = false;
        return;
      }

      currentJobId = data.job_id;
      logMsg('Job started. Polling status...', 'msg');

      const poll = setInterval(async () => {
        const s = await fetch('/status/' + currentJobId);
        const sdata = await s.json();
        const phase = sdata.phase || 'Processing...';
        const message = sdata.message || '';
        const current = sdata.current;
        const total = sdata.total;
        const isError = sdata.phase === 'error';
        const logKey = phase + '|' + message + '|' + (current || '') + '|' + (total || '');
        if (logKey !== lastLogKey) {
          lastLogKey = logKey;
          const phaseLabel = phaseLabels[phase] || phase;
          const detail = message ? (phaseLabel + ' — ' + message) : phaseLabel;
          if (sdata.phase === 'error') logMsg(detail, 'err');
          else if (sdata.phase === 'done') logMsg('Done. ' + (message || 'Deck ready.'), 'done');
          else logMsg(detail, 'msg');
        }
        showProgress(phase, message, current, total, isError);

        if (sdata.phase === 'done') {
          clearInterval(poll);
          submitBtn.disabled = false;
          setCancelVisible(false);
          showDownload(sdata.filename || 'deck.apkg', sdata.csv_filename || 'deck.csv');
        } else if (sdata.phase === 'error') {
          clearInterval(poll);
          submitBtn.disabled = false;
          setCancelVisible(false);
        }
      }, 600);
    });
    logMsg('Ready. Upload a file and click Generate deck.', 'msg');

    (async function loadOllamaModels() {
      try {
        const r = await fetch('/api/ollama-models');
        const data = await r.json();
        const models = data.models || [];
        const defaultModel = data.default || 'llama3.2:latest';
        ollamaModelEl.innerHTML = '';
        if (models.length === 0) {
          const opt = document.createElement('option');
          opt.value = defaultModel;
          opt.textContent = defaultModel + ' (default)';
          ollamaModelEl.appendChild(opt);
        } else {
          for (const m of models) {
            const opt = document.createElement('option');
            opt.value = m;
            opt.textContent = m;
            if (m === defaultModel) opt.selected = true;
            ollamaModelEl.appendChild(opt);
          }
        }
      } catch (e) {
        ollamaModelEl.innerHTML = '<option value="llama3.2:latest">llama3.2:latest (default)</option>';
      }
      setOllamaModelVisible(providerEl.value === 'ollama');
    })();
    providerEl.addEventListener('change', () => setOllamaModelVisible(providerEl.value === 'ollama'));

    cancelBtn.addEventListener('click', async () => {
      if (!currentJobId) return;
      try {
        await fetch('/cancel/' + currentJobId, { method: 'POST' });
        cancelBtn.disabled = true;
        cancelBtn.textContent = 'Cancelling…';
      } catch (e) {}
    });
  </script>
</body>
</html>
"""


def run_job(job_id: str, input_path: Path, deck_name: str, provider: str, out_path: Path, out_csv_path: Path, use_chapters: bool = False, model: str | None = None, workers: int = CONCURRENT_CHUNKS):
    cancel_check = lambda: _is_cancelled(job_id)
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
            use_chapters=use_chapters,
            cancel_check=cancel_check,
            model=model if provider == "ollama" else None,
            workers=workers,
        )
        with _jobs_lock:
            if job_id in jobs:
                jobs[job_id]["phase"] = "done"
                jobs[job_id]["path"] = str(out_path)
                jobs[job_id]["filename"] = out_path.name
                jobs[job_id]["csv_path"] = str(csv_path) if csv_path else None
                jobs[job_id]["csv_filename"] = csv_path.name if csv_path else None
        # Schedule cleanup so user has time to download; then temp dir is removed
        timer = threading.Timer(JOB_RETENTION_MINUTES * 60.0, _cleanup_job, [job_id])
        timer.daemon = True
        timer.start()
    except Exception as e:
        with _jobs_lock:
            if job_id in jobs:
                jobs[job_id]["phase"] = "error"
                jobs[job_id]["message"] = str(e)
        timer = threading.Timer(JOB_RETENTION_MINUTES * 60.0, _cleanup_job, [job_id])
        timer.daemon = True
        timer.start()


@app.route("/cancel/<job_id>", methods=["POST"])
def cancel_job(job_id):
    with _jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404
    if job.get("phase") in ("done", "error"):
        return jsonify({"ok": True, "message": "Job already finished"}), 200
    with _jobs_lock:
        jobs[job_id]["cancelled"] = True
    return jsonify({"ok": True, "message": "Cancel requested"})


@app.route("/api/ollama-models")
def ollama_models():
    """Return list of installed Ollama models and default. Used to populate the model dropdown."""
    try:
        url = (OLLAMA_URL or "").rstrip("/") + "/api/tags"
        r = requests.get(url, timeout=3)
        r.raise_for_status()
        data = r.json()
        models = []
        for m in (data.get("models") or []):
            name = m.get("name") if isinstance(m, dict) else getattr(m, "name", None)
            if name:
                models.append(name)
        return jsonify({"models": sorted(models), "default": OLLAMA_MODEL or "llama3.2:latest"})
    except Exception:
        return jsonify({"models": [], "default": OLLAMA_MODEL or "llama3.2:latest"})


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
    safe_name = secure_filename(Path(f.filename).name) or ("upload" + ext)
    deck_name = (request.form.get("deck") or "").strip() or Path(f.filename).stem
    provider = request.form.get("provider") or "ollama"
    use_chapters = (request.form.get("use_chapters") or "").strip() == "1"
    ollama_model = (request.form.get("ollama_model") or "").strip() or None
    try:
        workers = int((request.form.get("workers") or "").strip() or CONCURRENT_CHUNKS)
        workers = max(1, min(4, workers))
    except (TypeError, ValueError):
        workers = CONCURRENT_CHUNKS
    if provider == "gemini" and not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY not set. Use Ollama or set the key."}), 400

    job_id = str(uuid.uuid4())
    tmp = tempfile.mkdtemp()
    input_path = Path(tmp) / safe_name
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
            "cancelled": False,
        }
    t = threading.Thread(target=run_job, args=(job_id, input_path, deck_name, provider, out_path, out_csv_path, use_chapters, ollama_model, workers))
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
