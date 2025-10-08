# PyGate Changes Summary

## Admin Panel Improvements

### High Water Mark Default (admin_panel.py)
**Issue**: When adding newsgroups with high water mark set to 0, NNTP fetch operations would fail with "cannot read from timed out
  object" errors.

**Changes**:
- Changed high water mark default from 0 to 1 in newsgroup manager
- Now prompts: `High water mark (default: 1):`
- Prevents timeout errors when fetching from NNTP servers

**Location**: admin_panel.py, newsgroup manager section

### Double "Press Enter" Bug Fix (admin_panel.py)
**Issue**: Users had to press Enter twice after error messages throughout the admin panel.

**Root Cause**: `show_error()` method already calls `pause()` internally, but many locations were calling `self.pause()` again
  after `show_error()`.

**Changes**:
- Removed duplicate `self.pause()` calls after all `show_error()` invocations
- Affected multiple locations:
  - Newsgroup manager (add, edit, delete operations)
  - Newsrc manager menu
  - Filter manager
  - Network manager
  - Configuration manager
  - Various validation error handlers

**Impact**: Improved user experience - single Enter press after errors

### Log Viewer Improvements (admin_panel.py)
**Changes**:
1. **Navigation**: Changed "press 'b' for back" to "press 'Q'" for consistency
2. **Directory Scope**: Limited log search to `data/logs/` directory only (previously searched entire PyGate structure)
3. **Display**: Removed `data/logs/` prefix from filenames - shows just the filename
4. **Menu Flow**: Fixed "Q. Back to main menu" to return to log file selection menu instead of admin main menu
5. **Date Format**: Changed from `2025-10-08 12:00` to `03-Oct-25 12:00` for consistency

**Files Modified**:
- `get_log_files()`: Updated glob patterns to search only `data/logs/`
- `log_viewer()`: Added outer loop for proper menu navigation
- Display logic: Uses `os.path.basename()` for filename display

### Filter Manager (src/filter_manager.py)
**Changes**:
- Changed menu option from "3. Exit to Main Menu" to "Q. Exit to Main Menu"
- Updated input validation from `if mode == '3'` to `if mode.upper() == 'Q'`

**Consistency**: Matches other PyGate menus that use 'Q' for exit

## Date/Time Format Standardization

### Standard Format
All PyGate components now use consistent date/time format:
```
DD-Mon-YY HH:MM:SS - Message
```

Example: `08-Oct-25 13:25:17 - INFO - Starting PyGate`

### Files Modified

#### bin/gate.sh
**Changes**:
- Changed log format from `[DD-Mon-YYYY HH:MM:SS]` to `DD-Mon-YYYY HH:MM:SS -`
- Removed square brackets for cleaner output
- Updated `log()` function:
  ```bash
  log() {
      echo "$(date '+%d-%b-%Y %H:%M:%S') - $1" | tee -a "$LOGFILE"
  }
  ```

#### admin_panel.py
**Changes**:
- Log file selection menu: Changed date format from `%Y-%m-%d %H:%M` to `%d-%b-%y %H:%M`
- Affects log file listing display

**Impact**: All timestamps across PyGate now use the same format for easier log correlation and troubleshooting

## Summary of Changes

### Files Modified
1. **admin_panel.py**
   - High water mark default (0 → 1)
   - Removed 20+ duplicate `pause()` calls
   - Log viewer improvements (navigation, scope, display)
   - Date format standardization

2. **src/filter_manager.py**
   - Exit option changed (3 → Q)
   - Consistent with other menus

3. **bin/gate.sh**
   - Date/time format standardization
   - Removed square brackets from timestamps

### Impact
- **Reliability**: Fixed NNTP timeout errors with proper high water mark default
- **Usability**: Eliminated double Enter press requirement throughout admin panel
- **Consistency**: Standardized date/time format across all PyGate components
- **User Experience**: Improved log viewer navigation and display
- **Maintainability**: Cleaner, more consistent codebase

### Testing Recommendations
- Test newsgroup addition with default high water mark
- Verify single Enter press after all error messages
- Check log viewer navigation flow
- Confirm date/time format consistency across all logs
- Test filter manager exit with 'Q' key

## Configuration Notes

No configuration file changes required. All changes are internal code improvements that maintain backward compatibility.

## Upgrade Path

These changes are non-breaking and can be applied to existing PyGate installations without configuration changes or data migration.
