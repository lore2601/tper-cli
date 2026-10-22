"""Error types and stable exit codes.

Every failure surfaces as a :class:`TperError` so the CLI can print one
machine-readable JSON error object and exit with a documented code.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any


class ExitCode(IntEnum):
    """Process exit codes. These are part of the public interface."""

    OK = 0
    UPSTREAM = 1
    SETUP = 2
    VALIDATION = 3
    POLICY = 4
    INTERNAL = 5


class TperError(Exception):
    """Base class for all expected errors."""

    exit_code: ExitCode = ExitCode.INTERNAL
    reason: str = "internal"

    def __init__(
        self,
        message: str,
        *,
        hint: str | None = None,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        if reason is not None:
            self.reason = reason
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {
            "exitCode": int(self.exit_code),
            "reason": self.reason,
            "message": self.message,
        }
        if self.hint:
            error["hint"] = self.hint
        error.update(self.details)
        return {"error": error}


class ValidationError(TperError):
    """Invalid user input (bad stop code, time, line, ...)."""

    exit_code = ExitCode.VALIDATION
    reason = "invalidArgument"


class NotFoundError(ValidationError):
    """The stop, line, place or station does not exist."""

    reason = "notFound"


class AmbiguousError(ValidationError):
    """A name matched several things. ``candidates`` lists them."""

    reason = "ambiguous"


class SetupError(TperError):
    """Something local is missing: profile, optional dependency, open data."""

    exit_code = ExitCode.SETUP
    reason = "setupRequired"


class PolicyError(TperError):
    """The local policy refused the action."""

    exit_code = ExitCode.POLICY
    reason = "policyDenied"


class ConfirmationRequired(PolicyError):
    """A write was attempted non-interactively without ``--yes``."""

    reason = "confirmationRequired"


class NetworkError(TperError):
    """The service could not be reached."""

    exit_code = ExitCode.UPSTREAM
    reason = "networkError"


class UpstreamError(TperError):
    """A TPER or Trenitalia service answered with an error or something unexpected."""

    exit_code = ExitCode.UPSTREAM
    reason = "upstreamError"

    def __init__(
        self,
        message: str,
        *,
        service: str,
        http_status: int | None = None,
        hint: str | None = None,
        reason: str | None = None,
    ) -> None:
        details: dict[str, Any] = {"service": service}
        if http_status is not None:
            details["httpStatus"] = http_status
        super().__init__(message, hint=hint, reason=reason, details=details)
        self.service = service
        self.http_status = http_status
