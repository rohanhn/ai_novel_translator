import pytest

from novel_translator.config import Settings
from novel_translator.container import build_container, get_container


@pytest.fixture
def container(tmp_path):
    return build_container(
        Settings(provider="echo", db_path=tmp_path / "test.db", max_segment_chars=50)
    )


@pytest.fixture
def sample_txt(tmp_path):
    p = tmp_path / "sample.txt"
    p.write_text(
        "第一章 少年\n林动站在山上。\n他看着远方。\n\n第二章 修炼\n林动开始修炼。\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def api_client(container):
    from fastapi.testclient import TestClient

    from novel_translator.interfaces.api.app import app

    app.dependency_overrides[get_container] = lambda: container
    yield TestClient(app)
    app.dependency_overrides.clear()
