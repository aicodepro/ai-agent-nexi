def test_context_respects_token_budget():
    from engine.context_budget_manager import build_context

    context = build_context("word " * 500, max_chars=1000, max_tokens=20)

    estimated_tokens = 0 if not context else len(context) // 4 + 1
    assert estimated_tokens <= 20
