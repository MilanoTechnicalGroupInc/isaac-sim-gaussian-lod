"""Extension lifecycle and compact OmniUI control surface."""

from __future__ import annotations

import carb
import omni.ext
import omni.kit.app
import omni.ui as ui
import omni.usd
from omni.kit.menu.utils import MenuItemDescription, add_menu_items, remove_menu_items
from pxr import UsdGeom

from .runtime import EXTENSION_ID, GaussianLodRuntime


class GaussianLodExtension(omni.ext.IExt):
    def on_startup(self, _ext_id: str) -> None:
        settings = carb.settings.get_settings()
        root_prim = settings.get(f"/exts/{EXTENSION_ID}/root_prim") or "/World/GaussianLOD"
        self._runtime = GaussianLodRuntime(str(root_prim))
        self._runtime.enabled = bool(settings.get(f"/exts/{EXTENSION_ID}/enabled"))
        self._window = ui.Window("Gaussian LOD", width=460, height=560, visible=False)
        self._window.set_visibility_changed_fn(self._on_window_visibility)
        self._menu_items = [MenuItemDescription(name="Gaussian LOD", onclick_fn=self._show_window)]
        add_menu_items(self._menu_items, "Window")
        self._build_ui()
        self._runtime.subscribe(self._on_stats)
        app = omni.kit.app.get_app()
        self._update_subscription = app.get_update_event_stream().create_subscription_to_pop(
            lambda _event: self._runtime.update(),
            name=f"{EXTENSION_ID}.update",
        )
        self._stage_subscription = (
            omni.usd.get_context()
            .get_stage_event_stream()
            .create_subscription_to_pop(
                self._on_stage_event,
                name=f"{EXTENSION_ID}.stage",
            )
        )
        self._runtime.load_from_stage()

    def on_shutdown(self) -> None:
        remove_menu_items(self._menu_items, "Window")
        self._stage_subscription = None
        self._update_subscription = None
        if self._window is not None:
            self._window.destroy()
        self._window = None
        self._runtime = None

    def _show_window(self) -> None:
        self._window.visible = True

    def _on_window_visibility(self, visible: bool) -> None:
        if visible:
            self._refresh_manifest_ui()

    def _build_ui(self) -> None:
        with self._window.frame:
            with ui.VStack(spacing=6, height=0):
                ui.Label("Camera-frustum Gaussian LOD", height=24)
                self._status = ui.Label("No package loaded", word_wrap=True, height=48)
                with ui.HStack(height=28):
                    ui.Button("Reload package", clicked_fn=self._reload, width=140)
                    ui.Button("Warm all", clicked_fn=self._runtime.begin_warmup, width=100)
                ui.Separator()
                ui.Label("Camera selection", height=22)
                with ui.HStack(height=28):
                    self._camera_model = ui.SimpleStringModel("")
                    ui.StringField(self._camera_model)
                    ui.Button(
                        "Use selected",
                        clicked_fn=self._use_selected_camera,
                        width=110,
                    )
                with ui.HStack(height=28):
                    self._union_model = ui.SimpleBoolModel(False)
                    ui.CheckBox(self._union_model, width=20)
                    ui.Label("Union selected cameras", width=180)
                    ui.Button(
                        "Add selected",
                        clicked_fn=self._add_selected_camera,
                        width=110,
                    )
                    ui.Button(
                        "Clear",
                        clicked_fn=self._clear_camera_union,
                        width=60,
                    )
                self._union_label = ui.Label("Union: none", word_wrap=True, height=36)
                ui.Separator()
                with ui.HStack(height=28):
                    ui.Label("FOV margin (deg)", width=170)
                    self._margin_model = ui.SimpleFloatModel(2.0)
                    ui.FloatField(self._margin_model)
                with ui.HStack(height=28):
                    ui.Label("Update interval (s)", width=170)
                    self._interval_model = ui.SimpleFloatModel(0.05)
                    ui.FloatField(self._interval_model)
                with ui.HStack(height=28):
                    self._debug_model = ui.SimpleBoolModel(False)
                    ui.CheckBox(self._debug_model, width=20)
                    ui.Label("Draw visible tile bounds")
                ui.Button("Apply runtime settings", clicked_fn=self._apply_settings, height=28)
                ui.Separator()
                ui.Label("Tier distance bands", height=22)
                self._tier_frame = ui.Frame(height=0)
                self._tier_models = {}
                self._build_tier_rows()

    def _build_tier_rows(self) -> None:
        self._tier_frame.clear()
        self._tier_models = {}
        with self._tier_frame:
            with ui.VStack(spacing=3, height=0):
                manifest = self._runtime.manifest
                if manifest is None:
                    ui.Label("Load a package to edit tier ranges")
                    return
                with ui.HStack(height=20):
                    ui.Label("Tier", width=90)
                    ui.Label("Near", width=90)
                    ui.Label("Far", width=90)
                    ui.Label("Hysteresis", width=90)
                for tier in manifest.tiers:
                    near = ui.SimpleFloatModel(tier.near_m)
                    far = ui.SimpleFloatModel(tier.far_m)
                    hysteresis = ui.SimpleFloatModel(tier.hysteresis_m)
                    self._tier_models[tier.id] = (near, far, hysteresis)
                    with ui.HStack(height=26):
                        ui.Label(tier.id, width=90)
                        ui.FloatField(near, width=90)
                        ui.FloatField(far, width=90)
                        ui.FloatField(hysteresis, width=90)
                ui.Button("Apply tier ranges", clicked_fn=self._apply_tiers, height=28)

    def _reload(self) -> None:
        self._runtime.load_from_stage()
        self._refresh_manifest_ui()

    def _refresh_manifest_ui(self) -> None:
        manifest = self._runtime.manifest
        if manifest is not None:
            self._margin_model.set_value(manifest.runtime.fov_margin_deg)
            self._interval_model.set_value(manifest.runtime.update_interval_s)
            self._union_model.set_value(manifest.runtime.multi_camera_mode == "union")
        self._build_tier_rows()

    def _selected_camera(self) -> str | None:
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return None
        for path in omni.usd.get_context().get_selection().get_selected_prim_paths():
            prim = stage.GetPrimAtPath(path)
            if prim and prim.IsA(UsdGeom.Camera):
                return path
        self._status.text = "Select a perspective camera prim in the Stage"
        return None

    def _use_selected_camera(self) -> None:
        path = self._selected_camera()
        if path:
            self._runtime.active_camera = path
            self._camera_model.set_value(path)

    def _add_selected_camera(self) -> None:
        path = self._selected_camera()
        if path and path not in self._runtime.camera_union:
            self._runtime.camera_union.append(path)
            self._union_label.text = "Union: " + ", ".join(self._runtime.camera_union)

    def _clear_camera_union(self) -> None:
        self._runtime.camera_union.clear()
        self._union_label.text = "Union: none"

    def _apply_settings(self) -> None:
        self._runtime.configure(
            active_camera=self._camera_model.as_string,
            camera_union=self._runtime.camera_union,
            multi_camera_mode="union" if self._union_model.as_bool else "active",
            fov_margin_deg=self._margin_model.as_float,
            update_interval_s=self._interval_model.as_float,
            debug_overlay=self._debug_model.as_bool,
        )

    def _apply_tiers(self) -> None:
        ranges = {
            tier_id: tuple(model.as_float for model in models)
            for tier_id, models in self._tier_models.items()
        }
        try:
            self._runtime.set_tier_ranges(ranges)
        except ValueError as exc:
            self._status.text = str(exc)

    def _on_stats(self, stats) -> None:
        if self._status is not None:
            self._status.text = f"{stats.state}: {stats.message}"

    def _on_stage_event(self, event) -> None:
        event_type = int(event.type)
        if event_type in (
            int(omni.usd.StageEventType.CLOSING),
            int(omni.usd.StageEventType.CLOSED),
        ):
            self._runtime.reset()
        elif event_type == int(omni.usd.StageEventType.OPENED):
            self._runtime.load_from_stage()
            self._refresh_manifest_ui()
