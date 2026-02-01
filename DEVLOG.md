# Pygate Development Log
# Version prio to 1.5.7 did'nt have a devlog
#

PyGate - Python FidoNet-NNTP Gateway

PyGate is a Python-based gateway system that bridges FidoNet echomail and NNTP newsgroups, allowing
seamless message exchange between the two networks. PyGate is designed to run on the NNTP news server,
but can be run on a different computer as a client only.

**Last Updated:** February 1, 2026
**Language:** Python 3.7+


### Version 1.5.10 (February 1, 2026)

#### Article Fetch Error Recovery
Fixed issue where a timeout fetching one article would cause all subsequent articles
and newsgroups to fail with "cannot read from timed out object".

Changes in `nntp_module.py` `fetch_messages()`:
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

