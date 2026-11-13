from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_admin_user_flexible, get_current_user_optional
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.commerce import (
    AddressRequest,
    AddressResponse,
    AddressUpdateRequest,
    CartCheckoutRequest,
    CartItemInput,
    CartResponse,
    CartSyncRequest,
    DispatchUpdateRequest,
    OrderPaymentRequest,
    OrderPaymentResponse,
    OrderPaymentVerifyRequest,
    OrderTrackingResponse,
    ReviewCreateRequest,
    ReviewListResponse,
    ReviewResponse,
    WishlistResponse,
)
from app.schemas.product import (
    ProductCreateRequest,
    ProductUpdateRequest,
    ProductAdminStatusUpdate,
    ProductResponse,
    DeliveryStepResponse,
    MarketplacePageResponse,
    OrderCreateRequest,
    OrderResponse,
    OrderCancelRequest,
    OrderHistoryResponse,
    OrderStatusUpdateRequest,
    SellerPermissionToggleRequest,
)
from app.services.buyer_commerce_service import BuyerCommerceService
from app.services.product_service import ProductService, normalize_order_status

router = APIRouter(tags=["Community Products & Marketplace"])


def _product_response(product) -> ProductResponse:
    item = ProductResponse.model_validate(product)
    quantity = product.stock_quantity
    item.stock_quantity = quantity
    item.in_stock = bool(
        product.is_active
        and (product.approval_status or "").upper() == "APPROVED"
        and (product.stock_status or "").upper() != "OUT_OF_STOCK"
        and (quantity is None or quantity > 0)
    )
    count = int(getattr(product, "rating_count", 0) or 0)
    item.rating_count = count
    item.rating_average = round((getattr(product, "rating_sum", 0) or 0) / count, 2) if count else 0
    return item


def _order_response(order, whatsapp_url: Optional[str] = None) -> OrderResponse:
    product = order.product
    item = OrderResponse.model_validate(order)
    item.product_name = product.name if product else None
    item.product_image = product.images[0] if (product and product.images) else None
    item.seller_name = product.seller_name if product else None
    item.seller_phone = product.seller_phone if product else None
    item.seller_whatsapp = product.seller_whatsapp if product else None
    item.whatsapp_url = whatsapp_url
    item.status = normalize_order_status(order.status or "PLACED")
    item.status_label = next(
        (label for key, label in (
            ("PLACED", "Order placed"),
            ("CONFIRMED", "Seller confirmed"),
            ("SHIPPED", "Shipped"),
            ("OUT_FOR_DELIVERY", "Out for delivery"),
            ("DELIVERED", "Delivered"),
            ("CANCELLED", "Cancelled"),
        ) if key == item.status),
        item.status,
    )
    item.delivery_steps = [DeliveryStepResponse(**step) for step in ProductService.delivery_steps(order)]
    item.payment_status = (getattr(order, "payment_status", None) or "UNPAID").upper()
    return item


@router.get(
    "/marketplace",
    response_model=MarketplacePageResponse,
    summary="Shop page: any listed item a customer can buy",
)
def get_marketplace_page(
    category: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None, description="newest, price_asc, price_desc, popular"),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> MarketplacePageResponse:
    products = ProductService.get_public_products(
        db=db,
        category=category,
        district=district,
        search=search,
        sort_by=sort_by,
        min_price=min_price,
        max_price=max_price,
        limit=limit,
        offset=offset,
    )
    total = ProductService.count_public_products(
        db=db,
        category=category,
        district=district,
        search=search,
        min_price=min_price,
        max_price=max_price,
    )
    return MarketplacePageResponse(
        categories=ProductService.get_product_categories(db=db),
        products=[_product_response(p) for p in products],
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(products) < total,
        delivery_steps=[
            "Order placed",
            "Seller confirmed",
            "Shipped",
            "Out for delivery",
            "Delivered",
        ],
    )


@router.post(
    "/marketplace/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Buy a listed item",
)
def buy_marketplace_item(
    data: OrderCreateRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> OrderResponse:
    order, whatsapp_url = ProductService.create_order(db=db, data=data, buyer=current_user)
    return _order_response(order, whatsapp_url)


@router.get(
    "/marketplace/orders",
    response_model=List[OrderResponse],
    summary="My purchases and delivery status",
)
def list_my_purchases(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> List[OrderResponse]:
    if current_user is None:
        return []
    orders, _total = ProductService.get_buyer_orders(
        db, current_user, status_filter=status_filter, limit=limit, offset=offset
    )
    return [_order_response(order) for order in orders]


@router.get(
    "/marketplace/orders/history",
    response_model=OrderHistoryResponse,
    summary="Buyer order history",
)
def buyer_order_history(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> OrderHistoryResponse:
    if current_user is None:
        return OrderHistoryResponse(limit=limit, offset=offset)
    orders, total = ProductService.get_buyer_orders(
        db, current_user, status_filter=status_filter, limit=limit, offset=offset
    )
    return OrderHistoryResponse(
        orders=[_order_response(order) for order in orders],
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(orders) < total,
    )


@router.get(
    "/marketplace/orders/{order_id}",
    response_model=OrderResponse,
    summary="One purchase with the delivery steps",
)
def get_my_purchase(
    order_id: int,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> OrderResponse:
    if current_user is None:
        order = ProductService.get_order_by_id(db, order_id)
    else:
        order = ProductService.get_buyer_order(db, current_user, order_id)
    return _order_response(order)


@router.get(
    "/marketplace/orders/{order_id}/tracking",
    response_model=OrderTrackingResponse,
    summary="Live delivery tracking for one purchase",
)
def track_my_purchase(
    order_id: int,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> OrderTrackingResponse:
    return BuyerCommerceService.tracking(db, current_user, order_id)


@router.post(
    "/marketplace/orders/{order_id}/cancel",
    response_model=OrderResponse,
    summary="Buyer cancels an order before it is shipped",
)
def cancel_my_purchase(
    order_id: int,
    data: Optional[OrderCancelRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderResponse:
    reason = data.reason if data else None
    return _order_response(ProductService.cancel_buyer_order(db, current_user, order_id, reason))


@router.post(
    "/marketplace/orders/{order_id}/pay",
    response_model=OrderPaymentResponse,
    summary="Start Razorpay, UPI, or cash-on-delivery payment",
)
def pay_for_order(
    order_id: int,
    data: OrderPaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderPaymentResponse:
    return BuyerCommerceService.start_payment(db, current_user, order_id, data.method)


@router.post(
    "/marketplace/orders/{order_id}/pay/verify",
    response_model=OrderPaymentResponse,
    summary="Verify a Razorpay or UPI payment and mark the order paid",
)
def verify_order_payment(
    order_id: int,
    data: OrderPaymentVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderPaymentResponse:
    return BuyerCommerceService.verify_payment(
        db,
        current_user,
        order_id,
        data.razorpay_order_id,
        data.razorpay_payment_id,
        data.razorpay_signature,
    )


@router.post(
    "/marketplace/orders/{order_id}/review",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Rate a delivered order",
)
def review_my_purchase(
    order_id: int,
    data: ReviewCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewResponse:
    review = BuyerCommerceService.create_review(db, current_user, order_id, data)
    item = ReviewResponse.model_validate(review)
    item.buyer_name = current_user.name
    return item


@router.get("/marketplace/wishlist", response_model=WishlistResponse, summary="My saved products")
def list_wishlist(
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> WishlistResponse:
    if current_user is None:
        return WishlistResponse()
    return BuyerCommerceService.list_wishlist(db, current_user)


@router.post("/marketplace/wishlist/{product_id}", response_model=WishlistResponse, summary="Save a product")
def save_wishlist(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WishlistResponse:
    return BuyerCommerceService.add_wishlist(db, current_user, product_id)


@router.delete("/marketplace/wishlist/{product_id}", response_model=WishlistResponse, summary="Remove a saved product")
def delete_wishlist(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WishlistResponse:
    return BuyerCommerceService.remove_wishlist(db, current_user, product_id)


@router.get("/marketplace/addresses", response_model=List[AddressResponse], summary="Saved delivery addresses")
def list_addresses(
    current_user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)
) -> List[AddressResponse]:
    if current_user is None:
        return []
    return [AddressResponse.model_validate(row) for row in BuyerCommerceService.list_addresses(db, current_user)]


@router.post(
    "/marketplace/addresses",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a delivery address",
)
def create_address(
    data: AddressRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AddressResponse:
    return AddressResponse.model_validate(BuyerCommerceService.create_address(db, current_user, data))


@router.patch("/marketplace/addresses/{address_id}", response_model=AddressResponse, summary="Update a delivery address")
def update_address(
    address_id: int,
    data: AddressUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AddressResponse:
    return AddressResponse.model_validate(BuyerCommerceService.update_address(db, current_user, address_id, data))


@router.delete("/marketplace/addresses/{address_id}", summary="Delete a delivery address")
def delete_address(
    address_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    BuyerCommerceService.delete_address(db, current_user, address_id)
    return {"success": True, "message": "Address removed."}


@router.get("/marketplace/cart", response_model=CartResponse, summary="Current server-side cart")
def get_cart(
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> CartResponse:
    if current_user is None:
        return CartResponse()
    return BuyerCommerceService.get_cart(db, current_user)


@router.put("/marketplace/cart", response_model=CartResponse, summary="Replace the cart from the device")
def sync_cart(
    data: CartSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CartResponse:
    return BuyerCommerceService.sync_cart(db, current_user, data.items)


@router.post("/marketplace/cart/items", response_model=CartResponse, summary="Add one item to the cart")
def add_cart_item(
    data: CartItemInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CartResponse:
    return BuyerCommerceService.add_cart_item(db, current_user, data)


@router.patch("/marketplace/cart/items/{item_id}", response_model=CartResponse, summary="Change a cart quantity")
def update_cart_item(
    item_id: int,
    quantity: int = Query(..., ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CartResponse:
    return BuyerCommerceService.update_cart_item(db, current_user, item_id, quantity)


@router.delete("/marketplace/cart/items/{item_id}", response_model=CartResponse, summary="Remove a cart item")
def remove_cart_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CartResponse:
    return BuyerCommerceService.remove_cart_item(db, current_user, item_id)


@router.delete("/marketplace/cart", response_model=CartResponse, summary="Empty the cart")
def clear_cart(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> CartResponse:
    return BuyerCommerceService.clear_cart(db, current_user)


@router.post("/marketplace/cart/checkout", response_model=List[OrderResponse], summary="Place orders for everything in the cart")
def checkout_cart(
    data: CartCheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[OrderResponse]:
    orders, failed = BuyerCommerceService.checkout_cart(db, current_user, data.address_id, data.notes)
    if not orders and failed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="; ".join(failed))
    return [_order_response(order) for order in orders]


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
    sort_by: Optional[str] = Query(None, description="Sorting: newest, price_asc, price_desc, popular"),
    min_price: Optional[float] = Query(None, description="Minimum price filter"),
    max_price: Optional[float] = Query(None, description="Maximum price filter"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    products = ProductService.get_public_products(
        db=db,
        category=category,
        district=district,
        search=search,
        sort_by=sort_by,
        min_price=min_price,
        max_price=max_price,
        limit=limit,
        offset=offset,
    )
    return [_product_response(p) for p in products]


@router.get(
    "/products/categories",
    response_model=List[str],
    summary="List All Distinct Product Categories",
)
def get_product_categories(
    db: Session = Depends(get_db),
) -> List[str]:
    return ProductService.get_product_categories(db=db)


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
    return _product_response(product)


@router.get(
    "/products/{id}/reviews",
    response_model=ReviewListResponse,
    summary="Ratings and reviews for a product",
)
def list_product_reviews(id: int, db: Session = Depends(get_db)) -> ReviewListResponse:
    return BuyerCommerceService.list_product_reviews(db, id)


@router.post(
    "/products/order",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Place Product Order (Sends details directly to Seller)",
)
def place_product_order(
    data: OrderCreateRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    order, whatsapp_url = ProductService.create_order(db=db, data=data, buyer=current_user)
    return _order_response(order, whatsapp_url)


# =========================================================================
# SELLER / SUBSCRIBER CUSTOMER ENDPOINTS
# =========================================================================

@router.post(
    "/customer/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Any customer lists an item for sale",
)
def create_customer_product(
    data: ProductCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    product = ProductService.create_product(db=db, seller=current_user, data=data)
    return _product_response(product)


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
    return [_product_response(p) for p in products]


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
    return _product_response(product)


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
    return [_order_response(order) for order in orders]


@router.get(
    "/customer/products/orders/{id}",
    response_model=OrderResponse,
    summary="Get Seller Order Full Details",
)
def get_seller_order_detail(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = ProductService.get_seller_order_by_id(db=db, seller_id=current_user.id, order_id=id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order #{id} not found.",
        )
    return _order_response(order)


@router.put(
    "/customer/products/orders/{id}/status",
    response_model=OrderResponse,
    summary="Seller updates delivery status",
)
def update_seller_order_status(
    id: int,
    data: OrderStatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = ProductService.update_seller_order_status(
        db=db, seller_id=current_user.id, order_id=id, new_status=data.status, notes=data.notes
    )
    return _order_response(order)


@router.put(
    "/customer/products/orders/{id}/dispatch",
    response_model=OrderResponse,
    summary="Seller assigns a courier and records a tracking event",
)
def dispatch_seller_order(
    id: int,
    data: DispatchUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = BuyerCommerceService.dispatch(db, current_user, id, data)
    return _order_response(order)


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
    return [_product_response(p) for p in products]


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
    return _product_response(product)


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
        out.append(_order_response(o))
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
