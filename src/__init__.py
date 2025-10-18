"""
PyGate - Python FidoNet-NNTP Gateway
Based on SoupGate by Tom Torfs

A modular Python implementation of FidoNet <-> NNTP gateway functionality.
"""

import configparser
import os


def get_version():
    """Read version from configuration file"""
    try:
        # Look for pygate.cfg in parent directory
        config_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pygate.cfg')
        config = configparser.ConfigParser()
        config.read(config_file)
        return config.get('Gateway', 'version', fallback='1.0')
    except:
        return '1.0'


__version__ = get_version()
__author__ = "Stephen Walsh"
__license__ = "SoupGate Open-Source License"

from .gateway import Gateway
from .nntp_module import NNTPModule
from .fidonet_module import FidoNetModule
from .areafix_module import AreafixModule
from .spam_filter import SpamFilterModule

__all__ = [
    'Gateway',
    'NNTPModule',
    'FidoNetModule',
    'AreafixModule',
    'SpamFilterModule'
]
