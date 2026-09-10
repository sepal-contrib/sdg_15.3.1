"""SDG indicator 15.3.1 (Land Degradation Neutrality) — headless domain layer.

Side-effect free by contract: no module-level ``mkdir``, ``ee.Initialize``,
network call or config read anywhere in this package (spec §4, §11.2).
Re-exports are added by the tasks that create the modules they name.

No EXPECTED_DIVERGENCES: a docstring and an empty ``__all__``. There is no code here to diverge.
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()
