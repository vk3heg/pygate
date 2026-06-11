# [Arearemap] AddSeenBy

## Goal

Allow the sysop to add a single FidoNet address to the `SEEN-BY` line of
echomail messages that PyGate generates when gating NNTP -> FidoNet. The
addition applies only to areas that are explicitly remapped in the
`[Arearemap]` section. Areas that fall back to the default newsgroup mapping
(area name lowercased) are unaffected.

## Configuration

A new optional key, `AddSeenBy`, is recognised inside the existing
`[Arearemap]` section of `pygate.cfg`. Its value is a single full FidoNet
address.

```ini
[Arearemap]
AddSeenBy = 1:135/250
GENERAL = comp.misc
LINUX = comp.os.linux
```

Behaviour:

- `AddSeenBy` is optional. Absent or empty means current behaviour (no
  change to SEEN-BY).
- The key name is matched case-insensitively (`addseenby`, `AddSeenBy`,
  `ADDSEENBY` all work) - this falls out of `configparser`'s default key
  normalisation.
- Exactly one address. Lists of addresses are out of scope for this version.
- The address is a full FidoNet address with zone and (optional) point:
  `zone:net/node[.point]`. Examples: `1:135/250`, `2:221/1.100`.

## Behaviour

When `convert_nntp_to_fido()` (in `src/gateway.py`) builds an outbound
FidoNet message:

1. The existing `seen_by` list is built as today (gateway address + linked
   address, both formatted via `format_address_for_seenby()`).
2. The gateway looks up the configured `AddSeenBy` value.
3. If `AddSeenBy` is set AND the message's `area_tag` matches a key in
   `[Arearemap]` (case-insensitive comparison, excluding the `AddSeenBy`
   key itself), the formatted `AddSeenBy` address is appended to the
   `seen_by` list.
4. If the area is not listed in `[Arearemap]`, or `AddSeenBy` is not
   configured, the `seen_by` list is unchanged.

The reverse direction (FidoNet -> NNTP) is unaffected; SEEN-BY is not
constructed in that path.

## Edge cases

| Situation | Behaviour |
|-----------|-----------|
| `[Arearemap]` section absent entirely | No-op. |
| `AddSeenBy` not set, `[Arearemap]` populated | No-op. Existing behaviour. |
| `AddSeenBy` set, `[Arearemap]` has no area entries | No-op. No area matches. |
| `AddSeenBy` value is malformed | Log a warning once, skip the addition for all areas, continue normally. |
| `AddSeenBy` value equals `gateway_address` or `linked_address` | Address appears twice in SEEN-BY. No deduplication is performed (explicit non-goal). |
| Target area matches `[Arearemap]` key, AddSeenBy configured | Address appended to SEEN-BY. |

## Implementation outline

1. Add a helper `get_arearemap_seenby(area_tag: str) -> Optional[str]` on
   the `Gateway` class:
   - Returns `None` if `[Arearemap]` is absent, `AddSeenBy` is missing/
     empty, the address is malformed, or `area_tag` is not present in
     `[Arearemap]`.
   - Otherwise returns the formatted SEEN-BY string for the configured
     address (via `self.fidonet.format_address_for_seenby`).
   - Address validation reuses existing FidoNet address parsing in
     `fidonet_module`. A malformed value is logged once at WARNING and
     cached as "invalid" to avoid log spam.

2. Update `get_area_name_for_newsgroup()` (currently at
   `src/gateway.py:598`) to skip the `AddSeenBy` key when iterating
   `[Arearemap]`, so it is never treated as a `(fido_area -> newsgroup)`
   mapping. Comparison is case-insensitive.

3. In `convert_nntp_to_fido()` (`src/gateway.py:728`), after the existing
   `seen_by` list literal is built (around line 790), call
   `get_arearemap_seenby(area_tag)` and append the result if not `None`.

4. Document the new keyword in `pygate-sample.cfg` under the existing
   `[Arearemap]` comments.

## Testing

Manual:

- Configure `AddSeenBy = 1:135/250` in `[Arearemap]` plus at least one
  area remap (e.g. `GENERAL = comp.misc`).
- Inject an NNTP message destined for `GENERAL` (via the normal export
  path).
- Run `pygate.py --export` and inspect the generated `.pkt` for the new
  SEEN-BY entry containing `135/250`.
- Repeat with a message destined for an area NOT listed in `[Arearemap]`.
  Confirm the SEEN-BY for that message does not include `135/250`.
- Set `AddSeenBy = not-an-address`; confirm a warning is logged and the
  gateway continues to run normally without modifying SEEN-BY.

Automated unit tests are not required for this change, matching the
project's current testing posture.

## Non-goals

- Multiple `AddSeenBy` addresses (single global value only).
- Per-area `AddSeenBy` overrides.
- Modifying SEEN-BY on FidoNet messages re-emitted by PyGate in other
  flows (areafix replies, hold-queue releases, etc.).
- Deduplication when the configured address overlaps `gateway_address` or
  `linked_address`.

## Affected files

- `src/gateway.py` - helper method, iterator filter, injection point.
- `pygate-sample.cfg` - documentation of new keyword.
- `DEVLOG.md` - changelog entry under the next version bump.
- `CLAUDE.md` - mention in "Key Concepts" if appropriate.
