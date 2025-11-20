#!/usr/bin/env python3
"""
PyGate Admin Panel
Interactive terminal-based administration interface for PyGate
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List
import glob
import re
from datetime import datetime
import configparser

class AdminPanel:
    """Terminal-based admin panel for PyGate"""

    def __init__(self):
        self.running = True
        self.current_logfile = None
        self.log_viewer_position = 0
        self.config = None
        self.hold_module = None
        self.load_config()

    def load_config(self):
        """Load PyGate configuration"""
        try:
            self.config = configparser.ConfigParser()
            self.config.read('pygate.cfg')

            # Initialize hold module if config loaded successfully
            if self.config.has_section('FidoNet'):
                from src.hold_module import MessageHoldModule
                import logging
                logger = logging.getLogger('AdminPanel')
                self.hold_module = MessageHoldModule(self.config, logger)
        except Exception as e:
            print(f"Warning: Could not load configuration: {e}")

    def clear_screen(self):
        """Clear the terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def get_terminal_size(self):
        """Get terminal dimensions"""
        try:
            size = shutil.get_terminal_size()
            return size.columns, size.lines
        except:
            return 80, 24

    def get_log_viewer_page_size(self):
        """Calculate available lines for log viewer display"""
        cols, terminal_lines = self.get_terminal_size()
        # Reserve lines for header (3 lines) and footer (2 lines)
        header_lines = 3  # title, info, separator
        footer_lines = 2  # separator, help
        available_lines = terminal_lines - header_lines - footer_lines

        # Add reasonable limits: show between 10-25 lines of content
        # This prevents issues with incorrect terminal size detection
        # and provides a good viewing experience
        return max(10, min(available_lines, 40))

    def move_cursor(self, row: int, col: int):
        """Move cursor to specific position"""
        print(f'\033[{row};{col}H', end='')

    def clear_line(self):
        """Clear current line"""
        print('\033[K', end='')

    def show_header(self):
        """Display the admin panel header"""
        cols, lines = self.get_terminal_size()
        header = "=== PyGate Admin Panel ==="
        padding = (cols - len(header)) // 2
        print("=" * cols)
        print(" " * padding + header)
        print("=" * cols)
        print()

    def show_main_menu(self):
        """Display the main menu options"""
        print("1. Filter Manager")
        print("2. Log File Viewer")
        print("3. Gateway Status & System Info")
        print("4. Configuration Check")
        print("5. Hold Message Manager")
        print("6. Newsgroup Manager")
        print("Q. Exit")
        print()

    def get_input(self, prompt: str) -> str:
        """Get user input with prompt"""
        try:
            return input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            self.running = False
            return ""

    def pause(self, message: str = "Press Enter to continue..."):
        """Pause and wait for user input"""
        try:
            input(message)
        except (KeyboardInterrupt, EOFError):
            pass

    def show_error(self, message: str):
        """Display error message"""
        print(f"\n Error: {message}")
        self.pause()

    def show_success(self, message: str):
        """Display success message"""
        print(f"\n {message}")
        self.pause()

    def show_info(self, message: str):
        """Display info message"""
        print(f"\n  {message}")

    def run_filter_manager(self):
        """Launch the filter manager"""
        self.clear_screen()
        print("=== Launching Filter Manager ===")
        print()

        # Check if filter_manager.py exists
        filter_manager_path = 'src/filter_manager.py'
        if not os.path.exists(filter_manager_path):
            self.show_error("filter_manager.py not found in src directory")
            return

        try:
            # Run filter_manager.py in a subprocess
            subprocess.run([sys.executable, filter_manager_path], check=True)
        except subprocess.CalledProcessError as e:
            self.show_error(f"Filter Manager exited with error code {e.returncode}")
        except FileNotFoundError:
            self.show_error("Python interpreter not found")
        except KeyboardInterrupt:
            self.show_info("Filter Manager interrupted by user")

        self.pause()

    def get_log_files(self) -> List[str]:
        """Get list of available log files"""
        log_files = []

        # Look for log files in data/logs directory only
        log_patterns = [
            'data/logs/*.log',
            'data/logs/*.txt'
        ]

        for pattern in log_patterns:
            log_files.extend(glob.glob(pattern))

        # Remove duplicates and sort
        log_files = sorted(list(set(log_files)))

        return log_files

    def select_log_file(self) -> Optional[str]:
        """Let user select a log file"""
        log_files = self.get_log_files()

        if not log_files:
            self.show_error("No log files found")
            return None

        self.clear_screen()
        print("=== Select Log File ===")
        print()

        for i, file in enumerate(log_files, 1):
            file_size = self.get_file_size(file)
            mod_time = self.get_file_modified_time(file)
            # Display just the filename without the path
            filename = os.path.basename(file)
            print(f"{i:2d}. {filename:<30} ({file_size:>8}) {mod_time}")

        print()
        choice = self.get_input(f"Select log file (1-{len(log_files)}) or 'Q' to go back: ")

        if choice.upper() == 'Q':
            return None

        try:
            index = int(choice) - 1
            if 0 <= index < len(log_files):
                return log_files[index]
            else:
                self.show_error("Invalid selection")
                return None
        except ValueError:
            self.show_error("Invalid input")
            return None

    def get_file_size(self, filepath: str) -> str:
        """Get human-readable file size"""
        try:
            size = os.path.getsize(filepath)
            return self.format_bytes(size)
        except:
            return "Unknown"

    def format_bytes(self, bytes_count: int) -> str:
        """Format bytes into human-readable size"""
        try:
            size = float(bytes_count)
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024:
                    return f"{size:.1f}{unit}"
                size /= 1024
            return f"{size:.1f}TB"
        except:
            return "Unknown"

    def get_system_uptime(self) -> str:
        """Get system uptime in human-readable format"""
        try:
            # Read uptime from /proc/uptime (Linux)
            if os.path.exists('/proc/uptime'):
                with open('/proc/uptime', 'r') as f:
                    uptime_seconds = float(f.readline().split()[0])

                # Convert to days, hours, minutes
                days = int(uptime_seconds // 86400)
                hours = int((uptime_seconds % 86400) // 3600)
                minutes = int((uptime_seconds % 3600) // 60)

                if days > 0:
                    return f"{days}d {hours}h {minutes}m"
                elif hours > 0:
                    return f"{hours}h {minutes}m"
                else:
                    return f"{minutes}m"
            else:
                # Fallback for non-Linux systems - try using uptime command
                result = subprocess.run(['uptime'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    # Parse uptime output (format varies by system)
                    uptime_line = result.stdout.strip()
                    # Extract the "up X days, Y hours" part
                    if 'up' in uptime_line:
                        return uptime_line.split('up')[1].split(',')[0:2]
                    return uptime_line
                else:
                    return "Unable to determine"
        except Exception:
            return "Unable to determine"

    def get_file_modified_time(self, filepath: str) -> str:
        """Get file modification time"""
        try:
            mtime = os.path.getmtime(filepath)
            return datetime.fromtimestamp(mtime).strftime('%d-%b-%y %H:%M')
        except:
            return "Unknown"

    def read_log_file_lines(self, filepath: str) -> List[str]:
        """Read all lines from log file"""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                return f.readlines()
        except Exception as e:
            self.show_error(f"Error reading file: {e}")
            return []

    def display_log_page(self, lines: List[str], start_line: int, search_term: str = None):
        """Display a page of log lines"""
        cols, terminal_lines = self.get_terminal_size()

        # Get the current page size based on terminal dimensions
        page_size = self.get_log_viewer_page_size()
        end_line = min(start_line + page_size, len(lines))

        self.clear_screen()
        print(f"=== Log Viewer: {self.current_logfile} ===")
        print(f"Lines {start_line + 1}-{end_line} of {len(lines)} | Terminal: {cols}x{terminal_lines} | Page size: {page_size}")
        if search_term:
            print(f" Active search: '{search_term}' (N/Enter to find next, C to clear)")
        print("=" * cols)

        for i in range(start_line, end_line):
            line = lines[i].rstrip()

            # Check if this line matches the search term
            search_match = False
            if search_term and search_term.lower() in line.lower():
                search_match = True

            # Truncate long lines to fit terminal
            if len(line) > cols - 7:  # Extra space for search indicator
                line = line[:cols - 10] + "..."

            # Add search indicator if line matches
            prefix = " >" if search_match else "  "
            line_num = f"{i + 1:4d}:{prefix}"
            print(line_num + line)

        print("=" * cols)
        self.show_log_viewer_help(search_term)

    def show_log_viewer_help(self, search_term: str = None):
        """Show log viewer navigation help"""
        if search_term:
            print("N/Enter. Next match | P. Previous page | L. Last page | G. Go to line")
            print("S. New search | C. Clear search | Q. Back to log file menu")
        else:
            print("N. Next page | P. Previous page | L. Last page | G. Go to line | S. Search")
            print("C. Clear search | Q. Back to log file menu")

    def search_in_log(self, lines: List[str], search_term: str, start_from: int = 0) -> int:
        """Search for term in log lines, return line number or -1 if not found"""
        search_term = search_term.lower()

        for i in range(start_from, len(lines)):
            if search_term in lines[i].lower():
                return i

        # If not found from start_from onwards, search from beginning
        for i in range(0, start_from):
            if search_term in lines[i].lower():
                return i

        return -1

    def log_viewer(self):
        """Interactive log file viewer with paging"""
        while True:
            # Select log file
            selected_file = self.select_log_file()
            if not selected_file:
                return

            self.current_logfile = selected_file

            # Read file lines
            lines = self.read_log_file_lines(selected_file)
            if not lines:
                continue

            current_line = 0
            current_search_term = None  # Track current search term for continuing searches

            while True:
                # Get current page size (recalculated each time in case terminal was resized)
                page_size = self.get_log_viewer_page_size()

                self.display_log_page(lines, current_line, current_search_term)

                command = self.get_input("Command: ").upper().strip()

                if command == 'Q':
                    break
                elif command in ['N', 'NEXT', '']:
                    # Next page or continue search if search is active
                    if current_search_term:
                        # Continue searching from current position
                        found_line = self.search_in_log(lines, current_search_term, current_line + page_size)
                        if found_line != -1:
                            current_line = found_line - (found_line % page_size)
                            self.show_info(f"Found '{current_search_term}' at line {found_line + 1}")
                            self.pause()
                        else:
                            self.show_error(f"No more matches for '{current_search_term}'")
                    else:
                        # Normal next page
                        if current_line + page_size < len(lines):
                            current_line += page_size
                elif command in ['P', 'PREV', 'PREVIOUS']:
                    # Previous page
                    current_line = max(0, current_line - page_size)
                elif command in ['L', 'LAST']:
                    # Last page
                    total_pages = (len(lines) + page_size - 1) // page_size
                    current_line = (total_pages - 1) * page_size
                elif command in ['G', 'GOTO']:
                    # Go to specific line
                    line_input = self.get_input("Go to line number: ")
                    try:
                        target_line = int(line_input) - 1
                        if 0 <= target_line < len(lines):
                            current_line = target_line - (target_line % page_size)
                        else:
                            self.show_error(f"Line number must be between 1 and {len(lines)}")
                    except ValueError:
                        self.show_error("Invalid line number")
                elif command in ['S', 'SEARCH']:
                    # Search - either new search or continue with current search
                    search_input = self.get_input(f"Search for{' [' + current_search_term + ']' if current_search_term else ''}: ").strip()

                    # If user just presses enter and there's a current search, continue it
                    if not search_input and current_search_term:
                        search_term = current_search_term
                    elif search_input:
                        search_term = search_input
                        current_search_term = search_term  # Store new search term
                    else:
                        continue  # No search term and no current search

                    # Search from next page
                    found_line = self.search_in_log(lines, search_term, current_line + page_size)
                    if found_line != -1:
                        current_line = found_line - (found_line % page_size)
                        self.show_info(f"Found '{search_term}' at line {found_line + 1}")
                        self.pause()
                    else:
                        self.show_error(f"'{search_term}' not found")
                elif command in ['C', 'CLEAR']:
                    # Clear search
                    current_search_term = None
                    self.show_info("Search cleared")
                    self.pause()
                else:
                    self.show_error("Invalid command")

    def show_gateway_status(self):
        """Display gateway status and system information"""
        self.clear_screen()
        print("=== Gateway Status & System Information ===")
        print()

        # Check if gateway is running (simple check for now)
        if os.path.exists('pygate.py'):
            print(" PyGate executable found")
        else:
            print(" PyGate executable not found")

        # Check configuration file
        if os.path.exists('pygate.cfg'):
            print(" Configuration file found")
        else:
            print(" Configuration file not found")

        # Check filter configuration
        if os.path.exists('filter.cfg'):
            print(" Filter configuration found")
        elif os.path.exists('config/filter.cfg'):
            print(" Filter configuration found (config/filter.cfg)")
        else:
            print("  Filter configuration not found (optional)")

        # Check directories
        required_dirs = ['data/inbound', 'data/outbound', 'data/logs', 'data/temp']
        for dir_name in required_dirs:
            if os.path.exists(dir_name):
                print(f" {dir_name}/ directory exists")
            else:
                print(f" {dir_name}/ directory missing")

        # System Information
        print()
        print("=== System Information ===")
        print(f"Python Version: {sys.version.split()[0]}")
        print(f"Platform: {sys.platform}")

        # System uptime
        uptime = self.get_system_uptime()
        print(f"System Uptime: {uptime}")

        # Working directory
        print(f"Working Directory: {os.getcwd()}")

        # Terminal size
        cols, lines = self.get_terminal_size()
        print(f"Terminal Size: {cols}x{lines}")

        # File counts
        try:
            total_files = len(list(Path('.').rglob('*')))
            py_files = len(list(Path('.').rglob('*.py')))
            log_files = len(self.get_log_files())
            print(f"Files: {total_files} total, {py_files} Python, {log_files} logs")
        except Exception:
            print("Files: Unable to count")

        # Display disk space for all mounted filesystems
        print()
        print("=== Disk Space ===")
        try:
            result = subprocess.run(['df', '-h'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                # Print header
                print(lines[0])
                # Print filesystem lines (skip tmpfs and other virtual filesystems)
                for line in lines[1:]:
                    if line and not any(x in line for x in ['tmpfs', 'devtmpfs', 'udev', 'overlay']):
                        print(line)
            else:
                print("Unable to retrieve disk space information")
        except Exception as e:
            print(f"Error getting disk space: {e}")

        print()
        self.pause()

    def run_config_check(self):
        """Run configuration check using ConfigValidator"""
        self.clear_screen()
        print("=== Configuration Check ===")
        print()

        if not self.config:
            self.show_error("Configuration not loaded")
            return

        print("Running configuration check...")
        print()

        try:
            from src.config_validator import ConfigValidator
            import logging

            # Create logger for validator
            logger = logging.getLogger('ConfigCheck')
            logger.setLevel(logging.INFO)

            # Create validator
            validator = ConfigValidator(self.config, logger)

            # Get detailed validation report
            passed, failed = validator.get_validation_report()

            print("--- Configuration Validation Report ---")
            print()

            if passed:
                print("Passed Checks:")
                for check in passed:
                    print(f"  {check}")
                print()

            if failed:
                print("Failed Checks:")
                for check in failed:
                    print(f"  {check}")
                print()

            # Run full check
            success = validator.check_configuration()

            if success:
                print("Configuration check passed")

                # Test NNTP connection
                print()
                print("Testing NNTP connection...")
                try:
                    from src.nntp_module import NNTPModule
                    nntp = NNTPModule(self.config, logger)
                    if nntp.test_connection():
                        print(" NNTP connection test passed")
                    else:
                        print(" NNTP connection test failed")
                except Exception as e:
                    print(f" NNTP connection test error: {e}")
            else:
                print(" Configuration check failed")

        except Exception as e:
            self.show_error(f"Error running configuration check: {e}")

        print()
        self.pause()


    def hold_message_manager(self):
        """Main hold message management interface"""
        if not self.hold_module:
            self.show_error("Hold module not available. Check configuration.")
            return

        while True:
            self.clear_screen()
            print("=== Hold Message Manager ===")
            print()

            # Show statistics
            stats = self.hold_module.get_hold_statistics()
            print(f"Statistics: {stats['pending']} pending, {stats['approved']} approved, {stats['rejected']} rejected")
            print()

            print("1. View Held Messages")
            print("2. Release Held Message")
            print("3. Delete Held Message")
            print("Q. Exit back to Main Menu")
            print()

            choice = self.get_input("Select option: ").upper()

            if choice == '1':
                self.view_held_messages()
            elif choice == '2':
                self.release_held_message()
            elif choice == '3':
                self.delete_held_message()
            elif choice == 'Q':
                break
            else:
                self.show_error("Invalid selection")

    def view_held_messages(self):
        """Display list of held messages"""
        self.clear_screen()
        print("=== Held Messages ===")
        print()

        pending_messages = self.hold_module.get_pending_messages()

        if not pending_messages:
            print("No messages are currently being held for review.")
            self.pause()
            return

        print(f"Found {len(pending_messages)} messages held for review:")
        print()
        print("ID".ljust(8), "    Area".ljust(12), "    From".ljust(20), "    Subject".ljust(25), "    Direction".ljust(8), " Date & Time")
        print("-" * 105)

        for i, msg in enumerate(pending_messages, 1):
            hold_id = msg['hold_id'][:8]
            area = msg['area_tag'][:11]
            from_name = msg['from_name'][:19]
            subject = msg['subject'][:24]
            direction = msg.get('direction', 'unknown')[:7]
            # Show both date and time (first 19 chars: YYYY-MM-DD HH:MM:SS)
            date_time = msg['date'][:19].replace('T', ' ')

            print(f"{i:2d}. {hold_id} {area.ljust(12)} {from_name.ljust(20)} {subject.ljust(25)} {direction.ljust(8)} {date_time}")

        print()
        choice = self.get_input("Enter message number to view details, or Enter to go back: ")

        if choice.isdigit():
            try:
                index = int(choice) - 1
                if 0 <= index < len(pending_messages):
                    self.view_message_details(pending_messages[index])
            except (ValueError, IndexError):
                self.show_error("Invalid message number")

    def view_message_details(self, message: dict):
        """Display detailed view of a held message"""
        self.clear_screen()
        print("=== Message Details ===")
        print()

        print(f"Hold ID: {message['hold_id']}")
        print(f"Area: {message['area_tag']}")
        print(f"Newsgroup: {message['newsgroup']}")
        print(f"From: {message['from_name']}")
        print(f"Subject: {message['subject']}")
        print(f"Date: {message['date']}")
        print(f"Held At: {message['held_at']}")
        print(f"Message ID: {message.get('message_id', 'N/A')}")
        print(f"Direction: {message.get('direction', 'Unknown')} {'(FidoNet→NNTP)' if message.get('direction') == 'nntp' else '(NNTP→FidoNet)' if message.get('direction') == 'fidonet' else ''}")
        print()
        print("Body Preview:")
        print("-" * 40)
        print(message['body_preview'])
        print("-" * 40)
        print()

        while True:
            choice = self.get_input("Actions: [A]pprove, [R]eject, [V]iew full body, [B]ack: ").upper()

            if choice == 'A':
                if self.hold_module.approve_message(message['hold_id']):
                    self.show_success("Message approved successfully")
                    break
                else:
                    self.show_error("Failed to approve message")
            elif choice == 'R':
                reason = self.get_input("Reason for rejection (optional): ")
                if self.hold_module.reject_message(message['hold_id'], reason=reason):
                    self.show_success("Message rejected successfully")
                    break
                else:
                    self.show_error("Failed to reject message")
            elif choice == 'V':
                self.view_full_message_body(message)
            elif choice == 'B':
                break
            else:
                self.show_error("Invalid choice")

    def view_full_message_body(self, message: dict):
        """Display full message body"""
        self.clear_screen()
        print("=== Full Message Body ===")
        print()

        full_message = message.get('full_message', {})
        # Try 'body' first (NNTP messages), then 'text' (FidoNet messages)
        body = full_message.get('body') or full_message.get('text') or 'No body available'

        # Split into lines and display with paging
        lines = body.split('\n')
        page_size = self.get_log_viewer_page_size()
        current_line = 0

        while current_line < len(lines):
            self.clear_screen()
            print("=== Full Message Body ===")
            print(f"Lines {current_line + 1}-{min(current_line + page_size, len(lines))} of {len(lines)}")
            print("-" * 60)

            end_line = min(current_line + page_size, len(lines))
            for i in range(current_line, end_line):
                print(lines[i])

            print("-" * 60)
            if end_line < len(lines):
                choice = self.get_input("Press Enter for next page, B for back, Q to quit: ").upper()
                if choice == 'B':
                    current_line = max(0, current_line - page_size)
                elif choice == 'Q':
                    break
                else:
                    current_line = end_line
            else:
                self.pause("End of message. Press Enter to continue...")
                break

    def release_held_message(self):
        """Release (approve) a held message"""
        self.clear_screen()
        print("=== Release Held Message ===")
        print()

        pending_messages = self.hold_module.get_pending_messages()

        if not pending_messages:
            print("No messages are currently being held.")
            self.pause()
            return

        print("Messages available for release:")
        print()
        print("ID".ljust(8), "Area".ljust(12), "From".ljust(20), "Subject")
        print("-" * 60)

        for i, msg in enumerate(pending_messages, 1):
            hold_id = msg['hold_id'][:8]
            area = msg['area_tag'][:11]
            from_name = msg['from_name'][:19]
            subject = msg['subject'][:30]

            print(f"{i:2d}. {hold_id} {area.ljust(12)} {from_name.ljust(20)} {subject}")

        print()
        choice = self.get_input("Enter message number to release (or Enter to cancel): ")

        if choice.isdigit():
            try:
                index = int(choice) - 1
                if 0 <= index < len(pending_messages):
                    message = pending_messages[index]
                    confirm = self.get_input(f"Release message '{message['subject']}'? (y/N): ").upper()
                    if confirm == 'Y':
                        if self.hold_module.approve_message(message['hold_id']):
                            self.show_success("Message released successfully")
                        else:
                            self.show_error("Failed to release message")
                else:
                    self.show_error("Invalid message number")
            except (ValueError, IndexError):
                self.show_error("Invalid input")

    def delete_held_message(self):
        """Delete (reject) a held message"""
        self.clear_screen()
        print("=== Delete Held Message ===")
        print()

        pending_messages = self.hold_module.get_pending_messages()

        if not pending_messages:
            print("No messages are currently being held.")
            self.pause()
            return

        print("Messages available for deletion:")
        print()
        print("ID".ljust(8), "Area".ljust(12), "From".ljust(20), "Subject")
        print("-" * 60)

        for i, msg in enumerate(pending_messages, 1):
            hold_id = msg['hold_id'][:8]
            area = msg['area_tag'][:11]
            from_name = msg['from_name'][:19]
            subject = msg['subject'][:30]

            print(f"{i:2d}. {hold_id} {area.ljust(12)} {from_name.ljust(20)} {subject}")

        print()
        choice = self.get_input("Enter message number to delete (or Enter to cancel): ")

        if choice.isdigit():
            try:
                index = int(choice) - 1
                if 0 <= index < len(pending_messages):
                    message = pending_messages[index]
                    reason = self.get_input("Reason for deletion (optional): ")
                    confirm = self.get_input(f"Delete message '{message['subject']}'? (y/N): ").upper()
                    if confirm == 'Y':
                        if self.hold_module.reject_message(message['hold_id'], reason=reason):
                            self.show_success("Message deleted successfully")
                        else:
                            self.show_error("Failed to delete message")
                else:
                    self.show_error("Invalid message number")
            except (ValueError, IndexError):
                self.show_error("Invalid input")

    def run(self):
        """Main loop for the admin panel"""
        while self.running:
            self.clear_screen()
            self.show_header()
            self.show_main_menu()

            choice = self.get_input("Select option (1-6, Q): ")

            if choice == '1':
                self.run_filter_manager()
            elif choice == '2':
                self.log_viewer()
            elif choice == '3':
                self.show_gateway_status()
            elif choice == '4':
                self.run_config_check()
            elif choice == '5':
                self.hold_message_manager()
            elif choice == '6':
                self.newsrc_manager()
            elif choice.upper() == 'Q':
                print("\nGoodbye!")
                self.running = False
            else:
                self.show_error("Invalid selection")

    def execute_ctlinnd(self, command: str, newsgroup: str) -> tuple[bool, str]:
        """Execute ctlinnd command either locally or via SSH"""
        try:
            if not self.config:
                return False, "Configuration not loaded"

            # Check if SSH is enabled
            ssh_enabled = self.config.getboolean('SSH', 'enabled', fallback=False)

            if ssh_enabled:
                return self.execute_ctlinnd_ssh(command, newsgroup)
            else:
                return self.execute_ctlinnd_local(command, newsgroup)

        except Exception as e:
            return False, str(e)

    def execute_ctlinnd_local(self, command: str, newsgroup: str) -> tuple[bool, str]:
        """Execute ctlinnd command locally"""
        try:
            if not self.config.has_option('NNTP', 'ctlinndpath'):
                return False, "ctlinndpath not configured in [NNTP] section"

            ctlinnd_path = self.config.get('NNTP', 'ctlinndpath')
            if not os.path.exists(ctlinnd_path):
                return False, f"ctlinnd not found at: {ctlinnd_path}"

            result = subprocess.run([ctlinnd_path, command, newsgroup],
                                  capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr

        except subprocess.TimeoutExpired:
            return False, "ctlinnd command timed out"
        except Exception as e:
            return False, str(e)

    def execute_ctlinnd_ssh(self, command: str, newsgroup: str) -> tuple[bool, str]:
        """Execute ctlinnd command via SSH"""
        try:
            # Import paramiko here to make it optional
            try:
                import paramiko
            except ImportError:
                return False, "paramiko module required for SSH functionality. Install with: pip install paramiko"

            # Get SSH configuration
            hostname = self.config.get('SSH', 'hostname', fallback='')
            port = self.config.getint('SSH', 'port', fallback=22)
            username = self.config.get('SSH', 'username', fallback='')
            keyfile = self.config.get('SSH', 'keyfile', fallback='')
            password = self.config.get('SSH', 'password', fallback='')
            remote_ctlinnd_path = self.config.get('SSH', 'remote_ctlinnd_path', fallback='/usr/lib/news/bin/ctlinnd')

            if not hostname or not username:
                return False, "SSH hostname and username must be configured"

            # Create SSH client
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Connect
            if keyfile and os.path.exists(keyfile):
                ssh.connect(hostname, port=port, username=username, key_filename=keyfile, timeout=10)
            elif password:
                ssh.connect(hostname, port=port, username=username, password=password, timeout=10)
            else:
                return False, "SSH keyfile or password must be provided"

            # Execute command
            command_str = f"{remote_ctlinnd_path} {command} {newsgroup}"
            stdin, stdout, stderr = ssh.exec_command(command_str, timeout=30)

            # Get results
            stdout_data = stdout.read().decode()
            stderr_data = stderr.read().decode()
            exit_status = stdout.channel.recv_exit_status()

            ssh.close()

            if exit_status == 0:
                return True, stdout_data
            else:
                return False, stderr_data

        except Exception as e:
            return False, str(e)

    def newsrc_manager(self):
        """Newsrc file management interface"""
        while True:
            self.clear_screen()
            self.show_header()
            print("Newsgroup Manager")
            print("=" * 50)
            print()

            # Check if newsrc file exists
            newsrc_file = "newsrc"
            if self.config and self.config.has_option('Files', 'areas_file'):
                newsrc_file = self.config.get('Files', 'areas_file')

            if os.path.exists(newsrc_file):
                # Count entries
                entries_count = 0
                try:
                    with open(newsrc_file, 'r') as f:
                        for line in f:
                            if ':' in line.strip() and not line.strip().startswith('#'):
                                entries_count += 1
                    print(f"Current newsrc file: {newsrc_file}")
                    print(f"Newsgroup entries: {entries_count}")
                    print()
                except Exception as e:
                    print(f"Error reading newsrc file: {e}")
                    print()
            else:
                print(f"Newsrc file not found: {newsrc_file}")
                print()

            print("1. Sort newsrc file alphabetically")
            print("2. View newsrc file (Gated Newsgroups)")
            print("3. View newsgroups file (Available Groups)")
            print("4. Backup newsrc file")
            print("5. Restore from backup")
            print("6. Add newsgroup entry")
            print("7. Delete newsgroup entry")
            print("Q. Back to main menu")
            print()

            choice = self.get_input("Select option (1-7, Q): ").upper()

            if choice == '1':
                self.sort_newsrc_file(newsrc_file)
            elif choice == '2':
                self.view_newsrc_file(newsrc_file)
            elif choice == '3':
                self.view_newsgroups_file()
            elif choice == '4':
                self.backup_newsrc_file(newsrc_file)
            elif choice == '5':
                self.restore_newsrc_file(newsrc_file)
            elif choice == '6':
                self.add_newsgroup_entry(newsrc_file)
            elif choice == '7':
                self.delete_newsgroup_entry(newsrc_file)
            elif choice == 'Q':
                break
            else:
                self.show_error("Invalid selection")

    def sort_newsrc_file(self, newsrc_file):
        """Sort newsrc file alphabetically"""
        self.clear_screen()
        self.show_header()
        print("Sort Newsrc File")
        print("=" * 50)
        print()

        if not os.path.exists(newsrc_file):
            self.show_error(f"Newsrc file not found: {newsrc_file}")
            return

        try:
            # Create backup first
            backup_file = f"{newsrc_file}.bak"
            shutil.copy2(newsrc_file, backup_file)
            print(f"Backup created: {backup_file}")

            # Read and sort the file
            entries = []
            comments = []

            with open(newsrc_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith('#'):
                        comments.append(line)
                        continue
                    if ':' in line:
                        entries.append(line)
                    else:
                        comments.append(line)

            # Sort entries alphabetically
            entries.sort(key=lambda x: x.split(':')[0].strip().lower())

            # Write sorted output
            with open(newsrc_file, 'w') as f:
                for comment in comments:
                    f.write(comment + '\n')
                if comments:
                    f.write('\n')
                for entry in entries:
                    f.write(entry + '\n')

            print(f" Successfully sorted {len(entries)} newsgroup entries")
            print(f" Sorted file: {newsrc_file}")
            print(f" Backup saved: {backup_file}")

        except Exception as e:
            self.show_error(f"Failed to sort newsrc file: {e}")

        self.pause()

    def view_newsrc_file(self, newsrc_file):
        """View newsrc file contents with paging support"""
        if not os.path.exists(newsrc_file):
            self.clear_screen()
            self.show_header()
            print("View Newsrc File")
            print("=" * 50)
            print()
            self.show_error(f"Newsrc file not found: {newsrc_file}")
            return

        try:
            with open(newsrc_file, 'r') as f:
                lines = f.readlines()

            if not lines:
                self.clear_screen()
                self.show_header()
                print("View Newsrc File")
                print("=" * 50)
                print()
                print(" File is empty")
                self.pause()
                return

            # Get configurable page size
            lines_per_page = 30  # default
            if self.config and self.config.has_option('Files', 'newsgrouppagesize'):
                try:
                    lines_per_page = self.config.getint('Files', 'newsgrouppagesize')
                except ValueError:
                    lines_per_page = 30  # fallback to default
            current_page = 0
            total_pages = (len(lines) + lines_per_page - 1) // lines_per_page
            current_search_term = None  # Track current search term for highlighting

            while True:
                self.clear_screen()
                self.show_header()
                print("View Newsrc File")
                print("=" * 50)
                print()

                # Calculate start and end line numbers for current page
                start_line = current_page * lines_per_page
                end_line = min(start_line + lines_per_page, len(lines))

                # Show page info
                print(f" Contents of {newsrc_file}")
                print(f" Page {current_page + 1} of {total_pages} (Lines {start_line + 1}-{end_line} of {len(lines)})")
                if current_search_term:
                    print(f" Searching for: '{current_search_term}' (> marks matches)")
                print("-" * 70)

                # Display lines for current page
                for i in range(start_line, end_line):
                    line_num = i + 1
                    line_content = lines[i].rstrip()

                    # Check if this line matches current search
                    search_match = False
                    if current_search_term and ':' in line_content and not line_content.startswith('#'):
                        newsgroup = line_content.split(':', 1)[0].strip().lower()
                        if current_search_term in newsgroup:
                            search_match = True

                    # Determine prefix (normal space or search indicator)
                    prefix = " >" if search_match else "  "

                    # Highlight different types of lines
                    if line_content.startswith('#'):
                        print(f"{line_num:4}:{prefix}{line_content}")  # Comments
                    elif ':' in line_content:
                        # Parse newsgroup entry
                        parts = line_content.split(':', 1)
                        if len(parts) == 2:
                            newsgroup = parts[0].strip()
                            watermarks = parts[1].strip()
                            print(f"{line_num:4}:{prefix}{newsgroup:<39} {watermarks}")
                        else:
                            print(f"{line_num:4}:{prefix}{line_content}")
                    elif line_content.strip():
                        print(f"{line_num:4}:{prefix}{line_content}")  # Other non-empty lines
                    else:
                        print(f"{line_num:4}:{prefix}")  # Empty lines

                print("-" * 70)

                # Show navigation options on two lines
                line1 = []
                line2 = []

                if current_page > 0:
                    line1.append("P. Previous page")
                if current_page < total_pages - 1:
                    line1.append("N. Next page")

                line1.extend(["F. First page", "L. Last page"])
                line2.extend(["G. Go to page", "S. Search"])

                if current_search_term:
                    line2.append("C. Clear search")

                line2.append("Q. Back to newsrc menu")

                print(" | ".join(line1))
                print(" | ".join(line2))
                print()

                # Get user input
                choice = self.get_input("Navigation: ").upper().strip()

                if choice == 'Q':
                    break
                elif choice == 'N' and current_page < total_pages - 1:
                    current_page += 1
                elif choice == 'P' and current_page > 0:
                    current_page -= 1
                elif choice == 'F':
                    current_page = 0
                elif choice == 'L':
                    current_page = total_pages - 1
                elif choice == 'G':
                    page_input = self.get_input(f"Go to page (1-{total_pages}): ").strip()
                    try:
                        target_page = int(page_input)
                        if 1 <= target_page <= total_pages:
                            current_page = target_page - 1
                        else:
                            self.show_error(f"Invalid page number. Must be 1-{total_pages}")
                    except ValueError:
                        self.show_error("Invalid page number")
                elif choice in ['S', 'SEARCH']:
                    search_term = self.get_input("Search for (newsgroup name): ").strip().lower()
                    if search_term:
                        found_page = self.search_newsrc_content(lines, search_term, lines_per_page)
                        if found_page is not None:
                            current_search_term = search_term  # Store search term for highlighting
                            current_page = found_page
                        else:
                            self.show_error(f"'{search_term}' not found")
                elif choice in ['C', 'CLEAR']:
                    current_search_term = None  # Clear search highlighting
                else:
                    self.show_error("Invalid command")

        except Exception as e:
            self.clear_screen()
            self.show_header()
            print("View Newsrc File")
            print("=" * 50)
            print()
            self.show_error(f"Failed to read newsrc file: {e}")

    def search_newsrc_content(self, lines, search_term, lines_per_page):
        """Search for a newsgroup name in newsrc content and return the page number"""
        for i, line in enumerate(lines):
            line_content = line.strip()
            # Only search in newsgroup lines (lines with ':' that aren't comments)
            if ':' in line_content and not line_content.startswith('#'):
                newsgroup = line_content.split(':', 1)[0].strip().lower()
                if search_term in newsgroup:
                    return i // lines_per_page
        return None

    def view_newsgroups_file(self):
        """View newsgroups file contents with configurable paging support"""
        # Get newsgroups file path from config
        newsgroups_file = "newsgroups"
        if self.config and self.config.has_option('Files', 'newsgrouplist'):
            newsgroups_file = self.config.get('Files', 'newsgrouplist')

        if not os.path.exists(newsgroups_file):
            self.clear_screen()
            self.show_header()
            print("View Newsgroups File")
            print("=" * 50)
            print()
            self.show_error(f"Newsgroups file not found: {newsgroups_file}")
            return

        try:
            with open(newsgroups_file, 'r') as f:
                lines = f.readlines()

            if not lines:
                self.clear_screen()
                self.show_header()
                print("View Newsgroups File")
                print("=" * 50)
                print()
                print(" File is empty")
                self.pause()
                return

            # Get configurable page size
            lines_per_page = 40  # default
            if self.config and self.config.has_option('Files', 'newsgrouppagesize'):
                try:
                    lines_per_page = self.config.getint('Files', 'newsgrouppagesize')
                except ValueError:
                    lines_per_page = 40  # fallback to default

            current_page = 0
            total_pages = (len(lines) + lines_per_page - 1) // lines_per_page
            current_search_term = None  # Track current search term for highlighting
            search_matches = []  # List of line numbers that match search
            current_match_index = 0  # Current position in search matches

            while True:
                self.clear_screen()
                self.show_header()
                print("View Newsgroups File")
                print("=" * 50)
                print()

                # Calculate start and end line numbers for current page
                start_line = current_page * lines_per_page
                end_line = min(start_line + lines_per_page, len(lines))

                # Show page info
                print(f" File: {newsgroups_file}")
                print(f" Total lines: {len(lines):,} | Page {current_page + 1} of {total_pages} | Lines {start_line + 1}-{end_line}")
                if current_search_term and search_matches:
                    print(f"🔍 Searching for: '{current_search_term}' | Match {current_match_index + 1} of {len(search_matches)} (> marks matches)")
                elif current_search_term:
                    print(f"🔍 Searching for: '{current_search_term}' (> marks matches)")
                print()

                # Display lines for current page
                for i in range(start_line, end_line):
                    line_content = lines[i].rstrip()
                    line_number = f"{i + 1:6d}: "

                    # Highlight search matches
                    if current_search_term and current_search_term.lower() in line_content.lower():
                        print(f"{line_number}> {line_content}")
                    else:
                        print(f"{line_number}  {line_content}")

                print()
                # Show navigation menu on two lines
                if current_page > 0 and current_page < total_pages - 1:
                    print("N. Next page | P. Previous page | F. First page | L. Last page")
                elif current_page > 0:
                    print("P. Previous page | F. First page | L. Last page")
                elif current_page < total_pages - 1:
                    print("N. Next page | F. First page | L. Last page")
                else:
                    print("F. First page | L. Last page")

                if search_matches:
                    print("G. Go to page | S. Search | >. Next match | <. Prev match | C. Clear search | Q. Back to newsrc menu")
                else:
                    print("G. Go to page | S. Search | C. Clear search | Q. Back to newsrc menu")

                choice = self.get_input("Command: ").upper().strip()

                if choice in ['Q', 'QUIT', 'EXIT']:
                    break
                elif choice in ['N', 'NEXT']:
                    if current_page < total_pages - 1:
                        current_page += 1
                elif choice in ['P', 'PREV', 'PREVIOUS']:
                    if current_page > 0:
                        current_page -= 1
                elif choice in ['F', 'FIRST']:
                    current_page = 0
                elif choice in ['L', 'LAST']:
                    current_page = total_pages - 1
                elif choice in ['G', 'GOTO']:
                    page_input = self.get_input(f"Go to page (1-{total_pages}): ")
                    try:
                        target_page = int(page_input) - 1
                        if 0 <= target_page < total_pages:
                            current_page = target_page
                        else:
                            self.show_error(f"Page must be between 1 and {total_pages}")
                    except ValueError:
                        self.show_error("Invalid page number")
                elif choice in ['S', 'SEARCH']:
                    search_term = self.get_input("Search for newsgroup: ").strip()
                    if search_term:
                        search_matches = self.search_newsgroups_content(lines, search_term, lines_per_page)
                        if search_matches:
                            current_search_term = search_term
                            current_match_index = 0
                            # Go to page containing first match
                            current_page = search_matches[0] // lines_per_page
                        else:
                            self.show_error(f"'{search_term}' not found")
                elif choice in ['>', 'NEXT_MATCH', 'NEXTMATCH']:
                    if search_matches and len(search_matches) > 1:
                        current_match_index = (current_match_index + 1) % len(search_matches)
                        # Go to page containing current match
                        current_page = search_matches[current_match_index] // lines_per_page
                    elif not search_matches:
                        self.show_error("No active search. Use S to search first.")
                elif choice in ['<', 'PREV_MATCH', 'PREVMATCH']:
                    if search_matches and len(search_matches) > 1:
                        current_match_index = (current_match_index - 1) % len(search_matches)
                        # Go to page containing current match
                        current_page = search_matches[current_match_index] // lines_per_page
                    elif not search_matches:
                        self.show_error("No active search. Use S to search first.")
                elif choice in ['C', 'CLEAR']:
                    current_search_term = None
                    search_matches = []
                    current_match_index = 0
                else:
                    self.show_error("Invalid command")

        except Exception as e:
            self.clear_screen()
            self.show_header()
            print("View Newsgroups File")
            print("=" * 50)
            print()
            self.show_error(f"Error reading newsgroups file: {e}")

    def search_newsgroups_content(self, lines, search_term, lines_per_page):
        """Search for a term in newsgroups lines and return all matching line numbers"""
        search_term = search_term.lower()
        matches = []
        for i, line in enumerate(lines):
            line_content = line.strip().lower()
            if search_term in line_content:
                matches.append(i)
        return matches

    def backup_newsrc_file(self, newsrc_file):
        """Create a timestamped backup of newsrc file"""
        self.clear_screen()
        self.show_header()
        print("Backup Newsrc File")
        print("=" * 50)
        print()

        if not os.path.exists(newsrc_file):
            self.show_error(f"Newsrc file not found: {newsrc_file}")
            return

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"{newsrc_file}.backup_{timestamp}"
            shutil.copy2(newsrc_file, backup_file)

            file_size = os.path.getsize(backup_file)
            print(f" Backup created successfully!")
            print(f" Source: {newsrc_file}")
            print(f" Backup: {backup_file}")
            print(f" Size: {file_size} bytes")

        except Exception as e:
            self.show_error(f"Failed to create backup: {e}")

        self.pause()

    def restore_newsrc_file(self, newsrc_file):
        """Restore newsrc file from backup"""
        self.clear_screen()
        self.show_header()
        print("Restore Newsrc File")
        print("=" * 50)
        print()

        # Find available backups
        backup_pattern = f"{newsrc_file}.backup_*"
        backup_files = glob.glob(backup_pattern)

        # Also check for .bak file
        bak_file = f"{newsrc_file}.bak"
        if os.path.exists(bak_file):
            backup_files.append(bak_file)

        if not backup_files:
            self.show_error("No backup files found")
            return

        backup_files.sort(reverse=True)  # Most recent first

        print("Available backup files:")
        print()
        for i, backup in enumerate(backup_files[:10], 1):  # Show max 10 backups
            try:
                stat = os.stat(backup)
                size = stat.st_size
                mtime = datetime.fromtimestamp(stat.st_mtime)
                print(f"{i}. {backup}")
                print(f"    Modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"    Size: {size} bytes")
                print()
            except Exception:
                print(f"{i}. {backup} (unable to read stats)")

        print("C. Cancel")
        print()

        choice = self.get_input(f"Select backup to restore (1-{min(len(backup_files), 10)}, C): ").upper()

        if choice == 'C':
            return

        try:
            backup_index = int(choice) - 1
            if 0 <= backup_index < len(backup_files):
                selected_backup = backup_files[backup_index]

                # Confirm restoration
                print()
                print(f" This will replace the current {newsrc_file}")
                print(f" Source backup: {selected_backup}")
                confirm = self.get_input("Are you sure? (y/N): ").lower()

                if confirm == 'y':
                    # Create backup of current file first
                    current_backup = f"{newsrc_file}.before_restore"
                    if os.path.exists(newsrc_file):
                        shutil.copy2(newsrc_file, current_backup)
                        print(f" Current file backed up to: {current_backup}")

                    # Restore from backup
                    shutil.copy2(selected_backup, newsrc_file)
                    print(f" Successfully restored {newsrc_file} from backup")
                else:
                    print(" Restore cancelled")
            else:
                self.show_error("Invalid backup selection")
        except ValueError:
            self.show_error("Invalid selection")
        except Exception as e:
            self.show_error(f"Failed to restore backup: {e}")

        self.pause()

    def add_newsgroup_entry(self, newsrc_file):
        """Add a new newsgroup entry to newsrc file"""
        self.clear_screen()
        self.show_header()
        print("Add Newsgroup Entry")
        print("=" * 50)
        print()

        print("Enter the newsgroup name and initial water marks.")
        print("Format: newsgroup.name: low-high")
        print("Example: comp.lang.python: 0-0")
        print()

        # Get newsgroup name
        newsgroup = self.get_input("Newsgroup name: ").strip()
        if not newsgroup:
            self.show_error("Newsgroup name cannot be empty")
            return

        # Validate newsgroup name format
        if not re.match(r'^[a-zA-Z0-9._-]+$', newsgroup):
            self.show_error("Invalid newsgroup name. Use only letters, numbers, dots, hyphens, and underscores.")
            return

        # Get low water mark
        low_mark = self.get_input("Low water mark (default: 0): ").strip()
        if not low_mark:
            low_mark = "0"

        try:
            low_num = int(low_mark)
            if low_num < 0:
                raise ValueError("Water mark must be non-negative")
        except ValueError:
            self.show_error("Low water mark must be a non-negative integer")
            return

        # Get high water mark
        high_mark = self.get_input("High water mark (default: 1): ").strip()
        if not high_mark:
            high_mark = "1"

        try:
            high_num = int(high_mark)
            if high_num < low_num:
                raise ValueError("High water mark must be >= low water mark")
        except ValueError:
            self.show_error("High water mark must be >= low water mark and be an integer")
            return

        # Check if newsgroup already exists
        if os.path.exists(newsrc_file):
            try:
                with open(newsrc_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if ':' in line and not line.startswith('#'):
                            existing_group = line.split(':')[0].strip()
                            if existing_group.lower() == newsgroup.lower():
                                self.show_error(f"Newsgroup '{newsgroup}' already exists in newsrc file")
                                return
            except Exception as e:
                self.show_error(f"Error checking existing entries: {e}")
                return

        # Create the new entry
        new_entry = f"{newsgroup}: {low_num}-{high_num}"

        # Show preview and confirm
        print()
        print("New entry to add:")
        print(f"  {new_entry}")
        print()
        confirm = self.get_input("Add this entry? (y/N): ").lower()

        if confirm != 'y':
            print(" Entry not added")
            self.pause()
            return

        try:
            # Create backup first
            if os.path.exists(newsrc_file):
                backup_file = f"{newsrc_file}.bak"
                shutil.copy2(newsrc_file, backup_file)
                print(f" Backup created: {backup_file}")

            # Read existing entries
            entries = []
            comments = []

            if os.path.exists(newsrc_file):
                with open(newsrc_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith('#'):
                            comments.append(line)
                            continue
                        if ':' in line:
                            entries.append(line)
                        else:
                            comments.append(line)

            # Add new entry
            entries.append(new_entry)

            # Sort entries alphabetically
            entries.sort(key=lambda x: x.split(':')[0].strip().lower())

            # Write updated file
            with open(newsrc_file, 'w') as f:
                for comment in comments:
                    f.write(comment + '\n')
                if comments:
                    f.write('\n')
                for entry in entries:
                    f.write(entry + '\n')

            print(f" Successfully added newsgroup '{newsgroup}' to newsrc file")
            print(f" Updated file: {newsrc_file}")
            print(f" Total entries: {len(entries)}")

            # Check if running in client-only mode
            client_mode = self.config.getboolean('Gateway', 'client_mode', fallback=False)

            if client_mode:
                # Client mode: only update newsrc, skip server modification
                print()
                print("  Running in client mode - newsrc updated, server not modified")
                print(f" Newsgroup '{newsgroup}' added to newsrc")
            else:
                # Add to NNTP server using ctlinnd
                print()
                print("Adding newsgroup to NNTP server...")
                ctlinnd_success, ctlinnd_output = self.execute_ctlinnd('newgroup', newsgroup)

                if ctlinnd_success:
                    print(f" Successfully added newsgroup '{newsgroup}' to NNTP server")
                    if ctlinnd_output.strip():
                        print(f" Server response: {ctlinnd_output.strip()}")
                else:
                    print(f" Failed to add newsgroup '{newsgroup}' to NNTP server")
                    print(f" Error: {ctlinnd_output}")
                    print()
                    print("  The newsgroup has been added to newsrc but not to the NNTP server.")
                    print("You may need to manually run ctlinnd or check your configuration.")

                    # Ask if user wants to remove from newsrc due to ctlinnd failure
                    rollback = self.get_input("Remove from newsrc file due to server error? (y/N): ").lower()
                    if rollback == 'y':
                        try:
                            # Restore from backup
                            if os.path.exists(backup_file):
                                shutil.copy2(backup_file, newsrc_file)
                                print(f" Rolled back newsrc file from backup")
                            else:
                                # Manual removal
                                entries.remove(new_entry)
                                with open(newsrc_file, 'w') as f:
                                    for comment in comments:
                                        f.write(comment + '\n')
                                    if comments:
                                        f.write('\n')
                                    for entry in entries:
                                        f.write(entry + '\n')
                                print(f" Removed '{newsgroup}' from newsrc file")
                        except Exception as rollback_error:
                            print(f" Failed to rollback: {rollback_error}")

        except Exception as e:
            self.show_error(f"Failed to add newsgroup entry: {e}")

        self.pause()

    def delete_newsgroup_entry(self, newsrc_file):
        """Delete a newsgroup entry from newsrc file"""
        self.clear_screen()
        self.show_header()
        print("Delete Newsgroup Entry")
        print("=" * 50)
        print()

        if not os.path.exists(newsrc_file):
            self.show_error(f"Newsrc file not found: {newsrc_file}")
            return

        try:
            # Read existing entries
            entries = []
            comments = []

            with open(newsrc_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith('#'):
                        comments.append(line)
                        continue
                    if ':' in line:
                        entries.append(line)
                    else:
                        comments.append(line)

            if not entries:
                self.show_error("No newsgroup entries found in file")
                return

            # Display entries with numbers
            print(f"Current newsgroup entries ({len(entries)} total):")
            print()
            for i, entry in enumerate(entries, 1):
                newsgroup = entry.split(':')[0].strip()
                water_marks = entry.split(':', 1)[1].strip()
                print(f"{i:3}. {newsgroup:<40} {water_marks}")

            print()
            print("Enter newsgroup number to delete, or newsgroup name, or 'C' to cancel")
            choice = self.get_input("Selection: ").strip()

            if choice.upper() == 'C':
                return

            # Try to parse as number first
            selected_entry = None
            selected_index = None

            try:
                entry_num = int(choice)
                if 1 <= entry_num <= len(entries):
                    selected_index = entry_num - 1
                    selected_entry = entries[selected_index]
                else:
                    self.show_error(f"Invalid entry number. Must be 1-{len(entries)}")
                    return
            except ValueError:
                # Not a number, try to match by newsgroup name
                choice_lower = choice.lower()
                for i, entry in enumerate(entries):
                    newsgroup = entry.split(':')[0].strip().lower()
                    if newsgroup == choice_lower or newsgroup.endswith('.' + choice_lower) or choice_lower in newsgroup:
                        if selected_entry is None:
                            selected_entry = entry
                            selected_index = i
                        else:
                            # Multiple matches found
                            print()
                            print("Multiple matches found:")
                            matches = []
                            for j, e in enumerate(entries):
                                ng = e.split(':')[0].strip().lower()
                                if ng == choice_lower or ng.endswith('.' + choice_lower) or choice_lower in ng:
                                    matches.append((j, e))
                                    print(f"{j+1}. {e}")

                            print()
                            match_choice = self.get_input(f"Select specific entry (1-{len(entries)}): ").strip()
                            try:
                                match_num = int(match_choice)
                                if 1 <= match_num <= len(entries):
                                    selected_index = match_num - 1
                                    selected_entry = entries[selected_index]
                                else:
                                    self.show_error(f"Invalid selection")
                                    return
                            except ValueError:
                                self.show_error("Invalid selection")
                                return
                            break

                if selected_entry is None:
                    self.show_error(f"No newsgroup matching '{choice}' found")
                    return

            # Show selected entry and confirm deletion
            newsgroup_name = selected_entry.split(':')[0].strip()
            print()
            print(f"Selected entry to delete:")
            print(f"  {selected_entry}")
            print()
            print(f"  This will permanently remove '{newsgroup_name}' from the newsrc file")
            confirm = self.get_input("Are you sure? (y/N): ").lower()

            if confirm != 'y':
                print(" Deletion cancelled")
                self.pause()
                return

            # Create backup first
            backup_file = f"{newsrc_file}.bak"
            shutil.copy2(newsrc_file, backup_file)
            print(f" Backup created: {backup_file}")

            # Remove the selected entry
            entries.pop(selected_index)

            # Write updated file
            with open(newsrc_file, 'w') as f:
                for comment in comments:
                    f.write(comment + '\n')
                if comments and entries:
                    f.write('\n')
                for entry in entries:
                    f.write(entry + '\n')

            print(f" Successfully deleted newsgroup '{newsgroup_name}' from newsrc file")
            print(f" Updated file: {newsrc_file}")
            print(f" Remaining entries: {len(entries)}")

            # Check if running in client-only mode
            client_mode = self.config.getboolean('Gateway', 'client_mode', fallback=False)

            if client_mode:
                # Client mode: only update newsrc, skip server modification
                print()
                print("  Running in client mode - newsrc updated, server not modified")
                print(f" Newsgroup '{newsgroup_name}' removed from newsrc")
            else:
                # Remove from NNTP server using ctlinnd
                print()
                print("Removing newsgroup from NNTP server...")
                ctlinnd_success, ctlinnd_output = self.execute_ctlinnd('rmgroup', newsgroup_name)

                if ctlinnd_success:
                    print(f" Successfully removed newsgroup '{newsgroup_name}' from NNTP server")
                    if ctlinnd_output.strip():
                        print(f" Server response: {ctlinnd_output.strip()}")
                else:
                    print(f" Failed to remove newsgroup '{newsgroup_name}' from NNTP server")
                    print(f" Error: {ctlinnd_output}")
                    print()
                print("  The newsgroup has been removed from newsrc but not from the NNTP server.")
                print("You may need to manually run ctlinnd or check your configuration.")

                # Ask if user wants to restore to newsrc due to ctlinnd failure
                restore = self.get_input("Restore to newsrc file due to server error? (y/N): ").lower()
                if restore == 'y':
                    try:
                        # Restore from backup
                        if os.path.exists(backup_file):
                            shutil.copy2(backup_file, newsrc_file)
                            print(f" Restored newsrc file from backup")
                        else:
                            # Manual re-addition
                            entries.insert(selected_index, selected_entry)
                            entries.sort(key=lambda x: x.split(':')[0].strip().lower())
                            with open(newsrc_file, 'w') as f:
                                for comment in comments:
                                    f.write(comment + '\n')
                                if comments and entries:
                                    f.write('\n')
                                for entry in entries:
                                    f.write(entry + '\n')
                            print(f" Restored '{newsgroup_name}' to newsrc file")
                    except Exception as restore_error:
                        print(f" Failed to restore: {restore_error}")

        except Exception as e:
            self.show_error(f"Failed to delete newsgroup entry: {e}")

        self.pause()


def main():
    """Entry point for admin panel"""
    try:
        panel = AdminPanel()
        panel.run()
    except KeyboardInterrupt:
        print("\n\nExiting admin panel...")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
