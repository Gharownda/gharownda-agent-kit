from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--patch", required=True)
    parser.add_argument("--verification", required=True)
    parser.add_argument("--model-key", default="qwen3-14b-q4")
    parser.add_argument("--output", required=True)
    parser.parse_args()
    raise SystemExit("reviewer bootstrap incomplete")


if __name__ == "__main__":
    main()
