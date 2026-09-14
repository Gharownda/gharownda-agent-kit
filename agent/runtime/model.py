from __future__ import annotations

import json
import os
from pathlib import Path

from llama_cpp import Llama

RUNTIME_ROOT = Path(__file__).resolve().parents[2]


def load_gguf(model_key: str, *, context: int | None = None) -> tuple[dict, Llama]:
    manifest = json.loads((RUNTIME_ROOT / "benchmark" / "models.json").read_text())
    entry = next((item for item in manifest["active"] if item["key"] == model_key), None)
    if not entry:
        raise SystemExit(f"Unknown model key: {model_key}")
    context = context or int(os.environ.get("AGENT_CONTEXT_TOKENS", "8192"))
    llm = Llama.from_pretrained(
        repo_id=entry["repo"],
        filename=entry["file"],
        n_ctx=context,
        n_threads=max(1, min(4, os.cpu_count() or 1)),
        n_batch=128,
        verbose=False,
    )
    return entry, llm
