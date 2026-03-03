"""Configuration for the flashcard generator."""

import os

# Ollama (local LLM). Use 127.0.0.1 on Windows to avoid localhost resolving to IPv6.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_CHAT_PATH = "/api/chat"
OLLAMA_GENERATE_PATH = "/api/generate"
OLLAMA_OPENAI_CHAT_PATH = "/v1/chat/completions"  # OpenAI-compatible; some Windows builds expose only this
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:latest")

# Chunking
CHUNK_SIZE = 6
CHUNK_OVERLAP = 1

# Gemini (optional cloud provider)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"

# Parser
MAX_RETRIES = 3

# Parallel chunk processing (1 = sequential, 2+ = run N chunks at a time). Conservative default to avoid overloading Ollama/GPU.
CONCURRENT_CHUNKS = 2
