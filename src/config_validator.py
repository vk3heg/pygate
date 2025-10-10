#!/usr/bin/env python3
"""
PyGate Configuration Validator
Validates PyGate configuration and deployment setup
"""

import os
import logging
import configparser
from pathlib import Path
from typing import List, Tuple


class ConfigValidator:
    """Validates PyGate configuration and deployment"""

    def __init__(self, config: configparser.ConfigParser, logger: logging.Logger = None):
        """
        Initialize configuration validator

        Args:
            config: ConfigParser object with loaded configuration
            logger: Logger instance (optional)
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

    def check_configuration(self) -> bool:
        """
        Check gateway configuration and deployment setup

        Returns:
            bool: True if all checks pass, False otherwise
        """
        self.logger.info("Checking PyGate configuration and deployment")

        errors = []

        # Check FidoNet configuration
        if not self.config.get('FidoNet', 'gateway_address', fallback=''):
            errors.append("FidoNet address not configured")

        # Check NNTP configuration
        if not self.config.get('NNTP', 'host', fallback=''):
            errors.append("NNTP host not configured")

        # Check directories
        dirs_to_check = ['inbound_dir', 'outbound_dir', 'temp_dir']
        for dir_key in dirs_to_check:
            dir_path = self.config.get('Files', dir_key, fallback='')
            if dir_path and not os.path.exists(dir_path):
                try:
                    os.makedirs(dir_path, exist_ok=True)
                    self.logger.info(f"Created directory: {dir_path}")
                except Exception as e:
                    errors.append(f"Cannot create directory {dir_path}: {e}")

        # Check for binkd configuration file
        binkd_config_path = os.path.join('config', 'binkd.config')
        if not os.path.exists(binkd_config_path):
            errors.append(f"Binkd configuration file not found: {binkd_config_path}")
        else:
            self.logger.info(f"Found binkd configuration: {binkd_config_path}")

        # Check for binkd binary (Linux and Windows variants)
        binkd_binary_linux = os.path.join('bin', 'binkd')
        binkd_binary_windows = os.path.join('bin', 'binkd.exe')
        binkd_binary_windows_alt = os.path.join('bin', 'BINKDWIN.EXE')

        if os.path.exists(binkd_binary_linux):
            self.logger.info(f"Found binkd binary: {binkd_binary_linux}")
        elif os.path.exists(binkd_binary_windows):
            self.logger.info(f"Found binkd binary: {binkd_binary_windows}")
        elif os.path.exists(binkd_binary_windows_alt):
            self.logger.info(f"Found binkd binary: {binkd_binary_windows_alt}")
        else:
            errors.append(f"Binkd binary not found in bin/ directory (looking for 'binkd', 'binkd.exe', or 'BINKDWIN.EXE')")

        if errors:
            for error in errors:
                self.logger.error(error)
            return False

        self.logger.info("Configuration check passed")
        return True

    def get_validation_report(self) -> Tuple[List[str], List[str]]:
        """
        Get detailed validation report

        Returns:
            Tuple[List[str], List[str]]: (passed_checks, failed_checks)
        """
        passed = []
        failed = []

        # FidoNet configuration
        if self.config.get('FidoNet', 'gateway_address', fallback=''):
            passed.append("✓ FidoNet gateway address configured")
        else:
            failed.append("✗ FidoNet gateway address not configured")

        # NNTP configuration
        if self.config.get('NNTP', 'host', fallback=''):
            passed.append("✓ NNTP host configured")
        else:
            failed.append("✗ NNTP host not configured")

        # Directories
        dirs_to_check = {
            'inbound_dir': 'Inbound directory',
            'outbound_dir': 'Outbound directory',
            'temp_dir': 'Temp directory'
        }

        for dir_key, dir_name in dirs_to_check.items():
            dir_path = self.config.get('Files', dir_key, fallback='')
            if dir_path and os.path.exists(dir_path):
                passed.append(f"✓ {dir_name} exists: {dir_path}")
            elif dir_path:
                failed.append(f"✗ {dir_name} not found: {dir_path}")
            else:
                failed.append(f"✗ {dir_name} not configured")

        # Binkd configuration file
        binkd_config_path = os.path.join('config', 'binkd.config')
        if os.path.exists(binkd_config_path):
            passed.append(f"✓ Binkd configuration found: {binkd_config_path}")
        else:
            failed.append(f"✗ Binkd configuration not found: {binkd_config_path}")

        # Binkd binary
        binkd_binary_linux = os.path.join('bin', 'binkd')
        binkd_binary_windows = os.path.join('bin', 'binkd.exe')
        binkd_binary_windows_alt = os.path.join('bin', 'BINKDWIN.EXE')

        if os.path.exists(binkd_binary_linux):
            passed.append(f"✓ Binkd binary found: {binkd_binary_linux}")
        elif os.path.exists(binkd_binary_windows):
            passed.append(f"✓ Binkd binary found: {binkd_binary_windows}")
        elif os.path.exists(binkd_binary_windows_alt):
            passed.append(f"✓ Binkd binary found: {binkd_binary_windows_alt}")
        else:
            failed.append("✗ Binkd binary not found (looking for bin/binkd, bin/binkd.exe, or bin/BINKDWIN.EXE)")

        return passed, failed
