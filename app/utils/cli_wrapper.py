"""CLI Script Wrapper for Async Subprocess Execution.

This module provides an async wrapper around subprocess calls to CLI scripts,
preventing blocking of the async event loop during long-running operations.

Critical Pattern:
- Workers MUST use this wrapper instead of subprocess.run() directly
- Ensures non-blocking execution via asyncio.to_thread()
- Enforces timeout management per script type
- Provides structured error handling with CLIScriptError

Architecture Reference:
- project-context.md: CLI Scripts Architecture (lines 59-116)
- project-context.md: Integration Utilities (MANDATORY) (lines 117-278)
"""

import asyncio
import subprocess
from pathlib import Path

from app.utils.logging import get_logger

log = get_logger(__name__)


class CLIScriptError(Exception):
    """Raised when CLI script fails with non-zero exit code.

    Attributes:
        script (str): Script name (e.g., "generate_asset.py")
        exit_code (int): Process exit code
        stderr (str): Captured stderr output
    """

    def __init__(self, script: str, exit_code: int, stderr: str) -> None:
        self.script: str = script
        self.exit_code: int = exit_code
        self.stderr: str = stderr
        super().__init__(f"{script} failed with exit code {exit_code}: {stderr}")


async def run_cli_script(
    script: str,
    args: list[str],
    timeout: int = 600
) -> subprocess.CompletedProcess[str]:
    """Run CLI script without blocking async event loop.

    This function wraps `subprocess.run()` with `asyncio.to_thread()` to prevent
    blocking the event loop during long-running CLI operations (video generation,
    audio synthesis, etc.).

    Args:
        script: Script name (e.g., "generate_asset.py")
        args: List of command-line arguments
        timeout: Timeout in seconds (default: 600 = 10 min for Kling videos)

    Returns:
        CompletedProcess with stdout, stderr, returncode

    Raises:
        CLIScriptError: If script exits with non-zero code
        asyncio.TimeoutError: If script exceeds timeout
        ValueError: If script path contains path traversal sequences
        FileNotFoundError: If script file doesn't exist

    Example:
        >>> result = await run_cli_script(
        ...     "generate_asset.py",
        ...     ["--prompt", "A forest scene", "--output", "/path/to/asset.png"],
        ...     timeout=60
        ... )
        >>> print(result.stdout)
        "✅ Asset generated: /path/to/asset.png"
    """
    # Security: Validate script is within scripts directory (prevent path traversal)
    scripts_dir = Path("scripts").resolve()
    script_path = (Path("scripts") / script).resolve()

    if not script_path.is_relative_to(scripts_dir):
        raise ValueError(f"Script must be in scripts directory, got: {script}")

    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    command = ["python", str(script_path), *args]

    # Security: Sanitize args for logging (prevent exposing API keys, secrets)
    # Redact common sensitive argument patterns
    sanitized_args = []
    skip_next = False
    for arg in args:
        if skip_next:
            sanitized_args.append("***REDACTED***")
            skip_next = False
        elif arg.lower() in ("--api-key", "--key", "--token", "--secret", "--password"):
            sanitized_args.append(arg)
            skip_next = True
        elif "=" in arg and any(
            key in arg.lower() for key in ("key", "token", "secret", "password")
        ):
            param, _ = arg.split("=", 1)
            sanitized_args.append(f"{param}=***REDACTED***")
        else:
            # Truncate long arguments (prompts, file paths) to prevent log bloat
            sanitized_args.append(arg[:100] + "..." if len(arg) > 100 else arg)

    log.info("cli_script_start", script=script, args=sanitized_args, timeout=timeout)

    try:
        # Use asyncio.to_thread to avoid blocking event loop
        result = await asyncio.to_thread(
            subprocess.run,
            command,
            capture_output=True,  # Capture stdout/stderr
            text=True,            # Decode as UTF-8 strings
            errors='replace',     # Replace invalid UTF-8 with replacement character
            timeout=timeout       # Enforce timeout
        )

        if result.returncode != 0:
            # Truncate stderr to prevent log bloat
            stderr_truncated = (
                result.stderr[:500] + "..." if len(result.stderr) > 500
                else result.stderr
            )
            log.error(
                "cli_script_error",
                script=script,
                exit_code=result.returncode,
                stderr=stderr_truncated
            )
            raise CLIScriptError(script, result.returncode, result.stderr)

        # Truncate stdout to prevent log bloat
        stdout_truncated = (
            result.stdout[:500] + "..." if len(result.stdout) > 500
            else result.stdout
        )
        log.info("cli_script_success", script=script, stdout=stdout_truncated)
        return result

    except subprocess.TimeoutExpired as e:
        log.error("cli_script_timeout", script=script, timeout=timeout)
        raise asyncio.TimeoutError(f"{script} exceeded timeout of {timeout}s") from e
