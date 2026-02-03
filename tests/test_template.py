from sidecar.template import extract_variables, fill_template, validate_variables


class TestExtractVariables:
    def test_single_variable(self):
        assert extract_variables("Hello {{name}}") == ["name"]

    def test_multiple_variables(self):
        result = extract_variables("{{greeting}} {{name}}, welcome to {{place}}")
        assert result == ["greeting", "name", "place"]

    def test_no_variables(self):
        assert extract_variables("Hello world") == []

    def test_duplicate_variables(self):
        result = extract_variables("{{name}} and {{name}} again")
        assert result == ["name"]

    def test_spaces_in_braces(self):
        assert extract_variables("{{ name }}") == ["name"]
        assert extract_variables("{{  name  }}") == ["name"]

    def test_underscored_variable(self):
        assert extract_variables("{{first_name}}") == ["first_name"]

    def test_variable_with_numbers(self):
        assert extract_variables("{{item_1}}") == ["item_1"]

    def test_leading_underscore(self):
        assert extract_variables("{{_private}}") == ["_private"]

    def test_preserves_order(self):
        result = extract_variables("{{b}} {{a}} {{c}} {{a}}")
        assert result == ["b", "a", "c"]


class TestFillTemplate:
    def test_simple_fill(self):
        result = fill_template("Hello {{name}}", {"name": "World"})
        assert result == "Hello World"

    def test_multiple_fills(self):
        result = fill_template(
            "{{greeting}} {{name}}", {"greeting": "Hi", "name": "Alice"}
        )
        assert result == "Hi Alice"

    def test_missing_variable_left_unchanged(self):
        result = fill_template("Hello {{name}}", {})
        assert result == "Hello {{name}}"

    def test_no_variables(self):
        result = fill_template("Hello world", {"name": "test"})
        assert result == "Hello world"

    def test_spaces_in_braces(self):
        result = fill_template("Hello {{ name }}", {"name": "World"})
        assert result == "Hello World"

    def test_empty_variables(self):
        result = fill_template("Hello {{name}}", {"name": ""})
        assert result == "Hello "


class TestValidateVariables:
    def test_all_provided(self):
        assert validate_variables("{{name}}", {"name": "Alice"}) == []

    def test_missing_one(self):
        assert validate_variables("{{name}} {{age}}", {"name": "Alice"}) == ["age"]

    def test_missing_all(self):
        result = validate_variables("{{a}} {{b}}", {})
        assert result == ["a", "b"]

    def test_no_variables_needed(self):
        assert validate_variables("Hello world", {}) == []

    def test_extra_variables_ok(self):
        assert validate_variables("{{name}}", {"name": "A", "extra": "B"}) == []
