"""Small text pieces shared by Wisp's posts, and the frame of Myra's house style.

The house style is v4, `DOCS/specs/2026-11-24-house-style-v4-favorites.md`:
every menu looks like WiSP's Favorites, his lunchbox. A title line between two
of Myra's bars, `##` section headings each after one of her icons, `・` lines
for the items and her footer line with the site. Every menu gets its pieces
from a `Frame`, made of Wisp's app emojis; one not uploaded is left out.
"""

import re
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, TypeVar

MESSAGE_LIMIT: Final = 2000
LAYOUT_TEXT_LIMIT: Final = 4000
USER_ERROR: Final = "That didn't work. The error is posted in this channel."

_Words = TypeVar("_Words", bound=str | None)

# Pictographs, the technical, arrow and symbol blocks emoji come from (minus the
# music notes ♪ and ♫), ‼ and ⁉, plus the keycap, variation selector and
# zero-width joiner that build emoji sequences.
_EMOJI: Final = re.compile("[\U0001f000-\U0001faff⌀-⏿☀-♩♬-➿" "⬀-⯿‼⁉⃣️‍]")
# His name in a heading in capitals, which Myra spells WiSP.
_HIS_NAME: Final = re.compile(r"\bWISP\b")

# The plain divider of a short post, from house style v2.1.
SEPARATOR: Final = "𝄡" + "𝄚" * 22 + "𝄂"

# ---
# The Favorites style (house style v4)
# ---

# Wisp's app emojis the style is made of, by name.
TITLE_BAR: Final = ("headerbarright", "wisp_waveform", "headerbarleft")
FOOTER_BAR: Final = (
    "headerbarright",
    "headerbar",
    "wisp_waveform",
    "headerbar",
    "headerbarleft",
)
FOOTER_MIC: Final = "mic2"
# The section icons, taken in turn by a menu's sections.
SECTION_ICONS: Final = ("boing_bass", "wisp_play", "wisp_pause", "wisp_stop")
SITE: Final = "https://viibrmusic.com"
# Myra's blank line between entries of more than one line, as her songs have.
SPACER: Final = "** **"


@dataclass(frozen=True)
class Frame:
    """The pieces of a menu in WiSP's Favorites style.

    Each piece is the text of Wisp's app emojis, "" for one not uploaded, so
    a missing emoji is left out and the line still reads: with none uploaded
    the menu is plain text (`UNICODE_FRAME`). Headings are in capitals, with
    him spelled WiSP. A section heading takes the icon of its `place` in its
    menu, the icons in turn; a section a menu leaves out keeps its place, so
    the icons never shift.
    """

    title_bar: str
    footer_bar: str
    mic: str
    icons: tuple[str, ...]

    def title(self, name: str) -> str:
        """The menu's first line: `# ` and `name`, bold, between two title bars."""
        bold = f"**{heading_case(name)}**"
        if not self.title_bar:
            return f"# {bold}"
        return f"# {self.title_bar} {bold} {self.title_bar}"

    def heading(
        self, name: str, place: int, *, size: str = "##", gap: str = " "
    ) -> str:
        """A section heading: `size`, the icon of `place`, `gap`, `name` in bold.

        The lunchbox keeps Myra's own `size` and `gap` for two of its headings.
        """
        icon = self.icons[place % len(self.icons)]
        bold = f"**{heading_case(name)}**"
        return f"{size} {icon}{gap}{bold}" if icon else f"{size} {bold}"

    def item(self, text: str) -> str:
        """One item of a long list, in plain text: ` ・text`."""
        return f" ・{text}"

    def big_item(self, text: str) -> str:
        """One item of a short list, as large as a small heading: `### ・text`."""
        return f"### ・{text}"

    def note(self, text: str) -> str:
        """An information line, in plain text after a space."""
        return f" {text}"

    @property
    def footer(self) -> str:
        """The menu's last line: the site between two footer bars, as Myra drew it.

        With no bar uploaded it is the site alone, after the mic when it is up.
        """
        if not self.footer_bar:
            return self.big_item(f"{self.mic}{SITE}")
        bar = self.footer_bar
        return self.big_item(f"{bar}{self.mic}{SITE} {bar}・")

    @property
    def divider(self) -> str:
        """The line between the parts of a short post: the footer bar.

        With none of it uploaded it is the plain `SEPARATOR`, as in v2.1.
        """
        return self.footer_bar or SEPARATOR


def heading_case(name: str) -> str:
    """`name` in capitals for a heading, with Wisp spelled `WiSP` as Myra does.

    Only his name as a whole word changes, so "Wispy" is still "WISPY".
    """
    return _HIS_NAME.sub("WiSP", name.upper())


def frame_of(emoji: Callable[[str], str]) -> Frame:
    """The style's pieces from Wisp's app emojis.

    `emoji` gives an app emoji's text by name, or "" when it is not uploaded;
    a missing one is left out of its piece.
    """

    def bar(names: Sequence[str]) -> str:
        return "".join(emoji(name) for name in names)

    return Frame(
        title_bar=bar(TITLE_BAR),
        footer_bar=bar(FOOTER_BAR),
        mic=emoji(FOOTER_MIC),
        icons=tuple(emoji(name) for name in SECTION_ICONS),
    )


UNICODE_FRAME: Final = frame_of(lambda _name: "")
"""The style with none of its emojis uploaded: plain, readable text."""


# ---
# Lengths and fitting
# ---


def with_emoji(emoji: str, text: str) -> str:
    """`text` after its emoji and a space, or alone when there is no emoji."""
    return f"{emoji} {text}" if emoji else text


def text_length(text: str) -> int:
    """The length of `text` counted in UTF-16 units, as JavaScript counts it.

    Characters outside the Basic Multilingual Plane, such as the music symbols
    of `SEPARATOR`, count twice, so a text this fits never runs over Discord's limit
    however Discord counts it.
    """
    return len(text.encode("utf-16-le")) // 2


def clip(text: str, room: int) -> str:
    """The longest start of `text` within `room` UTF-16 units.

    It never ends inside a character, so a character outside the Basic
    Multilingual Plane is kept whole or left out.
    """
    used = 0
    for index, character in enumerate(text):
        used += text_length(character)
        if used > room:
            return text[:index]
    return text


def fit(
    head: list[str],
    optional: list[str],
    tail: Sequence[str] = (),
    limit: int = MESSAGE_LIMIT,
) -> str:
    """Join `head`, as many whole `optional` lines as fit in `limit`, and `tail`.

    Optional lines are taken in order, so the ones to drop first go last. The
    text is measured by `text_length`.
    """
    lines = head
    for line in optional:
        if text_length("\n".join([*lines, line, *tail])) > limit:
            break
        lines = [*lines, line]
    return "\n".join([*lines, *tail])


def richest(plain: Sequence[str], rich: Sequence[str], room: int) -> list[str]:
    """`plain`, with each line swapped for its `rich` form while all still fit.

    Lines are tried in order, and a swap is kept only when the joined lines
    stay within `room`, counted by `text_length`. The plain lines are kept
    even when they do not fit.
    """
    lines = list(plain)
    for index, line in enumerate(rich):
        tried = [*lines[:index], line, *lines[index + 1 :]]
        if text_length("\n".join(tried)) <= room:
            lines = tried
    return lines


def count(amount: int, noun: str) -> str:
    """`amount` with `noun`, pluralised with an "s" unless the amount is one."""
    return f"{amount} {noun}" if amount == 1 else f"{amount} {noun}s"


def any_role(role_ids: Collection[int], shown: int) -> str:
    """The roles as mentions, any one of which will do: "<@&1>, <@&2> or <@&3>".

    At most `shown` are named, lowest id first, then how many more there are,
    as in "<@&1>, <@&2> or 3 more". Empty when there are none. A mention only
    pings when the send allows it.
    """
    mentions = [f"<@&{role_id}>" for role_id in sorted(role_ids)]
    if len(mentions) > shown:
        named = mentions[:shown]
        return f"{', '.join(named)} or {len(mentions) - shown} more"
    if len(mentions) < 2:
        return "".join(mentions)
    return f"{', '.join(mentions[:-1])} or {mentions[-1]}"


def timestamp(moment: datetime) -> str:
    """`moment` as a Discord timestamp, which each reader sees in their own time.

    It shows as a short time of day, such as "10:00 PM".
    """
    return f"<t:{int(moment.timestamp())}:t>"


def daily_reset(now: datetime) -> str:
    """When the daily limits reset after `now`: next UTC midnight, as a timestamp."""
    midnight = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return timestamp(midnight + timedelta(days=1))


def channel_or(words: _Words, channel_id: int | None) -> str | _Words:
    """The channel's link, `<#id>`, or `words` when no channel is given."""
    return words if channel_id is None else f"<#{channel_id}>"


def round_half_up(value: float) -> int:
    """`value` as a whole number, a half rounding up, as the status card shows it."""
    return int(value + 0.5)


def meter_receipt(meter: str, before: float, after: float) -> str:
    """What a meter did, as whole numbers: `Wellbeing +8 (now 66)`.

    The change is the difference of the shown numbers, so it always adds up.
    """
    shown = round_half_up(after)
    change = shown - round_half_up(before)
    return f"{meter} {change:+d} (now {shown})"


def strip_emoji(text: str) -> str:
    """Remove Unicode emoji, keeping the ♪ and ♫ flair and every other character."""
    return _EMOJI.sub("", text)
