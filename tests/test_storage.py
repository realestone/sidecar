import tempfile
from pathlib import Path

import pytest

from sidecar.errors import ErrorCode, SidecarError
from sidecar.models import Prompt
from sidecar.storage import Storage


@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "test.db"
    return Storage(db_path=db_path)


@pytest.fixture
def sample_prompt():
    return Prompt(
        name="test-prompt",
        content="Hello {{name}}, welcome to {{place}}",
        category="greeting",
        variables=["name", "place"],
    )


class TestSaveAndGet:
    def test_save_and_get(self, storage, sample_prompt):
        storage.save_prompt(sample_prompt)
        result = storage.get_prompt("test-prompt")
        assert result.name == "test-prompt"
        assert result.content == "Hello {{name}}, welcome to {{place}}"
        assert result.category == "greeting"
        assert result.variables == ["name", "place"]
        assert result.use_count == 0

    def test_save_duplicate_raises(self, storage, sample_prompt):
        storage.save_prompt(sample_prompt)
        with pytest.raises(SidecarError) as exc_info:
            storage.save_prompt(sample_prompt)
        assert exc_info.value.code == ErrorCode.PROMPT_ALREADY_EXISTS

    def test_get_nonexistent_raises(self, storage):
        with pytest.raises(SidecarError) as exc_info:
            storage.get_prompt("nonexistent")
        assert exc_info.value.code == ErrorCode.PROMPT_NOT_FOUND


class TestDelete:
    def test_delete(self, storage, sample_prompt):
        storage.save_prompt(sample_prompt)
        deleted = storage.delete_prompt("test-prompt")
        assert deleted.name == "test-prompt"
        with pytest.raises(SidecarError) as exc_info:
            storage.get_prompt("test-prompt")
        assert exc_info.value.code == ErrorCode.PROMPT_NOT_FOUND

    def test_delete_nonexistent_raises(self, storage):
        with pytest.raises(SidecarError) as exc_info:
            storage.delete_prompt("nonexistent")
        assert exc_info.value.code == ErrorCode.PROMPT_NOT_FOUND


class TestList:
    def test_list_empty(self, storage):
        assert storage.list_prompts() == []

    def test_list_all(self, storage):
        storage.save_prompt(Prompt(name="alpha", content="a"))
        storage.save_prompt(Prompt(name="beta", content="b"))
        result = storage.list_prompts()
        assert len(result) == 2
        assert result[0].name == "alpha"
        assert result[1].name == "beta"

    def test_list_by_category(self, storage):
        storage.save_prompt(Prompt(name="a", content="x", category="cat1"))
        storage.save_prompt(Prompt(name="b", content="y", category="cat2"))
        result = storage.list_prompts(category="cat1")
        assert len(result) == 1
        assert result[0].name == "a"


class TestSearch:
    def test_search_by_name(self, storage):
        storage.save_prompt(Prompt(name="greeting-formal", content="Dear Sir"))
        storage.save_prompt(Prompt(name="goodbye", content="Farewell"))
        result = storage.search_prompts("greeting")
        assert len(result) == 1
        assert result[0].name == "greeting-formal"

    def test_search_by_content(self, storage):
        storage.save_prompt(Prompt(name="a", content="Hello world"))
        storage.save_prompt(Prompt(name="b", content="Goodbye world"))
        result = storage.search_prompts("Hello")
        assert len(result) == 1
        assert result[0].name == "a"

    def test_search_no_results(self, storage):
        storage.save_prompt(Prompt(name="a", content="b"))
        assert storage.search_prompts("zzzzz") == []


class TestRecent:
    def test_recent_order(self, storage):
        storage.save_prompt(Prompt(name="old", content="old"))
        storage.save_prompt(Prompt(name="new", content="new"))
        result = storage.recent_prompts(limit=10)
        assert result[0].name == "new"

    def test_recent_limit(self, storage):
        for i in range(5):
            storage.save_prompt(Prompt(name=f"p{i}", content=f"content {i}"))
        result = storage.recent_prompts(limit=2)
        assert len(result) == 2


class TestRecordUse:
    def test_record_use_increments(self, storage, sample_prompt):
        storage.save_prompt(sample_prompt)
        result = storage.record_use("test-prompt")
        assert result.use_count == 1
        result = storage.record_use("test-prompt")
        assert result.use_count == 2

    def test_record_use_updates_timestamp(self, storage, sample_prompt):
        storage.save_prompt(sample_prompt)
        original = storage.get_prompt("test-prompt")
        result = storage.record_use("test-prompt")
        assert result.updated_at >= original.updated_at


class TestSchemaVersion:
    def test_schema_version_stored(self, tmp_path):
        db_path = tmp_path / "test.db"
        s = Storage(db_path=db_path)
        row = s._conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        assert row["value"] == "1"

    def test_schema_version_mismatch(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "bad.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', '999')"
        )
        conn.execute("""
            CREATE TABLE prompts (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                variables TEXT NOT NULL DEFAULT '[]',
                use_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                record_type TEXT NOT NULL DEFAULT 'prompt',
                schema_version INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.commit()
        conn.close()

        with pytest.raises(SidecarError) as exc_info:
            Storage(db_path=db_path)
        assert exc_info.value.code == ErrorCode.SCHEMA_VERSION


class TestPersistence:
    def test_data_persists_across_instances(self, tmp_path):
        db_path = tmp_path / "persist.db"
        s1 = Storage(db_path=db_path)
        s1.save_prompt(Prompt(name="persistent", content="I persist"))

        s2 = Storage(db_path=db_path)
        result = s2.get_prompt("persistent")
        assert result.content == "I persist"
