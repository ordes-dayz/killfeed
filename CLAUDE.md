# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **DayZ Log Parser** that monitors DayZ server ADM log files for **PvP kill events only** and forwards them to Discord via webhooks with a configurable delay. The parser automatically finds and monitors the **latest ADM file** in a directory, switching to newer files as they're created. It provides **delayed killfeed notifications** for DayZ game servers while continuing to monitor logs in real-time.

## Development Commands

### Setup & Installation
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment (Linux/Mac)
source venv/bin/activate

# Activate virtual environment (Windows)
venv\Scripts\activate

# Install dependencies
pip install aiohttp
# Note: asyncio is included with Python 3.7+
```

### Running the Application
```bash
# Using command-line arguments
python killfeed.py --discord-webhook "URL" --logs-path "/path/to/logs"

# Using hardcoded constants (recommended for Windows services)
python killfeed.py
```

## Architecture & Key Components

### Core Application (`killfeed.py`)
- **DayZLogParser Class**: Main parser that handles log monitoring, message queuing, and Discord integration
- **Async File Monitoring**: Uses asyncio to monitor log files without blocking webhook processing
- **Message Queue System**: Queues messages for delayed sending while continuing real-time log monitoring
- **Regex Pattern Matching**: Optimized regex patterns specifically for DayZ PvP kill events
- **Position Tracking**: Maintains file read positions and starts at end of new files
- **Cross-Platform Signal Handling**: Graceful shutdown with immediate message flushing

### Key Features
- **PvP Only**: Filters and reports only player vs player kills (no suicides, animal kills, infections)
- **Delayed Notifications**: 5-minute delay by default (configurable via `DELAY_BEFORE_SEND`)
- **Real-time Log Processing**: No delay in reading/parsing - only in sending webhooks
- **Latest File Tracking**: Automatically finds and monitors the most recent ADM file
- **Smart File Switching**: Detects when newer ADM files are created and switches monitoring
- **Multiple Timestamp Formats**: Parses both underscore and dash timestamp formats in filenames
- **Graceful Shutdown**: Sends all queued messages immediately when script is stopped
- **Windows Optimized**: Enhanced for Windows deployment with appropriate signal handling

### Configuration System
The parser uses **constants and command-line arguments** (no JSON config files):

#### Constants in `killfeed.py`:
- `DISCORD_WEBHOOK_URL`: Discord webhook URL (leave blank to use arguments)
- `DAYZ_LOGS_DIR`: Path to DayZ logs directory (leave blank to use arguments)
- `DELAY_BEFORE_SEND`: Seconds to wait before sending webhooks (default: 300)
- `FILE_CHECK_INTERVAL`: Seconds between checking for newer files (default: 30)
- `CHECK_INTERVAL`: General polling interval (default: 5)

#### Command-line Arguments:
- `--discord-webhook`: Discord webhook URL
- `--logs-path`: Path to DayZ logs directory

### Log File Handling
- **Single Active File**: Monitors one ADM file at a time (the latest)
- **Automatic File Detection**: Scans directory for all ADM files and selects the newest
- **Timestamp Parsing**: Extracts creation time from filename patterns
- **Start at End**: New files are read from the end to avoid processing old events
- **Position Persistence**: Remembers where it left off reading each file
- **Error Resilience**: Handles missing files and permission issues gracefully

### Discord Integration
- **Webhook-based**: Uses Discord webhooks for message delivery
- **Simple Text Format**: Clean messages without emojis: `**Killer** killed **Victim** with Weapon (Distance)`
- **Fixed Branding**: Uses "DayZ Killfeed" as username with DayZ game icon

### Message Queue & Delay System
- **Queue-based**: Messages are queued with future send times
- **Background Processing**: Separate async task processes the queue
- **Non-blocking**: Log monitoring continues while messages are delayed
- **Immediate Flush**: All queued messages sent immediately on shutdown

### Graceful Shutdown System
- **Cross-platform Signals**: Handles SIGINT (Ctrl+C), SIGTERM, and Windows SIGBREAK
- **Message Preservation**: Sends all queued messages before shutdown
- **Clean Exit**: Ensures no kill events are lost when script stops

## File Structure

```
dayz-killfeed/
├── killfeed.py              # Core parser application (no shebang for Windows)
├── requirements.txt     # Python dependencies (aiohttp only)
├── SETUP.md            # Detailed setup instructions for DayZ server configuration
├── README.md           # Complete user documentation and setup guide
├── CLAUDE.md           # This development documentation file
├── logs-examples/      # Example ADM and log files for testing
└── venv/               # Python virtual environment
```

Note: No JSON configuration files - uses constants and arguments only.

## DayZ Server Integration

This parser requires specific DayZ server configuration:
- Server must run with `-adminlog` parameter
- Admin logging must be enabled in `serverDZ.cfg`
- Log files are typically found in the profiles directory specified by `-profiles=` parameter

## Supported ADM File Formats

The parser recognizes these ADM file naming patterns:

### Static Filename
- `DayZServer_x64.ADM` - Uses file modification time for comparison

### Timestamped Filenames
- **Underscore format**: `DayZServer_x64_2025_05_24_224940076.ADM`
- **Dash format**: `DayZServer_x64_2025-08-12_13-38-51.ADM`

### Common ADM Log Directories

**Windows:**
- `C:\DayZServer\profiles`
- `C:\Users\[USER]\Documents\DayZ`
- `[Server Installation Path]\profiles`

**Linux:**
- `/opt/dayzserver/profiles`
- `/home/steam/dayzserver/profiles`
- `/profiles`

## Development Notes

### Technical Architecture
- **Python 3.7+ Required**: Uses modern asyncio features
- **Async Design**: Two concurrent tasks - file monitoring and message queue processing
- **No Hash-based Deduplication**: Removed in favor of starting at end of new files
- **Optimized Regex**: Patterns specifically designed for DayZ PvP kill log formats
- **Memory Efficient**: Minimal memory footprint with queue-based message handling

### File Monitoring Logic
1. **Latest File Detection**: Scans directory for all `.ADM` files
2. **Timestamp Extraction**: Parses creation time from filename or uses file modification time
3. **File Selection**: Always monitors the file with the latest timestamp
4. **Auto-switching**: Detects and switches to newer files automatically
5. **Position Management**: Starts at end of new files, maintains position for current file

### Message Processing Flow
1. **Parse Event**: Regex pattern matches PvP kill events in real-time
2. **Queue Message**: Add to queue with future send time (now + delay)
3. **Background Processing**: Separate task checks queue and sends ready messages
4. **Discord Delivery**: HTTP POST to webhook URL with formatted message

### Kill Event Detection
Parses log formats like:
```
22:19:08 | Player "Victim" (DEAD) (id=123) killed by Player "Killer" (id=456) with DMR from 92.6 meters
```

Extracts:
- Timestamp: `22:19:08`
- Victim: `"Victim"`
- Killer: `"Killer"`
- Weapon: `DMR`
- Distance: `92.6` (if present)

### Error Handling & Resilience
- **File Access Errors**: Graceful handling of missing or locked files
- **Network Errors**: Continues operation if Discord webhook fails
- **Signal Handling**: Cross-platform shutdown signals with message preservation
- **Exception Recovery**: Continues monitoring even if individual events fail processing

### Windows-Specific Optimizations
- **No Shebang**: Removed `#!/usr/bin/env python3` for Windows deployment
- **Signal Handling**: Includes Windows-specific SIGBREAK (Ctrl+Break) support
- **Path Examples**: Windows-style path examples in error messages and documentation
- **Service Ready**: Designed to run as Windows service with hardcoded constants

### Testing Approach
- **Real ADM Files**: Uses actual DayZ server log files in `logs-examples/`
- **End-to-End Testing**: Tests file monitoring, parsing, queuing, and Discord delivery
- **Signal Testing**: Verifies graceful shutdown with queued message flushing
- **Cross-platform Testing**: Validates behavior on both Windows and Unix systems

### Performance Considerations
- **Single File Monitoring**: Only monitors one file at a time for efficiency
- **Pre-compiled Regex**: Patterns compiled once at startup
- **Minimal I/O**: Reads only new lines as they're written
- **Async Operations**: Non-blocking design for concurrent log monitoring and webhook sending

## Important Implementation Details

### Configuration Priority
1. **Constants in Code**: Used if non-empty
2. **Command-line Arguments**: Used if constants are empty
3. **Validation**: Both webhook URL and logs directory are required

### Message Queue Behavior
- **Thread-safe**: Uses asyncio-compatible queue operations
- **Persistent**: Messages remain queued even if Discord webhook fails temporarily
- **Ordered**: Messages sent in the order they were queued
- **Immediate on Shutdown**: All queued messages sent instantly when script stops

### Regex Pattern Details
The script uses multiple regex patterns to handle different DayZ log formats:
- Pattern 1: Standard format with distance in meters
- Pattern 2: Alternative format without distance
- Pattern 3: Full timestamp format with "has been killed by player"
- Pattern 4: Fallback patterns for edge cases

Only lines containing "killed by Player" or "has been killed by player" are processed.