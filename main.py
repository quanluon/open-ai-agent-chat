#!/usr/bin/env python3
"""
Daily job orchestrator:
- Re-scrapes OptiSigns support articles to Markdown
- Detects new/updated content via SHA-256
- Uploads only the delta to an OpenAI Vector Store
- Attaches/ensures the OptiBot Assistant is configured with the Vector Store
- Logs counts (added, updated, skipped, removed) and writes last run artifact

Environment variables (optional overrides):
- OPENAI_API_KEY: required
- ASSISTANT_ID: required
- MODEL (default: gpt-4o-mini)
- VECTOR_STORE_ID: required
- CHUNK_SIZE (default: 800)
- CHUNK_OVERLAP (default: 200)
- LOCALE (default: en-us)
- MAX_ARTICLES (default: 45)
- ARTICLES_DIR (default: ./articles)

State files:
- optibot_state.json: persists assistant/vector store IDs and configuration
- sync_state.json: tracks file hashes and OpenAI file IDs for delta sync
- runs/last_run.json: latest run summary
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from openai import OpenAI

from dotenv import load_dotenv
load_dotenv()



ROOT = Path(__file__).resolve().parent
ARTICLES_DIR = Path(os.environ.get("ARTICLES_DIR", ROOT / "articles")).resolve()
SYNC_STATE_FILE = ROOT / "sync_state.json"
RUNS_DIR = ROOT / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_scraper(locale: str, max_articles: int) -> None:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "scrape_to_markdown.py"),
        "--locale",
        locale,
        "--max-articles",
        str(max_articles),
        "--out-dir",
        str(ARTICLES_DIR),
    ]
    print(f"Running scraper: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(res.stdout)
    if res.returncode != 0:
        print(res.stderr)
        raise SystemExit(f"Scraper failed with exit code {res.returncode}")


def discover_markdown_files(directory: Path) -> List[Path]:
    return sorted([p for p in directory.glob("*.md") if p.is_file()])


def ensure_assistant_and_vector_store(client: OpenAI, model: str, assistant_id: str, vector_store_id: str, chunk_size: int, chunk_overlap: int) -> Tuple[str, str]:
    # Validate that IDs are provided
    if not assistant_id:
        raise SystemExit("ASSISTANT_ID environment variable is required")
    if not vector_store_id:
        raise SystemExit("VECTOR_STORE_ID environment variable is required")

    # Verify assistant exists and update if needed
    try:
        asst = client.beta.assistants.retrieve(assistant_id=assistant_id)
        # Update assistant to ensure it's properly configured
        asst = client.beta.assistants.update(
            assistant_id=assistant_id,
            model=model,
            instructions=(
                "You are OptiBot, the customer-support bot for OptiSigns.com.\n"
                "• Tone: helpful, factual, concise.\n"
                "• Only answer using the uploaded docs.\n"
                "• Max 5 bullet points; else link to the doc.\n"
                "• Cite up to 3 \"Article URL:\" lines per reply."
            ),
            tools=[{"type": "file_search"}],
            tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}},
        )
    except Exception as e:
        raise SystemExit(f"Failed to retrieve/update assistant {assistant_id}: {e}")

    # Verify vector store exists
    try:
        vs = client.vector_stores.retrieve(vector_store_id=vector_store_id)
    except Exception as e:
        raise SystemExit(f"Failed to retrieve vector store {vector_store_id}: {e}")

    return assistant_id, vector_store_id


def upload_delta(client: OpenAI, vector_store_id: str, files_to_add: List[Path], files_to_update: List[Tuple[Path, str]]) -> Tuple[Dict[str, str], List[str]]:
    """Upload added/updated files.

    Returns: (new_file_id_by_path, deleted_file_ids)
    """
    new_ids: Dict[str, str] = {}
    deleted_ids: List[str] = []

    # Remove old vector store files for updates
    for path, old_file_id in files_to_update:
        try:
            client.vector_stores.files.delete(vector_store_id=vector_store_id, file_id=old_file_id)
            client.files.delete(file_id=old_file_id)
            deleted_ids.append(old_file_id)
        except Exception:
            pass

    # Upload and attach new/updated files
    upload_paths = files_to_add + [p for p, _ in files_to_update]
    for p in upload_paths:
        with p.open("rb") as f:
            uploaded = client.files.create(file=f, purpose="assistants")
        client.vector_stores.files.create(vector_store_id=vector_store_id, file_id=uploaded.id)
        new_ids[str(p)] = uploaded.id
    return new_ids, deleted_ids


def main() -> None:
    """Main orchestrator for the daily OptiBot sync job."""
    start_time = datetime.now(timezone.utc)
    
    print("=" * 60)
    print("OptiBot Daily Sync Job")
    print(f"Started at: {start_time.isoformat()}")
    print("=" * 60)
    
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")

    # Load configuration from environment
    assistant_id = os.environ.get("ASSISTANT_ID")
    model = os.environ.get("MODEL", "gpt-4o-mini")
    vector_store_id = os.environ.get("VECTOR_STORE_ID")
    chunk_size = int(os.environ.get("CHUNK_SIZE", "800"))
    chunk_overlap = int(os.environ.get("CHUNK_OVERLAP", "200"))
    locale = os.environ.get("LOCALE", "en-us")
    max_articles = int(os.environ.get("MAX_ARTICLES", "5"))

    print(f"Configuration:")
    print(f"  Assistant ID: {assistant_id}")
    print(f"  Model: {model}")
    print(f"  Vector Store ID: {vector_store_id}")
    print(f"  Chunk Size: {chunk_size}")
    print(f"  Chunk Overlap: {chunk_overlap}")
    print(f"  Locale: {locale}")
    print(f"  Max Articles: {max_articles}")
    print(f"  Articles Dir: {ARTICLES_DIR}")
    print()

    client = OpenAI()

    try:
        # 1) Scrape & normalize articles
        print("Step 1: Scraping articles from Zendesk API...")
        run_scraper(locale=locale, max_articles=max_articles)
        print("✓ Scraping completed\n")

        # 2) Ensure Assistant & Vector Store exist
        print("Step 2: Ensuring Assistant and Vector Store...")
        assistant_id, vector_store_id = ensure_assistant_and_vector_store(
            client, model, assistant_id, vector_store_id, chunk_size, chunk_overlap
        )
        print(f"✓ Assistant ID: {assistant_id}")
        print(f"✓ Vector Store ID: {vector_store_id}\n")

        # 3) Delta detection
        print("Step 3: Detecting changes...")
        files = discover_markdown_files(ARTICLES_DIR)
        sync_state = read_json(SYNC_STATE_FILE)
        known_files: Dict[str, dict] = sync_state.get("files", {})

        to_add: List[Path] = []
        to_update: List[Tuple[Path, str]] = []
        skipped = 0

        for p in files:
            sha = compute_sha256(p)
            rec = known_files.get(str(p))
            if not rec:
                to_add.append(p)
                print(f"  + New: {p.name}")
            else:
                if rec.get("sha256") != sha:
                    to_update.append((p, rec.get("file_id", "")))
                    print(f"  ~ Updated: {p.name}")
                else:
                    skipped += 1

        # Detect removed files (present in state but not on disk)
        removed = [k for k in known_files.keys() if not Path(k).exists()]
        for path_str in removed:
            print(f"  - Removed: {Path(path_str).name}")

        print(f"\nDelta Summary:")
        print(f"  Added: {len(to_add)}")
        print(f"  Updated: {len(to_update)}")
        print(f"  Skipped: {skipped}")
        print(f"  Removed: {len(removed)}")
        print()

        # 4) Upload only the delta
        new_file_ids: Dict[str, str] = {}
        deleted_ids: List[str] = []
        if to_add or to_update:
            print("Step 4: Uploading changes to Vector Store...")
            new_file_ids, deleted_ids = upload_delta(client, vector_store_id, to_add, to_update)
            print(f"✓ Uploaded {len(new_file_ids)} files")
            if deleted_ids:
                print(f"✓ Deleted {len(deleted_ids)} old file versions")
        else:
            print("Step 4: No changes to upload")

        # 5) Update sync state
        print("\nStep 5: Updating sync state...")
        for p in to_add:
            known_files[str(p)] = {
                "sha256": compute_sha256(p),
                "file_id": new_file_ids.get(str(p), ""),
                "uploaded_at": now_iso(),
                "size_bytes": p.stat().st_size,
            }
        for p, _old in to_update:
            known_files[str(p)] = {
                "sha256": compute_sha256(p),
                "file_id": new_file_ids.get(str(p), ""),
                "uploaded_at": now_iso(),
                "size_bytes": p.stat().st_size,
            }
        # Keep removed entries but mark as removed for audit
        for path_str in removed:
            known_files[path_str]["removed"] = True
            known_files[path_str]["removed_at"] = now_iso()

        sync_state.update({
            "files": known_files,
            "assistant_id": assistant_id,
            "vector_store_id": vector_store_id,
            "last_run_at": now_iso(),
            "total_files": len(files),
            "total_size_bytes": sum(p.stat().st_size for p in files),
        })
        write_json(SYNC_STATE_FILE, sync_state)
        print("✓ Sync state updated")

        # 6) Write run artifact
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        summary = {
            "timestamp": now_iso(),
            "duration_seconds": duration,
            "status": "success",
            "added": len(to_add),
            "updated": len(to_update),
            "skipped": skipped,
            "removed_detected": len(removed),
            "deleted_remote_file_ids": deleted_ids,
            "assistant_id": assistant_id,
            "vector_store_id": vector_store_id,
            "articles_dir": str(ARTICLES_DIR),
            "total_files": len(files),
            "total_size_bytes": sum(p.stat().st_size for p in files),
            "logs_hint": "View detailed logs in your DigitalOcean App Platform Logs.",
        }
        write_json(RUNS_DIR / "last_run.json", summary)
        
        print(f"\n✓ Job completed successfully in {duration:.1f} seconds")
        print(f"✓ Run summary written to: {RUNS_DIR / 'last_run.json'}")
        
    except Exception as e:
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        error_summary = {
            "timestamp": now_iso(),
            "duration_seconds": duration,
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
        }
        write_json(RUNS_DIR / "last_run.json", error_summary)
        
        print(f"\n✗ Job failed after {duration:.1f} seconds: {e}")
        raise


if __name__ == "__main__":
    main()


