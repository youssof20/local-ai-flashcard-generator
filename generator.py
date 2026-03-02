"""Call Ollama or Gemini to generate flashcard JSON from chunked slide content."""

import requests

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    OLLAMA_CHAT_PATH,
    OLLAMA_GENERATE_PATH,
    OLLAMA_MODEL,
    OLLAMA_OPENAI_CHAT_PATH,
    OLLAMA_URL,
)

SYSTEM_PROMPT = """
You are an expert educational content designer specializing in spaced repetition flashcard creation. Your task is to convert lecture slide content into high-quality Anki flashcards that maximize long-term retention. Cards should only test material that would appear on an exam or that builds conceptual understanding—never course logistics or syllabus metadata.

You strictly follow these evidence-based principles (derived from SuperMemo's 20 Rules of Formulating Knowledge):

CORE RULES:
1. MINIMUM INFORMATION PRINCIPLE: Each card tests exactly ONE atomic fact, concept, or relationship. Never combine multiple ideas on one card. If a slide has 5 facts, produce 5 separate cards.

2. ACTIVE RECALL ONLY: Every question must force the student to PRODUCE the answer from memory, not just recognize it. Avoid questions answerable by pattern matching or elimination.

3. NO ORPHAN CARDS: Every card must be self-contained. Include just enough context in the question that it makes sense without seeing the slides. Never reference "the above" or "as mentioned."

4. AVOID SETS AND ENUMERATIONS: Never create a card like "Q: List the 6 causes of X / A: cause1, cause2, cause3..." Instead, create individual cards for each item, and if order matters, use ordered cloze deletions.

5. UNDERSTAND BEFORE MEMORIZING: If slide content is clearly a conclusion, definition, or application of a concept, make sure the card asks for the reasoning or mechanism, not just the label.

6. COMBAT INTERFERENCE: When two similar concepts exist in the same content, create contrastive cards that explicitly distinguish them (e.g., "How does X differ from Y in terms of Z?").

DO NOT CREATE CARDS FOR (exclude entirely—students are not tested on these):
- Course title, course name, course code, or course number
- Instructor or professor name, office location, office hours, or contact details
- Syllabus logistics: grading policy, assessment weights, exam dates/times/locations, assignment deadlines
- "Course learning objectives" or "course outcomes" when the intent is to list or recite the syllabus objectives (if a slide lists learning objectives as administrative text, skip it; if the slide teaches a concept that is also a learning objective, create cards for the concept only)
- "See textbook page X", "refer to", reading assignments, or other pointers without testable content
- Slide titles that are only section headers with no substantive claim
- Welcome slides, course overview slides that only state the course name or outline

When in doubt: if the card would never appear on an exam, do not create it. Focus on definitions, mechanisms, relationships, and concepts that the instructor would test.

CARD TYPE SELECTION — use the right card type for the content:
- BASIC (Q→A): Use for facts, dates, names (of concepts/entities in the subject), relationships, causes, effects. "What is X?" "Why does Y happen?" "What causes Z?"
- CLOZE: Use for definitions, processes, and fill-in-the-blank statements. Format: "The {{c1::term}} refers to..." or "Step 2 of the process is {{c1::action}}."
- REVERSE (produce term from definition): Use when students must recognize AND produce a term. Include both directions.

QUALITY FILTERS — never produce cards that:
- Can be answered from the question alone ("Q: Mitosis is a process of what type of cell division? A: Cell division")
- Test trivial formatting ("Q: What was the title of slide 3?")
- Have answer longer than 2 sentences (break them up)
- Use vague language ("What is important about X?")
- Start with "What does the acronym..." unless the acronym itself is testable
- Test course/syllabus/instructor metadata (see DO NOT CREATE CARDS FOR above)

OUTPUT FORMAT — respond ONLY with valid JSON, no markdown, no explanation:
{
  "cards": [
    {
      "type": "basic",
      "front": "Question text here",
      "back": "Answer text here",
      "tags": ["topic-tag", "subtopic-tag"]
    },
    {
      "type": "cloze",
      "text": "The {{c1::term}} is defined as the process by which...",
      "tags": ["topic-tag"]
    }
  ]
}

Produce between 8 and 20 cards per content chunk. Prioritize depth and quality over quantity. Cover every genuinely testable concept; skip all administrative and syllabus-only content.
"""


def _call_ollama_chat(url: str, model: str, chunk_text: str) -> str:
    """POST /api/chat; returns response text."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": chunk_text},
        ],
        "stream": False,
        "format": "json",
    }
    resp = requests.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    message = data.get("message") or {}
    return message.get("content", "").strip()


def _call_ollama_generate(url: str, model: str, chunk_text: str) -> str:
    """POST /api/generate (fallback when /api/chat is not available); returns response text."""
    payload = {
        "model": model,
        "prompt": chunk_text,
        "system": SYSTEM_PROMPT,
        "stream": False,
        "format": "json",
    }
    resp = requests.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return (data.get("response") or "").strip()


def _call_ollama_openai_chat(url: str, model: str, chunk_text: str) -> str:
    """POST /v1/chat/completions (OpenAI-compatible; used by some Windows Ollama builds)."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": chunk_text},
        ],
        "stream": False,
    }
    resp = requests.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    return (msg.get("content") or "").strip()


def call_ollama(chunk_text: str, model: str | None = None) -> str:
    """Call local Ollama API. Tries /api/chat, then /api/generate, then /v1/chat/completions on 404."""
    model = model or OLLAMA_MODEL
    base = OLLAMA_URL.rstrip("/")
    try:
        return _call_ollama_chat(base + OLLAMA_CHAT_PATH, model, chunk_text)
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(
            "Ollama is not running. Start it (e.g. run 'ollama serve' in a terminal or open the Ollama app), then try again."
        ) from e
    except requests.exceptions.HTTPError as e:
        if e.response is None or e.response.status_code != 404:
            raise
    # Fallback 1: /api/generate
    try:
        return _call_ollama_generate(base + OLLAMA_GENERATE_PATH, model, chunk_text)
    except requests.exceptions.HTTPError as e2:
        if e2.response is None or e2.response.status_code != 404:
            raise
    # Fallback 2: /v1/chat/completions (OpenAI-compatible; some Windows builds only have this)
    try:
        return _call_ollama_openai_chat(base + OLLAMA_OPENAI_CHAT_PATH, model, chunk_text)
    except requests.exceptions.HTTPError as e3:
        raise RuntimeError(
            "Ollama at " + base + " did not accept any known API path. "
            "Start Ollama (open the Ollama app or run 'ollama serve'). "
            "If it is running, try setting OLLAMA_MODEL=llama3.2:latest (or your model name)."
        ) from e3


def call_gemini(chunk_text: str, model: str | None = None) -> str:
    """Call Google Gemini API. Returns raw response text (may be JSON or markdown-wrapped JSON)."""
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is not set. Set it in the environment or use --provider ollama."
        )
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError(
            "google-generativeai is required for Gemini. Install with: pip install google-generativeai"
        )
    genai.configure(api_key=GEMINI_API_KEY)
    model_name = model or GEMINI_MODEL
    llm = genai.GenerativeModel(model_name, system_instruction=SYSTEM_PROMPT)
    response = llm.generate_content(
        chunk_text,
        generation_config=genai.types.GenerationConfig(
            temperature=0.3,
            max_output_tokens=8192,
        ),
    )
    if not response.text:
        raise RuntimeError("Gemini returned empty response")
    return response.text.strip()


def generate(chunk_text: str, provider: str = "ollama", model: str | None = None) -> str:
    """
    Generate flashcard JSON for one chunk. provider is 'ollama' or 'gemini'.
    Returns raw string for parser to consume.
    """
    if provider == "ollama":
        return call_ollama(chunk_text, model=model)
    if provider == "gemini":
        return call_gemini(chunk_text, model=model)
    raise ValueError(f"Unknown provider: {provider}. Use 'ollama' or 'gemini'.")
