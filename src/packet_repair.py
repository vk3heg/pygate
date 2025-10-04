#!/usr/bin/env python3
"""
PyGate Packet Repair Utility

Repairs FidoNet packets that have embedded null bytes in message text.
Null bytes are used as message terminators in FidoNet, so embedded nulls
in NNTP message bodies can corrupt packets.

This utility scans packets for embedded nulls and removes them from message text
while preserving the packet structure.
"""

import struct
import os
from typing import List, Dict, Optional, Tuple
import logging


class PacketRepairError(Exception):
    """Exception raised for packet repair errors"""
    pass


class PacketRepairer:
    """FidoNet packet repair utility"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    def read_null_string(self, data: bytes, pos: int) -> Tuple[bytes, int]:
        """Read null-terminated string from data"""
        result = bytearray()
        start_pos = pos
        while pos < len(data) and data[pos] != 0:
            result.append(data[pos])
            pos += 1
        if pos < len(data):
            pos += 1  # Skip the null terminator
        return bytes(result), pos

    def analyze_packet(self, packet_data: bytes) -> Dict:
        """
        Analyze packet structure and find embedded nulls in message text

        Returns:
            dict with keys:
                - valid: bool - whether packet structure is valid
                - messages: int - number of messages found
                - embedded_nulls: list of dicts with position info
                - errors: list of error strings
        """
        result = {
            'valid': True,
            'messages': 0,
            'embedded_nulls': [],
            'errors': []
        }

        if len(packet_data) < 58:
            result['valid'] = False
            result['errors'].append("Packet too small for header")
            return result

        pos = 58  # Start after packet header

        while pos < len(packet_data) - 2:
            # Read message version
            if pos + 2 > len(packet_data):
                break

            version = struct.unpack('<H', packet_data[pos:pos+2])[0]

            if version == 0:  # Packet terminator
                self.logger.debug(f"Found packet terminator at {pos:#06x}")
                break

            if version != 2:
                # This might be embedded nulls causing misalignment
                result['errors'].append(f"Unexpected version {version:#04x} at position {pos:#06x}")
                break

            result['messages'] += 1
            message_start = pos
            self.logger.debug(f"Processing message {result['messages']} at {pos:#06x}")

            # Skip message header (14 bytes)
            pos += 14

            # Read the 4 null-terminated strings (date, to, from, subject)
            for field_name in ['date', 'to', 'from', 'subject']:
                if pos >= len(packet_data):
                    result['errors'].append(f"Unexpected EOF reading {field_name} in message {result['messages']}")
                    result['valid'] = False
                    return result

                field_data, pos = self.read_null_string(packet_data, pos)
                self.logger.debug(f"  {field_name}: {len(field_data)} bytes")

            # Now read message text, looking for embedded nulls
            text_start = pos

            while pos < len(packet_data):
                if packet_data[pos] == 0:
                    # Check if this is the real message terminator
                    is_terminator = False

                    if pos + 1 < len(packet_data):
                        next_byte = packet_data[pos + 1]
                        if next_byte == 0:  # 00 00 = packet terminator
                            is_terminator = True
                        elif pos + 2 < len(packet_data):
                            next_word = struct.unpack('<H', packet_data[pos+1:pos+3])[0]
                            if next_word == 2:  # 00 02 00 = next message header
                                is_terminator = True

                    if is_terminator:
                        self.logger.debug(f"  Message text ends at {pos:#06x}")
                        pos += 1  # Move past the terminator
                        break
                    else:
                        # This is an embedded null
                        self.logger.warning(f"  Found embedded null at {pos:#06x}")
                        result['embedded_nulls'].append({
                            'message': result['messages'],
                            'position': pos,
                            'text_offset': pos - text_start,
                            'context': bytes(packet_data[max(0, pos-10):min(len(packet_data), pos+10)])
                        })

                pos += 1

        return result

    def repair_packet(self, packet_data: bytes) -> bytes:
        """
        Repair packet by removing embedded nulls from message text

        Args:
            packet_data: Original packet data as bytes

        Returns:
            Repaired packet data as bytes

        Raises:
            PacketRepairError: If packet structure is invalid
        """
        # Analyze first
        analysis = self.analyze_packet(packet_data)

        if not analysis['valid']:
            raise PacketRepairError(f"Invalid packet structure: {'; '.join(analysis['errors'])}")

        if not analysis['embedded_nulls']:
            self.logger.info("No embedded nulls found, packet is clean")
            return packet_data

        self.logger.info(f"Found {len(analysis['embedded_nulls'])} embedded null(s) to repair")

        # Rebuild packet without embedded nulls
        output = bytearray()
        output.extend(packet_data[0:58])  # Copy packet header

        pos = 58
        message_num = 0

        while pos < len(packet_data) - 2:
            # Read message version
            if pos + 2 > len(packet_data):
                break

            version = struct.unpack('<H', packet_data[pos:pos+2])[0]

            if version == 0:  # Packet terminator
                output.extend(b'\x00\x00')
                break

            if version != 2:
                break

            message_num += 1

            # Copy message header (14 bytes)
            output.extend(packet_data[pos:pos+14])
            pos += 14

            # Copy the 4 null-terminated strings
            for field_name in ['date', 'to', 'from', 'subject']:
                field_data, pos = self.read_null_string(packet_data, pos)
                output.extend(field_data)
                output.append(0)  # Null terminator

            # Read message text and filter out embedded nulls
            text_data = bytearray()

            while pos < len(packet_data):
                byte = packet_data[pos]
                pos += 1

                if byte == 0:
                    # Check if this is the message terminator
                    is_terminator = False

                    if pos < len(packet_data):
                        next_byte = packet_data[pos]
                        if next_byte == 0:  # Packet end
                            is_terminator = True
                        elif pos + 1 < len(packet_data):
                            next_word = struct.unpack('<H', packet_data[pos:pos+2])[0]
                            if next_word == 2:  # Next message
                                is_terminator = True

                    if is_terminator:
                        # Real terminator - write text and terminator
                        output.extend(text_data)
                        output.append(0)
                        break
                    else:
                        # Embedded null - skip it
                        self.logger.debug(f"Skipping embedded null in message {message_num} at position {pos-1:#06x}")
                        continue

                text_data.append(byte)

        return bytes(output)

    def repair_file(self, input_path: str, output_path: Optional[str] = None, backup: bool = True) -> Dict:
        """
        Repair a FidoNet packet file

        Args:
            input_path: Path to packet file to repair
            output_path: Path for repaired file (default: input_path with .repaired extension)
            backup: Whether to create backup of original file

        Returns:
            dict with repair statistics
        """
        if not os.path.exists(input_path):
            raise PacketRepairError(f"Input file not found: {input_path}")

        # Read original packet
        with open(input_path, 'rb') as f:
            original_data = f.read()

        original_size = len(original_data)
        self.logger.info(f"Read {original_size} bytes from {input_path}")

        # Analyze first
        analysis = self.analyze_packet(original_data)

        # Repair
        repaired_data = self.repair_packet(original_data)
        repaired_size = len(repaired_data)

        # Determine output path
        if output_path is None:
            if analysis['embedded_nulls']:
                # Has issues, use .repaired extension
                output_path = input_path + '.repaired'
            else:
                # Clean packet, no output needed
                return {
                    'input_file': input_path,
                    'original_size': original_size,
                    'repaired_size': repaired_size,
                    'messages': analysis['messages'],
                    'embedded_nulls': len(analysis['embedded_nulls']),
                    'bytes_removed': 0,
                    'status': 'clean'
                }

        # Create backup if requested
        if backup and os.path.exists(input_path):
            backup_path = input_path + '.bak'
            with open(backup_path, 'wb') as f:
                f.write(original_data)
            self.logger.info(f"Created backup: {backup_path}")

        # Write repaired packet
        with open(output_path, 'wb') as f:
            f.write(repaired_data)

        result = {
            'input_file': input_path,
            'output_file': output_path,
            'original_size': original_size,
            'repaired_size': repaired_size,
            'messages': analysis['messages'],
            'embedded_nulls': len(analysis['embedded_nulls']),
            'bytes_removed': original_size - repaired_size,
            'status': 'repaired'
        }

        self.logger.info(f"Repaired packet written to {output_path}")
        self.logger.info(f"Removed {result['bytes_removed']} embedded null byte(s)")

        return result


def main():
    """Command-line interface for packet repair"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Repair FidoNet packets with embedded null bytes',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze a packet
  %(prog)s --analyze badfile.pkt

  # Repair a packet
  %(prog)s badfile.pkt

  # Repair without backup
  %(prog)s --no-backup badfile.pkt

  # Specify output file
  %(prog)s badfile.pkt -o fixed.pkt
        """
    )

    parser.add_argument('input_file', help='Input packet file')
    parser.add_argument('-o', '--output', help='Output file (default: input + .repaired)')
    parser.add_argument('-a', '--analyze', action='store_true', help='Only analyze, do not repair')
    parser.add_argument('--no-backup', action='store_true', help='Do not create backup file')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('-q', '--quiet', action='store_true', help='Quiet mode, only errors')

    args = parser.parse_args()

    # Setup logging
    log_level = logging.INFO
    if args.verbose:
        log_level = logging.DEBUG
    elif args.quiet:
        log_level = logging.ERROR

    logging.basicConfig(
        level=log_level,
        format='%(levelname)s: %(message)s'
    )

    logger = logging.getLogger(__name__)
    repairer = PacketRepairer(logger)

    try:
        if args.analyze:
            # Analyze only
            with open(args.input_file, 'rb') as f:
                packet_data = f.read()

            analysis = repairer.analyze_packet(packet_data)

            print(f"Packet: {args.input_file}")
            print(f"Size: {len(packet_data)} bytes")
            print(f"Valid: {analysis['valid']}")
            print(f"Messages: {analysis['messages']}")
            print(f"Embedded nulls: {len(analysis['embedded_nulls'])}")

            if analysis['errors']:
                print("\nErrors:")
                for error in analysis['errors']:
                    print(f"  - {error}")

            if analysis['embedded_nulls']:
                print("\nEmbedded null locations:")
                for null in analysis['embedded_nulls']:
                    print(f"  Message {null['message']}, position {null['position']:#06x}")
                    print(f"    Context: {null['context'].hex(' ')}")

            return 0 if analysis['valid'] and not analysis['embedded_nulls'] else 1

        else:
            # Repair
            result = repairer.repair_file(
                args.input_file,
                args.output,
                backup=not args.no_backup
            )

            print(f"Status: {result['status']}")
            print(f"Messages: {result['messages']}")
            print(f"Original size: {result['original_size']} bytes")
            print(f"Repaired size: {result['repaired_size']} bytes")

            if result['bytes_removed'] > 0:
                print(f"Removed: {result['bytes_removed']} embedded null byte(s)")
                print(f"Output: {result['output_file']}")

            return 0

    except PacketRepairError as e:
        logger.error(str(e))
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
