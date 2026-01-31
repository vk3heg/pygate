"""
PyGate - Python FidoNet-NNTP Gateway
Based on SoupGate by Tom Torfs

A modular Python implementation of FidoNet <-> NNTP gateway functionality.
"""


def get_version():
    """Get version from main pygate module"""
    try:
        import pygate
        return pygate.__version__
    except (ImportError, AttributeError):
        return '1.5.8'  # Fallback if pygate module not yet loaded


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
