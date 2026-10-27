"""Tests for resolving viibrmusic.com share links, against local HTTP servers."""

import asyncio
import gc
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import timedelta

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from cogs.share_links import ShareLinkResolver, artist_on_page
from wisp.links import ShareLink, Track, TrackKind

SONG = "bcd66fde-26f8-475a-b2f0-2e648f1204fb"
OTHER_SONG = "a75630de-1111-4222-8333-444455556666"
APEX = "https://viibrmusic.com"
WWW = "https://www.viibrmusic.com"
SLOW_SECONDS = 2.0

# ---
# Local viibrmusic.com
# ---


@dataclass
class Site:
    """A stand-in for one viibrmusic.com host that records what it was asked."""

    redirects: dict[str, tuple[int, str]]
    slow: frozenset[str] = frozenset()
    ok: frozenset[str] = frozenset()
    requests: list[tuple[str, str]] = field(default_factory=list)

    async def handle(self, request: web.Request) -> web.StreamResponse:
        code = request.match_info["code"]
        self.requests.append((request.path, request.headers.get("User-Agent", "")))
        if code in self.slow:
            await asyncio.sleep(SLOW_SECONDS)
        if code in self.ok:
            return web.Response(text="a page")
        if code not in self.redirects:
            return web.Response(status=404)
        status, location = self.redirects[code]
        return web.Response(status=status, headers={"Location": location})


@dataclass
class Sites:
    apex: Site
    www: Site
    resolver: ShareLinkResolver


async def serve(site: Site) -> TestServer:
    app = web.Application()
    app.router.add_get("/s/{code}", site.handle)
    server = TestServer(app)
    await server.start_server()
    return server


@pytest.fixture
async def sites() -> AsyncIterator[Sites]:
    apex = Site(
        redirects={
            "bDBmywB5": (307, f"{APEX}/songs/{SONG}"),
            "HPmPDag9": (307, f"{APEX}/songs/{OTHER_SONG}"),
            "relative": (307, f"/songs/{SONG}"),
            "UPPER123": (307, f"{APEX}/songs/{SONG.upper()}"),
            "creator1": (307, f"{APEX}/creators/someone"),
            "elsewher": (307, f"https://evil.example/songs/{SONG}"),
            "loopcode": (308, f"{APEX}/s/loopcode"),
            "noplace1": (307, ""),
            "badloc12": (307, "http://[bad/songs/x"),
        },
        slow=frozenset({"slowslow"}),
        ok=frozenset({"pagepage"}),
    )
    www = Site(
        redirects={
            "HPmPDag9": (308, f"{APEX}/s/HPmPDag9"),
            "wwwtwice": (308, f"{WWW}/s/wwwtwice"),
            "swapcode": (308, f"{APEX}/s/bDBmywB5"),
        }
    )
    apex_server = await serve(apex)
    www_server = await serve(www)
    resolver = ShareLinkResolver(
        origins={
            "viibrmusic.com": str(apex_server.make_url("/")),
            "www.viibrmusic.com": str(www_server.make_url("/")),
        },
        timeout=timedelta(seconds=0.5),
    )
    try:
        yield Sites(apex, www, resolver)
    finally:
        await resolver.close()
        await apex_server.close()
        await www_server.close()


def link(code: str, origin: str = APEX) -> ShareLink:
    return ShareLink(code, f"{origin}/s/{code}")


def song(code: str, uuid: str, origin: str = APEX) -> Track:
    return Track(TrackKind.VIIBR, f"viibr:{uuid}", f"{origin}/s/{code}")


# ---
# Resolving
# ---


async def test_a_share_link_resolves_to_its_song_in_one_request(
    sites: Sites,
) -> None:
    track = await sites.resolver.resolve(link("bDBmywB5"))

    assert track == song("bDBmywB5", SONG)
    assert sites.apex.requests == [("/s/bDBmywB5", "WispBot/1.0")]


async def test_a_www_share_link_follows_one_hop_to_the_bare_domain(
    sites: Sites,
) -> None:
    track = await sites.resolver.resolve(link("HPmPDag9", WWW))

    assert track == song("HPmPDag9", OTHER_SONG, WWW)
    assert sites.www.requests == [("/s/HPmPDag9", "WispBot/1.0")]
    assert sites.apex.requests == [("/s/HPmPDag9", "WispBot/1.0")]


async def test_a_relative_song_location_resolves(sites: Sites) -> None:
    assert await sites.resolver.resolve(link("relative")) == song("relative", SONG)


async def test_the_songs_uuid_is_lowercased_in_the_key(sites: Sites) -> None:
    assert await sites.resolver.resolve(link("UPPER123")) == song("UPPER123", SONG)


@pytest.mark.parametrize(
    "code,origin",
    [
        ("zzzzzzzz", APEX),
        ("creator1", APEX),
        ("elsewher", APEX),
        ("pagepage", APEX),
        ("loopcode", APEX),
        ("noplace1", APEX),
        ("badloc12", APEX),
        ("wwwtwice", WWW),
        ("swapcode", WWW),
    ],
)
async def test_a_link_that_names_no_song_resolves_to_none(
    sites: Sites, code: str, origin: str
) -> None:
    assert await sites.resolver.resolve(link(code, origin)) is None
    assert len(sites.apex.requests) + len(sites.www.requests) == 1


async def test_a_slow_site_times_out(sites: Sites) -> None:
    with pytest.raises(TimeoutError):
        await sites.resolver.resolve(link("slowslow"))


@pytest.fixture
async def closed_port() -> AsyncIterator[str]:
    server = await serve(Site(redirects={}))
    url = str(server.make_url("/"))
    await server.close()
    yield url


async def test_an_unreachable_site_raises_a_client_error(closed_port: str) -> None:
    resolver = ShareLinkResolver(origins={"viibrmusic.com": closed_port})
    try:
        with pytest.raises(aiohttp.ClientError):
            await resolver.resolve(link("bDBmywB5"))
    finally:
        await resolver.close()


async def test_closing_an_unused_resolver_is_safe() -> None:
    await ShareLinkResolver().close()


@pytest.mark.filterwarnings(
    "error::ResourceWarning", "error::pytest.PytestUnraisableExceptionWarning"
)
async def test_a_closed_resolver_opens_no_new_session(sites: Sites) -> None:
    await sites.resolver.resolve(link("bDBmywB5"))
    await sites.resolver.close()

    with pytest.raises(aiohttp.ClientConnectionError, match="closed"):
        await sites.resolver.resolve(link("relative"))
    gc.collect()

    assert sites.apex.requests == [("/s/bDBmywB5", "WispBot/1.0")]


# ---
# Artists
# ---

ARTIST_PAGE = (
    "<html><head>"
    '<script type="application/ld+json">{"@context":"https://schema.org",'
    '"@type":"MusicRecording","name":"Ablaze | The Altar",'
    '"byArtist":{"@type":"Person","name":"Foggy X Music"}}</script>'
    "</head></html>"
)


@dataclass
class SongPages:
    """viibrmusic.com's song pages, served locally, and what was asked of them."""

    pages: dict[str, tuple[int, str]]
    requests: list[str] = field(default_factory=list)

    async def handle(self, request: web.Request) -> web.Response:
        uuid = request.match_info["uuid"]
        self.requests.append(request.path)
        status, text = self.pages.get(uuid, (404, "not here"))
        return web.Response(status=status, text=text, content_type="text/html")


@pytest.fixture
async def song_pages() -> AsyncIterator[tuple[SongPages, ShareLinkResolver]]:
    pages = SongPages(
        {
            SONG: (200, ARTIST_PAGE),
            OTHER_SONG: (200, "<html>no data</html>"),
        }
    )
    application = web.Application()
    application.router.add_get("/songs/{uuid}", pages.handle)
    server = TestServer(application)
    await server.start_server()
    resolver = ShareLinkResolver(origins={"viibrmusic.com": str(server.make_url("/"))})
    try:
        yield pages, resolver
    finally:
        await resolver.close()
        await server.close()


async def test_a_songs_artist_is_read_from_its_page(
    song_pages: tuple[SongPages, ShareLinkResolver],
) -> None:
    pages, resolver = song_pages

    assert await resolver.artist(f"viibr:{SONG}") == "Foggy X Music"
    assert pages.requests == [f"/songs/{SONG}"]


async def test_a_page_without_an_artist_or_a_missing_page_names_none(
    song_pages: tuple[SongPages, ShareLinkResolver],
) -> None:
    pages, resolver = song_pages

    assert await resolver.artist(f"viibr:{OTHER_SONG}") is None
    assert await resolver.artist("viibr:00000000-0000-0000-0000-000000000000") is None
    assert len(pages.requests) == 2


@pytest.mark.parametrize("key", [f"suno:{SONG}", "viibr:bDBmywB5", "viibr:", ""])
async def test_a_key_that_is_not_a_viibr_song_asks_nothing(
    song_pages: tuple[SongPages, ShareLinkResolver], key: str
) -> None:
    pages, resolver = song_pages

    assert await resolver.artist(key) is None
    assert pages.requests == []


async def test_an_unreachable_site_raises_for_an_artist(closed_port: str) -> None:
    resolver = ShareLinkResolver(origins={"viibrmusic.com": closed_port})
    try:
        with pytest.raises(aiohttp.ClientError):
            await resolver.artist(f"viibr:{SONG}")
    finally:
        await resolver.close()


@pytest.mark.parametrize(
    ("page", "artist"),
    [
        (ARTIST_PAGE, "Foggy X Music"),
        (
            '<script type="application/ld+json">{"byArtist":{"name":"  A  "}}</script>',
            "A",
        ),
        ('<script type="application/ld+json">not json</script>', None),
        ('<script type="application/ld+json">["a list"]</script>', None),
        ('<script type="application/ld+json">{"byArtist":"just text"}</script>', None),
        ('<script type="application/ld+json">{"byArtist":{"name":" "}}</script>', None),
        (
            '<script type="application/ld+json">{"@type":"WebSite"}</script>'
            '<script type="application/ld+json">{"byArtist":{"name":"B"}}</script>',
            "B",
        ),
        ("<html></html>", None),
    ],
)
def test_artist_on_page_reads_the_schema_org_artist(
    page: str, artist: str | None
) -> None:
    assert artist_on_page(page) == artist
