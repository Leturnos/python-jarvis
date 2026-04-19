import os
import yaml
import glob
from core.logger_config import logger
from core.config import config

class PluginManager:
    def __init__(self, plugins_dir="plugins"):
        self.plugins_dir = plugins_dir
        self.intents = {}  # Map of intent_name -> { description, risk_level, actions, plugin_name }
        self.load_plugins()

    def _expand_vars(self, data):
        """Recursively expand environment variables in a dictionary or list."""
        if isinstance(data, dict):
            return {k: self._expand_vars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._expand_vars(i) for i in data]
        elif isinstance(data, str):
            return os.path.expandvars(data)
        else:
            return data

    def load_plugins(self):
        """Loads all YAML/JSON plugin files from the plugins directory."""
        if not os.path.exists(self.plugins_dir):
            logger.warning(f"Plugins directory '{self.plugins_dir}' not found. Creating it.")
            os.makedirs(self.plugins_dir, exist_ok=True)
            return

        plugin_files = glob.glob(os.path.join(self.plugins_dir, "*.yaml")) + \
                       glob.glob(os.path.join(self.plugins_dir, "*.yml")) + \
                       glob.glob(os.path.join(self.plugins_dir, "*.json"))

        for file_path in plugin_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    plugin_data = yaml.safe_load(f)
                    
                if not plugin_data or "commands" not in plugin_data:
                    logger.warning(f"Invalid or empty plugin file: {file_path}")
                    continue

                plugin_name = plugin_data.get("name", os.path.basename(file_path))
                commands = self._expand_vars(plugin_data["commands"])

                for cmd in commands:
                    intent = cmd.get("intent")
                    if not intent:
                        logger.warning(f"Command without intent found in {plugin_name}")
                        continue
                    
                    if intent in self.intents:
                        logger.warning(f"Intent '{intent}' is being overwritten by plugin '{plugin_name}'")

                    self.intents[intent] = {
                        "description": cmd.get("description", ""),
                        "risk_level": cmd.get("risk_level", "safe"),
                        "actions": cmd.get("actions", []),
                        "plugin_name": plugin_name
                    }
                logger.info(f"Loaded plugin '{plugin_name}' with {len(commands)} intents.")
                
            except Exception as e:
                logger.error(f"Failed to load plugin {file_path}: {e}")

        logger.info(f"PluginManager initialization complete. Loaded {len(self.intents)} intents total.")

    def get_intents(self):
        """Returns a list of all loaded intent names and their descriptions."""
        return [{"intent": k, "description": v["description"], "risk_level": v["risk_level"]} 
                for k, v in self.intents.items()]

    def get_actions_for_intent(self, intent_name):
        """Returns the list of actions for a specific intent."""
        if intent_name in self.intents:
            return self.intents[intent_name]["actions"]
        return None

# Singleton instance
plugin_manager = PluginManager()
