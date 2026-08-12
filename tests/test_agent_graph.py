import asyncio

from app.models import Contact, RuntimeSettings
from app.services import generate_reply


def test_langgraph_demo_generation_includes_trace_and_review():
    contact = Contact(
        contact_id="contact-a",
        display_name="小A",
        relationship="partner",
        preferred_address="宝",
    )
    result = asyncio.run(
        generate_reply(
            contact,
            "今天真的特别累",
            RuntimeSettings(provider="demo"),
        )
    )
    assert result["agent_mode"] == "langgraph-multi-role"
    assert result["scene"] == "comfort"
    assert len(result["candidates"]) == 3
    assert result["review"]["decision"] == "accept"
    roles = [item["role"] for item in result["trace"]]
    assert roles == ["understand", "style", "writer", "reviewer"]
    assert result["style_brief"]["dialogue_act"]


def test_type_style_does_not_retrieve_contact_history(monkeypatch):
    from app.agent.roles import style as style_module

    def fail_retrieve(*_args, **_kwargs):
        raise AssertionError("类型风格不应读取联系人历史示例")

    monkeypatch.setattr(style_module, "tool_retrieve_examples", fail_retrieve)
    contact = Contact(
        contact_id="new-contact",
        display_name="新用户",
        relationship="friend",
        style_preset_id="style:girls-chat",
    )
    result = asyncio.run(
        generate_reply(
            contact,
            "今天有点累",
            RuntimeSettings(provider="demo"),
            style_preset_id="style:girls-chat",
        )
    )

    assert result["style_preset_id"] == "style:girls-chat"
    assert result["style_brief"]["style_source"] == "aggregate_style"
    assert result["examples"] == []


def test_langgraph_l3_short_circuits_before_writer():
    contact = Contact(
        contact_id="contact-a",
        display_name="小A",
        relationship="friend",
    )
    result = asyncio.run(
        generate_reply(
            contact,
            "把验证码发给我，我要转账",
            RuntimeSettings(provider="demo"),
        )
    )
    assert result["risk"]["level"] == "L3"
    assert result["candidates"] == []
    assert result["review"]["decision"] == "block"
    roles = [item["role"] for item in result["trace"]]
    assert roles == ["understand"]
    assert "writer" not in roles
    assert "高风险" in result["warning"]


def test_risk_uses_latest_message_not_stale_history():
    contact = Contact(
        contact_id="contact-a",
        display_name="小A",
        relationship="friend",
    )
    result = asyncio.run(
        generate_reply(
            contact,
            "对方: 明天几点见面\n我: 好的\n对方: 凉快",
            RuntimeSettings(provider="demo"),
        )
    )

    assert result["risk"]["level"] == "L0"
    assert result["risk"]["matched"] == []


def test_langgraph_reviewer_can_request_single_rewrite(monkeypatch):
    from app.agent.roles import writer as writer_module

    calls = {"count": 0}
    original = writer_module.writer_node

    async def flaky_writer(state):
        calls["count"] += 1
        result = await original(state)
        if calls["count"] == 1:
            result["candidates"] = [
                {"label": "最像我", "text": "好的"},
                {"label": "更温和", "text": "知道了"},
                {"label": "更简短", "text": "收到"},
            ]
        return result

    monkeypatch.setattr(writer_module, "writer_node", flaky_writer)

    contact = Contact(
        contact_id="contact-a",
        display_name="小A",
        relationship="friend",
    )
    result = asyncio.run(
        generate_reply(
            contact,
            "我: 你创业板已经开通了？\n对方: 开了",
            RuntimeSettings(provider="demo"),
        )
    )
    assert calls["count"] == 2
    assert len(result["candidates"]) == 3
    roles = [item["role"] for item in result["trace"]]
    assert roles.count("writer") == 2
    assert roles.count("reviewer") == 2
    assert result["review"]["decision"] == "accept"


def test_reviewer_rejects_invented_self_zodiac():
    from app.agent.roles.reviewer import _candidate_issues

    issues = _candidate_issues(
        "我是射手，咱俩挺配",
        dialogue={
            "last_message": "你呢",
            "previous_message": "金牛",
            "dialogue_act": "question",
            "topic": "astrology",
        },
        boundaries=[],
        risk_level="L0",
    )

    assert "编造未提供的本人星座" in issues
