from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Protocol


class AletheiaPlugin(Protocol):
    name: str

    def register(self) -> None: ...


@dataclass
class PluginManifest:
    name: str
    path: Path
    module_name: str


class PluginManager:
    def __init__(self, plugin_dirs: list[Path] | None = None) -> None:
        self.plugin_dirs = plugin_dirs or []
        self._plugins: dict[str, AletheiaPlugin] = {}

    def discover(self) -> list[PluginManifest]:
        manifests: list[PluginManifest] = []
        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                continue
            for file_path in plugin_dir.glob("*.py"):
                manifests.append(
                    PluginManifest(
                        name=file_path.stem,
                        path=file_path,
                        module_name=f"aletheia_plugin_{file_path.stem}",
                    )
                )
        return manifests

    def load_all(self) -> dict[str, AletheiaPlugin]:
        for manifest in self.discover():
            plugin = self._load_manifest(manifest)
            plugin.register()
            self._plugins[plugin.name] = plugin
        return dict(self._plugins)

    def loaded_plugins(self) -> dict[str, AletheiaPlugin]:
        return dict(self._plugins)

    def _load_manifest(self, manifest: PluginManifest) -> AletheiaPlugin:
        spec = importlib.util.spec_from_file_location(manifest.module_name, manifest.path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load plugin spec for {manifest.path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return _instantiate_plugin(module)


def _instantiate_plugin(module: ModuleType) -> AletheiaPlugin:
    plugin_cls = getattr(module, "PLUGIN_CLASS", None)
    if plugin_cls is not None:
        return plugin_cls()
    register_fn = getattr(module, "register_plugin", None)
    if register_fn is None:
        raise AttributeError("Plugin module must expose PLUGIN_CLASS or register_plugin().")
    plugin = register_fn()
    return plugin
