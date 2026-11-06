import base64
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from ai.chain import ProviderError
from ai.vision import Vision
from wisp.rules import VISION_MAX_BYTES, VISION_MAX_CHARS

KEY = "secret-test-key"
GIF = b"GIF89a-not-really"
Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]

# ---
# Fake servers
# ---


@asynccontextmanager
async def serve(
    gemini: Handler,
    picture: Handler | None = None,
) -> AsyncIterator[str]:
    """Run a local fake of the Gemini endpoint and a picture host; yield its URL."""
    app = web.Application()
    app.router.add_post("/models/{model}:generateContent", gemini)
    if picture is not None:
        app.router.add_get("/pic", picture)
    server = TestServer(app)
    await server.start_server()
    try:
        yield str(server.make_url("")).rstrip("/")
    finally:
        await server.close()


async def gif_picture(request: web.Request) -> web.Response:
    return web.Response(body=GIF, content_type="image/gif")


def described(text: str) -> web.Response:
    return web.json_response({"candidates": [{"content": {"parts": [{"text": text}]}}]})


async def describe(url: str, vision_url: str | None = None) -> str:
    vision = Vision("vision-model", KEY, url)
    try:
        return await vision.describe(vision_url or f"{url}/pic")
    finally:
        await vision.close()


# ---
# Asking the model
# ---


async def test_the_picture_is_sent_inline_and_described() -> None:
    bodies: list[dict[str, Any]] = []
    requests: list[web.Request] = []

    async def gemini(request: web.Request) -> web.Response:
        requests.append(request)
        bodies.append(await request.json())
        return described("  A cat waving.  ")

    async with serve(gemini, gif_picture) as url:
        assert await describe(url) == "A cat waving."

    assert requests[0].headers["x-goog-api-key"] == KEY
    assert requests[0].match_info["model"] == "vision-model"
    assert KEY not in str(requests[0].url)
    (content,) = bodies[0]["contents"]
    picture, question = content["parts"]
    assert picture == {
        "inline_data": {
            "mime_type": "image/gif",
            "data": base64.b64encode(GIF).decode(),
        }
    }
    assert "text" in question
    assert bodies[0]["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}


async def test_a_long_description_is_cut_down() -> None:
    async def gemini(request: web.Request) -> web.Response:
        return described("word " * 500)

    async with serve(gemini, gif_picture) as url:
        assert len(await describe(url)) <= VISION_MAX_CHARS


async def test_the_model_failing_is_a_provider_error() -> None:
    async def gemini(request: web.Request) -> web.Response:
        return web.Response(status=503, text="overloaded")

    async with serve(gemini, gif_picture) as url:
        with pytest.raises(ProviderError, match="503"):
            await describe(url)


# ---
# Fetching the picture
# ---


async def test_a_picture_over_the_limit_is_refused_and_never_sent() -> None:
    asked: list[str] = []

    async def gemini(request: web.Request) -> web.Response:
        asked.append("asked")
        return described("never")

    async def huge(request: web.Request) -> web.Response:
        return web.Response(
            body=b"x" * (VISION_MAX_BYTES + 1), content_type="image/png"
        )

    async with serve(gemini, huge) as url:
        with pytest.raises(ProviderError, match="too big"):
            await describe(url)
    assert asked == []


async def test_a_picture_without_a_length_is_still_capped() -> None:
    async def gemini(request: web.Request) -> web.Response:
        return described("never")

    async def streamed(request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(headers={"Content-Type": "image/png"})
        await response.prepare(request)
        chunk = b"x" * 1024 * 1024
        for _ in range(VISION_MAX_BYTES // len(chunk) + 1):
            await response.write(chunk)
        return response

    async with serve(gemini, streamed) as url:
        with pytest.raises(ProviderError, match="too big"):
            await describe(url)


async def test_something_that_is_not_a_picture_is_refused() -> None:
    async def gemini(request: web.Request) -> web.Response:
        return described("never")

    async def page(request: web.Request) -> web.Response:
        return web.Response(text="<html>", content_type="text/html")

    async with serve(gemini, page) as url:
        with pytest.raises(ProviderError, match="text/html"):
            await describe(url)


async def test_a_failed_download_is_a_provider_error() -> None:
    async def gemini(request: web.Request) -> web.Response:
        return described("never")

    async def gone(request: web.Request) -> web.Response:
        return web.Response(status=404)

    async with serve(gemini, gone) as url:
        with pytest.raises(ProviderError, match="404"):
            await describe(url)


async def test_an_unreachable_host_is_a_provider_error() -> None:
    async def gemini(request: web.Request) -> web.Response:
        return described("never")

    async with serve(gemini) as url:
        with pytest.raises(ProviderError):
            await describe(url, "http://127.0.0.1:1/pic")


async def test_no_key_means_no_request() -> None:
    vision = Vision("vision-model", None)
    try:
        with pytest.raises(ProviderError, match="no Google key"):
            await vision.describe("http://127.0.0.1:1/pic")
    finally:
        await vision.close()


async def test_a_closed_vision_opens_no_session() -> None:
    vision = Vision("vision-model", KEY)
    await vision.close()
    with pytest.raises(ProviderError, match="closed"):
        await vision.describe("http://127.0.0.1:1/pic")
