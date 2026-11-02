"""Secret-bearing URLs stay private in Uvicorn's real formatters and WS hooks."""

import asyncio
import io
import logging

import pytest
from uvicorn.logging import AccessFormatter, DefaultFormatter
from uvicorn.protocols.websockets.websockets_impl import WebSocketProtocol

import main  # noqa: F401 -- installs production log filters


SENTINEL = "SECRET_SENTINEL_DO_NOT_LOG"


@pytest.fixture
def captured_logger():
    records = []

    class Capture(logging.StreamHandler):
        def emit(self, record):
            records.append(record)
            super().emit(record)

    attached = []

    def capture(name, formatter):
        logger = logging.getLogger(name)
        output = io.StringIO()
        handler = Capture(output)
        handler.setFormatter(formatter)
        previous = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        attached.append((logger, handler, previous))
        return logger, output, records

    yield capture
    for logger, handler, previous in attached:
        logger.removeHandler(handler)
        logger.setLevel(previous)


@pytest.mark.parametrize("accepted", [True, False])
@pytest.mark.parametrize("token_key", ["token", "%74%6fken", "access_token"])
def test_actual_uvicorn_websocket_handshake_logs_redact_query_token(captured_logger, accepted, token_key):
    logger, output, records = captured_logger("uvicorn.error", DefaultFormatter(use_colors=False))

    async def emit_handshake_log():
        # Exercise installed Uvicorn's own log call, without binding a socket.
        protocol = WebSocketProtocol.__new__(WebSocketProtocol)
        protocol.logger = logger
        protocol.scope = {
            "client": ("192.0.2.10", 12345),
            "path": "/ws/stats",
            "query_string": f"{token_key}={SENTINEL}&mode=normal".encode(),
        }
        protocol.handshake_started_event = asyncio.Event()
        protocol.closed_event = asyncio.Event()
        protocol.extra_headers = []
        await protocol.asgi_send({"type": "websocket.accept" if accepted else "websocket.close"})

    asyncio.run(emit_handshake_log())
    assert SENTINEL not in output.getvalue()
    assert SENTINEL not in repr(records[0].args)
    assert f"/ws/stats?{token_key}=[REDACTED]&mode=normal" in output.getvalue()
    assert records[0].args == ()


@pytest.mark.parametrize("path", [
    f"/api/subscriptions/fetch/{SENTINEL}",
    f"/api/subscriptions/qr/{SENTINEL}?size=256",
    f"/api/subscriptions/info/{SENTINEL}",
    f"/s/{SENTINEL}",
    f"/ws/stats?mode=normal&token={SENTINEL}",
])
def test_real_access_formatter_preserves_shape_and_removes_secrets(captured_logger, path):
    formatter = AccessFormatter(
        fmt='%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False
    )
    logger, output, records = captured_logger("uvicorn.access", formatter)
    logger.info('%s - "%s %s HTTP/%s" %d', "192.0.2.10:12345", "GET", path, "1.1", 200)
    assert SENTINEL not in output.getvalue()
    assert SENTINEL not in repr(records[0].args)
    assert "[REDACTED]" in output.getvalue()
    assert "200 OK" in output.getvalue()
    assert "HTTP/1.1" in output.getvalue()


def test_error_message_mapping_and_traceback_are_redacted(captured_logger):
    logger, output, records = captured_logger("uvicorn.error", DefaultFormatter(use_colors=False))
    try:
        raise RuntimeError("upstream rejected /s/" + SENTINEL)
    except RuntimeError:
        logger.exception("request failed: %(url)s", {"url": f"/ws/stats?token={SENTINEL}"})
    assert SENTINEL not in output.getvalue()
    assert SENTINEL not in repr(records[0].args)
    assert records[0].exc_info is None
    assert "RuntimeError: upstream rejected /s/[REDACTED]" in output.getvalue()


def test_application_logger_redacts_error(captured_logger):
    logger, output, _ = captured_logger("uniproxy", logging.Formatter("%(message)s"))
    logger.error("failed to request %s", f"/api/subscriptions/fetch/{SENTINEL}")
    assert SENTINEL not in output.getvalue()
    assert "/api/subscriptions/fetch/[REDACTED]" in output.getvalue()


def test_unrelated_message_is_unchanged(captured_logger):
    logger, output, _ = captured_logger("uvicorn.error", DefaultFormatter(use_colors=False))
    logger.info("background task %s completed with %d entries", "health", 3)
    assert "background task health completed with 3 entries" in output.getvalue()
