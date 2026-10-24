"""Sanity checks on the rule tables."""

from wisp.links import TrackKind
from wisp.rules import (
    BADGE_BY_KEY,
    BADGES,
    BOND_TIERS,
    MEAL_POINTS,
    RHYME_SKILL,
    SNACKS,
    STAGE_RULES,
    Stage,
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
        assert all(low < high for low, high in zip(lower, higher))


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


def test_every_hatched_stage_has_a_rhyme_skill() -> None:
    assert set(RHYME_SKILL) == set(Stage) - {Stage.EGG}


def test_the_badge_catalog() -> None:
    assert [
        (badge.key, badge.name, badge.cost, badge.bond, badge.needs_tier)
        for badge in BADGES
    ] == [
        ("egg_warmer", "Egg Warmer", 25, 5, None),
        ("pickle_diplomat", "Pickle Diplomat", 25, 5, None),
        ("flame_keeper", "Flame Keeper", 100, 15, None),
        ("viibr_roadie", "ViiBR Roadie", 100, 15, None),
        ("team_wisp", "Team Wisp", 250, 25, None),
        ("bandmate", "Bandmate", 250, 25, "Bandmate"),
    ]
    assert {badge.key: badge.phrase for badge in BADGES} == {
        "egg_warmer": "is now an Egg Warmer",
        "pickle_diplomat": "is now a Pickle Diplomat",
        "flame_keeper": "is now a Flame Keeper",
        "viibr_roadie": "is now a ViiBR Roadie",
        "team_wisp": "joined Team Wisp",
        "bandmate": "is now one of Wisp's Bandmates",
    }
    assert BOND_TIERS[-1][0] == "Bandmate"
    assert BADGE_BY_KEY["team_wisp"].emoji_name == "badge_team_wisp"
    assert all(len(badge.key) <= 20 for badge in BADGES)
