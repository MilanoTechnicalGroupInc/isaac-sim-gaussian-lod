# ruff: noqa: F704, F821, I001
"""Click a visible OmniUI button by its text in a running Kit application.

Injected globals:
    button_text: exact visible button text.
"""

import isaacsim.core.experimental.utils.app as app_utils
import omni.ui as ui
from omni.kit.ui_test import Vec2, emulate_mouse_move_and_click
from omni.ui_query import OmniUIQuery


target = str(button_text).strip().casefold()
match = None
for window in ui.Workspace.get_windows():
    if not hasattr(window, "frame"):
        continue
    for path in OmniUIQuery.get_window_widget_paths(window):
        widget = OmniUIQuery.find_widget(path)
        text = str(getattr(widget, "text", "") or "").strip().casefold()
        name = str(getattr(widget, "name", "") or "").strip().casefold()
        if target not in (text, name):
            continue
        if not getattr(widget, "visible", True):
            continue
        match = widget
        break
    if match is not None:
        break

if match is None:
    raise RuntimeError(f"visible OmniUI button not found: {button_text}")

position = Vec2(
    match.screen_position_x + match.computed_width / 2,
    match.screen_position_y + match.computed_height / 2,
)
await emulate_mouse_move_and_click(position)
await app_utils.update_app_async(steps=10)
print(f"Clicked OmniUI button: {button_text}")
