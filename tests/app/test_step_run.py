"""Build is pure graph construction: no network, no task, no spinner.

The step is the LAST trigger before a run leaves pure Python: it shows only
the whole-spec and overall-period problems it owns, disables Build while any
fatal problem stands anywhere in the spec, and on a real click either fills
``maps``/``ctx`` and reports success, or -- for a spec ``resolve()`` itself
refuses -- notifies the error and leaves both reactives untouched.
"""

from __future__ import annotations

import re

import ipyvuetify
import pytest
import solara

from app.message import msg
from app.steps.run import RunStep, build
from sdg1531.engine.context import ExecutionContext
from sdg1531.engine.indicator import IndicatorMaps
from sdg1531.spec import Period, PeriodOverride, RunSpec, SubPeriods
from tests.spec_factory import default_spec

_MARKDOWN_RE = re.compile(r'<div class="solara-markdown[^"]*"[^>]*>(.*?)</div>', re.DOTALL)

# Every non-overall sub-period pinned to a range that resolves on its own,
# independent of `overall` -- so inverting `overall` below trips only
# `_base_period_problems`, not every other check that falls back to it.
_ISOLATING_OVERRIDE = PeriodOverride(start=2000, end=2015)

# default_spec()'s sensor is MODIS, and MODIS is one of the rungs that
# `_process_modis` requires a resolved float threshold for (validate() does
# not check it -- there is no rule for it in sdg1531.validate -- so an actually
# buildable spec needs it set here, matching tests/engine/test_integration.py).
_BUILDABLE_SPEC = default_spec(threshold=0.0)

_SPEC_WITH_A_RUN_PROBLEM = default_spec(
    periods=SubPeriods(
        overall=Period(start=2020, end=2000),  # inverted: start_not_before_end
        trend=_ISOLATING_OVERRIDE,
        state=_ISOLATING_OVERRIDE,
        performance=_ISOLATING_OVERRIDE,
        land_cover=_ISOLATING_OVERRIDE,
        soc=_ISOLATING_OVERRIDE,
    )
)


def _markdown_texts(node: object) -> list[str]:
    """Every rendered markdown paragraph under ``node``, in tree order.

    See ``tests/app/test_step_aoi.py`` for why this reads ``.template``
    rather than an extracted helper.
    """
    texts = []
    template = getattr(node, "template", None)
    if isinstance(template, str) and "solara-markdown" in template:
        match = _MARKDOWN_RE.search(template)
        if match:
            texts.append(match.group(1).strip())
    for child in getattr(node, "children", None) or ():
        texts.extend(_markdown_texts(child))
    return texts


def _find_widget(root: object, cls: type) -> object | None:
    """The first ``cls`` instance in the render tree, walking ``.children``."""
    if isinstance(root, cls):
        return root
    for child in getattr(root, "children", None) or []:
        found = _find_widget(child, cls)
        if found is not None:
            return found
    return None


class _FakeNotifier:
    """A spy standing in for ``use_notifications()``'s real bus-backed notifier."""

    def __init__(self) -> None:
        self.successes: list[str] = []
        self.errors: list[str] = []

    def success(self, message: str) -> None:
        self.successes.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)


def test_build_returns_the_maps_and_the_context():
    """Both statistics calls need the context, so build hands it back rather
    than making each panel re-derive the analysis scale."""
    maps, ctx = build(_BUILDABLE_SPEC)
    assert isinstance(maps, IndicatorMaps)
    assert isinstance(ctx, ExecutionContext)
    assert len(maps.layers()) == 7


def test_build_touches_no_network():
    """If this ever needs credentials it has stopped being pure graph
    construction, and the UI's whole no-spinner design is wrong."""
    import socket

    original = socket.socket

    def forbidden(*args, **kwargs):
        raise AssertionError("build() opened a socket; it must stay offline")

    socket.socket = forbidden
    try:
        build(_BUILDABLE_SPEC)
    finally:
        socket.socket = original


@pytest.mark.parametrize(
    ("spec", "expected_extra"),
    [
        (default_spec(), []),
        (
            _SPEC_WITH_A_RUN_PROBLEM,
            [
                "<p><strong>The assessment start year must be earlier than the "
                "end year.</strong></p>",
                "<p>Fix the problems above before building.</p>",
            ],
        ),
    ],
)
def test_the_step_renders_only_its_own_text(spec, expected_extra):
    """Pins what the step actually shows, in both states: a runnable spec
    shows only the description, and a spec with a fatal problem THIS step
    owns shows that problem's text and the blocked notice -- not just that
    the render did not raise."""
    spec_r = solara.reactive(spec)
    maps = solara.reactive(None)
    ctx = solara.reactive(None)
    box, rc = solara.render(RunStep(spec=spec_r, maps=maps, ctx=ctx), handle_error=False)
    assert rc is not None
    assert _markdown_texts(box) == [
        "<p>Build the indicator from the configuration above.</p>",
        *expected_extra,
    ]


@pytest.mark.parametrize(
    ("spec", "expected_disabled"),
    [(default_spec(), False), (_SPEC_WITH_A_RUN_PROBLEM, True)],
)
def test_the_build_button_is_disabled_exactly_when_not_runnable(spec, expected_disabled):
    """``is_runnable`` -- not a length check on ``problems_for`` -- gates the
    button, so a problem some OTHER step owns still disables it here."""
    spec_r = solara.reactive(spec)
    maps = solara.reactive(None)
    ctx = solara.reactive(None)
    box, rc = solara.render(RunStep(spec=spec_r, maps=maps, ctx=ctx), handle_error=False)
    assert rc is not None

    button = _find_widget(box, ipyvuetify.Btn)
    assert button is not None
    assert button.disabled is expected_disabled
    assert button.color == "primary"


def test_clicking_build_fills_the_reactives_and_reports_success(monkeypatch):
    """A real click on the rendered widget -- not a captured spy -- proves
    the button is wired to ``build()``, that BOTH reactives it hands back are
    written, and that the count in the success toast is the real one."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.steps.run.use_notifications", lambda: fake)

    spec = solara.reactive(_BUILDABLE_SPEC)
    maps = solara.reactive(None)
    ctx = solara.reactive(None)
    box, rc = solara.render(RunStep(spec=spec, maps=maps, ctx=ctx), handle_error=False)
    assert rc is not None

    button = _find_widget(box, ipyvuetify.Btn)
    assert button is not None
    assert button.disabled is False

    button.click()

    assert isinstance(maps.value, IndicatorMaps)
    assert isinstance(ctx.value, ExecutionContext)
    assert fake.successes == [msg("run.built", count=len(maps.value.layers()))]
    assert fake.errors == []


def test_clicking_build_on_a_spec_resolve_refuses_notifies_the_error_and_writes_nothing(
    monkeypatch,
):
    """``build()`` can still raise ``SpecError`` for a spec ``validate()`` never
    flagged (e.g. no vi_source at all) -- the tuple assignment must not run
    half-way, and the error the user sees must be the domain's own message."""
    fake = _FakeNotifier()
    monkeypatch.setattr("app.steps.run.use_notifications", lambda: fake)

    spec = solara.reactive(RunSpec())
    maps = solara.reactive(None)
    ctx = solara.reactive(None)
    box, rc = solara.render(RunStep(spec=spec, maps=maps, ctx=ctx), handle_error=False)
    assert rc is not None

    button = _find_widget(box, ipyvuetify.Btn)
    assert button is not None

    button.click()  # a programmatic click bypasses the `disabled` UI hint

    assert maps.value is None
    assert ctx.value is None
    assert fake.errors == ["vi_source is not set"]
    assert fake.successes == []


def test_the_step_renders():
    spec = solara.reactive(default_spec())
    maps = solara.reactive(None)
    ctx = solara.reactive(None)
    _box, rc = solara.render(RunStep(spec=spec, maps=maps, ctx=ctx), handle_error=False)
    assert rc is not None
