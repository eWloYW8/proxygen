import os
import yaml
from typing import Dict, Any, Optional
from app.core.config import settings

class ProfileRepo:
    def __init__(self):
        self.base_path = settings.PROFILE_DIR
        os.makedirs(self.base_path, exist_ok=True)

    def _get_path(self, name: str) -> str:
        return os.path.join(self.base_path, f"{name}.yaml")
    
    def load_profile(self, name: str) -> Optional[Dict[str, Any]]:
        '''
        Load a profile by name.
        Args:
            name (str): The name of the profile to load.
        Returns:
            Optional[Dict[str, Any]]: The loaded profile data or None if not found.
        Raises:
            FileNotFoundError: If the profile does not exist.
            IOError: If there is an error reading the profile file.
        '''
        path = self._get_path(name)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Profile '{name}' does not exist.")
        
        try:
            with open(path, 'r') as file:
                profile = yaml.safe_load(file)
                return profile
        except Exception as e:
            raise IOError(f"Error loading profile '{name}': {e}")
        
    def save_profile(self, name: str, profile: Dict[str, Any]) -> None:
        '''
        Save a profile by name.
        Args:
            name (str): The name of the profile to save.
            profile (Dict[str, Any]): The profile data to save.
        Raises:
            IOError: If there is an error writing the profile file.
        '''
        path = self._get_path(name)
        try:
            with open(path, 'w', encoding='utf-8') as file:
                yaml.safe_dump(profile, file, default_flow_style=False, sort_keys=False, allow_unicode=True)
        except Exception as e:
            raise IOError(f"Error saving profile '{name}': {e}")
        
profile_repo = ProfileRepo()