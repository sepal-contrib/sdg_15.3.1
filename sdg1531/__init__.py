"""SDG indicator 15.3.1 (Land Degradation Neutrality) — headless domain layer.

Side-effect free by contract: no module-level ``mkdir``, ``ee.Initialize``,
network call or config read anywhere in this package. Importing ``sdg1531`` must
stay free enough to happen at module scope in a Solara worker.

``__all__`` is empty and stays that way. The port was designed to expose explicit
re-exports plus an ``__all__`` here, and this file used to promise them
("Re-exports are added by the tasks that create the modules they name") -- eighteen
tasks landed and none did, because for a package this size
``from sdg1531.resolve import resolve`` is the clearer import and a re-export layer
is one more place for a name to go stale. The promise is deleted rather than kept;
``tests/test_rosters.py::test_the_namespace_exclusion_is_still_true`` AST-checks all
three ``__init__``s and pins the empty tuple, and the two sub-package ``__init__``s
say the same thing.

No EXPECTED_DIVERGENCES: a docstring and an empty ``__all__``. There is no code
here to diverge.
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()
