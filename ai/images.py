"""Wisp's pencils: the Cloudflare worker that draws the pictures he gives."""

from datetime import timedelta

import aiohttp

import config
from ai.chain import ERROR_BODY_CHARS, USER_AGENT, ProviderError
from ai.session import SessionOwner
from wisp.rules import IMAGE_MAX_BYTES, IMAGE_TIMEOUT

__all__ = ["ImageMaker", "images_from_config"]

PICTURE_TYPE = "image/jpeg"


class ImageMaker(SessionOwner):
    """Asks the image worker for a picture of a prompt.

    Every way it can fail is a ProviderError. Without an address it asks
    nothing. Once closed, it opens no other HTTP session.
    """

    def __init__(self, url: str | None, timeout: timedelta = IMAGE_TIMEOUT) -> None:
        super().__init__(timeout)
        self._url = url

    async def draw(self, prompt: str) -> bytes:
        """Return the worker's JPEG for `prompt`.

        Raises:
            ProviderError: It has no address or is closed, the worker refused
                or did not answer within the time limit, or its answer is not
                a picture under IMAGE_MAX_BYTES.
        """
        if self._url is None:
            raise ProviderError("no image worker address")
        if self._closed:
            raise ProviderError("closed for shutdown")
        session = self._open_session()
        try:
            async with session.post(
                self._url, headers={"User-Agent": USER_AGENT}, json={"prompt": prompt}
            ) as response:
                if response.status != 200:
                    reason = (await response.text())[:ERROR_BODY_CHARS]
                    raise ProviderError(f"HTTP {response.status} {reason}")
                if response.content_type != PICTURE_TYPE:
                    raise ProviderError(
                        f"worker sent {response.content_type}, not a picture"
                    )
                if (response.content_length or 0) > IMAGE_MAX_BYTES:
                    raise ProviderError("picture is too big")
                picture = await response.read()
        except aiohttp.ClientError as error:
            raise ProviderError(f"{type(error).__name__}") from error
        except TimeoutError as error:
            raise ProviderError("timed out") from error
        if not picture:
            raise ProviderError("empty picture")
        if len(picture) > IMAGE_MAX_BYTES:
            raise ProviderError("picture is too big")
        return picture


def images_from_config() -> ImageMaker:
    """Build the image maker from the environment's worker address."""
    return ImageMaker(config.CF_IMAGE_WORKER_URL)
