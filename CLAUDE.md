# PyGate

Python FidoNet-NNTP gateway. Bridges FidoNet echomail and NNTP newsgroups bidirectionally.
Based on SoupGate by Tom Torfs. Currently v1.5.19.

## Project Structure

### Core
- `pygate.py` (160 lines) - Entry point, CLI argument parsing, operation mode dispatch
- `src/gateway.py` (1148 lines) - `Gateway` class: orchestrates import/export/pack/maintenance operations
- `src/fidonet_module.py` (934 lines) - FidoNet packet reading/writing, MSGID handling, 4D addressing
- `src/nntp_module.py` (758 lines) - NNTP article conversion, Message-ID generation, header mapping
- `src/nntp_client.py` (452 lines) - NNTP server connection, article fetch/post, newsgroup management
- `src/areafix_module.py` (1031 lines) - Areafix request processing, area subscribe/unsubscribe
- `src/filter_manager.py` (1047 lines) - Area mapping, newsrc management, newsgroup filtering
- `src/spam_filter.py` (427 lines) - Regex-based spam/origin filtering
- `src/hold_module.py` (445 lines) - Message hold queue for admin review
- `src/config_validator.py` (146 lines) - Configuration validation and checks

### Admin & Tools
- `admin_panel.py` (2438 lines) - Interactive admin panel (newsgroup manager, held message review, config)
- `bin/gate.py` - Utility script

### Config
- `pygate-sample.cfg` - Sample config (INI format via configparser)
- `config/filter.cfg` - Spam/origin filter patterns (regex)
- `config/newsrc` - Newsgroup subscription state (high water marks)
- `config/newsgroups` - Newsgroup list
- `config/areafix.hlp` - Areafix help text
- `config/binkd.config` - Sample binkd config for packet transport

### Data Directories
- `data/inbound/` - Incoming FidoNet packets (.pkt)
- `data/outbound/` - Outgoing FidoNet packets for binkd
- `data/hold/` - Messages held for admin review
- `data/temp/` - Temporary files during processing
- `data/logs/` - Log files

## Operation Modes

```bash
pygate.py --import        # FidoNet packets -> NNTP articles
pygate.py --export        # NNTP articles -> FidoNet packets
pygate.py --pack          # Pack pending outbound messages
pygate.py --check         # Validate config and test NNTP connection
pygate.py --areafix       # Process areafix requests
pygate.py --maintenance   # Maintenance tasks
pygate.py --process-held  # Process approved held messages
```

## Key Concepts

- **Bidirectional gating**: FidoNet echomail <-> NNTP newsgroups
- **Area mapping**: FidoNet area names mapped to newsgroup names via `[Arearemap]` config section
- **MSGID preservation**: X-FTN-MSGID header preserves original FidoNet MSGIDs through NNTP round-trips to prevent duplicate detection failures
- **Packet format**: Standard FidoNet Type-2+ packets with packet password authentication
- **Client mode**: Can run as NNTP client only (no server management) or full gateway mode
- **Areafix**: Automated area subscription management via netmail
- **Spam filtering**: Regex patterns in `config/filter.cfg`, origin-based blocking, cross-post limits
- **Hold queue**: Messages can be held for admin review before gating
- **High water marks**: Tracks last-fetched article number per newsgroup in newsrc file

## Config Format

INI-style via `configparser`. Sections: `[Gateway]`, `[Mapping]`, `[FidoNet]`, `[Areafix]`, `[Arearemap]`, `[NNTP]`, `[SSH]`, `[Files]`, `[SpamFilter]`.

See `pygate-sample.cfg` for all options with comments.

## Dependencies

- Python 3.7+
- Standard library only (no pip packages for core gateway)
- Optional: SSH support for remote ctlinnd execution

## Notable Fixes (Recent)

- v1.5.19: NNTP->FidoNet X-Comment-To honoured when present - to_name prefers the article's X-Comment-To header, falling back to area default_to (or "All") when the header is missing/empty. Completes the round-trip that v1.5.15 only did one way.
- v1.5.18: [Arearemap] AddSeenBy is now per-area - append `| ADDR[, ...]` to each area mapping line. Removes the v1.5.17 global `AddSeenBy = ADDR` keyword (breaking config change; migrate by appending `| ADDR` to each affected area line).
- v1.5.17: INTL kludge for netmail hold notifications - write_message() now treats area='NETMAIL' as netmail (skips AREA: body line, emits INTL/FMPT/TOPT kludges per FTS-0001)
- v1.5.15: TK-contributed merge - X-Comment-To header round-trip (FidoNet->NNTP only; NNTP->FidoNet still addresses to area default_to "All"), NOTE/NEWSREADER kludges from User-Agent/X-Newsreader, X-Organization, Content-Transfer-Encoding: 8bit; tear line keeps PyGate identifier with version sourced from pygate.__version__
- v1.5.14: From-header bare-name fix in extract_name_from_email (handles display-name-only From: headers so ^From: filter patterns match)
- v1.5.13: FTS-0009 compliant MSGID for NNTP-originated messages (uses gateway_address + CRC32 of NNTP Message-ID; RFC-Message-ID kludge preserves NNTP origin)
- v1.5.12: Double dot-stuffing fix - removed pre-stuffing from build_nntp_article (RFC 3977 dot-stuffing is wire-level, belongs only in post())
- v1.5.11: Admin panel newsgroup manager enhancements
- v1.5.10: NNTP article fetch timeout recovery with reconnection logic
- v1.5.9: IPv6 Message-ID fix (colons replaced with hyphens for RFC compliance)
- v1.5.7: X-FTN-MSGID round-trip preservation
- v1.5.6: Multi-message packet parsing fix (null terminator vs empty line)

## CHARACTER RESTRICTIONS

Use plain ASCII only in ALL code, config files, and documentation.
Do NOT use any non-ASCII Unicode characters. This includes emoji, Unicode
symbols, and typographic characters that look harmless but are not ASCII.

Use plain ASCII alternatives:
- Dashes: use hyphen-minus ( - ) not em dash
- Arrows: use -> or <- not Unicode arrows
- Tick/cross: write (ok) or (fail) or [x] in plain text
- No emoji of any kind
