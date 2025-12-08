# app/api/v2/api.py

from fastapi import APIRouter
from app.api.v2.endpoints import profiles

router = APIRouter()

router.include_router(profiles.router, prefix="/profiles")