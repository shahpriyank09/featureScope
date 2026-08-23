from prism.integrations.greptile import _tool_error_message


def test_repository_not_found_tool_text_is_an_error() -> None:
    message = "Repository not found: example/repo on github"

    assert _tool_error_message({"text": message}) == message


def test_normal_tool_text_is_not_an_error() -> None:
    assert _tool_error_message({"text": "Review completed."}) is None
