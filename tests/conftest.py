import os
from pathlib import Path

import pytest


# Optional: make the debug dir visible to tests
@pytest.fixture(scope="session")
def artifacts_dir() -> Path | None:
    path = os.environ.get("MB_ARTIFACTS", "").strip()
    return Path(path) if path else None


@pytest.fixture
def save_artifact(request, artifacts_dir):
    """save_artifact(img, 'name') -> Path | None, and attach into pytest-html."""
    from tests.artifacts import save_png as _save_png

    def _save(img, name: str):
        path = _save_png(img, name)
        # Remember per-test so we can attach in the report
        if path:
            saved = getattr(request.node, "_mb_saved_artifacts", [])
            saved.append(path)
            request.node._mb_saved_artifacts = saved
        return path

    return _save


# Hook: attach images to the pytest-html report row for this test
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    from pytest_html import (
        extras,
    )  # safe even if plugin not used (imported only when hook runs)

    outcome = yield
    rep = outcome.get_result()
    # carry over any existing extras
    extra = getattr(rep, "extra", [])
    for path in getattr(item, "_mb_saved_artifacts", []):
        extra.append(extras.image(str(path), path.name))
    rep.extra = extra
