#!/usr/bin/env python3
"""
PyGate Spam Filter Module
Provides framework for spam filtering with pluggable filters
"""

import os
import re
from typing import Dict, List, Optional, Any, Callable, Tuple
from datetime import datetime, timedelta
import logging


class SpamFilterModule:
    """Spam filtering framework for PyGate"""

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.filters = []
        self.stats = {
            'total_checked': 0,
            'spam_blocked': 0,
            'ham_passed': 0
        }

        # Load filter patterns from filter.cfg
        self.filter_patterns = self.load_filter_patterns()

        # Load built-in filters
        self.load_builtin_filters()

        # Load custom filters if available
        self.load_custom_filters()

    def load_builtin_filters(self):
        """Load built-in spam filters"""
        # Pattern-based filters from filter.cfg
        self.add_filter(self.subject_filter, "Subject Filter", priority=20)
        self.add_filter(self.from_filter, "From Filter", priority=18)
        self.add_filter(self.user_agent_filter, "User-Agent Filter", priority=16)
        self.add_filter(self.path_filter, "Path Filter", priority=14)
        self.add_filter(self.newsgroups_filter, "Newsgroups Filter", priority=12)
        self.add_filter(self.content_type_filter, "Content-Type Filter", priority=10)
        self.add_filter(self.message_id_filter, "Message-ID Filter", priority=9)
        self.add_filter(self.organization_filter, "Organization Filter", priority=9)
        self.add_filter(self.injection_info_filter, "Injection-Info Filter", priority=9)
        self.add_filter(self.nntp_posting_host_filter, "NNTP-Posting-Host Filter", priority=9)
        self.add_filter(self.x_trace_filter, "X-Trace Filter", priority=9)
        self.add_filter(self.crosspost_filter, "Cross-Post Filter", priority=8)

        self.logger.info(f"Loaded {len(self.filters)} built-in spam filters")

    def load_custom_filters(self):
        """Load custom spam filters from plugins directory"""
        # This would load custom filter plugins
        # For now, just a placeholder
        pass

    def load_filter_patterns(self) -> Dict[str, List[str]]:
        """Load filter patterns from filter.cfg file"""
        patterns = {
            'Subject': [],
            'From': [],
            'User-Agent': [],
            'Path': [],
            'Newsgroups': [],
            'Content-Type': [],
            'Message-ID': [],
            'Organization': [],
            'Injection-Info': [],
            'NNTP-Posting-Host': [],
            'X-Trace': []
        }

        filter_file = self.config.get('SpamFilter', 'filter_file')

        if not os.path.exists(filter_file):
            self.logger.warning(f"Filter {filter_file} not found")
            return patterns

        try:
            with open(filter_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()

                    # Skip empty lines and comments
                    if not line or line.startswith('#') or line.startswith('##'):
                        continue

                    # Parse pattern lines that start with ^
                    if line.startswith('^'):
                        # Extract header and pattern
                        for header in patterns.keys():
                            pattern_prefix = f"^{header}:"
                            if line.startswith(pattern_prefix):
                                # Remove the header prefix and store the pattern
                                pattern = line[len(pattern_prefix):]
                                if pattern:  # Only add non-empty patterns
                                    patterns[header].append(pattern)
                                break

            # Log loaded patterns
            total_patterns = sum(len(p) for p in patterns.values())
            self.logger.info(f"Loaded {total_patterns} filter patterns")
            for header, header_patterns in patterns.items():
                if header_patterns:
                    self.logger.debug(f"  {header}: {len(header_patterns)} patterns")

        except Exception as e:
            self.logger.error(f"Error loading filter patterns: {e}")

        return patterns

    def add_filter(self, filter_func: Callable, name: str, priority: int = 10):
        """Add a spam filter function"""
        filter_entry = {
            'function': filter_func,
            'name': name,
            'priority': priority,
            'enabled': True,
            'stats': {
                'checked': 0,
                'blocked': 0
            }
        }

        self.filters.append(filter_entry)

        # Sort by priority (higher priority runs first)
        self.filters.sort(key=lambda x: x['priority'], reverse=True)

    def is_spam(self, message: Dict[str, Any]) -> bool:
        """Check if message is spam using all enabled filters"""
        self.stats['total_checked'] += 1

        # Skip filtering if disabled
        if not self.config.getboolean('SpamFilter', 'enabled'):
            return False

        for filter_entry in self.filters:
            if not filter_entry['enabled']:
                continue

            try:
                filter_entry['stats']['checked'] += 1

                # Run filter
                result = filter_entry['function'](message)

                if result:
                    # Message is spam
                    filter_entry['stats']['blocked'] += 1
                    self.stats['spam_blocked'] += 1

                    # Log appropriate information based on filter type
                    filter_name = filter_entry['name']
                    if filter_name == "From Filter":
                        log_info = message.get('from_name', 'Unknown')
                    elif filter_name == "Organization Filter":
                        headers = message.get('headers', {})
                        log_info = headers.get('organization', 'Unknown')
                    elif filter_name == "User-Agent Filter":
                        headers = message.get('headers', {})
                        log_info = headers.get('user-agent', 'Unknown')
                    elif filter_name == "Path Filter":
                        headers = message.get('headers', {})
                        log_info = headers.get('path', 'Unknown')
                    elif filter_name == "Newsgroups Filter":
                        log_info = message.get('newsgroup', 'Unknown')
                    elif filter_name == "Content-Type Filter":
                        headers = message.get('headers', {})
                        log_info = headers.get('content-type', 'Unknown')
                    elif filter_name == "Message-ID Filter":
                        headers = message.get('headers', {})
                        log_info = headers.get('message-id', 'Unknown')
                    elif filter_name == "Injection-Info Filter":
                        headers = message.get('headers', {})
                        log_info = headers.get('injection-info', 'Unknown')
                    elif filter_name == "NNTP-Posting-Host Filter":
                        headers = message.get('headers', {})
                        log_info = headers.get('nntp-posting-host', 'Unknown')
                    elif filter_name == "X-Trace Filter":
                        headers = message.get('headers', {})
                        log_info = headers.get('x-trace', 'Unknown')
                    else:
                        # Default to subject for Subject Filter and any other filters
                        log_info = message.get('subject', 'No Subject')

                    self.logger.info(f"Message blocked by {filter_name}: {log_info}")
                    return True

            except Exception as e:
                self.logger.error(f"Error in spam filter {filter_entry['name']}: {e}")

        # All filters passed - not spam
        self.stats['ham_passed'] += 1
        return False

    def subject_filter(self, message: Dict[str, Any]) -> bool:
        """Filter based on Subject header patterns"""
        return self._check_header_patterns(message, 'Subject', 'subject')

    def from_filter(self, message: Dict[str, Any]) -> bool:
        """Filter based on From header patterns"""
        return self._check_header_patterns(message, 'From', 'from_name')

    def user_agent_filter(self, message: Dict[str, Any]) -> bool:
        """Filter based on User-Agent header patterns"""
        # Get User-Agent from headers dict if available
        headers = message.get('headers', {})
        user_agent = headers.get('user-agent', '')
        return self._check_pattern_match('User-Agent', user_agent)

    def path_filter(self, message: Dict[str, Any]) -> bool:
        """Filter based on Path header patterns"""
        # Get Path from headers dict if available
        headers = message.get('headers', {})
        path = headers.get('path', '')
        return self._check_pattern_match('Path', path)

    def newsgroups_filter(self, message: Dict[str, Any]) -> bool:
        """Filter based on Newsgroups header patterns"""
        # Check the full Newsgroups header from the article (contains all cross-posted groups)
        headers = message.get('headers', {})
        newsgroups_header = headers.get('newsgroups', '')
        # Fallback to single newsgroup field if Newsgroups header not available
        if not newsgroups_header:
            newsgroups_header = message.get('newsgroup', '')
        return self._check_pattern_match('Newsgroups', newsgroups_header)

    def content_type_filter(self, message: Dict[str, Any]) -> bool:
        """Filter based on Content-Type header patterns"""
        # Get Content-Type from headers dict if available
        headers = message.get('headers', {})
        content_type = headers.get('content-type', '')
        return self._check_pattern_match('Content-Type', content_type)

    def message_id_filter(self, message: Dict[str, Any]) -> bool:
        """Filter based on Message-ID header patterns"""
        # Get Message-ID from headers dict if available
        headers = message.get('headers', {})
        message_id = headers.get('message-id', '')
        return self._check_pattern_match('Message-ID', message_id)

    def organization_filter(self, message: Dict[str, Any]) -> bool:
        """Filter based on Organization header patterns"""
        # Get Organization from headers dict if available
        headers = message.get('headers', {})
        organization = headers.get('organization', '')
        return self._check_pattern_match('Organization', organization)

    def injection_info_filter(self, message: Dict[str, Any]) -> bool:
        """Filter based on Injection-Info header patterns"""
        # Get Injection-Info from headers dict if available
        headers = message.get('headers', {})
        injection_info = headers.get('injection-info', '')
        return self._check_pattern_match('Injection-Info', injection_info)

    def nntp_posting_host_filter(self, message: Dict[str, Any]) -> bool:
        """Filter based on NNTP-Posting-Host header patterns"""
        # Get NNTP-Posting-Host from headers dict if available
        headers = message.get('headers', {})
        nntp_posting_host = headers.get('nntp-posting-host', '')
        return self._check_pattern_match('NNTP-Posting-Host', nntp_posting_host)

    def x_trace_filter(self, message: Dict[str, Any]) -> bool:
        """Filter based on X-Trace header patterns"""
        # Get X-Trace from headers dict if available
        headers = message.get('headers', {})
        x_trace = headers.get('x-trace', '')
        return self._check_pattern_match('X-Trace', x_trace)

    def crosspost_filter(self, message: Dict[str, Any]) -> bool:
        """Filter messages with excessive cross-posting"""
        # Get max crosspost limit from config
        max_crosspost = self.config.getint('SpamFilter', 'maxcrosspost')

        # Get Newsgroups header for cross-posting analysis
        # This contains the full list of cross-posted newsgroups from the article
        headers = message.get('headers', {})
        newsgroups_header = headers.get('newsgroups', '')

        # If no Newsgroups header, check the newsgroup field for comma-separated list
        if not newsgroups_header:
            newsgroups_header = message.get('newsgroup', '')

        if not newsgroups_header:
            # No newsgroups information, allow message
            return False

        # Count the number of newsgroups
        # Split by comma and count non-empty entries
        newsgroups_list = [ng.strip() for ng in newsgroups_header.split(',') if ng.strip()]
        crosspost_count = len(newsgroups_list)

        if crosspost_count > max_crosspost:
            self.logger.info(f"Cross-post filter triggered: {crosspost_count} newsgroups > {max_crosspost} limit")
            self.logger.debug(f"Newsgroups: {', '.join(newsgroups_list[:10])}{'...' if len(newsgroups_list) > 10 else ''}")
            return True

        return False

    def _check_header_patterns(self, message: Dict[str, Any], header_name: str, message_field: str) -> bool:
        """Check if message field matches any patterns for given header"""
        field_value = message.get(message_field, '')
        return self._check_pattern_match(header_name, field_value)

    def _check_pattern_match(self, header_name: str, value: str) -> bool:
        """Check if value matches any patterns for given header"""
        if not value:
            return False

        patterns = self.filter_patterns.get(header_name, [])

        for pattern in patterns:
            try:
                # Convert PCRE (?i) inline flags to Python re flags
                converted_pattern = self._convert_pcre_pattern(pattern)
                if re.search(converted_pattern, value, re.IGNORECASE):
                    self.logger.debug(f"{header_name} filter triggered: '{pattern}' matched '{value}'")
                    return True
            except re.error as e:
                # Try without conversion as fallback
                try:
                    if re.search(pattern, value, re.IGNORECASE):
                        self.logger.debug(f"{header_name} filter triggered: '{pattern}' matched '{value}'")
                        return True
                except re.error:
                    self.logger.warning(f"Invalid regex pattern in {header_name} filter: '{pattern}' - {e}")
                    continue

        return False

    def _convert_pcre_pattern(self, pattern: str) -> str:
        """Convert PCRE pattern to Python regex pattern"""
        # Handle PCRE inline case-insensitive flag (?i)
        # Remove (?i) since we're already using re.IGNORECASE
        converted = pattern.replace('(?i)', '')

        # Remove any leading .* that might cause issues
        if converted.startswith('.*'):
            converted = converted[2:]

        return converted


    def enable_filter(self, filter_name: str) -> bool:
        """Enable a specific filter"""
        for filter_entry in self.filters:
            if filter_entry['name'] == filter_name:
                filter_entry['enabled'] = True
                self.logger.info(f"Enabled spam filter: {filter_name}")
                return True
        return False

    def disable_filter(self, filter_name: str) -> bool:
        """Disable a specific filter"""
        for filter_entry in self.filters:
            if filter_entry['name'] == filter_name:
                filter_entry['enabled'] = False
                self.logger.info(f"Disabled spam filter: {filter_name}")
                return True
        return False

    def test_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Test a message against all filters and return detailed results"""
        results = {
            'is_spam': False,
            'triggered_filters': [],
            'filter_results': []
        }

        for filter_entry in self.filters:
            if not filter_entry['enabled']:
                continue

            try:
                result = filter_entry['function'](message)
                filter_result = {
                    'name': filter_entry['name'],
                    'triggered': result,
                    'priority': filter_entry['priority']
                }

                results['filter_results'].append(filter_result)

                if result:
                    results['triggered_filters'].append(filter_entry['name'])
                    results['is_spam'] = True

            except Exception as e:
                filter_result = {
                    'name': filter_entry['name'],
                    'triggered': False,
                    'error': str(e),
                    'priority': filter_entry['priority']
                }
                results['filter_results'].append(filter_result)

        return results

    def whitelist_add(self, pattern: str, pattern_type: str = 'from'):
        """Add pattern to whitelist (not implemented in basic version)"""
        # This would add patterns to a whitelist
        # Implementation depends on requirements
        pass

    def blacklist_add(self, pattern: str, pattern_type: str = 'keyword'):
        """Add pattern to blacklist (legacy method - not implemented)"""
        self.logger.warning("blacklist_add method is deprecated - use filter.cfg instead")

