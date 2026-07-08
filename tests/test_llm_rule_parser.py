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


def test_extract_json_object_from_markdown_response():
    payload = extract_json_object(
        """```json
        {"status":"draft","capabilities":["text_fit_box"]}
        ```"""
    )

    assert payload["status"] == "draft"
    assert payload["capabilities"] == ["text_fit_box"]
