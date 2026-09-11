"""palette.py vendors matplotlib's CSS4 hex values so lc_color keeps colour parity
without dragging matplotlib into the domain.

The legacy path is indicator_model.py:248-250:

    all_colors = [hx for _, hx in pltc.cnames.items()]
    random.seed(100)
    colors = random.sample(all_colors, len(self.lc_classlist_start))

so both the *order* of the vendored tuple and the sampler's output are load-bearing.
"""

from __future__ import annotations

import random

import pytest

matplotlib_colors = pytest.importorskip("matplotlib.colors")


def test_vendored_palette_equals_matplotlib_cnames() -> None:
    from sdg1531.palette import CSS4_HEX

    assert list(CSS4_HEX) == list(matplotlib_colors.cnames.values())


def test_palette_has_the_148_entries_the_legacy_sampler_saw() -> None:
    from sdg1531.palette import CSS4_HEX

    assert len(matplotlib_colors.cnames) == 148
    assert len(CSS4_HEX) == 148
    assert isinstance(CSS4_HEX, tuple)


@pytest.mark.parametrize("n", [1, 3, 7, 13, 37, 148])
def test_seeded_sample_reproduces_the_legacy_sequence(n: int) -> None:
    from sdg1531.palette import CSS4_HEX

    legacy_pool = [hx for _, hx in matplotlib_colors.cnames.items()]
    random.seed(100)
    legacy = random.sample(legacy_pool, n)

    # the port uses a private Random so it never perturbs the process-wide RNG
    assert random.Random(100).sample(CSS4_HEX, n) == legacy


def test_the_first_thirteen_are_pinned() -> None:
    from sdg1531.palette import CSS4_HEX

    assert random.Random(100).sample(CSS4_HEX, 13) == [
        "#2F4F4F",
        "#B0E0E6",
        "#DDA0DD",
        "#1E90FF",
        "#FFDEAD",
        "#BA55D3",
        "#AFEEEE",
        "#C0C0C0",
        "#8B008B",
        "#4682B4",
        "#9932CC",
        "#00FFFF",
        "#ADD8E6",
    ]
