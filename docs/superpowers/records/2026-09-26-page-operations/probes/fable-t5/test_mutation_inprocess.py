"""Replicates the report's Step 5 mutation without touching the checkout:
add_redact_annot runs OUTSIDE the wrapper, apply_redactions inside."""
import pytest
import engine.operations as ops
from engine.geometry import at_rotation_zero
from tests.test_page_geometry import (
    test_both_redaction_calls_run_at_rotation_zero as t_both,
    test_erase_region_paints_exactly_one_fill_on_the_target as t_fill,
    test_redact_region_black_box_lands_on_the_target as t_black,
)


def mutated(page, rect, fill):
    page.add_redact_annot(rect, fill=fill)
    with at_rotation_zero(page):
        page.apply_redactions(images=2, graphics=1, text=0)


@pytest.fixture(autouse=True)
def mutate(monkeypatch):
    monkeypatch.setattr(ops, "_erase_region", mutated)


@pytest.mark.parametrize("rotation", (90, 180, 270))
def test_spy_under_mutation(rotation, monkeypatch):
    t_both(rotation, monkeypatch)


@pytest.mark.parametrize("crop", ("contained", "oversized"))
@pytest.mark.parametrize("rotation", (0, 90, 180, 270))
def test_fill_under_mutation(rotation, crop, monkeypatch):
    monkeypatch.setattr("tests.test_page_geometry._erase_region", mutated)
    t_fill(rotation, crop)


@pytest.mark.parametrize("rotation", (0, 90, 180, 270))
def test_black_under_mutation(rotation):
    t_black(rotation)
