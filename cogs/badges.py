"""Badges: Wisp's vanity roles, how the Vault offers them and taking them back.

Buying one happens in the Vault (see `cogs.snacks`). A badge is worn for one
Wisp's life; once that life has ended the life loop's sweep takes the roles
back, and the buyers keep the badge in their Snack Pack.
"""

import contextlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

import discord
import pymysql

from cogs.assets import ASSETS_DIR
from db.badges import OwnedBadge
from wisp.bond import tier_for
from wisp.life import is_over
from wisp.rules import BADGE_BY_KEY, BADGES, Badge, badge_name
from wisp.text import count, with_emoji

if TYPE_CHECKING:
    from app import WispBot

BADGE_ART: Final = ASSETS_DIR / "badges"
_ROLE_ICONS: Final = "ROLE_ICONS"
_SET_UP: Final = "Wisp's badge for the ViiBR Vault"
_TAKING_BACK: Final = "taking back badge roles"
_FORGOTTEN: Final = "Wisp could not remember this badge role"
_RETIRED: Final = "This badge is no longer sold in the ViiBR Vault"
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
    renamed: list[str] = field(default_factory=list)
    iconed: list[str] = field(default_factory=list)
    retired: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        lines = [
            f"・Badge {what}: {', '.join(names)}"
            for what, names in (
                ("roles created", self.created),
                ("roles recreated", self.recreated),
                ("roles renamed", self.renamed),
                ("icons added", self.iconed),
                ("roles no longer sold, deleted", self.retired),
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
    """Make the badge roles match the catalog.

    Each missing role is created, a role whose name differs from its badge's
    is renamed, roles without an icon get one, and the roles of badges no
    longer sold are deleted (see `_delete_retired`). Roles are found by their
    stored id, so a stored role that was deleted is created again. A role gets
    its icon when its art exists and the server can show role icons; one
    Discord turns the icon down is made without it, and the server is treated
    as having no role icons. Failures are reported in `where`. A missing
    permission, or a new role that cannot be remembered, stops the setup
    there, since every later badge would fail the same way; the role that was
    not remembered is deleted again. Returns the lines for the setup reply.
    """
    setup = _RoleSetup(icons_allowed=_ROLE_ICONS in guild.features)
    stored = await bot.badges.role_ids(guild.id)
    for badge in BADGES:
        role_id = stored.get(badge.key)
        role = None if role_id is None else guild.get_role(role_id)
        context = f"creating the {badge.name} badge role"
        try:
            if role is None:
                await _create_role(bot, guild, badge, setup)
                (setup.created if role_id is None else setup.recreated).append(
                    badge.name
                )
                continue
            if role.name != badge.name:
                context = f"renaming the {badge.name} badge role"
                await role.edit(name=badge.name, reason=_SET_UP)
                setup.renamed.append(badge.name)
            context = f"adding the {badge.name} badge icon"
            if await _add_icon(role, badge, setup):
                setup.iconed.append(badge.name)
        except discord.Forbidden as error:
            await bot.report_error(guild, context, error, where=where)
            break
        except discord.HTTPException as error:
            await bot.report_error(guild, context, error, where=where)
        except pymysql.err.Error as error:
            context = f"remembering the {badge.name} badge role"
            await bot.report_error(guild, context, error, where=where)
            break
    else:
        await _delete_retired(bot, guild, stored, setup, where)
    return setup.lines()


async def _delete_retired(
    bot: "WispBot",
    guild: discord.Guild,
    stored: dict[str, int],
    setup: _RoleSetup,
    where: discord.abc.Messageable | None,
) -> None:
    """Delete the roles of stored badges that are no longer sold, then forget them.

    Only roles Wisp stored, by id, are deleted; one already gone is just
    forgotten. A role that cannot be deleted stays stored, so the next setup
    tries again and the sweep can still take it back. A missing permission
    stops here, since every later deletion would fail the same way.
    """
    for key, role_id in stored.items():
        if key in BADGE_BY_KEY:
            continue
        name = badge_name(key)
        context = f"deleting the {name} badge role, no longer sold"
        role = guild.get_role(role_id)
        try:
            if role is not None:
                await role.delete(reason=_RETIRED)
            await bot.badges.forget_role(guild.id, key)
        except discord.Forbidden as error:
            await bot.report_error(guild, context, error, where=where)
            return
        except (discord.HTTPException, pymysql.err.Error) as error:
            await bot.report_error(guild, context, error, where=where)
            continue
        setup.retired.append(name)


async def _create_role(
    bot: "WispBot", guild: discord.Guild, badge: Badge, setup: _RoleSetup
) -> None:
    """Create a badge's role, with its icon when allowed, and remember it.

    Raises:
        pymysql.err.Error: The role could not be remembered. It is deleted
            again, as far as Discord allows.
    """
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
    try:
        await bot.badges.set_role(guild.id, badge.key, role.id)
    except pymysql.err.Error:
        with contextlib.suppress(discord.HTTPException):
            await role.delete(reason=_FORGOTTEN)
        raise


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
    """One line per badge the member ever bought, in the order given.

    A badge no longer sold is kept as a collectible under its stored key.
    """
    lines = []
    for item in owned:
        title = f"Wisp v{item.version}'s {badge_name(item.badge)}"
        emoji = bot.emoji(f"badge_{item.badge}")
        lines.append(f"・{with_emoji(emoji, title)}")
    return lines


# ---
# When a life ends
# ---


async def sweep_badges(bot: "WispBot", guild_id: int, now: datetime) -> None:
    """Take back the badge roles of every ended life that are still worn.

    Each purchase is marked once its role is off, or once its member left or
    its role is gone, so it is never handled again; with nothing pending this
    is one query. A member who bought the badge again for the current life
    while the role came off gets it straight back. A failure leaves the
    purchase for the next sweep and is reported in Wisp's House once per
    streak of failing sweeps; a missing permission ends this sweep, since the
    rest would fail the same way.
    """
    streak = (guild_id, _TAKING_BACK)
    pending = await bot.badges.pending(guild_id)
    if not pending:
        bot.failing_displays.discard(streak)
        return
    guild = bot.get_guild(guild_id)
    if guild is None:
        return
    role_ids = await bot.badges.role_ids(guild_id)
    grouped: dict[tuple[int, int, int], set[str]] = {}
    for item in pending:
        grouped.setdefault((item.user_id, item.life_id, item.version), set()).add(
            item.badge
        )
    failed = False
    for (user_id, life_id, version), keys in grouped.items():
        roles = {
            key: role
            for key in sorted(keys)
            if key in role_ids and (role := guild.get_role(role_ids[key])) is not None
        }
        try:
            if roles:
                member = await guild.fetch_member(user_id)
                await member.remove_roles(
                    *roles.values(), reason=f"Wisp v{version}'s life ended"
                )
                await _give_back_rebought(bot, guild_id, member, roles)
        except discord.NotFound:
            pass
        except discord.HTTPException as error:
            failed = True
            if streak not in bot.failing_displays:
                bot.failing_displays.add(streak)
                await bot.report_error(guild, _TAKING_BACK, error)
            if isinstance(error, discord.Forbidden):
                return
            continue
        await bot.badges.mark_removed(guild_id, user_id, life_id, keys, now)
    if not failed:
        bot.failing_displays.discard(streak)


async def _give_back_rebought(
    bot: "WispBot",
    guild_id: int,
    member: discord.Member,
    removed: dict[str, discord.Role],
) -> None:
    """Give back any just-removed role the member bought again for the current life.

    A purchase can land between the sweep reading what is pending and taking
    the roles off.
    """
    life = await bot.lives.current(guild_id)
    if life is None or life.id is None or is_over(life):
        return
    owned = await bot.badges.owned(guild_id, member.id, life.id)
    rebought = [role for key, role in removed.items() if key in owned]
    if rebought:
        await member.add_roles(
            *rebought, reason=f"Bought again for Wisp v{life.version}"
        )
