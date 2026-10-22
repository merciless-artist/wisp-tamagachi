"""Sanity checks on the rule tables."""

from wisp.links import TrackKind
from wisp.rules import MEAL_POINTS, SNACKS, STAGE_RULES, Stage


def test_snack_keys_are_unique() -> None:
    keys = [snack.key for snack in SNACKS]
    assert len(keys) == len(set(keys)) == 9


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
