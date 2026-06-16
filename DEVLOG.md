# Pygate Development Log
#
# Versions prio to 1.5.6 did'nt have a devlog
#

PyGate - Python FidoNet-NNTP Gateway

PyGate is a Python-based gateway system that bridges FidoNet echomail and NNTP newsgroups, allowing
seamless message exchange between the two networks. PyGate is designed to run on the NNTP news server,
but can be run on a different computer as a client only.

**Last Updated:** June 16, 2026
**Language:** Python 3.7+


### Version 1.5.17 (June 16, 2026)

#### INTL Kludge for Netmail Hold Notifications

Fixed missing `\x01INTL` kludge (and a spurious `AREA:NETMAIL` body line)
on the hold-queue notification netmail produced by `src/hold_module.py`.
hpt reported the symptom as:

```
Mail without INTL-Kludge. Assuming 3:633/10.0 -> 3:633/280.0
```

Root cause: `write_message()` in `src/fidonet_module.py` chose the
netmail vs. echomail code path with `if not message.get('area')`. The
hold notification passes `area='NETMAIL'` (the conventional FTN tag for
the netmail area), so the message took the echomail path - emitting an
`AREA:NETMAIL` first body line and skipping the netmail-only INTL/FMPT/
TOPT kludges (FTS-0001, FSC-0039).

Fix: `write_message()` now treats the message as netmail when `area` is
empty *or* equals `NETMAIL` (case-insensitive). Areafix replies already
use `area=''` and are unaffected.


### Version 1.5.15 (May 25, 2026)

Merged a set of changes contributed by a fellow sysop (marked with `# TK`
comments in the source) that preserve FidoNet "To" and reader information across
the gateway in both directions, plus related header adjustments.

#### To/From Name Round-Trip via X-Comment-To

The FidoNet "To" name is now carried across the gateway using the `X-Comment-To`
NNTP header.

Changes in `src/nntp_module.py`:
- Inbound articles now capture `X-Comment-To` into the message `to_name`.
- `build_nntp_article()` now emits an `X-Comment-To:` header carrying the FidoNet
  recipient name.

Changes in `src/gateway.py`:
- FidoNet -> NNTP (`convert_fido_to_nntp`) now passes `to_name` through so the
  `X-Comment-To` header can be populated.

NNTP -> FidoNet direction: the contributed code set the FidoNet `to_name` from
the NNTP `X-Comment-To` header (falling back to `Unknown`). This was reverted so
`convert_nntp_to_fido` again addresses gated Usenet posts to the area
`default_to` ("All"), matching the long-standing behaviour where Usenet articles
are always addressed to "All".

#### Reader / Tosser Kludges (NOTE / NEWSREADER)

When gating NNTP -> FidoNet, the posting agent information is now preserved as
FidoNet kludge lines:
- NNTP `User-Agent` -> `\x01NOTE:` kludge
- NNTP `X-Newsreader` -> `\x01NEWSREADER:` kludge

Changes in `src/gateway.py` populate `note` (from `User-Agent`) and `newsreader`
(from `X-Newsreader`); `src/fidonet_module.py` preserves and writes both kludges.

Note: a copy/paste bug in the contributed code wrote the `newsreader` value under
a second `\x01NOTE:` label; this was corrected to `\x01NEWSREADER:` during the
merge so the two fields produce distinct kludges.

#### Header Adjustments (FidoNet -> NNTP)

In `build_nntp_article()` (`src/nntp_module.py`):
- Added `Content-Transfer-Encoding: 8bit`.
- The FidoNet origin line is now emitted as `X-Organization:` instead of the
  standard `Organization:` header.

In `src/fidonet_module.py`, the contributed code wrote the tear line as a bare
`---`. This was reverted to keep the PyGate software identifier (e.g.
`--- PyGate Linux v1.5.15`). `generate_tearline()` now sources the version from
`pygate.__version__` first, falling back to the `[Gateway] version` config value.


### Version 1.5.14 (April 13, 2026)

#### Spam Filter: From Header Bare-Name Fix

Fixed `extract_name_from_email()` in `src/nntp_module.py` so that `From:` headers
containing only a display name with no email address are handled correctly.

Previously, `parseaddr()` on a bare name like `From: forecast` returned an empty
`name` and set `email_addr` to the bare string. The fallback then returned
`'Unknown'` (because there was no `@`), so `from_name` was always `'Unknown'` for
these senders. Any `^From:` filter pattern targeting the actual name never matched.

Now the fallback returns the bare string as-is when no `@` is present:
```python
# Before
decoded_name = email_addr.split('@')[0] if '@' in email_addr else 'Unknown'
# After
decoded_name = email_addr.split('@')[0] if '@' in email_addr else (email_addr or 'Unknown')
```

#### Spam Filter: TraderSuccess.com Stock Trading Campaign

Added a dedicated filter section in `config/filter.cfg` for a recurring stock
trading spam campaign that posts under `From: forecast` via UsenetExpress. The
campaign rotates subject lines to evade simple filters; added patterns covering
the observed variants:

- `^Subject:(?i).*tradersuccess` — explicit site reference in subject
- `^Subject:.*【` — Unicode fullwidth bracket used in 4/5 observed messages
- `^Subject:(?i).*\bAI\s+CANNOT\b` — variant subject phrase
- `^Subject:(?i).*\bUncanny\s+Forecasts\b` — variant subject phrase

The pre-existing `^From:(?i)^forecast$` rule now works correctly following the
`extract_name_from_email` fix above.


### Version 1.5.13 (March 13, 2026)

#### FTS-0009 Compliant MSGID for NNTP-Originated Messages
Fixed `generate_fido_msgid()` in `gateway.py` to produce a valid FidoNet return
address in the MSGID of gated NNTP messages.

Previously the MSGID used the raw NNTP Message-ID as the address part, e.g.:
```
MSGID: <10ovp46$2juq8$1@dont-email.me> dd3db642
```
This is not a valid FidoNet address, so other nodes had no usable return address
and duplicate detection could not work correctly.

Now the MSGID uses the configured `gateway_address` from `[FidoNet]` as the
originating address, with a CRC32 of the NNTP Message-ID as the serial:
```
MSGID: 3:633/10 dd3db642
```
The serial remains deterministic per NNTP article (CRC32 of the message-id), or
a uuid/time-based value when no NNTP Message-ID is available.

For NNTP-originated messages, the original NNTP Message-ID is now also preserved
in a `RFC-Message-ID` kludge line so the NNTP origin remains traceable:
```
^ARFC-Message-ID: <10ovp46$2juq8$1@dont-email.me>
```
This kludge is written by `fidonet_module.py` and populated in `gateway.py` only
when the message did not originate from FidoNet (no X-FTN-MSGID header present).

Also fixed `generate_fido_reply()` which had the same problem — it was putting
the raw NNTP message-id in the REPLY address slot. It now uses the same
`gateway_address CRC32(parent_msgid)` format so the REPLY value matches what
PyGate stored as the parent's MSGID when it was originally gated.

Note: messages that originated in FidoNet (identified by the X-FTN-MSGID header)
are unaffected - their original MSGID is preserved as per the v1.5.7 fix.


### Version 1.5.12 (February 23, 2026)

#### Double Dot-Stuffing Fix (RFC 3977 Compliance)
Fixed a bug where lines starting with a dot in FidoNet messages had an extra dot
added when gated to NNTP, violating RFC 3977 s3.1.1.

Root cause: dot-stuffing was being applied twice:
1. `build_nntp_article()` in `nntp_module.py` was pre-stuffing body lines
2. `post()` in `nntp_client.py` was stuffing again at the wire level

Result: a FidoNet body line `. 1` became `... 1` on the wire. INN stripped one dot
per RFC 3977 and stored `.. 1`, so the user saw an extra leading dot on every
dot-prefixed line.

Fix: removed the dot-stuffing block from `build_nntp_article()`. Dot-stuffing is a
wire-level transport encoding and belongs only in `post()`. Article content must
contain literal dots; `post()` handles the protocol escaping.


### Version 1.5.11 (February 2, 2026)

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

