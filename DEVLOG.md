# Pygate Development Log
# Version prio to 1.5.6 did'nt have a devlog
#

PyGate - Python FidoNet-NNTP Gateway

PyGate is a Python-based gateway system that bridges FidoNet echomail and NNTP newsgroups, allowing
seamless message exchange between the two networks. PyGate is designed to run on the NNTP news server,
but can be run on a different computer as a client only.

**Last Updated:** February 3, 2026
**Language:** Python 3.7+


### Version 1.5.11 (February 3, 2026)

#### Admin Panel - Newsgroup Manager Enhancements

**Option 8: Fetch newsgroups from server**
- Connects to NNTP server and retrieves full newsgroup list
- Options to view (paged), save to file, or both
- Paged viewer with search, navigation, and match highlighting
- Saves with timestamp header and creates backup if file exists

**Option 9: Mark groups read**
- Mark ALL groups read to a specified article number
- Mark specific group read with paged group selection
- Accepts input as "12345" (converts to "1-12345") or full range
- Creates backup before modifying newsrc file
- Paged group selector with search and navigation


### Version 1.5.10 (February 1, 2026)

#### Article Fetch Error Recovery
Fixed issue where a timeout fetching one article would cause all subsequent articles
and newsgroups to fail with "cannot read from timed out object".

- **Detailed error logging**: Now logs error type (timeout, connection error, etc.) with newsgroup context
- **Reconnection logic**: After 3 consecutive connection errors, attempts to disconnect/reconnect
- **Always update high water mark**: Previously only updated when messages were fetched successfully.
  Now always updates to `end_article` to skip problematic articles on retry
- **Failed article tracking**: Logs which article numbers failed for diagnostics

Example log output:
```
ERROR - Timeout fetching article 1655389 from alt.usage.english: timed out
WARNING - Multiple connection errors, attempting reconnect to alt.usage.english
INFO - Reconnected successfully, continuing fetch from article 1655390
WARNING - Failed to fetch 1 article(s) from alt.usage.english: [1655389]
```


### Version 1.5.9 (January 31, 2026)

#### IPv6 Message-ID Fix
Fixed INN rejection of Message-IDs containing IPv6 addresses. When a FidoNet MSGID
contains an IPv6 address (e.g., `<cdp8888@2001:2061:2098:c800:c8d0:356e:d91e:e642>`),
the colons would cause NNTP servers to fail with "Can't parse Message-ID header field body".

Changes in `nntp_module.py`:
- `convert_fido_msgid()` now detects IPv6 addresses in the domain part
- IPv6 colons are replaced with hyphens for RFC compliance
- Example: `2001:2061:2098:c800:...` becomes `2001-2061-2098-c800-...`

Changes in `gateway.py`:
- `generate_fido_msgid()` now explicitly rejects IPv6 addresses from `socket.getfqdn()`
- Falls back to configured domain when IPv6 is detected


### Version 1.5.8 (January 30, 2026)

From conf/filter.cfg:

#==============================================================================
# FIDONET ORIGIN FILTERS
# Block messages from specific FidoNet systems
#==============================================================================

^Origin:(?i).*\(1:135/250\)

The pattern explained:
  - ^Origin: - matches the Origin header type
  - (?i) - case insensitive
  - .* - match anything
  - \(1:135/250\) - match the address in parentheses (escaped because parentheses are regex special chars)

This will block messages in both directions (FidoNet->NNTP and NNTP->FidoNet) from that system.


### Version 1.5.7 (January 29, 2026)

When converting NNTP to FidoNet, PyGate now checks for the X-FTN-MSGID header first. If present (indicating the
message originated from FidoNet), it uses the original MSGID instead of generating a new one. This allows FidoNet
duplicate detection to work correctly and prevents message loops.

The flow is now:
1. FidoNet -> NNTP: MSGID: 2:221/1 697c6658 -> X-FTN-MSGID: 2:221/1 697c6658
2. NNTP -> FidoNet: X-FTN-MSGID: 2:221/1 697c6658 -> MSGID: 2:221/1 697c6658 (same!)

Duplicate detection will now recognize it as the same message.


### Version 1.5.6 (January 28, 2026)

#### Version String Centralization
Moved version string from config file to main `pygate.py` module. The version in
`pygate.py` now overrides any setting in the config file.

Changes in `pygate.py`:
- Added `__version__ = '1.5'` after imports

Changes in `src/__init__.py`:
- Updated `get_version()` to import from pygate module

#### Multi-Message FidoNet Packet Fix
Fixed issue where only the first message in a FidoNet packet was gated to NNTP.
The `read_line()` method in `fidonet_module.py` was returning empty string for both
null terminators (end of message) and actual empty lines, causing the parser to
incorrectly detect end-of-message when the next message's version field wasn't null.

Changes in `fidonet_module.py`:
- `read_line()` now returns `False` sentinel for null terminator (end of message)
- Returns empty string `''` for actual empty lines
- Body reading loops updated to check `if line is False` for message boundary

#### Point Address Support (4D Addressing)
Added support for FidoNet point addresses (e.g., `2:221/1.100` instead of just `2:221/1`).

#### CHRS Kludge / Charset Fix for NNTP
Fixed missing charset in NNTP headers when gating from FidoNet. The CHRS kludge
was being read but not passed through to the NNTP article builder.

