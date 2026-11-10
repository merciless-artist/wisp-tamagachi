"""Tests for the picture client: Wisp's drawings from the Cloudflare worker."""

import asyncio
import gc
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from ai.chain import USER_AGENT, ProviderError
from ai.images import ImageMaker, images_from_config
from wisp.rules import IMAGE_MAX_BYTES, IMAGE_TIMEOUT

JPEG = b"\xff\xd8\xff-not-really-a-picture"
PNG = b"\x89PNG-wisp-as-a-teen"
Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]

# ---
# Fake worker
# ---


@asynccontextmanager
async def serve(handler: Handler) -> AsyncIterator[str]:
    """Run a local fake of the image worker; yield its URL."""
    app = web.Application()
    app.router.add_post("/", handler)
    server = TestServer(app)
    await server.start_server()
    try:
        yield str(server.make_url("/"))
    finally:
        await server.close()


async def picture(request: web.Request) -> web.Response:
    return web.Response(body=JPEG, content_type="image/jpeg")


# ---
# Asking the worker
# ---


async def test_the_prompt_and_reference_go_as_a_form_and_the_picture_comes_back() -> (
    None
):
    seen: list[tuple[object, ...]] = []

    async def worker(request: web.Request) -> web.Response:
        form = await request.post()
        reference = form["reference"]
        assert isinstance(reference, web.FileField)
        seen.append(
            (
                form["prompt"],
                reference.file.read(),
                reference.content_type,
                request.headers["User-Agent"],
            )
        )
        return await picture(request)

    async with serve(worker) as url:
        maker = ImageMaker(url)
        try:
            assert await maker.draw("a doodle", PNG) == JPEG
        finally:
            await maker.close()

    assert seen == [("a doodle", PNG, "image/png", USER_AGENT)]


@pytest.mark.parametrize(
    ("status", "reason"),
    [(400, "Missing prompt"), (502, "Image generation failed: boom")],
)
async def test_a_refusal_is_a_provider_error_with_the_workers_reason(
    status: int, reason: str
) -> None:
    async def worker(request: web.Request) -> web.Response:
        return web.Response(status=status, text=reason)

    async with serve(worker) as url:
        maker = ImageMaker(url)
        try:
            with pytest.raises(ProviderError, match=f"HTTP {status} {reason}"):
                await maker.draw("a doodle", PNG)
        finally:
            await maker.close()


async def test_an_answer_that_is_not_a_picture_is_refused() -> None:
    async def worker(request: web.Request) -> web.Response:
        return web.Response(text="hello", content_type="text/plain")

    async with serve(worker) as url:
        maker = ImageMaker(url)
        try:
            with pytest.raises(ProviderError, match="text/plain, not a picture"):
                await maker.draw("a doodle", PNG)
        finally:
            await maker.close()


@pytest.mark.parametrize(
    "body", [b"", b"x" * (IMAGE_MAX_BYTES + 1)], ids=["empty", "huge"]
)
async def test_an_empty_or_huge_picture_is_refused(body: bytes) -> None:
    async def worker(request: web.Request) -> web.Response:
        return web.Response(body=body, content_type="image/jpeg")

    async with serve(worker) as url:
        maker = ImageMaker(url)
        try:
            with pytest.raises(ProviderError, match="empty|too big"):
                await maker.draw("a doodle", PNG)
        finally:
            await maker.close()


async def test_a_slow_worker_times_out() -> None:
    async def worker(request: web.Request) -> web.Response:
        await asyncio.sleep(2)
        return await picture(request)

    async with serve(worker) as url:
        maker = ImageMaker(url, timeout=timedelta(seconds=0.2))
        try:
            with pytest.raises(ProviderError, match="timed out"):
                await maker.draw("a doodle", PNG)
        finally:
            await maker.close()


async def test_a_worker_that_cannot_be_reached_is_a_provider_error() -> None:
    maker = ImageMaker("http://127.0.0.1:1/")
    try:
        with pytest.raises(ProviderError, match="ClientConnectorError"):
            await maker.draw("a doodle", PNG)
    finally:
        await maker.close()


async def test_without_a_worker_address_it_asks_nothing() -> None:
    with pytest.raises(ProviderError, match="no image worker"):
        await ImageMaker(None).draw("a doodle", PNG)


@pytest.mark.parametrize(("url", "configured"), [(None, False), ("worker", True)])
def test_it_is_configured_only_with_a_worker_address(
    url: str | None, configured: bool
) -> None:
    assert ImageMaker(url).configured is configured


@pytest.mark.filterwarnings(
    "error::ResourceWarning", "error::pytest.PytestUnraisableExceptionWarning"
)
async def test_a_closed_maker_opens_no_new_session() -> None:
    requests = 0

    async def worker(request: web.Request) -> web.Response:
        nonlocal requests
        requests += 1
        return await picture(request)

    async with serve(worker) as url:
        maker = ImageMaker(url)
        assert await maker.draw("a doodle", PNG) == JPEG
        await maker.close()
        await maker.close()

        with pytest.raises(ProviderError, match="closed"):
            await maker.draw("a doodle", PNG)
        gc.collect()

    assert requests == 1


def test_the_time_limit_is_a_minute() -> None:
    assert IMAGE_TIMEOUT == timedelta(seconds=60)


def test_the_maker_is_built_from_the_environment() -> None:
    assert isinstance(images_from_config(), ImageMaker)
