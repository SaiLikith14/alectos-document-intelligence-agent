from fastapi import APIRouter
from app.core.config import get_settings
from app.schemas.common import HealthResponse

router = APIRouter(tags=['health'])


@router.get('/health', response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status='ok', service=get_settings().app_name)
