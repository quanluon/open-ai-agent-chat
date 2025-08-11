#!/usr/bin/env python3
"""
Ask a question against the OptiBot Assistant.

Usage:
  OPENAI_API_KEY=... python scripts/ask_assistant.py \
    --question "How do I add a YouTube video?" \
    --assistant-id asst_your_assistant_id_here
"""

from __future__ import annotations

import argparse
import json
import os

from typing import Optional
from dotenv import load_dotenv
load_dotenv()

try:
    from openai import OpenAI
except Exception as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: openai. Run: pip install -r requirements.txt") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ask a question to the OptiBot Assistant.")
    parser.add_argument("--question", required=True, help="User question")
    parser.add_argument("--assistant-id", required=True, help="Assistant ID")
    return parser.parse_args()


def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY environment variable is not set.")

    args = parse_args()
    assistant_id = args.assistant_id

    client = OpenAI()

    thread = client.beta.threads.create()
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=args.question,
    )

    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant_id,
    )

    run = client.beta.threads.runs.poll(
        thread_id=thread.id,
        run_id=run.id,
        poll_interval_ms=1000,
    )

    messages = client.beta.threads.messages.list(thread_id=thread.id)
    # Print assistant response and citations if available
    for m in reversed(messages.data):
        if m.role == "assistant":
            print("\n=== Assistant Response ===\n")
            for c in m.content:
                if getattr(c, "type", None) == "text":
                    print(c.text.value)
                    if c.text.annotations:
                        print("\nCitations:")
                        for ann in c.text.annotations:
                            file_path = getattr(getattr(ann, "file_path", None), "file_path", None)
                            if file_path:
                                print(f"- {file_path}")
            break


if __name__ == "__main__":
    main()


