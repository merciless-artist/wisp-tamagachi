"""Wisp's eyes: a Gemini vision model that describes the pictures members send."""

import asyncio
import base64

import aiohttp

import config
from ai.chain import (
    GEMINI_NO_THINKING,
    GEMINI_URL,
    USER_AGENT,
    GeminiProvider,
    ProviderError,
    post_for_text,
)
from wisp.rules import (
    AI_MAX_OUTPUT_TOKENS,
    AI_TIMEOUT,
    VISION_MAX_BYTES,
    VISION_MAX_CHARS,
    VISION_TYPES,
)

__all__ = ["Vision", "vision_from_config"]

DOWNLOAD_CHUNK_BYTES = 64 * 1024
QUESTION = "Describe this picture in one or two plain sentences."


class Vision:
    """Describes a picture found at a URL, in a sentence or two.

    Every way it can fail is a ProviderError. Without a key it asks nothing.
    Once closed, it opens no other HTTP session.
    """

    def __init__(
        self, model: str, api_key: str | None, base_url: str = GEMINI_URL
    ) -> None:
        self._url = f"{base_url}/models/{model}:generateContent"
        self._api_key = api_key
        self._session: aiohttp.ClientSession | None = None
        self._closed = False

    async def describe(self, picture_url: str) -> str:
        """Download the picture and return the model's description of it.

        Raises:
            ProviderError: it has no key, is closed, the picture is missing,
                not an allowed type or over VISION_MAX_BYTES, the model gave
                no answer, or the whole job took longer than AI_TIMEOUT.
        """
        if self._api_key is None:
            raise ProviderError("no Google key for the vision model")
        if self._closed:
            raise ProviderError("closed for shutdown")
        try:
            async with asyncio.timeout(AI_TIMEOUT.total_seconds()):
                return await self._describe(
                    self._open_session(), picture_url, self._api_key
                )
        except TimeoutError as error:
            raise ProviderError("timed out") from error

    async def _describe(
        self, session: aiohttp.ClientSession, picture_url: str, api_key: str
    ) -> str:
        """Download the picture and ask the model, with no limit of its own."""
        data, mime_type = await self._download(session, picture_url)
        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64.b64encode(data).decode("ascii"),
                            }
                        },
                        {"text": QUESTION},
                    ],
                }
            ],
            "generationConfig": {
                "maxOutputTokens": AI_MAX_OUTPUT_TOKENS,
                "thinkingConfig": dict(GEMINI_NO_THINKING),
            },
        }
        answer = await post_for_text(
            session,
            self._url,
            {"x-goog-api-key": api_key},
            body,
            GeminiProvider.extract,
        )
        return " ".join(answer.split())[:VISION_MAX_CHARS]

    async def close(self) -> None:
        """Close the HTTP session, if one was opened, and open no other."""
        self._closed = True
        session, self._session = self._session, None
        if session is not None:
            await session.close()

    @staticmethod
    async def _download(
        session: aiohttp.ClientSession, picture_url: str
    ) -> tuple[bytes, str]:
        """Fetch the picture, refusing a wrong type or more than VISION_MAX_BYTES.

        The URL is left out of every reason: Discord's carry signatures.
        """
        data = bytearray()
        try:
            async with session.get(
                picture_url, headers={"User-Agent": USER_AGENT}
            ) as response:
                if response.status != 200:
                    raise ProviderError(f"picture download HTTP {response.status}")
                mime_type = response.content_type
                if mime_type not in VISION_TYPES:
                    raise ProviderError(f"picture is {mime_type}, not an image")
                if (response.content_length or 0) > VISION_MAX_BYTES:
                    raise ProviderError("picture is too big")
                async for chunk in response.content.iter_chunked(DOWNLOAD_CHUNK_BYTES):
                    data += chunk
                    if len(data) > VISION_MAX_BYTES:
                        raise ProviderError("picture is too big")
        except aiohttp.ClientError as error:
            raise ProviderError(
                f"picture download failed: {type(error).__name__}"
            ) from error
        except TimeoutError as error:
            raise ProviderError("picture download timed out") from error
        return bytes(data), mime_type

    def _open_session(self) -> aiohttp.ClientSession:
        """Return the shared session, opening it on first use."""
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=AI_TIMEOUT.total_seconds())
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session


def vision_from_config() -> Vision:
    """Build the vision model from the environment's Google key and vision model."""
    return Vision(config.GOOGLE_VISION_MODEL, config.GOOGLE_API_KEY)
