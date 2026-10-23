import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

import config
from ai import chain
from ai.chain import (
    AIChain,
    AllProvidersFailed,
    ChatProvider,
    GeminiProvider,
    Prompt,
    Provider,
)

PROMPT = Prompt("Be Wisp.", "Say hi.")
KEY = "secret-test-key"

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]

# ---
# Fake servers
# ---


@asynccontextmanager
async def serve(
    gemini: Handler | None = None, chat: Handler | None = None
) -> AsyncIterator[str]:
    """Run a local fake of the Gemini and chat endpoints; yield its base URL."""
    app = web.Application()
    if gemini is not None:
        app.router.add_post("/models/{model}:generateContent", gemini)
    if chat is not None:
        app.router.add_post("/chat/completions", chat)
    server = TestServer(app)
    await server.start_server()
    try:
        yield str(server.make_url("")).rstrip("/")
    finally:
        await server.close()


def gemini_reply(*parts: dict[str, Any]) -> web.Response:
    return web.json_response({"candidates": [{"content": {"parts": list(parts)}}]})


def chat_reply(content: str) -> web.Response:
    return web.json_response({"choices": [{"message": {"content": content}}]})


async def ask(provider: Provider) -> str:
    chain_of_one = AIChain([provider])
    try:
        return await chain_of_one.complete(PROMPT)
    finally:
        await chain_of_one.close()


# ---
# Gemini
# ---


async def test_gemini_text_joins_parts_and_skips_thoughts() -> None:
    async def handler(request: web.Request) -> web.Response:
        return gemini_reply(
            {"text": "pondering", "thought": True},
            {"text": "Hello, "},
            {"text": "friend."},
        )

    async with serve(gemini=handler) as url:
        assert await ask(GeminiProvider("m", KEY, url)) == "Hello, friend."


async def test_gemini_sends_the_key_as_a_header_not_in_the_url() -> None:
    seen: list[web.Request] = []
    bodies: list[dict[str, Any]] = []

    async def handler(request: web.Request) -> web.Response:
        seen.append(request)
        bodies.append(await request.json())
        return gemini_reply({"text": "ok"})

    async with serve(gemini=handler) as url:
        await ask(GeminiProvider("gem-model", KEY, url))

    request = seen[0]
    assert request.headers["x-goog-api-key"] == KEY
    assert KEY not in str(request.url)
    assert request.match_info["model"] == "gem-model"
    assert bodies[0] == {
        "systemInstruction": {"parts": [{"text": "Be Wisp."}]},
        "contents": [{"role": "user", "parts": [{"text": "Say hi."}]}],
        "generationConfig": {"maxOutputTokens": 1024},
    }


def test_gemini_name_includes_the_model() -> None:
    assert GeminiProvider("flash-x", KEY).name == "gemini flash-x"


# ---
# Chat providers
# ---


async def test_chat_provider_reads_the_first_choice() -> None:
    seen: list[web.Request] = []
    bodies: list[dict[str, Any]] = []

    async def handler(request: web.Request) -> web.Response:
        seen.append(request)
        bodies.append(await request.json())
        return web.json_response(
            {
                "choices": [
                    {"message": {"content": "first"}},
                    {"message": {"content": "second"}},
                ]
            }
        )

    async with serve(chat=handler) as url:
        provider = ChatProvider("groq", f"{url}/chat/completions", "big", KEY)
        assert await ask(provider) == "first"

    assert seen[0].headers["Authorization"] == f"Bearer {KEY}"
    assert bodies[0] == {
        "model": "big",
        "messages": [
            {"role": "system", "content": "Be Wisp."},
            {"role": "user", "content": "Say hi."},
        ],
        "max_tokens": 1024,
    }


async def test_every_request_sends_a_user_agent() -> None:
    agents: list[str | None] = []

    async def gemini(request: web.Request) -> web.Response:
        agents.append(request.headers.get("User-Agent"))
        return gemini_reply({"text": "ok"})

    async def chat(request: web.Request) -> web.Response:
        agents.append(request.headers.get("User-Agent"))
        return chat_reply("ok")

    async with serve(gemini=gemini, chat=chat) as url:
        await ask(GeminiProvider("m", KEY, url))
        await ask(ChatProvider("groq", f"{url}/chat/completions", "big", KEY))

    assert agents == ["WispBot/1.0", "WispBot/1.0"]


# ---
# Falling through
# ---


async def test_chain_falls_through_to_the_next_provider_on_http_500() -> None:
    async def broken(request: web.Request) -> web.Response:
        return web.Response(status=500, text="boom")

    async def working(request: web.Request) -> web.Response:
        return chat_reply("from the second")

    async with serve(gemini=broken, chat=working) as url:
        ai = AIChain(
            [
                GeminiProvider("m", KEY, url),
                ChatProvider("groq", f"{url}/chat/completions", "big", KEY),
            ]
        )
        try:
            assert await ai.complete(PROMPT) == "from the second"
        finally:
            await ai.close()


async def test_chain_falls_through_on_bad_json_and_empty_text() -> None:
    async def not_json(request: web.Request) -> web.Response:
        return web.Response(text="<html>nope</html>")

    async def wrong_shape(request: web.Request) -> web.Response:
        return web.json_response({"candidates": []})

    async def empty(request: web.Request) -> web.Response:
        return gemini_reply({"text": "  "}, {"text": "hidden", "thought": True})

    async def working(request: web.Request) -> web.Response:
        return chat_reply("finally")

    async with (
        serve(gemini=not_json, chat=working) as url,
        serve(gemini=wrong_shape) as shape_url,
        serve(gemini=empty) as empty_url,
    ):
        ai = AIChain(
            [
                GeminiProvider("a", KEY, url),
                GeminiProvider("b", KEY, shape_url),
                GeminiProvider("c", KEY, empty_url),
                ChatProvider("groq", f"{url}/chat/completions", "big", KEY),
            ]
        )
        try:
            assert await ai.complete(PROMPT) == "finally"
        finally:
            await ai.close()


async def test_chain_falls_through_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chain, "AI_TIMEOUT", timedelta(milliseconds=100))

    async def slow(request: web.Request) -> web.Response:
        await asyncio.sleep(5)
        return gemini_reply({"text": "too late"})

    async def working(request: web.Request) -> web.Response:
        return chat_reply("on time")

    async with serve(gemini=slow, chat=working) as url:
        ai = AIChain(
            [
                GeminiProvider("m", KEY, url),
                ChatProvider("groq", f"{url}/chat/completions", "big", KEY),
            ]
        )
        try:
            assert await ai.complete(PROMPT) == "on time"
        finally:
            await ai.close()


async def test_connection_refused_falls_through() -> None:
    async def working(request: web.Request) -> web.Response:
        return chat_reply("still here")

    async with serve(chat=working) as url:
        async with serve() as dead_url:
            pass
        ai = AIChain(
            [
                ChatProvider("dead", f"{dead_url}/chat/completions", "big", KEY),
                ChatProvider("live", f"{url}/chat/completions", "big", KEY),
            ]
        )
        try:
            assert await ai.complete(PROMPT) == "still here"
        finally:
            await ai.close()


# ---
# Failure
# ---


async def test_all_providers_failing_raises_with_every_reason() -> None:
    async def broken(request: web.Request) -> web.Response:
        return web.Response(status=503, text="overloaded " + "x" * 400)

    async def empty(request: web.Request) -> web.Response:
        return chat_reply("")

    async with serve(gemini=broken, chat=empty) as url:
        ai = AIChain(
            [
                GeminiProvider("m", KEY, url),
                ChatProvider("groq", f"{url}/chat/completions", "big", KEY),
            ]
        )
        try:
            with pytest.raises(AllProvidersFailed) as raised:
                await ai.complete(PROMPT)
        finally:
            await ai.close()

    failures = raised.value.failures
    assert [name for name, _ in failures] == ["gemini m", "groq"]
    status_reason = failures[0][1]
    assert status_reason.startswith("HTTP 503 overloaded")
    assert len(status_reason) == len("HTTP 503 ") + 200
    assert "empty" in failures[1][1]
    text = str(raised.value)
    assert "gemini m" in text and "groq" in text and status_reason in text
    assert KEY not in text


async def test_empty_chain_raises() -> None:
    ai = AIChain([])
    with pytest.raises(AllProvidersFailed) as raised:
        await ai.complete(PROMPT)
    assert raised.value.failures == []
    assert "no AI providers" in str(raised.value)
    await ai.close()


async def test_close_without_a_request_is_safe_and_repeatable() -> None:
    ai = AIChain([])
    await ai.close()
    await ai.close()


# ---
# Configuration
# ---


def test_chain_from_config_skips_providers_without_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "GOOGLE_API_KEY",
        "GOOGLE_CHAT_MODEL",
        "GOOGLE_FALLBACK_MODEL",
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
    ):
        monkeypatch.setattr(config, name, None)
    monkeypatch.setattr(config, "GROQ_API_KEY", KEY)
    monkeypatch.setattr(config, "GROQ_MODEL", "big")

    assert [p.name for p in chain.chain_from_config().providers] == ["groq"]


def test_chain_from_config_orders_every_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "GOOGLE_API_KEY": KEY,
        "GOOGLE_CHAT_MODEL": "primary",
        "GOOGLE_FALLBACK_MODEL": "backup",
        "GROQ_API_KEY": KEY,
        "GROQ_MODEL": "big",
        "OPENROUTER_API_KEY": KEY,
        "OPENROUTER_MODEL": "free",
    }
    for name, value in values.items():
        monkeypatch.setattr(config, name, value)

    names = [p.name for p in chain.chain_from_config().providers]
    assert names == ["gemini primary", "gemini backup", "groq", "openrouter"]


def test_chain_from_config_needs_a_model_as_well_as_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "GOOGLE_API_KEY", KEY)
    monkeypatch.setattr(config, "GOOGLE_CHAT_MODEL", "primary")
    monkeypatch.setattr(config, "GOOGLE_FALLBACK_MODEL", None)
    for name in ("GROQ_API_KEY", "GROQ_MODEL", "OPENROUTER_API_KEY"):
        monkeypatch.setattr(config, name, None)
    monkeypatch.setattr(config, "OPENROUTER_MODEL", "free")

    names = [p.name for p in chain.chain_from_config().providers]
    assert names == ["gemini primary"]
