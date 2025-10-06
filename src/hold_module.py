#!/usr/bin/env python3
"""
PyGate Message Hold Module
Handles holding and reviewing usenet messages from arearemap groups
"""

import os
import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging


class MessageHoldModule:
    """Module for holding and reviewing messages from arearemap groups"""

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.hold_dir = Path(self.config.get('Files', 'hold_dir', fallback='hold'))
        self.hold_dir.mkdir(exist_ok=True)

        # Create subdirectories for organization
        (self.hold_dir / 'pending').mkdir(exist_ok=True)
        (self.hold_dir / 'approved').mkdir(exist_ok=True)
        (self.hold_dir / 'rejected').mkdir(exist_ok=True)
        (self.hold_dir / 'backup').mkdir(exist_ok=True)

        # File to track notification state (prevent duplicate notifications)
        self.notification_file = self.hold_dir / 'notifications.json'

    def should_hold_message(self, message: Dict[str, Any], area_tag: str) -> bool:
        """Check if message should be held for review"""
        # Check if holding is enabled globally
        if not self.config.getboolean('Arearemap', 'Hold', fallback=False):
            return False

        # Check if this area is in the arearemap section
        if not self.config.has_section('Arearemap'):
            return False

        # Check if area_tag is mapped in arearemap
        try:
            arearemap_areas = dict(self.config.items('Arearemap'))
            # Remove the 'hold' setting from the check
            arearemap_areas.pop('hold', None)

            # Check if this area tag exists in arearemap
            area_tag_upper = area_tag.upper()
            for area_name in arearemap_areas.keys():
                if area_name.upper() == area_tag_upper:
                    self.logger.info(f"Message in arearemap area '{area_tag}' will be held for review")
                    return True

        except Exception as e:
            self.logger.error(f"Error checking arearemap areas: {e}")

        return False

    def hold_message(self, message: Dict[str, Any], area_tag: str, direction: str = "auto") -> str:
        """Hold a message for review, returns hold ID"""
        try:
            # Generate unique hold ID
            hold_id = str(uuid.uuid4())

            # Determine message direction if not specified
            if direction == "auto":
                if 'newsgroup' in message:
                    direction = "fidonet"  # Message came from NNTP (going to FidoNet)
                else:
                    direction = "nntp"  # Message came from FidoNet (going to NNTP)

            # Get message body from different possible fields
            body = message.get('body', '') or message.get('text', '')

            # Create hold record
            hold_record = {
                'hold_id': hold_id,
                'area_tag': area_tag,
                'newsgroup': message.get('newsgroup', ''),
                'from_name': message.get('from_name', 'Unknown'),
                'subject': message.get('subject', ''),
                'date': message.get('date', datetime.now()).isoformat() if hasattr(message.get('date', datetime.now()), 'isoformat') else str(message.get('date', datetime.now())),
                'message_id': message.get('message_id', ''),
                'body_preview': body[:200] + ('...' if len(body) > 200 else ''),
                'full_message': message,
                'held_at': datetime.now().isoformat(),
                'status': 'pending',
                'reviewed_by': None,
                'reviewed_at': None,
                'action': None,
                'notes': '',
                'direction': direction  # Track message direction (nntp/fidonet)
            }

            # Save to pending directory
            hold_file = self.hold_dir / 'pending' / f"{hold_id}.json"
            with open(hold_file, 'w', encoding='utf-8') as f:
                json.dump(hold_record, f, indent=2, ensure_ascii=False, default=str)

            self.logger.info(f"Message held for review: (Area: {area_tag}, Subject: {message.get('subject', 'No subject')})")

            # Send notification if enabled
            self.send_hold_notification(area_tag)

            return hold_id

        except Exception as e:
            self.logger.error(f"Error holding message: {e}")
            return ""

    def get_pending_messages(self) -> List[Dict[str, Any]]:
        """Get list of pending messages for review"""
        pending_messages = []
        pending_dir = self.hold_dir / 'pending'

        try:
            for hold_file in pending_dir.glob('*.json'):
                try:
                    with open(hold_file, 'r', encoding='utf-8') as f:
                        hold_record = json.load(f)
                        pending_messages.append(hold_record)
                except Exception as e:
                    self.logger.error(f"Error reading hold file {hold_file}: {e}")

            # Sort by held_at date (newest first)
            pending_messages.sort(key=lambda x: x.get('held_at', ''), reverse=True)

        except Exception as e:
            self.logger.error(f"Error getting pending messages: {e}")

        return pending_messages

    def get_message_details(self, hold_id: str) -> Optional[Dict[str, Any]]:
        """Get full details of a held message"""
        try:
            hold_file = self.hold_dir / 'pending' / f"{hold_id}.json"
            if hold_file.exists():
                with open(hold_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"Error getting message details for {hold_id}: {e}")
        return None

    def approve_message(self, hold_id: str, reviewer: str = "admin") -> bool:
        """Approve a held message for posting"""
        try:
            # Load the held message
            hold_file = self.hold_dir / 'pending' / f"{hold_id}.json"
            if not hold_file.exists():
                self.logger.error(f"Hold file not found: {hold_id}")
                return False

            with open(hold_file, 'r', encoding='utf-8') as f:
                hold_record = json.load(f)

            # Update status
            hold_record['status'] = 'approved'
            hold_record['reviewed_by'] = reviewer
            hold_record['reviewed_at'] = datetime.now().isoformat()
            hold_record['action'] = 'approve'

            # Move to approved directory
            approved_file = self.hold_dir / 'approved' / f"{hold_id}.json"
            with open(approved_file, 'w', encoding='utf-8') as f:
                json.dump(hold_record, f, indent=2, ensure_ascii=False, default=str)

            # Remove from pending
            hold_file.unlink()

            self.logger.info(f"Message {hold_id} approved")
            return True

        except Exception as e:
            self.logger.error(f"Error approving message {hold_id}: {e}")
            return False

    def reject_message(self, hold_id: str, reviewer: str = "admin", reason: str = "") -> bool:
        """Reject a held message"""
        try:
            # Load the held message
            hold_file = self.hold_dir / 'pending' / f"{hold_id}.json"
            if not hold_file.exists():
                self.logger.error(f"Hold file not found: {hold_id}")
                return False

            with open(hold_file, 'r', encoding='utf-8') as f:
                hold_record = json.load(f)

            # Update status
            hold_record['status'] = 'rejected'
            hold_record['reviewed_by'] = reviewer
            hold_record['reviewed_at'] = datetime.now().isoformat()
            hold_record['action'] = 'reject'
            hold_record['notes'] = reason

            # Move to rejected directory
            rejected_file = self.hold_dir / 'rejected' / f"{hold_id}.json"
            with open(rejected_file, 'w', encoding='utf-8') as f:
                json.dump(hold_record, f, indent=2, ensure_ascii=False, default=str)

            # Remove from pending
            hold_file.unlink()

            self.logger.info(f"Message {hold_id} rejected: {reason}")
            return True

        except Exception as e:
            self.logger.error(f"Error rejecting message {hold_id}: {e}")
            return False

    def get_approved_messages(self) -> List[Dict[str, Any]]:
        """Get list of approved messages ready for posting"""
        approved_messages = []
        approved_dir = self.hold_dir / 'approved'

        try:
            for hold_file in approved_dir.glob('*.json'):
                try:
                    with open(hold_file, 'r', encoding='utf-8') as f:
                        hold_record = json.load(f)
                        approved_messages.append(hold_record)
                except Exception as e:
                    self.logger.error(f"Error reading approved file {hold_file}: {e}")

        except Exception as e:
            self.logger.error(f"Error getting approved messages: {e}")

        return approved_messages

    def release_approved_message(self, hold_id: str) -> Optional[Dict[str, Any]]:
        """Release an approved message and return the original message for posting"""
        try:
            approved_file = self.hold_dir / 'approved' / f"{hold_id}.json"
            if not approved_file.exists():
                self.logger.error(f"Approved file not found: {hold_id}")
                return None

            with open(approved_file, 'r', encoding='utf-8') as f:
                hold_record = json.load(f)

            # Get the original message
            original_message = hold_record.get('full_message', {})

            # Copy to backup directory before removing
            backup_file = self.hold_dir / 'backup' / f"{hold_id}.json"
            try:
                # Add timestamp for when it was released
                hold_record['released_at'] = datetime.now().isoformat()
                with open(backup_file, 'w', encoding='utf-8') as f:
                    json.dump(hold_record, f, indent=2, ensure_ascii=False, default=str)
                self.logger.info(f"Backed up approved message {hold_id} to backup directory")
            except Exception as backup_error:
                self.logger.error(f"Error backing up approved message {hold_id}: {backup_error}")
                # Continue even if backup fails - we don't want to block message posting

            # Remove the approved file (message will be posted)
            approved_file.unlink()

            self.logger.info(f"Released approved message {hold_id} for posting")
            return original_message

        except Exception as e:
            self.logger.error(f"Error releasing approved message {hold_id}: {e}")
            return None

    def cleanup_old_records(self, days_to_keep: int = 30):
        """Clean up old approved and rejected records"""
        try:
            from datetime import timedelta
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            cutoff_str = cutoff_date.isoformat()

            for directory in ['approved', 'rejected']:
                dir_path = self.hold_dir / directory
                if not dir_path.exists():
                    continue

                for hold_file in dir_path.glob('*.json'):
                    try:
                        with open(hold_file, 'r', encoding='utf-8') as f:
                            hold_record = json.load(f)

                        reviewed_at = hold_record.get('reviewed_at', '')
                        if reviewed_at and reviewed_at < cutoff_str:
                            hold_file.unlink()
                            self.logger.info(f"Cleaned up old {directory} record: {hold_file.name}")

                    except Exception as e:
                        self.logger.error(f"Error cleaning up {hold_file}: {e}")

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

    def get_hold_statistics(self) -> Dict[str, int]:
        """Get statistics about held messages"""
        stats = {
            'pending': 0,
            'approved': 0,
            'rejected': 0
        }

        try:
            for status in stats.keys():
                dir_path = self.hold_dir / status
                if dir_path.exists():
                    stats[status] = len(list(dir_path.glob('*.json')))

        except Exception as e:
            self.logger.error(f"Error getting hold statistics: {e}")

        return stats

    def load_notification_state(self) -> Dict[str, Any]:
        """Load notification state to prevent duplicate notifications"""
        try:
            if self.notification_file.exists():
                with open(self.notification_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading notification state: {e}")

        return {"last_notification": None, "notified_areas": []}

    def save_notification_state(self, state: Dict[str, Any]):
        """Save notification state"""
        try:
            with open(self.notification_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Error saving notification state: {e}")

    def should_send_notification(self, area_tag: str) -> bool:
        """Check if we should send a notification for this area"""
        # Check if notifications are enabled
        if not self.config.getboolean('Arearemap', 'notify_sysop', fallback=False):
            return False

        state = self.load_notification_state()

        # Check if we've already notified for this area recently (within last hour)
        last_notification = state.get("last_notification")
        if last_notification:
            try:
                last_time = datetime.fromisoformat(last_notification)
                current_time = datetime.now()

                # Don't send another notification if one was sent in the last hour
                if (current_time - last_time).total_seconds() < 3600:
                    return False
            except (ValueError, TypeError):
                pass  # If we can't parse the time, proceed with notification

        return True

    def generate_netmail_notification(self, areas_with_held_messages: List[str]) -> Dict[str, Any]:
        """Generate a netmail notification for held messages"""
        sysop_name = self.config.get('Gateway', 'sysop', fallback='Sysop')
        gateway_address = self.config.get('FidoNet', 'gateway_address')
        linked_address = self.config.get('FidoNet', 'linked_address')

        if not gateway_address or not linked_address:
            self.logger.error("Cannot send notification: gateway_address or linked_address not configured")
            return None

        # Count total pending messages
        pending_count = len(list((self.hold_dir / 'pending').glob('*.json')))

        # Create message body
        if len(areas_with_held_messages) == 1:
            area_text = f"area {areas_with_held_messages[0]}"
        else:
            area_list = ", ".join(areas_with_held_messages[:-1])
            area_text = f"areas {area_list} and {areas_with_held_messages[-1]}"

        body = f"""PyGate Message Hold Notification

You have {pending_count} message(s) held for review in {area_text}.

These messages require manual approval before being gated between
NNTP and FidoNet.

To review and approve/reject these messages, use the PyGate admin
panel or command line tools.

This notification was automatically generated by PyGate.

---
PyGate FTN-NNTP Gateway
{gateway_address}"""

        # Create netmail message structure
        netmail = {
            'area': 'NETMAIL',
            'from_name': 'PyGate',
            'from_address': gateway_address,
            'to_name': sysop_name,
            'to_address': linked_address,
            'subject': f'PyGate: Messages held for review ({len(areas_with_held_messages)} areas)',
            'datetime': datetime.now(),
            'text': body,
            'attributes': ['PVT'],  # Private netmail
            'priority': 'normal'
        }

        return netmail

    def send_hold_notification(self, area_tag: str):
        """Send notification if conditions are met"""
        if not self.should_send_notification(area_tag):
            return

        # Get all pending messages and their areas
        pending_messages = self.get_pending_messages()
        areas_with_messages = list(set(msg.get('area_tag', 'UNKNOWN') for msg in pending_messages))

        if not areas_with_messages:
            return

        # Generate and queue netmail
        netmail = self.generate_netmail_notification(areas_with_messages)
        if netmail:
            # Import here to avoid circular dependency
            from .fidonet_module import FidoNetModule

            # Create FidoNet module instance to send netmail
            fidonet = FidoNetModule(self.config, self.logger)
            success = fidonet.create_message(netmail, 'NETMAIL')

            # Actually create the packet file
            if success:
                success = fidonet.create_packets()

            if success:
                # Update notification state
                state = self.load_notification_state()
                state["last_notification"] = datetime.now().isoformat()
                state["notified_areas"] = areas_with_messages
                self.save_notification_state(state)

                self.logger.info(f"Sent netmail notification to {netmail['to_name']} about held messages in {len(areas_with_messages)} area(s)")
            else:
                self.logger.error("Failed to send netmail notification")
