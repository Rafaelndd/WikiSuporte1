import logging
import re
from typing import Pattern


_SENSITIVE_PATTERNS: list[Pattern[str]] = [
    re.compile(r"(?i)\b(password|passwd|pwd)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)\b(senha)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)\b(api[_-]?key)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)\b(token)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)\b(authorization)\s*[:=]\s*(bearer\s+[^\s,;]+)"),
    re.compile(r"(?i)\b(anydesk(?:\s*id)?)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)\b(login)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)(://[^:\s/]+:)([^@\s/]+)(@)"),
]


def _mask_match(match: re.Match[str]) -> str:
    if match.lastindex == 3:
        return f"{match.group(1)}***{match.group(3)}"
    if match.lastindex == 2:
        return f"{match.group(1)}: ***"
    return "***"


def redact_sensitive_text(text: str) -> str:
    if not text:
        return text
    redacted = text
    for pattern in _SENSITIVE_PATTERNS:
        redacted = pattern.sub(_mask_match, redacted)
    return redacted


class RedactSensitiveDataFilter(logging.Filter):
    """Mascara dados sensíveis antes de gravar logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
            redacted = redact_sensitive_text(message)
            record.msg = redacted
            record.args = ()
        except Exception:
            # Não interrompe fluxo de log em caso de erro no mascaramento.
            pass
        return True


def install_sensitive_data_redaction(logger: logging.Logger) -> None:
    """Instala filtro de mascaramento em handlers existentes (idempotente)."""
    for handler in logger.handlers:
        already_present = any(
            isinstance(log_filter, RedactSensitiveDataFilter)
            for log_filter in handler.filters
        )
        if not already_present:
            handler.addFilter(RedactSensitiveDataFilter())
