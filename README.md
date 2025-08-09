# OptiBot: Automated Support Knowledge Base

A complete solution for scraping OptiSigns support articles, converting them to clean Markdown, and automatically syncing them to an OpenAI Assistant with Vector Store for intelligent customer support.

## Quick Start

### Prerequisites

- Python 3.10+
- Docker (for deployment)
- OpenAI API key

### Environment Setup

1. **Clone and setup**:
   ```bash
   git clone https://github.com/quanluon/open-ai-agent-chat.git
   cd open-ai-agent-chat
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   ```bash
   cp .env.sample .env
   # Edit .env with your actual values
   ```

## How to Run Locally

### Option 1: Direct Python Execution

```bash
# Setup environment
cp .env.sample .env
# Edit .env with your OpenAI credentials

# Install dependencies
pip install -r requirements.txt

# Run individual components
python scripts/scrape_to_markdown.py --max-articles 10  # Test scraping
python scripts/bootstrap_optibot.py --docs-dir ./articles  # Setup Assistant
python main.py  # Run full pipeline
```

### Option 2: Docker (Recommended)

```bash
# Build image
docker build -t optibot:latest .

# Run with environment file
docker run --rm --env-file .env -v $(pwd)/logs:/app/runs optibot:latest

# Or run with environment variables
docker run --rm \
  -e OPENAI_API_KEY=your_key \
  -e ASSISTANT_ID=your_assistant_id \
  -e VECTOR_STORE_ID=your_vector_store_id \
  -v $(pwd)/logs:/app/runs \
  optibot:latest
```

### Testing Individual Scripts

```bash
# Test scraping only
python scripts/scrape_to_markdown.py --out-dir ./test-articles --max-articles 5

# Test Assistant API
python scripts/ask_assistant.py --question "How do I add a YouTube video?"

# Test Vector Store upload
python scripts/bootstrap_optibot.py --docs-dir ./articles
```

## How to Deploy

### Deployment Architecture

```
GitHub Repository → Self-Hosted Runner (DigitalOcean Droplet) → Docker Container → Cron Job
```

### Step 1: Setup DigitalOcean Droplet

1. **Create Droplet**:
   - OS: Ubuntu 22.04 LTS
   - Size: Basic (1GB RAM minimum)
   - Location: Choose closest region

2. **Install Dependencies**:
   ```bash
   # SSH into droplet
   ssh root@YOUR_DROPLET_IP
   
   # Update system
   apt update && apt upgrade -y
   
   # Install Docker
   curl -fsSL https://get.docker.com -o get-docker.sh
   sh get-docker.sh
   systemctl start docker
   systemctl enable docker
   
   # Install jq for JSON processing
   apt install -y jq
   ```

### Step 2: Setup GitHub Self-Hosted Runner

1. **In your GitHub repository**:
   - Go to **Settings** → **Actions** → **Runners**
   - Click **"New self-hosted runner"**
   - Select **Linux** and **x64**

2. **On your Droplet, run the provided commands**:
   ```bash
   # Download and configure runner
   mkdir actions-runner && cd actions-runner
   curl -o actions-runner-linux-x64-2.311.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz
   tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz
   
   # Configure runner (use token from GitHub)
   ./config.sh --url https://github.com/quanluon/open-ai-agent-chat --token YOUR_TOKEN
   
   # Install as service
   sudo ./svc.sh install
   sudo ./svc.sh start
   ```

### Step 3: Configure Repository Secrets

In GitHub repository **Settings** → **Secrets and variables** → **Actions**, add:

- `OPENAI_API_KEY`: Your OpenAI API key
- `ASSISTANT_ID`: Your OpenAI Assistant ID
- `VECTOR_STORE_ID`: Your OpenAI Vector Store ID

### Step 4: Deploy

1. **Automatic Deployment**:
   ```bash
   # Push to main branch triggers deployment
   git push origin main
   ```

2. **Manual Deployment**:
   - Go to **Actions** tab in GitHub
   - Select **"Deploy to Self-Hosted Droplet"**
   - Click **"Run workflow"**

3. **Manual Run** (for testing):
   - Go to **Actions** tab
   - Select **"Manual Run OptiBot"**
   - Click **"Run workflow"**
   - Optionally set custom article count

### Step 5: Monitor Deployment

#### Check Deployment Status

```bash
# SSH to droplet
ssh root@YOUR_DROPLET_IP

# Check if cron job is scheduled
crontab -l

# Check Docker image
docker images | grep optibot

# Verify environment file
cat /opt/optibot/.env

# Check log directory
ls -la /opt/optibot/logs/
```

#### View Logs

```bash
# Real-time cron execution logs
tail -f /opt/optibot/logs/cron.log

# Last run results
cat /opt/optibot/logs/last_run.json | jq .

# System cron logs
tail -f /var/log/cron
```

### Daily Job Schedule

- **Schedule**: Daily at 2 AM UTC (`0 2 * * * ...`)
- **Command**: `docker run --rm --env-file /opt/optibot/.env -v /opt/optibot/logs:/app/runs --name optibot-cron optibot:latest`
- **Logs**: `/opt/optibot/logs/cron.log`
- **Results**: `/opt/optibot/logs/last_run.json`

## Project Structure

```
├── main.py                    # Main orchestrator
├── Dockerfile                 # Container definition
├── requirements.txt           # Python dependencies
├── .env.sample               # Environment template
├── scripts/
│   ├── scrape_to_markdown.py # Article scraper
│   ├── bootstrap_optibot.py  # Assistant setup
│   └── ask_assistant.py      # Testing tool
└── .github/workflows/
    ├── deploy-self-hosted.yml # Auto deployment
    └── manual-run.yml         # Manual execution
```

## Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-...                    # Your OpenAI API key
ASSISTANT_ID=asst_...                    # Assistant ID from OpenAI
VECTOR_STORE_ID=vs_...                   # Vector Store ID from OpenAI

# Optional (with defaults)
MODEL=gpt-4o-mini                        # OpenAI model
CHUNK_SIZE=800                           # Token chunk size
CHUNK_OVERLAP=200                        # Chunk overlap
LOCALE=en-us                             # Article locale
MAX_ARTICLES=45                          # Max articles to process
ARTICLES_DIR=./articles                  # Output directory
```

## Troubleshooting

### Local Issues

```bash
# Check environment
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('API Key:', 'SET' if os.environ.get('OPENAI_API_KEY') else 'NOT SET')"

# Test Docker
docker run --rm optibot:latest python --version

# Check logs
tail -f logs/cron.log
```

### Deployment Issues

```bash
# Check runner status
sudo ./svc.sh status

# Restart runner
sudo ./svc.sh stop
sudo ./svc.sh start

# Check runner logs
cat _diag/Runner_*.log
```

### Common Fixes

1. **"Permission denied"**: `sudo chmod +x /opt/optibot/`
2. **"Docker not found"**: Install Docker and add user to docker group
3. **"Runner offline"**: Restart runner service
4. **"Secrets not found"**: Verify repository secrets are set

## Monitoring URLs

- **GitHub Actions**: https://github.com/quanluon/open-ai-agent-chat/actions
- **Workflow Logs**: Check specific workflow runs for detailed logs
- **Droplet Access**: SSH to your droplet for real-time monitoring

## Features

- ✅ **Automated Scraping**: Daily article collection from support.optisigns.com
- ✅ **Delta Detection**: Only processes new/updated articles
- ✅ **Vector Store Sync**: Automatic OpenAI Assistant updates
- ✅ **Docker Deployment**: Containerized for easy deployment
- ✅ **Self-Hosted CI/CD**: Runs on your own infrastructure
- ✅ **Comprehensive Logging**: Detailed execution tracking
- ✅ **Manual Testing**: On-demand execution for testing

## Example Output

```json
{
  "timestamp": "2024-01-15T02:00:30Z",
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
