from app.wechat_bridge import (
    _find_chat_result_candidates,
    _find_exact_chat_result,
    _find_message_editor,
    _find_search_edit,
    _find_web_search_document,
    _window_point,
)
import app.wechat_bridge as wechat_bridge
import pytest


class FakeRect:
    def __init__(self, left, top, right, bottom):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class FakeControl:
    def __init__(
        self,
        name,
        control_type,
        rect,
        *,
        children=None,
    ):
        self.Name = name
        self.ControlTypeName = control_type
        self.BoundingRectangle = FakeRect(*rect)
        self._children = children or []
        self._parent = None
        self._next = None
        for index, child in enumerate(self._children):
            child._parent = self
            if index + 1 < len(self._children):
                child._next = self._children[index + 1]

    def GetFirstChildControl(self):
        return self._children[0] if self._children else None

    def GetNextSiblingControl(self):
        return self._next

    def GetParentControl(self):
        return self._parent

    def SetFocus(self):
        pass

    def Click(self, waitTime=0):
        pass


class FakeWindow(FakeControl):
    def __init__(self, name, class_name):
        super().__init__(name, "WindowControl", (0, 0, 1000, 800))
        self.ClassName = class_name
        self.ProcessId = 1
        self.NativeWindowHandle = 1001


class FakeRoot:
    def __init__(self, children):
        self._children = children

    def GetChildren(self):
        return self._children


class FakeAutomation:
    def __init__(self, children):
        self._root = FakeRoot(children)

    def GetRootControl(self):
        return self._root


def test_finds_upper_left_search_edit_and_lower_right_editor():
    search = FakeControl("", "EditControl", (20, 20, 300, 60))
    editor = FakeControl("", "DocumentControl", (350, 500, 950, 740))
    window = FakeControl(
        "微信",
        "WindowControl",
        (0, 0, 1000, 800),
        children=[search, editor],
    )

    assert _find_search_edit(window) is search
    assert _find_message_editor(window, search) is editor


def test_exact_chat_result_excludes_web_search_entry():
    search = FakeControl("搜索", "EditControl", (20, 20, 300, 60))
    web_text = FakeControl("鲱鱼", "TextControl", (30, 90, 180, 115))
    web_result = FakeControl(
        "搜一搜 鲱鱼",
        "ListItemControl",
        (20, 70, 300, 130),
        children=[web_text],
    )
    chat_text = FakeControl("鲱鱼", "TextControl", (30, 160, 180, 185))
    chat_result = FakeControl(
        "联系人",
        "ListItemControl",
        (20, 140, 300, 205),
        children=[chat_text],
    )
    window = FakeControl(
        "微信",
        "WindowControl",
        (0, 0, 1000, 800),
        children=[search, web_result, chat_result],
    )

    assert _find_exact_chat_result(window, "鲱鱼", search) is chat_result


def test_only_web_search_result_returns_none():
    search = FakeControl("搜索", "EditControl", (20, 20, 300, 60))
    web_text = FakeControl("鲱鱼", "TextControl", (30, 90, 180, 115))
    web_result = FakeControl(
        "网页搜索 鲱鱼",
        "ListItemControl",
        (20, 70, 300, 130),
        children=[web_text],
    )
    window = FakeControl(
        "微信",
        "WindowControl",
        (0, 0, 1000, 800),
        children=[search, web_result],
    )

    assert _find_exact_chat_result(window, "鲱鱼", search) is None


def test_chat_result_candidates_skip_web_search_and_keep_visible_order():
    search = FakeControl("搜索", "EditControl", (20, 20, 300, 60))
    web_text = FakeControl("鲱鱼", "TextControl", (30, 90, 180, 115))
    web_result = FakeControl(
        "搜一搜 鲱鱼",
        "ListItemControl",
        (20, 70, 300, 130),
        children=[web_text],
    )
    first_chat = FakeControl("联系人", "ListItemControl", (20, 140, 300, 205))
    second_chat = FakeControl("群聊", "ListItemControl", (20, 215, 300, 280))
    window = FakeControl(
        "微信",
        "WindowControl",
        (0, 0, 1000, 800),
        children=[search, web_result, first_chat, second_chat],
    )

    assert _find_chat_result_candidates(window, search) == [first_chat, second_chat]


def test_web_search_document_is_detected():
    document = FakeControl(
        "辉股神 - 搜一搜",
        "DocumentControl",
        (0, 40, 1000, 800),
    )
    window = FakeControl(
        "微信",
        "WindowControl",
        (0, 0, 1000, 800),
        children=[document],
    )

    assert _find_web_search_document(window) is document


def test_normal_chat_document_is_not_web_search():
    document = FakeControl(
        "辉股神",
        "DocumentControl",
        (0, 40, 1000, 800),
    )
    window = FakeControl(
        "微信",
        "WindowControl",
        (0, 0, 1000, 800),
        children=[document],
    )

    assert _find_web_search_document(window) is None


def test_window_point_uses_window_relative_coordinates():
    window = FakeControl(
        "微信",
        "WindowControl",
        (100, 200, 1100, 1000),
    )

    assert _window_point(window, 0.15, 0.08) == (250, 264)
    assert _window_point(window, 0.64, 0.86) == (740, 888)


def test_rendered_send_stops_before_message_input_when_ocr_title_mismatches(
    monkeypatch,
):
    window = FakeWindow("微信", "Qt51514QWindowIcon")
    pasted = []
    clicked = []
    monkeypatch.setattr(wechat_bridge, "_leave_web_search_page", lambda _window: True)
    monkeypatch.setattr(
        wechat_bridge, "_click_screen_point", lambda *point: clicked.append(point)
    )
    monkeypatch.setattr(wechat_bridge, "_select_all", lambda: None)
    monkeypatch.setattr(wechat_bridge, "_paste_text", lambda text: pasted.append(text))
    monkeypatch.setattr(wechat_bridge, "_press_down", lambda: None)
    monkeypatch.setattr(wechat_bridge, "_press_enter", lambda: None)
    monkeypatch.setattr(wechat_bridge, "_find_web_search_document", lambda _w: None)
    monkeypatch.setattr(
        wechat_bridge, "_read_rendered_chat_title", lambda _window: "其他联系人"
    )
    monkeypatch.setattr(wechat_bridge.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="OCR 标题验证失败"):
        wechat_bridge._send_via_rendered_window(window, "鲱鱼", "测试草稿")

    assert pasted == ["鲱鱼"]
    assert len(clicked) == 1


def test_rendered_send_continues_only_after_ocr_title_matches(monkeypatch):
    window = FakeWindow("微信", "Qt51514QWindowIcon")
    pasted = []
    clicked = []
    monkeypatch.setattr(wechat_bridge, "_leave_web_search_page", lambda _window: True)
    monkeypatch.setattr(
        wechat_bridge, "_click_screen_point", lambda *point: clicked.append(point)
    )
    monkeypatch.setattr(wechat_bridge, "_select_all", lambda: None)
    monkeypatch.setattr(wechat_bridge, "_paste_text", lambda text: pasted.append(text))
    monkeypatch.setattr(wechat_bridge, "_press_down", lambda: None)
    monkeypatch.setattr(wechat_bridge, "_press_enter", lambda: None)
    monkeypatch.setattr(wechat_bridge, "_find_web_search_document", lambda _w: None)
    monkeypatch.setattr(
        wechat_bridge,
        "_read_rendered_chat_title",
        lambda _window: "鲱 鱼",
    )
    monkeypatch.setattr(wechat_bridge.time, "sleep", lambda _seconds: None)

    result = wechat_bridge._send_via_rendered_window(window, "鲱鱼", "测试草稿")

    assert pasted == ["鲱鱼", "测试草稿"]
    assert len(clicked) == 3
    assert result["target_verified"] is True
    assert result["title_verification"] == "windows_ocr"


def test_rendered_send_stops_if_title_changes_after_message_is_pasted(monkeypatch):
    window = FakeWindow("微信", "Qt51514QWindowIcon")
    pasted = []
    clicked = []
    titles = iter(["鲱鱼", "其他联系人"])
    monkeypatch.setattr(wechat_bridge, "_leave_web_search_page", lambda _window: True)
    monkeypatch.setattr(
        wechat_bridge, "_click_screen_point", lambda *point: clicked.append(point)
    )
    monkeypatch.setattr(wechat_bridge, "_select_all", lambda: None)
    monkeypatch.setattr(wechat_bridge, "_paste_text", lambda text: pasted.append(text))
    monkeypatch.setattr(wechat_bridge, "_press_down", lambda: None)
    monkeypatch.setattr(wechat_bridge, "_press_enter", lambda: None)
    monkeypatch.setattr(wechat_bridge, "_find_web_search_document", lambda _w: None)
    monkeypatch.setattr(
        wechat_bridge, "_read_rendered_chat_title", lambda _window: next(titles)
    )
    monkeypatch.setattr(wechat_bridge.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="发送前 OCR 标题复验失败"):
        wechat_bridge._send_via_rendered_window(window, "鲱鱼", "测试草稿")

    assert pasted == ["鲱鱼", "测试草稿"]
    assert len(clicked) == 2


def test_configured_chat_name_is_not_replaced_by_cli_display_name(monkeypatch):
    monkeypatch.setitem(
        wechat_bridge._CHAT_IDENTITIES,
        "鲱鱼",
        "test-contact-id",
    )
    assert wechat_bridge._resolve_current_chat_name("鲱鱼") == "鲱鱼"


def test_find_wechat_window_prefers_real_qt_window_over_web_window(monkeypatch):
    web_window = FakeWindow("微信", "Chrome_WidgetWin_0")
    real_window = FakeWindow("微信", "Qt51514QWindowIcon")
    monkeypatch.setattr(wechat_bridge, "auto", FakeAutomation([web_window, real_window]))

    assert wechat_bridge._find_wechat_window() is real_window


def test_find_wechat_window_falls_back_when_qt_window_is_missing(monkeypatch):
    mmui_window = FakeWindow("微信", "mmui::MainWindow")
    web_window = FakeWindow("微信", "Chrome_WidgetWin_0")
    monkeypatch.setattr(wechat_bridge, "auto", FakeAutomation([web_window, mmui_window]))

    assert wechat_bridge._find_wechat_window() is mmui_window


def test_find_wechat_window_retries_when_background_uia_first_returns_no_windows(
    monkeypatch,
):
    real_window = FakeWindow("微信", "Qt51514QWindowIcon")

    class EventuallyReadyRoot:
        def __init__(self):
            self.calls = 0

        def GetChildren(self):
            self.calls += 1
            return [] if self.calls == 1 else [real_window]

    class EventuallyReadyAutomation:
        def __init__(self):
            self.root = EventuallyReadyRoot()

        def GetRootControl(self):
            return self.root

    automation = EventuallyReadyAutomation()
    monkeypatch.setattr(wechat_bridge, "auto", automation)
    monkeypatch.setattr(wechat_bridge.time, "sleep", lambda _seconds: None)

    assert wechat_bridge._find_wechat_window() is real_window
    assert automation.root.calls == 2


def test_send_stops_when_target_chat_cannot_be_verified(monkeypatch):
    class SendWindow:
        def SetFocus(self):
            pass

    monkeypatch.setattr(wechat_bridge, "auto", object())
    monkeypatch.setattr(wechat_bridge, "_find_wechat_window", lambda: SendWindow())
    monkeypatch.setattr(wechat_bridge, "_find_search_edit", lambda _window: None)

    with pytest.raises(RuntimeError, match="无法验证目标会话"):
        wechat_bridge.send_wechat_message("鲱鱼", "测试草稿")


def test_send_uses_rendered_window_only_for_registered_stable_talker(monkeypatch):
    class SendWindow:
        def SetFocus(self):
            pass

    sent = []
    monkeypatch.setattr(wechat_bridge, "auto", object())
    monkeypatch.setattr(wechat_bridge, "_find_wechat_window", lambda: SendWindow())
    monkeypatch.setattr(wechat_bridge, "_find_search_edit", lambda _window: None)
    monkeypatch.setattr(
        wechat_bridge,
        "_send_via_rendered_window",
        lambda _window, name, text: sent.append((name, text))
        or {
            "sent": True,
            "chat_name": name,
            "stable_talker": "wxid_target",
            "selection": "rendered_window_coordinate",
        },
    )
    monkeypatch.setitem(wechat_bridge._CHAT_IDENTITIES, "鲱鱼", "wxid_target")

    result = wechat_bridge.send_wechat_message("鲱鱼", "测试草稿")

    assert sent == [("鲱鱼", "测试草稿")]
    assert result["sent"] is True
    assert result["stable_talker"] == "wxid_target"


def test_send_tries_next_non_web_result_after_title_mismatch(monkeypatch):
    class SendWindow:
        def SetFocus(self):
            pass

    search = FakeControl("搜索", "EditControl", (20, 20, 300, 60))
    first = FakeControl("联系人", "ListItemControl", (20, 100, 300, 150))
    second = FakeControl("联系人", "ListItemControl", (20, 160, 300, 210))
    selected = []
    first.Click = lambda waitTime=0: selected.append("first")
    second.Click = lambda waitTime=0: selected.append("second")
    titles = iter(["其他联系人", "鲱鱼"])

    monkeypatch.setattr(wechat_bridge, "auto", object())
    monkeypatch.setattr(wechat_bridge, "_find_wechat_window", lambda: SendWindow())
    monkeypatch.setattr(wechat_bridge, "_find_search_edit", lambda _window: search)
    monkeypatch.setattr(
        wechat_bridge,
        "_find_chat_result_candidates",
        lambda _window, _search: [first, second],
    )
    monkeypatch.setattr(
        wechat_bridge, "_read_open_chat_title", lambda _window: next(titles)
    )
    monkeypatch.setattr(wechat_bridge, "_find_message_editor", lambda *_args: search)
    monkeypatch.setattr(wechat_bridge, "_paste_text", lambda _text: None)
    monkeypatch.setattr(wechat_bridge, "_press_enter", lambda: None)
    monkeypatch.setattr(wechat_bridge.time, "sleep", lambda _seconds: None)

    result = wechat_bridge.send_wechat_message("鲱鱼", "测试草稿")

    assert selected == ["first", "second"]
    assert result["sent"] is True
    assert result["selection"] == "search_result_candidate_2"
