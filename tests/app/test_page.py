"""The shell renders and is wired the way pysepal requires."""

from __future__ import annotations

import inspect

import reacton.core
import solara

from app import page as page_module


def test_page_is_a_solara_component():
    # reacton.core.Component, not solara.core.Component -- the latter does not
    # exist. @solara.component returns a reacton ComponentFunction, which is a
    # reacton.core.Component; solara re-exports no Component name at all.
    assert isinstance(page_module.Page, reacton.core.Component)
    assert isinstance(page_module.Sdg1531App, reacton.core.Component)


def test_the_shell_renders():
    """A render that raises takes the whole app down at load; this is the
    cheapest possible guard against that."""
    _box, rc = solara.render(page_module.Sdg1531App(), handle_error=False)
    assert rc is not None


def test_the_shell_uses_mapapp_element_not_the_constructor():
    """`MapApp(...)` builds a widget outside Solara's render tree and the
    layout silently does not update. `MapApp.element(...)` is the only
    supported form."""
    source = inspect.getsource(page_module)
    assert "MapApp.element(" in source
    assert "MapApp(" not in source.replace("MapApp.element(", "")
