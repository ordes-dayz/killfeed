# DayZ Server Discord Killfeed

A Python script that monitors DayZ server logs and sends **PvP kill notifications** to Discord with a configurable delay. Only player vs player kills are reported - no suicides, animal kills, or infections.

## ✨ Features

- **🎯 PvP Only**: Reports only player vs player kills
- **⏰ Delayed Notifications**: 5-minute delay by default (configurable)
- **🔄 Real-time Monitoring**: Continuously monitors log files without blocking
- **📁 Auto File Detection**: Automatically finds and switches to the latest ADM file
- **🛡️ Graceful Shutdown**: Sends all queued messages when script is stopped
- **🖥️ Cross-Platform**: Works on Windows and Linux
- **⚙️ Flexible Configuration**: Use constants or command-line arguments

## 📋 Requirements

- Python 3.7+
- `aiohttp` library
- `asyncio` library (included with Python)

## 🚀 Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd dayz-killfeed
```

2. Install dependencies:
```bash
pip install aiohttp asyncio
```

## ⚙️ Configuration

### Method 1: Edit Constants (Recommended for Windows Services)

Edit the constants in `killfeed.py`:

```python
# Discord webhook URL
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"

# Path to DayZ logs directory
DAYZ_LOGS_DIR = r"C:\DayZServer\profiles"  # Windows
# DAYZ_LOGS_DIR = "/opt/dayzserver/profiles"  # Linux

# Timing settings
DELAY_BEFORE_SEND = 300  # 5 minutes delay before sending webhooks
FILE_CHECK_INTERVAL = 30  # Check for newer files every 30 seconds
```

### Method 2: Command-Line Arguments

```bash
python killfeed.py --discord-webhook "YOUR_WEBHOOK_URL" --logs-path "C:\DayZServer\profiles"
```

## 🎮 DayZ Server Setup

Your DayZ server must be configured to generate ADM log files:

1. **Server Launch Parameter**: Add `-adminlog` to your server startup command
2. **Server Config**: Enable admin logging in `serverDZ.cfg`
3. **Log Location**: ADM files are created in the profiles directory (specified by `-profiles=` parameter)

## 💬 Discord Setup

1. **Create Webhook**: Go to your Discord server → Channel Settings → Integrations → Webhooks → New Webhook
2. **Copy URL**: Copy the webhook URL and use it in the configuration
3. **Test**: The script will send messages in this format:
   ```
   **PlayerKiller** killed **PlayerVictim** with M4A1 (150m)
   ```

## Running as a Service

### Windows (using NSSM):
```cmd
nssm install DayZKillfeed
nssm set DayZKillfeed Application python.exe
nssm set DayZKillfeed AppParameters "C:\path\to\dayz_log_parser.py"
nssm start DayZKillfeed
```

### Linux (systemd):
```ini
[Unit]
Description=DayZ Killfeed Parser
After=network.target

[Service]
Type=simple
User=dayz
ExecStart=/usr/bin/python3 /path/to/dayz_log_parser.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## 🔧 How It Works

### 1. **File Monitoring System**
- Scans the configured directory for `.ADM` files
- Automatically detects the **latest** ADM file based on timestamps in filename
- **Switches monitoring** when newer ADM files are created (e.g., server restart)
- **Starts at end of file** to avoid processing old events

### 2. **Real-Time Log Processing**
- Monitors the latest ADM file continuously
- **Parses new lines** as they're written by the DayZ server
- Uses regex patterns to identify PvP kill events
- **Filters out** suicides, animal kills, and infections

### 3. **Delayed Webhook System**
- **Immediately parses** kill events (no delay in log reading)
- **Queues messages** with a future send time (default: 5 minutes later)
- **Background task** processes the queue and sends webhooks when ready
- **Non-blocking**: Log monitoring continues while webhooks are delayed

### 4. **Graceful Shutdown**
- **Signal handling**: Responds to Ctrl+C, SIGTERM, and Windows-specific signals
- **Immediate flush**: Sends all queued messages before shutdown
- **No lost events**: Ensures no kill notifications are lost when script stops

### 5. **Supported Log Formats**

The script automatically handles different ADM file naming patterns:

#### Static Filename
- `DayZServer_x64.ADM` - Uses file modification time

#### Timestamped Filenames  
- `DayZServer_x64_2025_05_24_224940076.ADM` (underscore format)
- `DayZServer_x64_2025-08-12_13-38-51.ADM` (dash format)

### 6. **Kill Event Detection**

Parses these log line formats:
```
22:19:08 | Player "Victim" (DEAD) (id=123) killed by Player "Killer" (id=456) with DMR from 92.6 meters
```

Extracts:
- **Timestamp**: `22:19:08`  
- **Victim**: `"Victim"`
- **Killer**: `"Killer"`
- **Weapon**: `DMR`
- **Distance**: `92.6 meters` (if available)

### 7. **Discord Message Formatting**

Player names are automatically sanitized to prevent Discord markdown formatting issues:
- Special characters (`*`, `_`, `` ` ``, `~`, `|`, `\`) are escaped with backslashes
- This ensures player names like `Player*123` or `_Sniper_` display correctly in Discord
- Bold formatting is preserved around sanitized names

## 🖥️ Usage Examples

### Windows (Command Prompt)
```cmd
# Using arguments
python killfeed.py --discord-webhook "https://discord.com/api/webhooks/..." --logs-path "C:\DayZServer\profiles"

# Using hardcoded constants
python killfeed.py
```

### Linux (Terminal)
```bash
# Using arguments  
python3 killfeed.py --discord-webhook "https://discord.com/api/webhooks/..." --logs-path "/opt/dayzserver/profiles"

# Using hardcoded constants
python3 killfeed.py
```

### Windows Service
For running as a Windows service, use hardcoded constants and create a service wrapper.

## 📊 Example Output

```
2025-08-15 14:30:15,123 - INFO - Starting DayZ Log Parser...
2025-08-15 14:30:15,124 - INFO - Monitoring directory: C:\DayZServer\profiles
2025-08-15 14:30:15,124 - INFO - Webhook delay: 300 seconds
2025-08-15 14:30:15,125 - INFO - Windows signal handlers registered (SIGINT, SIGTERM, SIGBREAK)
2025-08-15 14:30:15,126 - INFO - Latest ADM file: DayZServer_x64_2025-08-15_14-30-00.ADM
2025-08-15 14:30:15,127 - INFO - Starting at end of file (position: 1245)
2025-08-15 14:32:30,445 - INFO - Queued message for sending at 14:37:30: **Sniper123** killed **Runner456** with DMR (180m)
2025-08-15 14:37:30,891 - INFO - Sent to Discord: **Sniper123** killed **Runner456** with DMR (180m)
```

## 🛠️ Troubleshooting

### Common Issues

**"No ADM files found"**
- Check that your DayZ server has `-adminlog` parameter
- Verify the logs directory path is correct
- Ensure admin logging is enabled in `serverDZ.cfg`

**"Discord webhook failed"**  
- Verify the webhook URL is correct and valid
- Check Discord server permissions for the webhook

**Script stops unexpectedly**
- Check Python version (requires 3.7+)  
- Verify all dependencies are installed
- Check file permissions for the logs directory

**Missing Kill Events**
- Most likely regexp pattern doesn't match. You will need to update it manually.
- Some kills might not be logged depending on server config
- Check `adminLogPlayerHitsOnly` setting in `serverDZ.cfg`
- Ensure the server isn't filtering certain event types

### Common DayZ Log Directories

**Windows:**
- `C:\DayZServer\profiles`
- `C:\Users\[USER]\Documents\DayZ`
- `[Server Installation Path]\profiles`

**Linux:**
- `/opt/dayzserver/profiles`  
- `/home/steam/dayzserver/profiles`
- `/profiles`

## 📝 Configuration Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `DISCORD_WEBHOOK_URL` | `""` | Discord webhook URL for notifications |
| `DAYZ_LOGS_DIR` | `""` | Path to DayZ server logs directory |
| `DELAY_BEFORE_SEND` | `300` | Seconds to wait before sending webhooks |
| `FILE_CHECK_INTERVAL` | `30` | Seconds between checking for newer ADM files |
| `CHECK_INTERVAL` | `5` | General polling interval for file monitoring |

## 🔒 Security Notes

- Keep your Discord webhook URL private
- The script only reads log files - no server modifications
- No sensitive data is logged or transmitted
- Webhook URLs are not logged in console output

## 📄 License

This project is open source. Feel free to modify and distribute.

## 🤝 Contributing

Issues and pull requests are welcome! Please ensure any modifications maintain compatibility with both Windows and Linux environments.