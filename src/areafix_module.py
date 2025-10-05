#!/usr/bin/env python3
"""
PyGate Areafix Module
Handles FidoNet areafix requests for newsgroup management
Based on the existing fidonet_areafix_gateway.py
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
import logging


class AreafixModule:
    """Areafix processing module for PyGate"""

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

        # Wildcard protection settings
        self.blocked_patterns = ['*', '+*']  # Patterns that are blocked
        self.max_areas_per_request = config.getint('Areafix', 'max_areas_per_request', fallback=100)

    def is_areafix_message(self, message: Dict[str, Any]) -> bool:
        """Check if message is an areafix request"""
        to_name = message.get('to_name', '').upper()

        # Check if addressed to areafix (primary check)
        areafix_names = ['AREAFIX', 'AREAMGR']
        if any(name == to_name for name in areafix_names):
            # Also validate password in subject line
            return self.check_areafix_password(message)

        return False

    def check_areafix_password(self, message: Dict[str, Any]) -> bool:
        """Check if message contains valid areafix password in subject line"""
        expected_password = self.config.get('FidoNet', 'areafix_password')
        if not expected_password:
            return False

        # Check subject line for password (correct FidoNet areafix format)
        subject = message.get('subject', '').strip()
        if subject == expected_password:
            return True

        return False

    def check_wildcard_protection(self, commands: List[Dict[str, Any]]) -> Optional[str]:
        """
        Check if commands contain blocked wildcards or excessive requests
        Returns error message if blocked, None if allowed
        """
        # Check for wildcard patterns
        for command in commands:
            if command.get('action') == 'subscribe':
                area = command.get('area', '').strip()
                # Check if area matches blocked patterns
                if area in self.blocked_patterns:
                    return f"Wildcard subscription '{area}' is not permitted. Use QUERY to search for specific areas."

        # Check for excessive subscriptions
        subscribe_count = sum(1 for cmd in commands if cmd.get('action') == 'subscribe')
        if subscribe_count > self.max_areas_per_request:
            return f"Too many subscription requests ({subscribe_count} areas). Maximum allowed is {self.max_areas_per_request}. Please subscribe in smaller batches."

        return None  # All checks passed

    def process_areafix_message(self, message: Dict[str, Any]) -> bool:
        """Process areafix request and generate response"""
        try:
            self.logger.info(f"Processing areafix from {message.get('from_name', 'Unknown')}")

            # Parse areafix commands
            commands = self.parse_areafix_commands(message)

            # Check wildcard protection BEFORE processing commands
            block_reason = self.check_wildcard_protection(commands)
            if block_reason:
                self.logger.warning(f"BLOCKED areafix from {message.get('from_name', 'Unknown')}: {block_reason}")

                # Create rejection response
                rejection_result = {
                    'success': False,
                    'message': f"REQUEST BLOCKED\n\n{block_reason}\n\n" +
                              "WHAT TO DO INSTEAD:\n" +
                              "  1. Use 'QUERY <pattern>' to search for areas\n" +
                              "     Example: QUERY comp.*\n" +
                              "     Example: QUERY aus.*\n\n" +
                              "  2. Subscribe to specific areas\n" +
                              "     Example: +comp.lang.python\n" +
                              "     Example: +aus.cars\n\n" +
                              "  3. Send 'HELP' for more information\n\n" +
                              "Your request was automatically blocked for security reasons.",
                    'command': {'action': 'blocked', 'original': 'wildcard protection'}
                }

                # Generate and send rejection response
                response = self.generate_areafix_response(message, [rejection_result])
                return self.send_areafix_response(message, response)

            # Process each command (only if not blocked)
            results = []
            for command in commands:
                result = self.execute_areafix_command(command)
                results.append(result)

            # Generate response message
            response = self.generate_areafix_response(message, results)

            # Send response (add to outbound)
            return self.send_areafix_response(message, response)

        except Exception as e:
            self.logger.error(f"Error processing areafix message: {e}")
            return False

    def parse_areafix_commands(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse areafix commands from message text"""
        commands = []
        text = message.get('text', '')
        lines = text.split('\n')

        # Password is in subject line, so parse all lines in the body
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#') or line == '---':
                # Stop processing at '---' (end of commands marker)
                if line == '---':
                    break
                continue

            # Parse command
            command = self.parse_single_command(line, line_num)
            if command:
                commands.append(command)

        return commands

    def parse_single_command(self, line: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Parse a single areafix command line"""
        line = line.strip()

        # List command (subscribed areas only)
        if line.upper() in ['LIST', '%LIST']:
            return {
                'action': 'list',
                'line': line_num,
                'original': line
            }

        # Query command with optional search pattern
        if line.upper().startswith(('QUERY', '?')):
            parts = line.split(None, 1)
            search_pattern = parts[1] if len(parts) > 1 else ''
            return {
                'action': 'query',
                'pattern': search_pattern,
                'line': line_num,
                'original': line
            }


        # Help command
        if line.upper() in ['HELP', '%HELP']:
            return {
                'action': 'help',
                'line': line_num,
                'original': line
            }

        # Subscribe (+AREA or AREA)
        if line.startswith('+') or (not line.startswith('-') and not line.startswith('%')):
            area_name = line[1:] if line.startswith('+') else line
            area_name = area_name.strip()  # Keep original case
            if area_name:
                return {
                    'action': 'subscribe',
                    'area': area_name,
                    'line': line_num,
                    'original': line
                }

        # Unsubscribe (-AREA)
        if line.startswith('-'):
            area_name = line[1:].strip()  # Keep original case
            if area_name:
                return {
                    'action': 'unsubscribe',
                    'area': area_name,
                    'line': line_num,
                    'original': line
                }

        return None

    def execute_areafix_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single areafix command"""
        action = command['action']

        if action == 'list':
            return self.handle_list_command(command)
        elif action == 'query':
            return self.handle_query_command(command)
        elif action == 'help':
            return self.handle_help_command(command)
        elif action == 'subscribe':
            return self.handle_subscribe_command(command)
        elif action == 'unsubscribe':
            return self.handle_unsubscribe_command(command)
        else:
            return {
                'success': False,
                'message': f"Unknown command: {command.get('original', '')}",
                'command': command
            }

    def handle_query_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle QUERY command - search available newsgroups with optional pattern"""
        try:
            pattern = command.get('pattern', '').strip()
            available_areas = self.get_available_newsgroups()

            if pattern:
                # Filter newsgroups using wildcard pattern matching
                import fnmatch
                pattern_lower = pattern.lower()
                matched_newsgroups = []

                for area, newsgroup in available_areas.items():
                    newsgroup_lower = newsgroup.lower()
                    # Match against newsgroup name using wildcard pattern
                    if fnmatch.fnmatch(newsgroup_lower, pattern_lower):
                        matched_newsgroups.append(newsgroup_lower)

                if not matched_newsgroups:
                    return {
                        'success': True,
                        'message': f"No areas found matching pattern: {pattern}",
                        'command': command
                    }

                # Sort newsgroups alphabetically and create aligned list
                matched_newsgroups.sort()

                # Find the longest newsgroup name for alignment
                max_length = max(len(newsgroup) for newsgroup in matched_newsgroups) if matched_newsgroups else 0
                padding = max_length + 5  # 5 spaces past the longest name

                newsgroup_list = []
                for newsgroup in matched_newsgroups:
                    status = "yes" if self.area_in_newsrc(newsgroup) else "no"
                    newsgroup_list.append(f"{newsgroup:<{padding}}{status}")

                message = f"\nAreas matching '{pattern}' ({len(matched_newsgroups)} found):\n"
                message += "\n".join(newsgroup_list)

            else:
                # Show only subscribed areas when no pattern given
                subscribed_areas = self.get_subscribed_areas()

                if not subscribed_areas:
                    message = "No areas currently subscribed.\n\nUse QUERY <pattern> to search available areas."
                else:
                    # Get newsgroup names for subscribed areas and sort them
                    subscribed_newsgroups = []
                    for area, newsgroup in available_areas.items():
                        if area in subscribed_areas:
                            subscribed_newsgroups.append(newsgroup.lower())

                    subscribed_newsgroups.sort()

                    # Find the longest newsgroup name for alignment
                    max_length = max(len(newsgroup) for newsgroup in subscribed_newsgroups) if subscribed_newsgroups else 0
                    padding = max_length + 5  # 5 spaces past the longest name

                    newsgroup_list = []
                    for newsgroup in subscribed_newsgroups:
                        newsgroup_list.append(f"{newsgroup:<{padding}}yes")

                    message = f"Currently subscribed areas ({len(subscribed_newsgroups)}):\n"
                    message += "\n".join(newsgroup_list)

            return {
                'success': True,
                'message': message,
                'command': command
            }

        except Exception as e:
            return {
                'success': False,
                'message': f"Error processing query: {e}",
                'command': command
            }


    def handle_list_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle LIST command - show only subscribed areas"""
        try:
            # Get subscribed areas to avoid reading the huge newsgroups file
            subscribed_areas = self.get_subscribed_areas()

            if not subscribed_areas:
                message = "No areas currently subscribed.\n\n"
                message += "Use QUERY <pattern> to search for available areas to subscribe to.\n"
                message += "Use HELP for command information."
                return {
                    'success': True,
                    'message': message,
                    'command': command
                }

            # Get area mappings for display
            available_areas = self.get_available_newsgroups()

            # Get actual newsgroup names for subscribed areas
            newsgroup_list = []
            for area in sorted(subscribed_areas):
                newsgroup = available_areas.get(area, area.lower())
                newsgroup_list.append(newsgroup)

            message = f"Currently subscribed newsgroups ({len(subscribed_areas)}):\n\n"
            message += "\nNewsgroups\n"
            message += "-" * 40 + "\n"
            message += "\n\n".join(sorted(newsgroup_list))

            return {
                'success': True,
                'message': message,
                'command': command
            }

        except Exception as e:
            return {
                'success': False,
                'message': f"Error listing subscribed areas: {e}",
                'command': command
            }

    def handle_help_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle HELP command"""
        try:
            # Read help text from areafix.hlp file
            help_file_path = os.path.join(os.path.dirname(__file__), 'areafix.hlp')

            if os.path.exists(help_file_path):
                with open(help_file_path, 'r') as f:
                    help_text = f.read().strip()
            else:
                # Fallback if help file not found
                help_text = "Help file not found. Contact the sysop for assistance."
                self.logger.warning(f"Areafix help file not found at: {help_file_path}")

        except Exception as e:
            help_text = f"Error reading help file: {e}\nContact the sysop for assistance."
            self.logger.error(f"Error reading areafix help file: {e}")

        return {
            'success': True,
            'message': help_text,
            'command': command
        }

    def handle_subscribe_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle area subscription"""
        area_name = command['area']

        try:
            # Check if area exists (case-insensitive search)
            available_areas = self.get_available_newsgroups()
            matched_area = self.find_area_case_insensitive(area_name, available_areas)
            if not matched_area:
                return {
                    'success': False,
                    'message': f"+ {area_name}: FAILED - Area not available",
                    'command': command
                }

            newsgroup = available_areas[matched_area]

            # Check if already subscribed
            if self.area_in_newsrc(newsgroup):
                return {
                    'success': False,
                    'message': f"+ {matched_area}: ALREADY SUBSCRIBED",
                    'command': command
                }

            # Add subscription
            success = self.add_area_subscription(matched_area, newsgroup)
            if success:
                return {
                    'success': True,
                    'message': f"+ {matched_area}: ADDED",
                    'command': command
                }
            else:
                return {
                    'success': False,
                    'message': f"+ {matched_area}: FAILED - Unable to add newsgroup",
                    'command': command
                }

        except Exception as e:
            return {
                'success': False,
                'message': f"+ {area_name}: FAILED - {str(e)}",
                'command': command
            }

    def handle_unsubscribe_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle area unsubscription"""
        area_name = command['area']

        try:
            # Find the corresponding newsgroup for this area (case-insensitive)
            available_areas = self.get_available_newsgroups()
            matched_area = self.find_area_case_insensitive(area_name, available_areas)
            if not matched_area:
                return {
                    'success': False,
                    'message': f"- {area_name}: FAILED - Area not found",
                    'command': command
                }

            newsgroup = available_areas[matched_area]

            # Check if subscribed
            if not self.area_in_newsrc(newsgroup):
                return {
                    'success': False,
                    'message': f"- {matched_area}: NOT SUBSCRIBED",
                    'command': command
                }

            # Remove subscription
            success = self.remove_area_subscription(matched_area)
            if success:
                return {
                    'success': True,
                    'message': f"- {matched_area}: UNSUBSCRIBED",
                    'command': command
                }
            else:
                return {
                    'success': False,
                    'message': f"- {matched_area}: FAILED - Unable to remove newsgroup",
                    'command': command
                }

        except Exception as e:
            return {
                'success': False,
                'message': f"- {area_name}: FAILED - {str(e)}",
                'command': command
            }

    def get_available_newsgroups(self) -> Dict[str, str]:
        """Get list of available newsgroups and their mappings - similar to newsgrouplist function"""
        newsgroups_file = self.config.get('Files', 'newsgrouplist')

        # First, read the area remapping from [Arearemap] section to get FidoNet area -> newsgroup mappings
        area_mappings = {}
        if self.config.has_section('Arearemap'):
            try:
                for fidonet_area, newsgroup in self.config.items('Arearemap'):
                    # Skip special configuration flags (boolean settings, not newsgroup mappings)
                    if fidonet_area.lower() in ['hold', 'notify_sysop']:
                        continue
                    area_mappings[fidonet_area] = newsgroup
                    self.logger.debug(f"Area mapping: {fidonet_area} -> {newsgroup}")
            except Exception as e:
                self.logger.error(f"Error reading Arearemap section: {e}")

        # Now read available newsgroups
        available_newsgroups = set()
        if os.path.exists(newsgroups_file):
            try:
                self.logger.info(f"Reading available newsgroups from {newsgroups_file}")
                with open(newsgroups_file, 'r') as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if line and not line.startswith('#'):
                            # Extract just the newsgroup name (first field before whitespace)
                            newsgroup_name = line.split()[0] if line.split() else ""
                            if newsgroup_name:
                                available_newsgroups.add(newsgroup_name)
                                self.logger.debug(f"Found available newsgroup '{newsgroup_name}' at line {line_num}")
            except Exception as e:
                self.logger.error(f"Error reading newsgroups file: {e}")

        # Build the final mapping: area name -> newsgroup name
        areas = {}

        # Add explicit mappings from [Arearemap] section (FidoNet area -> newsgroup)
        for fidonet_area, newsgroup in area_mappings.items():
            if newsgroup in available_newsgroups:
                areas[fidonet_area] = newsgroup
            else:
                self.logger.warning(f"Mapped newsgroup '{newsgroup}' for area '{fidonet_area}' not found in available newsgroups")

        # For newsgroups not explicitly mapped, use uppercase newsgroup name as the area name
        for newsgroup in available_newsgroups:
            # Check if this newsgroup is already mapped via [Arearemap] section
            already_mapped = newsgroup in area_mappings.values()
            if not already_mapped:
                # Use uppercase newsgroup name as the FidoNet area name (matching packet examples)
                area_name = newsgroup.upper()
                areas[area_name] = newsgroup
                self.logger.debug(f"Auto-mapped: {area_name} -> {newsgroup}")

        self.logger.info(f"Loaded {len(areas)} available areas")
        return areas

    def find_area_case_insensitive(self, area_name: str, available_areas: Dict[str, str]) -> Optional[str]:
        """Find area name with case-insensitive matching"""
        # First try exact match
        if area_name in available_areas:
            return area_name

        # Try case-insensitive match
        area_upper = area_name.upper()
        for available_area in available_areas.keys():
            if available_area.upper() == area_upper:
                return available_area

        return None

    def newsgroup_to_area_name(self, newsgroup: str) -> str:
        """Convert newsgroup name back to area name using [Arearemap] section"""
        if self.config.has_section('Arearemap'):
            try:
                for fidonet_area, mapped_newsgroup in self.config.items('Arearemap'):
                    if mapped_newsgroup == newsgroup:
                        return fidonet_area
            except Exception as e:
                self.logger.error(f"Error reading Arearemap section: {e}")

        # If not found in [Arearemap], use newsgroup name as area name
        return newsgroup

    def get_subscribed_areas(self) -> Set[str]:
        """Get set of currently subscribed areas from newsrc file"""
        newsrc_file = self.config.get('Files', 'areas_file')
        subscribed = set()

        if os.path.exists(newsrc_file):
            try:
                self.logger.debug(f"Reading subscribed areas from {newsrc_file}")
                with open(newsrc_file, 'r') as f:
                    for line in f:
                        line = line.strip()

                        # Skip empty lines and comments
                        if not line or line.startswith('#'):
                            continue

                        # Parse newsrc format: "groupname: low-high"
                        if ':' in line:
                            newsgroup = line.split(':', 1)[0].strip()
                            # Convert newsgroup back to area name using our mappings
                            area_name = self.newsgroup_to_area_name(newsgroup)
                            subscribed.add(area_name)
                            self.logger.debug(f"Found subscribed newsgroup '{newsgroup}' -> area '{area_name}'")

            except Exception as e:
                self.logger.error(f"Error reading newsrc file: {e}")

        self.logger.debug(f"Found {len(subscribed)} subscribed areas")
        return subscribed

    def add_area_subscription(self, area_name: str, newsgroup: str) -> bool:
        """Add new area subscription using ctlinnd and newsrc"""
        try:
            area_lower = area_name.lower()
            newsgroup_lower = newsgroup.lower()
            self.logger.info(f"Processing add request for area: '{area_name}' -> newsgroup: '{newsgroup_lower}'")

            # Check if area exists in newsgrouplist
            if not self.area_exists_in_newsgrouplist(newsgroup_lower):
                self.logger.warning(f"Newsgroup '{newsgroup_lower}' not found in newsgrouplist")
                return False

            # Check if already in newsrc
            if self.area_in_newsrc(newsgroup_lower):
                self.logger.info(f"Newsgroup '{newsgroup_lower}' already in newsrc")
                return False

            # Add to newsrc
            self.add_to_newsrc(newsgroup_lower)

            # Check if running in client-only mode
            client_mode = self.config.getboolean('Gateway', 'client_mode', fallback=False)

            if client_mode:
                # Client mode: only update newsrc, assume newsgroup exists on server
                self.logger.info(f"Client mode: Added newsgroup '{newsgroup_lower}' to newsrc (skipping server modification)")
                return True
            else:
                # Full gateway mode: Add to news server using ctlinnd (local or SSH)
                success, output = self.execute_ctlinnd('newgroup', newsgroup_lower)
                if success:
                    self.logger.info(f"Successfully added newsgroup: {newsgroup_lower}")
                    return True
                else:
                    self.logger.error(f"Failed to add newsgroup {newsgroup_lower} to news server: {output}")
                    # Remove from newsrc if ctlinnd failed
                    self.remove_from_newsrc(newsgroup_lower)
                    return False

        except Exception as e:
            self.logger.error(f"Error adding area subscription: {e}")
            return False

    def remove_area_subscription(self, area_name: str) -> bool:
        """Remove area subscription using ctlinnd and newsrc"""
        try:
            # Find the corresponding newsgroup for this area
            available_areas = self.get_available_newsgroups()
            matched_area = self.find_area_case_insensitive(area_name, available_areas)
            if not matched_area:
                self.logger.warning(f"Area '{area_name}' not found in available areas")
                return False

            newsgroup = available_areas[matched_area]
            self.logger.info(f"Processing remove request for area: '{area_name}' -> newsgroup: '{newsgroup}'")

            # Check if in newsrc
            if not self.area_in_newsrc(newsgroup):
                self.logger.info(f"Newsgroup '{newsgroup}' not found in newsrc")
                return False

            # Remove from newsrc
            self.remove_from_newsrc(newsgroup)

            # Check if running in client-only mode
            client_mode = self.config.getboolean('Gateway', 'client_mode', fallback=False)

            if client_mode:
                # Client mode: only update newsrc, don't modify server
                self.logger.info(f"Client mode: Removed newsgroup '{newsgroup}' from newsrc (skipping server modification)")
                return True
            else:
                # Full gateway mode: Remove from news server using ctlinnd (local or SSH)
                success, output = self.execute_ctlinnd('rmgroup', newsgroup)
                if success:
                    self.logger.info(f"Successfully removed newsgroup: {newsgroup}")
                    return True
                else:
                    self.logger.error(f"Failed to remove newsgroup {newsgroup} from news server: {output}")
                    # Re-add to newsrc if ctlinnd failed
                    self.add_to_newsrc(newsgroup)
                return False

        except Exception as e:
            self.logger.error(f"Error removing area subscription: {e}")
            return False

    def generate_areafix_response(self, original_message: Dict[str, Any], results: List[Dict[str, Any]]) -> str:
        """Generate areafix response message"""
        response_lines = []

        response_lines.append("Areafix processing results:\n")
        response_lines.append("")

        # Separate command results from LIST results
        command_results = []
        list_results = []

        for result in results:
            action = result.get('command', {}).get('action')
            if action in ['list', 'help']:
                list_results.append(result)
            else:
                command_results.append(result)

        # First show command results (subscribe, unsubscribe, etc.)
        for result in command_results:
            response_lines.append(result['message'])

        # Then show LIST results
        for result in list_results:
            if command_results:  # Add blank line if there were previous commands
                response_lines.append("")
            response_lines.append(result['message'])

        response_lines.append("")
        response_lines.append("--- End of response ---\n")

        # Add footer if configured
        footer = self.get_areafix_footer()
        if footer:
            response_lines.append("")
            response_lines.append(footer)

        return "\n".join(response_lines)

    def get_areafix_footer(self) -> str:
        """Get areafix footer text from config if configured"""
        try:
            if self.config.has_section('Areafixfooter'):
                footer = self.config.get('Areafixfooter', 'footer', fallback='')
                return footer.strip() if footer else ''
            return ''
        except Exception as e:
            self.logger.error(f"Error reading areafix footer: {e}")
            return ''

    def send_areafix_response(self, original_message: Dict[str, Any], response_text: str) -> bool:
        """Send areafix response message"""
        try:
            # Create response message with proper FidoNet addressing
            response_message = {
                'from_name': 'Areafix',
                'to_name': original_message.get('from_name', 'Unknown'),
                'subject': 'Areafix response',
                'text': response_text,
                'datetime': __import__('datetime').datetime.now(),
                'msgid': '',
                'reply': original_message.get('msgid', ''),
                # Add explicit destination addressing for netmail routing
                'dest_node': original_message.get('orig_node', self.get_linked_node()),
                'dest_net': original_message.get('orig_net', self.get_linked_net()),
            }

            # Import and create FidoNet module instance
            from .fidonet_module import FidoNetModule
            fidonet = FidoNetModule(self.config, self.logger)

            # Temporarily modify the FidoNet create_message method to handle explicit addressing
            # Add message to pending messages directly with our addressing
            fido_message = {
                'area': '',  # Netmail
                'from_name': response_message['from_name'],
                'to_name': response_message['to_name'],
                'subject': response_message['subject'],
                'text': response_message['text'],
                'datetime': response_message['datetime'],
                'orig_node': fidonet.get_our_node(),
                'orig_net': fidonet.get_our_net(),
                'dest_node': response_message['dest_node'],
                'dest_net': response_message['dest_net'],
                'attr': 0,  # Message attributes
                'msgid': response_message.get('msgid', ''),
                'reply': response_message.get('reply', ''),
                'origin': fidonet.get_our_origin()
            }

            fidonet.pending_messages.append(fido_message)
            success = True

            if success:
                # Create the packet file
                packet_success = fidonet.create_packets()
                if packet_success:
                    self.logger.info(f"Areafix response packet created for {response_message['to_name']}")
                    return True
                else:
                    self.logger.error("Failed to create areafix response packet")
                    return False
            else:
                self.logger.error("Failed to queue areafix response message")
                return False

        except Exception as e:
            self.logger.error(f"Error sending areafix response: {e}")
            return False

    def get_our_node(self) -> int:
        """Get our FidoNet node number"""
        address = self.config.get('FidoNet', 'gateway_address')
        if not address:
            raise ValueError("gateway_address must be configured in [FidoNet] section")
        # Parse address and return node
        try:
            if '/' in address:
                net_node = address.split(':')[-1]  # Get after zone
                return int(net_node.split('/')[1].split('.')[0])  # Get node, ignore point
        except:
            raise ValueError(f"Invalid gateway_address format: {address}")
        raise ValueError(f"Invalid gateway_address format: {address}")

    def get_our_net(self) -> int:
        """Get our FidoNet net number"""
        address = self.config.get('FidoNet', 'gateway_address')
        if not address:
            raise ValueError("gateway_address must be configured in [FidoNet] section")
        # Parse address and return net
        try:
            if '/' in address:
                net_node = address.split(':')[-1]  # Get after zone
                return int(net_node.split('/')[0])  # Get net
        except:
            raise ValueError(f"Invalid gateway_address format: {address}")
        raise ValueError(f"Invalid gateway_address format: {address}")

    def get_our_origin(self) -> str:
        """Get our origin line"""
        address = self.config.get('FidoNet', 'gateway_address')
        if not address:
            raise ValueError("gateway_address must be configured in [FidoNet] section")
        origin_name = self.config.get('FidoNet', 'origin_line')
        return f"{origin_name} Areafix ({address})"

    def get_linked_node(self) -> int:
        """Get linked system node number"""
        address = self.config.get('FidoNet', 'linked_address')
        if not address:
            raise ValueError("linked_address must be configured in [FidoNet] section")
        # Parse address and return node
        try:
            if '/' in address:
                net_node = address.split(':')[-1]  # Get after zone
                return int(net_node.split('/')[1].split('.')[0])  # Get node, ignore point
        except:
            raise ValueError(f"Invalid linked_address format: {address}")
        raise ValueError(f"Invalid linked_address format: {address}")

    def get_linked_net(self) -> int:
        """Get linked system net number"""
        address = self.config.get('FidoNet', 'linked_address')
        if not address:
            raise ValueError("linked_address must be configured in [FidoNet] section")
        # Parse address and return net
        try:
            if '/' in address:
                net_node = address.split(':')[-1]  # Get after zone
                return int(net_node.split('/')[0])  # Get net
        except:
            raise ValueError(f"Invalid linked_address format: {address}")
        raise ValueError(f"Invalid linked_address format: {address}")

    def validate_area_name(self, area_name: str) -> bool:
        """Validate area name format"""
        # Basic validation - alphanumeric, dots, underscores
        if not area_name:
            return False

        # Check length
        if len(area_name) > 32:
            return False

        # Check characters
        allowed_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-')
        return all(c in allowed_chars for c in area_name.upper())

    def area_exists_in_newsgrouplist(self, newsgroup: str) -> bool:
        """Check if newsgroup exists in newsgrouplist - case insensitive"""
        try:
            newsgroup_lower = newsgroup.lower()
            newsgroups_file = self.config.get('Files', 'newsgrouplist')
            self.logger.debug(f"Searching for newsgroup '{newsgroup_lower}' in newsgrouplist")

            with open(newsgroups_file, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    # Extract just the newsgroup name (first field before whitespace)
                    newsgroup_name = line.split()[0].lower() if line.split() else ""
                    if newsgroup_name == newsgroup_lower:
                        self.logger.debug(f"Found newsgroup '{newsgroup_lower}' at line {line_num} in newsgrouplist")
                        return True

            self.logger.warning(f"Newsgroup '{newsgroup_lower}' not found in newsgrouplist after checking all entries")
            return False
        except Exception as e:
            self.logger.error(f"Error reading newsgrouplist: {e}")
            return False

    def area_in_newsrc(self, newsgroup: str) -> bool:
        """Check if newsgroup is in newsrc file - case insensitive"""
        try:
            newsgroup_lower = newsgroup.lower()
            newsrc_file = self.config.get('Files', 'areas_file')

            with open(newsrc_file, 'r') as f:
                for line in f:
                    # newsrc format: "groupname: low-high"
                    if ':' in line:
                        newsrc_group = line.split(':')[0].strip().lower()
                        if newsrc_group == newsgroup_lower:
                            return True
            return False
        except Exception as e:
            self.logger.error(f"Error reading newsrc: {e}")
            return False

    def add_to_newsrc(self, newsgroup: str):
        """Add newsgroup to newsrc file"""
        try:
            newsgroup_lower = newsgroup.lower()
            newsrc_file = self.config.get('Files', 'areas_file')

            with open(newsrc_file, 'a') as f:
                f.write(f"{newsgroup_lower}: 0-0\n")

            self.logger.info(f"Added '{newsgroup_lower}' to newsrc")
        except Exception as e:
            self.logger.error(f"Error adding to newsrc: {e}")
            raise

    def remove_from_newsrc(self, newsgroup: str):
        """Remove newsgroup from newsrc file"""
        try:
            newsgroup_lower = newsgroup.lower()
            newsrc_file = self.config.get('Files', 'areas_file')

            with open(newsrc_file, 'r') as f:
                lines = f.readlines()

            # Filter out the line for this newsgroup
            remaining_lines = []
            removed = False
            for line in lines:
                if ':' in line:
                    newsrc_group = line.split(':')[0].strip().lower()
                    if newsrc_group == newsgroup_lower:
                        removed = True
                        continue
                remaining_lines.append(line)

            # Write back the remaining lines
            with open(newsrc_file, 'w') as f:
                f.writelines(remaining_lines)

            if removed:
                self.logger.info(f"Removed '{newsgroup_lower}' from newsrc")
            else:
                self.logger.warning(f"Newsgroup '{newsgroup_lower}' was not found in newsrc during removal")
        except Exception as e:
            self.logger.error(f"Error removing from newsrc: {e}")
            raise

    def execute_ctlinnd(self, command: str, newsgroup: str) -> tuple[bool, str]:
        """Execute ctlinnd command either locally or via SSH"""
        try:
            # Check if SSH is enabled
            ssh_enabled = self.config.getboolean('SSH', 'enabled', fallback=False)

            if ssh_enabled:
                return self.execute_ctlinnd_ssh(command, newsgroup)
            else:
                return self.execute_ctlinnd_local(command, newsgroup)

        except Exception as e:
            self.logger.error(f"Error executing ctlinnd {command} {newsgroup}: {e}")
            return False, str(e)

    def execute_ctlinnd_local(self, command: str, newsgroup: str) -> tuple[bool, str]:
        """Execute ctlinnd command locally"""
        try:
            ctlinnd_path = self.config.get('NNTP', 'ctlinndpath')
            result = subprocess.run([ctlinnd_path, command, newsgroup],
                                  capture_output=True, text=True)

            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr

        except Exception as e:
            return False, str(e)

    def execute_ctlinnd_ssh(self, command: str, newsgroup: str) -> tuple[bool, str]:
        """Execute ctlinnd command via SSH"""
        try:
            # Import paramiko here to make it optional
            try:
                import paramiko
            except ImportError:
                raise Exception("paramiko module required for SSH functionality. Install with: pip install paramiko")

            # Get SSH configuration
            hostname = self.config.get('SSH', 'hostname')
            port = self.config.getint('SSH', 'port', fallback=22)
            username = self.config.get('SSH', 'username')
            keyfile = self.config.get('SSH', 'keyfile', fallback='')
            password = self.config.get('SSH', 'password', fallback='')
            remote_ctlinnd_path = self.config.get('SSH', 'remote_ctlinnd_path')

            if not hostname or not username:
                raise Exception("SSH hostname and username must be configured")

            # Create SSH client
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Connect with key-based or password authentication
            if keyfile and os.path.exists(keyfile):
                self.logger.debug(f"Connecting to {hostname} via SSH using key file: {keyfile}")
                ssh.connect(hostname, port=port, username=username, key_filename=keyfile, timeout=30)
            elif password:
                self.logger.debug(f"Connecting to {hostname} via SSH using password")
                ssh.connect(hostname, port=port, username=username, password=password, timeout=30)
            else:
                raise Exception("SSH authentication requires either keyfile or password")

            # Execute ctlinnd command
            ssh_command = f"{remote_ctlinnd_path} {command} {newsgroup}"
            self.logger.debug(f"Executing SSH command: {ssh_command}")

            stdin, stdout, stderr = ssh.exec_command(ssh_command)

            # Wait for command to complete and get results
            exit_status = stdout.channel.recv_exit_status()
            stdout_data = stdout.read().decode('utf-8')
            stderr_data = stderr.read().decode('utf-8')

            # Close SSH connection
            ssh.close()

            if exit_status == 0:
                self.logger.debug(f"SSH ctlinnd {command} successful")
                return True, stdout_data
            else:
                self.logger.error(f"SSH ctlinnd {command} failed with exit code {exit_status}: {stderr_data}")
                return False, stderr_data

        except Exception as e:
            self.logger.error(f"SSH ctlinnd execution error: {e}")
            return False, str(e)

    def cleanup_old_responses(self):
        """Clean up old areafix response files"""
        # This could be used to clean up temporary files, logs, etc.
        pass
