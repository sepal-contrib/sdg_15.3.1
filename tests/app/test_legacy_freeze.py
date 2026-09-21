"""The legacy science is frozen: the parity harness imports it.

Stage A of the parity harness runs `component/scripts/run_15_3_1.py` against
`component/model/indicator_model.py` to produce the golden graphs the port is
compared to. An innocent edit there silently invalidates the D9 evidence, so
this pins the four directories that must not move.

Pinned by the CONTENT ON DISK, and it took two wrong versions to get here.

The first named a baseline commit and asked `git diff` what had changed since.
That pins where the freeze started rather than what is frozen, and it breaks
on any history rewrite (the SHA is orphaned and `git diff` exits 128, which is
how CI found it) and again on a squash-merge, which erases every commit this
branch has.

The second used `git rev-parse HEAD:<dir>`, a tree hash, which survives both.
But it reads the COMMITTED tree: editing a frozen file and running the suite
still passed, because the commit had not moved. A guard that only notices an
edit you have already committed is not much of a guard.

So this digests the files as they sit in the working tree. No git, no history,
no commit needed -- it fails on the edit itself, works in a tarball checkout,
and is identical before and after a squash-merge.
"""

from __future__ import annotations

import hashlib
import pathlib

#: Directory -> the digest of its contents, from :func:`digest_of` below.
#: Regenerate with:
#:
#:     python -c "from tests.app.test_legacy_freeze import *; \
#:                print({d: digest_of(d) for d in FROZEN})"
#:
#: A value changed here without a matching entry in
#: `tests/parity/expected_divergences.py` is precisely the mistake this exists
#: to catch, so changing one is a deliberate act, not a fix for a red test.
FROZEN = {
    "component/model": "4fa401be1f01c4dc166eb3f09eb29cbab277f97cd2957f31470c7894998eff2f",
    "component/scripts": "f76d8da20e58e2673aa923a7781c2cdd06846cba9e5857560722ace6501335de",
    "component/parameter": "3dcb6bb81e87d42b6059efc749fcbda2e0d87f9e32b8152f2fbb963e1b396346",
    "component/message": "c55fe83bd0e39bd4e1a4c17ae285ee127631a2e87f73e7bb0bb2db0f82120d06",
}

#: Byte-compiled copies of the very files being hashed. They are derived, not
#: source, and are absent in a fresh checkout -- including them would make the
#: digest depend on whether anything had imported the module yet.
_IGNORED = ("__pycache__",)


def digest_of(directory: str) -> str:
    """A stable digest of every file under ``directory``.

    Paths are sorted and hashed alongside their bytes, so a rename, a deletion
    and an edit all change the result -- hashing the concatenated contents
    alone would miss a rename, and hashing the names alone would miss an edit.
    """
    root = pathlib.Path(directory)
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if any(part in _IGNORED for part in path.parts):
            continue
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def test_the_frozen_legacy_is_unmodified():
    moved = {
        directory: actual
        for directory, expected in FROZEN.items()
        if (actual := digest_of(directory)) != expected
    }
    assert not moved, f"the parity reference was modified: {moved}"


def test_every_frozen_directory_still_exists():
    """Without this, deleting a frozen directory outright would leave
    ``digest_of`` hashing nothing and the test above comparing one empty
    digest to another -- passing, on a reference that is gone."""
    for directory in FROZEN:
        path = pathlib.Path(directory)
        assert path.is_dir(), f"the parity reference is gone: {directory}"
        assert any(path.rglob("*.py")), f"the parity reference is empty: {directory}"


def test_the_reclassify_files_survive():
    """Spec 2 owns these; spec 1 must not take them with the rest of the UI."""
    assert pathlib.Path("component/widget/reclassify").is_dir()
    assert pathlib.Path("component/tile/reclassify_tile.py").is_file()


def test_the_notebook_survives():
    """The Voila notebook is kept for spec 3 to remove together with its
    workflow. It no longer RUNS -- the tiles it builds were retired with the
    rest of the Voila UI -- so this pins only that the file is still here for
    SEPAL's launcher, not that it works."""
    assert pathlib.Path("ui.ipynb").is_file()
