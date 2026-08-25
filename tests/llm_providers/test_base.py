import pytest

from llm_providers.base import parse_evaluation_json


def test_parse_evaluation_json_plain():
    text = '{"rating": "Level 2", "critique": "c", "recommendations": "r"}'
    assert parse_evaluation_json(text) == {"rating": "Level 2", "critique": "c", "recommendations": "r"}


def test_parse_evaluation_json_fenced_with_language():
    text = '```json\n{"rating": "Level 3", "critique": "c", "recommendations": "r"}\n```'
    assert parse_evaluation_json(text)["rating"] == "Level 3"


def test_parse_evaluation_json_fenced_without_language():
    text = '```\n{"rating": "Level 1", "critique": "c", "recommendations": "r"}\n```'
    assert parse_evaluation_json(text)["rating"] == "Level 1"


def test_parse_evaluation_json_invalid_raises_value_error():
    with pytest.raises(ValueError):
        parse_evaluation_json("this is not json")


def test_parse_evaluation_json_non_dict_raises_value_error():
    with pytest.raises(ValueError):
        parse_evaluation_json("[1, 2, 3]")
