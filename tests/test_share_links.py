"""Tests for resolving viibrmusic.com share links, against local HTTP servers."""

import asyncio
import gc
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import timedelta

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from cogs.share_links import ShareLinkResolver
from wisp.links import ShareLink, Track, TrackKind
from wisp.rules import SONG_TITLE_LIMIT

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
    pages: dict[str, tuple[int, str]] = field(default_factory=dict)
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

    async def song(self, request: web.Request) -> web.StreamResponse:
        uuid = request.match_info["uuid"]
        self.requests.append((request.path, request.headers.get("User-Agent", "")))
        if uuid in self.slow:
            await asyncio.sleep(SLOW_SECONDS)
        status, page = self.pages.get(uuid, (404, ""))
        return web.Response(status=status, text=page, content_type="text/html")


@dataclass
class Sites:
    apex: Site
    www: Site
    resolver: ShareLinkResolver


async def serve(site: Site) -> TestServer:
    app = web.Application()
    app.router.add_get("/s/{code}", site.handle)
    app.router.add_get("/songs/{uuid}", site.song)
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
# Song titles
# ---

LONG_SONG = "c0ffee00-0000-4000-8000-000000000001"
PLAIN_SONG = "c0ffee00-0000-4000-8000-000000000002"
BROKEN_SONG = "c0ffee00-0000-4000-8000-000000000003"
GRAPH_SONG = "c0ffee00-0000-4000-8000-000000000004"
FAILING_SONG = "c0ffee00-0000-4000-8000-000000000005"
SLOW_SONG = "c0ffee00-0000-4000-8000-000000000006"


def song_page(*blocks: object, title: str = "") -> str:
    """A song page like viibrmusic.com's: its og:title and JSON-LD blocks."""
    scripts = "".join(
        '<script type="application/ld+json">'
        f"{block if isinstance(block, str) else json.dumps(block)}</script>"
        for block in blocks
    )
    return (
        f'<html><head><meta property="og:title" content="{title}">{scripts}'
        "</head><body>a song</body></html>"
    )


def recording(name: object) -> dict[str, object]:
    return {"@context": "https://schema.org", "@type": "MusicRecording", "name": name}


@pytest.fixture
def pages(sites: Sites) -> Sites:
    """Song pages on the bare domain, the way viibrmusic.com writes them."""
    sites.apex.pages.update(
        {
            SONG: (
                200,
                song_page(
                    {"@type": "WebSite", "name": "ViiBR Music"},
                    recording("Time Goes by Foggy X"),
                    title="Time Goes by Foggy X by Foggy X · ViiBR Music",
                ),
            ),
            OTHER_SONG: (200, song_page(recording("  .if \n  again "))),
            LONG_SONG: (200, song_page(recording("x" * (SONG_TITLE_LIMIT + 50)))),
            PLAIN_SONG: (200, song_page(title="Only og by Someone · ViiBR Music")),
            BROKEN_SONG: (200, song_page("{not json", recording(7))),
            GRAPH_SONG: (
                200,
                song_page(
                    {"@graph": [{"@type": "Person"}, recording("In a graph")]},
                ),
            ),
            FAILING_SONG: (500, ""),
        }
    )
    sites.apex.slow = sites.apex.slow | {SLOW_SONG}
    return sites


async def test_a_song_page_gives_its_json_ld_name(pages: Sites) -> None:
    title = await pages.resolver.song_title(f"{APEX}/songs/{SONG}")

    assert title == "Time Goes by Foggy X"
    assert pages.apex.requests == [(f"/songs/{SONG}", "WispBot/1.0")]


async def test_a_www_song_link_is_read_on_the_bare_domain(pages: Sites) -> None:
    title = await pages.resolver.song_title(f"{WWW}/songs/{SONG.upper()}")

    assert title == "Time Goes by Foggy X"
    assert pages.www.requests == []


async def test_a_share_link_is_read_at_the_song_it_redirects_to(pages: Sites) -> None:
    title = await pages.resolver.song_title(f"{APEX}/s/HPmPDag9")

    assert title == ".if again"
    assert pages.apex.requests == [
        ("/s/HPmPDag9", "WispBot/1.0"),
        (f"/songs/{OTHER_SONG}", "WispBot/1.0"),
    ]


async def test_a_long_name_is_cut_to_what_is_stored(pages: Sites) -> None:
    title = await pages.resolver.song_title(f"{APEX}/songs/{LONG_SONG}")

    assert title == "x" * SONG_TITLE_LIMIT


async def test_a_name_inside_a_graph_is_found(pages: Sites) -> None:
    assert await pages.resolver.song_title(f"{APEX}/songs/{GRAPH_SONG}") == (
        "In a graph"
    )


@pytest.mark.parametrize(
    "url",
    [
        f"{APEX}/songs/{PLAIN_SONG}",
        f"{APEX}/songs/{BROKEN_SONG}",
        f"{APEX}/songs/a75630de-9999-4222-8333-444455556666",
        f"{APEX}/s/zzzzzzzz",
        f"{APEX}/s/creator1",
    ],
)
async def test_a_page_without_a_name_gives_an_empty_title(
    pages: Sites, url: str
) -> None:
    assert await pages.resolver.song_title(url) == ""


async def test_a_link_that_is_not_a_viibr_song_is_not_read(pages: Sites) -> None:
    title = await pages.resolver.song_title(f"https://suno.com/song/{SONG}")

    assert title == ""
    assert pages.apex.requests == []


@pytest.mark.parametrize("uuid", [FAILING_SONG, SLOW_SONG])
async def test_a_page_that_cannot_be_read_gives_no_title(
    pages: Sites, uuid: str
) -> None:
    assert await pages.resolver.song_title(f"{APEX}/songs/{uuid}") is None


async def test_a_slow_share_link_gives_no_title(pages: Sites) -> None:
    assert await pages.resolver.song_title(f"{APEX}/s/slowslow") is None


async def test_an_unreachable_site_gives_no_title(closed_port: str) -> None:
    resolver = ShareLinkResolver(origins={"viibrmusic.com": closed_port})
    try:
        assert await resolver.song_title(f"{APEX}/songs/{SONG}") is None
    finally:
        await resolver.close()
