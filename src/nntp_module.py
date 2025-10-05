#!/usr/bin/env python3
"""
PyGate NNTP Module
Handles NNTP server communication for the gateway
"""

import os
import time
import re
import email
from email.utils import parseaddr, formataddr, parsedate_to_datetime
from email.header import decode_header
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
import logging

# Use custom NNTP client instead of deprecated nntplib
from .nntp_client import (
    CustomNNTPClient as NNTP,
    CustomNNTP_SSL as NNTP_SSL,
    NNTPError,
    NNTPPermanentError,
    NNTPTemporaryError
)


class NNTPModule:
    """NNTP communication module for PyGate"""

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.connection = None

    def connect(self) -> bool:
        """Connect to NNTP server"""
        try:
            host = self.config.get('NNTP', 'host')
            port = self.config.getint('NNTP', 'port')
            username = self.config.get('NNTP', 'username')
            password = self.config.get('NNTP', 'password')
            use_ssl = self.config.getboolean('NNTP', 'use_ssl')
            timeout = self.config.getint('NNTP', 'timeout')

            if not host:
                self.logger.error("NNTP host not configured")
                return False

            self.logger.info(f"Connecting to NNTP server {host}:{port}")

            # Create connection object
            if use_ssl:
                self.connection = NNTP_SSL(host, port, timeout=timeout)
            else:
                self.connection = NNTP(host, port, timeout=timeout)

            # Explicitly connect (custom client requires this)
            self.connection.connect()

            # Authenticate if credentials provided
            if username and password:
                self.logger.info("Authenticating to NNTP server")
                try:
                    self.connection.login(username, password)
                    self.logger.info("NNTP authentication successful")
                except NNTPPermanentError as e:
                    self.logger.error(f"NNTP authentication failed: {e}")
                    self.connection.quit()
                    self.connection = None
                    return False

            return True

        except Exception as e:
            self.logger.error(f"Cannot connect to NNTP server: {e}")
            self.connection = None
            return False

    def disconnect(self):
        """Disconnect from NNTP server"""
        if self.connection:
            try:
                self.connection.quit()
                self.logger.info("Disconnected from NNTP server")
            except:
                pass
            finally:
                self.connection = None

    def post_message(self, message: Dict[str, Any]) -> bool:
        """Post a message to NNTP server"""
        if not self.connection and not self.connect():
            return False

        try:
            # Get newsgroup from area mapping
            newsgroup = self.get_newsgroup_for_area(message.get('area', ''))
            if not newsgroup:
                self.logger.error(f"No newsgroup mapping for area: {message.get('area', '')}")
                return False

            # Build NNTP article
            article_lines = self.build_nntp_article(message, newsgroup)

            # Debug: Log the headers we're sending
            article_text = '\n'.join(article_lines)
            self.logger.debug(f"Posting article headers:\n{article_text[:article_text.find(chr(10)+chr(10))]}")

            # Post article
            self.logger.info(f"Posting message to {newsgroup}: {message.get('subject', 'No Subject')}")

            try:
                self.connection.group(newsgroup)  # Select newsgroup
                resp = self.connection.post(article_text.encode('utf-8'))
                self.logger.info(f"Message posted successfully: {resp}")
                return True

            except NNTPError as e:
                self.logger.error(f"Failed to post message: {e}")
                return False

        except Exception as e:
            self.logger.error(f"Error posting message: {e}")
            return False

    def fetch_messages(self, newsgroup: str, area_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch messages from newsgroup"""
        if not self.connection and not self.connect():
            return []

        messages = []

        try:
            self.logger.info(f"Fetching messages from {newsgroup}")

            # Select newsgroup
            resp, count, first, last, name = self.connection.group(newsgroup)

            # Convert to integers
            first_num = int(first)
            last_num = int(last)

            # Get last processed article for this area
            last_processed = area_config.get('last_article', 0)
            start_article = max(last_processed + 1, first_num)

            if start_article > last_num:
                return messages

            # Determine fetch limit
            is_new_newsgroup = (last_processed == 0)
            if is_new_newsgroup:
                # New newsgroup - use initial fetch limit
                initial_fetch = self.config.getint('SpamFilter', 'initialfetch')
                fetch_limit = min(initial_fetch, last_num - start_article + 1)
                self.logger.info(f"New newsgroup detected: limiting initial fetch to {fetch_limit} articles")
                end_article = min(start_article + fetch_limit - 1, last_num)
            else:
                # Existing newsgroup - use standard limit per run (100 articles)
                fetch_limit = min(100, last_num - start_article + 1)
                end_article = min(start_article + fetch_limit - 1, last_num)

            # Fetch articles
            for article_num in range(start_article, end_article + 1):
                try:
                    resp, article_info = self.connection.article(str(article_num))
                    lines = article_info.lines

                    # Parse article
                    message = self.parse_nntp_article(lines, newsgroup, article_num)
                    if message:
                        messages.append(message)
                        self.logger.debug(f"Fetched article {article_num}: {message.get('subject', 'No Subject')}")

                except NNTPTemporaryError:
                    # Article doesn't exist, skip
                    continue
                except Exception as e:
                    self.logger.error(f"Error fetching article {article_num}: {e}")
                    continue

            # Log fetch results with context
            if is_new_newsgroup:
                self.logger.info(f"Initial fetch from new newsgroup {newsgroup}: {len(messages)}/{fetch_limit} articles")
            else:
                self.logger.info(f"Fetched {len(messages)} messages from {newsgroup}")

            # Update last processed article to the end of our fetch range
            if messages:
                # Update to the highest article number we attempted to fetch
                area_config['last_article'] = end_article

        except Exception as e:
            self.logger.error(f"Error fetching from {newsgroup}: {e}")

        return messages

    def parse_nntp_article(self, lines: List[bytes], newsgroup: str, article_num: int) -> Optional[Dict[str, Any]]:
        """Parse NNTP article into message dict"""
        try:
            # Convert bytes to string
            article_text = []
            for line in lines:
                if isinstance(line, bytes):
                    article_text.append(line.decode('utf-8', errors='replace'))
                else:
                    article_text.append(str(line))

            # Find header/body separation
            header_lines = []
            body_lines = []
            in_body = False

            for line in article_text:
                if not in_body and line.strip() == '':
                    in_body = True
                    continue

                if in_body:
                    body_lines.append(line)
                else:
                    header_lines.append(line)

            # Parse headers
            headers = {}
            current_header = None
            current_value = ""

            for line in header_lines:
                if line.startswith(' ') or line.startswith('\t'):
                    # Continuation line
                    if current_header:
                        current_value += " " + line.strip()
                else:
                    # Save previous header
                    if current_header:
                        headers[current_header.lower()] = current_value.strip()

                    # Start new header
                    if ':' in line:
                        current_header, current_value = line.split(':', 1)
                        current_header = current_header.strip()
                        current_value = current_value.strip()

            # Save last header
            if current_header:
                headers[current_header.lower()] = current_value.strip()

            # Extract key information
            message = {
                'newsgroup': newsgroup,
                'article_num': article_num,
                'from_name': self.extract_name_from_email(headers.get('from', 'Unknown')),
                'from_email': self.extract_email_from_header(headers.get('from', '')),
                'subject': self.decode_and_truncate_subject(headers.get('subject', '')),
                'date': self.parse_date(headers.get('date', '')),
                'message_id': headers.get('message-id', ''),
                'references': headers.get('references', ''),
                'body': self.extract_text_from_body(body_lines, headers),
                'headers': headers
            }

            return message

        except Exception as e:
            self.logger.error(f"Error parsing article {article_num}: {e}")
            return None

    def build_nntp_article(self, message: Dict[str, Any], newsgroup: str) -> List[str]:
        """Build NNTP article from FidoNet message"""
        lines = []

        # Required headers
        from_email = self.config.get('Mapping', 'gate_email')
        from_name = message.get('from_name', 'Unknown')

        lines.append(f"From: {from_name} <{from_email}>")
        lines.append(f"Newsgroups: {newsgroup}")
        lines.append(f"Subject: {message.get('subject', '')}")

        # Handle datetime - may be datetime object or ISO string (from hold system)
        msg_datetime = message.get('datetime', datetime.now())
        if isinstance(msg_datetime, str):
            # Parse ISO format datetime string from hold system
            try:
                msg_datetime = datetime.fromisoformat(msg_datetime.replace('Z', '+00:00'))
            except ValueError:
                # Fallback to current time if parsing fails
                self.logger.warning(f"Failed to parse datetime string: {msg_datetime}, using current time")
                msg_datetime = datetime.now()

        lines.append(f"Date: {self.format_date(msg_datetime)}")
        lines.append(f"Organization: {self.config.get('FidoNet', 'origin_line')}")

        # Sender header - identifies the actual posting agent (gateway)
        gate_email = self.config.get('Mapping', 'gate_email', fallback=f'pygate@{self.get_message_id_domain()}')
        lines.append(f"Sender: {gate_email}")

        # Message-ID
        msgid = message.get('msgid', '')
        if msgid:
            # Convert FidoNet MSGID to NNTP format
            nntp_msgid = self.convert_fido_msgid(msgid)
            lines.append(f"Message-ID: {nntp_msgid}")
        else:
            # Generate Message-ID using proper domain
            import uuid
            domain = self.get_message_id_domain()
            lines.append(f"Message-ID: <{uuid.uuid4()}@{domain}>")

        # References (for replies)
        references = message.get('reply', '')
        if references:
            nntp_references = self.convert_fido_reply(references)
            if nntp_references:
                lines.append(f"References: {nntp_references}")

        # Gateway signature and FTN information
        lines.append("X-Gateway: PyGate FidoNet-NNTP Gateway")
        lines.append(f"X-FidoNet-Area: {message.get('area', '')}")

        # Only add X-FTN-MSGID if msgid is not empty
        msgid = message.get('msgid', '').strip()
        if msgid:
            lines.append(f"X-FTN-MSGID: {msgid}")

        lines.append(f"X-FTN-From: {message.get('from_name', 'Unknown')}")

        # Empty line between headers and body
        lines.append("")

        # Body
        body = message.get('text', '')

        # Fallback to alternative body fields if 'text' is empty
        if not body.strip():
            for key in ['body', 'message', 'content', 'msg']:
                if key in message and message[key]:
                    body = message[key]
                    break

        # Add FidoNet origin if present
        origin = message.get('origin', '')
        if origin:
            body += f"\n\n * Origin: {origin}"

        # Split body into lines and handle NNTP dot-stuffing
        body_lines = body.split('\n')
        for line in body_lines:
            line = line.rstrip()
            # Handle NNTP dot-stuffing: escape lines starting with dot
            if line.startswith('.'):
                if line == '.':
                    # A lone dot is NNTP end-of-message marker, should be escaped
                    line = '..'
                else:
                    # Lines starting with dot should be dot-stuffed
                    line = '.' + line
            lines.append(line)

        return lines

    def get_newsgroup_for_area(self, area: str) -> Optional[str]:
        """Get newsgroup mapping for FidoNet area"""
        if not area:
            return None

        # Check for explicit mapping in [Arearemap] section
        if self.config.has_section('Arearemap'):
            try:
                for fido_area, newsgroup in self.config.items('Arearemap'):
                    if fido_area.upper() == area.upper():
                        return newsgroup
            except Exception as e:
                self.logger.error(f"Error reading Arearemap section: {e}")

        # Default: use area name as newsgroup name (convert to lowercase)
        return area.lower()

    def extract_name_from_email(self, from_header: str) -> str:
        """Extract name from email header with MIME decoding and FIDONET length validation"""
        try:
            name, email_addr = parseaddr(from_header)

            # Decode MIME header if needed
            if name:
                decoded_name = self.decode_mime_header(name)
            else:
                decoded_name = email_addr.split('@')[0] if '@' in email_addr else 'Unknown'

            # Truncate to fit FIDONET fromUserName field (35 chars + null terminator)
            if len(decoded_name) > 35:
                decoded_name = decoded_name[:35]

            return decoded_name
        except:
            return 'Unknown'

    def decode_mime_header(self, header_value: str) -> str:
        """Decode MIME-encoded header values like =?iso-8859-1?q?text?="""
        try:
            decoded_parts = decode_header(header_value)
            result = ''
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    if encoding:
                        result += part.decode(encoding, errors='replace')
                    else:
                        result += part.decode('ascii', errors='replace')
                else:
                    result += part
            return result
        except Exception:
            return header_value  # Return original if decoding fails

    def decode_and_truncate_subject(self, subject_header: str) -> str:
        """Decode MIME subject header and truncate to fit FIDONET subject field (72 bytes)"""
        try:
            decoded_subject = self.decode_mime_header(subject_header)
            # Truncate to fit FIDONET subject field (71 chars + 1 null terminator = 72 bytes)
            if len(decoded_subject) > 71:
                decoded_subject = decoded_subject[:71]
            return decoded_subject
        except Exception:
            return subject_header[:71] if len(subject_header) > 71 else subject_header

    def extract_email_from_header(self, from_header: str) -> str:
        """Extract email address from header"""
        try:
            name, email_addr = parseaddr(from_header)
            return email_addr if email_addr else ''
        except:
            return ''

    def parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime"""
        try:
            if date_str:
                return parsedate_to_datetime(date_str)
            return datetime.now(timezone.utc)
        except:
            return datetime.now(timezone.utc)

    def extract_text_from_body(self, body_lines: List[str], headers: Dict[str, str]) -> str:
        """Extract plain text from message body, handling MIME content"""
        try:
            # Join body lines to reconstruct the message
            body_text = '\n'.join(body_lines)

            # Get content type
            content_type = headers.get('content-type', 'text/plain')
            content_transfer_encoding = headers.get('content-transfer-encoding', '7bit')

            # If it's not multipart and is plain text, handle encoding only
            if not content_type.lower().startswith('multipart/'):
                return self.decode_text_content(body_text, content_transfer_encoding)

            # For multipart messages, we need to parse the MIME structure
            # Reconstruct the full message for email.message_from_string
            full_message = []

            # Add headers
            for key, value in headers.items():
                full_message.append(f"{key}: {value}")
            full_message.append("")  # Empty line between headers and body
            full_message.extend(body_lines)

            # Parse with email module
            message_text = '\n'.join(full_message)
            msg = email.message_from_string(message_text)

            # Extract text parts
            text_parts = []
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        charset = part.get_content_charset() or 'utf-8'
                        text_parts.append(payload.decode(charset, errors='replace'))
                    else:
                        text_parts.append(str(payload))

            if text_parts:
                # Join text parts and only strip trailing whitespace (preserve blank lines within body)
                result = '\n'.join(text_parts)
                # Only remove excessive trailing newlines, but preserve internal blank lines
                return result.rstrip('\n') + '\n' if result.rstrip() else result.rstrip()

            # Fallback to original body if no text parts found
            return self.decode_text_content(body_text, content_transfer_encoding)

        except Exception as e:
            self.logger.debug(f"Error extracting text from body: {e}")
            # Fallback to simple join
            return '\n'.join(body_lines)

    def decode_text_content(self, text: str, encoding: str) -> str:
        """Decode text content based on transfer encoding"""
        try:
            encoding = encoding.lower()

            if encoding == 'quoted-printable':
                import quopri
                # Handle quoted-printable encoding
                decoded_bytes = quopri.decodestring(text.encode('utf-8'))
                return decoded_bytes.decode('utf-8', errors='replace')
            elif encoding == 'base64':
                import base64
                # Handle base64 encoding
                decoded_bytes = base64.b64decode(text.encode('utf-8'))
                return decoded_bytes.decode('utf-8', errors='replace')
            else:
                # 7bit, 8bit, binary - return as is
                return text

        except Exception as e:
            self.logger.debug(f"Error decoding text content: {e}")
            return text

    def format_date(self, dt: datetime) -> str:
        """Format datetime for NNTP"""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime('%a, %d %b %Y %H:%M:%S %z')

    def convert_fido_msgid(self, fido_msgid: str) -> str:
        """Convert FidoNet MSGID to NNTP Message-ID"""
        # If already in NNTP format, return as-is
        if fido_msgid.startswith('<') and fido_msgid.endswith('>'):
            return fido_msgid

        # If empty, generate a unique ID
        if not fido_msgid.strip():
            import uuid
            return f"<{uuid.uuid4()}@pygate.fidonet>"

        # Convert FidoNet format "zone:net/node[.point] serial" to RFC-compliant
        try:
            parts = fido_msgid.strip().split()
            if len(parts) >= 2:
                address_part = parts[0]
                serial_part = parts[1]

                # Convert address format: "3:633/280.1" -> "3.633.280.1"
                # Replace colons and slashes with dots for RFC compliance
                safe_address = address_part.replace(':', '.').replace('/', '.')

                # Create RFC-compliant Message-ID
                domain = self.get_message_id_domain()
                return f"<{serial_part}.{safe_address}@{domain}>"
            else:
                # Fallback for malformed MSGID
                safe_msgid = fido_msgid.replace(':', '.').replace('/', '.').replace(' ', '.')
                domain = self.get_message_id_domain()
                return f"<{safe_msgid}@{domain}>"

        except Exception:
            # Ultimate fallback
            import hashlib
            hash_obj = hashlib.md5(fido_msgid.encode('utf-8'))
            domain = self.get_message_id_domain()
            return f"<{hash_obj.hexdigest()}@{domain}>"

    def convert_fido_reply(self, fido_reply: str) -> str:
        """Convert FidoNet REPLY to NNTP References"""
        # Use the same conversion logic as MSGID
        return self.convert_fido_msgid(fido_reply)

    def get_message_id_domain(self) -> str:
        """Get domain name for Message-ID generation"""
        try:
            # Extract domain from gate_email in config
            gate_email = self.config.get('Mapping', 'gate_email', fallback='')
            if '@' in gate_email:
                return gate_email.split('@')[1]
            else:
                # Fallback to a reasonable default
                return 'pygate.local'
        except Exception:
            return 'pygate.local'

    def list_newsgroups(self) -> List[Tuple[str, str, str, str]]:
        """List available newsgroups"""
        if not self.connection and not self.connect():
            return []

        try:
            resp, groups = self.connection.list()
            newsgroups = []

            for group_info in groups:
                name = group_info.group
                last_num = group_info.last
                first_num = group_info.first
                flag = group_info.flag
                newsgroups.append((name, last_num, first_num, flag))

            return newsgroups

        except Exception as e:
            self.logger.error(f"Error listing newsgroups: {e}")
            return []

    def test_connection(self) -> bool:
        """Test NNTP connection"""
        if self.connect():
            self.disconnect()
            return True
        return False
