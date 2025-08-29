"""Shared configuration and types."""

from .hardware import detect_hardware_info, parse_total_ram_gb
from .session import SessionManager, SessionState

__all__ = ["SessionManager", "SessionState", "detect_hardware_info", "parse_total_ram_gb"]
