from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    get_admin_user_flexible,
    get_db,
)
from app.db.models.user import User
from app.schemas.product import (
    ProductCreateRequest,
    ProductUpdateRequest,
    ProductAdminStatusUpdate,
    ProductResponse,
    OrderCreateRequest,
    OrderResponse,
    SellerPermissionToggleRequest,
)
from app.services.product_service import ProductService

router = APIRouter(tags=["Community Products & Marketplace"])


# =========================================================================
# PUBLIC ENDPOINTS (FOR LANDING PAGE & SHOPPERS)
# =========================================================================

@router.get(
    "/products",
    response_model=List[ProductResponse],
    summary="List Approved & Active Products for Landing Page Showcase",
)
def get_public_products(
    category: Optional[str] = Query(None, description="Filter by category"),
    district: Optional[str] = Query(None, description="Filter by district"),
    search: Optional[str] = Query(None, description="Keyword search in product title/desc"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    products = ProductService.get_public_products(
        db=db, category=category, district=district, search=search, limit=limit, offset=offset
    )
    return [ProductResponse.model_validate(p) for p in products]


@router.get(
    "/products/{id}",
    response_model=ProductResponse,
    summary="Get Product Details by ID",
)
def get_product_by_id(
    id: int,
    db: Session = Depends(get_db),
):
    product = ProductService.get_product_by_id(db=db, product_id=id)
    return ProductResponse.model_validate(product)


@router.post(
    "/products/order",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Place Product Order (Sends details directly to Seller)",
)
def place_product_order(
    data: OrderCreateRequest,
    db: Session = Depends(get_db),
):
    order, whatsapp_url = ProductService.create_order(db=db, data=data)
    product = order.product
    resp = OrderResponse.model_validate(order)
    resp.product_name = product.name if product else None
    resp.product_image = product.images[0] if (product and product.images) else None
    resp.seller_name = product.seller_name if product else None
    resp.seller_phone = product.seller_phone if product else None
    resp.seller_whatsapp = product.seller_whatsapp if product else None
    resp.whatsapp_url = whatsapp_url
    return resp


# =========================================================================
# SELLER / SUBSCRIBER CUSTOMER ENDPOINTS
# =========================================================================

@router.post(
    "/customer/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subscribed Customer Adds Product to Sell",
)
def create_customer_product(
    data: ProductCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    product = ProductService.create_product(db=db, seller=current_user, data=data)
    return ProductResponse.model_validate(product)


@router.get(
    "/customer/products/my-products",
    response_model=List[ProductResponse],
    summary="List Current Seller's Listed Products",
)
def get_my_products(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    products = ProductService.get_seller_products(db=db, seller_id=current_user.id)
    return [ProductResponse.model_validate(p) for p in products]


@router.put(
    "/customer/products/{id}",
    response_model=ProductResponse,
    summary="Update Listed Product",
)
def update_customer_product(
    id: int,
    data: ProductUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    product = ProductService.update_product(db=db, product_id=id, user=current_user, data=data)
    return ProductResponse.model_validate(product)


@router.delete(
    "/customer/products/{id}",
    summary="Delete Listed Product",
)
def delete_customer_product(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    success = ProductService.delete_product(db=db, product_id=id, user=current_user)
    return {"success": success, "message": "Product deleted successfully"}


@router.get(
    "/customer/products/my-orders",
    response_model=List[OrderResponse],
    summary="List Orders Received by Current Seller",
)
def get_my_orders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    orders = ProductService.get_seller_orders(db=db, seller_id=current_user.id)
    out = []
    for o in orders:
        item = OrderResponse.model_validate(o)
        if o.product:
            item.product_name = o.product.name
            item.product_image = o.product.images[0] if o.product.images else None
        out.append(item)
    return out


# =========================================================================
# ADMIN CONTROLS (ALLOW / DENY, ON / OFF TOGGLE, SELLER PERMISSION)
# =========================================================================

@router.get(
    "/admin/products",
    response_model=List[ProductResponse],
    summary="Admin: List All Products with Approval & Active Status",
)
def list_admin_products(
    status: Optional[str] = Query(None, description="Filter by approval status (APPROVED, DENIED, PENDING, all)"),
    is_active: Optional[bool] = Query(None, description="Filter by on/off active status"),
    search: Optional[str] = Query(None, description="Search keyword in product or seller"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    products = ProductService.get_all_products_admin(
        db=db, status_filter=status, is_active=is_active, search=search, limit=limit, offset=offset
    )
    return [ProductResponse.model_validate(p) for p in products]


@router.put(
    "/admin/products/{id}/status",
    response_model=ProductResponse,
    summary="Admin: Toggle Product On/Off and Allow/Deny Approval Status",
)
def toggle_admin_product_status(
    id: int,
    data: ProductAdminStatusUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    product = ProductService.toggle_product_status(db=db, product_id=id, data=data)
    return ProductResponse.model_validate(product)


@router.delete(
    "/admin/products/{id}",
    summary="Admin: Remove Product Listing",
)
def delete_admin_product(
    id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    success = ProductService.delete_product(db=db, product_id=id, user=admin)
    return {"success": success, "message": "Product listing removed by admin"}


@router.get(
    "/admin/products/orders",
    response_model=List[OrderResponse],
    summary="Admin: View All Customer Orders Across Kerala",
)
def list_admin_orders(
    status: Optional[str] = Query(None, description="Filter by order status"),
    search: Optional[str] = Query(None, description="Search by order code, buyer name, or phone"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    orders = ProductService.get_all_orders_admin(
        db=db, status_filter=status, search=search, limit=limit, offset=offset
    )
    out = []
    for o in orders:
        item = OrderResponse.model_validate(o)
        if o.product:
            item.product_name = o.product.name
            item.product_image = o.product.images[0] if o.product.images else None
            item.seller_name = o.product.seller_name
            item.seller_phone = o.product.seller_phone
        out.append(item)
    return out


@router.put(
    "/admin/users/{user_id}/seller-permission",
    summary="Admin: Toggle ₹500 Customer Seller Permission (Allow / Deny Selling)",
)
def toggle_customer_seller_permission(
    user_id: int,
    data: SellerPermissionToggleRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    user = ProductService.toggle_seller_permission(db=db, user_id=user_id, data=data)
    return {
        "success": True,
        "message": f"Seller permission updated for {user.name}.",
        "user_id": user.id,
        "can_sell_products": user.can_sell_products,
        "is_subscriber": user.is_subscriber,
        "subscription_plan": user.subscription_plan,
    }
