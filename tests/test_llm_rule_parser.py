import json

import pytest

from src.service.llm_rule_parser import LlmRuleParser, extract_json_object


def test_llm_parser_uses_local_fallback_when_unconfigured():
    parser = LlmRuleParser(api_key="", base_url="")
    fallback = {"template_id": "JJMB1", "status": "draft", "font_options": ["F1"]}

    draft = parser.parse(
        kind="template_rule",
        natural_text="Font Options 为 F1",
        context={},
        fallback=fallback,
    )

    assert draft["template_id"] == "JJMB1"
    assert draft["font_options"] == ["F1"]
    assert draft["parser"] == {"source": "local", "llm_configured": False}


def test_llm_parser_required_mode_rejects_unconfigured():
    parser = LlmRuleParser(api_key="", base_url="")

    with pytest.raises(RuntimeError, match="LLM 规则编译未配置"):
        parser.parse(
            kind="template_rule",
            natural_text="Font Options 为 F1",
            context={},
            fallback={"template_id": "JJMB1"},
            require_llm=True,
        )


def test_llm_parser_required_mode_returns_llm_source(monkeypatch):
    parser = LlmRuleParser(api_key="key", base_url="https://example.test/v1")
    monkeypatch.setattr(parser, "_call_llm", lambda **kwargs: {"font_options": ["F1", "F2"]})

    draft = parser.parse(
        kind="template_rule",
        natural_text="Font Options 为 F1-F2",
        context={},
        fallback={"template_id": "JJMB1", "font_options": ["F1"]},
        require_llm=True,
    )

    assert draft["font_options"] == ["F1", "F2"]
    assert draft["parser"] == {"source": "llm", "llm_configured": True}


def test_llm_parser_can_force_local_fallback_when_configured(monkeypatch):
    parser = LlmRuleParser(api_key="key", base_url="https://example.test/v1")
    monkeypatch.setattr(parser, "_call_llm", lambda **kwargs: pytest.fail("LLM should not be called"))

    draft = parser.parse(
        kind="template_rule",
        natural_text="Font Options 为 F1",
        context={},
        fallback={"template_id": "JJMB1", "font_options": ["F1"]},
        allow_llm=False,
    )

    assert draft["font_options"] == ["F1"]
    assert draft["parser"] == {"source": "local", "llm_configured": True}


def test_llm_parser_normalizes_object_option_arrays(monkeypatch):
    parser = LlmRuleParser(api_key="key", base_url="https://example.test/v1")
    monkeypatch.setattr(
        parser,
        "_call_llm",
        lambda **kwargs: {
            "font_options": [{"id": "F1"}, {"name": "F2"}, {"value": "F3"}],
            "style_options": [{"code": "Style1"}, {"option": "Style2"}],
            "design_font_options": [{"font_option": "F10"}, {"key": "F11"}],
            "design_options": {
                "design_font_options": [{"id": "F10"}, {"id": "F12"}],
                "text_slots_mapping": {"F10": {"text1": "Text1"}},
            },
        },
    )

    draft = parser.parse(
        kind="template_rule",
        natural_text="Font Options 为 F1-F3，F10-F12 为设计",
        context={},
        fallback={"template_id": "JJMB1", "font_options": ["F1"]},
        require_llm=True,
    )

    assert draft["font_options"] == ["F1", "F2", "F3"]
    assert draft["style_options"] == ["Style1", "Style2"]
    assert draft["design_font_options"] == ["F10", "F11"]
    assert draft["design_options"]["design_font_options"] == ["F10", "F12"]
    assert draft["design_options"]["text_slots_mapping"] == {"F10": {"text1": "Text1"}}


def test_extract_json_object_from_markdown_response():
    payload = extract_json_object(
        """```json
        {"status":"draft","capabilities":["text_fit_box"]}
        ```"""
    )

    assert payload["status"] == "draft"
    assert payload["capabilities"] == ["text_fit_box"]


def test_llm_special_rule_request_enables_json_output_and_safe_ast_prompt(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"{\\"rules\\":[]}"}}]}'

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("src.service.llm_rule_parser.urllib.request.urlopen", fake_urlopen)
    parser = LlmRuleParser(api_key="key", base_url="https://api.deepseek.com", model="deepseek-chat")

    parser._call_llm(kind="template_special_rules", natural_text="Name 奇数红色偶数白色", context={})

    payload = json.loads(captured["request"].data.decode("utf-8"))
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["model"] == "deepseek-chat"
    assert "不得返回脚本" in payload["messages"][0]["content"]
    assert captured["request"].full_url.endswith("/v1/chat/completions")
