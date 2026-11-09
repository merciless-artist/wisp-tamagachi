"""Wisp's sense of meaning: Gemini embeddings for searching what he remembers."""

from typing import Any, Final

import config
from ai.chain import GEMINI_URL, USER_AGENT, ProviderError, post_json
from ai.session import SessionOwner
from wisp.rules import MEMORY_EMBED_SIZE, MEMORY_EMBED_TIMEOUT

__all__ = ["Embedder", "embedder_from_config"]

# Gemini Embedding 2 is told what a text is for in the text itself.
_SEARCH_PREFIX: Final = "task: search result | query: "
_SAVED_PREFIX: Final = "title: none | text: "


class Embedder(SessionOwner):
    """Turns text into a list of numbers that stands for what it means.

    Every way it can fail is a ProviderError. Without a key it asks nothing.
    Once closed, it opens no other HTTP session.
    """

    def __init__(
        self, model: str, api_key: str | None, base_url: str = GEMINI_URL
    ) -> None:
        super().__init__(MEMORY_EMBED_TIMEOUT)
        self._url = f"{base_url}/models/{model}:embedContent"
        self._api_key = api_key

    async def for_search(self, text: str) -> list[float]:
        """The embedding of something to look up in his memory.

        Raises:
            ProviderError: it has no key, is closed or got no usable answer.
        """
        return await self._embed(f"{_SEARCH_PREFIX}{text}")

    async def for_saving(self, text: str) -> list[float]:
        """The embedding of something to save in his memory.

        Raises:
            ProviderError: it has no key, is closed or got no usable answer.
        """
        return await self._embed(f"{_SAVED_PREFIX}{text}")

    async def _embed(self, text: str) -> list[float]:
        if self._api_key is None:
            raise ProviderError("no Google key for the embedding model")
        if self._closed:
            raise ProviderError("closed for shutdown")
        reply = await post_json(
            self._open_session(),
            self._url,
            {"x-goog-api-key": self._api_key, "User-Agent": USER_AGENT},
            {
                "content": {"parts": [{"text": text}]},
                "output_dimensionality": MEMORY_EMBED_SIZE,
            },
        )
        return _values(reply)


def _values(reply: Any) -> list[float]:
    """The numbers in an embedding reply, checked for the size asked for."""
    try:
        values = [float(value) for value in reply["embedding"]["values"]]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ProviderError(
            f"unexpected reply shape: {type(error).__name__}"
        ) from error
    if len(values) != MEMORY_EMBED_SIZE:
        raise ProviderError(f"expected {MEMORY_EMBED_SIZE} numbers, got {len(values)}")
    return values


def embedder_from_config() -> Embedder:
    """Build the embedder from the environment's Google key and embedding model."""
    return Embedder(config.GOOGLE_EMBEDDING_MODEL, config.GOOGLE_API_KEY)
