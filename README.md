# 🛡️ BaleChatCleaner (Advanced Anti-Glitch Bot)

**BaleChatCleaner** is a specialized, production-ready bot designed to clean messages, posts, and media in **Bale messenger channels and groups** without causing server desynchronization, client-side glitches, or rate-limit crashes.

It includes an interactive **in-app Admin Panel** (inline buttons), **granular message filtering** (including inverted filters like *"delete all except audio & documents"*), live job management (Pause / Resume / Abort), and a Docker setup optimized for **Portainer on Debian 13 VPS**.

---

## ⚡ The Glitch Problem & How We Solve It

### Why Channels Glitch During Mass Deletion
When bots delete hundreds of messages in rapid bursts:
1. **Socket & Push Desync:** The messenger's backend drops or throttles push notifications to mobile and desktop subscribers. Consequently, deleted messages disappear for some users but remain visible as "ghost messages" for others until they manually restart or clear cache.
2. **Replication Lag:** Multi-node database sharding on messaging servers experiences delay propagating deletions across all read replicas.
3. **HTTP 429 Rate Limits:** Burst deletion triggers server throttles, crashing unhandled cleaner bots.

### The Anti-Glitch Engine Architecture
* **Paced Token-Bucket Rate Limiter:** Ensures a steady, controlled interval between deletions (default **120ms** for channels, **60ms** for groups).
* **Socket Flush Heartbeat:** Every **20–30 messages**, the engine automatically pauses for **1.5–2.0 seconds** to allow server-to-client WebSocket streams to catch up and synchronize all devices.
* **Smart 429 Backoff:** Intercepts `Too Many Requests` and cools down for `retry_after + 1.0s` automatically.
* **Error Resilience:** Gracefully skips already-deleted messages or permission-restricted posts without terminating the queue.

---

## ✨ Features

- **In-App Admin Panel:** Manage everything inside Bale via interactive inline buttons (no web server or external login needed).
- **Granular Message Filtering:**
  - 📝 Text
  - 🖼 Photos
  - 🎬 Videos
  - 🎵 Audio & Music
  - 📄 Documents & Files
  - 🎤 Voice Notes
  - 🎭 Stickers
  - 🎞 GIFs & Animations
- **Negation Filters ("All Except X"):** Keep specific media types while purging everything else (e.g., delete all spam/chat but **keep audios and documents**).
- **Real-Time Job Control:** Live progress bar (`[██████░░░░] 60%`), with instant **Pause**, **Resume**, and **Abort** buttons.
- **Continuous Message Indexing:** Passively records incoming channel and group posts in a local SQLite database for instant, 100% accurate historical cleaning.
- **Retroactive Range Cleaning:** Supports custom message ID ranges (e.g., messages `100` to `500`).
- **Safety Speed Profiles:**
  - 🛡️ **Ultra-Safe (Recommended):** 180ms delay + 2.0s sync flush pause every 20 messages.
  - ⚖️ **Balanced:** 100ms delay + 1.2s sync flush pause every 30 messages.
  - ⚡ **Fast:** 50ms delay + adaptive rate handling.

---

## 🚀 Quick Deployment Guide (Portainer on Debian 13 VPS)

### Method 1: Deploy via Portainer (Recommended)

1. Open your **Portainer Web Dashboard** (`https://your-vps-ip:9443`).
2. Go to **Stacks** -> **Add stack**.
3. Name your stack: `bale-chat-cleaner`.
4. Choose **Repository** (or paste `docker-compose.yml` into **Web editor**):
   - **Repository URL:** `https://github.com/your-username/BaleChatCleaner`
   - **Repository reference:** `refs/heads/main`
5. In the **Environment variables** section, add:
   ```env
   BOT_TOKEN=your_bale_bot_token_from_botfather
   ADMIN_IDS=your_bale_user_id
   BALE_API_ENDPOINT=https://tapi.bale.ai
   ```
6. Click **Deploy the stack**.

---

### Method 2: Deploy via Docker CLI

```bash
# 1. Clone the repository
git clone https://github.com/your-username/BaleChatCleaner.git
cd BaleChatCleaner

# 2. Copy and configure environment variables
cp .env.example .env
nano .env  # Enter your BOT_TOKEN and ADMIN_IDS

# 3. Build and run in detached mode
docker compose up -d --build

# 4. Check container logs
docker compose logs -f
```

---

## ⚙️ Configuration Reference (`.env`)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `BOT_TOKEN` | *Required* | Bale Bot Token received from `@botfather` in Bale. |
| `ADMIN_IDS` | *Empty* | Comma-separated Bale user IDs allowed to access the panel (e.g. `12345678,98765432`). |
| `BALE_API_ENDPOINT` | `https://tapi.bale.ai` | Base URL for the Bale Bot API. |
| `DB_PATH` | `/app/data/cleaner.db` | Location of the persistent SQLite database. |
| `DEFAULT_CHANNEL_DELAY` | `0.12` | Seconds delay between message deletions in channels. |
| `DEFAULT_GROUP_DELAY` | `0.06` | Seconds delay between message deletions in groups. |
| `SYNC_PAUSE_INTERVAL` | `25` | Pause deletion every $N$ messages to flush client sockets. |
| `SYNC_PAUSE_DURATION` | `1.5` | Duration in seconds of the sync flush pause. |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

---

## 📖 How to Use the Bot

1. **Obtain Bot Token:**
   - Open Bale and message `@botfather`.
   - Send `/newbot`, choose a name and username.
   - Copy the generated token into `.env`.

2. **Add Bot to Your Channel or Group:**
   - Go to your Channel/Group settings -> **Administrators** -> **Add Administrator**.
   - Search for your bot username and add it.
   - Enable **Delete Messages** (and optionally *Post Messages* if you want confirmation logs).
   - Send or post a test message so the bot registers the chat in its database.

3. **Open the Admin Panel:**
   - Start a private chat with your bot in Bale.
   - Send `/start` or `/panel`.
   - Click **Manage Chats & Channels** -> Select your channel.
   - Choose **Start Cleaning Job**.
   - Select your **Scope** (`Last 100`, `Last 500`, `All Tracked`, etc.).
   - Configure **Filters** (`All`, `Only Text`, `All Except Audio & Docs`).
   - Pick a **Speed Profile** and click **CONFIRM & START CLEANING**.
   - Monitor progress live or click `⏸ Pause` / `⏹ Abort` at any time!

---

## 🧪 Testing & Local Development

Run unit tests locally using the built-in virtualenv:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run pytest suite
pytest -v
```

---

## 📄 License
MIT License. Free for personal and commercial use.
