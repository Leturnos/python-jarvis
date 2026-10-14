import glob
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import yaml

from core.infra.config import config, update_yaml_plugin_preset
from core.infra.logger_config import logger
from core.shared.paths import get_app_root


class PluginManager:
    """Manages automation plugins and presets, with dynamic enable/disable controls."""

    def __init__(self, plugins_dir: str | Path | None = None) -> None:
        if plugins_dir is None:
            self.plugins_dir = str(get_app_root() / "plugins")
        else:
            p = Path(plugins_dir)
            self.plugins_dir = str(p if p.is_absolute() else get_app_root() / p)

        self.intents: dict[
            str, Any
        ] = {}  # Map of intent_name -> { description, risk_level, actions, phrases, plugin_name, plugin_id }
        self.available_plugins: dict[str, dict[str, Any]] = {}
        self._change_listeners: list[Callable[[], None]] = []
        self.load_plugins()

    def register_change_listener(self, callback: Callable[[], None]) -> None:
        """Registers a callback function to be called when plugins are enabled or disabled."""
        self._change_listeners.append(callback)

    def _notify_listeners(self) -> None:
        """Notifies all registered listeners about plugin configuration changes."""
        for cb in self._change_listeners:
            try:
                cb()
            except Exception as e:
                logger.warning(f"Error notifying plugin change listener: {e}")

    def is_plugin_enabled(self, plugin_id: str) -> bool:
        """Checks whether a plugin is enabled according to configuration."""
        plugins_cfg = config.get("plugins", {})
        if "enabled_presets" not in plugins_cfg:
            return True
        enabled_presets = plugins_cfg.get("enabled_presets")
        if not isinstance(enabled_presets, list):
            return True
        return plugin_id in enabled_presets

    def set_plugin_enabled(self, plugin_id: str, enabled: bool) -> None:
        """Enables or disables a plugin preset, persists changes, and reloads active intents."""
        update_yaml_plugin_preset(plugin_id, enabled)

        # Update running in-memory config as well
        plugins_cfg = config.setdefault("plugins", {})
        enabled_list = plugins_cfg.setdefault("enabled_presets", [])
        if enabled and plugin_id not in enabled_list:
            enabled_list.append(plugin_id)
        elif not enabled and plugin_id in enabled_list:
            enabled_list.remove(plugin_id)

        self.load_plugins()
        self._notify_listeners()
        logger.info(
            f"Plugin preset '{plugin_id}' set to {'enabled' if enabled else 'disabled'}."
        )

    def get_available_plugins(self) -> list[dict[str, Any]]:
        """Returns a list of all discovered plugins with metadata and enabled status."""
        return list(self.available_plugins.values())

    def _expand_vars(self, data: Any) -> Any:
        """Recursively expand environment variables in a dictionary or list."""
        if isinstance(data, dict):
            return {k: self._expand_vars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._expand_vars(i) for i in data]
        elif isinstance(data, str):
            return os.path.expandvars(data)
        else:
            return data

    def _resolve_actions(
        self,
        actions: list[dict[str, Any]],
        shared_actions: dict[str, Any],
        plugin_name: str,
    ) -> list[dict[str, Any]]:
        """Resolves 'include' actions by replacing them with shared actions."""
        resolved: list[dict[str, Any]] = []
        for action in actions:
            if action.get("type") == "include":
                ref_name = action.get("name")
                if ref_name in shared_actions:
                    resolved.extend(shared_actions[ref_name])
                else:
                    logger.error(
                        f"Plugin '{plugin_name}': Shared action '{ref_name}' not found."
                    )
            else:
                resolved.append(action)
        return resolved

    def load_plugins(self) -> None:
        """Loads all YAML/JSON plugin files from the plugins directory."""
        self.intents.clear()
        self.available_plugins.clear()

        if not os.path.exists(self.plugins_dir):
            logger.warning(
                f"Plugins directory '{self.plugins_dir}' not found. Creating it."
            )
            os.makedirs(self.plugins_dir, exist_ok=True)
            return

        plugin_files = (
            glob.glob(os.path.join(self.plugins_dir, "*.yaml"))
            + glob.glob(os.path.join(self.plugins_dir, "*.yml"))
            + glob.glob(os.path.join(self.plugins_dir, "*.json"))
        )

        for file_path in plugin_files:
            try:
                with open(file_path, encoding="utf-8") as f:
                    plugin_data = yaml.safe_load(f)

                if not plugin_data or "commands" not in plugin_data:
                    logger.warning(f"Invalid or empty plugin file: {file_path}")
                    continue

                stem_id = Path(file_path).stem
                plugin_id = str(plugin_data.get("id") or stem_id).strip()
                plugin_name = plugin_data.get("name", plugin_id)
                plugin_desc = plugin_data.get("description", "")
                plugin_category = plugin_data.get("category", "Geral")
                plugin_version = str(plugin_data.get("version", "1.0.0"))

                is_enabled = self.is_plugin_enabled(plugin_id)

                raw_shared_actions = plugin_data.get("shared_actions", {})
                shared_actions = self._expand_vars(raw_shared_actions)
                commands = self._expand_vars(plugin_data["commands"])

                # Store metadata regardless of enabled status for UI management
                self.available_plugins[plugin_id] = {
                    "id": plugin_id,
                    "name": plugin_name,
                    "description": plugin_desc,
                    "category": plugin_category,
                    "version": plugin_version,
                    "file_path": file_path,
                    "is_enabled": is_enabled,
                    "commands_count": len(commands)
                    if isinstance(commands, list)
                    else 0,
                    "commands": [
                        {
                            "intent": cmd.get("intent", ""),
                            "description": cmd.get("description", ""),
                            "phrases": cmd.get("phrases", []),
                            "risk_level": cmd.get("risk_level", "safe"),
                        }
                        for cmd in commands
                        if isinstance(cmd, dict)
                    ]
                    if isinstance(commands, list)
                    else [],
                }

                # If disabled by user preference, skip registering intents
                if not is_enabled:
                    logger.debug(
                        f"Plugin '{plugin_id}' is disabled by user configuration. Skipping intents."
                    )
                    continue

                for cmd in commands:
                    intent = cmd.get("intent")
                    if not intent:
                        logger.warning(f"Command without intent found in {plugin_name}")
                        continue

                    if intent in self.intents:
                        logger.warning(
                            f"Intent '{intent}' is being overwritten by plugin '{plugin_name}'"
                        )

                    resolved_actions = self._resolve_actions(
                        cmd.get("actions", []), shared_actions, plugin_name
                    )

                    self.intents[intent] = {
                        "description": cmd.get("description", ""),
                        "risk_level": cmd.get("risk_level", "safe"),
                        "phrases": cmd.get("phrases", []),
                        "actions": resolved_actions,
                        "plugin_name": plugin_name,
                        "plugin_id": plugin_id,
                    }

                logger.info(
                    f"Loaded plugin '{plugin_name}' ({plugin_id}) with {len(commands)} intents."
                )

            except Exception as e:
                logger.error(f"Failed to load plugin {file_path}: {e}")

        logger.info(
            f"PluginManager initialization complete. Loaded {len(self.intents)} intents total from {len(self.available_plugins)} plugins."
        )

    def get_intents(self) -> list[dict[str, Any]]:
        """Returns a list of all loaded active intent names, descriptions and phrases."""
        return [
            {
                "intent": k,
                "description": v["description"],
                "phrases": v.get("phrases", []),
                "risk_level": v["risk_level"],
                "plugin_name": v.get("plugin_name", ""),
                "plugin_id": v.get("plugin_id", ""),
                "category": self.available_plugins.get(v.get("plugin_id", ""), {}).get(
                    "category", "Geral"
                ),
            }
            for k, v in self.intents.items()
        ]

    def get_actions_for_intent(self, intent_name: str) -> list[dict[str, Any]] | None:
        """Returns the list of actions for a specific active intent."""
        if intent_name in self.intents:
            return cast(list[dict[str, Any]], self.intents[intent_name]["actions"])
        return None


# Singleton instance
plugin_manager = PluginManager()
