"""``app/panels/fields.py``: a problem reaches a control, or it reaches the alert.

Moving validation messages out of one per-step alert and onto the controls
themselves buys locality at the cost of a new failure mode: a problem whose
field no control claims could now reach nothing at all, and an app that
silently stops reporting a rule is worse than one that reports it in an
awkward place. Two properties close that, and both are checked here rather
than described.

1. :class:`ProblemRouter` partitions. Every problem handed in comes back from
   exactly one ``take`` or from ``rest`` -- never both, never neither.
2. Every step renders its ``rest``. An unrecognised field injected into any of
   the four configuration steps still appears on screen.

Property 1 is the mechanism; property 2 is the thing that actually matters,
and it is asserted against the real steps rather than against the router,
because a step that computed ``rest`` correctly and then dropped it on the
floor would satisfy property 1 alone.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
import solara
from hypothesis import given
from hypothesis import strategies as st
from pysepal.solara.notifications import NotificationProvider

from app.panels.fields import ProblemRouter
from app.steps.land_cover import LandCoverStep
from app.steps.productivity import ProductivityStep
from app.steps.run import BuildOutcome, RunStep
from app.steps.soc import SocStep
from sdg1531.validate import Problem
from tests.app.render_helpers import alert_texts, field_messages
from tests.spec_factory import default_spec

#: The marker text injected below. Long and unmistakable so a test that found
#: it cannot have found some real rule's message by coincidence.
_INJECTED = "an unrouted problem that must still reach the user"


def _problem(field: str, *, fatal: bool = True) -> Problem:
    return Problem(field=field, code="injected", message=_INJECTED, fatal=fatal)


_FIELDS = st.sampled_from(
    [
        "",
        "aoi",
        "land_cover",
        "land_cover.start_asset",
        "periods.overall.start",
        "periods.soc",
        "vi_source.names",
        "water_mask",
        "something.nobody.claims",
    ]
)


@given(
    fields=st.lists(_FIELDS, max_size=8),
    takes=st.lists(st.lists(_FIELDS, min_size=1, max_size=3), max_size=4),
)
def test_the_router_hands_every_problem_to_exactly_one_place(fields, takes):
    """Property 1. Whatever the ``take`` calls ask for, and in whatever order,
    the taken groups plus ``rest`` reconstruct the input exactly once over.

    Generated rather than enumerated because the failure this guards against
    is an overlap between two ``take`` calls over the same dotted subtree
    (``land_cover`` and ``land_cover.start_asset`` are both in ``_FIELDS``
    precisely so that case is generated), which a hand-written pair of
    examples would only cover in the order it happened to be written in.
    """
    problems = [_problem(field) for field in fields]
    router = ProblemRouter(problems)

    taken = [router.take(*group) for group in takes]
    flat = [problem for group in taken for problem in group]

    # Identity, not equality: two injected problems on the same field are
    # equal as frozen dataclasses, so a router that duplicated one and dropped
    # another would balance out under `==`.
    assert sorted(map(id, flat + list(router.rest))) == sorted(map(id, problems))


def test_a_later_take_cannot_reclaim_what_an_earlier_one_took():
    """The ordering rule ``ProblemRouter``'s docstring states, made concrete:
    ``land_cover`` owns ``land_cover.start_asset`` by the dotted-subtree rule,
    so taking the specific field first is what leaves the general one with
    only its own.
    """
    specific = _problem("land_cover.start_asset")
    general = _problem("land_cover")
    router = ProblemRouter([specific, general])

    assert router.take("land_cover.start_asset") == (specific,)
    assert router.take("land_cover") == (general,)
    assert router.rest == ()


@solara.component
def _RendersNothing(**_: object) -> None:
    """A drop-in for a component under test, accepting any props and drawing
    nothing -- a named component, not ``solara.component(lambda ...)``, whose
    source solara cannot parse to validate hooks against."""


@solara.component
def _Harness(build: Callable[[], None]) -> None:
    """One step, under a mounted ``NotificationProvider``.

    ``LandCoverStep`` calls ``use_notifications()``, which raises without a
    provider. The rest of ``tests/app`` gets one from whichever module
    rendered the page first, so those step tests pass as a directory and fail
    run alone; this module mounts its own rather than inheriting that.

    ``build`` is a factory, not an element: an element has to be CREATED
    inside this component's body to be added to its container.
    """
    NotificationProvider()
    build()


def _render_step(build: Callable[[], None]) -> object:
    """Render on a running loop -- ``LandCoverStep``'s custom-arm picker
    schedules an asset listing at mount (see ``test_step_land_cover.py``'s own
    ``_render``), and the other three are unaffected by having one."""

    async def main() -> tuple[object, object]:
        return solara.render(_Harness(build=build), handle_error=False)

    box, rc = asyncio.run(main())
    assert rc is not None
    return box


@pytest.mark.parametrize(
    ("step", "unclaimed_field"),
    [
        # One field per step that the step OWNS (`app.state.STEP_PREFIXES`)
        # and no control in it claims. `run`'s empty field is the real
        # `internal_error` case; `climate.coefficient` and `transition_matrix`
        # are real fields with no widget; `periods.soc.middle` stands for a
        # field added under a prefix whose endpoints are already claimed.
        ("run", ""),
        ("productivity", "climate.coefficient"),
        ("land_cover", "transition_matrix"),
        ("soc", "periods.soc.middle"),
    ],
)
@pytest.mark.parametrize("fatal", [True, False])
def test_a_problem_no_control_claims_still_reaches_the_user(
    monkeypatch, step, unclaimed_field, fatal
):
    """Property 2, the one that matters.

    ``problems_for`` is patched in the STEP's own namespace, which is where
    each step imported it to, so this drives the real render path with a
    problem the router cannot place. Both severities are checked: the fatal
    and non-fatal halves take different routes inside
    ``app/panels/fields.py``, so a regression could lose one and keep the
    other.
    """
    spec = solara.reactive(default_spec())
    injected = (_problem(unclaimed_field, fatal=fatal),)
    monkeypatch.setattr(f"app.steps.{step}.problems_for", lambda *_: injected)

    components = {
        "run": lambda: RunStep(spec=spec, outcome=BuildOutcome()),
        "productivity": lambda: ProductivityStep(spec=spec),
        "land_cover": lambda: LandCoverStep(spec=spec),
        "soc": lambda: SocStep(spec=spec),
    }
    box = _render_step(components[step])

    shown = [text for _severity, text in field_messages(box) + alert_texts(box)]
    assert shown.count(_INJECTED) == 1, (
        f"{step} did not show a problem on {unclaimed_field!r} exactly once; "
        "a field no control claims must still fall through to the step's alert"
    )


def test_the_injection_would_notice_a_step_that_dropped_it(monkeypatch):
    """Mutation guard for the check above: the assertion is only meaningful if
    a step that genuinely showed nothing would fail it. Patching the alert to
    render nothing is the smallest way to make that happen, and it must turn
    the run step's own case red.
    """
    spec = solara.reactive(default_spec())
    monkeypatch.setattr("app.steps.run.problems_for", lambda *_: (_problem(""),))
    monkeypatch.setattr("app.steps.run.ProblemsList", _RendersNothing)

    box = _render_step(lambda: RunStep(spec=spec, outcome=BuildOutcome()))

    shown = [text for _severity, text in field_messages(box) + alert_texts(box)]
    assert _INJECTED not in shown
