"""Sign Wisp in to his own Suno account, once, and store the grant.

Run from the repo, on a PC with a browser, signed in to suno.com as Wisp (not
as Myra)::

    .venv/Scripts/python tools/suno_login.py

It registers Wisp as an OAuth client with Suno, opens Suno's sign-in page,
waits for the approval to come back to a local address, stores the tokens in
the database (`suno_auth`), then checks them by listing the Suno tools. That
check spends no credits. Running it again replaces the stored grant.
"""

import asyncio
import base64
import hashlib
import json
import secrets
import sys
import webbrowser
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlencode

import aiohttp
from aiohttp import web

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from db.database import Database  # noqa: E402
from db.schema import create_tables  # noqa: E402
from db.suno import SunoGrant, SunoRepo  # noqa: E402

RESOURCE: Final = "https://api.suno.com"
MCP_URL: Final = f"{RESOURCE}/mcp"
OAUTH: Final = "https://studio-api-prod.suno.com/api/v2/external/oauth"
SCOPES: Final = (
    "api:v0 credits:spend library:read library:write download profile:read "
    "offline_access"
)
PORT: Final = 53682
REDIRECT: Final = f"http://127.0.0.1:{PORT}/callback"
USER_AGENT: Final = "Wisp-Discord-Bot"
SIGN_IN_WAIT: Final = 600
TIMEOUT: Final = aiohttp.ClientTimeout(total=30)


class SunoSignInError(Exception):
    """Suno refused a step of the sign-in; the message says which."""


# ---
# OAuth
# ---


async def _json(response: aiohttp.ClientResponse, step: str) -> dict[str, Any]:
    """The JSON body of `response`, or SunoSignInError naming `step`."""
    body = await response.text()
    if response.status >= 400:
        raise SunoSignInError(f"{step}: HTTP {response.status}: {body[:300]}")
    answer: dict[str, Any] = json.loads(body)
    return answer


async def register(session: aiohttp.ClientSession) -> str:
    """Register Wisp as a public OAuth client and return its client id."""
    async with session.post(
        f"{OAUTH}/register/",
        json={
            "client_name": "Wisp",
            "redirect_uris": [REDIRECT],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    ) as response:
        client_id: str = (await _json(response, "registering Wisp"))["client_id"]
    return client_id


def pkce_pair() -> tuple[str, str]:
    """A PKCE verifier and its S256 challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


async def wait_for_code(state: str) -> str:
    """Serve the redirect address until Suno sends the approval, then its code."""
    arrived: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    async def callback(request: web.Request) -> web.Response:
        if request.query.get("state") != state:
            return web.Response(text="This sign-in link is not Wisp's.", status=400)
        if "error" in request.query:
            if not arrived.done():
                arrived.set_exception(
                    SunoSignInError(f"Suno said: {request.query['error']}")
                )
            return web.Response(text="Suno refused. You can close this tab.")
        if not arrived.done():
            arrived.set_result(request.query["code"])
        return web.Response(text="Wisp is signed in to Suno. You can close this tab.")

    app = web.Application()
    app.router.add_get("/callback", callback)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", PORT).start()
    try:
        return await asyncio.wait_for(arrived, SIGN_IN_WAIT)
    finally:
        await runner.cleanup()


async def exchange(
    session: aiohttp.ClientSession, client_id: str, code: str, verifier: str
) -> SunoGrant:
    """Trade the approval `code` for Wisp's tokens."""
    async with session.post(
        f"{OAUTH}/token/",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT,
            "client_id": client_id,
            "code_verifier": verifier,
            "resource": RESOURCE,
        },
    ) as response:
        tokens = await _json(response, "getting the tokens")
    if not tokens.get("refresh_token"):
        raise SunoSignInError("Suno gave no refresh token, so Wisp would sign out")
    return SunoGrant(
        client_id=client_id,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        expires_at=datetime.now(UTC) + timedelta(seconds=int(tokens["expires_in"])),
        scope=tokens.get("scope", SCOPES),
    )


# ---
# Check
# ---


async def _rpc(
    session: aiohttp.ClientSession,
    token: str,
    message: dict[str, Any],
    mcp_session: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Send one MCP message; return its answer (None for a notification) and
    the MCP session id Suno uses."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
    }
    if mcp_session is not None:
        headers["Mcp-Session-Id"] = mcp_session
    async with session.post(MCP_URL, json=message, headers=headers) as response:
        body = await response.text()
        if response.status >= 400:
            raise SunoSignInError(
                f"checking the sign-in: HTTP {response.status}: {body[:300]}"
            )
        mcp_session = response.headers.get("Mcp-Session-Id", mcp_session)
        if "id" not in message:
            return None, mcp_session
        if response.content_type == "text/event-stream":
            events = [
                line[5:].strip()
                for line in body.splitlines()
                if line.startswith("data:") and line[5:].strip().startswith("{")
            ]
            if not events:
                raise SunoSignInError(f"checking the sign-in: no answer: {body[:300]}")
            body = events[-1]
    answer: dict[str, Any] = json.loads(body)
    return answer, mcp_session


async def tool_names(session: aiohttp.ClientSession, token: str) -> list[str]:
    """The names of the tools Suno's MCP offers Wisp; this spends no credits."""
    _, mcp_session = await _rpc(
        session,
        token,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "Wisp", "version": "1.0"},
            },
        },
        None,
    )
    await _rpc(
        session,
        token,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        mcp_session,
    )
    listed, _ = await _rpc(
        session,
        token,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        mcp_session,
    )
    if listed is None or "result" not in listed:
        raise SunoSignInError(f"checking the sign-in: {json.dumps(listed)[:300]}")
    return [tool["name"] for tool in listed["result"]["tools"]]


# ---
# Run
# ---


async def main() -> None:
    """Sign Wisp in, store the grant and show which Suno tools he can use."""
    db = Database(config.TABLE_PREFIX)
    await db.connect()
    try:
        await create_tables(db)
        async with aiohttp.ClientSession(
            headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
        ) as session:
            client_id = await register(session)
            verifier, challenge = pkce_pair()
            state = secrets.token_urlsafe(24)
            link = f"{OAUTH}/authorize/?" + urlencode(
                {
                    "response_type": "code",
                    "client_id": client_id,
                    "redirect_uri": REDIRECT,
                    "scope": SCOPES,
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "resource": RESOURCE,
                }
            )
            print("Sign in to Suno as Wisp in the browser tab that opens.")
            print(f"If no tab opens, paste this link into the browser:\n{link}")
            webbrowser.open(link)
            code = await wait_for_code(state)
            grant = await exchange(session, client_id, code, verifier)
            await SunoRepo(db).save(grant, datetime.now(UTC))
            print("Saved Wisp's Suno sign-in.")
            names = await tool_names(session, grant.access_token)
            print("Suno tools Wisp can use:", ", ".join(names))
    finally:
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (
        SunoSignInError,
        aiohttp.ClientError,
        TimeoutError,
        json.JSONDecodeError,
        KeyError,
    ) as error:
        print(f"Error in Suno sign-in: {type(error).__name__}: {error}")
        sys.exit(1)
