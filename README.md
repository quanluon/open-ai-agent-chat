# OptiBot: Automated Support Knowledge Base

A complete solution for scraping OptiSigns support articles, converting them to clean Markdown, and automatically syncing them to an OpenAI Assistant with Vector Store for intelligent customer support.

## Overview

This project demonstrates:

1. **Web scraping & content normalization** - Ingests messy web content and converts to clean Markdown
2. **API-based vector store upload** - Programmatically uploads content without UI drag-and-drop
3. **Daily automated sync** - Detects changes and uploads only deltas
4. **Production deployment** - Dockerized for DigitalOcean App Platform scheduling

## System Prompt (verbatim)

You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply.

### Prerequisites

- Python 3.10+
- Set `OPENAI_API_KEY` in your environment.
- Install deps:

```bash
pip install -r requirements.txt
```

### Files

- `scripts/scrape_to_markdown.py`: Scrapes ≥30 articles from `support.optisigns.com` using Zendesk API, converts HTML to clean Markdown, preserves headings/code blocks, removes nav/ads, and adds citation headers.
- `scripts/bootstrap_optibot.py`: Legacy script for creating Vector Store and Assistant (use environment variables instead).
- `scripts/ask_assistant.py`: CLI tool to test the Assistant with questions and view citations.
- `main.py`: **Main orchestrator** - runs daily job: scrape → detect delta → upload changes → log results.
- `Dockerfile`: Production-ready container for DigitalOcean App Platform scheduling.
- `.env.sample`: Environment variable template.

### Chunking Strategy

- **Strategy**: Static token-based chunking with overlap
- **Parameters**: `--chunk-size` (default 800 tokens), `--chunk-overlap` (default 200 tokens)
- **Rationale**: 800-token chunks balance retrieval specificity and context packing for downstream reasoning. 200-token overlap preserves continuity for section boundaries and reduces information loss at chunk edges.
- **Logging**: The bootstrap script estimates total chunks client-side using the same stride formula and writes file-level and aggregate stats to `optibot_state.json` and stdout. Final server-side chunk counts may differ slightly.

### Setup Assistant and Vector Store

Create your Assistant and Vector Store in the OpenAI Playground or via API, then set the IDs in your environment:

```bash
export ASSISTANT_ID=asst_your_assistant_id_here
export VECTOR_STORE_ID=vs_your_vector_store_id_here
```

### Optional API sanity check

Ask a question directly via API using your Assistant:

```bash
OPENAI_API_KEY=... python scripts/ask_assistant.py \
  --question "How do I add a YouTube video?" \
  --assistant-id asst_your_assistant_id_here
```

This prints the answer and any file citations the API returns.

## Testing & Validation

### Quick Sanity Check

After running the job, test the Assistant:

1. **Open OpenAI Playground**: Go to https://platform.openai.com/playground
2. **Select Assistants**: Choose the Assistants experience
3. **Load Assistant**: Use the Assistant ID from `optibot_state.json` or `runs/last_run.json`
4. **Test Question**: Ask "How do I add a YouTube video?"
5. **Verify Response**:
   - Uses at most 5 bullet points or links to the doc
   - Includes up to 3 citations labeled "Article URL:"
   - Tone is helpful, factual, and concise
6. **Take Screenshot**: Document the successful response

### API Testing

Test the Assistant programmatically:

```bash
OPENAI_API_KEY=... python scripts/ask_assistant.py \
  --question "How do I add a YouTube video?" \
  --state-file runs/last_run.json
```

### Validation Checklist

- [ ] Scraper fetches ≥30 articles from support.optisigns.com
- [ ] Markdown files are clean (no nav/ads, preserved headings/code blocks)
- [ ] Vector Store upload works via API (no UI drag-and-drop)
- [ ] Assistant responds with correct system prompt behavior
- [ ] Citations include "Article URL:" format
- [ ] Daily job detects and uploads only deltas
- [ ] Run logs show added/updated/skipped counts
- [ ] Docker container runs successfully

## Scrape ⇒ Markdown

Run the scraper to collect ≥30 articles into `./articles/` as clean Markdown:

```bash
python3 scripts/scrape_to_markdown.py \
  --out-dir ./articles \
  --max-articles 40
```

Or simply run with defaults (writes to `./articles`):

```bash
python3 scripts/scrape_to_markdown.py
```

Details:

- Scope: Only `support.optisigns.com` pages are crawled via the Zendesk API; article pages match `/hc/<locale>/articles/<id>-<slug>`.
- Extraction: Converts HTML to Markdown, preserving headings, lists, code blocks, and links.
- Filenames: `<id>-<slug>.md` to avoid collisions and keep stable references.
- Citations: Each file prepends `Article URL: <source>` for downstream citation.
- Links: Internal links to other scraped articles are rewritten to local `./<id>-<slug>.md` when resolvable; anchors are preserved.

## Orchestrator & Scheduling

Run the whole pipeline locally:

```bash
OPENAI_API_KEY=... python3 main.py
```

Environment overrides:

- `ASSISTANT_ID` (required: your assistant ID)
- `VECTOR_STORE_ID` (required: your vector store ID)
- `MODEL` (default: gpt-4o-mini)
- `CHUNK_SIZE` (default: 800)
- `CHUNK_OVERLAP` (default: 200)
- `LOCALE` (default: en-us)
- `MAX_ARTICLES` (default: 45)
- `ARTICLES_DIR` (default: `./articles`)

Artifacts & logs:

- `sync_state.json`: per-file SHA and remote file_id for delta sync
- `runs/last_run.json`: counts of added/updated/skipped/removed and IDs of deleted remote files

### Docker

Build and run:

```bash
docker build -t optibot-job .
docker run --rm -e OPENAI_API_KEY=$OPENAI_API_KEY optibot-job
```

### DigitalOcean App Platform (Scheduled Job)

1. **Create App**: Create a new App, select Docker, and point to this repo directory
2. **Configure Job**:
   - Set Run Command to `python main.py`
   - Add environment variable `OPENAI_API_KEY`
   - Set schedule to run daily (e.g., "0 2 \* \* \*" for 2 AM UTC)
3. **Deploy**: Deploy the app
4. **Monitor**:
   - View logs in the DO App Platform dashboard
   - Check `/app/runs/last_run.json` in the container for run artifacts
   - Optionally attach a volume to persist run history

#### Job Features

- **Delta Detection**: Uses SHA-256 hashing to detect new/updated articles
- **Efficient Upload**: Only uploads changed files to minimize API usage
- **Comprehensive Logging**: Logs added, updated, skipped, and removed counts
- **Error Handling**: Graceful error handling with detailed error reporting
- **State Persistence**: Maintains sync state between runs

#### Run Artifacts

The job creates detailed run artifacts at `runs/last_run.json`:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "duration_seconds": 45.2,
  "status": "success",
  "added": 3,
  "updated": 1,
  "skipped": 41,
  "removed_detected": 0,
  "assistant_id": "asst_...",
  "vector_store_id": "vs_...",
  "total_files": 45,
  "total_size_bytes": 1024000
}
```
