#!/usr/bin/env python3
"""
Bootstrap script to:
- Create an OpenAI Vector Store with a chosen chunking strategy
- Upload Markdown files via API (no UI drag-and-drop)
- Create or update the OptiBot Assistant and attach the Vector Store
- Log how many files and estimated chunks were embedded

Usage:
  OPENAI_API_KEY=... python scripts/bootstrap_optibot.py \
    --docs-dir /absolute/path/to/test/articles \
    --assistant-name OptiBot \
    --model gpt-4o-mini \
    --chunk-size 800 \
    --chunk-overlap 200

Notes:
- "Estimated" chunks are computed client-side using the same formula as the static chunking strategy to provide a clear log.
- The Vector Store also chunks server-side using the same parameters; the server-side stats may differ slightly for edge cases.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import List, Tuple

try:
    from openai import OpenAI
except Exception as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: openai. Run: pip install -r requirements.txt") from exc

try:
    import tiktoken
except Exception as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: tiktoken. Run: pip install -r requirements.txt") from exc


DEFAULT_MODEL = "gpt-4o-mini"
STATE_FILE = "optibot_state.json"


SYSTEM_PROMPT = (
    "You are OptiBot, the customer-support bot for OptiSigns.com.\n"
    "• Tone: helpful, factual, concise.\n"
    "• Only answer using the uploaded docs.\n"
    "• Max 5 bullet points; else link to the doc.\n"
    "• Cite up to 3 \"Article URL:\" lines per reply."
)


def discover_markdown_files(docs_dir: Path) -> List[Path]:
    patterns = ("**/*.md", "**/*.mdx")
    files: List[Path] = []
    for pattern in patterns:
        files.extend(sorted(docs_dir.glob(pattern)))
    return [f for f in files if f.is_file()]


def estimate_chunks_for_text(token_count: int, chunk_size: int, chunk_overlap: int) -> int:
    if token_count <= 0:
        return 0
    if token_count <= chunk_size:
        return 1
    stride = max(1, chunk_size - chunk_overlap)
    remaining = max(0, token_count - chunk_size)
    additional = math.ceil(remaining / stride)
    return 1 + additional


def tokenize_and_estimate_file_chunks(path: Path, encoding_name: str, chunk_size: int, chunk_overlap: int) -> Tuple[int, int]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    encoding = tiktoken.get_encoding(encoding_name)
    token_count = len(encoding.encode(text))
    chunk_estimate = estimate_chunks_for_text(token_count, chunk_size, chunk_overlap)
    return token_count, chunk_estimate


def create_vector_store_with_chunking(client: OpenAI, name: str, chunk_size: int, chunk_overlap: int) -> str:
    vector_store = client.vector_stores.create(
        name=name,
        chunking_strategy={
            "type": "static",
            "max_chunk_size_tokens": chunk_size,
            "chunk_overlap_tokens": chunk_overlap,
        },
    )
    return vector_store.id


def upload_files_to_vector_store(client: OpenAI, vector_store_id: str, file_paths: List[Path]) -> None:
    file_streams = []
    try:
        for p in file_paths:
            file_streams.append((p.name, p.open("rb")))
        client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store_id,
            files=[fs for _, fs in file_streams],
        )
    finally:
        for _, fs in file_streams:
            try:
                fs.close()
            except Exception:
                pass


def create_or_update_assistant(
    client: OpenAI,
    assistant_name: str,
    model: str,
    vector_store_id: str,
    existing_assistant_id: str | None = None,
) -> str:
    tools = [{"type": "file_search"}]
    tool_resources = {"file_search": {"vector_store_ids": [vector_store_id]}}

    if existing_assistant_id:
        assistant = client.beta.assistants.update(
            assistant_id=existing_assistant_id,
            name=assistant_name,
            model=model,
            instructions=SYSTEM_PROMPT,
            tools=tools,
            tool_resources=tool_resources,
        )
        return assistant.id

    assistant = client.beta.assistants.create(
        name=assistant_name,
        model=model,
        instructions=SYSTEM_PROMPT,
        tools=tools,
        tool_resources=tool_resources,
    )
    return assistant.id


def write_state_file(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap OptiBot with Vector Store and Assistant.")
    parser.add_argument("--docs-dir", required=True, type=Path, help="Absolute path to directory containing Markdown docs")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model for the Assistant (default: gpt-4o-mini)")
    parser.add_argument("--assistant-name", default="OptiBot", help="Assistant name")
    parser.add_argument("--assistant-id", default=None, help="Existing Assistant ID to update instead of creating a new one")
    parser.add_argument("--vector-store-name", default="OptiSigns Knowledge Base", help="Vector Store name")
    parser.add_argument("--chunk-size", type=int, default=800, help="Static chunk size in tokens")
    parser.add_argument("--chunk-overlap", type=int, default=200, help="Static chunk overlap in tokens")
    parser.add_argument("--encoding", default="cl100k_base", help="Tokenizer encoding name for token estimation")
    parser.add_argument("--state-out", type=Path, default=Path(STATE_FILE), help="Path to write state JSON")
    return parser.parse_args()


def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY environment variable is not set.")

    args = parse_args()
    docs_dir: Path = args.docs_dir
    if not docs_dir.is_absolute():
        raise SystemExit("--docs-dir must be an absolute path.")

    client = OpenAI()

    # Discover files
    files = discover_markdown_files(docs_dir)
    if not files:
        raise SystemExit(f"No Markdown files found in {docs_dir}")

    # Estimate tokens and chunks
    total_tokens = 0
    total_chunks = 0
    per_file_stats = []
    for f in files:
        tokens, chunks = tokenize_and_estimate_file_chunks(
            f, args.encoding, args.chunk_size, args.chunk_overlap
        )
        per_file_stats.append({"file": str(f), "tokens": tokens, "estimated_chunks": chunks})
        total_tokens += tokens
        total_chunks += chunks

    # Create Vector Store and upload files
    vector_store_id = create_vector_store_with_chunking(
        client, args.vector_store_name, args.chunk_size, args.chunk_overlap
    )
    upload_files_to_vector_store(client, vector_store_id, files)

    # Create or update Assistant and attach the vector store
    assistant_id = create_or_update_assistant(
        client=client,
        assistant_name=args.assistant_name,
        model=args.model,
        vector_store_id=vector_store_id,
        existing_assistant_id=args.assistant_id,
    )

    state = {
        "assistant_id": assistant_id,
        "vector_store_id": vector_store_id,
        "model": args.model,
        "assistant_name": args.assistant_name,
        "vector_store_name": args.vector_store_name,
        "chunk_size": args.chunk_size,
        "chunk_overlap": args.chunk_overlap,
        "encoding": args.encoding,
        "docs_dir": str(docs_dir),
        "file_count": len(files),
        "estimated_total_tokens": total_tokens,
        "estimated_total_chunks": total_chunks,
        "per_file": per_file_stats,
    }
    write_state_file(args.state_out, state)

    print("=== OptiBot bootstrap complete ===")
    print(f"Assistant ID: {assistant_id}")
    print(f"Vector Store ID: {vector_store_id}")
    print(f"Files uploaded: {len(files)}")
    print(f"Estimated chunks (client-side): {total_chunks}")
    print(f"State written to: {args.state_out}")


if __name__ == "__main__":
    main()


