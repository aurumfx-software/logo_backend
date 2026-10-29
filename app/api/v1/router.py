from fastapi import APIRouter
from app.api.v1.endpoints import (
    admin,
    auth,
    category,
    customer,
    favorite,
    health,
    logo,
    merchant,
    notification,
    product,
    promotion,
    user,
    wallet,
    wallet_ws,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(customer.router)
api_router.include_router(product.router)
api_router.include_router(user.router)
api_router.include_router(merchant.router)
api_router.include_router(category.router)
api_router.include_router(promotion.router)
api_router.include_router(category.router, prefix="/field-staff", tags=["Field Staff Categories"])
api_router.include_router(logo.router)
api_router.include_router(favorite.router)
api_router.include_router(notification.router)
api_router.include_router(admin.router)
api_router.include_router(wallet.router)
api_router.include_router(wallet_ws.router)
