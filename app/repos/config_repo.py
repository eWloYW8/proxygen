import os
import yaml
import logging
from typing import Dict, Any, List
from app.core.config import settings

logger = logging.getLogger(__name__)

class ConfigRepo:
    def __init__(self):
        self.rules_dir = settings.RULES_DIR
        os.makedirs(self.rules_dir, exist_ok=True)

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        path = os.path.join(self.rules_dir, filename)
        if not os.path.exists(path):
            logger.warning(f"Configuration file not found: {path}")
            return {}
        
        try:
            with open(path, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file) or {}
        except Exception as e:
            logger.error(f"Error loading configuration file {path}: {e}")
            return {}

    def load_rules(self) -> Dict[str, Any]:
        return self._load_yaml("rules.yaml")

    def load_proxy_groups(self) -> Dict[str, Any]:
        return self._load_yaml("proxy-groups.yaml")
    
    def load_override_config(self, filename: str) -> Dict[str, Any]:
        """
        Load an override configuration file from the rules directory.
        If extension is missing, defaults to .yaml
        """
        if not filename:
            return {}
            
        clean_name = filename.strip()
        if not clean_name.lower().endswith(('.yaml', '.yml')):
            clean_name += ".yaml"
            
        return self._load_yaml(clean_name)

    def load_provider_file(self, relative_path: str) -> List[str]:
        clean_path = relative_path.strip()
        if clean_path.startswith("./"):
            clean_path = clean_path[2:]
        
        path = os.path.join(self.rules_dir, clean_path)
        
        if not os.path.exists(path):
            logger.warning(f"Rule provider file not found: {path}")
            return []
        
        try:
            with open(path, 'r', encoding='utf-8') as file:
                # Filter comments and empty lines
                return [line.strip() for line in file if line.strip() and not line.strip().startswith('#')]
        except Exception as e:
            logger.error(f"Error loading rule provider file {path}: {e}")
            return []

config_repo = ConfigRepo()
