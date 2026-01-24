#!/usr/bin/env python3
"""
PyGate - Python FidoNet-NNTP Gateway
Based on SoupGate by Tom Torfs

Main entry point for the gateway system
"""

import sys
import os
import argparse
import signal
import time
import configparser
from pathlib import Path

# Add pygate directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.gateway import Gateway
from src.config_validator import ConfigValidator

# Version string - this is the authoritative version for PyGate
# This overrides any version setting in the config file
__version__ = '1.5.5'


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    print("\nReceived shutdown signal, exiting...")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description='PyGate - Python FidoNet-NNTP Gateway',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --import           Import FidoNet packets and gate to NNTP
  %(prog)s --export           Export NNTP messages and pack into FidoNet packets
  %(prog)s --pack             Pack any pending outbound messages into packets
  %(prog)s --check            Check configuration and test connections
  %(prog)s --areafix          Process areafix requests only
  %(prog)s --maintenance      Perform maintenance tasks

Configuration:
  Edit pygate.cfg to configure FidoNet addresses, NNTP servers, and directories.
        """)

    parser.add_argument('--config', '-c', default='pygate.cfg',
                      help='Configuration file (default: pygate.cfg)')

    # Operation modes (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--import', '-i', action='store_true', dest='import_mode',
                          help='Import FidoNet packets and gate to NNTP')
    mode_group.add_argument('--export', '-e', action='store_true',
                          help='Export NNTP messages and pack into FidoNet packets')
    mode_group.add_argument('--pack', '-p', action='store_true',
                          help='Pack any pending outbound messages into packets')
    mode_group.add_argument('--check', action='store_true',
                          help='Check configuration and test connections')
    mode_group.add_argument('--areafix', '-a', action='store_true',
                          help='Process areafix requests only')
    mode_group.add_argument('--maintenance', '-m', action='store_true',
                          help='Perform maintenance tasks')
    mode_group.add_argument('--process-held', action='store_true',
                          help='Process approved held messages')

    # Additional options
    parser.add_argument('--verbose', '-v', action='store_true',
                      help='Enable verbose output')
    parser.add_argument('--dry-run', action='store_true',
                      help='Dry run mode (no actual changes)')
    parser.add_argument('--version', action='version',
                      version=f'PyGate {__version__}')

    args = parser.parse_args()

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Print banner
    print(f"PyGate v{__version__} - Python FidoNet-NNTP Gateway")
    print("Based on SoupGate by Tom Torfs")
    print("Copyright (c) 2025-2026 by Stephen Walsh")
    print()

    # Initialize gateway
    # Skip spam filter loading for operations that don't need it (performance optimization)
    # Spam filter is only needed for import and export operations
    load_spam_filter = args.import_mode or args.export

    try:
        gateway = Gateway(args.config, load_spam_filter=load_spam_filter)
    except Exception as e:
        print(f"Error initializing gateway: {e}")
        sys.exit(1)

    # Execute requested operation
    success = True

    try:
        if args.import_mode:
            print("Starting import operation...")
            success = gateway.import_packets()

        elif args.export:
            print("Starting export operation...")
            success = gateway.export_messages()

        elif args.pack:
            print("Starting pack operation...")
            success = gateway.pack_messages()

        elif args.check:
            print("Checking configuration...")
            # Use ConfigValidator for comprehensive checks
            validator = ConfigValidator(gateway.config, gateway.logger)
            success = validator.check_configuration()
            if success:
                print("Configuration check passed")
                # Test NNTP connection
                print("Testing NNTP connection...")
                if gateway.nntp.test_connection():
                    print("NNTP connection test passed")
                else:
                    print("NNTP connection test failed")
                    success = False

        elif args.areafix:
            print("Processing areafix requests...")
            success = gateway.process_areafix_only()

        elif args.maintenance:
            print("Performing maintenance...")
            gateway.maintenance()

        elif args.process_held:
            print("Processing approved held messages...")
            success = gateway.process_approved_messages()
            if not success:
                print("Failed to process some approved messages")

    except KeyboardInterrupt:
        print("\nOperation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error during operation: {e}")
        gateway.logger.error(f"Operation failed: {e}")
        success = False

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
