"""Ingress is bounded before multipart parsing or any route mutation."""

import asyncio

import anyio
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security import LimitedRequestBodies


def run_request(chunks, headers=()):
    seen, sent = [], []

    async def app(scope, receive, send):
        while True:
            message = await receive()
            seen.append(message["body"])
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})

    async def run():
        incoming = iter(
            [
                {
                    "type": "http.request",
                    "body": chunk,
                    "more_body": i < len(chunks) - 1,
                }
                for i, chunk in enumerate(chunks)
            ]
        )

        async def receive():
            return next(incoming)

        async def send(message):
            sent.append(message)

        await LimitedRequestBodies(app)(
            {"type": "http", "method": "POST", "headers": list(headers)},
            receive,
            send,
        )

    asyncio.run(run())
    return next(item["status"] for item in sent if "status" in item), b"".join(seen)


@pytest.mark.parametrize("headers", [[], [(b"transfer-encoding", b"chunked")]])
def test_streamed_body_cannot_bypass_limit(monkeypatch, headers):
    monkeypatch.setattr("app.security.MAX_REQUEST_BODY_BYTES", 8)
    assert run_request([b"1234", b"56789"], headers) == (413, b"")


def test_boundary_body_replayed_exactly(monkeypatch):
    monkeypatch.setattr("app.security.MAX_REQUEST_BODY_BYTES", 8)
    assert run_request([b"1234", b"5678"]) == (204, b"12345678")


@pytest.mark.parametrize("length", [b"9", b"9" * 5000])
def test_declared_oversize_rejected_without_receiving(monkeypatch, length):
    monkeypatch.setattr("app.security.MAX_REQUEST_BODY_BYTES", 8)
    assert run_request([], [(b"content-length", length)]) == (413, b"")


@pytest.mark.parametrize("length", [b"-1", b"+1", b"", b"one", b"1,1"])
def test_invalid_lengths_rejected(length):
    assert run_request([], [(b"content-length", length)]) == (400, b"")


def test_duplicate_lengths_rejected():
    assert run_request([], [(b"content-length", b"1")] * 2) == (400, b"")


def test_misleading_length_does_not_bypass_actual_limit(monkeypatch):
    monkeypatch.setattr("app.security.MAX_REQUEST_BODY_BYTES", 8)
    assert run_request([b"123456789"], [(b"content-length", b"1")]) == (413, b"")
    assert run_request([b"12"], [(b"content-length", b"1")]) == (400, b"")


def test_spooled_body_replays_without_changes():
    body = b"x" * (1024 * 1024 + 1)
    assert run_request([body]) == (204, body)


def test_oversized_request_closes_scratch_file(monkeypatch):
    from tempfile import SpooledTemporaryFile

    files = []

    def tracked_spool(*args, **kwargs):
        spool = SpooledTemporaryFile(*args, **kwargs)
        files.append(spool)
        return spool

    monkeypatch.setattr("app.security.SpooledTemporaryFile", tracked_spool)
    monkeypatch.setattr("app.security.MAX_REQUEST_BODY_BYTES", 8)
    assert run_request([b"1234", b"56789"])[0] == 413
    assert files and all(spool.closed for spool in files)


def test_slow_request_times_out_and_releases_admission(monkeypatch):
    original = anyio.fail_after
    monkeypatch.setattr("app.security.anyio.fail_after", lambda _: original(0.01))

    async def run():
        middleware = LimitedRequestBodies(None)
        sent = []

        async def receive():
            await anyio.sleep(1)

        async def send(message):
            sent.append(message)

        await middleware(
            {"type": "http", "method": "POST", "headers": []}, receive, send
        )
        assert sent[0]["status"] == 408
        assert middleware.capacity.borrowed_tokens == 0

    asyncio.run(run())


def test_host_and_origin_checks_precede_body_limit(tmp_path, monkeypatch):
    library, data = tmp_path / "library", tmp_path / "data"
    library.mkdir()
    data.mkdir()
    monkeypatch.setattr("app.security.MAX_REQUEST_BODY_BYTES", 8)
    with TestClient(
        create_app(
            Settings(
                library_path=library, data_path=data, allowed_hosts=("testserver",)
            )
        )
    ) as client:
        for headers, expected in [
            ({"Host": "attacker.example"}, 400),
            ({"Origin": "http://attacker.example"}, 403),
            ({"Origin": "http://testserver"}, 413),
        ]:
            response = client.post("/rescan", content=b"123456789", headers=headers)
            assert response.status_code == expected
            assert response.headers["x-content-type-options"] == "nosniff"


def test_concurrent_submissions_are_bounded():
    async def run():
        middleware = LimitedRequestBodies(None)
        borrowers = [object() for _ in range(4)]
        for borrower in borrowers:
            middleware.capacity.acquire_on_behalf_of_nowait(borrower)
        sent = []

        async def receive():
            pytest.fail("Busy request must not be read")

        async def send(message):
            sent.append(message)

        await middleware(
            {"type": "http", "method": "POST", "headers": []}, receive, send
        )
        assert sent[0]["status"] == 503
        for borrower in borrowers:
            middleware.capacity.release_on_behalf_of(borrower)

    asyncio.run(run())


@pytest.mark.parametrize("body", [b"", b"upload"])
def test_disconnect_after_replay_is_preserved(body):
    async def run():
        incoming = iter(
            [
                {"type": "http.request", "body": body, "more_body": False},
                {"type": "http.disconnect"},
            ]
        )

        async def receive():
            return next(incoming)

        async def app(scope, replay, send):
            assert (await replay())["body"] == body
            assert await replay() == {"type": "http.disconnect"}

        await LimitedRequestBodies(app)(
            {"type": "http", "method": "POST", "headers": []}, receive, None
        )

    asyncio.run(run())


def test_trusted_proxy_scheme_only_applies_to_configured_peer(tmp_path):
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    library, data = tmp_path / "library", tmp_path / "data"
    library.mkdir()
    data.mkdir()
    app = create_app(
        Settings(library_path=library, data_path=data, allowed_hosts=("testserver",))
    )
    proxy = ProxyHeadersMiddleware(app, trusted_hosts="192.0.2.10")
    for peer, expected in [("192.0.2.10", 303), ("192.0.2.11", 403)]:
        with TestClient(proxy, client=(peer, 12345)) as client:
            response = client.post(
                "/rescan",
                follow_redirects=False,
                headers={"Origin": "https://testserver", "X-Forwarded-Proto": "https"},
            )
            assert response.status_code == expected
