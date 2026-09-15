from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path


def extract_html(raw: str) -> str:
    fenced = re.search(r"```(?:html)?\s*(.*?)```", raw, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        raw = fenced.group(1)
    start = raw.lower().find("<!doctype html")
    if start < 0:
        start = raw.lower().find("<html")
    if start < 0:
        raise ValueError("model output contains no HTML document")
    html = raw[start:].strip()
    if "</html>" not in html.lower():
        raise ValueError("model output does not contain a complete HTML document")
    end = html.lower().rfind("</html>") + len("</html>")
    return html[:end]


def run_model(model_ref: str, prompt: str) -> tuple[str, float]:
    command = [
        "llama",
        "cli",
        "-hf",
        model_ref,
        "-p",
        "/no_think\n" + prompt,
        "-n",
        "1800",
        "--temp",
        "0",
        "--no-display-prompt",
    ]
    started = time.perf_counter()
    completed = subprocess.run(command, text=True, capture_output=True, timeout=1500, check=False)
    elapsed = time.perf_counter() - started
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout)[-3000:])
    return completed.stdout, elapsed


def render(html_path: Path, output_dir: Path) -> None:
    chrome = os.environ.get("CHROME_BIN", "google-chrome")
    url = html_path.resolve().as_uri()
    for name, size in (("mobile", "390,844"), ("desktop", "1280,900")):
        target = output_dir / f"{html_path.stem}-{name}.png"
        subprocess.run(
            [chrome, "--headless", "--no-sandbox", "--disable-gpu", f"--window-size={size}", f"--screenshot={target}", url],
            text=True,
            capture_output=True,
            timeout=120,
            check=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-key", required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    models = json.loads((root / "models.json").read_text())["candidates"]
    model = next((item for item in models if item["key"] == args.model_key), None)
    if not model:
        raise SystemExit(f"unknown UI model: {args.model_key}")

    cases = json.loads((root / "cases.json").read_text())["cases"]
    case = next((item for item in cases if item["id"] == args.case), None)
    if not case:
        raise SystemExit(f"unknown UI case: {args.case}")

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    record = {"case": case["id"], "model": args.model_key, "valid": False, "elapsed_seconds": None, "error": None}
    try:
        raw, elapsed = run_model(model["hf_ref"], case["prompt"])
        (output / f"{case['id']}.raw.txt").write_text(raw)
        html = extract_html(raw)
        html_path = output / f"{case['id']}.html"
        html_path.write_text(html)
        missing = [text for text in case.get("required_text", []) if text.lower() not in html.lower()]
        if missing:
            raise ValueError(f"missing required text: {missing}")
        render(html_path, output)
        record.update(valid=True, elapsed_seconds=round(elapsed, 2))
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"

    (output / "results.json").write_text(json.dumps({"model": model, "results": [record]}, indent=2))
    if not record["valid"]:
        raise SystemExit("UI benchmark case failed")


if __name__ == "__main__":
    main()
