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


def test_extract_json_object_from_markdown_response():
    payload = extract_json_object(
        """```json
        {"status":"draft","capabilities":["text_fit_box"]}
        ```"""
    )

    assert payload["status"] == "draft"
    assert payload["capabilities"] == ["text_fit_box"]
