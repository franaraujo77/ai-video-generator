"""
Unit tests for app/utils/cli_wrapper.py.

Tests CLI script wrapper for async subprocess execution, error handling,
timeout management, and non-blocking event loop behavior.
"""

import asyncio
import subprocess
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.utils.cli_wrapper import CLIScriptError, run_cli_script


class TestCLIScriptError:
    """Test CLIScriptError exception class."""

    def test_cli_script_error_attributes(self):
        """Test CLIScriptError has correct attributes and message format."""
        script = "generate_asset.py"
        exit_code = 1
        stderr = "API key missing"

        error = CLIScriptError(script, exit_code, stderr)

        assert error.script == script
        assert error.exit_code == exit_code
        assert error.stderr == stderr
        assert str(error) == f"{script} failed with exit code {exit_code}: {stderr}"


class TestRunCLIScript:
    """Test run_cli_script async function."""

    @pytest.mark.asyncio
    async def test_run_cli_script_success(self, mocker):
        """Test successful script execution returns CompletedProcess."""
        # Mock successful subprocess result
        mock_result = Mock(
            returncode=0,
            stdout="✅ Asset generated: /tmp/test.png",
            stderr=""
        )

        # Mock asyncio.to_thread to return mock result
        mocker.patch("asyncio.to_thread", return_value=mock_result)

        # Mock logger to avoid actual logging
        mocker.patch("app.utils.cli_wrapper.log")

        # Execute
        result = await run_cli_script(
            "generate_asset.py",
            ["--output", "/tmp/test.png"],
            timeout=60
        )

        # Verify
        assert result.returncode == 0
        assert result.stdout == "✅ Asset generated: /tmp/test.png"
        assert result.stderr == ""

    @pytest.mark.asyncio
    async def test_run_cli_script_failure(self, mocker):
        """Test script failure raises CLIScriptError with stderr."""
        # Mock failed subprocess result
        mock_result = Mock(
            returncode=1,
            stdout="",
            stderr="❌ GEMINI_API_KEY not found in environment"
        )

        mocker.patch("asyncio.to_thread", return_value=mock_result)
        mocker.patch("app.utils.cli_wrapper.log")

        # Execute and verify exception
        with pytest.raises(CLIScriptError) as exc_info:
            await run_cli_script(
                "generate_asset.py",
                ["--output", "/tmp/test.png"]
            )

        # Verify exception attributes
        assert exc_info.value.script == "generate_asset.py"
        assert exc_info.value.exit_code == 1
        assert "GEMINI_API_KEY not found" in exc_info.value.stderr

    @pytest.mark.asyncio
    async def test_run_cli_script_timeout(self, mocker):
        """Test script timeout raises asyncio.TimeoutError."""
        # Mock subprocess.TimeoutExpired exception
        mocker.patch(
            "asyncio.to_thread",
            side_effect=subprocess.TimeoutExpired(
                cmd=["python", "scripts/generate_video.py"],
                timeout=5
            )
        )
        mocker.patch("app.utils.cli_wrapper.log")

        # Execute and verify timeout exception
        with pytest.raises(asyncio.TimeoutError) as exc_info:
            await run_cli_script(
                "generate_video.py",
                ["--image", "comp.png", "--prompt", "motion"],
                timeout=5
            )

        # Verify timeout message includes script name
        assert "generate_video.py" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_run_cli_script_event_loop_non_blocking(self, mocker):
        """Test concurrent script executions don't block each other."""
        # Create mock results with delays to simulate long-running operations
        async def mock_to_thread_with_delay(*args, **kwargs):
            await asyncio.sleep(0.1)  # Simulate 100ms operation
            return Mock(returncode=0, stdout="Success", stderr="")

        mocker.patch("asyncio.to_thread", side_effect=mock_to_thread_with_delay)
        mocker.patch("app.utils.cli_wrapper.log")

        # Execute 3 scripts concurrently
        start_time = asyncio.get_event_loop().time()

        results = await asyncio.gather(
            run_cli_script("generate_asset.py", ["--output", "asset1.png"]),
            run_cli_script("generate_asset.py", ["--output", "asset2.png"]),
            run_cli_script("generate_asset.py", ["--output", "asset3.png"])
        )

        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time

        # Verify all succeeded
        assert len(results) == 3
        assert all(r.returncode == 0 for r in results)

        # Verify concurrent execution (should be ~0.1s, not 0.3s)
        # Allow some overhead for test execution
        assert duration < 0.25, f"Expected ~0.1s but took {duration}s (should be concurrent)"

    @pytest.mark.asyncio
    async def test_run_cli_script_constructs_correct_command(self, mocker):
        """Test command construction with script path and arguments."""
        mock_result = Mock(returncode=0, stdout="Success", stderr="")

        # Capture the command passed to subprocess.run
        captured_command = None

        def capture_subprocess_run(command, **kwargs):
            nonlocal captured_command
            captured_command = command
            return mock_result

        mocker.patch("asyncio.to_thread", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs))
        mocker.patch("subprocess.run", side_effect=capture_subprocess_run)
        mocker.patch("app.utils.cli_wrapper.log")

        # Execute
        await run_cli_script(
            "generate_asset.py",
            ["--prompt", "A forest", "--output", "/tmp/asset.png"],
            timeout=60
        )

        # Verify command construction
        assert captured_command[0] == "python"
        assert "scripts/generate_asset.py" in captured_command[1]
        assert "--prompt" in captured_command
        assert "A forest" in captured_command
        assert "--output" in captured_command
        assert "/tmp/asset.png" in captured_command

    @pytest.mark.asyncio
    async def test_run_cli_script_passes_timeout_to_subprocess(self, mocker):
        """Test timeout parameter is passed to subprocess.run."""
        mock_result = Mock(returncode=0, stdout="Success", stderr="")

        captured_kwargs = {}

        def capture_subprocess_run(command, **kwargs):
            nonlocal captured_kwargs
            captured_kwargs.update(kwargs)
            return mock_result

        mocker.patch("asyncio.to_thread", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs))
        mocker.patch("subprocess.run", side_effect=capture_subprocess_run)
        mocker.patch("app.utils.cli_wrapper.log")

        # Execute with custom timeout
        await run_cli_script("generate_video.py", ["--image", "comp.png"], timeout=300)

        # Verify timeout passed to subprocess
        assert captured_kwargs.get("timeout") == 300
        assert captured_kwargs.get("capture_output") is True
        assert captured_kwargs.get("text") is True

    @pytest.mark.asyncio
    async def test_run_cli_script_captures_stdout_stderr(self, mocker):
        """Test stdout and stderr are captured from subprocess."""
        mock_result = Mock(
            returncode=0,
            stdout="✅ Video generated successfully",
            stderr="⚠️ Warning: Low GPU memory"
        )

        mocker.patch("asyncio.to_thread", return_value=mock_result)
        mocker.patch("app.utils.cli_wrapper.log")

        # Execute
        result = await run_cli_script("generate_video.py", ["--image", "comp.png"])

        # Verify output captured
        assert "Video generated successfully" in result.stdout
        assert "Warning: Low GPU memory" in result.stderr

    @pytest.mark.asyncio
    async def test_run_cli_script_logging_on_success(self, mocker):
        """Test logging events are emitted on successful execution."""
        mock_result = Mock(returncode=0, stdout="Success", stderr="")
        mocker.patch("asyncio.to_thread", return_value=mock_result)

        mock_log = mocker.patch("app.utils.cli_wrapper.log")

        # Execute
        await run_cli_script("generate_asset.py", ["--output", "test.png"], timeout=60)

        # Verify log.info called for start and success
        assert mock_log.info.call_count == 2

        # Verify first call (cli_script_start)
        start_call = mock_log.info.call_args_list[0]
        assert start_call[0][0] == "cli_script_start"
        assert start_call[1]["script"] == "generate_asset.py"
        assert start_call[1]["timeout"] == 60

        # Verify second call (cli_script_success)
        success_call = mock_log.info.call_args_list[1]
        assert success_call[0][0] == "cli_script_success"

    @pytest.mark.asyncio
    async def test_run_cli_script_logging_on_failure(self, mocker):
        """Test logging events are emitted on script failure."""
        mock_result = Mock(returncode=1, stdout="", stderr="API key missing")
        mocker.patch("asyncio.to_thread", return_value=mock_result)

        mock_log = mocker.patch("app.utils.cli_wrapper.log")

        # Execute
        with pytest.raises(CLIScriptError):
            await run_cli_script("generate_asset.py", ["--output", "test.png"])

        # Verify log.error called
        assert mock_log.error.call_count == 1
        error_call = mock_log.error.call_args_list[0]
        assert error_call[0][0] == "cli_script_error"
        assert error_call[1]["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_run_cli_script_logging_on_timeout(self, mocker):
        """Test logging events are emitted on timeout."""
        mocker.patch(
            "asyncio.to_thread",
            side_effect=subprocess.TimeoutExpired(cmd=["python", "script.py"], timeout=5)
        )

        mock_log = mocker.patch("app.utils.cli_wrapper.log")

        # Execute
        with pytest.raises(asyncio.TimeoutError):
            await run_cli_script("generate_video.py", ["--image", "comp.png"], timeout=5)

        # Verify log.error called for timeout
        assert mock_log.error.call_count == 1
        timeout_call = mock_log.error.call_args_list[0]
        assert timeout_call[0][0] == "cli_script_timeout"
        assert timeout_call[1]["timeout"] == 5

    @pytest.mark.asyncio
    async def test_run_cli_script_path_traversal_blocked(self, mocker):
        """Test path traversal attempts are blocked for security."""
        mocker.patch("app.utils.cli_wrapper.log")

        # Attempt path traversal
        with pytest.raises(ValueError) as exc_info:
            await run_cli_script("../app/models.py", ["arg"])

        assert "Script must be in scripts directory" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_run_cli_script_missing_file_raises_filenotfound(self, mocker):
        """Test missing script file raises FileNotFoundError."""
        mocker.patch("app.utils.cli_wrapper.log")

        # Attempt to run non-existent script
        with pytest.raises(FileNotFoundError) as exc_info:
            await run_cli_script("nonexistent_script.py", ["arg"])

        assert "Script not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_run_cli_script_sanitizes_sensitive_args_in_logs(self, mocker):
        """Test sensitive arguments are redacted in logs."""
        mock_result = Mock(returncode=0, stdout="Success", stderr="")
        mocker.patch("asyncio.to_thread", return_value=mock_result)

        mock_log = mocker.patch("app.utils.cli_wrapper.log")

        # Execute with sensitive args
        await run_cli_script(
            "generate_asset.py",
            ["--api-key", "secret123", "--output", "/tmp/test.png"],
            timeout=60
        )

        # Verify log.info called with sanitized args
        start_call = mock_log.info.call_args_list[0]
        sanitized_args = start_call[1]["args"]

        # API key should be redacted
        assert "***REDACTED***" in sanitized_args
        assert "secret123" not in str(sanitized_args)

    @pytest.mark.asyncio
    async def test_run_cli_script_timeout_exception_chain(self, mocker):
        """Test timeout exception properly chains subprocess.TimeoutExpired."""
        timeout_exc = subprocess.TimeoutExpired(
            cmd=["python", "scripts/generate_video.py"],
            timeout=5
        )
        mocker.patch("asyncio.to_thread", side_effect=timeout_exc)
        mocker.patch("app.utils.cli_wrapper.log")

        # Execute and verify exception chain
        with pytest.raises(asyncio.TimeoutError) as exc_info:
            await run_cli_script("generate_video.py", ["--image", "comp.png"], timeout=5)

        # Verify exception chain preserves original TimeoutExpired
        assert exc_info.value.__cause__.__class__ == subprocess.TimeoutExpired
        assert exc_info.value.__cause__ == timeout_exc

    @pytest.mark.asyncio
    async def test_run_cli_script_handles_unicode_decode_errors(self, mocker):
        """Test non-UTF-8 output is handled gracefully with replacement chars."""
        # Mock result with replacement characters (simulating errors='replace')
        mock_result = Mock(
            returncode=0,
            stdout="Output with �� replacement chars",
            stderr=""
        )
        mocker.patch("asyncio.to_thread", return_value=mock_result)
        mocker.patch("app.utils.cli_wrapper.log")

        # Execute
        result = await run_cli_script("generate_asset.py", ["--output", "test.png"])

        # Verify replacement characters preserved
        assert "replacement chars" in result.stdout

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_run_actual_cli_script_with_python(self):
        """Integration test: Execute real subprocess with Python -c command."""
        # Create a temporary test script
        import tempfile
        import os
        from pathlib import Path

        # Create test script in scripts/ directory
        scripts_dir = Path("scripts")
        scripts_dir.mkdir(exist_ok=True)

        test_script = scripts_dir / "test_echo.py"
        test_script.write_text('import sys\nprint("Test output:", sys.argv[1])')

        try:
            # Execute real subprocess
            result = await run_cli_script("test_echo.py", ["hello"], timeout=5)

            # Verify output
            assert result.returncode == 0
            assert "Test output: hello" in result.stdout
        finally:
            # Cleanup
            if test_script.exists():
                test_script.unlink()
