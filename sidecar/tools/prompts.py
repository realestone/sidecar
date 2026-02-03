import json
import re

from ..errors import SidecarError
from ..models import Prompt
from ..storage import Storage
from ..template import extract_variables, fill_template, validate_variables

NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _validate_name(name: str) -> None:
    if not NAME_PATTERN.match(name):
        raise SidecarError.invalid_name(name)


def register_tools(mcp, storage: Storage) -> None:
    @mcp.tool()
    def prompt_save(
        name: str,
        content: str,
        category: str = "general",
    ) -> str:
        """Save a new prompt template. Variables use {{variable_name}} syntax."""
        _validate_name(name)
        variables = extract_variables(content)
        prompt = Prompt(name=name, content=content, category=category, variables=variables)
        storage.save_prompt(prompt)
        result = {
            "status": "saved",
            "name": prompt.name,
            "variables": prompt.variables,
            "category": prompt.category,
        }
        return json.dumps(result)

    @mcp.tool()
    def prompt_get(name: str) -> str:
        """Get a prompt template by name."""
        prompt = storage.get_prompt(name)
        return json.dumps(prompt.to_dict())

    @mcp.tool()
    def prompt_use(
        name: str,
        variables: dict[str, str] | None = None,
    ) -> str:
        """Use a prompt: fill in variables and return the expanded text. Increments use count."""
        prompt = storage.get_prompt(name)
        vars_dict = variables or {}

        if prompt.variables:
            missing = validate_variables(prompt.content, vars_dict)
            if missing:
                raise SidecarError.missing_variables(missing)

        filled = fill_template(prompt.content, vars_dict)
        storage.record_use(name)

        result = {
            "name": prompt.name,
            "filled": filled,
            "use_count": prompt.use_count + 1,
        }
        return json.dumps(result)

    @mcp.tool()
    def prompt_list(category: str | None = None) -> str:
        """List all prompts, optionally filtered by category."""
        prompts = storage.list_prompts(category)
        result = [
            {
                "name": p.name,
                "category": p.category,
                "variables": p.variables,
                "use_count": p.use_count,
            }
            for p in prompts
        ]
        return json.dumps(result)

    @mcp.tool()
    def prompt_recent(limit: int = 10) -> str:
        """List recently used/updated prompts."""
        prompts = storage.recent_prompts(limit)
        result = [
            {
                "name": p.name,
                "category": p.category,
                "use_count": p.use_count,
                "updated_at": p.updated_at,
            }
            for p in prompts
        ]
        return json.dumps(result)

    @mcp.tool()
    def prompt_search(query: str) -> str:
        """Search prompts by name, content, or category."""
        prompts = storage.search_prompts(query)
        result = [
            {
                "name": p.name,
                "category": p.category,
                "variables": p.variables,
                "use_count": p.use_count,
            }
            for p in prompts
        ]
        return json.dumps(result)

    @mcp.tool()
    def prompt_delete(name: str) -> str:
        """Delete a prompt by name."""
        prompt = storage.delete_prompt(name)
        result = {"status": "deleted", "name": prompt.name}
        return json.dumps(result)
