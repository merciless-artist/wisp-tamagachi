"""Sanity checks on the rule tables."""

from datetime import timedelta

import pytest

from wisp.links import TrackKind
from wisp.rules import (
    BADGE_BY_KEY,
    BADGES,
    BOND_TIERS,
    FAREWELL_AT_DAY,
    MEAL_POINTS,
    OLD_FOGEY_AT_DAY,
    RHYME_SKILL,
    RHYME_SURE_TURNS,
    SNACKS,
    STAGE_MIN_TIME,
    STAGE_RULES,
    Stage,
    badge_name,
)


def test_snack_keys_are_unique() -> None:
    keys = [snack.key for snack in SNACKS]
    assert len(keys) == len(set(keys))


def test_snack_asset_names_follow_the_key() -> None:
    snack = next(snack for snack in SNACKS if snack.key == "viibrwave")
    assert snack.emoji_name == "snack_viibrwave"
    assert snack.gif_name == "eat_viibrwave.gif"


def test_only_the_daily_snack_is_free() -> None:
    assert [snack.key for snack in SNACKS if snack.cost == 0] == ["sinewave"]


def test_stage_requirements_rise_with_each_stage() -> None:
    ordered = [STAGE_RULES[stage] for stage in (Stage.CHILD, Stage.TEEN, Stage.ADULT)]
    for lower, higher in zip(ordered, ordered[1:]):
        assert lower.growth < higher.growth
        assert lower.share < higher.share
        assert lower.by_day < higher.by_day


def test_every_wisp_is_adult_before_old_age_and_gone_by_day_30() -> None:
    assert STAGE_RULES[Stage.ADULT].by_day < OLD_FOGEY_AT_DAY < FAREWELL_AT_DAY
    assert FAREWELL_AT_DAY == 30
    assert STAGE_MIN_TIME == timedelta(days=3)


def test_every_track_kind_has_meal_points() -> None:
    assert set(MEAL_POINTS) == set(TrackKind)


def test_stage_labels() -> None:
    assert [stage.label for stage in Stage] == [
        "Egg",
        "Baby",
        "Child",
        "Teen",
        "Adult",
        "Rockstar",
        "Old Fogey",
    ]


def test_every_hatched_stage_has_a_rhyme_skill_and_sure_turns() -> None:
    assert set(RHYME_SKILL) == set(Stage) - {Stage.EGG}
    assert set(RHYME_SURE_TURNS) == set(RHYME_SKILL)


def test_the_badge_catalog() -> None:
    assert [
        (badge.key, badge.name, badge.cost, badge.bond, badge.needs_tier)
        for badge in BADGES
    ] == [
        ("pickle_diplomat", "Pickle Diplomat", 25, 5, None),
        ("flame_keeper", "Flame Keeper", 100, 15, None),
        ("team_viibr", "Team ViiBR", 250, 25, None),
        ("bandmate", "Bandmate", 250, 25, "Bandmate"),
    ]
    assert {badge.key: badge.phrase for badge in BADGES} == {
        "pickle_diplomat": "is now a Pickle Diplomat",
        "flame_keeper": "is now a Flame Keeper",
        "team_viibr": "joined Team ViiBR",
        "bandmate": "is now one of Wisp's Bandmates",
    }
    assert BOND_TIERS[-1][0] == "Bandmate"
    assert BADGE_BY_KEY["team_viibr"].emoji_name == "badge_team_viibr"
    assert all(len(badge.key) <= 20 for badge in BADGES)


@pytest.mark.parametrize(
    ("key", "name"),
    [
        ("team_viibr", "Team ViiBR"),
        ("egg_warmer", "Egg Warmer"),
        ("viibr_roadie", "ViiBR Roadie"),
        ("some_old_badge", "Some Old Badge"),
    ],
)
def test_a_badge_no_longer_sold_still_has_a_readable_name(key: str, name: str) -> None:
    assert badge_name(key) == name
