"""Badges: Wisp's vanity roles, how the Vault offers them and taking them back.

Buying one happens in the Vault (see `cogs.snacks`). A badge is worn for one
Wisp's life; when that life ends its buyers lose the roles but keep the badge
in their Snack Pack.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

import discord
import pymysql

from cogs.assets import ASSETS_DIR
from db.badges import OwnedBadge
from wisp.bond import tier_for
from wisp.life import Life, is_over
from wisp.rules import BADGE_BY_KEY, BADGES, Badge
from wisp.text import count, with_emoji

if TYPE_CHECKING:
    from app import WispBot

BADGE_ART: Final = ASSETS_DIR / "badges"
_ROLE_ICONS: Final = "ROLE_ICONS"
_SET_UP: Final = "Wisp's badge for the ViiBR Vault"
_TAKING_BACK: Final = "taking back badge roles"
_NO_ICONS: Final = (
    "・Role icons are not available on this server (it needs more boosts), "
    "so the badges have no icons."
)
OWNED: Final = "owned"
COMING_SOON: Final = "coming soon"
BETWEEN_WISPS: Final = "with the next Wisp"

# ---
# Roles in the server
# ---


def _icon(badge: Badge) -> bytes | None:
    """The badge's role icon, when its art is on disk."""
    path: Path = BADGE_ART / f"{badge.key}.png"
    return path.read_bytes() if path.is_file() else None


@dataclass
class _RoleSetup:
    """What a setup did to the badge roles, for the setup reply."""

    icons_allowed: bool
    created: list[str] = field(default_factory=list)
    recreated: list[str] = field(default_factory=list)
    iconed: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        lines = [
            f"・Badge {what}: {', '.join(names)}"
            for what, names in (
                ("roles created", self.created),
                ("roles recreated", self.recreated),
                ("icons added", self.iconed),
            )
            if names
        ]
        if not lines:
            lines.append(f"・Badge roles: all {len(BADGES)} ready")
        if not self.icons_allowed:
            lines.append(_NO_ICONS)
        return lines


async def ensure_badge_roles(
    bot: "WispBot", guild: discord.Guild, where: discord.abc.Messageable | None
) -> list[str]:
    """Create each badge role that is missing and give icons to roles without one.

    Roles are found by their stored id, so a stored role that was deleted is
    created again. A role gets its icon when its art exists and the server can
    show role icons; one Discord turns the icon down is made without it, and
    the server is treated as having no role icons. Any other failure, such as a
    missing Manage Roles permission, is reported in `where`. Returns the lines
    for the setup reply.
    """
    setup = _RoleSetup(icons_allowed=_ROLE_ICONS in guild.features)
    stored = await bot.badges.role_ids(guild.id)
    for badge in BADGES:
        role_id = stored.get(badge.key)
        role = None if role_id is None else guild.get_role(role_id)
        try:
            if role is None:
                await _create_role(bot, guild, badge, setup)
                (setup.created if role_id is None else setup.recreated).append(
                    badge.name
                )
            elif await _add_icon(role, badge, setup):
                setup.iconed.append(badge.name)
        except discord.HTTPException as error:
            context = (
                f"creating the {badge.name} badge role"
                if role is None
                else f"adding the {badge.name} badge icon"
            )
            await bot.report_error(guild, context, error, where=where)
    return setup.lines()


async def _create_role(
    bot: "WispBot", guild: discord.Guild, badge: Badge, setup: _RoleSetup
) -> None:
    """Create a badge's role, with its icon when allowed, and remember it."""
    icon = _icon(badge) if setup.icons_allowed else None
    role: discord.Role | None = None
    if icon is not None:
        try:
            role = await guild.create_role(
                name=badge.name, display_icon=icon, reason=_SET_UP
            )
        except discord.Forbidden:
            raise
        except discord.HTTPException:
            setup.icons_allowed = False
    if role is None:
        role = await guild.create_role(name=badge.name, reason=_SET_UP)
    await bot.badges.set_role(guild.id, badge.key, role.id)


async def _add_icon(role: discord.Role, badge: Badge, setup: _RoleSetup) -> bool:
    """Give a role without an icon its badge art; whether it was given one."""
    if not setup.icons_allowed or role.display_icon is not None:
        return False
    icon = _icon(badge)
    if icon is None:
        return False
    try:
        await role.edit(display_icon=icon, reason=_SET_UP)
    except discord.Forbidden:
        raise
    except discord.HTTPException:
        setup.icons_allowed = False
        return False
    return True


async def badge_role(
    bot: "WispBot", guild: discord.Guild, badge: Badge
) -> discord.Role | None:
    """The badge's role in the server, or None when it is not set up or is gone."""
    role_id = (await bot.badges.role_ids(guild.id)).get(badge.key)
    return None if role_id is None else guild.get_role(role_id)


# ---
# The Vault
# ---


@dataclass(frozen=True)
class Offer:
    """A badge as the Vault offers it to one member.

    `reason` says why they cannot get it now, or is None when they can.
    """

    badge: Badge
    reason: str | None


async def badge_offers(
    bot: "WispBot", guild_id: int, user_id: int, bond: int
) -> list[Offer]:
    """Every badge, and whether the member, with `bond`, can get it now.

    A badge is owned once bought for the current life, waits for a role
    until setup has made one, and waits for a Wisp while there is none.
    """
    life = await bot.lives.current(guild_id)
    life_id = None if life is None or is_over(life) else life.id
    owned = (
        set() if life_id is None else await bot.badges.owned(guild_id, user_id, life_id)
    )
    guild = bot.get_guild(guild_id)
    roles = await bot.badges.role_ids(guild_id)
    tier = tier_for(bond)
    offers = []
    for badge in BADGES:
        role_id = roles.get(badge.key)
        reason: str | None = None
        if badge.key in owned:
            reason = OWNED
        elif badge.needs_tier is not None and tier != badge.needs_tier:
            reason = f"{badge.needs_tier}s only"
        elif role_id is None or guild is None or guild.get_role(role_id) is None:
            reason = COMING_SOON
        elif life_id is None:
            reason = BETWEEN_WISPS
        offers.append(Offer(badge, reason))
    return offers


def _named(bot: "WispBot", badge: Badge) -> str:
    return with_emoji(bot.emoji(badge.emoji_name), badge.name)


def badge_section(bot: "WispBot", offers: list[Offer]) -> list[str]:
    """The Vault's Badges lines: each badge's price and bond, and any reason."""
    lines = ["Badges"]
    for offer in offers:
        badge = offer.badge
        price = count(badge.cost, "point")
        line = f"・{_named(bot, badge)} ・ {price} ・ bond +{badge.bond}"
        lines.append(line if offer.reason is None else f"{line} ・ {offer.reason}")
    return lines


def badge_options(bot: "WispBot", offers: list[Offer]) -> list[discord.SelectOption]:
    """The badges the member can get now, as options for the Vault's select."""
    return [
        discord.SelectOption(
            label=offer.badge.name,
            value=offer.badge.key,
            description=(
                f"{count(offer.badge.cost, 'point')} ・ bond +{offer.badge.bond}"
            ),
            emoji=bot.emojis_by_name.get(offer.badge.emoji_name),
        )
        for offer in offers
        if offer.reason is None
    ]


# ---
# The Snack Pack
# ---


def badge_pack_lines(bot: "WispBot", owned: list[OwnedBadge]) -> list[str]:
    """One line per badge the member ever bought, in the order given."""
    lines = []
    for item in owned:
        badge = BADGE_BY_KEY.get(item.badge)
        if badge is not None:
            title = f"Wisp v{item.version}'s {badge.name}"
            lines.append(f"・{with_emoji(bot.emoji(badge.emoji_name), title)}")
    return lines


# ---
# When a life ends
# ---


async def strip_badges(bot: "WispBot", guild_id: int, life: Life) -> None:
    """Take the badge roles bought for an ended life off the members who bought them.

    Members are fetched by id, and one who left is skipped. A failure is
    reported in Wisp's House and never stops the rest. Doing it again is
    harmless: a member without the role is left as they are.
    """
    guild = bot.get_guild(guild_id)
    if guild is None or life.id is None:
        return
    try:
        buyers = await bot.badges.buyers(guild_id, life.id)
        if not buyers:
            return
        role_ids = await bot.badges.role_ids(guild_id)
    except pymysql.err.Error as error:
        await bot.report_error(guild, _TAKING_BACK, error)
        return
    reason = f"Wisp v{life.version}'s life ended"
    for user_id, keys in buyers.items():
        roles = [
            role
            for key in sorted(keys)
            if key in role_ids and (role := guild.get_role(role_ids[key])) is not None
        ]
        if not roles:
            continue
        try:
            member = await guild.fetch_member(user_id)
            await member.remove_roles(*roles, reason=reason)
        except discord.NotFound:
            continue
        except discord.HTTPException as error:
            await bot.report_error(guild, _TAKING_BACK, error)
