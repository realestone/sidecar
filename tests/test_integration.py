import json

import pytest

from sidecar.errors import ErrorCode, SidecarError
from sidecar.models import Prompt
from sidecar.storage import Storage
from sidecar.template import extract_variables, fill_template, validate_variables
from sidecar.tools.prompts import register_tools


class FakeMCP:
    """Minimal stand-in for FastMCP to capture registered tools."""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorator


@pytest.fixture
def env(tmp_path):
    storage = Storage(db_path=tmp_path / "test.db")
    mcp = FakeMCP()
    register_tools(mcp, storage)
    return mcp.tools, storage


class TestPromptSave:
    def test_save_basic(self, env):
        tools, _ = env
        result = json.loads(tools["prompt_save"](name="hello", content="Hello world"))
        assert result["status"] == "saved"
        assert result["name"] == "hello"
        assert result["variables"] == []
        assert result["category"] == "general"

    def test_save_with_variables(self, env):
        tools, _ = env
        result = json.loads(
            tools["prompt_save"](name="greet", content="Hello {{name}}, welcome to {{place}}")
        )
        assert result["variables"] == ["name", "place"]

    def test_save_with_category(self, env):
        tools, _ = env
        result = json.loads(
            tools["prompt_save"](name="formal", content="Dear Sir", category="email")
        )
        assert result["category"] == "email"

    def test_save_duplicate_raises(self, env):
        tools, _ = env
        tools["prompt_save"](name="dup", content="a")
        with pytest.raises(SidecarError) as exc_info:
            tools["prompt_save"](name="dup", content="b")
        assert exc_info.value.code == ErrorCode.PROMPT_ALREADY_EXISTS

    def test_save_invalid_name(self, env):
        tools, _ = env
        with pytest.raises(SidecarError) as exc_info:
            tools["prompt_save"](name="BAD NAME!", content="x")
        assert exc_info.value.code == ErrorCode.INVALID_NAME


class TestPromptGet:
    def test_get_existing(self, env):
        tools, _ = env
        tools["prompt_save"](name="fetch-me", content="I am here")
        result = json.loads(tools["prompt_get"](name="fetch-me"))
        assert result["name"] == "fetch-me"
        assert result["content"] == "I am here"

    def test_get_nonexistent(self, env):
        tools, _ = env
        with pytest.raises(SidecarError) as exc_info:
            tools["prompt_get"](name="ghost")
        assert exc_info.value.code == ErrorCode.PROMPT_NOT_FOUND


class TestPromptUse:
    def test_use_with_variables(self, env):
        tools, _ = env
        tools["prompt_save"](name="greet", content="Hello {{name}}")
        result = json.loads(
            tools["prompt_use"](name="greet", variables={"name": "Alice"})
        )
        assert result["filled"] == "Hello Alice"
        assert result["use_count"] == 1

    def test_use_static_prompt(self, env):
        tools, _ = env
        tools["prompt_save"](name="static", content="No vars here")
        result = json.loads(tools["prompt_use"](name="static"))
        assert result["filled"] == "No vars here"
        assert result["use_count"] == 1

    def test_use_static_with_empty_dict(self, env):
        tools, _ = env
        tools["prompt_save"](name="static2", content="Still no vars")
        result = json.loads(tools["prompt_use"](name="static2", variables={}))
        assert result["filled"] == "Still no vars"

    def test_use_missing_variables(self, env):
        tools, _ = env
        tools["prompt_save"](name="needs-vars", content="{{a}} and {{b}}")
        with pytest.raises(SidecarError) as exc_info:
            tools["prompt_use"](name="needs-vars", variables={"a": "x"})
        assert exc_info.value.code == ErrorCode.MISSING_VARIABLES

    def test_use_increments_count(self, env):
        tools, _ = env
        tools["prompt_save"](name="counter", content="count me")
        tools["prompt_use"](name="counter")
        tools["prompt_use"](name="counter")
        result = json.loads(tools["prompt_use"](name="counter"))
        assert result["use_count"] == 3

    def test_use_nonexistent(self, env):
        tools, _ = env
        with pytest.raises(SidecarError) as exc_info:
            tools["prompt_use"](name="nope")
        assert exc_info.value.code == ErrorCode.PROMPT_NOT_FOUND


class TestPromptList:
    def test_list_empty(self, env):
        tools, _ = env
        result = json.loads(tools["prompt_list"]())
        assert result == []

    def test_list_all(self, env):
        tools, _ = env
        tools["prompt_save"](name="a", content="x")
        tools["prompt_save"](name="b", content="y")
        result = json.loads(tools["prompt_list"]())
        assert len(result) == 2

    def test_list_by_category(self, env):
        tools, _ = env
        tools["prompt_save"](name="a", content="x", category="cat1")
        tools["prompt_save"](name="b", content="y", category="cat2")
        result = json.loads(tools["prompt_list"](category="cat1"))
        assert len(result) == 1
        assert result[0]["name"] == "a"


class TestPromptRecent:
    def test_recent(self, env):
        tools, _ = env
        tools["prompt_save"](name="old", content="old")
        tools["prompt_save"](name="new", content="new")
        result = json.loads(tools["prompt_recent"]())
        assert result[0]["name"] == "new"

    def test_recent_limit(self, env):
        tools, _ = env
        for i in range(5):
            tools["prompt_save"](name=f"p{i}", content=f"c{i}")
        result = json.loads(tools["prompt_recent"](limit=2))
        assert len(result) == 2


class TestPromptSearch:
    def test_search_by_name(self, env):
        tools, _ = env
        tools["prompt_save"](name="greeting-formal", content="Dear Sir")
        tools["prompt_save"](name="goodbye", content="Farewell")
        result = json.loads(tools["prompt_search"](query="greeting"))
        assert len(result) == 1
        assert result[0]["name"] == "greeting-formal"

    def test_search_by_content(self, env):
        tools, _ = env
        tools["prompt_save"](name="a", content="Hello world")
        tools["prompt_save"](name="b", content="Goodbye world")
        result = json.loads(tools["prompt_search"](query="Hello"))
        assert len(result) == 1

    def test_search_no_results(self, env):
        tools, _ = env
        result = json.loads(tools["prompt_search"](query="zzzzz"))
        assert result == []


class TestPromptDelete:
    def test_delete(self, env):
        tools, _ = env
        tools["prompt_save"](name="doomed", content="bye")
        result = json.loads(tools["prompt_delete"](name="doomed"))
        assert result["status"] == "deleted"
        with pytest.raises(SidecarError):
            tools["prompt_get"](name="doomed")

    def test_delete_nonexistent(self, env):
        tools, _ = env
        with pytest.raises(SidecarError) as exc_info:
            tools["prompt_delete"](name="ghost")
        assert exc_info.value.code == ErrorCode.PROMPT_NOT_FOUND
