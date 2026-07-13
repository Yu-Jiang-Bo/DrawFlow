"""Shared synchronization for template registry, scans, and rule publication."""

import threading


TEMPLATE_STATE_LOCK = threading.RLock()
