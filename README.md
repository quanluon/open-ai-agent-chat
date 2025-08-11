# OptiBot: Automated Support Knowledge Base

A complete solution for scraping OptiSigns support articles, converting them to clean Markdown, and automatically syncing them to an OpenAI Assistant with Vector Store for intelligent customer support.

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- Docker (for deployment)
- OpenAI API key
- DigitalOcean Droplet (for production deployment)

## 🏃‍♂️ How to Run Locally

### Step 1: Clone and Setup

```bash
git clone https://github.com/quanluon/open-ai-agent-chat.git
cd open-ai-agent-chat
```

### Step 2: Environment Configuration

```bash
# Copy environment template
cp .env.sample .env

# Edit .env file with your credentials
nano .env  # or use your preferred editor
```

**Required environment variables:**

```bash
OPENAI_API_KEY=sk-your_openai_api_key_here
ASSISTANT_ID=asst_your_assistant_id_here
VECTOR_STORE_ID=vs_your_vector_store_id_here
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Run the Application

#### Option A: Full Pipeline

```bash
# Run complete scrape → process → upload pipeline
python main.py
```

#### Option B: Individual Components

```bash
# 1. Test scraping only (10 articles)
python scripts/scrape_to_markdown.py --max-articles 10

# 2. Setup Assistant and Vector Store
python scripts/bootstrap_optibot.py --docs-dir ./articles

# 3. Test Assistant API
python scripts/ask_assistant.py --question "How do I add a YouTube video?"

# 4. Run full pipeline
python main.py
```

#### Option C: Docker (Recommended)

```bash
# Build optimized Docker image
docker build -t optibot:latest .

# Run with environment file
docker run --rm --env-file .env -v $(pwd)/logs:/app/runs optibot:latest

# View results in logs
tail -f logs/cron.log
```

### Local Testing Results

After running locally, you should see:

- **Articles**: Scraped markdown files in `./articles/` directory
- **Logs**: Execution logs in console output
- **Results**: Summary printed to console with counts of processed articles

## 🚀 How to Deploy (Production)

### Deployment Architecture

```
GitHub Repository → GitHub Actions (Build) → Docker Hub → Self-Hosted Runner (DigitalOcean Droplet) → Docker Container → Cron Job (Daily 2 AM UTC)
```

### Step 1: Setup DigitalOcean Droplet

1. **Create Droplet**:

   - **OS**: Ubuntu 22.04 LTS
   - **Size**: Basic plan (1GB RAM minimum)
   - **Location**: Choose closest region
   - **SSH Keys**: Add your SSH key

2. **Connect to Droplet**:

   ```bash
   ssh root@YOUR_DROPLET_IP
   ```

3. **Install Required Software**:

   ```bash
   # Update system
   apt update && apt upgrade -y

   # Install Docker
   curl -fsSL https://get.docker.com -o get-docker.sh
   sh get-docker.sh
   systemctl start docker
   systemctl enable docker

   # Install additional tools
   apt install -y jq curl

   # Create project directory
   mkdir -p /opt/optibot/logs
   ```

### Step 2: Setup GitHub Self-Hosted Runner

1. **In GitHub Repository**:

   - Go to **Settings** → **Actions** → **Runners**
   - Click **"New self-hosted runner"**
   - Select **Linux** and **x64**
   - Copy the provided commands

2. **On Your Droplet**:

   ```bash
   # Create runner directory
   mkdir actions-runner && cd actions-runner

   # Download runner (use commands from GitHub)
   curl -o actions-runner-linux-x64-2.311.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz
   tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz

   # Configure runner (use token from GitHub)
   ./config.sh --url https://github.com/quanluon/open-ai-agent-chat --token YOUR_GITHUB_TOKEN

   # Install as service
   sudo ./svc.sh install
   sudo ./svc.sh start
   ```

3. **Verify Runner**:
   - Check GitHub repository settings to see runner is "Online"

### Step 3: Configure Repository Secrets

In GitHub repository **Settings** → **Secrets and variables** → **Actions**, add:

| Secret Name          | Value           | Description                  |
| -------------------- | --------------- | ---------------------------- |
| `OPENAI_API_KEY`     | `sk-...`        | Your OpenAI API key          |
| `ASSISTANT_ID`       | `asst_...`      | Your OpenAI Assistant ID     |
| `VECTOR_STORE_ID`    | `vs_...`        | Your OpenAI Vector Store ID  |
| `DOCKERHUB_USERNAME` | `your-username` | Your Docker Hub username     |
| `DOCKERHUB_TOKEN`    | `your-token`    | Your Docker Hub access token |

### Step 4: Deploy

#### Automatic Deployment (Recommended)

```bash
# Any push to main branch triggers build and deploy
git push origin main
```

#### Manual Deployment

1. Go to GitHub **Actions** tab
2. Select **"Manual Deploy"** workflow
3. Click **"Run workflow"**
4. Monitor execution in real-time

### Step 5: Monitor Deployment

#### Check Deployment Status

```bash
# SSH to droplet
ssh root@YOUR_DROPLET_IP

# Verify cron job is scheduled
crontab -l

# Check Docker image exists
docker images | grep optibot

# Verify environment file
cat /opt/optibot/.env

# Check log directory
ls -la /opt/optibot/logs/
```

#### View Execution Logs

```bash
# Real-time cron execution logs
tail -f /opt/optibot/logs/cron.log

# System cron logs
journalctl -u cron -f
```

### Daily Job Details

- **Schedule**: Daily at 2 AM UTC (`*/1 * * * *`)
- **Command**: Docker container execution with environment variables
- **Logs**: `/opt/optibot/logs/cron.log`
- **Persistence**: Logs persist between runs

## 📊 Monitoring & Logs

### GitHub Actions Logs

- **URL**: https://github.com/quanluon/open-ai-agent-chat/actions
- **Workflows**:
  - `build-and-deploy.yml` - Automatic build and deployment
  - `deploy-self-hosted.yml` - Manual deployment

### Droplet Logs

```bash
# SSH into droplet
ssh root@YOUR_DROPLET_IP

# View real-time logs
tail -f /opt/optibot/logs/cron.log

# Monitor disk usage
df -h /opt/optibot/

# Check Docker containers
docker ps -a | grep optibot
```

### Log Files Location

- **Cron execution**: `/opt/optibot/logs/cron.log`

## ⚙️ Configuration

### Environment Variables

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

### Cron Job Configuration

The deployment automatically sets up this cron job:

```bash
*/1 * * * *  /usr/bin/docker run --rm --env-file /opt/optibot/.env -v /opt/optibot/logs:/app/runs --name optibot-cron optibot:latest >> /opt/optibot/logs/cron.log 2>&1
```

## 🔧 Troubleshooting

### Local Issues

```bash
# Check environment variables
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('API Key:', 'SET' if os.environ.get('OPENAI_API_KEY') else 'NOT SET')"

# Test Docker build
docker build -t optibot:test .

# Run with verbose output
python main.py --verbose
```

### Deployment Issues

#### Runner Problems

```bash
# Check runner status
sudo ./svc.sh status

# Restart runner service
sudo ./svc.sh stop
sudo ./svc.sh start

# View runner logs
cat _diag/Runner_*.log
```

#### Permission Issues

```bash
# Fix permissions
sudo chmod -R 777 /opt/optibot/
sudo chown -R $USER:$USER /opt/optibot/

# Check Docker permissions
sudo usermod -aG docker $USER
newgrp docker
```

#### Container Issues

```bash
# Check for existing containers
docker ps -a | grep optibot

# Remove conflicting containers
docker stop optibot-cron optibot-test 2>/dev/null || true
docker rm optibot-cron optibot-test 2>/dev/null || true

# Pull latest image
docker pull your-username/optisign-bot:latest
```

#### Common Error Fixes

| Error                     | Solution                                    |
| ------------------------- | ------------------------------------------- |
| "Permission denied"       | `sudo chmod -R 777 /opt/optibot/`           |
| "Docker not found"        | Install Docker and add user to docker group |
| "Runner offline"          | Restart runner service                      |
| "Secrets not found"       | Verify repository secrets are set           |
| "Cron not running"        | `sudo systemctl start cron`                 |
| "Container name conflict" | Remove existing containers first            |

## 📁 Project Structure

```
├── main.py                    # Main orchestrator script
├── Dockerfile                 # Optimized multi-stage container
├── requirements.txt           # Python dependencies
├── .env.sample               # Environment template
├── scripts/
│   ├── scrape_to_markdown.py # Article scraper
│   ├── bootstrap_optibot.py  # Assistant setup
│   └── ask_assistant.py      # Testing tool
├── .github/workflows/
│   ├── build-and-deploy.yml  # Build and auto deployment
│   └── deploy-self-hosted.yml # Manual deployment
├── articles/                  # Scraped markdown files
└── logs/                      # Local logs
```

## 🎯 Features

- ✅ **Automated Scraping**: Daily article collection from OptiSigns support
- ✅ **Simplified Processing**: Processes all articles each run (no delta detection)
- ✅ **Vector Store Sync**: Automatic OpenAI Assistant updates
- ✅ **Optimized Docker**: Multi-stage build with security best practices
- ✅ **CI/CD Pipeline**: GitHub Actions with Docker Hub integration
- ✅ **Self-Hosted Deployment**: Runs on your own DigitalOcean infrastructure
- ✅ **Console Logging**: All output goes to cron.log
- ✅ **Manual Testing**: On-demand execution for testing
- ✅ **Cron Scheduling**: Reliable daily execution

## 📊 Expected Output

After successful execution, you'll see console output like:

```
OptiBot Daily Sync Job
Started at: 2024-01-15T02:00:00Z
Configuration:
  Assistant ID: asst_xxx
  Model: gpt-4o-mini
  Vector Store ID: vs_xxx
  Chunk Size: 800
  Chunk Overlap: 200
  Locale: en-us
  Max Articles: 45
  Articles Dir: /app/articles

Step 1: Scraping articles from OptiSigns support...
✓ Scraping completed

Step 2: Ensuring Assistant and Vector Store...
✓ Assistant ID: asst_xxx
✓ Vector Store ID: vs_xxx

Step 3: Processing articles...
  + Processing: article1.md
  + Processing: article2.md
  ...

Step 4: Uploading changes to Vector Store...
✓ Uploaded 45 files

Step 5: Job completed

✓ Job completed successfully in 45.2 seconds
  - Added: 45 files
  - Updated: 0 files
  - Skipped: 0 files
  - Removed: 0 files
  - Duration: 45.2 seconds
```

## 🆘 Support

- **GitHub Issues**: Report bugs or request features
- **Actions Logs**: Check workflow execution details
- **Droplet Logs**: Monitor daily job execution
- **OpenAI Dashboard**: Verify Assistant and Vector Store updates
