import pytest
import responses

from llm import client as llm


class TestParseJson:
    def test_plain_object(self):
        assert llm._parse_json('{"a": 1}') == {"a": 1}

    def test_fenced_block(self):
        assert llm._parse_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_unlabelled_fence(self):
        assert llm._parse_json('```\n{"a": 1}\n```') == {"a": 1}

    def test_leading_and_trailing_prose(self):
        assert llm._parse_json('Sure thing! {"a": 1} Let me know.') == {"a": 1}

    def test_array_at_top_level(self):
        assert llm._parse_json("[1, 2, 3]") == [1, 2, 3]

    def test_nested_braces(self):
        assert llm._parse_json('{"a": {"b": [1, {"c": 2}]}}') == {"a": {"b": [1, {"c": 2}]}}

    def test_braces_inside_strings_do_not_confuse_the_scan(self):
        assert llm._parse_json('{"a": "} not the end {"}') == {"a": "} not the end {"}

    def test_escaped_quote_inside_string(self):
        assert llm._parse_json('{"a": "say \\"hi\\""}') == {"a": 'say "hi"'}

    def test_no_json_at_all(self):
        with pytest.raises(llm.LLMBadOutput):
            llm._parse_json("I am afraid I cannot help with that.")

    def test_truncated_json(self):
        with pytest.raises(llm.LLMBadOutput):
            llm._parse_json('{"a": 1')

    def test_malformed_json(self):
        with pytest.raises(llm.LLMBadOutput):
            llm._parse_json("{'a': 1,}")


def accept_anything(payload):
    return payload


def test_missing_api_key_is_unavailable_not_a_crash(settings):
    settings.OPENROUTER_API_KEY = ""
    with pytest.raises(llm.LLMUnavailable):
        llm.complete_json("sys", "user", accept_anything)


@responses.activate
def test_http_error_becomes_unavailable(settings):
    settings.OPENROUTER_API_KEY = "k"
    responses.add(
        responses.POST,
        "https://openrouter.ai/api/v1/chat/completions",
        body="upstream exploded",
        status=500,
    )
    with pytest.raises(llm.LLMUnavailable):
        llm.complete_json("sys", "user", accept_anything)


@responses.activate
def test_rate_limit_becomes_unavailable(settings):
    settings.OPENROUTER_API_KEY = "k"
    responses.add(
        responses.POST,
        "https://openrouter.ai/api/v1/chat/completions",
        json={"error": "slow down"},
        status=429,
    )
    with pytest.raises(llm.LLMUnavailable):
        llm.complete_json("sys", "user", accept_anything)


@responses.activate
def test_error_tunnelled_inside_a_200_response(settings):
    settings.OPENROUTER_API_KEY = "k"
    responses.add(
        responses.POST,
        "https://openrouter.ai/api/v1/chat/completions",
        json={"error": {"message": "no credits"}},
        status=200,
    )
    with pytest.raises(llm.LLMUnavailable):
        llm.complete_json("sys", "user", accept_anything)


@responses.activate
def test_unexpected_response_shape(settings):
    settings.OPENROUTER_API_KEY = "k"
    responses.add(
        responses.POST,
        "https://openrouter.ai/api/v1/chat/completions",
        json={"choices": [{}]},
        status=200,
    )
    with pytest.raises(llm.LLMUnavailable):
        llm.complete_json("sys", "user", accept_anything)


def _reply(content):
    return {"choices": [{"message": {"content": content}}], "usage": {}}


@responses.activate
def test_retries_exactly_once_then_gives_up(settings):
    settings.OPENROUTER_API_KEY = "k"
    url = "https://openrouter.ai/api/v1/chat/completions"
    responses.add(responses.POST, url, json=_reply("nope"), status=200)
    responses.add(responses.POST, url, json=_reply("still nope"), status=200)
    responses.add(responses.POST, url, json=_reply('{"ok": true}'), status=200)

    with pytest.raises(llm.LLMBadOutput):
        llm.complete_json("sys", "user", accept_anything)

    assert len(responses.calls) == 2


@responses.activate
def test_validator_rejection_triggers_the_retry(settings):
    settings.OPENROUTER_API_KEY = "k"
    url = "https://openrouter.ai/api/v1/chat/completions"
    responses.add(responses.POST, url, json=_reply('{"wrong": 1}'), status=200)
    responses.add(responses.POST, url, json=_reply('{"right": 1}'), status=200)

    def needs_right_key(payload):
        if "right" not in payload:
            raise llm.LLMBadOutput("missing key")
        return payload

    assert llm.complete_json("sys", "user", needs_right_key) == {"right": 1}
    assert len(responses.calls) == 2
