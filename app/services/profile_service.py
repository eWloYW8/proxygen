import httpx
import logging
import re
from typing import List, Dict, Any, Tuple
from datetime import datetime
from fastapi import HTTPException, Depends
from yaml import safe_load

from app.repos.profile_repo import profile_repo
from app.services.clash_config_service import ClashConfigService

logger = logging.getLogger(__name__)

class ProfileService:
    def __init__(self, clash_config_service: ClashConfigService = Depends(ClashConfigService)):
        self.clash_config_service = clash_config_service

    async def generate_multiple_profiles_with_config(self, name: List[str]) -> Tuple[Dict[str, Any], Dict[str, str]]:
        logger.info(f"Generating multiple profiles: {name}")

        all_proxies = []
        subscription_info = {}

        # Load each profile and aggregate proxies
        for profile_name in name:
            try:
                profile = profile_repo.load_profile(profile_name)
                proxies = profile.get("proxies", [])
                if proxies:
                    all_proxies.extend(proxies)
                    
                    # Extract subscription info from proxy names
                    for proxy in proxies:
                        self._extract_subscription_info(proxy.get("name", ""), subscription_info)

            except FileNotFoundError:
                msg = f"Profile '{profile_name}' not found, skipping."
                logger.warning(msg)
                raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found.")
            except IOError as e:
                logger.error(f"Error loading profile '{profile_name}': {e}")
                raise HTTPException(status_code=500, detail=f"Error loading profile '{profile_name}'")

        full_config = self.clash_config_service.add_config_to_proxies(all_proxies)
                    
        return full_config, subscription_info

    def _extract_subscription_info(self, proxy_name: str, subscription_info = Dict[str, str]) -> None:        
        # Match Traffic info: e.g., "Traffic: 74.95 GB / 200 GB"
        traffic_match = re.search(r"(?:Traffic|流量).*?(\d+(?:\.\d+)?)\s*(GB|G).*?(\d+(?:\.\d+)?)\s*(GB|G)", proxy_name, re.IGNORECASE)
        if traffic_match:
            used_val, used_unit, total_val, total_unit = traffic_match.groups()
            
            multiplier = 1024**3 
            
            upload = 0 # Usually not distinguished in simple strings
            download = int(float(used_val) * multiplier)
            total = int(float(total_val) * multiplier)
            
            subscription_info["upload"] = str(upload)
            subscription_info["download"] = str(download)
            subscription_info["total"] = str(total)

        # Match Expire info: e.g., "Expire: 2026-01-04"
        expire_match = re.search(r"(?:Expire|到期|过期).*?(\d{4}-\d{2}-\d{2})", proxy_name, re.IGNORECASE)
        if expire_match:
            expire_date_str = expire_match.group(1)
            try:
                expire_ts = int(datetime.strptime(expire_date_str, "%Y-%m-%d").timestamp())
                subscription_info["expire"] = str(expire_ts)
            except ValueError:
                logger.warning(f"Invalid expire date format in proxy name: {proxy_name}")
        
    async def fetch_and_update_profile(self, name: str, url: str) -> int:
        logger.info(f"Fetching profile '{name}' from {url}")
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, timeout=10.0)
                response.raise_for_status()
            except httpx.RequestError as e:
                logger.error(f"Network error fetching profile from {url}: {e}")
                raise HTTPException(status_code=502, detail=f"Network error fetching profile: {e}")
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching profile from {url}: {e}")
                raise HTTPException(status_code=e.response.status_code, detail=f"Remote server error: {e}")

        external_config = safe_load(response.text) or {}
        proxies = external_config.get("proxies", [])

        if not proxies:
            logger.warning(f"No proxies found in remote URL: {url}")
            raise HTTPException(status_code=404, detail=f"No proxies found in remote URL")

        profile_data = {"proxies": proxies}

        try:
            profile_repo.save_profile(name, profile_data)
        except Exception as e:
            logger.error(f"Error saving profile '{name}': {e}")
            raise HTTPException(status_code=500, detail=f"Error saving profile: {e}")

        logger.info(f"Profile '{name}' updated with {len(proxies)} proxies")

        return len(proxies)