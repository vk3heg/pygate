#!/bin/bash
#
# Enhanced PyGate Automation Script
# Runs PyGate import/export cycle with robust error handling
# Designed to be run every 30 minutes via cron
#

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYGATE_DIR="$(dirname "$SCRIPT_DIR")"
LOGFILE="$PYGATE_DIR/data/logs/gate.log"
LOCKFILE="/tmp/pygate.lock"
MAX_RUNTIME=1800  # 30 minutes max runtime
DEBUG=${DEBUG:-0}

# Logging function
log() {
    echo "[$(date '+%d-%b-%Y %H:%M:%S')] $1" | tee -a "$LOGFILE"
}

# Debug logging
debug() {
    [[ $DEBUG -eq 1 ]] && log "DEBUG: $1"
}

# Error handler
error_exit() {
    log "ERROR: $1"
    cleanup
    exit 1
}

# Cleanup function
cleanup() {
    [[ -f "$LOCKFILE" ]] && rm -f "$LOCKFILE"
    debug "Cleanup completed"
}

# Function to run commands with timeout
run_with_timeout() {
    local cmd="$1"
    local timeout="$2"
    local desc="$3"

    log "Starting: $desc"
    debug "Command: $cmd (timeout: ${timeout}s)"

    if timeout "$timeout" bash -c "$cmd"; then
        log "Completed: $desc"
        return 0
    else
        local exit_code=$?
        if [[ $exit_code -eq 124 ]]; then
            log "TIMEOUT: $desc exceeded $timeout seconds"
        else
            log "FAILED: $desc (exit code: $exit_code)"
        fi
        return $exit_code
    fi
}

# Check for existing lock file
check_lock() {
    if [[ -f "$LOCKFILE" ]]; then
        local lock_pid=$(cat "$LOCKFILE" 2>/dev/null)
        if [[ -n "$lock_pid" ]] && kill -0 "$lock_pid" 2>/dev/null; then
            log "PyGate is already running (PID: $lock_pid). Exiting."
            exit 0
        else
            log "Stale lock file found. Removing..."
            rm -f "$LOCKFILE"
        fi
    fi

    # Create lock file
    echo $$ > "$LOCKFILE"
    trap cleanup EXIT INT TERM
    debug "Lock file created (PID: $$)"
}

# Pre-flight checks
preflight_checks() {
    log "Performing pre-flight checks..."

    # Check if pygate.py exists
    [[ -f "$PYGATE_DIR/pygate.py" ]] || error_exit "pygate.py not found in $PYGATE_DIR"

    # Check Python availability
    command -v python3 >/dev/null || error_exit "python3 not found in PATH"

    # Check configuration (try new location first, then old location)
    if [[ -f "$PYGATE_DIR/config/pygate.cfg" ]]; then
        CONFIG_FILE="$PYGATE_DIR/config/pygate.cfg"
        debug "Using config file: config/pygate.cfg"
    elif [[ -f "$PYGATE_DIR/pygate.cfg" ]]; then
        CONFIG_FILE="$PYGATE_DIR/pygate.cfg"
        debug "Using config file: pygate.cfg (consider moving to config/ directory)"
    else
        error_exit "Configuration file not found (checked config/pygate.cfg and pygate.cfg)"
    fi

    # Check required directories
    for dir in "data/inbound" "data/outbound" "data/logs" "data/hold" "data/temp"; do
        if [[ ! -d "$PYGATE_DIR/$dir" ]]; then
            debug "Creating directory: $dir"
            mkdir -p "$PYGATE_DIR/$dir" || error_exit "Cannot create directory: $dir"
        fi
    done

    # Test basic configuration (quick check)
    if ! python3 "$PYGATE_DIR/pygate.py" --config "$CONFIG_FILE" --check --dry-run >/dev/null 2>&1; then
        log "WARNING: Configuration check failed - proceeding anyway"
    fi

    debug "Pre-flight checks completed"
}

# Generate statistics
generate_stats() {
    local stats_file="$PYGATE_DIR/data/logs/gate_stats.log"

    # Count files in various directories
    local inbound_count=$(find "$PYGATE_DIR/data/inbound" -name "*.pkt" 2>/dev/null | wc -l)
    local outbound_count=$(find "$PYGATE_DIR/data/outbound" -name "*.pkt" 2>/dev/null | wc -l)
    local held_count=$(find "$PYGATE_DIR/data/hold/pending" -name "*.json" 2>/dev/null | wc -l)
    local processed_count=$(find "$PYGATE_DIR/data/inbound/processed" -name "*.pkt" -mtime -1 2>/dev/null | wc -l)

    # Log statistics
    echo "[$(date '+%d-%b-%Y %H:%M:%S')] Inbound: $inbound_count, Outbound: $outbound_count, Held: $held_count, Processed(24h): $processed_count" >> "$stats_file"

    # Rotate stats file if it gets too large (keep last 1000 lines)
    if [[ -f "$stats_file" ]] && [[ $(wc -l < "$stats_file") -gt 1000 ]]; then
        debug "Rotating stats file"
        tail -500 "$stats_file" > "$stats_file.tmp" && mv "$stats_file.tmp" "$stats_file"
    fi

    debug "Statistics: Inbound=$inbound_count, Outbound=$outbound_count, Held=$held_count"
}

# Check disk space
check_disk_space() {
    local min_free_mb=100
    local available_mb=$(df "$PYGATE_DIR" | awk 'NR==2 {print int($4/1024)}')

    if [[ $available_mb -lt $min_free_mb ]]; then
        log "WARNING: Low disk space: ${available_mb}MB available (minimum: ${min_free_mb}MB)"
        return 1
    fi

    debug "Disk space OK: ${available_mb}MB available"
    return 0
}

# Main processing function
run_pygate_cycle() {
    local start_time=$(date +%s)
    log "Starting PyGate cycle"

    cd "$PYGATE_DIR" || error_exit "Cannot change to PyGate directory"

    # Check disk space before processing
    check_disk_space || log "WARNING: Continuing despite low disk space"

    # Import FidoNet packets
    if run_with_timeout "python3 pygate.py --import" 300 "Import FidoNet packets"; then
        local imported_files=$(find data/inbound/processed -name "*.pkt" -newer "$LOCKFILE" 2>/dev/null | wc -l)
        [[ $imported_files -gt 0 ]] && log "Imported $imported_files packet(s)"
    else
        log "WARNING: Import phase failed - continuing with export"
    fi

    # Export NNTP messages
    if run_with_timeout "python3 pygate.py --export" 600 "Export NNTP messages"; then
        local exported_files=$(find data/outbound -name "*.pkt" -newer "$LOCKFILE" 2>/dev/null | wc -l)
        [[ $exported_files -gt 0 ]] && log "Created $exported_files outbound packet(s)"
    else
        log "WARNING: Export phase failed"
    fi

    # Process held messages (if any)
    local held_count=$(find data/hold/approved -name "*.json" 2>/dev/null | wc -l)
    if [[ $held_count -gt 0 ]]; then
        log "Processing $held_count held message(s)"
        run_with_timeout "python3 pygate.py --process-held" 300 "Process held messages"
    fi

    # Pack outbound messages
    if ! run_with_timeout "python3 pygate.py --pack" 180 "Pack outbound messages"; then
        log "WARNING: Pack phase failed"
    fi

    # Connect to FidoNet hub with binkd to send/receive packets
    if [[ -f "$PYGATE_DIR/bin/binkd" ]] && [[ -f "$CONFIG_FILE" ]]; then
        # Extract linked_address from pygate.cfg
        local linked_address=$(grep -E "^linked_address\s*=" "$CONFIG_FILE" | sed 's/^linked_address\s*=\s*//' | tr -d ' ')

        if [[ -n "$linked_address" ]]; then
            local binkd_config="$PYGATE_DIR/config/binkd.config"
            # Check for binkd config in both new and old locations
            if [[ ! -f "$binkd_config" ]] && [[ -f "$PYGATE_DIR/binkd.config" ]]; then
                binkd_config="$PYGATE_DIR/binkd.config"
            fi

            if [[ -f "$binkd_config" ]]; then
                log "Connecting to FidoNet hub ($linked_address)"
                run_with_timeout "$PYGATE_DIR/bin/binkd -p -P $linked_address $binkd_config" 300 "FidoNet hub connection (binkd)" || log "WARNING: FidoNet hub connection failed"
            else
                log "WARNING: binkd.config not found - skipping FidoNet connection"
            fi
        else
            log "WARNING: linked_address not found in config - skipping FidoNet connection"
        fi
    else
        log "WARNING: binkd binary not found - skipping FidoNet connection"
    fi

    # Areafix processing (lightweight)
    run_with_timeout "python3 pygate.py --areafix" 60 "Process areafix requests" || true

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    log "PyGate cycle completed in ${duration}s"
}

# Maintenance tasks (run less frequently)
run_maintenance() {
    local hour=$(date +%H)

    # Run maintenance at 2 AM
    if [[ "$hour" == "02" ]]; then
        log "Running maintenance tasks"
        run_with_timeout "python3 pygate.py --maintenance" 600 "Maintenance tasks" || log "WARNING: Maintenance failed"
    fi
}

# Log rotation
rotate_logs() {
    local max_size_mb=10

    if [[ -f "$LOGFILE" ]]; then
        local size_mb=$(du -m "$LOGFILE" | cut -f1)
        if [[ $size_mb -gt $max_size_mb ]]; then
            debug "Rotating log file (size: ${size_mb}MB)"
            cp "$LOGFILE" "${LOGFILE}.old"
            echo "[$(date '+%d-%b-%Y %H:%M:%S')] Log rotated (previous log saved as gate.log.old)" > "$LOGFILE"
        fi
    fi
}

# Main execution
main() {
    # Set up signal handlers
    trap 'error_exit "Interrupted by signal"' INT TERM

    log "PyGate automation started (PID: $$)"

    # Rotate logs if needed
    rotate_logs

    # Perform checks
    check_lock
    preflight_checks

    # Run the main cycle
    run_pygate_cycle

    # Generate statistics
    generate_stats

    # Run maintenance if scheduled
    run_maintenance

    log "PyGate automation completed successfully"
}

# Handle command line arguments
case "${1:-}" in
    --debug)
        DEBUG=1
        log "Debug mode enabled"
        ;;
    --help|-h)
        echo "Usage: $0 [--debug] [--help]"
        echo "Enhanced PyGate automation script"
        echo ""
        echo "Options:"
        echo "  --debug    Enable debug logging"
        echo "  --help     Show this help message"
        exit 0
        ;;
esac

# Run main function
main "$@"
