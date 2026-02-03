import re

VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")


def extract_variables(template: str) -> list[str]:
    """Extract unique variable names from a template string, in order of first appearance."""
    seen: set[str] = set()
    result: list[str] = []
    for match in VARIABLE_PATTERN.finditer(template):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def fill_template(template: str, variables: dict[str, str]) -> str:
    """Replace all {{var}} placeholders with values from the variables dict."""

    def replacer(match: re.Match) -> str:
        name = match.group(1)
        return variables.get(name, match.group(0))

    return VARIABLE_PATTERN.sub(replacer, template)


def validate_variables(template: str, variables: dict[str, str]) -> list[str]:
    """Return list of variable names required by the template but missing from variables."""
    required = extract_variables(template)
    return [v for v in required if v not in variables]
