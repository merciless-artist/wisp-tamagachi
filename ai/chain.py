"""Wisp's AI provider chain: Gemini, a Gemini fallback, Groq, then OpenRouter."""

import logging
from collections.abc import Callable, Sequence
from typing import Any, Protocol

import aiohttp

import config
from ai.prompt import Prompt
from wisp.rules import AI_MAX_OUTPUT_TOKENS, AI_TIMEOUT

__all__ = [
    "AIChain",
    "AllProvidersFailed",
    "ChatProvider",
    "GeminiProvider",
    "Prompt",
    "Provider",
    "ProviderError",
    "chain_from_config",
]

log = logging.getLogger("wisp")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Groq sits behind Cloudflare, which refuses requests that have no User-Agent.
USER_AGENT = "WispBot/1.0"
ERROR_BODY_CHARS = 200

# ---
# Errors
# ---


class ProviderError(Exception):
    """One provider could not give an answer; the next one should be tried."""


class AllProvidersFailed(Exception):
    """Every provider in the chain failed, or the chain has none."""

    def __init__(self, failures: list[tuple[str, str]]) -> None:
        self.failures = failures
        if failures:
            detail = "; ".join(f"{name}: {reason}" for name, reason in failures)
        else:
            detail = "no AI providers are configured"
        super().__init__(detail)


# ---
# Providers
# ---


class Provider(Protocol):
    """Something that can turn a prompt into text."""

    name: str

    async def complete(self, session: aiohttp.ClientSession, prompt: Prompt) -> str:
        """Return the model's answer, or raise ProviderError."""
        ...


async def _post_for_text(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    extract: Callable[[Any], str],
) -> str:
    """POST a JSON body and pull the answer out of the reply.

    Every way this can go wrong is raised as a ProviderError. Keys travel in
    headers, never the URL, so a reason cannot leak one.
    """
    try:
        async with session.post(
            url, headers={**headers, "User-Agent": USER_AGENT}, json=body
        ) as response:
            if response.status != 200:
                text = await response.text()
                raise ProviderError(f"HTTP {response.status} {text[:ERROR_BODY_CHARS]}")
            data = await response.json(content_type=None)
    except aiohttp.ClientError as error:
        raise ProviderError(f"{type(error).__name__}: {error}") from error
    except TimeoutError as error:
        raise ProviderError("timed out") from error
    except ValueError as error:
        raise ProviderError(f"reply was not JSON: {error}") from error
    try:
        answer = extract(data).strip()
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as error:
        raise ProviderError(
            f"unexpected reply shape: {type(error).__name__}"
        ) from error
    if not answer:
        raise ProviderError("empty text")
    return answer


class GeminiProvider:
    """Google's Gemini ``generateContent`` API."""

    def __init__(self, model: str, api_key: str, base_url: str = GEMINI_URL) -> None:
        self.name = f"gemini {model}"
        self._url = f"{base_url}/models/{model}:generateContent"
        self._api_key = api_key

    async def complete(self, session: aiohttp.ClientSession, prompt: Prompt) -> str:
        """Ask Gemini; thought parts are left out of the answer."""
        body = {
            "systemInstruction": {"parts": [{"text": prompt.system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt.user}]}],
            "generationConfig": {"maxOutputTokens": AI_MAX_OUTPUT_TOKENS},
        }
        return await _post_for_text(
            session,
            self._url,
            {"x-goog-api-key": self._api_key},
            body,
            self._extract,
        )

    @staticmethod
    def _extract(data: Any) -> str:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(
            part["text"] for part in parts if "text" in part and not part.get("thought")
        )


class ChatProvider:
    """An OpenAI-style chat completions API, such as Groq or OpenRouter."""

    def __init__(self, name: str, url: str, model: str, api_key: str) -> None:
        self.name = name
        self._url = url
        self._model = model
        self._api_key = api_key

    async def complete(self, session: aiohttp.ClientSession, prompt: Prompt) -> str:
        """Ask the chat model for one reply."""
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            "max_tokens": AI_MAX_OUTPUT_TOKENS,
        }
        return await _post_for_text(
            session,
            self._url,
            {"Authorization": f"Bearer {self._api_key}"},
            body,
            self._extract,
        )

    @staticmethod
    def _extract(data: Any) -> str:
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("content is not text")
        return content


# ---
# Chain
# ---


class AIChain:
    """Tries each provider in turn and returns the first answer."""

    def __init__(self, providers: Sequence[Provider]) -> None:
        self.providers = tuple(providers)
        self._session: aiohttp.ClientSession | None = None

    async def complete(self, prompt: Prompt) -> str:
        """Return the first provider's answer; raise AllProvidersFailed if none."""
        session = self._open_session()
        failures: list[tuple[str, str]] = []
        for provider in self.providers:
            try:
                return await provider.complete(session, prompt)
            except ProviderError as error:
                log.warning("AI provider %s failed: %s", provider.name, error)
                failures.append((provider.name, str(error)))
        raise AllProvidersFailed(failures)

    async def close(self) -> None:
        """Close the HTTP session, if one was opened."""
        session, self._session = self._session, None
        if session is not None:
            await session.close()

    def _open_session(self) -> aiohttp.ClientSession:
        """Return the shared session, opening it on first use.

        Its timeout applies to each request, so it is the limit for one provider.
        """
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=AI_TIMEOUT.total_seconds())
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session


def chain_from_config() -> AIChain:
    """Build the chain from the environment, skipping providers that lack settings."""
    providers: list[Provider] = []
    if config.GOOGLE_API_KEY:
        providers += [
            GeminiProvider(model, config.GOOGLE_API_KEY)
            for model in (config.GOOGLE_CHAT_MODEL, config.GOOGLE_FALLBACK_MODEL)
            if model
        ]
    if config.GROQ_API_KEY and config.GROQ_MODEL:
        providers.append(
            ChatProvider("groq", GROQ_URL, config.GROQ_MODEL, config.GROQ_API_KEY)
        )
    if config.OPENROUTER_API_KEY and config.OPENROUTER_MODEL:
        providers.append(
            ChatProvider(
                "openrouter",
                OPENROUTER_URL,
                config.OPENROUTER_MODEL,
                config.OPENROUTER_API_KEY,
            )
        )
    return AIChain(providers)
