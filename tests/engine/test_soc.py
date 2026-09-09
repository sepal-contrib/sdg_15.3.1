"""Soil organic carbon. Transcribed from component/scripts/soil_organic_carbon.py:6-178.

The interesting fact under test is D13: the first year pair is encoded at scale 100
(:50) and every later pair at scale 10 (:114), so from year two onward the codes fall
outside IPCC_TRANSITION_CODES entirely and every CHANGED pixel loses its stock update.
Phase 1 preserves this byte-for-byte behind
``Compatibility.soc_subsequent_transition_scale``.
"""

from __future__ import annotations

from sdg1531.engine.soc import soc_transition_code
from sdg1531.tables import IPCC_TRANSITION_CODES, TRANSLATION_MATRIX
from tests.engine.graph import _call, _image_constant, _root

# --- the defect, stated against the tables themselves -------------------------


def test_scale_100_codes_are_exactly_the_ipcc_domain():
    """soil_organic_carbon.py:50 -- the first pair is encoded correctly."""
    codes = sorted(set(TRANSLATION_MATRIX[1]))
    scale_100 = {a * 100 + b for a in codes for b in codes}

    assert scale_100 == set(IPCC_TRANSITION_CODES)
    assert len(scale_100) == 49


def test_scale_10_codes_are_disjoint_from_the_ipcc_domain():
    """soil_organic_carbon.py:114 -- from year two onward the transition codes are
    110..770, which no entry of IPCC_TRANSITION_CODES matches, so `Image.remap` (no
    defaultValue) masks every changed pixel out of the three stock-change remaps."""
    codes = sorted(set(TRANSLATION_MATRIX[1]))
    scale_10 = {a * 10 + b for a in codes for b in codes}

    assert len(scale_10) == 49
    assert scale_10.isdisjoint(set(IPCC_TRANSITION_CODES))


# --- soc_transition_code, the one place the multiplier lives ------------------


def _code_parts(scale):
    """`(multiplied constant, scale, added constant)` of `soc_transition_code`'s node.

    The two inputs are `ee.Image(1)` and `ee.Image(2)` so that the OPERAND ORDER is
    readable off the graph: `lc1.multiply(s).add(lc0)` is an equally valid-looking
    node that decodes every transition backwards.
    """
    import ee

    node = soc_transition_code(ee.Image(1), ee.Image(2), scale)
    deref, _graph, root = _root(node)

    add = _call(root)
    assert add is not None and add["functionName"] == "Image.add"
    multiply = _call(deref(add["arguments"]["image1"]))
    assert multiply is not None and multiply["functionName"] == "Image.multiply"

    return (
        _image_constant(deref(multiply["arguments"]["image1"]), deref),
        _image_constant(deref(multiply["arguments"]["image2"]), deref),
        _image_constant(deref(add["arguments"]["image2"]), deref),
    )


def test_soc_transition_code_multiplies_the_FIRST_image_by_the_scale():
    """soil_organic_carbon.py:50 / :114 -- `lc_time0.multiply(scale).add(lc_time1)`."""
    assert _code_parts(100) == (1, 100, 2)
    assert _code_parts(10) == (1, 10, 2)
