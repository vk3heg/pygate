#!/usr/bin/env python3
"""
Custom NNTP Client - Replacement for deprecated nntplib

A lightweight NNTP client implementation that provides the functionality
needed by PyGate's filter manager without relying on the deprecated nntplib.
"""

import socket
import ssl
import re
import email
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass


@dataclass
class NNTPResponse:
    """Container for NNTP server responses"""
    code: int
    message: str
    lines: List[bytes] = None


class NNTPError(Exception):
    """Base exception for NNTP errors"""
    pass


class NNTPPermanentError(NNTPError):
    """Exception for NNTP permanent errors (5xx response codes)"""
    def __init__(self, response: NNTPResponse = None, message: str = None):
        if response:
            self.response = response
            super().__init__(f"{response.code} {response.message}")
        else:
            super().__init__(message or "NNTP permanent error")


class NNTPTemporaryError(NNTPError):
    """Exception for NNTP temporary errors (4xx response codes)"""
    def __init__(self, response: NNTPResponse = None, message: str = None):
        if response:
            self.response = response
            super().__init__(f"{response.code} {response.message}")
        else:
            super().__init__(message or "NNTP temporary error")


class NNTPReplyError(NNTPError):
    """Exception for NNTP reply errors"""
    def __init__(self, response: NNTPResponse):
        self.response = response
        super().__init__(f"{response.code} {response.message}")


class NNTPDataError(NNTPError):
    """Exception for NNTP data errors"""
    pass


class CustomNNTPClient:
    """
    Custom NNTP client to replace deprecated nntplib.

    Implements the subset of nntplib functionality needed by filter_manager.py
    """

    def __init__(self, host: str, port: int = 119, timeout: int = 30):
        """Initialize NNTP client"""
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None
        self.file = None
        self.debugging = 0
        self.welcome = None
        self.authenticated = False

    def connect(self) -> NNTPResponse:
        """Connect to NNTP server"""
        try:
            self.sock = socket.create_connection((self.host, self.port), self.timeout)
            self.file = self.sock.makefile('rb')

            # Read welcome message
            self.welcome = self._getresp()
            return self.welcome

        except socket.error as e:
            raise NNTPError(f"Could not connect to {self.host}:{self.port} - {e}")

    def _putline(self, line: str) -> None:
        """Send a line to the server"""
        if self.debugging:
            print(f"*put* {repr(line)}")

        line = line + '\r\n'
        self.sock.sendall(line.encode('utf-8'))

    def _putcmd(self, line: str) -> None:
        """Send a command to the server"""
        if self.debugging:
            print(f"*cmd* {repr(line)}")
        self._putline(line)

    def _getline(self) -> str:
        """Get a line from the server"""
        line = self.file.readline()
        if not line:
            raise NNTPError("Connection lost")

        if line[-2:] == b'\r\n':
            line = line[:-2]
        elif line[-1:] == b'\n':
            line = line[:-1]

        line_str = line.decode('utf-8', errors='replace')
        if self.debugging:
            print(f"*get* {repr(line_str)}")

        return line_str

    def _getresp(self) -> NNTPResponse:
        """Get a response from the server"""
        resp = self._getline()
        if self.debugging:
            print(f"*resp* {repr(resp)}")

        # Parse response code and message
        try:
            code = int(resp[:3])
            message = resp[4:] if len(resp) > 3 else ""
        except ValueError:
            raise NNTPDataError(f"Invalid response format: {resp}")

        return NNTPResponse(code, message)

    def _check_resp(self, resp: NNTPResponse, expected_codes: List[int] = None) -> NNTPResponse:
        """Check response code and raise appropriate exception if error"""
        # Raise appropriate exception based on response code
        if resp.code >= 500:
            raise NNTPPermanentError(resp)
        elif resp.code >= 400:
            raise NNTPTemporaryError(resp)

        # If specific codes expected, verify
        if expected_codes and resp.code not in expected_codes:
            if resp.code >= 500:
                raise NNTPPermanentError(resp)
            elif resp.code >= 400:
                raise NNTPTemporaryError(resp)
            else:
                raise NNTPReplyError(resp)

        return resp

    def _getlongresp(self) -> Tuple[NNTPResponse, List[bytes]]:
        """Get a multi-line response from the server"""
        resp = self._getresp()

        lines = []
        while True:
            line = self.file.readline()
            if not line:
                raise NNTPError("Connection lost during multi-line response")

            if line == b'.\r\n' or line == b'.\n':
                break

            # Handle byte-stuffing (lines starting with '.' are escaped as '..')
            if line.startswith(b'..'):
                line = line[1:]

            # Remove trailing CRLF but keep the line as bytes
            if line.endswith(b'\r\n'):
                line = line[:-2]
            elif line.endswith(b'\n'):
                line = line[:-1]

            lines.append(line)

        return resp, lines

    def _shortcmd(self, line: str) -> NNTPResponse:
        """Send a command and get a single-line response"""
        self._putcmd(line)
        return self._getresp()

    def _longcmd(self, line: str) -> Tuple[NNTPResponse, List[bytes]]:
        """Send a command and get a multi-line response"""
        self._putcmd(line)
        return self._getlongresp()

    def login(self, username: str, password: str) -> None:
        """Authenticate with the NNTP server"""
        # Send username
        resp = self._shortcmd(f'AUTHINFO USER {username}')

        if resp.code == 281:
            # Authentication successful with just username
            self.authenticated = True
            return
        elif resp.code == 381:
            # Password required
            resp = self._shortcmd(f'AUTHINFO PASS {password}')
            if resp.code == 281:
                self.authenticated = True
                return
            else:
                raise NNTPReplyError(resp)
        else:
            raise NNTPReplyError(resp)

    def group(self, name: str) -> Tuple[NNTPResponse, int, int, int, str]:
        """Select a newsgroup"""
        resp = self._shortcmd(f'GROUP {name}')

        if resp.code != 211:
            raise NNTPReplyError(resp)

        # Parse response: "211 count first last group-name"
        parts = resp.message.split()
        if len(parts) < 4:
            raise NNTPDataError(f"Invalid GROUP response: {resp.message}")

        try:
            count = int(parts[0])
            first = int(parts[1])
            last = int(parts[2])
            group_name = parts[3]
        except ValueError:
            raise NNTPDataError(f"Invalid GROUP response numbers: {resp.message}")

        return resp, count, first, last, group_name

    def article(self, message_spec: str) -> Tuple[NNTPResponse, Any]:
        """Retrieve an article"""
        resp, lines = self._longcmd(f'ARTICLE {message_spec}')

        if resp.code != 220:
            raise NNTPReplyError(resp)

        # Return in format compatible with nntplib
        class ArticleInfo:
            def __init__(self, lines):
                self.lines = lines

        return resp, ArticleInfo(lines)

    def head(self, message_spec: str) -> Tuple[NNTPResponse, Any]:
        """Retrieve article headers"""
        resp, lines = self._longcmd(f'HEAD {message_spec}')

        if resp.code != 221:
            raise NNTPReplyError(resp)

        # Return in format compatible with nntplib
        class HeaderInfo:
            def __init__(self, lines):
                self.lines = lines

        return resp, HeaderInfo(lines)

    def post(self, data: bytes) -> NNTPResponse:
        """Post an article to the server"""
        # Send POST command
        resp = self._shortcmd('POST')

        if resp.code != 340:
            # Server not ready for posting
            self._check_resp(resp, [340])

        # Send article data
        # Data should already be properly formatted with headers and body
        lines = data.split(b'\n')
        for line in lines:
            # Byte-stuff lines starting with '.'
            if line.startswith(b'.'):
                line = b'.' + line
            self.sock.sendall(line + b'\r\n')

        # Send termination sequence
        self.sock.sendall(b'.\r\n')

        # Get response
        resp = self._getresp()
        if resp.code != 240:
            self._check_resp(resp, [240])

        return resp

    def over(self, message_spec: str) -> Tuple[NNTPResponse, List[Tuple]]:
        """Get overview information for articles (OVER command)"""
        resp, lines = self._longcmd(f'OVER {message_spec}')

        if resp.code != 224:
            self._check_resp(resp, [224])

        # Parse overview data
        # Format: article_num <tab> subject <tab> from <tab> date <tab> message-id <tab> references <tab> bytes <tab> lines
        overview_data = []
        for line in lines:
            line_str = line.decode('utf-8', errors='replace')
            parts = line_str.split('\t')
            if len(parts) >= 8:
                try:
                    article_num = int(parts[0])
                    overview_data.append((
                        article_num,
                        parts[1],  # subject
                        parts[2],  # from
                        parts[3],  # date
                        parts[4],  # message-id
                        parts[5],  # references
                        int(parts[6]) if parts[6].isdigit() else 0,  # bytes
                        int(parts[7]) if parts[7].isdigit() else 0   # lines
                    ))
                except (ValueError, IndexError):
                    continue

        return resp, overview_data

    def xover(self, start: int, end: int) -> Tuple[NNTPResponse, List[Tuple]]:
        """Get overview information for articles (XOVER command - older servers)"""
        # XOVER is the old name for OVER, try OVER first, fallback to XOVER
        try:
            return self.over(f'{start}-{end}')
        except (NNTPPermanentError, NNTPTemporaryError):
            # Try XOVER instead
            resp, lines = self._longcmd(f'XOVER {start}-{end}')

            if resp.code != 224:
                self._check_resp(resp, [224])

            # Parse same as over()
            overview_data = []
            for line in lines:
                line_str = line.decode('utf-8', errors='replace')
                parts = line_str.split('\t')
                if len(parts) >= 8:
                    try:
                        article_num = int(parts[0])
                        overview_data.append((
                            article_num,
                            parts[1],  # subject
                            parts[2],  # from
                            parts[3],  # date
                            parts[4],  # message-id
                            parts[5],  # references
                            int(parts[6]) if parts[6].isdigit() else 0,  # bytes
                            int(parts[7]) if parts[7].isdigit() else 0   # lines
                        ))
                    except (ValueError, IndexError):
                        continue

            return resp, overview_data

    def list(self, group_pattern: str = None) -> Tuple[NNTPResponse, List[Tuple]]:
        """List newsgroups"""
        if group_pattern:
            resp, lines = self._longcmd(f'LIST ACTIVE {group_pattern}')
        else:
            resp, lines = self._longcmd('LIST')

        if resp.code != 215:
            self._check_resp(resp, [215])

        # Parse list data
        # Format: group last first posting-status
        groups = []
        for line in lines:
            line_str = line.decode('utf-8', errors='replace')
            parts = line_str.split()
            if len(parts) >= 4:
                try:
                    groups.append((
                        parts[0],           # group name
                        int(parts[1]),      # last article number
                        int(parts[2]),      # first article number
                        parts[3]            # posting status
                    ))
                except (ValueError, IndexError):
                    continue

        return resp, groups

    def quit(self) -> NNTPResponse:
        """Close the connection"""
        try:
            resp = self._shortcmd('QUIT')
        except:
            resp = None

        if self.file:
            self.file.close()
        if self.sock:
            self.sock.close()

        self.file = None
        self.sock = None
        self.authenticated = False

        return resp

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.quit()


class CustomNNTP_SSL(CustomNNTPClient):
    """SSL version of the custom NNTP client"""

    def __init__(self, host: str, port: int = 563, timeout: int = 30,
                 context: ssl.SSLContext = None):
        super().__init__(host, port, timeout)
        self.context = context or ssl.create_default_context()

    def connect(self) -> NNTPResponse:
        """Connect to NNTP server with SSL"""
        try:
            sock = socket.create_connection((self.host, self.port), self.timeout)
            self.sock = self.context.wrap_socket(sock, server_hostname=self.host)
            self.file = self.sock.makefile('rb')

            # Read welcome message
            self.welcome = self._getresp()
            return self.welcome

        except socket.error as e:
            raise NNTPError(f"Could not connect to {self.host}:{self.port} with SSL - {e}")


# Compatibility aliases to match nntplib naming
NNTP = CustomNNTPClient
NNTP_SSL = CustomNNTP_SSL

# Export all classes and exceptions
__all__ = [
    'NNTP',
    'NNTP_SSL',
    'CustomNNTPClient',
    'CustomNNTP_SSL',
    'NNTPError',
    'NNTPPermanentError',
    'NNTPTemporaryError',
    'NNTPReplyError',
    'NNTPDataError',
    'NNTPResponse'
]