"""Regression: urllib do_open already passes timeout=req.timeout."""

from __future__ import annotations

import http.client
import urllib.request
from typing import Any
from unittest.mock import MagicMock, patch

from main import RSS_FETCH_TIMEOUT_S, _TimeoutHTTPHandler, _TimeoutHTTPSHandler


def test_http_handler_sets_req_timeout_without_kwarg_collision() -> None:
    handler = _TimeoutHTTPHandler(RSS_FETCH_TIMEOUT_S)
    req = urllib.request.Request("http://example.com/rss.xml")
    captured: dict[str, Any] = {}

    def fake_do_open(
        http_class: object,
        request: urllib.request.Request,
        **kwargs: Any,
    ) -> MagicMock:
        captured["http_class"] = http_class
        captured["timeout"] = request.timeout
        captured["kwargs"] = kwargs
        return MagicMock()

    with patch.object(handler, "do_open", side_effect=fake_do_open):
        handler.http_open(req)

    assert captured["http_class"] is http.client.HTTPConnection
    assert captured["timeout"] == RSS_FETCH_TIMEOUT_S
    assert "timeout" not in captured["kwargs"]


def test_https_handler_sets_req_timeout_without_kwarg_collision() -> None:
    handler = _TimeoutHTTPSHandler(RSS_FETCH_TIMEOUT_S)
    req = urllib.request.Request("https://example.com/rss.xml")
    captured: dict[str, Any] = {}

    def fake_do_open(
        http_class: object,
        request: urllib.request.Request,
        **kwargs: Any,
    ) -> MagicMock:
        captured["http_class"] = http_class
        captured["timeout"] = request.timeout
        captured["kwargs"] = kwargs
        return MagicMock()

    with patch.object(handler, "do_open", side_effect=fake_do_open):
        handler.https_open(req)

    assert captured["http_class"] is http.client.HTTPSConnection
    assert captured["timeout"] == RSS_FETCH_TIMEOUT_S
    assert "timeout" not in captured["kwargs"]
    assert "context" in captured["kwargs"]
