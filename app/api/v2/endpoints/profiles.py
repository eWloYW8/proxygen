# app/api/v2/endpoints/profiles.py

import logging
from fastapi import APIRouter, Query, HTTPException, Response, Depends
from typing import List, Optional

from app.core.config import settings
from app.services.profile_service import ProfileService

router = APIRouter()

logger = logging.getLogger(__name__)

async def verify_api_key(api_key: Optional[str] = Query(None)):
    if settings.USE_API_KEY:
        if not api_key or api_key != settings.API_KEY:
            raise HTTPException(status_code=403, detail="Invalid API Key")

@router.get("/")
async def get_profiles(response: Response,
                       name: List[str] = Query(...),
                       profile_service: ProfileService = Depends(ProfileService),
                       _: None = Depends(verify_api_key)):
    full_config, sub_info = await profile_service.generate_multiple_profiles_with_config(name)
    
    logger.debug(f"Get sub_info for profiles {name}: {sub_info}")

    response.headers["Content-Disposition"] = f"inline; filename={name[0]}"
    if "upload" in sub_info and "expire" in sub_info:
        response.headers["subscription-userinfo"] = (
            f"upload={sub_info['upload']}; download={sub_info['download']}; total={sub_info['total']}; expire={sub_info.get('expire', '0')}"
        )

    return full_config

@router.put("/{profile}")
async def update_profile(profile: str, 
                         url: str = Query(...), 
                         profile_service: ProfileService = Depends(ProfileService),
                         _: None = Depends(verify_api_key)):
    count = await profile_service.fetch_and_update_profile(profile, url)
    return {
        "status": "success",
        "message": f"Profile '{profile}' updated with {count} proxies."
    }