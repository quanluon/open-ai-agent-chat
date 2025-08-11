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
RUNS_DIR = ROOT / "runs"
SYNC_STATE_FILE = RUNS_DIR / "sync_state.json"

try:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
except PermissionError:
    # If we can't create the directory, try to use a writable location
    RUNS_DIR = Path("/tmp/runs")
    SYNC_STATE_FILE = RUNS_DIR / "sync_state.json"
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Warning: Using temporary directory for runs: {RUNS_DIR}")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_sync_state() -> dict:
    """Read sync state from JSON file."""
    try:
        if not SYNC_STATE_FILE.exists():
            return {"files": {}, "last_run": None}
        return json.loads(SYNC_STATE_FILE.read_text(encoding="utf-8"))
    except PermissionError:
        print(f"Warning: Permission denied accessing {SYNC_STATE_FILE}, using empty state")
        return {"files": {}, "last_run": None}
    except Exception as e:
        print(f"Warning: Could not read sync state: {e}")
        return {"files": {}, "last_run": None}


def write_sync_state(state: dict) -> None:
    """Write sync state to JSON file."""
    try:
        # Ensure the directory exists
        SYNC_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SYNC_STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    except PermissionError:
        print(f"Warning: Permission denied writing to {SYNC_STATE_FILE}, sync state not persisted")
    except Exception as e:
        print(f"Warning: Could not write sync state: {e}")


def parse_last_modified(content: str) -> Optional[str]:
    """Extract Last-Modified date from markdown content."""
    lines = content.split('\n')
    for line in lines:
        if line.startswith('Last Modified:'):
            return line.replace('Last Modified:', '').strip()
    return None


def detect_delta(files: List[Path], sync_state: dict) -> Tuple[List[Path], List[Tuple[Path, str]], List[str], int]:
    """
    Detect which files are new, updated, or removed.
    
    Uses both SHA256 hash and Last-Modified date for change detection.
    
    Returns: (to_add, to_update, removed, skipped)
    """
    to_add: List[Path] = []
    to_update: List[Tuple[Path, str]] = []
    removed: List[str] = []
    skipped = 0
    
    known_files = sync_state.get("files", {})
    
    # Check current files
    for file_path in files:
        file_hash = compute_sha256(file_path)
        filename = file_path.name
        
        # Parse Last-Modified from file content
        try:
            content = file_path.read_text(encoding="utf-8")
            last_modified = parse_last_modified(content)
        except Exception:
            last_modified = None
        
        if filename not in known_files:
            # New file
            to_add.append(file_path)
            print(f"  + New: {filename}")
        else:
            known_hash = known_files[filename].get("hash")
            known_last_modified = known_files[filename].get("last_modified")
            
            # Check if file has changed (hash or last_modified)
            hash_changed = known_hash != file_hash
            date_changed = (known_last_modified != last_modified and 
                          last_modified is not None and 
                          known_last_modified is not None)
            
            if hash_changed or date_changed:
                # Updated file
                old_file_id = known_files[filename].get("file_id", "")
                to_update.append((file_path, old_file_id))
                change_reason = []
                if hash_changed:
                    change_reason.append("content")
                if date_changed:
                    change_reason.append("date")
                print(f"  ~ Updated: {filename} ({', '.join(change_reason)})")
            else:
                # Unchanged file
                skipped += 1
                print(f"  - Skipped: {filename}")
    
    # Detect removed files
    current_filenames = {f.name for f in files}
    for filename in known_files:
        if filename not in current_filenames:
            removed.append(filename)
            print(f"  - Removed: {filename}")
    
    return to_add, to_update, removed, skipped





def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_scraper(locale: str, max_articles: int) -> None:
    cmd = [
        sys.executable,
        str(ROOT / "src" / "scrape_to_markdown.py"),
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
        print("Step 1: Scraping articles from OptiSigns support...")
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
        sync_state = read_sync_state()
        
        to_add, to_update, removed, skipped = detect_delta(files, sync_state)

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
        known_files = sync_state.get("files", {})
        
        # Update file records
        for file_path in to_add:
            filename = file_path.name
            try:
                content = file_path.read_text(encoding="utf-8")
                last_modified = parse_last_modified(content)
            except Exception:
                last_modified = None
            
            known_files[filename] = {
                "hash": compute_sha256(file_path),
                "file_id": new_file_ids.get(str(file_path), ""),
                "last_modified": last_modified,
                "last_sync": now_iso(),
                "size": file_path.stat().st_size
            }
        
        for file_path, _ in to_update:
            filename = file_path.name
            try:
                content = file_path.read_text(encoding="utf-8")
                last_modified = parse_last_modified(content)
            except Exception:
                last_modified = None
            
            known_files[filename] = {
                "hash": compute_sha256(file_path),
                "file_id": new_file_ids.get(str(file_path), ""),
                "last_modified": last_modified,
                "last_sync": now_iso(),
                "size": file_path.stat().st_size
            }
        
        # Remove deleted files from state
        for filename in removed:
            known_files.pop(filename, None)
        
        # Update sync state
        sync_state.update({
            "files": known_files,
            "last_run": now_iso(),
            "assistant_id": assistant_id,
            "vector_store_id": vector_store_id,
            "total_files": len(files),
            "total_size": sum(f.stat().st_size for f in files)
        })
        
        write_sync_state(sync_state)
        print("✓ Sync state updated")

        # 6) Job completion
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        print(f"\n✓ Job completed successfully in {duration:.1f} seconds")
        print(f"  - Added: {len(to_add)} files")
        print(f"  - Updated: {len(to_update)} files")
        print(f"  - Skipped: {skipped} files")
        print(f"  - Removed: {len(removed)} files")
        print(f"  - Duration: {duration:.1f} seconds")
        print(f"  - Sync state: {SYNC_STATE_FILE}")
        
    except Exception as e:
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        print(f"\n✗ Job failed after {duration:.1f} seconds: {e}")
        raise


if __name__ == "__main__":
    main()


