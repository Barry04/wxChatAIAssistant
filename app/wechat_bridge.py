from dataclasses import asdict, dataclass
from contextlib import nullcontext
import ctypes
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any


try:
    import uiautomation as auto
except ImportError:
    auto = None


_CHAT_IDENTITIES: dict[str, str] = {}
_WEB_SEARCH_MARKERS = ("搜一搜", "网络搜索", "网页搜索", "搜索网络", "web search")
_TITLE_OCR_SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "read_wechat_title.ps1"


def register_chat_identity(chat_name: str, talker: str) -> None:
    """Associate the current visible name with the stable WeChat session ID."""
    chat_name = str(chat_name or "").strip()
    talker = str(talker or "").strip()
    if chat_name and talker:
        _CHAT_IDENTITIES[chat_name] = talker


def _resolve_current_chat_name(chat_name: str) -> str:
    # The configured display name is the value that can be searched in the
    # visible WeChat UI. The CLI session listing may return a mojibake name
    # for this WeChat build, so never replace a known-good UI name with it.
    return chat_name


@dataclass
class WeChatStatus:
    available: bool
    running: bool
    logged_in: bool
    window_name: str = ""
    window_class: str = ""
    process_id: int = 0
    message: str = ""


def _decode_uia_text(value: str) -> str:
    if not value:
        return ""
    try:
        return value.encode("latin1").decode("gbk")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _automation_context():
    if auto is None:
        return nullcontext()
    initializer = getattr(auto, "UIAutomationInitializerInThread", None)
    return initializer() if initializer else nullcontext()


def _walk_controls(root, max_depth: int = 8):
    def walk(control, depth: int):
        if depth > max_depth:
            return
        yield control
        child = control.GetFirstChildControl()
        while child:
            yield from walk(child, depth + 1)
            child = child.GetNextSiblingControl()

    yield from walk(root, 0)


def _rect_tuple(control) -> tuple[int, int, int, int]:
    rect = control.BoundingRectangle
    return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


def _rect_area(control) -> int:
    left, top, right, bottom = _rect_tuple(control)
    return max(0, right - left) * max(0, bottom - top)


def _normalized_control_name(control) -> str:
    return _decode_uia_text(str(control.Name or "")).strip()


def _ancestor_names(control, limit: int = 5) -> list[str]:
    names: list[str] = []
    current = control
    for _ in range(limit):
        if current is None:
            break
        name = _normalized_control_name(current)
        if name:
            names.append(name)
        getter = getattr(current, "GetParentControl", None)
        current = getter() if getter else None
    return names


def _contains_web_search_marker(control) -> bool:
    combined = " ".join(_ancestor_names(control)).lower()
    return any(marker in combined for marker in _WEB_SEARCH_MARKERS)


def _find_web_search_document(window):
    for control in _walk_controls(window):
        if control.ControlTypeName != "DocumentControl":
            continue
        name = _normalized_control_name(control)
        if any(marker in name.lower() for marker in _WEB_SEARCH_MARKERS):
            return control
    return None


def _leave_web_search_page(window) -> bool:
    """Return to the chat surface when WeChat is showing its embedded search page."""
    if _find_web_search_document(window) is None:
        return True
    for control in _walk_controls(window):
        if control.ControlTypeName != "ButtonControl":
            continue
        name = _normalized_control_name(control).lower()
        if "后退" not in name and "back" not in name:
            continue
        control.Click(waitTime=0)
        time.sleep(0.8)
        return _find_web_search_document(window) is None
    return False


def _find_search_edit(window):
    win_left, win_top, win_right, win_bottom = _rect_tuple(window)
    win_width = max(1, win_right - win_left)
    win_height = max(1, win_bottom - win_top)
    candidates = []
    for control in _walk_controls(window):
        if control.ControlTypeName != "EditControl":
            continue
        left, top, right, bottom = _rect_tuple(control)
        if right <= left or bottom <= top:
            continue
        name = _normalized_control_name(control).lower()
        in_upper_left = (
            left < win_left + win_width * 0.55
            and top < win_top + win_height * 0.3
        )
        named_search = any(token in name for token in ("搜索", "search"))
        if not in_upper_left and not named_search:
            continue
        score = (100 if named_search else 0) + (50 if in_upper_left else 0)
        score -= int((top - win_top) / 10)
        candidates.append((score, control))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1] if candidates else None


def _clickable_ancestor(control):
    current = control
    for _ in range(5):
        if current is None:
            break
        if current.ControlTypeName in {"ListItemControl", "ButtonControl"}:
            return current
        getter = getattr(current, "GetParentControl", None)
        current = getter() if getter else None
    return control


def _find_chat_result_candidates(window, search_edit):
    """Return visible chat-search candidates in their on-screen order.

    WeChat's embedded web search may be interleaved with contact results.  A
    caller must therefore walk these candidates one by one instead of assuming
    that the first row is a chat.
    """
    win_left, _, win_right, _ = _rect_tuple(window)
    win_width = max(1, win_right - win_left)
    search_bottom = _rect_tuple(search_edit)[3]
    candidates = []
    seen: set[int] = set()
    for control in _walk_controls(window):
        if control.ControlTypeName not in {"ListItemControl", "ButtonControl"}:
            continue
        if _contains_web_search_marker(control):
            continue
        identity = id(control)
        if identity in seen:
            continue
        left, top, right, bottom = _rect_tuple(control)
        if not (
            left < win_left + win_width * 0.58
            and top >= search_bottom
            and right > left
            and bottom > top
        ):
            continue
        seen.add(identity)
        candidates.append((top, left, control))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return [control for _, _, control in candidates]


def _find_exact_chat_result(window, chat_name: str, search_edit):
    target = chat_name.strip()
    if not target:
        return None
    candidates = []
    for clickable in _find_chat_result_candidates(window, search_edit):
        for control in _walk_controls(clickable):
            if _normalized_control_name(control) != target:
                continue
            _, top, _, _ = _rect_tuple(clickable)
            score = 100 if clickable.ControlTypeName == "ListItemControl" else 50
            score -= int(top / 20)
            candidates.append((score, clickable))
            break
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1] if candidates else None


def _find_message_editor(window, search_edit):
    win_left, win_top, win_right, win_bottom = _rect_tuple(window)
    win_width = max(1, win_right - win_left)
    win_height = max(1, win_bottom - win_top)
    candidates = []
    for control in _walk_controls(window):
        if control is search_edit:
            continue
        if control.ControlTypeName not in {"EditControl", "DocumentControl"}:
            continue
        if _contains_web_search_marker(control):
            continue
        left, top, right, bottom = _rect_tuple(control)
        in_message_area = (
            left >= win_left + win_width * 0.25
            and top >= win_top + win_height * 0.35
            and right > left
            and bottom > top
        )
        if not in_message_area:
            continue
        candidates.append((_rect_area(control), control))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1] if candidates else None


def _read_open_chat_title(window) -> str:
    """Read the visible title of the currently opened chat from UIA.

    Only a title in the right-side conversation pane is accepted.  Returning
    an empty string means the target cannot be verified and must not be sent.
    """
    win_left, win_top, win_right, win_bottom = _rect_tuple(window)
    win_width = max(1, win_right - win_left)
    candidates = []
    for control in _walk_controls(window):
        name = _normalized_control_name(control)
        if not name or _contains_web_search_marker(control):
            continue
        left, top, right, bottom = _rect_tuple(control)
        if not (
            left >= win_left + win_width * 0.28
            and top <= win_top + (win_bottom - win_top) * 0.24
            and right > left
            and bottom > top
        ):
            continue
        if control.ControlTypeName not in {"TextControl", "ButtonControl", "PaneControl"}:
            continue
        candidates.append((top, left, -_rect_area(control), name))
    candidates.sort()
    return candidates[0][3] if candidates else ""


def _click_screen_point(x: int, y: int) -> None:
    """Click a screen point without requiring the rendered WeChat UI to expose UIA controls."""
    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(x), int(y))
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


def _key_event(vk: int, flags: int = 0) -> None:
    ctypes.windll.user32.keybd_event(vk, 0, flags, 0)


def _select_all() -> None:
    _key_event(0x11)
    _key_event(0x41)
    _key_event(0x41, 0x0002)
    _key_event(0x11, 0x0002)


def _paste_text(text: str) -> None:
    # uiautomation.SetClipboardText uses the legacy ANSI clipboard path on
    # this WeChat build, which turns Chinese text into question marks.
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.EmptyClipboard.restype = ctypes.c_bool
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.CloseClipboard.restype = ctypes.c_bool
    encoded = text.encode("utf-16-le") + b"\x00\x00"
    handle = kernel32.GlobalAlloc(0x0002, len(encoded))
    if not handle:
        raise RuntimeError("unable to allocate clipboard memory")
    try:
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise RuntimeError("unable to lock clipboard memory")
        try:
            ctypes.memmove(pointer, encoded, len(encoded))
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.OpenClipboard(0):
            raise RuntimeError("unable to open system clipboard")
        try:
            if not user32.EmptyClipboard():
                raise RuntimeError("unable to clear system clipboard")
            if not user32.SetClipboardData(13, handle):
                raise RuntimeError("unable to set Unicode clipboard data")
            handle = 0
        finally:
            user32.CloseClipboard()
    finally:
        if handle:
            kernel32.GlobalFree(handle)
    _key_event(0x11)
    _key_event(0x56)
    _key_event(0x56, 0x0002)
    _key_event(0x11, 0x0002)
    time.sleep(0.15)


def _paste_files(paths: list[str]) -> None:
    files = [str(Path(path)) for path in paths if str(path).strip()]
    if not files:
        raise ValueError("附件路径为空")
    encoded = ("\0".join(files) + "\0\0").encode("utf-16-le")
    dropfiles_size = 20
    total = dropfiles_size + len(encoded)
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.EmptyClipboard.restype = ctypes.c_bool
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.CloseClipboard.restype = ctypes.c_bool
    handle = kernel32.GlobalAlloc(0x0042, total)
    if not handle:
        raise RuntimeError("unable to allocate file clipboard memory")
    try:
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise RuntimeError("unable to lock file clipboard memory")
        try:
            payload = bytearray(total)
            payload[0:4] = dropfiles_size.to_bytes(4, "little")
            payload[16:20] = (1).to_bytes(4, "little")
            payload[dropfiles_size:] = encoded
            ctypes.memmove(pointer, bytes(payload), total)
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.OpenClipboard(0):
            raise RuntimeError("unable to open system clipboard")
        try:
            if not user32.EmptyClipboard():
                raise RuntimeError("unable to clear system clipboard")
            if not user32.SetClipboardData(15, handle):
                raise RuntimeError("unable to set file clipboard data")
            handle = 0
        finally:
            user32.CloseClipboard()
    finally:
        if handle:
            kernel32.GlobalFree(handle)
    _key_event(0x11)
    _key_event(0x56)
    _key_event(0x56, 0x0002)
    _key_event(0x11, 0x0002)
    time.sleep(0.35)


def _press_enter() -> None:
    _key_event(0x0D)
    _key_event(0x0D, 0x0002)


def _press_down() -> None:
    _key_event(0x28)
    _key_event(0x28, 0x0002)


def _window_point(window, x_ratio: float, y_ratio: float) -> tuple[int, int]:
    left, top, right, bottom = _rect_tuple(window)
    width = max(1, right - left)
    height = max(1, bottom - top)
    return (
        round(left + width * x_ratio),
        round(top + height * y_ratio),
    )


def _find_quote_target(window, preview: str):
    target = str(preview or "").strip()
    if not target:
        return None
    matches = []
    for control in _walk_controls(window, max_depth=12):
        name = _normalized_control_name(control)
        if not name or _contains_web_search_marker(control):
            continue
        if target not in name and name not in target:
            continue
        if control.ControlTypeName not in {
            "TextControl",
            "ListItemControl",
            "ButtonControl",
            "PaneControl",
        }:
            continue
        _, top, _, _ = _rect_tuple(control)
        matches.append((top, control))
    matches.sort(key=lambda item: item[0])
    return matches[-1][1] if matches else None


def _invoke_quote(control) -> None:
    clickable = _clickable_ancestor(control)
    right_click = getattr(clickable, "RightClick", None)
    if right_click:
        right_click(waitTime=0)
    else:
        left, top, right, bottom = _rect_tuple(clickable)
        _click_screen_point((left + right) // 2, (top + bottom) // 2)
    time.sleep(0.35)
    window = clickable
    getter = getattr(clickable, "GetParentControl", None)
    for _ in range(8):
        current = getter() if getter else None
        if current is None:
            break
        window = current
        getter = getattr(current, "GetParentControl", None)
    for menu in _walk_controls(window, max_depth=6):
        name = _normalized_control_name(menu)
        if menu.ControlTypeName in {"MenuItemControl", "TextControl", "ButtonControl"} and "引用" in name:
            menu.Click(waitTime=0)
            return
    raise RuntimeError("找不到可引用气泡")


def _find_mention_candidate(window, name: str):
    target = str(name or "").strip()
    if not target or "所有人" in target:
        return None
    matches = []
    for control in _walk_controls(window, max_depth=12):
        label = _normalized_control_name(control)
        if not label or _contains_web_search_marker(control):
            continue
        if "所有人" in label:
            continue
        if label != target and target not in label:
            continue
        if control.ControlTypeName not in {
            "ListItemControl",
            "ButtonControl",
            "TextControl",
            "PaneControl",
        }:
            continue
        _, top, _, _ = _rect_tuple(control)
        matches.append((top, control))
    matches.sort(key=lambda item: item[0])
    return matches[0][1] if matches else None


def _select_mentions(window, names: list[str]) -> None:
    for name in names:
        target = str(name or "").strip()
        if not target or "所有人" in target:
            raise RuntimeError("at_all_not_supported")
        _paste_text("@")
        time.sleep(0.35)
        candidate = _find_mention_candidate(window, target)
        if candidate is None:
            raise RuntimeError("未能点选联系人提及")
        clickable = _clickable_ancestor(candidate)
        clickable.Click(waitTime=0)
        time.sleep(0.2)


def _normalized_title(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def _read_rendered_chat_title(window) -> str:
    handle = int(getattr(window, "NativeWindowHandle", 0) or 0)
    if handle <= 0 or not _TITLE_OCR_SCRIPT.exists():
        return ""
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_TITLE_OCR_SCRIPT),
            "-WindowHandle",
            str(handle),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8-sig",
        errors="replace",
        timeout=10,
        creationflags=creationflags,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    try:
        payload = json.loads(completed.stdout.strip())
    except json.JSONDecodeError:
        return ""
    lines = payload.get("lines") if isinstance(payload, dict) else []
    return str(lines[0] if lines else payload.get("text") or "").strip()


def _send_via_rendered_window(
    window,
    chat_name: str,
    text: str,
    files: list[str] | None = None,
    quote_preview: str = "",
    at_names: list[str] | None = None,
) -> dict[str, Any]:
    """Use guarded coordinates for WeChat's self-rendered MMUI surface."""
    files = [str(path) for path in (files or []) if str(path).strip()]
    message = str(text or "").strip()
    if not _leave_web_search_page(window):
        raise RuntimeError("微信当前停留在搜一搜页面，未能返回聊天界面，已中止发送")

    # These ratios target the actual search and composer regions of the WeChat window.
    search_point = _window_point(window, 0.09, 0.08)
    editor_point = _window_point(window, 0.64, 0.86)
    send_point = _window_point(window, 0.965, 0.952)

    window.SetFocus()
    time.sleep(0.2)
    _click_screen_point(*search_point)
    time.sleep(0.1)
    _select_all()
    _paste_text(chat_name)
    time.sleep(0.8)

    # Select the first chat result explicitly. A bare Enter from the search box
    # opens WeChat's embedded web search when no result is focused.
    _press_down()
    _press_enter()
    time.sleep(0.8)
    if _find_web_search_document(window) is not None:
        raise RuntimeError("聊天搜索未选中会话，微信已进入搜一搜页面，已中止发送")

    opened_title = _read_rendered_chat_title(window)
    if _normalized_title(opened_title) != _normalized_title(chat_name):
        raise RuntimeError(
            f"目标会话 OCR 标题验证失败：期望“{chat_name}”，"
            f"实际“{opened_title or '未识别'}”，已中止发送"
        )

    quote_text = str(quote_preview or "").strip()
    if quote_text:
        target = _find_quote_target(window, quote_text)
        if target is None:
            raise RuntimeError("找不到可引用气泡")
        _invoke_quote(target)
        time.sleep(0.3)

    mention_names = [str(name).strip() for name in (at_names or []) if str(name).strip()]
    if mention_names:
        if any("所有人" in name for name in mention_names):
            raise RuntimeError("at_all_not_supported")
        _click_screen_point(*editor_point)
        _select_mentions(window, mention_names)

    def _send_current_payload(paste) -> None:
        _click_screen_point(*editor_point)
        paste()
        time.sleep(0.2)
        final_title = _read_rendered_chat_title(window)
        if _normalized_title(final_title) != _normalized_title(chat_name):
            raise RuntimeError(
                f"发送前 OCR 标题复验失败：期望“{chat_name}”，"
                f"实际“{final_title or '未识别'}”，已中止发送"
            )
        _click_screen_point(*send_point)
        time.sleep(0.5)

    if files:
        _send_current_payload(lambda: _paste_files(files))
    if message:
        _send_current_payload(
            lambda: (_select_all(), _paste_text(message))
        )
    return {
        "sent": True,
        "chat_name": chat_name,
        "stable_talker": _CHAT_IDENTITIES.get(chat_name.strip(), ""),
        "selection": "rendered_window_coordinate",
        "target_verified": True,
        "title_verification": "windows_ocr",
    }


def _find_wechat_window(*, attempts: int = 3, retry_interval: float = 0.15):
    if auto is None:
        return None
    for attempt in range(max(1, attempts)):
        root = auto.GetRootControl()
        candidates = []
        for window in root.GetChildren():
            class_name = window.ClassName or ""
            name = _decode_uia_text(window.Name or "")
            if class_name == "Qt51514QWindowIcon":
                priority = 0
            elif class_name.startswith("mmui::"):
                priority = 1
            elif name in {"微信", "WeChat", "Weixin"}:
                priority = 2
            else:
                continue
            candidates.append((priority, window))
        if candidates:
            return min(candidates, key=lambda item: item[0])[1]
        if attempt < max(1, attempts) - 1:
            time.sleep(retry_interval)
    return None


def find_wechat_window():
    with _automation_context():
        return _find_wechat_window()


def get_wechat_status() -> dict[str, Any]:
    if auto is None:
        return asdict(
            WeChatStatus(
                available=False,
                running=False,
                logged_in=False,
                message="缺少 uiautomation 依赖。",
            )
        )

    with _automation_context():
        window = _find_wechat_window()
        if window is None:
            return asdict(
                WeChatStatus(
                    available=True,
                    running=False,
                    logged_in=False,
                    message="未发现可见的微信主窗口。",
                )
            )

        class_name = window.ClassName or ""
        name = _decode_uia_text(window.Name or "")
        logged_in = "LoginWindow" not in class_name
        return asdict(
            WeChatStatus(
                available=True,
                running=True,
                logged_in=logged_in,
                window_name=name,
                window_class=class_name,
                process_id=window.ProcessId,
                message=(
                    "微信主界面可用。"
                    if logged_in
                    else "微信处于登录窗口，请先完成登录。"
                ),
            )
        )


def inspect_visible_controls(limit: int = 200) -> list[dict[str, Any]]:
    with _automation_context():
        window = _find_wechat_window()
        if window is None:
            return []

        controls: list[dict[str, Any]] = []

        def walk(control, depth: int = 0) -> None:
            if len(controls) >= limit or depth > 8:
                return
            name = _decode_uia_text(control.Name or "")
            control_type = control.ControlTypeName
            if name or control_type in {
                "EditControl",
                "DocumentControl",
                "ListControl",
                "ListItemControl",
            }:
                rect = control.BoundingRectangle
                controls.append(
                    {
                        "depth": depth,
                        "type": control_type,
                        "name": name[:300],
                        "class_name": control.ClassName or "",
                        "automation_id": control.AutomationId or "",
                        "rect": [rect.left, rect.top, rect.right, rect.bottom],
                    }
                )
            child = control.GetFirstChildControl()
            while child and len(controls) < limit:
                walk(child, depth + 1)
                child = child.GetNextSiblingControl()

        walk(window)
        return controls


def send_wechat_message(chat_name: str, text: str) -> dict[str, Any]:
    return _send_wechat_payload(chat_name, text=text)


def send_wechat_files(chat_name: str, files: list[str]) -> dict[str, Any]:
    return _send_wechat_payload(chat_name, files=files)


def send_wechat_quote(chat_name: str, quote_preview: str, text: str) -> dict[str, Any]:
    if not str(quote_preview or "").strip():
        raise RuntimeError("找不到可引用气泡")
    return _send_wechat_payload(
        chat_name, text=text, quote_preview=quote_preview
    )


def send_wechat_mention(
    chat_name: str,
    at_names: list[str],
    text: str,
    quote_preview: str = "",
) -> dict[str, Any]:
    names = [str(name).strip() for name in at_names if str(name).strip()]
    if any("所有人" in name for name in names):
        raise RuntimeError("at_all_not_supported")
    if not names:
        raise RuntimeError("未能点选联系人提及")
    return _send_wechat_payload(
        chat_name, text=text, at_names=names, quote_preview=quote_preview
    )


def _send_wechat_payload(
    chat_name: str,
    text: str = "",
    files: list[str] | None = None,
    quote_preview: str = "",
    at_names: list[str] | None = None,
) -> dict[str, Any]:
    current_chat_name = _resolve_current_chat_name(chat_name)
    files = [str(path) for path in (files or []) if str(path).strip()]
    message = str(text or "").strip()
    quote_text = str(quote_preview or "").strip()
    mention_names = [str(name).strip() for name in (at_names or []) if str(name).strip()]
    if auto is None:
        raise RuntimeError("缺少 uiautomation 依赖")
    if not chat_name.strip() or (not message and not files):
        raise ValueError("会话名称和回复内容不能为空")

    def _deliver(editor) -> None:
        if quote_text:
            target = _find_quote_target(window, quote_text)
            if target is None:
                raise RuntimeError("找不到可引用气泡")
            _invoke_quote(target)
            time.sleep(0.3)
        if mention_names:
            if any("所有人" in name for name in mention_names):
                raise RuntimeError("at_all_not_supported")
            editor.SetFocus()
            editor.Click(waitTime=0)
            _select_mentions(window, mention_names)
        if files:
            editor.SetFocus()
            editor.Click(waitTime=0)
            _paste_files(files)
            _press_enter()
            time.sleep(0.4)
        if message:
            editor.SetFocus()
            editor.Click(waitTime=0)
            _paste_text(message)
            _press_enter()

    with _automation_context():
        window = _find_wechat_window()
        if window is None:
            raise RuntimeError("未发现微信主窗口")

        window.SetFocus()
        time.sleep(0.2)
        search_edit = _find_search_edit(window)
        if search_edit is not None:
            search_edit.SetFocus()
            search_edit.Click(waitTime=0)
            _select_all()
            _paste_text(current_chat_name)
            time.sleep(0.8)
            candidates = _find_chat_result_candidates(window, search_edit)
            if not candidates:
                raise RuntimeError(
                    f"未找到可尝试的聊天会话“{current_chat_name}”，"
                    "已排除搜一搜/网页搜索结果"
                )
            for index, chat_result in enumerate(candidates, start=1):
                chat_result.Click(waitTime=0)
                time.sleep(0.8)
                opened_title = _read_open_chat_title(window)
                if opened_title != current_chat_name:
                    # Re-open search before selecting the next visible result.
                    search_edit.SetFocus()
                    search_edit.Click(waitTime=0)
                    _select_all()
                    _paste_text(current_chat_name)
                    time.sleep(0.5)
                    candidates = _find_chat_result_candidates(window, search_edit)
                    continue
                message_editor = _find_message_editor(window, search_edit)
                if message_editor is None:
                    raise RuntimeError("目标会话已验证，但未识别到消息输入框，已中止发送")
                _deliver(message_editor)
                return {
                    "sent": True,
                    "chat_name": current_chat_name,
                    "stable_talker": _CHAT_IDENTITIES.get(chat_name.strip(), ""),
                    "selection": f"search_result_candidate_{index}",
                    "target_verified": True,
                }
            raise RuntimeError(
                f"搜索结果均未打开目标会话“{current_chat_name}”，已中止发送"
            )
        stable_talker = _CHAT_IDENTITIES.get(chat_name.strip(), "")
        if stable_talker:
            kwargs = {}
            if files:
                kwargs["files"] = files
            if quote_text:
                kwargs["quote_preview"] = quote_text
            if mention_names:
                kwargs["at_names"] = mention_names
            return _send_via_rendered_window(
                window, current_chat_name, message, **kwargs
            )
        # The rendered fallback may only be used when the caller registered a
        # stable talker ID. Automation verifies the resulting message against
        # that same talker's database timeline before reporting success.
        raise RuntimeError(
            f"无法验证目标会话“{current_chat_name}”，已中止发送以避免误发到当前会话"
        )
