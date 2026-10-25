"""Tests for stdin deadlock prevention and non-blocking JSON reading in hook adapter.

Scenario:
- When sys.stdin is not a tty (e.g. pipe or mock stream) but no data is piped / EOF is delayed,
  standard sys.stdin.read() blocks indefinitely.
- read_hook_input() must handle non-blocking or select-based timeout gracefully without hanging,
  returning {} if no input arrives within a bounded threshold (e.g. 0.1s - 0.25s) or if EOF is reached.
- Valid JSON on stdin (with EOF or immediate availability) still parses correctly into dict.
"""
from __future__ import annotations

import io
import json
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from guard_cli.hook import read_hook_input


def test_read_hook_input_pipe_no_data_times_out_without_deadlock():
    """When stdin is a pipe with no data written and write-end kept open,

    read_hook_input() must not hang indefinitely; it should return {} within bounded timeout (~0.2s).
    """
    r_fd, w_fd = os.pipe()
    pipe_in = os.fdopen(r_fd, "r", encoding="utf-8")
    result: list[dict] = []

    def target():
        result.append(read_hook_input())

    th = threading.Thread(target=target, daemon=True)
    start_time = time.monotonic()
    try:
        with patch("sys.stdin", pipe_in):
            th.start()
            # Wait up to 0.4s (well above 0.2s threshold, but short enough to avoid hanging test suite)
            th.join(timeout=0.4)
            elapsed = time.monotonic() - start_time

            # If read_hook_input uses standard blocking read(), thread is still alive here
            assert not th.is_alive(), (
                f"read_hook_input() deadlocked on empty pipe! Still running after {elapsed:.3f}s"
            )
            assert result == [{}]
            assert elapsed >= 0.15, f"Expected select to wait bounded threshold (~0.2s), took {elapsed:.3f}s"
    finally:
        try:
            os.close(w_fd)
        except OSError:
            pass
        th.join(timeout=0.2)
        try:
            pipe_in.close()
        except OSError:
            pass


def test_read_hook_input_pipe_with_eof_returns_empty_dict():
    """When stdin is an empty pipe where EOF was reached (write end closed),

    read_hook_input() returns {} immediately without hanging.
    """
    r_fd, w_fd = os.pipe()
    os.close(w_fd)  # Signal immediate EOF
    pipe_in = os.fdopen(r_fd, "r", encoding="utf-8")
    try:
        with patch("sys.stdin", pipe_in):
            start_time = time.monotonic()
            data = read_hook_input()
            elapsed = time.monotonic() - start_time
            assert data == {}
            assert elapsed < 0.1  # EOF is ready immediately
    finally:
        pipe_in.close()


def test_read_hook_input_pipe_with_valid_json():
    """When stdin has valid JSON available, read_hook_input() parses and returns it."""
    r_fd, w_fd = os.pipe()
    payload = {"conversationId": "conv-1234", "cwd": "/tmp/test", "stop_hook_active": True}
    with os.fdopen(w_fd, "w", encoding="utf-8") as pipe_out:
        json.dump(payload, pipe_out)

    pipe_in = os.fdopen(r_fd, "r", encoding="utf-8")
    try:
        with patch("sys.stdin", pipe_in):
            data = read_hook_input()
            assert data == payload
    finally:
        pipe_in.close()


def test_read_hook_input_pipe_with_invalid_json():
    """When stdin has malformed JSON, read_hook_input() returns {} safely."""
    r_fd, w_fd = os.pipe()
    with os.fdopen(w_fd, "w", encoding="utf-8") as pipe_out:
        pipe_out.write("NOT_VALID_JSON{:::}")

    pipe_in = os.fdopen(r_fd, "r", encoding="utf-8")
    try:
        with patch("sys.stdin", pipe_in):
            data = read_hook_input()
            assert data == {}
    finally:
        pipe_in.close()


def test_read_hook_input_tty_returns_empty_immediately():
    """When stdin is a tty (interactive terminal), returns {} immediately without reading."""
    mock_stdin = MagicMock()
    mock_stdin.isatty.return_value = True

    with patch("sys.stdin", mock_stdin):
        start_time = time.monotonic()
        data = read_hook_input()
        elapsed = time.monotonic() - start_time

        assert data == {}
        assert elapsed < 0.05
        mock_stdin.read.assert_not_called()


def test_read_hook_input_debug_payload_capture(tmp_path, monkeypatch):
    """When GUARD_DEBUG_PAYLOAD=1, valid JSON payload is saved to .guard/last_payload.json."""
    monkeypatch.setenv("GUARD_DEBUG_PAYLOAD", "1")
    monkeypatch.chdir(tmp_path)

    payload = {"session_id": "sess-debug", "test": True}
    r_fd, w_fd = os.pipe()
    with os.fdopen(w_fd, "w", encoding="utf-8") as pipe_out:
        json.dump(payload, pipe_out)

    pipe_in = os.fdopen(r_fd, "r", encoding="utf-8")
    try:
        with patch("sys.stdin", pipe_in):
            data = read_hook_input()
            assert data == payload
            payload_file = tmp_path / ".guard" / "last_payload.json"
            assert payload_file.exists()
            assert json.loads(payload_file.read_text(encoding="utf-8")) == payload
    finally:
        pipe_in.close()


def test_read_hook_input_in_memory_stream_compatibility():
    """Ensures fallback works for streams without fileno (e.g. io.StringIO in tests)."""
    payload = {"source": "stringio"}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        data = read_hook_input()
        assert data == payload
