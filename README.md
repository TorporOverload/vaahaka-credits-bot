# Vaahaka Credits Discord Bot

A Discord bot that rewards users with credits for uploading PDF documents. Each page in a PDF equals one credit, encouraging knowledge sharing and content contribution.

## Features

- **Automatic PDF Detection**: Monitors channels for PDF uploads and automatically awards credits
- **Duplicate Prevention**: Uses SHA-256 hashing to ensure each unique PDF is only counted once
- **Real-time Tracking**: Instantly processes uploads and updates user balances
- **Configurable Leaderboard Channel**: Admins can choose where leaderboard updates and upload notifications are posted
- **Rich Upload Notifications**: Posts a detailed embed (book, points earned, total credits, rank) when a new PDF is credited
- **Automatic Public Leaderboard Updates**: Posts an updated top-10 leaderboard when new credits are added
- **Historical Scanning**: Scan existing channel history to retroactively award credits
- **User Statistics**: View personal stats including total credits, rank, and uploaded books
- **All-time Rankings (Paginated)**: Browse the complete ranked list of all contributors
- **Leaderboard**: Public leaderboard displaying top contributors with trophy emojis

## Commands

- `/stats` - View your personal credits, rank, and list of uploaded books (public)
- `/leaderboard` - Display the top 10 contributors with trophy cabinet style
- `/alltime` - View complete all-time rankings of all contributors (paginated)
- `/set_leaderboard_channel` - Set the channel for automatic leaderboard updates and upload notifications (Admin only)
- `/run_leaderboard_listner` - Scan channel history for existing PDFs (Admin only; auto-adds the current channel to the PDF listen allowlist)
- `/listen_add channel:#channel` - Add a channel to the PDF listen allowlist (Admin only)
- `/listen_remove channel:#channel` - Remove a channel from the PDF listen allowlist (Admin only)
- `/listen_list` - Show configured PDF listen channels (Admin only)
- `/listen_clear` - Clear all configured PDF listen channels (revert to listening in no channels) (Admin only)

### Channel listening configuration (persistent)
The bot processes PDF uploads only in channels you explicitly configure using a **persisted channel allowlist** stored in the SQLite database.

Behavior:
- If **no channels are configured** for your server, the bot listens for PDFs in **no channels** (default).
- If **one or more channels are configured**, the bot will **only** process PDFs uploaded in those channels.
- Running `/run_leaderboard_listner` in a channel will automatically add that channel to the allowlist (so future uploads there are processed).

Admin commands:
- `/listen_add channel:#channel` - Add a channel to the allowlist (enables processing in that channel)
- `/listen_remove channel:#channel` - Remove a channel from the allowlist
- `/listen_list` - Show configured channels
- `/listen_clear` - Clear the allowlist (reverts to listening in no channels)

## Setup

### Prerequisites

- Python 3.10 or higher
- A Discord bot token
- Discord server with appropriate permissions

### Installation

1. Clone this repository:
```bash
git clone https://github.com/TorporOverload/vaahaka-credits-bot
cd vaahaka_credits_bot
```

2. Install dependencies using uv or pip:
```bash
# Using uv (recommended)
uv sync
```

3. Create a `.env` file in the project root:
```bash
cp .env.example .env
```

4. Edit `.env` and add your credentials:
```
DISCORD_TOKEN=your_discord_bot_token_here
GUILD_ID=your_guild_id_here

# Dev mode: when enabled, anyone can run admin-only commands (DO NOT use in production)
DEV_MODE=0
```

### Docker (Docker Compose)

#### Prerequisites
- Docker + Docker Compose (Compose v2 recommended)

#### Run with Docker Compose
1. Create your `.env` file (same as above) and set at least `DISCORD_TOKEN` (and optionally `GUILD_ID`, `DEV_MODE`, etc).
2. Create a local data directory (used to persist the SQLite DB):
```bash
mkdir -p data
```
PowerShell:
```bash
New-Item -ItemType Directory -Force data | Out-Null
```
3. Build and start the bot:
```bash
docker compose up -d --build
```
4. View logs:
```bash
docker compose logs -f
```
5. Stop:
```bash
docker compose down
```

#### Data persistence (SQLite)
The bot uses SQLite. With Docker Compose, the database is persisted via a bind mount:
- container: `/data/vaahaka_credits.db`
- host: `./data/vaahaka_credits.db`

If you see `sqlite3.OperationalError: unable to open database file`, it usually means `./data` doesn’t exist or isn’t writable by Docker—create the folder and try again.

To delete the database data, stop the container and remove the `./data` directory.

To enable dev mode, set `DEV_MODE=1` (or `true` / `yes` / `on`). When enabled, the bot bypasses administrator permission checks for admin-only slash commands.

### Configure the Leaderboard Channel (Required for public updates)

The bot can automatically post:
- rich upload notifications (embed with book, points earned, total credits, rank)
- updated top-10 leaderboard after new credits are added

To enable this, run the admin command in your server:

- `/set_leaderboard_channel channel:#your-channel`

After it’s set, the bot will post updates in that channel whenever someone earns credits for a new (non-duplicate) PDF upload.

### Getting Your Discord Bot Token

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to the "Bot" section and click "Add Bot"
4. Under "Token", click "Reset Token" and copy it to your `.env` file
5. Enable these Privileged Gateway Intents:
   - Message Content Intent
   - Server Members Intent

### Inviting the Bot to Your Server

1. In the Developer Portal, go to "OAuth2" > "URL Generator"
2. Select scopes:
   - `bot`
   - `applications.commands`
3. Select bot permissions:
   - Read Messages/View Channels []
   - Send Messages [x]
   - Add Reactions [x]
   - Read Message History [x]
   - Use Slash Commands [x]
4. Copy the generated URL and open it in your browser to invite the bot

### Getting Your Guild ID

1. Enable Developer Mode in Discord (User Settings > Advanced > Developer Mode)
2. Right-click your server name and click "Copy Server ID"
3. Paste it into your `.env` file

## Running the Bot

```bash
python main.py
```

The bot will:
1. Connect to Discord
2. Initialize the SQLite database
3. Sync slash commands to your server
4. Start monitoring for PDF uploads

## Database Schema

The bot uses SQLite with three tables:

### `credits` Table
| Column | Type | Description |
|--------|------|-------------|
| user_id | INTEGER (PK) | Discord user ID |
| points | INTEGER | Total cumulative pages uploaded |
| last_upload | DATETIME | Timestamp of most recent upload |

### `uploads` Table
| Column | Type | Description |
|--------|------|-------------|
| file_hash | TEXT (PK) | SHA-256 hash of the PDF |
| user_id | INTEGER | Discord user ID who uploaded |
| file_name | TEXT | Original filename |
| page_count | INTEGER | Number of pages in the PDF |
| upload_date | DATETIME | Timestamp of upload |

### `config` Table
| Column | Type | Description |
|--------|------|-------------|
| key | TEXT (PK) | Configuration key (e.g., `leaderboard_channel`) |
| value | TEXT | Configuration value |

## How It Works

1. **Real-time Monitoring**: By default, the bot listens for PDF uploads in **no channels**. After you configure one or more listen channels, it will only process PDFs in those channels.
2. **PDF Detection**: When a PDF is uploaded, the bot downloads and processes it
3. **Hash Calculation**: A SHA-256 hash is calculated to detect duplicates
4. **Page Counting**: pypdf extracts the page count from the PDF
5. **Credit Award**: If unique, the user receives credits equal to the page count
6. **Acknowledgment**: The bot reacts with 🏆, sends a confirmation message, posts a rich upload notification embed to the configured leaderboard channel (if set), and refreshes the public top-10 leaderboard

## Project Structure

```
vaahaka_credits_bot/
├── main.py              # Bot initialization and commands
├── database.py          # Database operations and queries
├── pdf_processor.py     # PDF processing and hashing
├── pyproject.toml       # Project dependencies
├── .env.example         # Environment variables template
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

## Troubleshooting

### Bot doesn't respond to commands
- Ensure slash commands are synced (should happen automatically on startup)
- Check that GUILD_ID is correct in your `.env` file
- Verify the bot has appropriate permissions in your server

### PDFs aren't being detected
- Ensure Message Content Intent is enabled in the Discord Developer Portal
- Check that the bot has "Read Message History" permission
- Verify the file is actually a PDF (not renamed)

### Database errors
- Delete `vaahaka_credits.db` to reset the database
- Ensure the bot has write permissions in the directory

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

This project is open source and available under the MIT License.
