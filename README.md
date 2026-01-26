# PyGate - Python FidoNet-NNTP Gateway

PyGate is a Python-based gateway system that bridges FidoNet echomail and NNTP newsgroups, allowing
seamless message exchange between the two networks. PyGate is designed to run on the NNTP news server,
but can be run on a different computer as a client only.

**Version:** 1.5.6
**Author:** Stephen Walsh
**Contact:** vk3heg@gmail.com | FidoNet 3:633/280 | FSXNet 21:1/195 | Amiganet 39:901/280
**Based on:** SoupGate by Tom Torfs

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Log Management](#log-management)
- [Message Hold System](#message-hold-system)
- [Spam Filtering](#spam-filtering)
- [Areafix Wildcard Protection](#areafix-wildcard-protection)
- [Troubleshooting](#troubleshooting)
- [File Structure](#file-structure)
- [Examples](#examples)

## Features

### Core Functionality
- **Bidirectional Gateway**: Messages flow seamlessly between FidoNet and NNTP
- **Flexible Deployment Modes**: Full gateway mode or client-only mode
- **Area Mapping**: Flexible mapping between FidoNet areas and NNTP newsgroups
- **Message Hold System**: Manual review and approval of messages
- **Spam Filtering**: Advanced regex-based filtering with built-in patterns
- **Netmail Notifications**: Automatic notifications for held messages
- **Areafix Support**: Dynamic area management via netmail with wildcard protection
- **Character Set Handling**: Proper encoding conversion per FTS standards

### Advanced Features
- **Message Deduplication**: Prevents duplicate messages
- **Cross-posting Control**: Configurable limits on cross-posted messages
- **Timezone Support**: Proper timezone handling (TZUTC)
- **Message Threading**: Preserves reply chains and references
- **Administrative Panel**: Admin panel interface for message review of held messages, filter management,
-   newsrc management, newsgroups list viewing.

## Requirements

- Python 3.7 or higher
- NNTP server access
- FidoNet mailer (binkd recommended)
- Required Python packages:
  - `configparser`
  - `pathlib`
  - `logging`
  - `datetime`
  - `uuid`
  - `json`
  - `paramiko` (for SSH/remote ctlinnd on Windows deployments)
  - `psutil` (for automation script process management)

## Installation

1. **Extract PyGate files** to your chosen directory:
   ```bash
   mkdir /opt/pygate
   cd /opt/pygate
   # Extract files here
   ```

2. **Set executable permissions**:
   ```bash
   chmod +x pygate.py admin_panel.py
   chmod +x src/*.py
   chmod +x bin/*
   ```

3. **Install Python dependencies** (if needed):
   ```bash
   # Linux: Install paramiko and psutil
   pip3 install paramiko psutil

   # Windows: Install paramiko and psutil
   # Open Command Prompt or PowerShell as Administrator
   pip install paramiko psutil

   # If paramiko fails on Windows, install Microsoft C++ Build Tools first:
   # Download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/
   # Then retry: pip install paramiko
   ```

4. **Copy the FidoNet mailer**:
   ```bash
   # For Linux: Copy binkd binary to bin/ directory
   cp /usr/local/bin/binkd bin/

   # For Windows: Copy binkd.exe to bin\ directory
   copy C:\binkd\binkdwin.exe bin\
   ```

5. **Directory structure is already organized**:
   ```bash
   # Directories are pre-organized:
   # config/     - Configuration files
   # src/        - Python modules
   # data/       - Runtime data (inbound, outbound, logs, hold, temp)
   # bin/        - Binaries and scripts
   # cache/      - Cache files
   ```

6. **Configure your system** (see Configuration section)

## Configuration

### Main Configuration File: `pygate.cfg`

Located in the PyGate root directory, the main configuration file controls all aspects of PyGate operation:

```ini
[Gateway]
# Gateway identification
name = PyGate
sysop = Your Name
location = Your Location
origin_line = Your BBS Name, PyGate NNTP<>Fido Gate

# Operation mode
# client_mode = false    # Default: Full gateway mode (manages NNTP server)
# client_mode = true     # Client mode: NNTP client only (no server management)

[FidoNet]
# Your FidoNet addresses
gateway_address = 1:123/456
linked_address = 1:123/0

# Authentication
packet_password = your_packet_password
areafix_password = your_areafix_password

# Directories
inbound_dir = data/inbound
outbound_dir = data/outbound
temp_dir = data/temp
hold_dir = data/hold

[NNTP]
# NNTP server configuration
host = news.example.com
port = 119
username = your_username
password = your_password
use_ssl = false
timeout = 30

[Files]
# File locations
areas_file = config/newsrc
log_file = data/logs/pygate.log
log_level = INFO

# Log retention (days to keep compressed log files)
# Default: 30 days
log_retention_days = 30

[SpamFilter]
# Spam filtering settings
enabled = true
filter_file = config/filter.cfg
maxcrosspost = 4
initialfetch = 200

[Arearemap]
# Area mappings: FIDO_AREA = newsgroup.name
AMIGA-DEMOS = comp.sys.amiga.demos
LINUX = comp.os.linux.misc
PYTHON = comp.lang.python

# Message hold settings
Hold = yes
notify_sysop = yes
```

### Deployment Modes

PyGate supports two deployment modes:

#### Full Gateway Mode (Default)
In this mode, PyGate manages both the NNTP connection and the server configuration:
- Updates local newsrc file when areas are added/removed
- Executes `ctlinnd` commands to create/remove newsgroups on NNTP server
- Requires server administrative privileges or SSH access
- Best for deployments where PyGate runs on or manages the news server

```ini
[Gateway]
client_mode = false  # or omit this line (false is default)
```

#### Client-Only Mode
In this mode, PyGate operates as a standard NNTP client without server management:
- Updates local newsrc file when areas are added/removed
- Does NOT execute `ctlinnd` commands
- Assumes newsgroups already exist on the remote NNTP server
- Does not require server administrative privileges
- Best for connecting to external/remote news servers you don't control

```ini
[Gateway]
client_mode = true
```

**When to use client-only mode:**
- Connecting to a remote news server you don't administer
- Using a commercial or third-party news provider
- Testing PyGate without affecting server configuration
- Security-restricted environments where ctlinnd access is unavailable

**Note:** In client-only mode, areafix operations will still update your local newsrc file, but you
  must ensure the corresponding newsgroups exist on the NNTP server before subscribing to them.

### Areas Configuration: `config/newsrc`

The newsrc file tracks article numbers for each newsgroup:

```
# Format: newsgroup: low_number-high_number
comp.sys.amiga.demos: 0-53
alt.bbs.mystic: 0-127
comp.lang.python: 0-2341
```

Use the admin panel's Newsgroup Manager to keep this file organized:

```bash
python3 admin_panel.py
# Select option 6: Newsgroup Manager
# Select option 1: Sort newsrc file alphabetically
# Multiple additional management options available
```

### Filter Configuration: `config/filter.cfg`

See the [Spam Filtering](#spam-filtering) section for detailed filter configuration.

## Usage

### Command Line Options

PyGate supports several operation modes:

```bash
# Import FidoNet packets to NNTP
./pygate.py --import

# Export NNTP messages to FidoNet
./pygate.py --export

# Process approved held messages
./pygate.py --process-held

# Pack outbound messages
./pygate.py --pack

# Configuration check
./pygate.py --check

# Areafix processing only
./pygate.py --areafix

# Maintenance tasks
./pygate.py --maintenance
```

### Typical Workflow

1. **Import**: Process incoming FidoNet packets
   ```bash
   ./pygate.py --import
   ```

2. **Export**: Fetch and process NNTP messages
   ```bash
   ./pygate.py --export
   ```

3. **Review**: Check for held messages (if using hold system)
   ```bash
   python3 admin_panel.py
   ```

4. **Process**: Handle approved messages
   ```bash
   ./pygate.py --process-held
   ```

### Automated Operation

PyGate includes a cross-platform automation script (`bin/gate.py`) that provides robust error handling,
logging, and maintenance features.

#### Using gate.py (Recommended)

The automation script provides a complete automated workflow for both Linux and Windows:

```bash
# Run the automation script manually
./bin/gate.py          # Linux/Unix
python bin\gate.py     # Windows

# Enable debug mode for troubleshooting
./bin/gate.py --debug          # Linux/Unix
python bin\gate.py --debug     # Windows

# Perform a dry run (test without executing commands)
./bin/gate.py --dry-run        # Linux/Unix
python bin\gate.py --dry-run   # Windows
```

**Features of gate.py:**
- **Lock file management**: Prevents overlapping executions
- **Timeout handling**: Prevents runaway processes
- **Pre-flight checks**: Validates configuration and directories
- **Integrated workflow**: Import → Export → Process held → Pack → Binkd connection → Areafix
- **Statistics tracking**: Logs packet counts to `data/logs/gate_stats.log`
- **Disk space monitoring**: Warns when space is low
- **Log rotation**: Automatically rotates large log files with gzip compression
- **Log cleanup**: Removes old compressed logs based on retention period (configurable via
-                  `log_retention_days`)
- **Maintenance scheduling**: Runs maintenance tasks at 2 AM
- **Error recovery**: Continues operation even if individual steps fail

**Set up automated operation (recommended):**

Linux (cron):
```bash
# Every 30 minutes - full PyGate cycle with gate.py
*/30 * * * * /opt/pygate/bin/gate.py

# Or every 15 minutes for higher frequency
*/15 * * * * /opt/pygate/bin/gate.py
```

Windows (Task Scheduler):
- Create a new task
- Program: `C:\Python3\python.exe` (or your Python path)
- Arguments: `C:\pygate\bin\gate.py`
- Set to repeat every 30 minutes (or 15 minutes for higher frequency)
- Run whether user is logged on or not

The automation script logs to `data/logs/gate.log` and maintains statistics in `data/logs/gate_stats.log`.

#### Manual Cron Setup (Alternative)

If you prefer manual control, set up individual cron jobs:

```bash
# Every 15 minutes - import and export
*/15 * * * * cd /opt/pygate && ./pygate.py --import
*/15 * * * * cd /opt/pygate && ./pygate.py --export

# Daily maintenance
0 2 * * * cd /opt/pygate && ./pygate.py --maintenance
```

### Log Management

PyGate provides automated log management to prevent unbounded log growth:

#### Automatic Log Rotation

When log files exceed 10MB, they are automatically:
1. **Compressed** using gzip compression
2. **Timestamped** with format: `logfile.DDMMMYY.gz` (PyGate date format)
3. **Archived** in the same log directory
4. **Replaced** with a fresh log file

The following logs are automatically rotated:
- `pygate.log` - PyGate main operations log
- `gate.log` - gate.py automation script log
- `binkd.log` - Binkd mailer log

Example rotated logs:
```
data/logs/pygate.log.12Oct25.gz
data/logs/gate.log.12Oct25.gz
data/logs/binkd.log.12Oct25.gz
```

#### Automatic Log Cleanup

During the 2 AM maintenance cycle, old compressed logs are automatically removed based on the configured
retention period.

**Configuration:**

In `pygate.cfg`:
```ini
[Files]
# Log retention (days to keep compressed log files)
# Default: 30 days
log_retention_days = 30
```

**Examples:**

```ini
# Keep logs for 15 days (saves disk space)
log_retention_days = 15

# Keep logs for 90 days (compliance requirements)
log_retention_days = 90

# Keep logs for 7 days (minimal retention)
log_retention_days = 7
```

**What gets cleaned:**
- Compressed log files (`.log.*.gz`) older than retention period
- Cleanup runs during the 2 AM maintenance window
- Active log files are never deleted, only rotated when they exceed 10MB

**Benefits:**
- **Automatic**: No manual intervention required
- **Configurable**: Adjust retention to your needs
- **Space efficient**: gzip compression typically achieves 90%+ compression
- **Safe**: Only removes compressed archives, never active logs

## Message Hold System

The hold system allows manual review of messages before they are gated, providing control over message flow.
When areas are remapped to fidonet echomail areas. This is mainly to protect fidonet from usenet spam.

### Configuration

Enable holding in `pygate.cfg`:

```ini
[Arearemap]
Hold = yes
notify_sysop = yes
```

### How It Works

1. **Message Evaluation**: Each message is checked against area mappings
2. **Hold Decision**: Messages in mapped areas are held for review
3. **Notification**: Netmail sent to sysop (once per hour maximum)
4. **Review Process**: Admin reviews messages via admin panel
5. **Action**: Messages are approved, rejected, or archived

### Notification System

When messages are held:
- **Netmail** sent to sysop at `linked_address`
- **Rate Limited**: Maximum one notification per hour
- **Comprehensive**: Lists all areas with pending messages
- **Tracking**: State saved in `hold/notifications.json`

Example netmail:
```
From: PyGate
To: Stephen Walsh
Subject: PyGate: Messages held for review (2 areas)

You have 3 message(s) held for review in areas MYSTIC and LINUX.

These messages require manual approval before being gated between
NNTP and FidoNet.

To review and approve/reject these messages, use the PyGate admin
panel or command line tools.
```

### Administrative Interface

Use the command-line admin panel for comprehensive PyGate management:

```bash
python3 admin_panel.py
```

This provides an interactive command-line interface for:
- **Message Hold Management**: Review, approve, and reject held messages
- **Spam Filter Management**: Add/remove/edit filter patterns and view statistics
- **Newsrc File Management**: Sort, view, backup, restore, add/delete newsgroups
- **System Monitoring**: View logs, check gateway status, and system information

## Admin Panel Features

The PyGate admin panel provides six main functions accessible through a simple menu system:

### 1. Filter Manager
- **Add/Edit/Delete** spam filter patterns
- **Test patterns** against sample text
- **Import/Export** filter configurations
- **Built-in pattern library** with common spam patterns

### 2. Log File Viewer
- **Real-time log monitoring** with live updates
- **Search functionality** to find specific events
- **Paged viewing** for large log files
- **Error highlighting** and filtering options

### 3. Gateway Status & System Information
- **Connection testing** for NNTP and FidoNet
- **Current processing status** (when run on the news server)
- **Performance metrics**
- **PyGate version** and build information
- **System resources** and disk usage
- **Python environment** details
- **Dependency versions**

### 4. Configuration Check
- **Comprehensive validation** of pygate.cfg settings
- **Detailed pass/fail report** showing all validation checks
- **Binkd verification** - checks for binkd.config and binkd binary
- **Directory validation** - verifies all required directories exist
- **NNTP connection test** - confirms server connectivity
- **Fast execution** - direct validation without subprocess overhead

### 5. Hold Message Manager
- **Review pending messages** held for approval
- **Approve/reject messages** with notes
- **Bulk operations** for multiple messages
- **Search and filter** held messages
- **View message content** and headers

### 6. Newsgroup Manager

Complete newsrc file management with advanced features:

#### File Operations
- **Sort newsgroups** alphabetically with automatic backup
- **View file contents** with syntax highlighting and paging
- **Create timestamped backups** for safety
- **Restore from backup** with file selection

#### Newsgroup Management
- **Add newsgroups**: Interactive guided setup with validation
  - Newsgroup name validation (format checking)
  - Water mark configuration (low/high article numbers, default high water mark: 1)
  - Duplicate prevention
  - **Automatic NNTP server integration** via ctlinnd
  - **Delete newsgroups**: Multiple selection methods
  - Select by number, exact name, or partial match
  - **Automatic NNTP server cleanup** via ctlinnd
  - Confirmation required for safety

#### Advanced Viewing Features
- **Paged navigation**: 40 lines per page with smart controls
- **Search functionality**: Find specific newsgroups with highlighting
- **Visual indicators**: `>` markers show search matches
- **Navigation options**:
  - `N/P`: Next/Previous page
  - `F/L`: First/Last page
  - `G`: Go to specific page number
  - `S`: Search for newsgroup names
  - `C`: Clear search highlighting
  - `Q`: Return to menu

#### NNTP Server Integration
The newsrc manager can synchronize with your NNTP server (in full gateway mode):
- **Adding newsgroups**: Executes `ctlinnd newgroup <newsgroup>` (full gateway mode)
- **Removing newsgroups**: Executes `ctlinnd rmgroup <newsgroup>` (full gateway mode)
- **Client mode**: Only updates newsrc file, skips server modifications
- **Error handling**: Offers rollback if server operations fail (full gateway mode)
- **SSH support**: Works with both local and remote ctlinnd (full gateway mode)
- **Status reporting**: Clear feedback on both file and server operations

When running in client-only mode (`client_mode = true`), the admin panel will display:
```
ℹ️  Running in client mode - newsrc updated, server not modified
✅ Newsgroup 'alt.test.new' added to newsrc
```

### Example Admin Panel Session

```bash
$ python3 admin_panel.py

PyGate Admin Panel
==================

1. Filter Manager
2. Log File Viewer
3. Gateway Status & System Information
4. Configuration Check
5. Hold Message Manager
6. Newsgroup Manager
Q. Exit

Select option (1-6, Q): 6

Newsgroup Manager
=================

📄 Current newsrc file: newsrc
📊 Newsgroup entries: 125

1. Sort newsrc file alphabetically
2. View newsrc file
3. Backup newsrc file
4. Restore from backup
5. Add newsgroup entry
6. Delete newsgroup entry
Q. Back to main menu

Select option (1-6, Q): 5

Add Newsgroup Entry
===================

Newsgroup name: alt.test.new
Low water mark (default: 1): 1
High water mark (default: 1): 100

New entry to add:
  alt.test.new: 1-1

Add this entry? (y/N): y

✅ Backup created: newsrc.bak
✅ Successfully added newsgroup 'alt.test.new' to newsrc file
📄 Updated file: newsrc
📊 Total entries: 126

Adding newsgroup to NNTP server...
✅ Successfully added newsgroup 'alt.test.new' to NNTP server
📝 Server response: Created alt.test.new
```

## Spam Filtering

PyGate includes a sophisticated spam filtering system with both built-in and configurable filters.

### Built-in Filters

Seven built-in spam patterns are automatically applied:
1. **Cross-posting limits** (configurable)
2. **Common spam subjects**
3. **Suspicious URLs**
4. **Excessive capitals**
5. **Common spam phrases**
6. **Binary/encoding patterns**
7. **Suspicious headers**

### Custom Filter Patterns

Edit `config/filter.cfg` to add custom regex patterns:

```
# Comments start with #
# Each line is a regex pattern

# Block spam subjects
^Subject:(?i).*\bfree\s+(money|cash|prize|gift)\b

# Block drug-related content
^Subject:(?i).*\b(buy|order|sell|purchase)\s+(dmt|lsd|marijuana)\b

# Block excessive punctuation
^Subject:.*[!]{3,}

# Block common spam phrases
(?i)\b(make money|work from home|click here)\b
```

### Filter Examples and Explanations

#### Example 1: Free Money Spam
```regex
^Subject:(?i).*\bfree\s+(money|cash|prize|gift)\b
```

**Pattern breakdown:**
- `^Subject:` - Matches lines starting with "Subject:" (email header)
- `(?i)` - Case-insensitive flag (matches FREE, Free, free, etc.)
- `.*` - Matches any characters (rest of subject line)
- `\b` - Word boundary (ensures "free" is complete word)
- `free` - Matches literal word "free"
- `\s+` - Matches one or more whitespace characters
- `(money|cash|prize|gift)` - Matches any of these words
- `\b` - Another word boundary

**What it catches:**
- ✅ "Free money online!"
- ✅ "Get FREE CASH now"
- ✅ "Win free prize today"
- ✅ "Free gift with purchase"

**What it WON'T catch:**
- ❌ "Freedom of speech" (no space + target word)
- ❌ "Sugar-free diet" (free not followed by target words)
- ❌ "Free software" (software not in target word list)

#### Example 2: Drug Sales
```regex
^Subject:(?i).*\b(buy|order|sell|purchase)\s+(dmt|lsd|psilocybin|mushroom|marijuana|cannabis|hemp)\b
```

**Pattern requires BOTH groups:**
1. First group: `(buy|order|sell|purchase)` - action words
2. Whitespace: `\s+`
3. Second group: `(dmt|lsd|psilocybin|mushroom|marijuana|cannabis|hemp)` - substance words

**Examples:**
- ✅ "Buy hemp" - matches (buy + space + hemp)
- ✅ "Order cannabis" - matches (order + space + cannabis)
- ❌ "Buy groceries" - first group matches, "groceries" not in second
- ❌ "Hemp products" - second group matches, no action word

### Testing Filters

Test your filter patterns:

```bash
# Check filter syntax
./pygate.py --check

# View filter statistics in logs
tail -f logs/pygate.log | grep -i filter
```

### Filter Performance

- Filters are compiled once at startup for efficiency
- Patterns are applied to headers and message body
- Failed messages are logged with filter details
- Statistics tracked: filtered vs. passed messages in logfile

## Areafix Wildcard Protection

PyGate includes built-in protection against wildcard subscription attempts that could subscribe users
to thousands of newsgroups.

### What It Protects Against

With 30,000+ newsgroups available, a wildcard `*` subscription would:
- Subscribe the user to ALL newsgroups
- Overwhelm their system with massive traffic
- Consume excessive bandwidth and disk space
- Create processing delays for everyone

### How It Works

The areafix module automatically blocks:
1. **Wildcard subscriptions**: `*` or `+*` in areafix requests
2. **Excessive subscriptions**: More than 100 areas in a single request (configurable)

When blocked, the user receives a helpful rejection message explaining what happened and how to
correctly subscribe.

### Configuration

Add to `config/pygate.cfg`:

```ini
[Areafix]
# Maximum areas allowed in a single areafix request
# Default: 100 if not specified
max_areas_per_request = 100

# Existing areafix settings
areafix_password = yourpassword
```

### Example: Blocked Request

**User sends:**
```
TO: AREAFIX
SUBJECT: password

*
```

**User receives:**
```
REQUEST BLOCKED

Wildcard subscription '*' is not permitted. Use QUERY to search for specific areas.

WHAT TO DO INSTEAD:
  1. Use 'QUERY <pattern>' to search for areas
     Example: QUERY comp.*
     Example: QUERY aus.*

  2. Subscribe to specific areas
     Example: +comp.lang.python
     Example: +aus.cars

  3. Send 'HELP' for more information

Your request was automatically blocked for security reasons.
```

### Example: Allowed Request

**User sends:**
```
TO: AREAFIX
SUBJECT: password

+comp.lang.python
+aus.cars
QUERY comp.*
```

**Result:** All commands processed normally.

### Logging

Blocked requests are logged for admin review:

```
2025-10-05 14:32:15 - PyGate - WARNING - BLOCKED areafix from Fred Basit: Wildcard subscription '*' is
not permitted.
```

### Customization

#### Change Maximum Areas Limit

In `config/pygate.cfg`:
```ini
[Areafix]
max_areas_per_request = 50   # More restrictive
# or
max_areas_per_request = 200  # More permissive
```

### Benefits

- **Automatic Protection**: No manual configuration required, works out of the box
- **User Education**: Rejection messages explain why blocked and provide alternatives
- **System Protection**: Prevents accidental or malicious mass subscriptions
- **Configurable**: Adjust limits to your needs
- **Full Logging**: All blocks recorded for admin review

## Troubleshooting

### Common Issues

#### Connection Problems

**NNTP Connection Failed:**
```bash
# Test NNTP connection
./pygate.py --check
```

Check:
- NNTP server hostname/IP
- Port number (usually 119 or 563 for SSL)
- Username/password
- Firewall settings
- Network connectivity

**FidoNet Packet Issues:**
```bash
# Check packet directory permissions
ls -la data/inbound/ data/outbound/

# Verify binkd configuration
cat config/binkd.config
```

#### Message Flow Issues

**Messages Not Gating:**
1. Check area mappings in config/newsrc
2. Verify spam filter isn't blocking
3. Check message hold system
4. Review log files for errors

**Duplicate Messages:**
- Check article number tracking in newsrc
- Verify message-ID handling
- Check for timestamp issues

#### Hold System Issues

**Notifications Not Sending:**
- Verify `notify_sysop = yes` in config
- Check FidoNet addresses are correct
- Ensure notification rate limiting (1 hour)
- Check data/hold/notifications.json

**Messages Stuck in Hold:**
- Use admin panel to review/approve
- Check direction field in JSON files
- Verify date parsing in held messages

### Log Analysis

Monitor operations via log files:

```bash
# Real-time monitoring of PyGate operations
tail -f data/logs/pygate.log

# Monitor gate.py automation script
tail -f data/logs/gate.log

# View statistics from gate.py
tail -f data/logs/gate_stats.log

# View compressed archived logs
zcat data/logs/pygate.log.12Oct25.gz | less
zgrep -i error data/logs/pygate.log.*.gz
zgrep -i error data/logs/binkd.log.*.gz

# Error analysis
grep -i error data/logs/pygate.log
grep -i error data/logs/gate.log

# Filter statistics
grep -i filter data/logs/pygate.log

# Message counts
grep -i "exported\|gated\|filtered" data/logs/pygate.log

# Check gate.py execution history
grep "PyGate cycle completed" data/logs/gate.log
```

### Debug Mode

Enable verbose logging:

```ini
[Files]
log_level = DEBUG
```

### Recovery Procedures

**Corrupt Areas File:**
```bash
# Backup current file
cp config/newsrc config/newsrc.backup

# Reset areas (lose article tracking)
echo "# PyGate Areas - Reset" > config/newsrc

# Or restore from backup
cp config/newsrc.bak config/newsrc
```

**Stuck Messages:**
```bash
# Move problematic packets
mv data/inbound/*.pkt data/inbound/bad/

# Clear outbound
rm data/outbound/*.pkt

# Reset hold directories
rm data/hold/pending/*.json
rm data/hold/approved/*.json
```

## File Structure

```
pygate/
├── pygate.py                   # Main gateway script
├── pygate.cfg                  # Main configuration
├── admin_panel.py              # Command-line admin interface
├── README.md                   # This file your reading now
├── src/                        # Python modules
│   ├── cache/                  # Cache files
│   │   └── __pycache__/        # Python bytecode cache
│   ├── gateway.py              # Core gateway module
│   ├── config_validator.py     # Configuration validation module
│   ├── nntp_module.py          # NNTP handling
│   ├── fidonet_module.py       # FidoNet packet processing
│   ├── hold_module.py          # Message hold system
│   ├── spam_filter.py          # Spam filtering
│   ├── areafix_module.py       # Areafix processing
│   ├── filter_manager.py       # Filter management
│   └── nntp_client.py          # NNTP client module
├── config/                     # Configuration files
│   ├── newsrc                  # Areas configuration
│   ├── filter.cfg              # Spam filter patterns
│   ├── binkd.config            # Binkd mailer configuration
│   ├── newsgroups              # Newsgroups list
│   └── areafix.hlp             # Areafix help file
├── bin/                        # Binaries and scripts
│   ├── binkd                   # Binkd mailer binary (Linux)
│   ├── binkdwin.exe            # Binkd mailer binary (Windows)
│   └── gate.py                 # Automated PyGate execution script (cross-platform)
└── data/                       # Runtime data
    ├── logs/                   # Log files
    │   ├── pygate.log          # PyGate operation logs
    │   ├── gate.log            # gate.py automation logs
    │   ├── binkd.log           # Binkd mailer logs
    │   └── gate_stats.log      # Statistics from gate.py
    ├── inbound/                # Incoming FidoNet packets
    │   ├── processed/          # Processed packets
    │   └── bad/                # Failed packets
    ├── outbound/               # Outgoing FidoNet packets
    ├── in/                     # Binkd incoming temp
    ├── out/                    # Binkd outgoing temp
    ├── temp/                   # Temporary files
    ├── secure/                 # Secure directory
    └── hold/                   # Message hold system
        ├── pending/            # Messages awaiting review
        ├── approved/           # Approved messages
        ├── rejected/           # Rejected messages
        ├── backup/             # Backup of held messages after releasing
        └── notifications.json  # Notification tracking
```

## Examples

### Example 1: Basic Setup

```bash
# 1. Configure PyGate
vim config/pygate.cfg

# 2. Set up initial areas
echo "comp.lang.python: 0-0" > config/newsrc
echo "alt.bbs.mystic: 0-0" >> config/newsrc

# 3. Test configuration
./pygate.py --check

# 4. Initial import/export (manual)
./pygate.py --import
./pygate.py --export

# OR use the automation script (recommended)
./bin/gate.py               # Linux
python bin\gate.py          # Windows

# 5. Set up automated operation
# Linux (cron):
crontab -e
# Add: */30 * * * * /opt/pygate/bin/gate.py

# Windows (Task Scheduler):
# Create task to run: python C:\pygate\bin\gate.py every 30 minutes
```

### Example 2: Adding New Areas

Using the admin panel (recommended):
```bash
# 1. Use admin panel
python3 admin_panel.py
# Select 6: Newsgroup Manager
# Select 5: Add newsgroup entry
# Enter: comp.sys.amiga
# In full gateway mode: Automatically creates newsgroup with ctlinnd
# In client mode: Only updates newsrc (ensure newsgroup exists on server)

# 2. Add area mapping (if needed)
# Edit config/pygate.cfg and add to [Arearemap] section:
# AMIGA = comp.sys.amiga

# 3. Test new area
./pygate.py --export
```

Manual method (full gateway mode):
```bash
# 1. Add to newsrc manually
echo "comp.sys.amiga: 0-0" >> config/newsrc

# 2. Add to NNTP server
ctlinnd newgroup comp.sys.amiga

# 3. Sort newsrc file using admin panel
python3 admin_panel.py  # Option 6 → Option 1

# 4. Test new area
./pygate.py --export
```

Manual method (client-only mode):
```bash
# 1. Ensure newsgroup exists on remote NNTP server first

# 2. Add to newsrc manually
echo "comp.sys.amiga: 0-0" >> config/newsrc

# 3. Sort newsrc file using admin panel
python3 admin_panel.py  # Option 6 → Option 1

# 4. Test new area
./pygate.py --export
```

### Example 3: Filter Testing

```bash
# 1. Add test filter
echo "^Subject:.*TEST.*" >> config/filter.cfg

# 2. Check filter syntax
./pygate.py --check

# 3. Monitor filtering
tail -f logs/pygate.log | grep -i filter

# 4. Test with real messages
./pygate.py --export
```

### Example 4: Newsgroup Management with Admin Panel

```bash
# 1. Launch admin panel
python3 admin_panel.py

# 2. Select Newsgroup Manager (option 6)
# Menu shows current file status:
# 📄 Current newsrc file: config/newsrc
# 📊 Newsgroup entries: 125

# 3. View newsrc with paging and search
# Select option 2: View newsrc file
# Navigation example:
Navigation: S                    # Search
Search for: python              # Find python-related groups
# Shows: 🔍 Searching for: 'python' (> marks matches)
#   43: > comp.lang.python      0-2341
Navigation: N                    # Next page (search persists)
Navigation: C                    # Clear search
Navigation: G                    # Go to specific page
Go to page (1-15): 8
Navigation: Q                    # Back to menu

# 4. Add new newsgroup with server integration
# Select option 5: Add newsgroup entry
Newsgroup name: alt.test.new
Low water mark: 0
High water mark: 0
# Automatically runs ctlinnd newgroup

# 5. Sort and backup
# Select option 1: Sort newsrc file alphabetically
# Automatically creates backup before sorting
```

### Example 5: Hold System Workflow

```bash
# 1. Enable holding
# Edit config/pygate.cfg: Hold = yes, notify_sysop = yes

# 2. Import messages (some may be held)
./pygate.py --import

# 3. Check for notifications
tail data/logs/pygate.log | grep -i netmail

# 4. Review held messages using admin panel
python3 admin_panel.py
# Select 5: Hold Message Manager

# 5. Process approved messages
./pygate.py --process-held
```

### Example 6: Monitoring with Automation Script

```bash
# 1. Run automation script manually with debug mode
./bin/gate.py --debug        # Linux
python bin\gate.py --debug   # Windows

# 2. Monitor automation logs in real-time
tail -f data/logs/gate.log

# 3. Check statistics
tail -20 data/logs/gate_stats.log

# 4. View recent execution summary
grep "PyGate cycle completed" data/logs/gate.log | tail -10

# 5. Check for errors in automation
grep -i "error\|warning\|failed" data/logs/gate.log

# 6. Verify cron is running (Linux)
grep "gate.py" /var/log/syslog  # or check your system's cron log
```

---

**Support:** For issues or questions, check log files first, then review this documentation.
The PyGate system provides detailed logging to help diagnose problems.

**License:** Based on SoupGate by Tom Torfs. Created and enhanced by Stephen Walsh for modern Python
and FidoNet standards.

