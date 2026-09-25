from fastapi import APIRouter
from app.api.v1.endpoints import (
    admin,
    auth,
    category,
    favorite,
    health,
    logo,
    merchant,
    notification,
    user,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(user.router)
api_router.include_router(merchant.router)
api_router.include_router(category.router)
api_router.include_router(category.router, prefix="/field-staff", tags=["Field Staff Categories"])
api_router.include_router(logo.router)
api_router.include_router(favorite.router)
api_router.include_router(notification.router)
api_router.include_router(admin.router)
