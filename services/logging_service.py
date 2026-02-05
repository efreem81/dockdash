"""Centralized logging configuration for DockDash.

This module provides:
- Persistent app log level (stored in DB)
- Safe, consistent stdout logging format
- Helpers to apply log level changes at runtime
"""

from __future__ import annotations

import logging
import os
import sys
import warnings
from typing import Optional


_VALID_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
}


def normalize_level(level: str | None, default: str = 'INFO') -> str:
    level = (level or '').strip().upper() or default
    return level if level in _VALID_LEVELS else default


def get_effective_log_level(app=None) -> str:
    """Return the effective log level string.

    Priority:
    1) DB AppSettings.log_level (if available)
    2) env APP_LOG_LEVEL
    3) default INFO
    """
    # Avoid importing models unless we have an app context.
    try:
        from flask import has_app_context
        if app is not None:
            # Explicit app passed; treat as ok.
            pass
        if has_app_context():
            from models import AppSettings
            settings = AppSettings.get_settings()
            return normalize_level(getattr(settings, 'log_level', None), default=normalize_level(os.environ.get('APP_LOG_LEVEL')))
    except Exception:
        pass

    return normalize_level(os.environ.get('APP_LOG_LEVEL'), default='INFO')


def configure_app_logging(app=None, level: Optional[str] = None) -> str:
    """Configure root/Flask logging. Returns the applied level string."""
    applied_level = normalize_level(level) if level else get_effective_log_level(app=app)
    numeric_level = _VALID_LEVELS[applied_level]

    root = logging.getLogger()

    # Ensure we have exactly one stdout handler with a good format.
    handler_exists = any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    if not handler_exists:
        handler = logging.StreamHandler(stream=sys.stdout)
        formatter = logging.Formatter(
            fmt='%(asctime)s %(levelname)s %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)

    root.setLevel(numeric_level)

    # Suppress urllib3 TLS verification warnings (request made with verify=False).
    try:
        from urllib3.exceptions import InsecureRequestWarning
        warnings.filterwarnings('ignore', category=InsecureRequestWarning)
    except Exception:
        pass

    # Keep noisy libraries quieter unless explicitly debugging.
    if numeric_level > logging.DEBUG:
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('requests').setLevel(logging.WARNING)

    if app is not None:
        try:
            app.logger.setLevel(numeric_level)
        except Exception:
            pass

    return applied_level


def set_db_log_level(level: str) -> str:
    """Persist app log level in DB (requires app context)."""
    from models import AppSettings
    from config import db

    normalized = normalize_level(level)
    settings = AppSettings.get_settings()
    settings.log_level = normalized
    db.session.add(settings)
    db.session.commit()
    return normalized
