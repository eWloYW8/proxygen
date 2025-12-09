# app/services/profile_service.py

import httpx
import logging
import re
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from fastapi import HTTPException, Depends
from yaml import safe_load

from app.repos.profile_repo import profile_repo
from app.repos.config_repo import config_repo
from app.services.clash_config_service import ClashConfigService

logger = logging.getLogger(__name__)

class ProfileService:
    def __init__(self, clash_config_service: ClashConfigService = Depends(ClashConfigService)):
        self.clash_config_service = clash_config_service

    async def generate_multiple_profiles_with_config(self, name: List[str], override: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, str]]:
        logger.info(f"Generating multiple profiles: {name} (Override: {override})")

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
                    # This works because fetch_and_update_profile now injects this info into a dummy proxy
                    for proxy in proxies:
                        self._extract_subscription_info(proxy.get("name", ""), subscription_info)

            except FileNotFoundError:
                msg = f"Profile '{profile_name}' not found, skipping."
                logger.warning(msg)
                # We assume the user might want to generate even if one sub is missing, 
                # but raising 404 is also valid depending on requirement.
                # raising 404 here to match original logic strictness:
                raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found.")
            except IOError as e:
                logger.error(f"Error loading profile '{profile_name}': {e}")
                raise HTTPException(status_code=500, detail=f"Error loading profile '{profile_name}'")

        override_data = {}
        if override:
            override_data = config_repo.load_override_config(override)
            if not override_data:
                logger.warning(f"Override file '{override}' provided but content is empty or file missing.")

        full_config = self.clash_config_service.add_config_to_proxies(all_proxies, override_data)
                    
        return full_config, subscription_info

    def _extract_subscription_info(self, proxy_name: str, subscription_info: Dict[str, str]) -> None:        
        # Match Traffic info: e.g., "Traffic: 74.95 GB / 200 GB"
        # Optimized regex to catch Chinese "流量" as well
        traffic_match = re.search(r"(?:Traffic|流量).*?(\d+(?:\.\d+)?)\s*(GB|G|MB|M).*?(\d+(?:\.\d+)?)\s*(GB|G|MB|M)", proxy_name, re.IGNORECASE)
        
        if traffic_match:
            used_val, used_unit, total_val, total_unit = traffic_match.groups()
            
            def to_bytes(val, unit):
                unit = unit.upper()
                multiplier = 1024**3 if 'G' in unit else 1024**2
                return int(float(val) * multiplier)

            # Note: Subscription headers usually give total used (up+down). 
            # We assume it's download for simplicity or split it if needed.
            download = to_bytes(used_val, used_unit)
            total = to_bytes(total_val, total_unit)
            
            subscription_info["upload"] = "0" 
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
        
        # 1. Use a compatible User-Agent to avoid blocks
        headers = {
            "User-Agent": "Clash.Meta/1.18.1 Proxygen/0.1.0",
            "Accept": "application/x-yaml, text/yaml, text/plain",
        }
        
        async with httpx.AsyncClient(verify=False) as client:
            try:
                response = await client.get(url, headers=headers, timeout=30.0, follow_redirects=True)
                response.raise_for_status()
            except httpx.RequestError as e:
                logger.error(f"Network error fetching profile from {url}: {e}")
                raise HTTPException(status_code=502, detail=f"Network error fetching profile: {e}")
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching profile from {url}: {e}")
                raise HTTPException(status_code=e.response.status_code, detail=f"Remote server error: {e}")

        # 2. Parse YAML safely
        try:
            external_config = safe_load(response.text)
        except Exception as e:
            logger.warning(f"Failed to parse YAML: {e}")
            external_config = None

        # 3. Validation: Check if it's a valid Clash config (dict with 'proxies')
        if not isinstance(external_config, dict) or "proxies" not in external_config:
            # Common error: User provided a raw Base64 subscription link (vmess://...)
            # Since we are not a SubConverter, we can't parse raw links easily.
            detail_msg = "Invalid subscription format. URL must return a Clash YAML configuration."
            if isinstance(external_config, str) or external_config is None:
                detail_msg += " Detected non-YAML content (possibly Base64). Please use a conversion service (Subconverter) to get a '&flag=clash' URL."
            
            logger.error(f"Profile content invalid for url: {url}")
            raise HTTPException(status_code=400, detail=detail_msg)

        proxies = external_config.get("proxies", [])

        if not proxies:
            logger.warning(f"No proxies found in remote URL: {url}")
            raise HTTPException(status_code=404, detail=f"No proxies found in remote URL")

        # 4. Handle Subscription-Userinfo Header
        # Inject a dummy proxy node so that metadata is preserved in the file 
        # and can be read back by _extract_subscription_info later.
        user_info_header = response.headers.get("subscription-userinfo")
        if user_info_header:
            logger.info(f"Found subscription info header: {user_info_header}")
            dummy_proxy = self._create_traffic_proxy_node(user_info_header)
            if dummy_proxy:
                # Remove any existing dummy traffic nodes to prevent duplicates
                proxies = [p for p in proxies if not self._is_traffic_node(p)]
                # Insert at the top
                proxies.insert(0, dummy_proxy)

        profile_data = {"proxies": proxies}

        try:
            profile_repo.save_profile(name, profile_data)
        except Exception as e:
            logger.error(f"Error saving profile '{name}': {e}")
            raise HTTPException(status_code=500, detail=f"Error saving profile: {e}")

        logger.info(f"Profile '{name}' updated with {len(proxies)} proxies")

        return len(proxies)

    def _is_traffic_node(self, proxy: Dict[str, Any]) -> bool:
        name = proxy.get("name", "")
        return "Traffic" in name or "流量" in name or "Expire" in name or "到期" in name

    def _create_traffic_proxy_node(self, header_str: str) -> Optional[Dict[str, Any]]:
        """
        Parses 'upload=123; download=456; total=789; expire=123456' 
        and creates a dummy SS proxy named 'Traffic: X GB / Y GB | Expire: YYYY-MM-DD'
        """
        try:
            info = {}
            parts = header_str.split(';')
            for part in parts:
                if '=' in part:
                    k, v = part.strip().split('=', 1)
                    info[k.strip()] = int(v.strip())
            
            upload = info.get('upload', 0)
            download = info.get('download', 0)
            total = info.get('total', 0)
            expire = info.get('expire', 0)

            used_gb = (upload + download) / (1024**3)
            total_gb = total / (1024**3)
            
            name_parts = [f"Traffic: {used_gb:.2f} GB / {total_gb:.2f} GB"]
            
            if expire:
                expire_date = datetime.fromtimestamp(expire).strftime("%Y-%m-%d")
                name_parts.append(f"Expire: {expire_date}")

            final_name = " | ".join(name_parts)

            # Return a dummy Shadowsocks node that won't actually work but holds the name
            return {
                "name": final_name,
                "type": "ss",
                "server": "127.0.0.1",
                "port": 1234,
                "cipher": "aes-128-gcm",
                "password": "dummy"
            }
        except Exception as e:
            logger.warning(f"Failed to parse subscription header '{header_str}': {e}")
            return None