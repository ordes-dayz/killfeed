"""
DayZ Log Parser for Discord Killfeed
Monitors the latest DayZ server ADM log file for kill events and sends them to Discord.
Automatically switches to newer ADM files as they are created.
"""

import os
import re
import time
import asyncio
import aiohttp
import argparse
import signal
import atexit
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Tuple, List
import logging

# Windows-specific imports for shared file access
if os.name == 'nt':  # Windows
    import msvcrt
    import io

# Optional hardcoded configuration. Keep blank to use arguments instead.
# Windows example: DAYZ_LOGS_DIR = r"C:\DayZServer\profiles"
# Linux example: DAYZ_LOGS_DIR = "/opt/dayzserver/profiles"
DISCORD_WEBHOOK_URL = ""
DAYZ_LOGS_DIR = ""

# Timings configuration
FILE_CHECK_INTERVAL = 30 # Seconds between checking for newer files
CHECK_INTERVAL = 5 # seconds
DELAY_BEFORE_SEND = 300 # seconds to wait before send webhook

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def open_shared_read(filepath: str):
    """
    Open file for reading with shared access on Windows, normal on Unix
    This allows other processes (like DayZ server) to write to the file
    
    On Windows, we use a different approach: read the file in chunks periodically
    rather than keeping it open continuously.
    """
    # For now, just return regular file handle - we'll modify the monitoring approach
    return open(filepath, 'r', encoding='utf-8', errors='ignore')


class DayZLogParser:
    def __init__(self, discord_webhook: str, logs_dir: str):
        self.config = {
            "discord_webhook": discord_webhook,
            "log_directory": logs_dir,
            "file_check_interval": FILE_CHECK_INTERVAL,
            "check_interval": CHECK_INTERVAL
        }
        self.last_position = {}  # Track file positions for each log file
        self.current_log_file: Optional[str] = None  # Currently monitored file
        self.last_file_check = 0  # Last time we checked for newer files
        self.message_queue: List[Tuple[str, datetime]] = []  # Queue for delayed messages (message, timestamp)
        self.shutdown_requested = False  # Flag for graceful shutdown

        # Compile regex patterns for PvP kills only
        self.kill_patterns = [
            # DayZ log format with "killed by Player" and distance
            re.compile(
                r'(\d{2}:\d{2}:\d{2}) \| Player "([^"]+)" .*killed by Player "([^"]+)" .*with (.+?) from ([\d.]+) meters?'),
            # DayZ log format with "killed by Player" without distance
            re.compile(
                r'(\d{2}:\d{2}:\d{2}) \| Player "([^"]+)" .*killed by Player "([^"]+)" .*with (.+?)(?:\s|$)'),
            # Format with "has been killed by player" and distance
            re.compile(
                r'(\d{4}-\d{2}-\d{2}:\d{2}:\d{2}:\d{2}) \| Player "([^"]+)" .*has been killed by player "([^"]+)" .*with (.+) from ([\d.]+)m'),
            # Format with "has been killed by player" without distance  
            re.compile(
                r'(\d{4}-\d{2}-\d{2}:\d{2}:\d{2}:\d{2}) \| Player "([^"]+)" .*has been killed by player "([^"]+)" .*with (.+)')
        ]


    def parse_adm_timestamp(self, filename: str) -> Optional[datetime]:
        """Parse timestamp from ADM filename"""
        import re
        from datetime import datetime
        
        # Pattern for underscore format: DayZServer_x64_2025_05_24_224940076.ADM
        underscore_pattern = r'DayZServer_x64_(\d{4})_(\d{2})_(\d{2})_(\d{2})(\d{2})(\d{2})(\d+)\.ADM'
        
        # Pattern for dash format: DayZServer_x64_2025-08-12_13-38-51.ADM
        dash_pattern = r'DayZServer_x64_(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})\.ADM'
        
        # Try underscore format first
        match = re.match(underscore_pattern, filename)
        if match:
            year, month, day, hour, minute, second = match.groups()[:6]
            try:
                return datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
            except ValueError:
                pass
                
        # Try dash format
        match = re.match(dash_pattern, filename)
        if match:
            year, month, day, hour, minute, second = match.groups()
            try:
                return datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
            except ValueError:
                pass
                
        return None

    def find_latest_adm_file(self) -> Optional[str]:
        """Find the latest ADM file in the configured directory"""
        log_dir = self.config["log_directory"]
        
        if not os.path.exists(log_dir):
            logger.warning(f"Log directory not found: {log_dir}")
            logger.info("Common DayZ ADM log directories:")
            if os.name == 'nt':  # Windows
                logger.info("  - C:\\DayZServer\\profiles")
                logger.info("  - C:\\Users\\[USER]\\Documents\\DayZ")
                logger.info("  - [DayZ Server Path]\\profiles")
            else:  # Linux/Unix
                logger.info("  - /opt/dayzserver/profiles")
                logger.info("  - /home/steam/dayzserver/profiles")
                logger.info("  - /profiles")
            return None
            
        # Find all ADM files
        adm_files = []
        try:
            for filename in os.listdir(log_dir):
                if filename.endswith('.ADM'):
                    filepath = os.path.join(log_dir, filename)
                    if os.path.exists(filepath):
                        adm_files.append((filepath, filename))
        except OSError as e:
            logger.error(f"Error reading directory {log_dir}: {e}")
            return None
            
        if not adm_files:
            logger.warning(f"No ADM files found in {log_dir}")
            return None
            
        # Find the latest file by parsing timestamps from filenames
        latest_file = None
        latest_timestamp = None
        
        for filepath, filename in adm_files:
            # Handle static filename (DayZServer_x64.ADM) - use file modification time
            if filename == "DayZServer_x64.ADM":
                try:
                    mod_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                    if latest_timestamp is None or mod_time > latest_timestamp:
                        latest_timestamp = mod_time
                        latest_file = filepath
                except OSError:
                    pass
            else:
                # Parse timestamp from filename
                timestamp = self.parse_adm_timestamp(filename)
                if timestamp and (latest_timestamp is None or timestamp > latest_timestamp):
                    latest_timestamp = timestamp
                    latest_file = filepath
                    
        if latest_file:
            logger.info(f"Latest ADM file: {latest_file} (timestamp: {latest_timestamp})")
            
        return latest_file

    def parse_kill_event(self, line: str) -> Optional[Dict]:
        """Parse a log line for kill events"""
        for pattern in self.kill_patterns:
            match = pattern.search(line)
            if match:
                return self.extract_kill_data(match, pattern, line)
        return None

    def extract_kill_data(self, match, pattern, original_line: str) -> Dict:
        """Extract kill data from regex match - PvP kills only"""
        groups = match.groups()

        # Only process PvP kills (both "killed by Player" and "has been killed by player")
        if not ("killed by Player" in original_line or "has been killed by player" in original_line):
            return None

        # Extract data based on pattern match
        if len(groups) >= 4:
            timestamp = groups[0] if groups[0] else datetime.now().strftime("%H:%M:%S")
            victim = groups[1]
            killer = groups[2]
            weapon = groups[3]
            # Distance might be in groups[4] if present
            distance = float(groups[4]) if len(groups) > 4 and groups[4] else 0
        else:
            return None

        kill_data = {
            "timestamp": timestamp,
            "victim": victim,
            "killer": killer,
            "weapon": weapon,
            "distance": distance,
            "original_line": original_line
        }

        return kill_data

    def sanitize_discord_text(self, text: str) -> str:
        """Escape Discord markdown characters to prevent formatting issues"""
        if not text:
            return text
        
        # Escape Discord markdown characters
        escape_chars = ['\\', '*', '_', '`', '~', '|']
        sanitized = text
        
        for char in escape_chars:
            sanitized = sanitized.replace(char, f'\\{char}')
        
        return sanitized

    def format_discord_message(self, kill_data: Dict) -> str:
        """Format kill data into Discord message - PvP kills only"""
        if not kill_data:
            return ""

        distance_str = f" ({kill_data['distance']:.0f}m)" if kill_data["distance"] > 0 else ""
        weapon_str = kill_data["weapon"] if kill_data["weapon"] != "Unknown" else "unknown weapon"
        
        # Sanitize player names to prevent Discord formatting issues
        safe_killer = self.sanitize_discord_text(kill_data['killer'])
        safe_victim = self.sanitize_discord_text(kill_data['victim'])

        return f"**{safe_killer}** killed **{safe_victim}** with {weapon_str}{distance_str}"

    def queue_message(self, message: str):
        """Queue a message for delayed sending"""
        if message:
            send_time = datetime.now() + timedelta(seconds=DELAY_BEFORE_SEND)
            self.message_queue.append((message, send_time))
            logger.info(f"Queued message for sending at {send_time.strftime('%H:%M:%S')}: {message}")

    async def process_message_queue(self):
        """Background task to process queued messages"""
        while not self.shutdown_requested:
            try:
                now = datetime.now()
                messages_to_send = []
                remaining_messages = []
                
                # Check which messages are ready to send
                for message, send_time in self.message_queue:
                    if now >= send_time:
                        messages_to_send.append(message)
                    else:
                        remaining_messages.append((message, send_time))
                
                # Update queue with remaining messages
                self.message_queue = remaining_messages
                
                # Send ready messages
                for message in messages_to_send:
                    await self.send_to_discord(message)
                
                # Wait before checking again
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error processing message queue: {e}")
                await asyncio.sleep(5)

    async def graceful_shutdown(self):
        """Send all queued messages immediately before shutdown"""
        logger.info("Graceful shutdown requested - sending all queued messages immediately")
        
        if self.message_queue:
            logger.info(f"Sending {len(self.message_queue)} queued messages before shutdown")
            
            # Send all queued messages immediately
            for message, _ in self.message_queue:
                try:
                    await self.send_to_discord(message)
                except Exception as e:
                    logger.error(f"Error sending message during shutdown: {e}")
            
            # Clear the queue
            self.message_queue.clear()
            logger.info("All queued messages sent")
        else:
            logger.info("No queued messages to send")

    def request_shutdown(self):
        """Request graceful shutdown (called by signal handlers)"""
        logger.info("Shutdown signal received")
        self.shutdown_requested = True

    async def send_to_discord(self, message: str) -> bool:
        """Send message to Discord webhook"""
        if not message:
            return False

        payload = {
            "content": message,
            "username": "DayZ Killfeed",
            "avatar_url": "https://cdn.cloudflare.steamstatic.com/steam/apps/221100/header.jpg"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.config["discord_webhook"], json=payload) as response:
                    if response.status == 204:
                        logger.info(f"Sent to Discord: {message}")
                        return True
                    else:
                        logger.error(f"Discord webhook failed: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Error sending to Discord: {e}")
            return False

    def get_file_position(self, filepath: str) -> int:
        """Get last read position for a file"""
        return self.last_position.get(filepath, 0)

    def set_file_position(self, filepath: str, position: int):
        """Set last read position for a file"""
        self.last_position[filepath] = position


    def should_check_for_newer_file(self) -> bool:
        """Check if it's time to look for a newer file"""
        current_time = time.time()
        if current_time - self.last_file_check >= self.config["file_check_interval"]:
            self.last_file_check = current_time
            return True
        return False

    async def monitor_latest_file(self):
        """Monitor the latest ADM file, switching to newer files when they appear"""
        logger.info("Starting DayZ ADM file monitoring...")
        
        while not self.shutdown_requested:
            # Find initial file or check for newer files if current file monitoring exited
            if self.current_log_file is None:
                latest_file = self.find_latest_adm_file()
                
                if not latest_file:
                    logger.error("No ADM files found. Retrying in 30 seconds...")
                    await asyncio.sleep(30)
                    continue
                    
                logger.info(f"Starting monitoring: {latest_file}")
                self.current_log_file = latest_file
                # Start at end of new file to only process new lines
                try:
                    file_size = os.path.getsize(latest_file)
                    self.set_file_position(latest_file, file_size)
                    logger.info(f"Starting at end of file (position: {file_size})")
                except OSError:
                    self.set_file_position(latest_file, 0)
            else:
                # Check if we need to switch files after monitor_single_file exited
                latest_file = self.find_latest_adm_file()
                if latest_file and latest_file != self.current_log_file:
                    logger.info(f"Switching from {self.current_log_file} to {latest_file}")
                    self.current_log_file = latest_file
                    # Start at end of new file to only process new lines
                    try:
                        file_size = os.path.getsize(latest_file)
                        self.set_file_position(latest_file, file_size)
                        logger.info(f"Starting at end of file (position: {file_size})")
                    except OSError:
                        self.set_file_position(latest_file, 0)
                    
            if not self.current_log_file:
                await asyncio.sleep(5)
                continue
                
            # Monitor the current file (this will exit when a newer file is found)
            try:
                await self.monitor_single_file(self.current_log_file)
                # After monitor_single_file exits, loop back to check for file switch
            except Exception as e:
                logger.error(f"Error monitoring {self.current_log_file}: {e}")
                await asyncio.sleep(5)

    async def monitor_single_file(self, filepath: str):
        """Monitor a single log file for changes using periodic reads (Windows-friendly)"""
        
        last_file_check_time = time.time()
        
        while not self.shutdown_requested:
            try:
                # Open file, read new content, then close it (prevents locking)
                last_pos = self.get_file_position(filepath)
                
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    # Seek to last known position
                    f.seek(last_pos)
                    
                    # Read all available new lines
                    new_lines = []
                    while True:
                        line = f.readline()
                        if line:
                            new_lines.append(line)
                        else:
                            break
                    
                    # Update position after reading
                    new_pos = f.tell()
                    
                # File is now closed, process the lines we read
                for line in new_lines:
                    kill_data = self.parse_kill_event(line)
                    if kill_data:
                        message = self.format_discord_message(kill_data)
                        if message:
                            self.queue_message(message)
                
                # Update position after processing all lines
                if new_lines:
                    self.set_file_position(filepath, new_pos)
                    
                # Check for newer files periodically
                current_time = time.time()
                if current_time - last_file_check_time >= self.config["file_check_interval"]:
                    last_file_check_time = current_time
                    latest_file = self.find_latest_adm_file()
                    
                    # If we found a newer file, exit this function to switch
                    if latest_file and latest_file != filepath:
                        logger.info(f"Found newer file {latest_file}, exiting current file monitoring")
                        break

                # Check if file was rotated (size decreased)
                try:
                    current_size = os.path.getsize(filepath)
                    if current_size < last_pos:
                        logger.info(f"Log file rotated: {filepath}")
                        self.set_file_position(filepath, 0)
                except OSError:
                    # File might have been deleted/moved
                    logger.warning(f"Could not access file: {filepath}")
                    break
                    
                # Wait before next check
                await asyncio.sleep(1)
                
            except FileNotFoundError:
                logger.warning(f"Log file not found: {filepath}")
                await asyncio.sleep(5)
                break
            except Exception as e:
                logger.error(f"Error monitoring {filepath}: {e}")
                await asyncio.sleep(5)

    async def run(self):
        """Main run loop"""
        logger.info("Starting DayZ Log Parser...")
        logger.info(f"Monitoring directory: {self.config['log_directory']}")
        logger.info(f"File check interval: {self.config['file_check_interval']} seconds")
        logger.info(f"Webhook delay: {DELAY_BEFORE_SEND} seconds")

        # Set up signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}")
            self.request_shutdown()

        # Register signal handlers (optimized for Windows)
        try:
            signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C (all platforms)
            signal.signal(signal.SIGTERM, signal_handler)  # Termination signal (all platforms)
            
            # Windows-specific signals
            if os.name == 'nt':  # Windows
                try:
                    signal.signal(signal.SIGBREAK, signal_handler)  # Ctrl+Break (Windows)
                    logger.info("Windows signal handlers registered (SIGINT, SIGTERM, SIGBREAK)")
                except AttributeError:
                    logger.info("Windows signal handlers registered (SIGINT, SIGTERM)")
            else:
                logger.info("Unix signal handlers registered (SIGINT, SIGTERM)")
                
        except Exception as e:
            logger.warning(f"Could not set up some signal handlers: {e}")

        try:
            # Start background task for processing message queue
            queue_task = asyncio.create_task(self.process_message_queue())
            
            # Start file monitoring
            monitor_task = asyncio.create_task(self.monitor_latest_file())
            
            # Run both tasks concurrently until shutdown is requested
            await asyncio.gather(queue_task, monitor_task, return_exceptions=True)
            
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received")
            self.request_shutdown()
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            self.request_shutdown()
        finally:
            # Always attempt graceful shutdown
            await self.graceful_shutdown()


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='DayZ Log Parser for Discord Killfeed')
    parser.add_argument('--discord-webhook', type=str, help='Discord webhook URL')
    parser.add_argument('--logs-path', type=str, help='Path to DayZ logs directory')
    return parser.parse_args()

def get_config():
    """Get configuration from constants and arguments"""
    args = parse_arguments()
    
    # Use constants if set, otherwise use arguments
    discord_webhook = DISCORD_WEBHOOK_URL if DISCORD_WEBHOOK_URL else args.discord_webhook
    logs_dir = DAYZ_LOGS_DIR if DAYZ_LOGS_DIR else args.logs_path
    
    # Validate required configuration
    if not discord_webhook:
        logger.error("Discord webhook URL is required. Set DISCORD_WEBHOOK_URL constant or use --discord-webhook argument")
        return None, None
        
    if not logs_dir:
        logger.error("Logs directory is required. Set DAYZ_LOGS_DIR constant or use --logs-path argument")
        return None, None
    
    return discord_webhook, logs_dir

# Main execution
if __name__ == "__main__":
    discord_webhook, logs_dir = get_config()
    if discord_webhook and logs_dir:
        parser = DayZLogParser(discord_webhook, logs_dir)
        asyncio.run(parser.run())
    else:
        exit(1)
