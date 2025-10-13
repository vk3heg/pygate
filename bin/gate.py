#!/usr/bin/env python3
"""
Enhanced PyGate Automation Script
Runs PyGate import/export cycle with robust error handling
Designed to be run every 30 minutes via Task Scheduler (Windows) or cron (Unix)
Cross-platform replacement for gate.bat
"""

import os
import sys
import time
import argparse
import subprocess
import platform
import signal
from pathlib import Path
from datetime import datetime
import psutil
import tempfile


class PyGateAutomation:
    """Automation handler for PyGate operations"""

    def __init__(self, debug=False, dry_run=False):
        self.debug_mode = debug
        self.dry_run = dry_run

        # Configuration
        self.script_dir = Path(__file__).parent.resolve()
        self.pygate_dir = self.script_dir.parent
        self.log_dir = self.pygate_dir / "data" / "logs"
        self.logfile = self.log_dir / "gate.log"
        self.lockfile = Path(tempfile.gettempdir()) / "pygate.lock"
        self.max_runtime = 1800

        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Statistics tracking
        self.stats = {
            'imported_files': 0,
            'exported_files': 0,
            'held_count': 0,
            'processed_count': 0
        }

        # Track start time for cycle duration
        self.cycle_start_time = None

        # Set up signal handlers for clean shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle signals for clean shutdown"""
        signal_name = signal.Signals(signum).name
        self.log(f"Interrupted by signal {signal_name}")
        self.cleanup()
        sys.exit(128 + signum)

    def log(self, message):
        """Log a message to both file and stdout"""
        timestamp = datetime.now().strftime("%d-%b-%y %H:%M:%S")
        log_entry = f"{timestamp} - {message}"

        # Write to log file
        try:
            with open(self.logfile, 'a', encoding='utf-8') as f:
                f.write(log_entry + '\n')
        except Exception as e:
            print(f"{timestamp} - ERROR: Cannot write to log file: {e}")

        # Also print to stdout
        print(log_entry)

    def debug(self, message):
        """Log a debug message if debug mode is enabled"""
        if self.debug_mode:
            self.log(f"DEBUG: {message}")

    def error_exit(self, message, exit_code=1):
        """Log error and exit"""
        self.log(f"ERROR: {message}")
        self.cleanup()
        sys.exit(exit_code)

    def cleanup(self):
        """Clean up resources and lock files"""
        try:
            if self.lockfile.exists():
                self.lockfile.unlink()
                self.debug("Lock file removed")
        except Exception as e:
            self.debug(f"Error during cleanup: {e}")

    def run_with_timeout(self, cmd, timeout_val, desc):
        """Run a command with timeout"""
        self.log(f"Starting: {desc}")
        self.debug(f"Command: {cmd} (timeout: {timeout_val}s)")

        if self.dry_run:
            self.log(f"DRY RUN: Would execute {desc}")
            return True, None

        try:
            # Split command if it's a string
            if isinstance(cmd, str):
                import shlex
                cmd_list = shlex.split(cmd) if platform.system() != "Windows" else cmd
            else:
                cmd_list = cmd

            result = subprocess.run(
                cmd_list,
                cwd=self.pygate_dir,
                timeout=timeout_val,
                capture_output=True,
                text=True,
                shell=isinstance(cmd, str) and platform.system() == "Windows"
            )

            if result.returncode == 0:
                self.log(f"Completed: {desc}")
                return True, result
            else:
                self.log(f"FAILED: {desc} (exit code: {result.returncode})")
                if result.stderr and self.debug_mode:
                    self.debug(f"Error output: {result.stderr[:500]}")
                return False, result

        except subprocess.TimeoutExpired:
            self.log(f"TIMEOUT: {desc} exceeded {timeout_val}s")
            return False, None
        except Exception as e:
            self.log(f"EXCEPTION: {desc} - {str(e)}")
            return False, None

    def check_lock(self):
        """Check and create lock file to prevent concurrent execution"""
        if self.dry_run:
            self.log("DRY RUN: Skipping lock file check")
            return

        if self.lockfile.exists():
            try:
                with open(self.lockfile, 'r') as f:
                    lock_pid = int(f.read().strip())

                # Check if process is still running
                if psutil.pid_exists(lock_pid):
                    try:
                        proc = psutil.Process(lock_pid)
                        # Check if it's actually a Python process
                        if 'python' in proc.name().lower():
                            self.log(f"PyGate is already running (PID: {lock_pid}). Exiting.")
                            sys.exit(0)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                # Stale lock file
                self.log("Stale lock file found. Removing...")
                self.lockfile.unlink()

            except Exception as e:
                self.debug(f"Error checking lock file: {e}")
                # Try to remove potentially corrupted lock file
                try:
                    self.lockfile.unlink()
                except:
                    pass

        # Create lock file with current PID
        current_pid = os.getpid()
        try:
            with open(self.lockfile, 'w') as f:
                f.write(str(current_pid))
            self.debug(f"Lock file created (PID: {current_pid})")
        except Exception as e:
            self.error_exit(f"Cannot create lock file: {e}")

    def preflight_checks(self):
        """Perform pre-flight checks before running PyGate"""
        self.log("Performing pre-flight checks...")

        # Check if pygate.py exists
        pygate_script = self.pygate_dir / "pygate.py"
        if not pygate_script.exists():
            self.error_exit(f"pygate.py not found in {self.pygate_dir}")

        # Check Python availability
        try:
            result = subprocess.run(
                [sys.executable, "--version"],
                capture_output=True,
                text=True
            )
            self.debug(f"Python version: {result.stdout.strip()}")
        except Exception as e:
            self.error_exit(f"Python not available: {e}")

        # Check configuration file
        config_file = self.pygate_dir / "pygate.cfg"
        if not config_file.exists():
            self.error_exit(f"Configuration file not found: {config_file}")

        self.config_file = config_file
        self.debug(f"Using config file: {config_file}")

        # Read log retention days from config (default: 30 days)
        self.log_retention_days = 30  # Default value
        try:
            with open(config_file, 'r') as f:
                for line in f:
                    if line.strip().startswith('log_retention_days'):
                        parts = line.strip().split('=', 1)
                        if len(parts) == 2:
                            try:
                                self.log_retention_days = int(parts[1].strip())
                                self.debug(f"Log retention: {self.log_retention_days} days")
                            except ValueError:
                                self.debug(f"Invalid log_retention_days value, using default: 30")
                        break
        except Exception as e:
            self.debug(f"Error reading log_retention_days from config: {e}")

        # Check and create required directories
        required_dirs = [
            "data/inbound",
            "data/outbound",
            "data/logs",
            "data/hold",
            "data/temp"
        ]

        for dir_path in required_dirs:
            full_path = self.pygate_dir / dir_path
            if not full_path.exists():
                self.debug(f"Creating directory: {dir_path}")
                try:
                    full_path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    self.error_exit(f"Cannot create directory {dir_path}: {e}")

        # Test basic configuration (quick check)
        success, _ = self.run_with_timeout(
            [sys.executable, str(pygate_script), "--config", str(config_file), "--check", "--dry-run"],
            30,
            "Configuration validation"
        )
        if not success:
            self.log("WARNING: Configuration check failed - proceeding anyway")

        self.debug("Pre-flight checks completed")

    def generate_stats(self):
        """Generate and log statistics"""
        stats_file = self.log_dir / "gate_stats.log"

        # Count files in various directories
        inbound_dir = self.pygate_dir / "data" / "inbound"
        outbound_dir = self.pygate_dir / "data" / "outbound"
        hold_pending_dir = self.pygate_dir / "data" / "hold" / "pending"
        processed_dir = self.pygate_dir / "data" / "inbound" / "processed"

        inbound_count = len(list(inbound_dir.glob("*.pkt"))) if inbound_dir.exists() else 0
        outbound_count = len(list(outbound_dir.glob("*.pkt"))) if outbound_dir.exists() else 0
        held_count = len(list(hold_pending_dir.glob("*.json"))) if hold_pending_dir.exists() else 0

        # Count processed files from last 24 hours
        processed_count = 0
        if processed_dir.exists():
            day_ago = time.time() - 86400  # 24 hours in seconds
            processed_count = sum(1 for f in processed_dir.glob("*.pkt") if f.stat().st_mtime > day_ago)

        # Log statistics
        timestamp = datetime.now().strftime("%d-%b-%y %H:%M:%S")
        stats_entry = (f"{timestamp} - Inbound: {inbound_count}, "
                      f"Outbound: {outbound_count}, Held: {held_count}, "
                      f"Processed(24h): {processed_count}")

        try:
            with open(stats_file, 'a', encoding='utf-8') as f:
                f.write(stats_entry + '\n')
        except Exception as e:
            self.debug(f"Error writing stats: {e}")

        # Rotate stats file if it gets too large (keep last 500 lines)
        if stats_file.exists():
            try:
                with open(stats_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                if len(lines) > 1000:
                    self.debug("Rotating stats file")
                    with open(stats_file, 'w', encoding='utf-8') as f:
                        f.writelines(lines[-500:])
            except Exception as e:
                self.debug(f"Error rotating stats file: {e}")

        self.debug(f"Statistics: Inbound={inbound_count}, Outbound={outbound_count}, Held={held_count}")

    def check_disk_space(self):
        """Check available disk space"""
        min_free_mb = 100

        try:
            stat = os.statvfs(str(self.pygate_dir)) if hasattr(os, 'statvfs') else None

            if stat:
                # Unix-like systems
                available_mb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024)
            else:
                # Windows
                import shutil
                total, used, free = shutil.disk_usage(str(self.pygate_dir))
                available_mb = free / (1024 * 1024)

            if available_mb < min_free_mb:
                self.log(f"WARNING: Low disk space: {available_mb:.1f}MB available (minimum: {min_free_mb}MB)")
                return False

            self.debug(f"Disk space OK: {available_mb:.1f}MB available")
            return True

        except Exception as e:
            self.debug(f"Error checking disk space: {e}")
            return True  # Continue anyway

    def run_pygate_cycle(self):
        """Run the main PyGate import/export cycle"""
        self.cycle_start_time = time.time()
        self.log("Starting PyGate cycle")

        # Check disk space before processing
        if not self.check_disk_space():
            self.log("WARNING: Continuing despite low disk space")

        pygate_script = self.pygate_dir / "pygate.py"

        # Get lock file timestamp for counting new files
        lock_time = self.lockfile.stat().st_mtime if self.lockfile.exists() and not self.dry_run else time.time()

        # Import FidoNet packets
        success, result = self.run_with_timeout(
            [sys.executable, str(pygate_script), "--import"],
            300,
            "Import FidoNet packets"
        )

        if success:
            processed_dir = self.pygate_dir / "data" / "inbound" / "processed"
            if processed_dir.exists():
                # Count files newer than lock file
                imported_files = sum(1 for f in processed_dir.glob("*.pkt") if f.stat().st_mtime > lock_time)
                if imported_files > 0:
                    self.log(f"Imported {imported_files} packet(s)")
        else:
            self.log("WARNING: Import phase failed - continuing with export")

        # Export NNTP messages
        success, result = self.run_with_timeout(
            [sys.executable, str(pygate_script), "--export"],
            600,
            "Export NNTP messages"
        )

        if success:
            outbound_dir = self.pygate_dir / "data" / "outbound"
            if outbound_dir.exists():
                # Count files newer than lock file
                exported_files = sum(1 for f in outbound_dir.glob("*.pkt") if f.stat().st_mtime > lock_time)
                if exported_files > 0:
                    self.log(f"Created {exported_files} outbound packet(s)")
        else:
            self.log("WARNING: Export phase failed")

        # Process held messages (if any)
        hold_approved_dir = self.pygate_dir / "data" / "hold" / "approved"
        if hold_approved_dir.exists():
            held_count = len(list(hold_approved_dir.glob("*.json")))
            if held_count > 0:
                self.log(f"Processing {held_count} held message(s)")
                self.run_with_timeout(
                    [sys.executable, str(pygate_script), "--process-held"],
                    300,
                    "Process held messages"
                )

        # Pack outbound messages
        success, result = self.run_with_timeout(
            [sys.executable, str(pygate_script), "--pack"],
            180,
            "Pack outbound messages"
        )
        if not success:
            self.log("WARNING: Pack phase failed")

        # Connect to FidoNet hub with binkd
        self.run_binkd_connection()

        # Areafix processing
        self.run_with_timeout(
            [sys.executable, str(pygate_script), "--areafix"],
            60,
            "Process areafix requests"
        )

        # Calculate and log cycle duration
        if self.cycle_start_time:
            duration = int(time.time() - self.cycle_start_time)
            self.log(f"PyGate cycle completed in {duration}s")
        else:
            self.log("PyGate cycle completed")

    def run_binkd_connection(self):
        """Run binkd to connect to FidoNet hub"""
        # Determine binkd executable name based on platform
        if platform.system() == "Windows":
            binkd_exe = self.pygate_dir / "bin" / "BINKDWIN.EXE"
        else:
            binkd_exe = self.pygate_dir / "bin" / "binkd"

        if not binkd_exe.exists():
            self.log("WARNING: binkd binary not found - skipping FidoNet connection")
            return

        # Read linked_address from config
        linked_address = None
        try:
            with open(self.config_file, 'r') as f:
                for line in f:
                    if line.strip().startswith('linked_address'):
                        parts = line.strip().split('=', 1)
                        if len(parts) == 2:
                            linked_address = parts[1].strip()
                            break
        except Exception as e:
            self.debug(f"Error reading config for linked_address: {e}")

        if not linked_address:
            self.log("WARNING: linked_address not found in config - skipping FidoNet connection")
            return

        # Find binkd config (check both new and old locations)
        binkd_config = self.pygate_dir / "config" / "binkd.config"
        if not binkd_config.exists():
            binkd_config = self.pygate_dir / "binkd.config"
            if not binkd_config.exists():
                self.log("WARNING: binkd.config not found - skipping FidoNet connection")
                return

        # Run binkd
        self.log(f"Connecting to FidoNet hub ({linked_address})")
        cmd = [str(binkd_exe), "-p", "-P", linked_address, str(binkd_config)]
        success, result = self.run_with_timeout(cmd, 300, "FidoNet hub connection (binkd)")

        if not success:
            self.log("WARNING: FidoNet hub connection failed")

    def run_maintenance(self):
        """Run maintenance tasks at 2 AM"""
        current_hour = datetime.now().hour

        if current_hour == 2:
            self.log("Running maintenance tasks")

            # Run PyGate's maintenance (cleans up old packets)
            pygate_script = self.pygate_dir / "pygate.py"
            success, result = self.run_with_timeout(
                [sys.executable, str(pygate_script), "--maintenance"],
                600,
                "Maintenance tasks"
            )
            if not success:
                self.log("WARNING: Maintenance failed")

            # Clean up old compressed log files
            try:
                current_time = time.time()
                max_age_seconds = self.log_retention_days * 24 * 3600
                removed_count = 0

                for log_file in self.log_dir.glob("*.log.*.gz"):
                    if current_time - log_file.stat().st_mtime > max_age_seconds:
                        log_file.unlink()
                        removed_count += 1
                        self.debug(f"Removed old log: {log_file.name}")

                if removed_count > 0:
                    self.log(f"Removed {removed_count} old compressed log file(s) (retention: {self.log_retention_days} days)")
            except Exception as e:
                self.log(f"WARNING: Error cleaning old logs: {e}")

            # Clean up old hold backup files
            try:
                hold_backup_dir = self.pygate_dir / "data" / "hold" / "backup"
                if hold_backup_dir.exists():
                    current_time = time.time()
                    max_age_seconds = self.log_retention_days * 24 * 3600
                    removed_count = 0

                    for backup_file in hold_backup_dir.glob("*.json"):
                        if current_time - backup_file.stat().st_mtime > max_age_seconds:
                            backup_file.unlink()
                            removed_count += 1
                            self.debug(f"Removed old hold backup: {backup_file.name}")

                    if removed_count > 0:
                        self.log(f"Removed {removed_count} old hold backup file(s) (retention: {self.log_retention_days} days)")
            except Exception as e:
                self.log(f"WARNING: Error cleaning old hold backups: {e}")

    def rotate_logs(self):
        """Rotate log files if they're too large"""
        max_size_mb = 10
        import shutil
        import gzip

        # PyGate date format for rotated logs (e.g., "12Oct25")
        timestamp_str = datetime.now().strftime("%d%b%y")

        # Rotate gate.log (this script's log)
        if self.logfile.exists():
            try:
                size_mb = self.logfile.stat().st_size / (1024 * 1024)
                if size_mb > max_size_mb:
                    self.debug(f"Rotating gate.log (size: {size_mb:.1f}MB)")

                    # Compress and save with timestamp
                    gzip_file = self.log_dir / f"gate.log.{timestamp_str}.gz"

                    with open(self.logfile, 'rb') as f_in:
                        with gzip.open(gzip_file, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)

                    self.debug(f"Compressed to {gzip_file.name}")

                    # Start new log
                    timestamp = datetime.now().strftime("%d-%b-%y %H:%M:%S")
                    with open(self.logfile, 'w', encoding='utf-8') as f:
                        f.write(f"{timestamp} - Log rotated (previous log compressed to {gzip_file.name})\n")
            except Exception as e:
                self.debug(f"Error rotating gate.log: {e}")

        # Rotate pygate.log (PyGate's main log)
        pygate_logfile = self.log_dir / "pygate.log"
        if pygate_logfile.exists():
            try:
                size_mb = pygate_logfile.stat().st_size / (1024 * 1024)
                if size_mb > max_size_mb:
                    self.debug(f"Rotating pygate.log (size: {size_mb:.1f}MB)")

                    # Compress and save with timestamp
                    gzip_file = self.log_dir / f"pygate.log.{timestamp_str}.gz"

                    with open(pygate_logfile, 'rb') as f_in:
                        with gzip.open(gzip_file, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)

                    self.debug(f"Compressed to {gzip_file.name}")

                    # Start new log with rotation message
                    timestamp = datetime.now().strftime("%d-%b-%y %H:%M:%S")
                    with open(pygate_logfile, 'w', encoding='utf-8') as f:
                        f.write(f"{timestamp} - INFO - Log rotated (previous log compressed to {gzip_file.name})\n")
            except Exception as e:
                self.debug(f"Error rotating pygate.log: {e}")

        # Rotate binkd.log (binkd mailer log)
        binkd_logfile = self.log_dir / "binkd.log"
        if binkd_logfile.exists():
            try:
                size_mb = binkd_logfile.stat().st_size / (1024 * 1024)
                if size_mb > max_size_mb:
                    self.debug(f"Rotating binkd.log (size: {size_mb:.1f}MB)")

                    # Compress and save with timestamp
                    gzip_file = self.log_dir / f"binkd.log.{timestamp_str}.gz"

                    with open(binkd_logfile, 'rb') as f_in:
                        with gzip.open(gzip_file, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)

                    self.debug(f"Compressed to {gzip_file.name}")

                    # Start new log with rotation message
                    timestamp = datetime.now().strftime("%d-%b-%y %H:%M:%S")
                    with open(binkd_logfile, 'w', encoding='utf-8') as f:
                        f.write(f"{timestamp} - Log rotated by PyGate automation (previous log compressed to {gzip_file.name})\n")
            except Exception as e:
                self.debug(f"Error rotating binkd.log: {e}")

    def run(self):
        """Main execution method"""
        try:
            if self.dry_run:
                self.log(f"PyGate automation started in DRY RUN mode (PID: {os.getpid()})")
            else:
                self.log(f"PyGate automation started (PID: {os.getpid()})")

            self.rotate_logs()
            self.check_lock()
            self.preflight_checks()
            self.run_pygate_cycle()
            self.generate_stats()
            self.run_maintenance()

            if self.dry_run:
                self.log("PyGate automation DRY RUN completed successfully")
            else:
                self.log("PyGate automation completed successfully")

            self.cleanup()
            return 0

        except KeyboardInterrupt:
            self.log("Interrupted by user")
            self.cleanup()
            return 130
        except Exception as e:
            self.error_exit(f"Unexpected error: {e}")
            return 1


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Enhanced PyGate automation script",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without executing commands'
    )

    args = parser.parse_args()

    # Create and run automation
    automation = PyGateAutomation(debug=args.debug, dry_run=args.dry_run)
    exit_code = automation.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
