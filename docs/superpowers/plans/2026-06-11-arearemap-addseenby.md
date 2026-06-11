# [Arearemap] AddSeenBy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional `AddSeenBy` keyword to the `[Arearemap]` section of `pygate.cfg` that appends a single FidoNet address to the SEEN-BY line of NNTP -> FidoNet gated messages, but only for areas explicitly listed in `[Arearemap]`.

**Architecture:** One new helper method on the `Gateway` class resolves the configured AddSeenBy address (with caching and one-time validation warning) and the set of areas that should receive it. The existing `convert_nntp_to_fido()` calls this helper and appends the formatted address to its `seen_by` list. `get_area_name_for_newsgroup()` is updated to skip the `AddSeenBy` key while iterating `[Arearemap]` so it is never treated as a (FidoNet area -> newsgroup) mapping.

**Tech Stack:** Python 3.7+ standard library (`configparser`, `re`, `logging`). No new dependencies.

**Project context:** PyGate has no test framework (no `tests/`, no `pytest.ini`). Verification uses ad-hoc Python REPL checks (`python3 -c "..."`) against a fixture config in `/tmp/`, plus a final end-to-end sanity run.

---

## File Structure

- **Modify** `src/gateway.py` — add `get_arearemap_seenby()` and private cache builder, filter `AddSeenBy` in `get_area_name_for_newsgroup()`, append in `convert_nntp_to_fido()`.
- **Modify** `pygate-sample.cfg` — document the new keyword under `[Arearemap]`.
- **Modify** `DEVLOG.md` — add a new entry for the version bump.
- **Modify** `pygate.py` — bump `__version__` to `1.5.16`.
- **Modify** `CLAUDE.md` — bump version reference and add a Notable Fixes entry.

No new files. All changes are localised to the `Gateway` class plus config/doc updates.

---

## Task 1: Helper `get_arearemap_seenby()` on `Gateway`

**Files:**
- Modify: `src/gateway.py` (add new method + private helper near `get_area_name_for_newsgroup`, around line 598; add `import re` if not already present near top of file)

- [ ] **Step 1: Verify `re` is imported in `src/gateway.py`**

Run:
```bash
grep -n "^import re\|^from re " /home/vk3heg/claude/pygate/src/gateway.py
```

If no match, add `import re` to the existing imports block (alongside `import os`, `import logging`, etc. — keep stdlib imports grouped).

- [ ] **Step 2: Add private cache builder `_build_arearemap_seenby_cache`**

Insert this method on the `Gateway` class, immediately above `get_area_name_for_newsgroup` (currently at line 598). Use the exact code below:

```python
    # Regex matches "zone:net/node[.point][@domain]" (FidoNet 4D address).
    _ADDSEENBY_RE = re.compile(r'^\d+:\d+/\d+(\.\d+)?(@\S+)?$')

    def _build_arearemap_seenby_cache(self):
        """Resolve [Arearemap] AddSeenBy once.

        Returns (formatted_address_or_None, set_of_area_keys_lowercase).
        Logs a warning once if AddSeenBy is set but malformed.
        """
        if not self.config.has_section('Arearemap'):
            return None, set()

        addr_raw = ''
        area_keys = set()
        try:
            for key, value in self.config.items('Arearemap'):
                if key.lower() == 'addseenby':
                    addr_raw = (value or '').strip()
                else:
                    area_keys.add(key.lower())
        except Exception as e:
            self.logger.error(f"Error reading Arearemap section: {e}")
            return None, set()

        if not addr_raw:
            return None, area_keys

        if not self._ADDSEENBY_RE.match(addr_raw):
            self.logger.warning(
                f"[Arearemap] AddSeenBy value '{addr_raw}' is not a valid "
                f"FidoNet address (expected zone:net/node[.point]); "
                f"SEEN-BY will not be modified"
            )
            return None, area_keys

        formatted = self.fidonet.format_address_for_seenby(addr_raw)
        return formatted, area_keys
```

- [ ] **Step 3: Add public method `get_arearemap_seenby`**

Insert immediately after `_build_arearemap_seenby_cache`:

```python
    def get_arearemap_seenby(self, area_tag: str):
        """Return formatted SEEN-BY address to append for ``area_tag``, or None.

        Honors the optional ``AddSeenBy`` keyword in ``[Arearemap]``.
        Returns None if AddSeenBy is unset/invalid, or if ``area_tag`` is
        not listed as an area in ``[Arearemap]``.
        """
        if not hasattr(self, '_arearemap_seenby_cache'):
            self._arearemap_seenby_cache = self._build_arearemap_seenby_cache()
        formatted, area_keys = self._arearemap_seenby_cache
        if formatted and area_tag.lower() in area_keys:
            return formatted
        return None
```

- [ ] **Step 4: Verify the method works against an ad-hoc fixture config**

Write this fixture to `/tmp/pygate_addseenby_t1.cfg`:

```bash
cat > /tmp/pygate_addseenby_t1.cfg <<'EOF'
[Gateway]
version = 1.5.16
[FidoNet]
gateway_address = 3:633/10
linked_address = 3:633/1
origin_line = test
[NNTP]
server = localhost
port = 119
[Files]
areas_file = /tmp/pygate_areas_t1.cfg
[Arearemap]
AddSeenBy = 1:135/250
GENERAL = comp.misc
LINUX = comp.os.linux
[SpamFilter]
enabled = false
EOF
touch /tmp/pygate_areas_t1.cfg
```

Then exercise the helper directly:

```bash
cd /home/vk3heg/claude/pygate && python3 -c "
from src.gateway import Gateway
g = Gateway('/tmp/pygate_addseenby_t1.cfg', load_spam_filter=False)
print('GENERAL:', repr(g.get_arearemap_seenby('GENERAL')))
print('LINUX:',   repr(g.get_arearemap_seenby('LINUX')))
print('UNKNOWN:', repr(g.get_arearemap_seenby('UNKNOWN')))
"
```

Expected output:
```
GENERAL: '135/250'
LINUX: '135/250'
UNKNOWN: None
```

- [ ] **Step 5: Verify malformed AddSeenBy logs once and returns None**

```bash
sed -i 's|AddSeenBy = 1:135/250|AddSeenBy = not-an-address|' /tmp/pygate_addseenby_t1.cfg
cd /home/vk3heg/claude/pygate && python3 -c "
from src.gateway import Gateway
g = Gateway('/tmp/pygate_addseenby_t1.cfg', load_spam_filter=False)
print('GENERAL:', repr(g.get_arearemap_seenby('GENERAL')))
print('GENERAL:', repr(g.get_arearemap_seenby('GENERAL')))
" 2>&1 | grep -E "AddSeenBy|GENERAL"
```

Expected: one WARNING line about `not-an-address`, then two `GENERAL: None` lines (warning issued once because the cache is built once).

- [ ] **Step 6: Verify absent AddSeenBy returns None for everything**

```bash
sed -i '/AddSeenBy = /d' /tmp/pygate_addseenby_t1.cfg
cd /home/vk3heg/claude/pygate && python3 -c "
from src.gateway import Gateway
g = Gateway('/tmp/pygate_addseenby_t1.cfg', load_spam_filter=False)
print('GENERAL:', repr(g.get_arearemap_seenby('GENERAL')))
"
```

Expected: `GENERAL: None` and no WARNING line.

- [ ] **Step 7: Commit**

```bash
cd /home/vk3heg/claude/pygate && git add src/gateway.py && git commit -m "$(cat <<'EOF'
gateway: add get_arearemap_seenby helper for AddSeenBy support

Resolves the [Arearemap] AddSeenBy keyword once, validates the address
with a regex sanity check, caches the result, and exposes a per-area
lookup. Used by the upcoming SEEN-BY injection in convert_nntp_to_fido.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Filter `AddSeenBy` from area-name lookup

**Files:**
- Modify: `src/gateway.py:598-610` (`get_area_name_for_newsgroup`)

- [ ] **Step 1: Update the iterator to skip `AddSeenBy`**

In `get_area_name_for_newsgroup`, change the iteration body from:

```python
        if self.config.has_section('Arearemap'):
            try:
                for fido_area, mapped_newsgroup in self.config.items('Arearemap'):
                    if mapped_newsgroup == newsgroup:
                        return fido_area.upper()
            except Exception as e:
                self.logger.error(f"Error reading Arearemap section: {e}")
```

to:

```python
        if self.config.has_section('Arearemap'):
            try:
                for fido_area, mapped_newsgroup in self.config.items('Arearemap'):
                    if fido_area.lower() == 'addseenby':
                        continue
                    if mapped_newsgroup == newsgroup:
                        return fido_area.upper()
            except Exception as e:
                self.logger.error(f"Error reading Arearemap section: {e}")
```

- [ ] **Step 2: Verify the lookup still works and ignores AddSeenBy**

Re-add a valid AddSeenBy to the fixture and verify the area lookup:

```bash
cat > /tmp/pygate_addseenby_t1.cfg <<'EOF'
[Gateway]
version = 1.5.16
[FidoNet]
gateway_address = 3:633/10
linked_address = 3:633/1
origin_line = test
[NNTP]
server = localhost
port = 119
[Files]
areas_file = /tmp/pygate_areas_t1.cfg
[Arearemap]
AddSeenBy = 1:135/250
GENERAL = comp.misc
LINUX = comp.os.linux
[SpamFilter]
enabled = false
EOF

cd /home/vk3heg/claude/pygate && python3 -c "
from src.gateway import Gateway
g = Gateway('/tmp/pygate_addseenby_t1.cfg', load_spam_filter=False)
print('comp.misc       ->', g.get_area_name_for_newsgroup('comp.misc'))
print('comp.os.linux   ->', g.get_area_name_for_newsgroup('comp.os.linux'))
print('1:135/250       ->', g.get_area_name_for_newsgroup('1:135/250'))
print('comp.unrelated  ->', g.get_area_name_for_newsgroup('comp.unrelated'))
"
```

Expected output:
```
comp.misc       -> GENERAL
comp.os.linux   -> LINUX
1:135/250       -> 1:135/250
comp.unrelated  -> comp.unrelated
```

(The `1:135/250` lookup returning the input unchanged confirms the AddSeenBy key is no longer treated as a fido_area mapping; otherwise it would have returned `ADDSEENBY`.)

- [ ] **Step 3: Commit**

```bash
cd /home/vk3heg/claude/pygate && git add src/gateway.py && git commit -m "$(cat <<'EOF'
gateway: skip AddSeenBy key when scanning [Arearemap] for area name

get_area_name_for_newsgroup now ignores the AddSeenBy entry so the
configured address is never mistaken for a (fido area -> newsgroup)
mapping.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Append AddSeenBy to `seen_by` in `convert_nntp_to_fido`

**Files:**
- Modify: `src/gateway.py` (around line 788-797, the `seen_by` list literal inside `convert_nntp_to_fido`)

- [ ] **Step 1: Insert the append after the existing `seen_by`/`path` block**

Find this block in `convert_nntp_to_fido` (currently around line 788-797):

```python
            # SEEN-BY and PATH per FTS-0004.001 EchoMail specification
            # SEEN-BY must include both source and destination to prevent message loops
            'seen_by': [
                self.fidonet.format_address_for_seenby(gateway_address),
                self.fidonet.format_address_for_seenby(
                    self.get_linked_address()
                )
            ],
            'path': [self.fidonet.format_address_for_seenby(gateway_address)]
        }

        return fido_message
```

Replace it with:

```python
            # SEEN-BY and PATH per FTS-0004.001 EchoMail specification
            # SEEN-BY must include both source and destination to prevent message loops
            'seen_by': [
                self.fidonet.format_address_for_seenby(gateway_address),
                self.fidonet.format_address_for_seenby(
                    self.get_linked_address()
                )
            ],
            'path': [self.fidonet.format_address_for_seenby(gateway_address)]
        }

        extra_seenby = self.get_arearemap_seenby(area_tag)
        if extra_seenby:
            fido_message['seen_by'].append(extra_seenby)

        return fido_message
```

- [ ] **Step 2: Verify by exercising `convert_nntp_to_fido` with a synthetic NNTP message**

```bash
cd /home/vk3heg/claude/pygate && python3 -c "
from src.gateway import Gateway
g = Gateway('/tmp/pygate_addseenby_t1.cfg', load_spam_filter=False)
synthetic = {
    'message_id': '<test@example>',
    'subject': 'hello',
    'body': 'body',
    'from_name': 'Tester',
    'from_email': 'tester@example.com',
    'date': '',
    'headers': {},
}
m = g.convert_nntp_to_fido(synthetic, 'GENERAL', {'newsgroup': 'comp.misc'})
print('GENERAL seen_by:', m['seen_by'])
m2 = g.convert_nntp_to_fido(synthetic, 'UNRELATED', {'newsgroup': 'comp.unrelated'})
print('UNRELATED seen_by:', m2['seen_by'])
"
```

Expected output:
```
GENERAL seen_by: ['633/10', '633/1', '135/250']
UNRELATED seen_by: ['633/10', '633/1']
```

(`135/250` is appended ONLY for `GENERAL` because it is listed in `[Arearemap]`; `UNRELATED` is unaffected.)

- [ ] **Step 3: Commit**

```bash
cd /home/vk3heg/claude/pygate && git add src/gateway.py && git commit -m "$(cat <<'EOF'
gateway: append AddSeenBy address to SEEN-BY for mapped areas

convert_nntp_to_fido now appends the [Arearemap] AddSeenBy address to
the message's seen_by list when the target area is listed in
[Arearemap]. Areas that fall back to the default newsgroup mapping are
unaffected.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Document `AddSeenBy` in `pygate-sample.cfg`

**Files:**
- Modify: `pygate-sample.cfg:42-52`

- [ ] **Step 1: Add documentation under the `[Arearemap]` header**

Replace the existing block:

```
[Arearemap]
# PyGate Newsgroups Mapping
# Format: FIDONET_AREA newsgroup.name
# If no mapping exists, the usenet area name will be used as the fidonet area name
# Only add entries here if you need to remap an area to a different newsgroup name
# Example remappings (uncomment and modify as needed):
#
# LINUX comp.os.linux.misc
# PYTHON comp.lang.python
# TEST alt.test
```

with:

```
[Arearemap]
# PyGate Newsgroups Mapping
# Format: FIDONET_AREA = newsgroup.name
# If no mapping exists, the usenet area name will be used as the fidonet area name
# Only add entries here if you need to remap an area to a different newsgroup name
# Example remappings (uncomment and modify as needed):
#
# LINUX = comp.os.linux.misc
# PYTHON = comp.lang.python
# TEST = alt.test

# Optional: AddSeenBy
# Appends a single FidoNet address to the SEEN-BY line of NNTP -> FidoNet
# gated messages, but only for areas listed in this [Arearemap] section.
# Areas that fall back to the default newsgroup mapping are unaffected.
# Format: zone:net/node[.point]
# Example:
# AddSeenBy = 1:135/250
```

(The `Format` line was also corrected to show the `=` separator that configparser actually expects; the previous version showed space-separated which would not parse.)

- [ ] **Step 2: Verify the file still parses cleanly**

```bash
python3 -c "
import configparser
c = configparser.ConfigParser()
c.read('/home/vk3heg/claude/pygate/pygate-sample.cfg')
print('Sections:', c.sections())
print('Arearemap items:', list(c.items('Arearemap')))
"
```

Expected: no exception, `Arearemap` listed in sections, items list is empty (all examples are commented).

- [ ] **Step 3: Commit**

```bash
cd /home/vk3heg/claude/pygate && git add pygate-sample.cfg && git commit -m "$(cat <<'EOF'
sample config: document [Arearemap] AddSeenBy keyword

Adds documentation for the new optional AddSeenBy key. Also corrects
the Arearemap example syntax to show the '=' separator that
configparser expects.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Version bump + DEVLOG entry + CLAUDE.md update

**Files:**
- Modify: `pygate.py:22` (`__version__`)
- Modify: `DEVLOG.md` (new section at top)
- Modify: `CLAUDE.md:4` (version line) and `CLAUDE.md` Notable Fixes block

- [ ] **Step 1: Bump version in `pygate.py`**

Change line 22 from:

```python
__version__ = '1.5.15'
```

to:

```python
__version__ = '1.5.16'
```

- [ ] **Step 2: Add DEVLOG entry**

Insert the following entry in `DEVLOG.md` immediately above the `### Version 1.5.15` heading, and update the `**Last Updated:**` line at the top of the file to today's date (`June 11, 2026`):

```markdown
### Version 1.5.16 (June 11, 2026)

#### [Arearemap] AddSeenBy

Added an optional `AddSeenBy` keyword to the `[Arearemap]` section. When
set, the configured FidoNet address is appended to the SEEN-BY line of
messages gated NNTP -> FidoNet, but only for areas explicitly listed in
`[Arearemap]`. Areas that fall back to the default newsgroup mapping are
unaffected.

Configuration:

```
[Arearemap]
AddSeenBy = 1:135/250
GENERAL = comp.misc
LINUX = comp.os.linux
```

Implementation notes:

- A new `Gateway.get_arearemap_seenby(area_tag)` helper resolves and
  caches the configured address, formats it via
  `format_address_for_seenby`, and returns it only when `area_tag` is
  listed in `[Arearemap]`.
- `get_area_name_for_newsgroup()` skips the `AddSeenBy` key when
  iterating, so it is never treated as a (FidoNet area -> newsgroup)
  mapping.
- Malformed `AddSeenBy` values are logged once at WARNING and ignored.
- No deduplication: if the configured address equals `gateway_address`
  or `linked_address`, it will appear twice on SEEN-BY.
- Only the NNTP -> FidoNet direction is affected.
```

- [ ] **Step 3: Update `CLAUDE.md` version reference and Notable Fixes**

Change line 4 from:

```
Based on SoupGate by Tom Torfs. Currently v1.5.15.
```

to:

```
Based on SoupGate by Tom Torfs. Currently v1.5.16.
```

In the `## Notable Fixes (Recent)` block, insert this entry above the existing `- v1.5.15:` line:

```
- v1.5.16: [Arearemap] AddSeenBy keyword - appends a single FidoNet address to the SEEN-BY line of NNTP->FidoNet messages, but only for areas listed in [Arearemap]
```

- [ ] **Step 4: Verify versions are consistent**

```bash
cd /home/vk3heg/claude/pygate && grep -nH "1\.5\.16" pygate.py DEVLOG.md CLAUDE.md | head
```

Expected: at least one match per file showing `1.5.16`.

- [ ] **Step 5: Commit**

```bash
cd /home/vk3heg/claude/pygate && git add pygate.py DEVLOG.md CLAUDE.md && git commit -m "$(cat <<'EOF'
bump to v1.5.16: [Arearemap] AddSeenBy keyword

DEVLOG entry, CLAUDE.md version line + Notable Fixes entry, pygate.py
__version__ bump.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: End-to-end sanity check

**Files:** none (verification only)

- [ ] **Step 1: Run `--check` against the fixture config to confirm no regressions in config parsing**

```bash
cd /home/vk3heg/claude/pygate && python3 pygate.py --config /tmp/pygate_addseenby_t1.cfg --check 2>&1 | head -30
```

Expected: the existing `--check` output appears. The NNTP connection check may fail (localhost:119 unreachable) — that is unrelated. No traceback from `[Arearemap]` parsing.

- [ ] **Step 2: Confirm `convert_nntp_to_fido` end-to-end still produces the expected `seen_by`**

```bash
cd /home/vk3heg/claude/pygate && python3 -c "
from src.gateway import Gateway
g = Gateway('/tmp/pygate_addseenby_t1.cfg', load_spam_filter=False)
synthetic = {
    'message_id': '<final@example>',
    'subject': 'final',
    'body': 'final body',
    'from_name': 'Tester',
    'from_email': 'tester@example.com',
    'date': '',
    'headers': {},
}
m = g.convert_nntp_to_fido(synthetic, 'GENERAL', {'newsgroup': 'comp.misc'})
assert '135/250' in m['seen_by'], f'AddSeenBy missing from {m[\"seen_by\"]}'
m2 = g.convert_nntp_to_fido(synthetic, 'UNRELATED', {'newsgroup': 'comp.unrelated'})
assert '135/250' not in m2['seen_by'], f'AddSeenBy leaked to {m2[\"seen_by\"]}'
print('OK')
"
```

Expected: `OK` on the last line. No assertion errors.

- [ ] **Step 3: Clean up fixture files**

```bash
rm -f /tmp/pygate_addseenby_t1.cfg /tmp/pygate_areas_t1.cfg
```

- [ ] **Step 4: Final commit summary**

```bash
cd /home/vk3heg/claude/pygate && git log --oneline main ^HEAD~6 2>/dev/null || git log --oneline -6
```

Expected: six new commits visible (Tasks 1-5 plus the prior design-doc commit `697e6aa`).

---

## Self-review

**Spec coverage:**
- Config syntax (one `AddSeenBy` key, global): Task 4 documents, Task 1 reads.
- Apply only NNTP -> FidoNet: Task 3 injects only in `convert_nntp_to_fido`.
- Apply only to areas in `[Arearemap]`: Task 1 builds and filters the area set; Task 3 calls helper with `area_tag`.
- Edge cases (absent section, missing key, no other entries, malformed value, duplicate addresses): covered by Task 1 logic and Tasks 1.4-1.6 verification steps.
- `get_area_name_for_newsgroup` skips `AddSeenBy`: Task 2.
- Sample config documentation: Task 4.

**Placeholder scan:** No TBD/TODO. Every code change shows the exact code. Every verification step shows the exact command and expected output.

**Type/name consistency:** `get_arearemap_seenby`, `_build_arearemap_seenby_cache`, and `_ADDSEENBY_RE` are referenced consistently across Tasks 1-3. `_arearemap_seenby_cache` attribute is the same name throughout. `area_tag` is the parameter name across the helper and the call site.

**Spec gaps:** None. The version bump + DEVLOG + CLAUDE.md tasks were not strictly in the spec but follow the project's established pattern (every feature gets a version bump and changelog entry), so I included them as Task 5.
