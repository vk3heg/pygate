# Pygate Development Log
# Version prio to 1.5.7 did'nt have a devlog
#

PyGate - Python FidoNet-NNTP Gateway

PyGate is a Python-based gateway system that bridges FidoNet echomail and NNTP newsgroups, allowing
seamless message exchange between the two networks. PyGate is designed to run on the NNTP news server,
but can be run on a different computer as a client only.

**Last Updated:** January 31, 2026
**Language:** Python 3.7+


### Version 1.5.8 (January 31, 2026)

#==============================================================================
# FIDONET ORIGIN FILTERS
# Block messages from specific FidoNet systems
#==============================================================================

^Origin:(?i).*\(1:135/250\)

The pattern explained:
  - ^Origin: - matches the Origin header type
  - (?i) - case insensitive
  - .* - match anything
  - \(1:135/250\) - match the address in parentheses (escaped because parentheses are regex special chars)

This will block messages in both directions (FidoNet->NNTP and NNTP->FidoNet) from that system.


### Version 1.5.7 (January 30, 2026)

When converting NNTP to FidoNet, PyGate now checks for the X-FTN-MSGID header first. If present (indicating the
message originated from FidoNet), it uses the original MSGID instead of generating a new one. This allows FidoNet
duplicate detection to work correctly and prevents message loops.

The flow is now:
1. FidoNet -> NNTP: MSGID: 2:221/1 697c6658 -> X-FTN-MSGID: 2:221/1 697c6658
2. NNTP -> FidoNet: X-FTN-MSGID: 2:221/1 697c6658 -> MSGID: 2:221/1 697c6658 (same!)

Duplicate detection will now recognize it as the same message.

