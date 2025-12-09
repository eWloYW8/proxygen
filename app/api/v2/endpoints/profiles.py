# app/api/v2/endpoints/profiles.py

import logging
from fastapi import APIRouter, Query, HTTPException, Response
from typing import List, Optional

from app.core.config import settings
from app.services.profile_service import profile_service

router = APIRouter()

logger = logging.getLogger(__name__)

@router.get("/")
async def get_profiles(
    response: Response, 
    name: List[str] = Query(...), 
    api_key: str = Query(...),
    override: Optional[str] = Query(None, description="Filename in rules directory to override config (e.g. dns.yaml)")
):
    if api_key != settings.API_KEY:
        logger.warning(f"Unauthorized access attempt with API key: {api_key}")
        raise HTTPException(status_code=401, detail="Unauthorized access")

    full_config, sub_info = await profile_service.generate_multiple_profiles_with_config(name, override)

    logger.debug(f"Get sub_info for profiles {name}: {sub_info}")

    response.headers["Content-Disposition"] = f"inline; filename={name[0]}"
    if "upload" in sub_info and "expire" in sub_info:
        response.headers["subscription-userinfo"] = (
            f"upload={sub_info['upload']}; download={sub_info['download']}; total={sub_info['total']}; expire={sub_info.get('expire', '0')}"
        )

    return full_config

@router.put("/{profile}")
async def update_profile(profile: str, url: str = Query(...), api_key: str = Query(...)):
    if api_key != settings.API_KEY:
        logger.warning(f"Unauthorized access attempt with API key: {api_key}")
        raise HTTPException(status_code=401, detail="Unauthorized access")

    count = await profile_service.fetch_and_update_profile(profile, url)
    return {
        "status": "success",
        "message": f"Profile '{profile}' updated with {count} proxies."
    }