"""Node failure reasons must never be blank (asyncio.TimeoutError has no message)."""

from __future__ import annotations

import asyncio

from aletheia.core.graph_flow import describe_node_failure


def test_timeout_message_names_the_limit_and_the_setting() -> None:
    msg = describe_node_failure(asyncio.TimeoutError(), 120)
    assert "120s" in msg
    assert "ALETHEIA_NODE_TIMEOUT_SECS" in msg


def test_other_errors_keep_their_message() -> None:
    assert describe_node_failure(ValueError("bad input"), 120) == "bad input"


def test_empty_exception_falls_back_to_class_name() -> None:
    assert describe_node_failure(RuntimeError(), 120) == "RuntimeError"
