"""
Input validation utilities for security-critical operations.

Prevents command injection, path traversal, and other input-based attacks.
"""

import re
from pathlib import Path
from typing import Literal


class ValidationError(ValueError):
    """Raised when input validation fails."""

    pass


def validate_backup_name(backup_name: str, *, allow_system_prefix: bool = True) -> str:
    """
    Validate backup name to prevent path traversal and command injection.

    Args:
        backup_name: User-provided backup name
        allow_system_prefix: Whether to allow system_backup_ prefix

    Returns:
        Validated backup name

    Raises:
        ValidationError: If backup name is invalid
    """
    if not backup_name:
        raise ValidationError("Backup name cannot be empty")

    # Check length
    if len(backup_name) > 255:
        raise ValidationError("Backup name too long (max 255 characters)")

    # Check for path traversal attempts
    if ".." in backup_name:
        raise ValidationError("Backup name cannot contain '..'")

    if backup_name.startswith("/") or backup_name.startswith("\\"):
        raise ValidationError("Backup name cannot be an absolute path")

    # Check for shell metacharacters that could enable command injection
    dangerous_chars = [";", "&", "|", "$", "`", "(", ")", "<", ">", "\n", "\r"]
    for char in dangerous_chars:
        if char in backup_name:
            raise ValidationError(f"Backup name contains invalid character: {char!r}")

    # Validate format: must be alphanumeric, dash, underscore, or dot
    # Allow timestamp format: backup_YYYYMMDD_HHMMSS or system_backup_YYYYMMDD_HHMMSS
    if allow_system_prefix:
        pattern = r"^(system_)?backup_\d{8}_\d{6}(\.\w+)?$"
    else:
        pattern = r"^backup_\d{8}_\d{6}(\.\w+)?$"

    if not re.match(pattern, backup_name):
        raise ValidationError(
            f"Backup name must match format: {'(system_)?' if allow_system_prefix else ''}backup_YYYYMMDD_HHMMSS"
        )

    return backup_name


def validate_backup_dir(backup_dir: str) -> str:
    """
    Validate backup directory to prevent path traversal.

    Args:
        backup_dir: User-provided backup directory

    Returns:
        Validated backup directory

    Raises:
        ValidationError: If directory path is invalid
    """
    if not backup_dir:
        raise ValidationError("Backup directory cannot be empty")

    # Check for path traversal
    if ".." in backup_dir:
        raise ValidationError("Backup directory cannot contain '..'")

    # Must be relative path (not absolute)
    if backup_dir.startswith("/") or (len(backup_dir) > 1 and backup_dir[1] == ":"):
        raise ValidationError("Backup directory must be a relative path")

    # Check for shell metacharacters
    dangerous_chars = [";", "&", "|", "$", "`", "(", ")", "<", ">", "\n", "\r"]
    for char in dangerous_chars:
        if char in backup_dir:
            raise ValidationError(f"Backup directory contains invalid character: {char!r}")

    # Only allow alphanumeric, dash, underscore, slash
    if not re.match(r"^[\w\-/]+$", backup_dir):
        raise ValidationError("Backup directory contains invalid characters")

    return backup_dir


def validate_backup_components(components: str | None) -> str | None:
    """
    Validate backup components string.

    Args:
        components: Comma-separated list of component names

    Returns:
        Validated components string or None

    Raises:
        ValidationError: If components string is invalid
    """
    if not components:
        return None

    # Check for shell metacharacters
    dangerous_chars = [";", "&", "|", "$", "`", "(", ")", "<", ">", "\n", "\r", ".."]
    for char in dangerous_chars:
        if char in components:
            raise ValidationError(f"Components string contains invalid character: {char!r}")

    # Split and validate individual components
    valid_components = {"database", "models", "config", "outputs", "logs", "docker_volumes"}
    component_list = [c.strip() for c in components.split(",")]

    for component in component_list:
        if component not in valid_components:
            raise ValidationError(f"Invalid component: {component!r}")

    return components


def validate_file_path(
    file_path: Path | str,
    allowed_base: Path,
    *,
    must_exist: bool = False,
    allowed_extensions: set[str] | None = None,
) -> Path:
    """
    Validate that a file path is within allowed directory and safe to use.

    Args:
        file_path: File path to validate
        allowed_base: Base directory that file must be within
        must_exist: If True, path must exist
        allowed_extensions: If provided, file extension must be in this set

    Returns:
        Resolved absolute path

    Raises:
        ValidationError: If path is invalid or unsafe
    """
    try:
        path = Path(file_path).resolve()
        base = Path(allowed_base).resolve()
    except (ValueError, OSError) as e:
        raise ValidationError(f"Invalid path: {e}") from e

    # Check if path is within allowed base
    try:
        path.relative_to(base)
    except ValueError as e:
        raise ValidationError(f"Path is outside allowed directory: {path}") from e

    # Check existence
    if must_exist and not path.exists():
        raise ValidationError(f"Path does not exist: {path}")

    # Check extension
    if allowed_extensions is not None and path.suffix not in allowed_extensions:
        raise ValidationError(f"File extension {path.suffix!r} not allowed")

    return path


def sanitize_shell_arg(arg: str) -> str:
    """
    Sanitize a string for use as a shell argument.

    This is a defense-in-depth measure. Prefer passing arguments as list to subprocess.run
    instead of using shell=True.

    Args:
        arg: Argument to sanitize

    Returns:
        Sanitized argument

    Raises:
        ValidationError: If argument contains dangerous characters
    """
    # Reject strings with shell metacharacters
    dangerous_chars = [";", "&", "|", "$", "`", "(", ")", "<", ">", "\n", "\r", "\\"]
    for char in dangerous_chars:
        if char in arg:
            raise ValidationError(f"Argument contains dangerous character: {char!r}")

    return arg
