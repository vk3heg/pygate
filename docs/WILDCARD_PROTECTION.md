# PyGate Wildcard Protection

## Feature Added

PyGate's areafix module now includes built-in wildcard protection to prevent users from subscribing to all newsgroups with a single `*` command.

## How It Works

### Automatic Blocking

When a user sends an areafix message with wildcard or excessive subscriptions:

1. **Message received** to AREAFIX/AREAMGR
2. **Password validated** (existing functionality)
3. **Commands parsed** (existing functionality)
4. **NEW: Wildcard protection check**
   - Blocks `*` and `+*` patterns
   - Blocks requests with >100 areas (configurable)
5. **Rejection message sent** back to user
6. **Request logged** for admin review

### No Processing if Blocked

PyGate blocks the request early and sends a helpful rejection message immediately.

## Configuration

### pygate.cfg Configuration

Add to your `[Areafix]` section:

```ini
[Areafix]
# Maximum areas allowed in a single areafix request
# Default: 100
max_areas_per_request = 100

# Existing settings...
areafix_password = yourpassword
```

### Default Settings (if not configured)

If you don't add `max_areas_per_request` to your config:
- Default limit: **100 areas per request**
- Blocked patterns: `*` and `+*`

## Examples

### Example 1: Wildcard Blocked

**User sends:**
```
TO: AREAFIX
SUBJECT: mypassword

*
```

**User receives:**
```
Areafix processing results:

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

--- End of response ---
```

### Example 2: Excessive Subscriptions Blocked

**User sends:**
```
TO: AREAFIX
SUBJECT: mypassword

+area1
+area2
... (150 areas total) ...
+area150
```

**User receives:**
```
REQUEST BLOCKED

Too many subscription requests (150 areas). Maximum allowed is 100.
Please subscribe in smaller batches.

WHAT TO DO INSTEAD:
  1. Use 'QUERY <pattern>' to search for areas
  2. Subscribe to specific areas
  3. Send 'HELP' for more information

Your request was automatically blocked for security reasons.
```

### Example 3: Legitimate Request (Allowed)

**User sends:**
```
TO: AREAFIX
SUBJECT: mypassword

+comp.lang.python
+aus.cars
QUERY comp.*
```

**User receives:**
```
Areafix processing results:

+ comp.lang.python: ADDED
+ aus.cars: ADDED

Areas matching 'comp.*' (684 found):
comp.ai                              yes
comp.lang.c                          no
comp.lang.python                     yes
...

--- End of response ---
```

## Log Output

### When Wildcard is Blocked

```
2025-10-05 14:32:15 - PyGate - INFO - Processing areafix from Nick Andre
2025-10-05 14:32:15 - PyGate - WARNING - BLOCKED areafix from Nick Andre: Wildcard subscription '*' is not permitted. Use QUERY to search for specific areas.
```

### When Excessive Request is Blocked

```
2025-10-05 14:35:20 - PyGate - INFO - Processing areafix from Andrew Clarke
2025-10-05 14:35:20 - PyGate - WARNING - BLOCKED areafix from Andrew Clarke: Too many subscription requests (150 areas). Maximum allowed is 100. Please subscribe in smaller batches.
```

### When Request is Allowed

```
2025-10-05 14:40:10 - PyGate - INFO - Processing areafix from Deon George
2025-10-05 14:40:10 - PyGate - INFO - Areafix response packet created for Deon George
```

## Blocked Patterns

### Default Blocked Patterns

1. **`*`** - Plain wildcard
2. **`+*`** - Wildcard with subscribe prefix

### Why These Are Blocked

With 34,716 newsgroups available:
- Subscribing to all would create **34,716 new subscriptions**
- Would overwhelm the user's system
- Would consume massive bandwidth
- Would create processing delays

## Benefits for PyGate Users

### 1. Automatic Protection
- No manual configuration required
- Works out of the box

### 2. User Education
- Rejection message explains why blocked
- Provides helpful alternatives
- Shows correct usage examples

### 3. System Protection
- Prevents accidental mass subscriptions
- Reduces bandwidth usage
- Prevents storage issues

### 4. Configurable Limits
- Adjust `max_areas_per_request` to your needs
- Can set to 50, 200, etc.

## Customization

### Change Maximum Areas Limit

In `pygate.cfg`:
```ini
[Areafix]
max_areas_per_request = 50  # More restrictive
```

or

```ini
[Areafix]
max_areas_per_request = 200  # More permissive
```

### Add More Blocked Patterns (Code Change)

Edit `src/areafix_module.py` line 24:

```python
self.blocked_patterns = ['*', '+*', 'ALL', '+ALL']  # Add more patterns
```

### Disable Protection (Not Recommended)

Edit `src/areafix_module.py` line 24:

```python
self.blocked_patterns = []  # Disable wildcard blocking
self.max_areas_per_request = 999999  # Effectively unlimited
```

### PyGate Areafix (Built-in)
- ✅ Blocks at processing time
- ✅ Sends immediate rejection message
- ✅ Logged in PyGate logs
- ✅ No quarantine needed
- ✅ User gets instant feedback


## Testing PyGate Protection

### Test 1: Wildcard Subscription

Send yourself an areafix message:
```
TO: AREAFIX
SUBJECT: <your_password>

*
```

Expected result: Rejection message explaining wildcard is blocked

### Test 2: Excessive Subscriptions

Create a message with 150 subscriptions, send to AREAFIX.

Expected result: Rejection message about exceeding limit

### Test 3: Legitimate Request

```
TO: AREAFIX
SUBJECT: <your_password>

+comp.lang.python
+aus.cars
```

Expected result: Subscriptions processed normally

## Configuration Examples

### Conservative (Tight Limits)

```ini
[Areafix]
max_areas_per_request = 25
areafix_password = yourpassword
```

### Moderate (Default)

```ini
[Areafix]
max_areas_per_request = 100
areafix_password = yourpassword
```

### Permissive (Higher Limits)

```ini
[Areafix]
max_areas_per_request = 250
areafix_password = yourpassword
```

## Integration with Existing PyGate

### No Changes Required

The protection is built into the areafix module and works automatically with your existing PyGate installation.

### Backward Compatible

- If `max_areas_per_request` is not in config, defaults to 100
- Existing areafix functionality unchanged
- Only adds protection layer

## Security Benefits

1. **Prevents accidental damage**
   - Users can't accidentally subscribe to everything
   - Typos like `*` instead of area name are caught

2. **Prevents malicious requests**
   - Deliberate attempts to overload system blocked
   - Excessive requests detected and rejected

3. **Educates users**
   - Helpful error messages
   - Shows correct usage
   - Reduces support requests

## Summary

### What Was Added

- ✅ Wildcard pattern blocking (`*`, `+*`)
- ✅ Excessive subscription limiting (default: 100)
- ✅ Helpful rejection messages
- ✅ Configurable limits
- ✅ Full logging

### What Stays the Same

- ✅ All existing areafix commands work
- ✅ QUERY, LIST, HELP unchanged
- ✅ Normal subscriptions work fine
- ✅ Password protection still required

### For PyGate Users

The wildcard protection is now active in PyGate's areafix module. It will automatically block dangerous wildcard subscriptions and send helpful rejection messages to users.

No configuration changes are required - it works out of the box with sensible defaults!
