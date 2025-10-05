#!/usr/bin/env python3
"""
PyGate Core Gateway Module
Handles the main gateway operations between FidoNet and NNTP
"""

import os
import sys
import logging
import configparser
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from .nntp_module import NNTPModule
from .fidonet_module import FidoNetModule
from .areafix_module import AreafixModule
from .spam_filter import SpamFilterModule
from .hold_module import MessageHoldModule


class Gateway:
    """Core PyGate Gateway class"""

    def __init__(self, config_file: str = "pygate.cfg", load_spam_filter: bool = True):
        self.config_file = config_file
        self.config = configparser.ConfigParser()

        # Default configuration
        self.setup_default_config()

        # Load configuration
        self.load_config()

        # Setup logging
        self.setup_logging()

        # Initialize modules
        self.nntp = NNTPModule(self.config, self.logger)
        self.fidonet = FidoNetModule(self.config, self.logger)
        self.areafix = AreafixModule(self.config, self.logger)

        # Lazy load spam filter (not needed for areafix-only operations)
        self._spam_filter = None
        if load_spam_filter:
            self._spam_filter = SpamFilterModule(self.config, self.logger)

        self.hold_module = MessageHoldModule(self.config, self.logger)

        self.logger.info("PyGate gateway initialized")

    @property
    def spam_filter(self):
        """Lazy load spam filter on first access"""
        if self._spam_filter is None:
            self.logger.info("Lazy loading spam filter module")
            self._spam_filter = SpamFilterModule(self.config, self.logger)
        return self._spam_filter

    def setup_default_config(self):
        """Setup default configuration"""
        self.config['Gateway'] = {
            'name': 'PyGate',
            'version': '1.0',
            'debug': 'false',
            'log_level': 'INFO',
            'origin_line': 'PyGate'
        }

        self.config['FidoNet'] = {
            'gateway_address': '',
            'linked_address': '',
            'packet_password': '',
            'areafix_password': ''
        }

        self.config['NNTP'] = {
            'host': '',
            'port': '119',
            'username': '',
            'password': '',
            'use_ssl': 'false',
            'timeout': '30'
        }

        self.config['Mapping'] = {
            'areas_file': 'areas.cfg',
            'default_newsgroup': '',
            'gate_email': 'gate@example.com'
        }

        self.config['Files'] = {}

    def load_config(self):
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            try:
                self.config.read(self.config_file)
                print(f"Configuration loaded from {self.config_file}")
            except Exception as e:
                print(f"Error loading config: {e}")
        else:
            self.create_default_config()

    def create_default_config(self):
        """Create default configuration file"""
        with open(self.config_file, 'w') as f:
            self.config.write(f)
        print(f"Created default configuration file: {self.config_file}")
        print("Please edit the configuration file with your settings.")

    def setup_logging(self):
        """Setup logging configuration"""
        log_level = self.config.get('Gateway', 'log_level')
        log_file = self.config.get('Files', 'log_file')

        # Setup logging format with custom date format
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        date_format = '%d-%b-%y %H:%M:%S'  # Day-Month-Year format (e.g., 23-Sep-25 16:30:45)

        # Setup file handler
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format=log_format,
            datefmt=date_format,
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )

        self.logger = logging.getLogger('PyGate')

    def import_packets(self) -> bool:
        """Import FidoNet packets and gate to NNTP (MODE_IMPORT equivalent)"""
        self.logger.info("Starting packet import operation")

        try:
            # First, process any approved held messages for NNTP posting
            self.process_approved_messages_to_nntp()

            inbound_dir = self.config.get('Files', 'inbound_dir')
            if not os.path.exists(inbound_dir):
                self.logger.warning(f"Inbound directory {inbound_dir} does not exist")
                return True  # Not an error if no inbound

            packets_processed = 0

            # Process all .pkt files in inbound
            for packet_file in Path(inbound_dir).glob("*.pkt"):
                self.logger.info(f"Processing packet: {packet_file}")

                try:
                    # Parse FidoNet packet
                    messages = self.fidonet.parse_packet(str(packet_file))

                    # Track messages by area
                    area_stats = {}
                    packet_areafix = 0

                    for message in messages:
                        # Check if it's an areafix message
                        if self.areafix.is_areafix_message(message):
                            self.areafix.process_areafix_message(message)
                            packet_areafix += 1
                        else:
                            area = message.get('area', 'NETMAIL')

                            # Initialize area stats if not exists
                            if area not in area_stats:
                                area_stats[area] = {'gated': 0, 'filtered': 0, 'failed': 0}

                            # Apply spam filter
                            if not self.spam_filter.is_spam(message):
                                # Load area configuration (used for both holding and gating)
                                areas = self.load_areas_config()
                                area_config = areas.get(area, {'newsgroup': area.lower()})

                                # Check if message should be held for review (FidoNet to NNTP direction)
                                if self.hold_module.should_hold_message(message, area):
                                    # Hold the original FidoNet message for review
                                    hold_id = self.hold_module.hold_message(message, area, direction="nntp")
                                    if hold_id:
                                        self.logger.info(f"FidoNet message held for review: {hold_id}")
                                    # Count as filtered since it's not being posted immediately
                                    area_stats[area]['filtered'] += 1
                                else:
                                    # Gate to NNTP
                                    nntp_message = self.convert_fido_to_nntp(message, area_config)
                                    success = self.nntp.post_message(nntp_message)
                                    if success:
                                        area_stats[area]['gated'] += 1
                                    else:
                                        area_stats[area]['failed'] += 1
                            else:
                                area_stats[area]['filtered'] += 1

                    # Log summary for each area in this packet
                    for area, stats in area_stats.items():
                        if stats['gated'] > 0 or stats['filtered'] > 0 or stats['failed'] > 0:
                            self.logger.info(f"Area {area}: {stats['gated']} gated, {stats['filtered']} filtered, {stats['failed']} failed")

                    # Log areafix messages if any
                    if packet_areafix > 0:
                        self.logger.info(f"Areafix: {packet_areafix} processed")

                    # Move processed packet
                    processed_dir = Path(inbound_dir) / "processed"
                    processed_dir.mkdir(exist_ok=True)
                    packet_file.rename(processed_dir / packet_file.name)
                    packets_processed += 1

                except Exception as e:
                    self.logger.error(f"Error processing packet {packet_file}: {e}")
                    # Move to bad directory
                    bad_dir = Path(inbound_dir) / "bad"
                    bad_dir.mkdir(exist_ok=True)
                    packet_file.rename(bad_dir / packet_file.name)

            self.logger.info(f"Import complete: {packets_processed} packets processed")
            return True

        except Exception as e:
            self.logger.error(f"Error during import: {e}")
            return False

    def process_areafix_only(self) -> bool:
        """Process only areafix messages from packets (no spam filtering needed)"""
        self.logger.info("Starting areafix-only processing")

        try:
            inbound_dir = self.config.get('Files', 'inbound_dir')
            if not os.path.exists(inbound_dir):
                self.logger.warning(f"Inbound directory {inbound_dir} does not exist")
                return True  # Not an error if no inbound

            packets_processed = 0
            areafix_total = 0

            # Process all .pkt files in inbound
            for packet_file in Path(inbound_dir).glob("*.pkt"):
                self.logger.info(f"Processing packet for areafix: {packet_file}")

                try:
                    # Parse FidoNet packet
                    messages = self.fidonet.parse_packet(str(packet_file))

                    packet_areafix = 0
                    packet_other = 0

                    for message in messages:
                        # Only process areafix messages
                        if self.areafix.is_areafix_message(message):
                            self.areafix.process_areafix_message(message)
                            packet_areafix += 1
                        else:
                            # Count non-areafix messages
                            packet_other += 1

                    # Log areafix messages if any
                    if packet_areafix > 0:
                        self.logger.info(f"Areafix: {packet_areafix} processed from {packet_file.name}")
                        areafix_total += packet_areafix

                    # Only move packet if it contained ONLY areafix messages
                    # If it has other messages, leave it for the next import cycle
                    if packet_other == 0:
                        # Move processed packet (only areafix messages)
                        processed_dir = Path(inbound_dir) / "processed"
                        processed_dir.mkdir(exist_ok=True)
                        packet_file.rename(processed_dir / packet_file.name)
                        packets_processed += 1
                    else:
                        # Leave packet in inbound for next import cycle
                        self.logger.info(f"Packet {packet_file.name} has {packet_other} non-areafix message(s), leaving in inbound for next import cycle")
                        packets_processed += 1

                except Exception as e:
                    self.logger.error(f"Error processing packet {packet_file}: {e}")
                    # Move to bad directory
                    bad_dir = Path(inbound_dir) / "bad"
                    bad_dir.mkdir(exist_ok=True)
                    packet_file.rename(bad_dir / packet_file.name)

            self.logger.info(f"Areafix processing complete: {areafix_total} messages from {packets_processed} packets")
            return True

        except Exception as e:
            self.logger.error(f"Error during areafix processing: {e}")
            return False

    def export_messages(self) -> bool:
        """Export NNTP messages to FidoNet packets (MODE_EXPORT equivalent)"""
        self.logger.info("Starting message export operation")

        try:
            # First, process any approved held messages
            self.process_approved_messages()

            # Get areas configuration
            areas = self.load_areas_config()
            if not areas:
                self.logger.warning("No areas configured for export")
                return True

            messages_exported = 0

            for area_tag, area_config in areas.items():
                newsgroup = area_config.get('newsgroup')
                if not newsgroup:
                    continue

                self.logger.info(f"Processing area {area_tag} -> {newsgroup}")

                try:
                    # Fetch messages from NNTP
                    messages = self.nntp.fetch_messages(newsgroup, area_config)

                    area_exported = 0
                    area_filtered = 0
                    area_failed = 0

                    for message in messages:
                        # Apply spam filter
                        if not self.spam_filter.is_spam(message):
                            # Check if message should be held for review
                            if self.hold_module.should_hold_message(message, area_tag):
                                # Hold message for review
                                hold_id = self.hold_module.hold_message(message, area_tag, direction="fidonet")
                                if hold_id:
                                    self.logger.info(f"Message held for review: {hold_id}")
                                # Count as filtered since it's not being sent immediately
                                area_filtered += 1
                            else:
                                # Convert and create FidoNet message
                                fido_message = self.convert_nntp_to_fido(message, area_tag, area_config)

                                # Add to outbound
                                success = self.fidonet.create_message(fido_message, area_tag)
                                if success:
                                    messages_exported += 1
                                    area_exported += 1
                                else:
                                    area_failed += 1
                        else:
                            area_filtered += 1

                    # Log summary for this area
                    if area_exported > 0 or area_filtered > 0 or area_failed > 0:
                        self.logger.info(f"Area {area_tag}: {area_exported} exported, {area_filtered} filtered, {area_failed} failed")
                    else:
                        self.logger.info(f"Area {area_tag}: no new messages")

                except Exception as e:
                    self.logger.error(f"Error processing area {area_tag}: {e}")

            # Create outbound packets from exported messages
            if messages_exported > 0:
                self.logger.info(f"Packing {messages_exported} exported messages into FidoNet packets...")
                packet_success = self.fidonet.create_packets()
                if packet_success:
                    self.logger.info("All exported messages successfully packed into packets")
                else:
                    self.logger.error("Failed to pack some exported messages")
                    return False
            else:
                self.logger.info("No new messages to pack")

            # Save updated areas configuration
            if self.save_areas_config(areas):
                self.logger.info("Areas configuration updated with new article numbers")
            else:
                self.logger.warning("Failed to update areas configuration")

            self.logger.info(f"Export and pack complete: {messages_exported} messages exported and packed")
            return True

        except Exception as e:
            self.logger.error(f"Error during export: {e}")
            return False

    def process_approved_messages(self) -> bool:
        """Process approved held messages and post them"""
        self.logger.info("Processing approved held messages")

        try:
            approved_messages = self.hold_module.get_approved_messages()
            if not approved_messages:
                self.logger.info("No approved messages to process")
                return True

            messages_posted = 0
            messages_failed = 0

            for approved_record in approved_messages:
                try:
                    # Check message direction from the hold record
                    direction = approved_record.get('direction', 'unknown')

                    if direction in ['fidonet', 'fido']:
                        # This message is meant for FidoNet posting (came from NNTP)
                        # Get the original message
                        original_message = self.hold_module.release_approved_message(approved_record['hold_id'])
                        if not original_message:
                            self.logger.error(f"Failed to retrieve approved message {approved_record['hold_id']}")
                            messages_failed += 1
                            continue

                        area_tag = approved_record['area_tag']

                        # Get area configuration
                        areas = self.load_areas_config()
                        area_config = areas.get(area_tag, {})

                        if not area_config:
                            self.logger.error(f"No area configuration found for {area_tag}")
                            messages_failed += 1
                            continue

                        # Convert and create FidoNet message
                        fido_message = self.convert_nntp_to_fido(original_message, area_tag, area_config)

                        # Add to outbound
                        success = self.fidonet.create_message(fido_message, area_tag)
                        if success:
                            messages_posted += 1
                            self.logger.info(f"Posted approved message {approved_record['hold_id']} to {area_tag}")
                        else:
                            messages_failed += 1
                            self.logger.error(f"Failed to post approved message {approved_record['hold_id']}")
                    else:
                        # This message should be handled by the NNTP processing
                        # (it came from FidoNet and is going to NNTP)
                        continue

                except Exception as e:
                    self.logger.error(f"Error processing approved message {approved_record.get('hold_id', 'unknown')}: {e}")
                    messages_failed += 1

            if messages_posted > 0:
                self.logger.info(f"Creating packets for {messages_posted} approved messages...")
                packet_success = self.fidonet.create_packets()
                if packet_success:
                    self.logger.info(f"Successfully posted {messages_posted} approved messages")
                else:
                    self.logger.error("Failed to create packets for approved messages")
                    return False

            if messages_failed > 0:
                self.logger.warning(f"{messages_failed} approved messages failed to post")

            self.logger.info(f"Approved message processing complete: {messages_posted} posted, {messages_failed} failed")
            return True

        except Exception as e:
            self.logger.error(f"Error processing approved messages: {e}")
            return False

    def process_approved_messages_to_nntp(self) -> bool:
        """Process approved held messages and post them to NNTP"""
        self.logger.info("Processing approved held messages for NNTP posting")

        try:
            approved_messages = self.hold_module.get_approved_messages()
            if not approved_messages:
                self.logger.info("No approved messages to post to NNTP")
                return True

            messages_posted = 0
            messages_failed = 0

            for approved_record in approved_messages:
                try:
                    # Check message direction from the hold record BEFORE releasing
                    direction = approved_record.get('direction', 'unknown')

                    if direction != 'nntp':
                        # This message should be handled by the FidoNet processing
                        # (it came from NNTP and is going to FidoNet)
                        # Skip it - don't release it here
                        continue

                    # Get the original message (only for NNTP-bound messages)
                    original_message = self.hold_module.release_approved_message(approved_record['hold_id'])
                    if not original_message:
                        self.logger.error(f"Failed to retrieve approved message {approved_record['hold_id']}")
                        messages_failed += 1
                        continue

                    # This message is meant for NNTP posting (came from FidoNet)
                    # Restore area information from hold record
                    original_message['area'] = approved_record['area_tag']
                    success = self.nntp.post_message(original_message)
                    if success:
                        messages_posted += 1
                        self.logger.info(f"Posted approved message {approved_record['hold_id']} to NNTP")
                    else:
                        messages_failed += 1
                        self.logger.error(f"Failed to post approved message {approved_record['hold_id']} to NNTP")

                except Exception as e:
                    self.logger.error(f"Error processing approved NNTP message {approved_record.get('hold_id', 'unknown')}: {e}")
                    messages_failed += 1

            if messages_failed > 0:
                self.logger.warning(f"{messages_failed} approved NNTP messages failed to post")

            self.logger.info(f"Approved NNTP message processing complete: {messages_posted} posted, {messages_failed} failed")
            return True

        except Exception as e:
            self.logger.error(f"Error processing approved NNTP messages: {e}")
            return False

    def get_area_name_for_newsgroup(self, newsgroup: str) -> str:
        """Get FidoNet area name for newsgroup, checking [Arearemap] section first"""
        # Check for explicit mapping in [Arearemap] section
        if self.config.has_section('Arearemap'):
            try:
                for fido_area, mapped_newsgroup in self.config.items('Arearemap'):
                    if mapped_newsgroup == newsgroup:
                        return fido_area.upper()
            except Exception as e:
                self.logger.error(f"Error reading Arearemap section: {e}")

        # Default: use newsgroup name as area name
        return newsgroup

    def load_areas_config(self) -> Dict[str, Dict[str, Any]]:
        """Load areas configuration file"""
        areas_file = self.config.get('Files', 'areas_file')
        areas = {}

        if not os.path.exists(areas_file):
            self.logger.warning(f"Areas file {areas_file} not found")
            return areas

        try:
            with open(areas_file, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()

                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue

                    # Parse format: newsgroup_name: low-high
                    if ':' in line:
                        newsgroup, range_part = line.split(':', 1)
                        newsgroup = newsgroup.strip()
                        range_part = range_part.strip()

                        # Parse range (e.g., "0-17" or "0-0")
                        if '-' in range_part:
                            try:
                                low_str, high_str = range_part.split('-', 1)
                                low_msg = int(low_str.strip())
                                high_msg = int(high_str.strip())

                                # Get proper FidoNet area name for this newsgroup
                                area_tag = self.get_area_name_for_newsgroup(newsgroup)

                                areas[area_tag] = {
                                    'newsgroup': newsgroup,
                                    'enabled': True,
                                    'last_article': high_msg,
                                    'low_message': low_msg,
                                    'high_message': high_msg
                                }

                            except ValueError as e:
                                self.logger.warning(f"Invalid range format on line {line_num}: {range_part}")
                        else:
                            self.logger.warning(f"Invalid format on line {line_num}: missing '-' in range")
                    else:
                        self.logger.warning(f"Invalid format on line {line_num}: missing ':'")

            self.logger.info(f"Loaded {len(areas)} areas from {areas_file}")

        except Exception as e:
            self.logger.error(f"Error loading areas config: {e}")

        return areas

    def save_areas_config(self, areas: Dict[str, Dict[str, Any]]) -> bool:
        """Save updated areas configuration back to file"""
        areas_file = self.config.get('Files', 'areas_file')

        try:
            # Create backup
            backup_file = f"{areas_file}.bak"
            if os.path.exists(areas_file):
                import shutil
                shutil.copy2(areas_file, backup_file)

            with open(areas_file, 'w') as f:
                f.write("# PyGate Areas Configuration\n")
                f.write("# Format: newsgroup_name: low_message-high_message\n")
                f.write("# Example: comp.sys.amiga.demos: 0-53\n")
                f.write("\n")

                for area_tag, area_config in areas.items():
                    newsgroup = area_config.get('newsgroup', '')
                    if newsgroup:
                        low_msg = area_config.get('low_message', 0)
                        high_msg = area_config.get('last_article', area_config.get('high_message', 0))
                        f.write(f"{newsgroup}: {low_msg}-{high_msg}\n")

            self.logger.info(f"Updated areas configuration saved to {areas_file}")
            return True

        except Exception as e:
            self.logger.error(f"Error saving areas config: {e}")
            return False

    def parse_message_date(self, date_value):
        """Parse date from message, handling both datetime objects and strings"""
        if isinstance(date_value, datetime):
            return date_value
        elif isinstance(date_value, str):
            try:
                # Try parsing ISO format first (common in JSON)
                if 'T' in date_value or '+' in date_value:
                    # Handle ISO format with T or space
                    if ' ' in date_value and 'T' not in date_value:
                        # Convert space to T for ISO parsing
                        date_value = date_value.replace(' ', 'T', 1)

                    if date_value.endswith('+00:00'):
                        return datetime.fromisoformat(date_value)
                    elif 'Z' in date_value:
                        return datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                    else:
                        return datetime.fromisoformat(date_value)
                else:
                    # Try parsing other common formats
                    from email.utils import parsedate_to_datetime
                    return parsedate_to_datetime(date_value)
            except (ValueError, TypeError):
                # If parsing fails, return current time
                return datetime.now()
        else:
            return datetime.now()

    def convert_nntp_to_fido(self, nntp_message: Dict[str, Any], area_tag: str, area_config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert NNTP message to FidoNet format following FSC-0043.002"""
        gateway_address = self.config.get('FidoNet', 'gateway_address')
        if not gateway_address:
            raise ValueError("gateway_address must be configured in [FidoNet] section")

        # Parse the date properly
        message_date = self.parse_message_date(nntp_message.get('date', datetime.now()))

        fido_message = {
            'area': area_tag,
            'from_name': nntp_message.get('from_name', 'Unknown'),
            'to_name': area_config.get('default_to', 'All'),
            'subject': nntp_message.get('subject', ''),
            'datetime': message_date,
            'text': nntp_message.get('body', ''),
            'origin': f"{self.config.get('FidoNet', 'origin_line')} ({gateway_address})",
            'msgid': self.generate_fido_msgid(nntp_message.get('message_id', '')),
            'reply': self.generate_fido_reply(nntp_message.get('references', '')),
            # FSC-0043.002 echomail trailer components
            'tearline': self.generate_tearline(),
            'pid': f"PyGate {self.config.get('Gateway', 'version')}",
            'tid': self.generate_tid(),
            # Additional kludges for compatibility
            'chrs': self.determine_best_charset(nntp_message.get('subject', '') + ' ' + nntp_message.get('body', '')),
            'tzutc': self.generate_tzutc_offset(message_date),
            # REPLYADDR for return email address (FSC-0035.001)
            'replyaddr': nntp_message.get('from_email', ''),
            # REPLYTO for FidoNet routing (FSC-0035.001)
            'replyto': f"{gateway_address} UUCP",
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

    def get_linked_address(self) -> str:
        """Get linked FidoNet address from config"""
        linked_address = self.config.get('FidoNet', 'linked_address')
        if not linked_address:
            raise ValueError("linked_address must be configured in [FidoNet] section")
        return linked_address

    def generate_fido_msgid(self, nntp_message_id: str = '') -> str:
        """Generate FidoNet MSGID from NNTP Message-ID or create new one"""
        import hashlib
        import time
        import binascii

        if nntp_message_id:
            # Use the original NNTP Message-ID and add CRC32
            message_id = nntp_message_id.strip('<>')

            # Calculate CRC32 of the message ID
            crc32_value = binascii.crc32(message_id.encode('utf-8')) & 0xffffffff
            crc32_hex = f"{crc32_value:08x}"

            return f"<{message_id}> {crc32_hex}"
        else:
            # Generate a new Message-ID in RFC format
            import uuid
            import socket

            # Try to get a reasonable hostname
            try:
                hostname = socket.getfqdn()
                if hostname == 'localhost' or '.' not in hostname:
                    hostname = self.config.get('Gateway', 'domain', 'gateway.local')
            except:
                hostname = self.config.get('Gateway', 'domain', 'gateway.local')

            # Generate unique message ID
            unique_id = str(uuid.uuid4()).replace('-', '')[:16]
            timestamp = f"{int(time.time()):08x}"
            message_id = f"{unique_id}{timestamp}@{hostname}"

            # Calculate CRC32
            crc32_value = binascii.crc32(message_id.encode('utf-8')) & 0xffffffff
            crc32_hex = f"{crc32_value:08x}"

            return f"<{message_id}> {crc32_hex}"

    def generate_fido_reply(self, references: str) -> str:
        """Generate FidoNet REPLY from NNTP References (use only immediate parent)"""
        import binascii

        if not references:
            return ''

        # References contains space-separated Message-IDs, we want the last one (immediate parent)
        refs = references.strip().split()
        if not refs:
            return ''

        # Get the last (most recent) reference
        parent_msgid = refs[-1].strip('<>')

        # Calculate CRC32 of the parent message ID
        crc32_value = binascii.crc32(parent_msgid.encode('utf-8')) & 0xffffffff
        crc32_hex = f"{crc32_value:08x}"

        return f"<{parent_msgid}> {crc32_hex}"

    def generate_tzutc_offset(self, message_date: datetime) -> str:
        """Generate TZUTC offset per FTS-4008.002 specification"""
        from datetime import timezone

        # If message_date is naive (no timezone), assume it's local time
        if message_date.tzinfo is None:
            # Get local timezone offset
            import time
            if time.daylight:
                # Daylight saving time is in effect
                offset_seconds = -time.altzone
            else:
                # Standard time
                offset_seconds = -time.timezone
        else:
            # Message has timezone info, calculate offset from UTC
            utc_offset = message_date.utcoffset()
            if utc_offset is not None:
                offset_seconds = int(utc_offset.total_seconds())
            else:
                offset_seconds = 0

        # Convert seconds to hours and minutes
        # Handle negative offsets properly
        if offset_seconds < 0:
            abs_seconds = abs(offset_seconds)
            offset_hours = abs_seconds // 3600
            offset_minutes = (abs_seconds % 3600) // 60
            return f"-{offset_hours:02d}{offset_minutes:02d}"
        else:
            offset_hours = offset_seconds // 3600
            offset_minutes = (offset_seconds % 3600) // 60
            return f"{offset_hours:02d}{offset_minutes:02d}"

    def generate_tearline(self) -> str:
        """Generate tear line with OS and version info"""
        import platform

        # Get PyGate version
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

    def generate_tid(self) -> str:
        """Generate TID (Tosser ID) with platform identifier following FidoNet conventions"""
        import platform

        # Get PyGate version
        version = self.config.get('Gateway', 'version')

        # Get operating system - use short form for TID
        os_name = platform.system()
        if os_name == 'Linux':
            os_short = 'Linux'
        elif os_name == 'Windows':
            os_short = 'Windows'
        elif os_name == 'Darwin':
            os_short = 'macOS'
        else:
            os_short = os_name

        # Format: "PyGate/Platform Version" (e.g., "PyGate/Linux 1.0")
        return f"PyGate/{os_short} {version}"

    def parse_tzutc_offset(self, tzutc_str: str, message_date: datetime) -> datetime:
        """Parse TZUTC offset and apply to datetime per FTS-4008.002"""
        if not tzutc_str or len(tzutc_str) < 4:
            return message_date

        try:
            # Parse TZUTC format: [-]hhmm
            # Per FTS-4008.002: robust implementations should accept and ignore optional plus
            if tzutc_str.startswith('-'):
                sign = -1
                offset_str = tzutc_str[1:]
            elif tzutc_str.startswith('+'):
                sign = 1
                offset_str = tzutc_str[1:]  # Strip optional plus per spec
            else:
                sign = 1
                offset_str = tzutc_str

            if len(offset_str) >= 4:
                hours = int(offset_str[:2])
                minutes = int(offset_str[2:4])

                # Convert to total seconds
                total_seconds = sign * (hours * 3600 + minutes * 60)

                # Create timezone object
                from datetime import timezone, timedelta
                tz = timezone(timedelta(seconds=total_seconds))

                # If message_date is naive, assume it's in the TZUTC timezone
                if message_date.tzinfo is None:
                    return message_date.replace(tzinfo=tz)
                else:
                    # Convert to the specified timezone
                    return message_date.astimezone(tz)

        except (ValueError, IndexError):
            pass

        return message_date

    def get_charset_encoding(self, chrs_str: str) -> str:
        """Get Python encoding name from FTS-5003.001 CHRS identifier"""
        if not chrs_str:
            return 'cp437'  # Default to CP437 per FTS-5003.001 recommendations

        # Parse CHRS: <identifier> <level> format
        parts = chrs_str.strip().split()
        if not parts:
            return 'cp437'

        identifier = parts[0].upper()

        # FTS-5003.001 Level 2 character sets (eight-bit, ASCII based)
        charset_map = {
            'CP437': 'cp437',      # IBM codepage 437 (DOS Latin US)
            'CP850': 'cp850',      # IBM codepage 850 (DOS Latin 1)
            'CP852': 'cp852',      # IBM codepage 852 (DOS Latin 2)
            'CP866': 'cp866',      # IBM codepage 866 (Cyrillic Russian)
            'CP848': 'cp1125',     # IBM codepage 848 (Cyrillic Ukrainian) - closest match
            'CP1250': 'cp1250',    # Windows, Eastern Europe
            'CP1251': 'cp1251',    # Windows, Cyrillic
            'CP1252': 'cp1252',    # Windows, Western Europe
            'CP10000': 'mac-roman', # Macintosh Roman character set
            'LATIN-1': 'iso-8859-1',  # ISO 8859-1 (Western European)
            'LATIN-2': 'iso-8859-2',  # ISO 8859-2 (Eastern European)
            'LATIN-5': 'iso-8859-9',  # ISO 8859-9 (Turkish)
            'LATIN-9': 'iso-8859-15', # ISO 8859-15 (Western Europe with EURO sign)
            # Level 4
            'UTF-8': 'utf-8',      # UTF-8 encoding for the Unicode character set
            # Level 1 (seven-bit) - rarely used but included for completeness
            'ASCII': 'ascii',      # ISO 646-1 (US ASCII)
            # Obsolete identifiers that should still be handled
            'IBMPC': 'cp437',      # IBM PC character sets - treat as CP437
            '+7_FIDO': 'cp866',    # Synonym for CP866
            'MAC': 'mac-roman',    # Macintosh character set
        }

        return charset_map.get(identifier, 'cp437')

    def convert_text_encoding(self, text: str, from_charset: str, to_charset: str = 'utf-8') -> str:
        """Convert text between character encodings"""
        if not text or from_charset == to_charset:
            return text

        try:
            # If text is already UTF-8, try to decode it first
            if isinstance(text, str):
                # Encode to bytes using source charset, then decode as UTF-8
                if from_charset == 'utf-8':
                    return text
                # For conversion from other charsets, we need to assume text is in that charset
                # This is a limitation - in practice, text encoding detection would be better
                encoded_bytes = text.encode('latin1')  # Preserve byte values
                decoded_text = encoded_bytes.decode(from_charset, errors='replace')
                if to_charset == 'utf-8':
                    return decoded_text
                else:
                    return decoded_text.encode(to_charset, errors='replace').decode(to_charset)
            else:
                # Text is bytes
                decoded_text = text.decode(from_charset, errors='replace')
                if to_charset == 'utf-8':
                    return decoded_text
                else:
                    return decoded_text.encode(to_charset, errors='replace').decode(to_charset)
        except (UnicodeDecodeError, UnicodeEncodeError, LookupError):
            # If conversion fails, return original text
            return text if isinstance(text, str) else text.decode('utf-8', errors='replace')

    def determine_best_charset(self, text: str) -> str:
        """Determine best FTS-5003.001 charset for text content"""
        if not text:
            return 'ASCII 1'

        # Check if pure ASCII
        try:
            text.encode('ascii')
            return 'ASCII 1'  # Level 1 pure ASCII
        except UnicodeEncodeError:
            pass

        # Check if CP437 (common DOS charset) can represent the text
        try:
            text.encode('cp437')
            return 'CP437 2'  # Level 2 CP437
        except UnicodeEncodeError:
            pass

        # Check if CP1252 (Windows Western) can represent the text
        try:
            text.encode('cp1252')
            return 'CP1252 2'  # Level 2 Windows Western
        except UnicodeEncodeError:
            pass

        # Fall back to UTF-8 for international content
        return 'UTF-8 4'  # Level 4 UTF-8

    def convert_fido_to_nntp(self, fido_message: Dict[str, Any], area_config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert FidoNet message to NNTP format"""
        # Get original datetime and apply TZUTC if present
        original_date = fido_message.get('datetime', datetime.now())
        tzutc_str = fido_message.get('tzutc', '')

        # Apply TZUTC timezone information per FTS-4008.002
        message_date = self.parse_tzutc_offset(tzutc_str, original_date) if tzutc_str else original_date

        # Handle character set conversion per FTS-5003.001
        chrs_str = fido_message.get('chrs', '')
        source_encoding = self.get_charset_encoding(chrs_str)

        # Convert text content to UTF-8 for NNTP
        from_name = self.convert_text_encoding(fido_message.get('from_name', 'Unknown'), source_encoding, 'utf-8')
        subject = self.convert_text_encoding(fido_message.get('subject', ''), source_encoding, 'utf-8')
        body = self.convert_text_encoding(fido_message.get('text', ''), source_encoding, 'utf-8')

        nntp_message = {
            'newsgroup': area_config.get('newsgroup', ''),
            'from_name': from_name,
            'subject': subject,
            'date': message_date,
            'body': body,
            'message_id': fido_message.get('msgid', ''),
            'references': fido_message.get('reply', ''),
            'organization': self.config.get('FidoNet', 'origin_line'),
            'original_charset': chrs_str,  # Keep track of original charset
            'area': fido_message.get('area', '')  # Include FidoNet area for mapping
        }

        return nntp_message

    def pack_messages(self) -> bool:
        """Pack outbound messages into packets"""
        self.logger.info("Packing outbound messages")
        return self.fidonet.create_packets()

    def check_configuration(self) -> bool:
        """
        Check gateway configuration (deprecated - use ConfigValidator instead)

        This method is kept for backward compatibility but delegates to ConfigValidator.
        """
        from .config_validator import ConfigValidator

        validator = ConfigValidator(self.config, self.logger)
        return validator.check_configuration()

    def maintenance(self):
        """Perform maintenance tasks"""
        self.logger.info("Performing maintenance tasks")

        # Clean up old processed packets
        try:
            inbound_dir = Path(self.config.get('Files', 'inbound_dir'))
            processed_dir = inbound_dir / "processed"

            if processed_dir.exists():
                # Remove packets older than 30 days
                import time
                current_time = time.time()

                for packet_file in processed_dir.glob("*.pkt"):
                    if current_time - packet_file.stat().st_mtime > (30 * 24 * 3600):
                        packet_file.unlink()
                        self.logger.info(f"Removed old packet: {packet_file}")

        except Exception as e:
            self.logger.error(f"Error during maintenance: {e}")
