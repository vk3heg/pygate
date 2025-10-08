#!/usr/bin/env python3
"""
PyGate Filter Configuration Manager

A tool to help create and update filter.cfg rules by connecting to news servers,
retrieving specific messages, and interactively selecting fields for filtering.

Usage:
    python filter_manager.py

Author: Generated for PyGate NNTP-FidoNet Gateway
"""

import configparser
import re
import sys
import os
from typing import Dict, List, Optional, Tuple
import email
import email.header
from email.message import Message
from datetime import datetime, timedelta
import time
import shutil

# Use custom NNTP client instead of deprecated nntplib
try:
    from nntp_client import CustomNNTPClient, CustomNNTP_SSL, NNTPError
    # Create compatibility aliases
    nntplib_NNTP = CustomNNTPClient
    nntplib_NNTP_SSL = CustomNNTP_SSL
    nntplib_NNTPError = NNTPError
except ImportError:
    # Fallback to nntplib if custom client not available
    import nntplib
    nntplib_NNTP = nntplib.NNTP
    nntplib_NNTP_SSL = nntplib.NNTP_SSL
    nntplib_NNTPError = nntplib.NNTPError


class FilterManager:
    """Manages filter.cfg updates by analyzing NNTP messages."""

    def __init__(self, config_file: str = "pygate.cfg"):
        """Initialize the filter manager with configuration."""
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.nntp_conn = None
        self.load_config()

    def load_config(self) -> None:
        """Load configuration from pygate.cfg."""
        try:
            self.config.read(self.config_file)
            if 'NNTP' not in self.config:
                raise ValueError("NNTP section not found in config file")
        except Exception as e:
            print(f"Error loading config: {e}")
            sys.exit(1)

    def connect_to_server(self) -> bool:
        """Connect to the NNTP server using configuration settings."""
        try:
            nntp_config = self.config['NNTP']
            host = nntp_config.get('host')
            port = int(nntp_config.get('port', 119))
            username = nntp_config.get('username')
            password = nntp_config.get('password')
            use_ssl = nntp_config.getboolean('use_ssl', False)
            timeout = int(nntp_config.get('timeout', 30))

            print(f"Connecting to {host}:{port}...")

            if use_ssl:
                self.nntp_conn = nntplib_NNTP_SSL(host, port=port, timeout=timeout)
                self.nntp_conn.connect()
            else:
                self.nntp_conn = nntplib_NNTP(host, port=port, timeout=timeout)
                self.nntp_conn.connect()

            if username and password:
                self.nntp_conn.login(username, password)
                print("Authentication successful")

            print("Connected successfully!")
            return True

        except Exception as e:
            print(f"Failed to connect to NNTP server: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from the NNTP server."""
        if self.nntp_conn:
            try:
                self.nntp_conn.quit()
            except:
                pass
            self.nntp_conn = None

    def normalize_message_id(self, message_id: str) -> str:
        """Normalize message ID format for NNTP retrieval."""
        message_id = message_id.strip()

        # If it's a numeric article number, return as-is
        if message_id.isdigit():
            return message_id

        # If it looks like a Message-ID but missing angle brackets, add them
        if '@' in message_id and not message_id.startswith('<'):
            return f"<{message_id}>"

        # If it already has angle brackets, return as-is
        if message_id.startswith('<') and message_id.endswith('>'):
            return message_id

        # Otherwise return as-is and let NNTP server handle it
        return message_id

    def get_message(self, newsgroup: str, message_id: str) -> Optional[Message]:
        """Retrieve a specific message from a newsgroup."""
        try:
            # Select the newsgroup
            self.nntp_conn.group(newsgroup)
            print(f"Selected newsgroup: {newsgroup}")

            # Normalize message ID format
            normalized_id = self.normalize_message_id(message_id)
            print(f"Retrieving message: {normalized_id}")

            # Retrieve the message
            resp, info = self.nntp_conn.article(normalized_id)

            # Parse the message
            message_lines = [line.decode('utf-8', errors='replace') for line in info.lines]
            message_text = '\n'.join(message_lines)

            # Parse as email message
            message = email.message_from_string(message_text)
            return message

        except nntplib_NNTPError as e:
            print(f"NNTP error retrieving message: {e}")
            print("\nTroubleshooting tips:")
            print("- For Message-ID format: use <message-id@domain.com> (with angle brackets)")
            print("- For article number format: use just the number (e.g., 12345)")
            print("- Make sure the message exists in the specified newsgroup")
            return None
        except Exception as e:
            print(f"Error retrieving message: {e}")
            return None

    def decode_header(self, header_value: str) -> str:
        """Decode email header that may contain encoded text."""
        try:
            decoded_parts = email.header.decode_header(header_value)
            decoded_string = ""
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    if encoding:
                        decoded_string += part.decode(encoding, errors='replace')
                    else:
                        decoded_string += part.decode('utf-8', errors='replace')
                else:
                    decoded_string += part
            return decoded_string
        except Exception:
            return header_value

    def analyze_message(self, message: Message) -> Dict[str, str]:
        """Extract and decode important headers from the message."""
        headers = {}

        # Important headers to analyze
        important_headers = [
            'From', 'To', 'Subject', 'Date', 'Message-ID', 'Reply-To',
            'Newsgroups', 'User-Agent', 'X-Mailer', 'Organization',
            'Content-Type', 'MIME-Version', 'References', 'In-Reply-To'
        ]

        for header in important_headers:
            value = message.get(header)
            if value:
                headers[header] = self.decode_header(value)

        # Get body preview (first 300 characters)
        try:
            if message.is_multipart():
                body = ""
                for part in message.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode('utf-8', errors='replace')[:300]
                            break
            else:
                payload = message.get_payload(decode=True)
                if payload:
                    body = payload.decode('utf-8', errors='replace')[:300]
                else:
                    body = str(message.get_payload())[:300]

            if body:
                headers['Body-Preview'] = body + ("..." if len(body) == 300 else "")
        except Exception as e:
            headers['Body-Preview'] = f"[Error reading body: {e}]"

        return headers

    def get_terminal_size(self) -> Tuple[int, int]:
        """Get terminal dimensions"""
        try:
            size = shutil.get_terminal_size()
            return size.columns, size.lines
        except:
            return 80, 24

    def get_message_list_page_size(self) -> int:
        """Calculate available lines for message list display"""
        cols, lines = self.get_terminal_size()
        header_lines = 5  # title, separator, column headers, separator
        footer_lines = 2  # separator, help
        available_lines = lines - header_lines - footer_lines
        # Add reasonable limits: show between 10-25 lines of content
        # This prevents issues with very large terminals
        return max(10, min(available_lines, 40))

    def get_paginated_list_page_size(self) -> int:
        """Calculate available lines for paginated list display"""
        cols, lines = self.get_terminal_size()
        header_lines = 4  # title, separator, blank line
        footer_lines = 2  # separator, help
        available_lines = lines - header_lines - footer_lines
        # Add reasonable limits: show between 10-30 lines of content
        # This prevents issues with very large terminals
        return max(10, min(available_lines, 40))

    def clear_screen(self):
        """Clear the terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def pause(self, message: str = "Press Enter to continue..."):
        """Pause and wait for user input"""
        try:
            input(message)
        except (KeyboardInterrupt, EOFError):
            pass

    def display_message_analysis(self, headers: Dict[str, str]) -> None:
        """Display the analyzed message headers in a formatted way."""
        print("\n" + "="*80)
        print("MESSAGE ANALYSIS")
        print("="*80)

        for header, value in headers.items():
            if header == 'Body-Preview':
                print(f"\n{header}:")
                print("-" * len(header))
                print(value)
            else:
                print(f"{header}: {value}")
        print("="*80)

    def select_filter_fields(self, headers: Dict[str, str]) -> List[Tuple[str, str, str]]:
        """Interactive selection of fields and patterns for filter rules."""
        print("\nAvailable fields for filtering:")
        print("-" * 40)

        field_list = [key for key in headers.keys() if key != 'Body-Preview']
        for i, field in enumerate(field_list, 1):
            print(f"{i:2d}. {field}: {headers[field][:60]}...")

        filters = []

        while True:
            print(f"\nCurrent filters: {len(filters)}")
            for i, (field, pattern, description) in enumerate(filters, 1):
                print(f"  {i}. ^{field}:{pattern}")

            print("\nOptions:")
            print("1. Add a new filter rule")
            print("2. Remove a filter rule")
            print("3. Finish and generate filters")
            print("4. Cancel")

            choice = input("\nEnter choice (1-4): ").strip()

            if choice == '1':
                # Add new filter
                print("\nSelect field to filter on:")
                for i, field in enumerate(field_list, 1):
                    print(f"{i:2d}. {field}")

                try:
                    field_choice = int(input(f"Enter field number (1-{len(field_list)}): ")) - 1
                    if 0 <= field_choice < len(field_list):
                        selected_field = field_list[field_choice]
                        field_value = headers[selected_field]

                        print(f"\nSelected field: {selected_field}")
                        print(f"Current value: {field_value}")
                        print("\nChoose pattern type:")
                        print("1. Exact match (entire field)")
                        print("2. Contains text (substring)")
                        print("3. Regex pattern")
                        print("4. Custom pattern")

                        pattern_choice = input("Enter pattern type (1-4): ").strip()

                        if pattern_choice == '1':
                            # Exact match - escape special regex chars
                            escaped_value = re.escape(field_value)
                            pattern = f"^{escaped_value}$"
                            description = f"Exact match: {field_value}"

                        elif pattern_choice == '2':
                            # Contains - ask for substring
                            substring = input("Enter text to match (case-insensitive): ").strip()
                            if substring:
                                escaped_substring = re.escape(substring)
                                pattern = f"(?i).*{escaped_substring}"
                                description = f"Contains: {substring}"
                            else:
                                continue

                        elif pattern_choice == '3':
                            # Regex pattern
                            print("Common regex patterns:")
                            print("  (?i)     - Case insensitive")
                            print("  .*       - Match anything")
                            print("  \\b       - Word boundary")
                            print("  [a-z]+   - One or more letters")
                            print("  @gmail\\.com$ - Ends with @gmail.com")

                            regex_pattern = input("Enter regex pattern: ").strip()
                            if regex_pattern:
                                pattern = regex_pattern
                                description = f"Regex: {regex_pattern}"
                            else:
                                continue

                        elif pattern_choice == '4':
                            # Custom pattern
                            custom_pattern = input("Enter custom pattern: ").strip()
                            if custom_pattern:
                                pattern = custom_pattern
                                description = f"Custom: {custom_pattern}"
                            else:
                                continue

                        else:
                            print("Invalid choice")
                            continue

                        # Validate the regex pattern
                        try:
                            re.compile(pattern)
                            filters.append((selected_field, pattern, description))
                            print(f"Added filter: ^{selected_field}:{pattern}")
                        except re.error as e:
                            print(f"Invalid regex pattern: {e}")
                    else:
                        print("Invalid field number")
                except ValueError:
                    print("Invalid input")

            elif choice == '2':
                # Remove filter
                if not filters:
                    print("No filters to remove")
                    continue

                try:
                    remove_idx = int(input(f"Enter filter number to remove (1-{len(filters)}): ")) - 1
                    if 0 <= remove_idx < len(filters):
                        removed = filters.pop(remove_idx)
                        print(f"Removed filter: ^{removed[0]}:{removed[1]}")
                    else:
                        print("Invalid filter number")
                except ValueError:
                    print("Invalid input")

            elif choice == '3':
                # Finish
                break

            elif choice == '4':
                # Cancel
                return []

            else:
                print("Invalid choice")

        return filters

    def append_to_filter_config(self, filters: List[Tuple[str, str, str]]) -> bool:
        """Append new filter rules to filter.cfg."""
        if not filters:
            print("No filters to add")
            return False

        filter_file = self.config.get('SpamFilter', 'filter_file')

        try:
            # Create backup
            if os.path.exists(filter_file):
                import shutil
                backup_file = f"{filter_file}.backup"
                shutil.copy2(filter_file, backup_file)
                print(f"Created backup: {backup_file}")

            # Append new filters
            with open(filter_file, 'a', encoding='utf-8') as f:
                f.write("\n#==============================================================================\n")
                f.write("# FILTERS ADDED BY FILTER_MANAGER\n")
                f.write(f"# Generated from message analysis\n")
                f.write("#==============================================================================\n\n")

                for field, pattern, description in filters:
                    f.write(f"# {description}\n")
                    f.write(f"^{field}:{pattern}\n\n")

            print(f"Added {len(filters)} filter(s) to {filter_file}")
            return True

        except Exception as e:
            print(f"Error updating filter file: {e}")
            return False

    def get_messages_by_date(self, newsgroup: str, start_date: datetime, end_date: datetime = None) -> List[Dict]:
        """Get messages from newsgroup within date range."""
        try:
            # Select the newsgroup
            resp, count, first, last, name = self.nntp_conn.group(newsgroup)
            print(f"Selected newsgroup: {newsgroup} ({count} messages)")

            if end_date is None:
                end_date = datetime.now()

            messages = []
            print(f"Scanning messages from {start_date.strftime('%d-%m-%Y')} to {end_date.strftime('%d-%m-%Y')}...")

            # Ask user for scan range to avoid missing older messages
            print(f"Newsgroup has messages {first}-{last}")
            scan_choice = input(f"Scan all messages or limit to recent? (all/recent/custom): ").strip().lower()

            if scan_choice == 'all':
                scan_start = int(first)
                print(f"Scanning all {int(last) - int(first) + 1} messages...")
            elif scan_choice == 'custom':
                try:
                    scan_start = int(input(f"Start scanning from message number (min {first}): "))
                    scan_start = max(int(first), min(scan_start, int(last)))
                except ValueError:
                    scan_start = int(first)
            else:  # recent
                scan_start = max(int(first), int(last) - 500)
                print(f"Scanning last 500 messages ({scan_start}-{last})...")

            for msg_num in range(int(last), scan_start, -1):
                try:
                    # Get headers only first
                    resp, info = self.nntp_conn.head(str(msg_num))
                    header_lines = [line.decode('utf-8', errors='replace') for line in info.lines]
                    header_text = '\n'.join(header_lines)

                    # Parse headers to get date
                    msg = email.message_from_string(header_text)
                    date_header = msg.get('Date')
                    if not date_header:
                        continue

                    # Parse date
                    try:
                        msg_date = email.utils.parsedate_to_datetime(date_header)
                        # Strip timezone info to make comparison work
                        if msg_date.tzinfo is not None:
                            msg_date = msg_date.replace(tzinfo=None)

                        # Convert to date-only for comparison (ignore time)
                        msg_date_only = msg_date.date()
                        start_date_only = start_date.date()
                        end_date_only = end_date.date()

                    except Exception as e:
                        continue

                    # Check if message is in our date range (date-only comparison)
                    if start_date_only <= msg_date_only <= end_date_only:
                        subject = self.decode_header(msg.get('Subject', 'No Subject'))
                        from_header = self.decode_header(msg.get('From', 'Unknown'))

                        messages.append({
                            'number': msg_num,
                            'date': msg_date,
                            'subject': subject,
                            'from': from_header,
                            'message_id': msg.get('Message-ID', ''),
                            'headers': msg
                        })

                        print(f"Found: {msg_date.strftime('%d-%m-%Y %H:%M')} - {subject[:60]}...")

                except nntplib_NNTPError:
                    continue
                except Exception as e:
                    continue

            messages.sort(key=lambda x: x['date'], reverse=True)
            print(f"\nFound {len(messages)} messages in date range")
            return messages

        except Exception as e:
            print(f"Error retrieving messages by date: {e}")
            return []

    def display_message_list(self, messages: List[Dict]) -> None:
        """Display list of messages for selection with paging."""
        if not messages:
            print("No messages to display")
            return

        current_page = 0

        while True:
            # Recalculate page size and layout for each iteration (in case terminal was resized)
            cols, lines = self.get_terminal_size()
            page_size = self.get_message_list_page_size()
            total_pages = (len(messages) + page_size - 1) // page_size

            start_idx = current_page * page_size
            end_idx = min(start_idx + page_size, len(messages))

            self.clear_screen()
            print("=" * cols)
            print(f"MESSAGES IN DATE RANGE - Page {current_page + 1}/{total_pages} ({len(messages)} total) | Terminal: {cols}x{lines} | Page size: {page_size}")
            print("=" * cols)
            print(f"{'#':<3} {'Date':<16} {'From':<25} {'Subject'}")
            print("-" * cols)

            for i in range(start_idx, end_idx):
                msg = messages[i]
                date_str = msg['date'].strftime('%d-%m-%Y %H:%M')
                from_str = msg['from'][:24]
                subject_len = cols - 3 - 16 - 25 - 4  # remaining space for subject
                subject_str = msg['subject'][:max(20, subject_len)]
                print(f"{i+1:<3} {date_str:<16} {from_str:<25} {subject_str}")

            print("=" * cols)

            # Show navigation help
            nav_help = "[Enter/Space]=Next [b]=Previous [q]=Done"
            if total_pages > 1:
                print(nav_help)
            else:
                print("Press Enter to continue...")

            try:
                command = input("Navigation: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                break

            if command in ['q', 'quit', 'done']:
                break
            elif command in ['', ' ', 'n', 'next']:
                if current_page < total_pages - 1:
                    current_page += 1
                else:
                    # At last page, Enter exits to message selection
                    break
            elif command in ['b', 'back', 'prev', 'previous'] and current_page > 0:
                current_page -= 1
            elif command.isdigit():
                page_num = int(command) - 1
                if 0 <= page_num < total_pages:
                    current_page = page_num

    def select_messages_for_analysis(self, messages: List[Dict]) -> List[Dict]:
        """Allow user to select multiple messages for analysis."""
        while True:
            print(f"\nSelect messages to analyze (1-{len(messages)}):")
            print("Enter numbers separated by commas (e.g., 1,3,5-8)")
            print("Or 'all' for all messages, 'q' to quit")
            print("Note: Message list above supports paging navigation")

            selection = input("Selection: ").strip()

            if selection.lower() == 'q':
                return []

            if selection.lower() == 'all':
                return messages

            try:
                selected_indices = []
                for part in selection.split(','):
                    part = part.strip()
                    if '-' in part:
                        start, end = map(int, part.split('-'))
                        selected_indices.extend(range(start-1, end))
                    else:
                        selected_indices.append(int(part)-1)

                selected_messages = []
                for idx in selected_indices:
                    if 0 <= idx < len(messages):
                        selected_messages.append(messages[idx])

                if selected_messages:
                    print(f"Selected {len(selected_messages)} messages")
                    return selected_messages
                else:
                    print("No valid messages selected")

            except ValueError:
                print("Invalid selection format")

    def bulk_analyze_messages(self, newsgroup: str, messages: List[Dict]) -> List[Tuple[str, str, str]]:
        """Analyze multiple messages and generate bulk filter rules."""
        print(f"\nAnalyzing {len(messages)} messages for common patterns...")

        # Collect all message data
        all_headers = []
        for msg_info in messages:
            try:
                # Get full message content
                resp, info = self.nntp_conn.article(str(msg_info['number']))
                message_lines = [line.decode('utf-8', errors='replace') for line in info.lines]
                message_text = '\n'.join(message_lines)
                message = email.message_from_string(message_text)

                headers = self.analyze_message(message)
                all_headers.append((headers, msg_info))

            except Exception as e:
                print(f"Error analyzing message {msg_info['number']}: {e}")
                continue

        print(f"\nAnalyzed {len(all_headers)} messages")

        # Show common patterns
        self.show_common_patterns(all_headers)

        # Generate suggested filters
        return self.generate_bulk_filters(newsgroup, all_headers)

    def show_common_patterns(self, all_headers: List[Tuple[Dict, Dict]]) -> None:
        """Show common patterns across selected messages with paging."""
        cols, lines = self.get_terminal_size()

        # Count common subjects patterns
        subjects = [headers['Subject'] for headers, _ in all_headers if 'Subject' in headers]
        from_headers = [headers['From'] for headers, _ in all_headers if 'From' in headers]

        # Count senders
        sender_counts = {}
        for sender in from_headers:
            sender_counts[sender] = sender_counts.get(sender, 0) + 1

        # Sort senders by count (most frequent first)
        sorted_senders = sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)

        # Display subjects with paging
        self._display_paginated_list(
            subjects,
            title=f"SUBJECTS FOUND ({len(subjects)} total)",
            formatter=lambda i, item: f"{i:3d}. {item}"
        )

        # Display senders with paging
        self._display_paginated_list(
            sorted_senders,
            title=f"SENDERS FOUND ({len(from_headers)} total messages, {len(sorted_senders)} unique senders)",
            formatter=lambda i, item: f"{item[1]:3d}x {item[0]}"
        )

    def _display_paginated_list(self, items: List, title: str, formatter) -> None:
        """Display a list with paging support."""
        if not items:
            print(f"\n{title}: No items to display")
            self.pause()
            return

        current_page = 0

        while True:
            # Recalculate page size and layout for each iteration (in case terminal was resized)
            cols, lines = self.get_terminal_size()
            page_size = self.get_paginated_list_page_size()
            total_pages = (len(items) + page_size - 1) // page_size

            start_idx = current_page * page_size
            end_idx = min(start_idx + page_size, len(items))

            self.clear_screen()
            print("=" * cols)
            print(f"{title} - Page {current_page + 1}/{total_pages} | Terminal: {cols}x{lines} | Page size: {page_size}")
            print("=" * cols)
            print()

            for i in range(start_idx, end_idx):
                display_text = formatter(i + 1, items[i])
                # Truncate long lines to fit terminal
                if len(display_text) > cols - 2:
                    display_text = display_text[:cols - 5] + "..."
                print(display_text)

            print()
            print("=" * cols)

            # Show navigation help
            if total_pages > 1:
                nav_help = "[Enter/Space]=Next [b]=Previous [g]=Go to page [q]=Done"
                print(nav_help)
            else:
                print("Press Enter to continue...")

            try:
                command = input("Navigation: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                break

            if command in ['q', 'quit', 'done']:
                break
            elif command in ['', ' ', 'n', 'next'] and current_page < total_pages - 1:
                current_page += 1
            elif command in ['b', 'back', 'prev', 'previous'] and current_page > 0:
                current_page -= 1
            elif command.startswith('g'):
                # Go to specific page
                parts = command.split()
                if len(parts) == 2:
                    try:
                        page_num = int(parts[1]) - 1
                        if 0 <= page_num < total_pages:
                            current_page = page_num
                        else:
                            print(f"Page number must be between 1 and {total_pages}")
                            self.pause()
                    except ValueError:
                        print("Invalid page number")
                        self.pause()
                else:
                    try:
                        page_input = input(f"Go to page (1-{total_pages}): ")
                        page_num = int(page_input) - 1
                        if 0 <= page_num < total_pages:
                            current_page = page_num
                        else:
                            print(f"Page number must be between 1 and {total_pages}")
                            self.pause()
                    except ValueError:
                        print("Invalid page number")
                        self.pause()
            elif command == '':
                # Empty input means continue to next section
                break

    def generate_bulk_filters(self, newsgroup: str, all_headers: List[Tuple[Dict, Dict]]) -> List[Tuple[str, str, str]]:
        """Generate filter rules for bulk messages."""
        print(f"\nGenerating filter suggestions...")

        filters = []

        # Option 1: Block all messages from common senders
        from_headers = [headers['From'] for headers, _ in all_headers if 'From' in headers]
        sender_counts = {}
        for sender in from_headers:
            sender_counts[sender] = sender_counts.get(sender, 0) + 1

        print("\nFilter options:")
        print("1. Block by sender (From header)")
        print("2. Block by subject patterns")
        print("3. Block all in this newsgroup from date range")
        print("4. Custom pattern selection")

        choice = input("Select option (1-4): ").strip()

        if choice == '1':
            if not sender_counts:
                print("No senders found")
            else:
                # For single or multiple messages, always offer to block senders
                for sender, count in sender_counts.items():
                    escaped_sender = re.escape(sender)
                    filters.append(('From', f'.*{escaped_sender}', f'Block sender: {sender} ({count} message{"s" if count > 1 else ""})'))
                    print(f"Added filter to block: {sender}")

        elif choice == '2':
            # Look for common subject patterns
            subjects = [headers['Subject'] for headers, _ in all_headers if 'Subject' in headers]
            # Find common words in subjects
            all_words = []
            for subject in subjects:
                words = re.findall(r'\b\w+\b', subject.lower())
                all_words.extend(words)

            word_counts = {}
            for word in all_words:
                if len(word) > 3:  # Skip short words
                    word_counts[word] = word_counts.get(word, 0) + 1

            print("\nCommon words in subjects:")

            if not word_counts:
                print("No significant words found in subjects (words must be > 3 characters)")
                filters.append(('Subject', '.*', 'Block all subjects (no specific patterns found)'))
            else:
                # Show all words and let user choose, or auto-suggest based on frequency
                sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:10]

                if len(subjects) == 1:
                    # Single message - show all words and let user pick
                    print("Available words from the subject:")
                    for i, (word, count) in enumerate(sorted_words, 1):
                        print(f"{i:2d}. {word} ({count} time{'s' if count > 1 else ''})")

                    print(f"{len(sorted_words) + 1:2d}. Create phrase filter (multiple words together)")

                    word_choice = input("\nSelect word numbers (comma-separated), 'all', or phrase option: ").strip()
                    if word_choice.lower() == 'all':
                        for word, count in sorted_words:
                            filters.append(('Subject', f'(?i).*\\b{re.escape(word)}\\b', f'Contains word: {word}'))
                    elif word_choice == str(len(sorted_words) + 1):
                        # Phrase filter option
                        print(f"\nOriginal subject: {subjects[0]}")
                        phrase = input("Enter phrase to filter on (e.g., 'sovereign citizens'): ").strip()
                        if phrase:
                            escaped_phrase = re.escape(phrase)
                            filters.append(('Subject', f'(?i).*{escaped_phrase}', f'Contains phrase: {phrase}'))
                            print(f"Added phrase filter for: {phrase}")
                        else:
                            print("No phrase entered, skipping")
                    elif word_choice:
                        try:
                            indices = [int(x.strip()) - 1 for x in word_choice.split(',')]
                            phrase_idx = len(sorted_words)  # The phrase option index

                            if phrase_idx in [int(x.strip()) - 1 for x in word_choice.split(',')]:
                                # User selected phrase option along with word numbers
                                print(f"\nOriginal subject: {subjects[0]}")
                                phrase = input("Enter phrase to filter on (e.g., 'sovereign citizens'): ").strip()
                                if phrase:
                                    escaped_phrase = re.escape(phrase)
                                    filters.append(('Subject', f'(?i).*{escaped_phrase}', f'Contains phrase: {phrase}'))
                                    print(f"Added phrase filter for: {phrase}")

                            # Process individual word selections
                            for idx in indices:
                                if 0 <= idx < len(sorted_words):
                                    word, count = sorted_words[idx]
                                    filters.append(('Subject', f'(?i).*\\b{re.escape(word)}\\b', f'Contains word: {word}'))

                        except ValueError:
                            print("Invalid selection, using all words")
                            for word, count in sorted_words:
                                filters.append(('Subject', f'(?i).*\\b{re.escape(word)}\\b', f'Contains word: {word}'))
                else:
                    # Multiple messages - use words that appear more than once
                    for word, count in sorted_words:
                        if count > 1:
                            filters.append(('Subject', f'(?i).*\\b{re.escape(word)}\\b', f'Contains word: {word} ({count} times)'))
                        else:
                            print(f"Word '{word}' appears only once, skipping")

                    if not filters:
                        print("No words appear multiple times. Showing all significant words:")
                        for word, count in sorted_words:
                            filters.append(('Subject', f'(?i).*\\b{re.escape(word)}\\b', f'Contains word: {word} ({count} time{"s" if count > 1 else ""})'))
                            print(f"Added filter for: {word}")

        elif choice == '3':
            # Block by newsgroup and date range
            start_date = min(msg_info['date'] for _, msg_info in all_headers)
            end_date = max(msg_info['date'] for _, msg_info in all_headers)
            filters.append(('Newsgroups', f'(?i).*{re.escape(newsgroup)}', f'Block {newsgroup} (bulk spam detected)'))

        return filters

    def run(self) -> None:
        """Main interactive loop."""
        print("PyGate Filter Configuration Manager")
        print("=" * 40)

        # Connect to server
        if not self.connect_to_server():
            return

        try:
            while True:
                print("\nMode selection:")
                print("1. Analyze single message by Message-ID")
                print("2. Browse messages by date range")
                print("Q. Exit to Main Menu")

                mode = input("Select mode (1-2, Q): ").strip()

                if mode.upper() == 'Q':
                    break
                elif mode == '1':
                    self.single_message_mode()
                elif mode == '2':
                    self.date_range_mode()
                else:
                    print("Invalid selection")

        except KeyboardInterrupt:
            print("\n\nInterrupted by user")

        finally:
            self.disconnect()
            print("Disconnected from server")

    def single_message_mode(self) -> None:
        """Original single message analysis mode."""
        print("\n--- Single Message Analysis ---")
        newsgroup = input("Newsgroup name: ").strip()
        if not newsgroup:
            print("Newsgroup name is required")
            return

        message_id = input("Message ID: ").strip()
        if not message_id:
            print("Message ID is required")
            return

        # Retrieve and analyze message
        message = self.get_message(newsgroup, message_id)
        if not message:
            print("Failed to retrieve message")
            return

        # Analyze message
        headers = self.analyze_message(message)
        self.display_message_analysis(headers)

        # Interactive filter selection
        filters = self.select_filter_fields(headers)

        if filters:
            self.preview_and_apply_filters(filters)

    def date_range_mode(self) -> None:
        """Date range browsing and bulk analysis mode."""
        print("\n--- Date Range Analysis ---")
        newsgroup = input("Newsgroup name: ").strip()
        if not newsgroup:
            print("Newsgroup name is required")
            return

        # Get date range
        print("\nEnter start date for spam (format: DD-MM-YYYY)")
        print("Example: 15-09-2025")
        start_date_str = input("Start date: ").strip()

        try:
            start_date = datetime.strptime(start_date_str, '%d-%m-%Y')
        except ValueError:
            print("Invalid date format")
            return

        end_date_str = input("End date (press Enter for today): ").strip()
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%d-%m-%Y')
            except ValueError:
                print("Invalid date format")
                return
        else:
            end_date = datetime.now()

        # Get messages in date range
        messages = self.get_messages_by_date(newsgroup, start_date, end_date)
        if not messages:
            print("No messages found in date range")
            return

        # Display messages
        self.display_message_list(messages)

        # Select messages for analysis
        selected_messages = self.select_messages_for_analysis(messages)
        if not selected_messages:
            return

        # Bulk analyze
        filters = self.bulk_analyze_messages(newsgroup, selected_messages)

        if filters:
            self.preview_and_apply_filters(filters)

    def preview_and_apply_filters(self, filters: List[Tuple[str, str, str]]) -> None:
        """Show preview and apply filters."""
        # Show preview
        print("\nGenerated filter rules:")
        print("-" * 40)
        for field, pattern, description in filters:
            print(f"# {description}")
            print(f"^{field}:{pattern}")

        confirm = input(f"\nAdd these {len(filters)} filters to filter.cfg? (y/n): ")
        if confirm.lower() == 'y':
            if self.append_to_filter_config(filters):
                print("Filters added successfully!")
            else:
                print("Failed to add filters")
        else:
            print("Filters not added")


def main():
    """Entry point for the filter manager."""
    if len(sys.argv) > 1:
        if sys.argv[1] in ['--help', '-h']:
            print("PyGate Filter Configuration Manager")
            print("=" * 40)
            print("Usage: python filter_manager.py")
            print("")
            print("Interactive tool to create spam filter rules by analyzing NNTP messages.")
            print("")
            print("The tool will:")
            print("1. Connect to your NNTP server (using pygate.cfg settings)")
            print("2. Ask for newsgroup name and message ID")
            print("3. Retrieve and analyze the message")
            print("4. Let you select fields to create filter rules")
            print("5. Add new rules to filter.cfg")
            print("")
            print("Options:")
            print("  --help, -h    Show this help message")
            print("  --test        Test connection only")
            return
        elif sys.argv[1] == '--test':
            print("Testing connection...")
            filter_mgr = FilterManager()
            if filter_mgr.connect_to_server():
                print("Connection test successful!")
                filter_mgr.disconnect()
            else:
                print("Connection test failed!")
            return

    filter_mgr = FilterManager()
    filter_mgr.run()


if __name__ == "__main__":
    main()
