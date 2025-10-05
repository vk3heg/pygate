#!/usr/bin/env python3
"""
PyGate FidoNet Module
Handles FidoNet packet parsing and creation
"""

import os
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import logging


class FidoNetModule:
    """FidoNet packet handling module for PyGate"""

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.pending_messages = []

    def generate_tearline(self) -> str:
        """Generate tear line with OS and version info"""
        import platform

        # Get PyGate version from config
        version = self.config.get('Gateway', 'version')

        # Get operating system
        os_name = platform.system()
        if os_name == 'Linux':
            os_display = 'Linux'
        elif os_name == 'Windows':
            os_display = 'Windows'
        elif os_name == 'Darwin':
            os_display = 'macOS'
        else:
            os_display = os_name  # Fall back to actual system name

        return f"PyGate {os_display} v{version}"

    def parse_packet(self, packet_path: str) -> List[Dict[str, Any]]:
        """Parse FidoNet packet and return list of messages"""
        messages = []

        try:
            with open(packet_path, 'rb') as f:
                # Read packet header (58 bytes)
                header_data = f.read(58)
                if len(header_data) < 58:
                    self.logger.error(f"File too small for packet header")
                    return messages

                self.logger.debug(f"Read {len(header_data)} header bytes")

                # Read messages
                message_count = 0
                while True:
                    # Read message header (14 bytes)
                    msg_header = f.read(14)
                    if len(msg_header) < 14:
                        self.logger.debug("End of file or incomplete message header")
                        break

                    # Unpack message header
                    version, orig_node, dest_node, orig_net, dest_net, attrib, cost = struct.unpack('<HHHHHHH', msg_header)
                    self.logger.debug(f"Message {message_count + 1} header:")
                    self.logger.debug(f"  Version: {version}")
                    self.logger.debug(f"  From: {orig_net}/{orig_node}")
                    self.logger.debug(f"  To: {dest_net}/{dest_node}")

                    if version == 0:  # End of packet marker
                        self.logger.debug("Found end of packet marker")
                        break

                    # Validate this is a real message header (version should be 2)
                    if version != 2:
                        self.logger.debug(f"Invalid message version {version}, this is likely data, not a message header")
                        break

                    # Read null-terminated strings
                    msg_date = self.read_null_string(f)
                    msg_to = self.read_null_string(f)
                    msg_from = self.read_null_string(f)
                    msg_subject = self.read_null_string(f)
                    self.logger.debug(f"  Date: '{msg_date}'")
                    self.logger.debug(f"  To: '{msg_to}'")
                    self.logger.debug(f"  From: '{msg_from}'")
                    self.logger.debug(f"  Subject: '{msg_subject}'")

                    # Read message body
                    body_lines = []
                    control_lines = []
                    area = ''

                    while True:
                        line = self.read_line(f)
                        if line is None:  # End of file
                            self.logger.debug("Reached end of file while reading body")
                            break
                        if line == '':  # End of message (null terminator) - but could also be empty line
                            # Check if this is truly the end by reading ahead
                            pos = f.tell()
                            next_byte = f.read(1)
                            if not next_byte or next_byte == b'\x00':
                                self.logger.debug("Found true end of message marker")
                                break
                            else:
                                # It was just an empty line, seek back and continue
                                f.seek(pos)
                                self.logger.debug("Empty line, continuing...")
                                # Don't add empty lines to body, just continue
                                continue

                        self.logger.debug(f"Read line: {repr(line)}")

                        # Check if this is a control line following FSC-0043.002
                        # Control lines have sentinels at beginning of line
                        if line.startswith('\x01'):
                            control_lines.append(line[1:])  # Remove ^A
                            self.logger.debug(f"Control line: {line[1:]}")
                        elif line.startswith('AREA:'):
                            # AREA: must be first non-^a line in echomail
                            area = line[5:].strip()
                            control_lines.append(line)
                            self.logger.debug(f"Area: {area}")
                        elif line.startswith('SEEN-BY:'):
                            # Part of echomail trailer
                            control_lines.append(line)
                            self.logger.debug(f"Echomail SEEN-BY: {line}")
                        elif line.startswith('---'):
                            # Tear line - part of echomail trailer
                            control_lines.append(line)
                            self.logger.debug(f"FidoNet tear line: {line}")
                        elif line.startswith(' * Origin:'):
                            # Origin line - note the leading space as per FSC-0043.002
                            control_lines.append(line)
                            self.logger.debug(f"FidoNet origin line: {line}")
                        elif line.startswith('# Origin:'):
                            # Internetworking gateway origin line
                            control_lines.append(line)
                            self.logger.debug(f"Gateway origin line: {line}")
                        else:
                            # Don't process quoted control lines or those with leading blanks/tabs
                            stripped = line.lstrip(' \t')
                            if (not stripped.startswith('\x01') and
                                not stripped.startswith('AREA:') and
                                not stripped.startswith('SEEN-BY:') and
                                not stripped.startswith('---') and
                                not stripped.startswith(' * Origin:')):
                                body_lines.append(line)
                                self.logger.debug(f"Message text: {line}")
                            else:
                                # Quoted or indented control line - treat as regular text
                                body_lines.append(line)
                                self.logger.debug(f"Quoted control line (treated as text): {line}")

                    message = {
                        'to_name': msg_to,
                        'from_name': msg_from,
                        'subject': msg_subject,
                        'text': '\n'.join(body_lines),
                        'control_lines': control_lines,
                        'orig_net': orig_net,
                        'orig_node': orig_node,
                        'dest_net': dest_net,
                        'dest_node': dest_node,
                        'date_written': msg_date,
                        'attr': attrib,
                        'area': area,
                        'datetime': datetime.now()  # Will be parsed properly later
                    }

                    # Extract MSGID and other kludges from control lines
                    self.extract_message_ids(message)

                    # Debug logging
                    self.logger.debug(f"Parsed message body lines: {body_lines}")
                    self.logger.debug(f"Final message text: '{message['text']}'")
                    self.logger.debug(f"Message text length: {len(message['text'])}")
                    self.logger.debug(f"Control lines: {control_lines}")
                    self.logger.debug(f"Area: '{area}'")

                    messages.append(message)
                    message_count += 1
                    self.logger.debug(f"Parsed message {message_count}:")
                    self.logger.debug(f"  Body: {repr(message['text'])}")
                    self.logger.debug(f"  Control lines: {control_lines}")
                    self.logger.debug(f"  Area: {area}")

                    # After reading one message, check for next message
                    save_pos = f.tell()
                    next_header = f.read(14)
                    if len(next_header) < 14:
                        self.logger.debug("No more data for another message")
                        break
                    next_version = struct.unpack('<H', next_header[:2])[0]
                    if next_version != 2 and next_version != 0:
                        self.logger.debug(f"Next data doesn't look like a message header (version={next_version}), stopping")
                        break

                    # Seek back to read the header properly in next iteration
                    f.seek(save_pos)

                self.logger.debug(f"Total messages parsed: {len(messages)}")

        except Exception as e:
            self.logger.error(f"Error parsing packet {packet_path}: {e}")
            import traceback
            traceback.print_exc()

        self.logger.info(f"Parsed {len(messages)} messages from {packet_path}")
        return messages

    def parse_packet_header(self, header_data: bytes) -> Dict[str, Any]:
        """Parse FidoNet packet header"""
        # FidoNet Type 2+ packet header structure (58 bytes)
        fields = struct.unpack('<HHHHHHHHHHHHBB8sHHHH4s', header_data)

        header = {
            'orig_node': fields[0],
            'dest_node': fields[1],
            'year': fields[2],
            'month': fields[3],
            'day': fields[4],
            'hour': fields[5],
            'minute': fields[6],
            'second': fields[7],
            'baud': fields[8],
            'packet_type': fields[9],
            'orig_net': fields[10],
            'dest_net': fields[11],
            'prod_code_low': fields[12],
            'prod_revision': fields[13],
            'password': fields[14].decode('ascii', errors='ignore').rstrip('\x00'),
            'qm_orig_zone': fields[15],
            'qm_dest_zone': fields[16],
            'aux_net': fields[17],
            'cap_valid': fields[18],
            'prod_code_high': fields[19],
            'prod_data': fields[20].decode('ascii', errors='ignore').rstrip('\x00'),
            'cap_word': fields[21].decode('ascii', errors='ignore').rstrip('\x00')
        }

        return header

    def parse_message(self, f, packet_header: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a single FidoNet message"""
        try:
            # Read message header (12 more bytes after the type)
            msg_header_data = f.read(12)
            if len(msg_header_data) < 12:
                return None

            # Parse message header - format similar to fidonet_areafix_gateway.py
            orig_node, dest_node, orig_net, dest_net, attrib, cost = struct.unpack('<HHHHHH', msg_header_data)

            message = {
                'orig_node': orig_node,
                'dest_node': dest_node,
                'orig_net': orig_net,
                'dest_net': dest_net,
                'attr': attrib,
                'cost': cost,
            }

            # Read null-terminated strings
            message['date_written'] = self.read_null_string(f)
            message['to_name'] = self.read_null_string(f)
            message['from_name'] = self.read_null_string(f)
            message['subject'] = self.read_null_string(f)

            # Read message text line by line (similar to fidonet_areafix_gateway.py)
            body_lines = []
            control_lines = []
            area = ''

            while True:
                line = self.read_line(f)
                if line is None:  # End of file
                    break
                if line == '':  # End of message (null terminator)
                    break

                # Check if this is a control line following FSC-0043.002
                # Control lines have sentinels at beginning of line only
                if line.startswith('\x01'):
                    control_lines.append(line[1:])  # Remove ^A
                elif line.startswith('AREA:'):
                    area = line[5:].strip()
                    control_lines.append(line)
                elif line.startswith('SEEN-BY:'):
                    control_lines.append(line)
                elif line.startswith('---'):
                    control_lines.append(line)
                elif line.startswith(' * Origin:'):
                    control_lines.append(line)
                elif line.startswith('# Origin:'):
                    control_lines.append(line)
                else:
                    # Don't process quoted or indented control lines
                    stripped = line.lstrip(' \t')
                    if (not stripped.startswith('\x01') and
                        not stripped.startswith('AREA:') and
                        not stripped.startswith('SEEN-BY:')):
                        body_lines.append(line)
                    else:
                        body_lines.append(line)  # Treat as regular text

            message['text'] = '\n'.join(body_lines)
            message['area'] = area
            message['control_lines'] = control_lines

            # Parse kludges (control lines starting with \x01)
            message['kludges'] = self.parse_kludges(message['text'])

            # Set datetime
            message['datetime'] = message.get('date_written', datetime.now())

            # Extract origin, msgid, reply etc. from kludges
            self.extract_message_ids(message)

            return message

        except Exception as e:
            self.logger.error(f"Error parsing message: {e}")
            return None

    def read_null_string(self, f) -> str:
        """Read null-terminated string from file"""
        result = bytearray()
        while True:
            byte = f.read(1)
            if not byte or byte == b'\x00':
                break
            result.extend(byte)
        return result.decode('cp437', errors='replace')

    def read_line(self, f) -> Optional[str]:
        """Read a line until CR, LF, or null"""
        result = b''
        while True:
            byte = f.read(1)
            if not byte:  # EOF
                return None
            if byte == b'\x00':  # End of message
                return ''
            if byte == b'\r':
                # Check for CRLF
                next_byte = f.read(1)
                if next_byte == b'\n':
                    break  # CRLF
                else:
                    f.seek(-1, 1)  # Put back the byte
                    break  # Just CR
            elif byte == b'\n':
                break  # LF
            result += byte
        return result.decode('cp437', errors='ignore')

    def parse_fido_datetime(self, date_bytes: bytes) -> datetime:
        """Parse FidoNet datetime format"""
        try:
            date_str = date_bytes.decode('ascii', errors='ignore').rstrip('\x00 ')
            # Format: "DD MMM YY  HH:MM:SS"
            if len(date_str) >= 19:
                day = int(date_str[0:2])
                month_str = date_str[3:6]
                year = int(date_str[7:9])
                if year < 80:
                    year += 2000
                else:
                    year += 1900
                hour = int(date_str[11:13])
                minute = int(date_str[14:16])
                second = int(date_str[17:19])

                month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                             'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                month = month_names.index(month_str) + 1

                return datetime(year, month, day, hour, minute, second)
        except:
            pass

        return datetime.now()

    def parse_kludges(self, text: str) -> Dict[str, str]:
        """Parse kludge lines from message text"""
        kludges = {}
        lines = text.split('\n')

        for line in lines:
            if line.startswith('\x01'):
                kludge_line = line[1:].strip()
                if ':' in kludge_line:
                    key, value = kludge_line.split(':', 1)
                    kludges[key.upper().strip()] = value.strip()
                else:
                    # Some kludges don't have colons
                    parts = kludge_line.split(' ', 1)
                    if len(parts) >= 2:
                        kludges[parts[0].upper()] = parts[1]
                    else:
                        kludges[parts[0].upper()] = ''

        return kludges

    def extract_message_ids(self, message: Dict[str, Any]):
        """Extract message IDs and other info from kludges"""
        kludges = message.get('kludges', {})

        # Also check control_lines for kludges (they may have been separated during parsing)
        control_lines = message.get('control_lines', [])
        for line in control_lines:
            if line.startswith('MSGID:'):
                kludges['MSGID'] = line[6:].strip()
            elif line.startswith('REPLY:'):
                kludges['REPLY'] = line[6:].strip()
            elif line.startswith('TID:'):
                kludges['TID'] = line[4:].strip()
            elif line.startswith('PID:'):
                kludges['PID'] = line[4:].strip()
            elif line.startswith('TZUTC:'):
                kludges['TZUTC'] = line[6:].strip()
            elif line.startswith('TZUTCINFO:'):
                # FTS-4008.002 line 68-69: TZUTCINFO is identical to TZUTC
                kludges['TZUTC'] = line[10:].strip()
            elif line.startswith('CHRS:'):
                kludges['CHRS'] = line[5:].strip()
            elif line.startswith('CHARSET:'):
                # FTS-5003.001: CHARSET is synonym for CHRS
                kludges['CHRS'] = line[8:].strip()
            elif line.startswith('CODEPAGE:'):
                # FTS-5003.001: Obsolete CODEPAGE kludge, used with IBMPC
                # Should override CHRS: IBMPC identifier
                codepage = line[9:].strip()
                if codepage.isdigit():
                    kludges['CHRS'] = f"CP{codepage} 2"

        message['msgid'] = kludges.get('MSGID', '')
        message['reply'] = kludges.get('REPLY', '')
        message['tzutc'] = kludges.get('TZUTC', '')
        message['chrs'] = kludges.get('CHRS', '')
        message['origin'] = ''

        # Look for origin line in text
        text_lines = message['text'].split('\n')
        for line in reversed(text_lines):
            if line.strip().startswith('* Origin:'):
                message['origin'] = line.strip()[9:].strip()
                break

    def create_message(self, message: Dict[str, Any], area: str) -> bool:
        """Add message to pending messages for packet creation"""
        try:
            # Add area and other FidoNet-specific fields
            fido_message = {
                'area': area,
                'from_name': message.get('from_name', 'Unknown'),
                'to_name': message.get('to_name', 'All'),
                'subject': message.get('subject', ''),
                'text': message.get('text', ''),
                'datetime': message.get('datetime', datetime.now()),
                'orig_node': self.get_our_node(),
                'orig_net': self.get_our_net(),
                'dest_node': self.get_dest_node(area),
                'dest_net': self.get_dest_net(area),
                'attr': 0,  # Message attributes
                'msgid': message.get('msgid', ''),
                'reply': message.get('reply', ''),
                'origin': message.get('origin', self.get_our_origin()),
                # Preserve kludge fields
                'pid': message.get('pid', ''),
                'tid': message.get('tid', ''),
                'chrs': message.get('chrs', ''),
                'tzutc': message.get('tzutc', ''),
                'replyaddr': message.get('replyaddr', ''),
                'replyto': message.get('replyto', ''),
                'tearline': message.get('tearline', ''),
                'seen_by': message.get('seen_by', []),
                'path': message.get('path', [])
            }

            self.pending_messages.append(fido_message)
            return True

        except Exception as e:
            self.logger.error(f"Error creating FidoNet message: {e}")
            return False

    def create_packets(self) -> bool:
        """Create FidoNet packets from pending messages"""
        if not self.pending_messages:
            self.logger.info("No messages to pack")
            return True

        try:
            # Group messages by destination
            dest_groups = {}
            for message in self.pending_messages:
                dest_key = f"{message['dest_net']}/{message['dest_node']}"
                if dest_key not in dest_groups:
                    dest_groups[dest_key] = []
                dest_groups[dest_key].append(message)

            # Create packet for each destination
            packets_created = 0
            for dest_key, messages in dest_groups.items():
                packet_path = self.create_packet_file(messages)
                if packet_path:
                    packets_created += 1
                    self.logger.info(f"Created packet {packet_path} with {len(messages)} messages")

            # Clear pending messages
            self.pending_messages.clear()

            self.logger.info(f"Created {packets_created} packets")
            return True

        except Exception as e:
            self.logger.error(f"Error creating packets: {e}")
            return False

    def create_packet_file(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        """Create a FidoNet packet file"""
        if not messages:
            return None

        try:
            outbound_dir = self.config.get('Files', 'outbound_dir')
            os.makedirs(outbound_dir, exist_ok=True)

            # Generate packet filename in 8.3 DOS format
            now = datetime.now()
            # Use 8 hex digits for filename (based on timestamp)
            timestamp = int(now.timestamp())
            packet_name = f"{timestamp:08x}.pkt"
            packet_path = os.path.join(outbound_dir, packet_name)

            # If file exists, increment timestamp to avoid collision
            while os.path.exists(packet_path):
                timestamp += 1
                packet_name = f"{timestamp:08x}.pkt"
                packet_path = os.path.join(outbound_dir, packet_name)

            with open(packet_path, 'wb') as f:
                # Write packet header
                self.write_packet_header(f, messages[0])

                # Write messages
                for message in messages:
                    self.write_message(f, message)

                # Write end-of-packet marker
                f.write(struct.pack('<H', 0))

            return packet_path

        except Exception as e:
            self.logger.error(f"Error creating packet file: {e}")
            return None

    def write_packet_header(self, f, first_message: Dict[str, Any]):
        """Write FidoNet packet header (58 bytes)"""
        now = datetime.now()

        # Get our address (gateway address) - must be configured
        gateway_addr = self.config.get('FidoNet', 'gateway_address')
        if not gateway_addr:
            raise ValueError("gateway_address must be configured in [FidoNet] section")
        our_address = self.parse_fido_address(gateway_addr)

        # Get destination address from linked_address configuration - must be configured
        linked_addr = self.config.get('FidoNet', 'linked_address')
        if not linked_addr:
            raise ValueError("linked_address must be configured in [FidoNet] section")
        dest_address = self.parse_fido_address(linked_addr)

        password = self.config.get('FidoNet', 'packet_password').encode('ascii')[:8]
        password = password.ljust(8, b'\x00')

        # FidoNet Type 2+ packet header (58 bytes total per FTS-0001)
        # Build header in parts to ensure exact 58 bytes
        # Note: Some tools expect 0-based months (Jan=0) based on pktinfo behavior
        header_part1 = struct.pack('<HHHHHHHHHHHHBB8s',
            our_address['node'],          # orig_node (H) - 0
            dest_address['node'],         # dest_node (H) - 2
            now.year,                     # year (H) - 4
            now.month - 1,                # month (H) - 6 (0-based: Jan=0)
            now.day,                      # day (H) - 8
            now.hour,                     # hour (H) - 10
            now.minute,                   # minute (H) - 12
            now.second,                   # second (H) - 14
            0,                            # baud rate (H) - 16
            2,                            # packet type (H) - 18
            our_address['net'],           # orig_net (H) - 20
            dest_address['net'],          # dest_net (H) - 22
            0,                            # product code low (B) - 24
            0,                            # product revision (B) - 25
            password                      # password (8s) - 26-33
        )

        # Type 2+ fields matching SoupGate structure exactly (offset 34-57)
        dest_zone = dest_address['zone']  # Get zone from parsed destination address
        header_part2 = struct.pack('<HHHHBBHHHHHI',
            our_address['zone'],          # qm_orig_zone (H) - 34
            dest_zone,                    # qm_dest_zone (H) - 36
            0,                            # aux_net (H) - 38
            0x0100,                       # cwvalidate (H) - 40
            1,                            # pcodehigh (B) - 42
            0,                            # prevminor (B) - 43
            0x0001,                       # capword (H) - 44
            our_address.get('zone', 1),   # orig_zone (H) - 46
            dest_zone,                    # dest_zone (H) - 48
            0,                            # orig_point (H) - 50
            0,                            # dest_point (H) - 52
            0                             # extrainfo (I) - 54
        )

        # Header should be exactly 58 bytes
        header_data = header_part1 + header_part2

        f.write(header_data)

    def write_message(self, f, message: Dict[str, Any]):
        """Write a FidoNet message to packet following FSC-0043.002"""

        # Message type (2 = normal message)
        f.write(struct.pack('<H', 2))

        # Message header (12 bytes)
        msg_header = struct.pack('<HHHHHH',
            message['orig_node'],
            message['dest_node'],
            message['orig_net'],
            message['dest_net'],
            message['attr'],
            0   # cost
        )

        f.write(msg_header)

        # Write date string (exactly 20 bytes, NOT null terminated per FTS-0001.016)
        date_str = message['datetime'].strftime('%d %b %y  %H:%M:%S')
        # Ensure exactly 20 bytes by padding or truncating
        date_bytes = date_str.encode('cp437', errors='replace')
        if len(date_bytes) < 20:
            date_bytes = date_bytes.ljust(20, b' ')  # Pad with spaces
        elif len(date_bytes) > 20:
            date_bytes = date_bytes[:20]  # Truncate
        f.write(date_bytes)  # No null terminator for DateTime field

        # Validate and truncate to_name to 35 chars (36 bytes - 1 null terminator)
        to_name = message['to_name']
        if len(to_name) > 35:
            to_name = to_name[:35]
            self.logger.warning(f"Truncated to_name from {len(message['to_name'])} to 35 chars: {message['to_name']}")
        f.write(to_name.encode('cp437', errors='replace') + b'\x00')

        # Validate and truncate from_name to 35 chars (36 bytes - 1 null terminator)
        from_name = message['from_name']
        if len(from_name) > 35:
            from_name = from_name[:35]
            self.logger.warning(f"Truncated from_name from {len(message['from_name'])} to 35 chars: {message['from_name']}")
        f.write(from_name.encode('cp437', errors='replace') + b'\x00')

        # Truncate subject line to 71 characters (72 bytes - 1 null terminator)
        subject = message['subject']
        if len(subject) > 71:
            subject = subject[:71]
            self.logger.warning(f"Truncated subject from {len(message['subject'])} to 71 chars: {message['subject']}")
        f.write(subject.encode('cp437', errors='replace') + b'\x00')

        # Build message text according to FSC-0043.002
        text_lines = []

        # For echomail: AREA: line must be first non-^a line
        if message.get('area'):
            text_lines.append(f"AREA:{message['area']}")

        # Add kludges (^a control lines)
        # For netmail: Add INTL kludge first (FTS-5001)
        if not message.get('area'):  # Netmail only
            # INTL format: ^aINTL <dest_zone>:<dest_net>/<dest_node> <orig_zone>:<orig_net>/<orig_node>
            dest_zone = message.get('dest_zone', 0)
            dest_net = message.get('dest_net', 0)
            dest_node = message.get('dest_node', 0)
            orig_zone = message.get('orig_zone', 0)
            orig_net = message.get('orig_net', 0)
            orig_node = message.get('orig_node', 0)
            text_lines.append(f"\x01INTL {dest_zone}:{dest_net}/{dest_node} {orig_zone}:{orig_net}/{orig_node}")

        if message.get('msgid'):
            text_lines.append(f"\x01MSGID: {message['msgid']}")
        if message.get('reply'):
            text_lines.append(f"\x01REPLY: {message['reply']}")

        # Add other kludges as needed
        if message.get('pid'):
            text_lines.append(f"\x01PID: {message['pid']}")
        if message.get('tid'):
            text_lines.append(f"\x01TID: {message['tid']}")
        if message.get('chrs'):
            text_lines.append(f"\x01CHRS: {message['chrs']}")
        if message.get('tzutc'):
            text_lines.append(f"\x01TZUTC: {message['tzutc']}")
        if message.get('replyaddr'):
            text_lines.append(f"\x01REPLYADDR {message['replyaddr']}")
        if message.get('replyto'):
            text_lines.append(f"\x01REPLYTO {message['replyto']}")

        # Add message text body
        if message.get('text'):
            # Filter out LF and soft CR/LF as per FSC-0043.002
            # Also remove null bytes which are used as FidoNet message terminators
            cleaned_text = message['text'].replace('\x00', '').replace('\n', '\r').replace('\r\r', '\r')
            text_lines.append(cleaned_text)

        # Add echomail trailer for echomail only (4-part package)
        if message.get('area'):
            # Add blank line before tear line
            text_lines.append('')

            # 1. Tear line
            tear_line = message.get('tearline', self.generate_tearline())
            if not tear_line.startswith('---'):
                tear_line = f"--- {tear_line}"
            text_lines.append(tear_line)

            # 2. Origin line (note the leading space before *)
            origin_text = message.get('origin', self.get_our_origin())
            text_lines.append(f" * Origin: {origin_text}")

            # 3. SEEN-BY lines (should be managed by mail processor)
            seen_by = message.get('seen_by', [])
            if seen_by:
                # Format SEEN-BY with net/node abbreviation
                seen_by_line = "SEEN-BY:"
                current_net = None
                for address in seen_by:
                    if '/' in address:
                        net, node = address.split('/')
                        if net != current_net:
                            seen_by_line += f" {net}/{node}"
                            current_net = net
                        else:
                            seen_by_line += f" {node}"
                    else:
                        seen_by_line += f" {address}"
                text_lines.append(seen_by_line)

            # 4. PATH lines (routing path)
            path = message.get('path', [])
            if path:
                path_line = "\x01PATH:"
                current_net = None
                for address in path:
                    if '/' in address:
                        net, node = address.split('/')
                        if net != current_net:
                            path_line += f" {net}/{node}"
                            current_net = net
                        else:
                            path_line += f" {node}"
                    else:
                        path_line += f" {address}"
                text_lines.append(path_line)

        # Write message text
        message_text = '\r'.join(text_lines)
        f.write(message_text.encode('cp437', errors='replace') + b'\x00')

    def get_our_node(self) -> int:
        """Get our FidoNet node number"""
        gateway_addr = self.config.get('FidoNet', 'gateway_address')
        if not gateway_addr:
            raise ValueError("gateway_address must be configured in [FidoNet] section")
        address = self.parse_fido_address(gateway_addr)
        return address['node']

    def get_our_net(self) -> int:
        """Get our FidoNet net number"""
        gateway_addr = self.config.get('FidoNet', 'gateway_address')
        if not gateway_addr:
            raise ValueError("gateway_address must be configured in [FidoNet] section")
        address = self.parse_fido_address(gateway_addr)
        return address['net']

    def get_dest_node(self, area: str) -> int:
        """Get destination node for area"""
        # Use linked system address as default destination
        linked_addr = self.config.get('FidoNet', 'linked_address')
        if not linked_addr:
            raise ValueError("linked_address must be configured in [FidoNet] section")
        linked_address = self.parse_fido_address(linked_addr)
        return linked_address['node']

    def get_dest_net(self, area: str) -> int:
        """Get destination net for area"""
        # Use linked system address as default destination
        linked_addr = self.config.get('FidoNet', 'linked_address')
        if not linked_addr:
            raise ValueError("linked_address must be configured in [FidoNet] section")
        linked_address = self.parse_fido_address(linked_addr)
        return linked_address['net']

    def get_our_origin(self) -> str:
        """Get our origin line"""
        gateway_addr = self.config.get('FidoNet', 'gateway_address')
        if not gateway_addr:
            raise ValueError("gateway_address must be configured in [FidoNet] section")
        origin_name = self.config.get('FidoNet', 'origin_line')
        return f"{origin_name} ({gateway_addr})"

    def get_our_address(self) -> str:
        """Get our full FidoNet address"""
        gateway_addr = self.config.get('FidoNet', 'gateway_address')
        if not gateway_addr:
            raise ValueError("gateway_address must be configured in [FidoNet] section")
        return gateway_addr

    def format_address_for_seenby(self, address: str) -> str:
        """Format FidoNet address for SEEN-BY line (net/node format)"""
        parsed = self.parse_fido_address(address)
        return f"{parsed['net']}/{parsed['node']}"

    def parse_fido_address(self, address: str) -> Dict[str, int]:
        """Parse FidoNet address string"""
        # Format: zone:net/node[.point][@domain]
        result = {'zone': 1, 'net': 234, 'node': 5, 'point': 0}

        try:
            # Remove domain part
            if '@' in address:
                address = address.split('@')[0]

            # Split zone:net/node.point
            if ':' in address:
                zone_part, rest = address.split(':', 1)
                result['zone'] = int(zone_part)
            else:
                rest = address

            if '/' in rest:
                net_part, node_part = rest.split('/', 1)
                result['net'] = int(net_part)

                if '.' in node_part:
                    node, point = node_part.split('.', 1)
                    result['node'] = int(node)
                    result['point'] = int(point)
                else:
                    result['node'] = int(node_part)

        except ValueError as e:
            self.logger.error(f"Invalid FidoNet address format: {address}")

        return result

    def validate_packet(self, packet_path: str) -> bool:
        """Validate FidoNet packet structure"""
        try:
            with open(packet_path, 'rb') as f:
                # Check packet header
                header_data = f.read(58)
                if len(header_data) < 58:
                    return False

                header = self.parse_packet_header(header_data)

                # Check password
                expected_password = self.config.get('FidoNet', 'packet_password')
                if expected_password and header.get('password', '') != expected_password:
                    self.logger.warning(f"Password mismatch in packet {packet_path}")
                    return False

                return True

        except Exception as e:
            self.logger.error(f"Error validating packet {packet_path}: {e}")
            return False
