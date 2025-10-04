"""
PyGate - Python FidoNet-NNTP Gateway
Based on SoupGate by Tom Torfs

A modular Python implementation of FidoNet <-> NNTP gateway functionality.
"""

__version__ = "1.0"
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