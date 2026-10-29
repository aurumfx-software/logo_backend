from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.auth import GenericMessageResponse
from app.schemas.wallet_payment import (
    RazorpayTopupOrderResponse,
    RazorpayTopupVerifyRequest,
    RazorpayTopupVerifyResponse,
    RazorpayWalletConfigResponse,
    WalletTopupCreateRequest,
    WalletTopupListItem,
    WalletTopupListResponse,
    WalletTopupOrderStatusResponse,
)
from app.services.razorpay_service import RazorpayService
from app.services.wallet_topup_service import WalletTopupService

router = APIRouter(prefix="/wallet/topup", tags=["Wallet Top-up (Razorpay)"])


@router.get(
    "/razorpay/config",
    response_model=RazorpayWalletConfigResponse,
    summary="Razorpay checkout config for wallet top-up",
    description="Returns public key id and min/max amounts for the merchant app checkout.",
)
def razorpay_wallet_config() -> RazorpayWalletConfigResponse:
    return WalletTopupService.get_checkout_config()


@router.post(
    "/razorpay/order",
    response_model=RazorpayTopupOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Merchant: create Razorpay order to add money to wallet",
)
def create_razorpay_wallet_topup_order(
    payload: WalletTopupCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RazorpayTopupOrderResponse:
    return WalletTopupService.create_razorpay_topup_order(
        db=db, user=current_user, payload=payload
    )


@router.post(
    "/razorpay/verify",
    response_model=RazorpayTopupVerifyResponse,
    summary="Merchant: verify Razorpay payment and credit wallet",
    description=(
        "Call after Razorpay checkout success with order_id, payment_id, and signature "
        "from the client SDK."
    ),
)
def verify_razorpay_wallet_topup(
    payload: RazorpayTopupVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RazorpayTopupVerifyResponse:
    return WalletTopupService.verify_and_credit(db=db, user=current_user, payload=payload)


@router.post(
    "/razorpay/webhook",
    response_model=GenericMessageResponse,
    summary="Razorpay webhook (payment captured)",
    description="Configure in Razorpay dashboard; verifies X-Razorpay-Signature header.",
)
async def razorpay_wallet_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_razorpay_signature: str = Header(default="", alias="X-Razorpay-Signature"),
) -> GenericMessageResponse:
    body = await request.body()
    RazorpayService.verify_webhook_signature(body, x_razorpay_signature)
    parsed = RazorpayService.parse_webhook_payment(body)
    if not parsed:
        return GenericMessageResponse(message="Webhook ignored (unsupported event).")
    result = WalletTopupService.process_webhook_payment(
        db=db,
        razorpay_order_id=parsed["razorpay_order_id"],
        razorpay_payment_id=parsed["razorpay_payment_id"],
    )
    if not result:
        return GenericMessageResponse(message="No matching wallet top-up order.")
    return GenericMessageResponse(message=result.message)


@router.get(
    "/orders",
    response_model=WalletTopupListResponse,
    summary="List my wallet top-up orders",
)
def list_wallet_topup_orders(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WalletTopupListResponse:
    rows = WalletTopupService.list_my_topups(db=db, user=current_user, limit=limit)
    return WalletTopupListResponse(
        data=[WalletTopupListItem.model_validate(r) for r in rows],
        message=f"Retrieved {len(rows)} top-up order(s)",
    )


@router.get(
    "/orders/{topup_id}",
    response_model=WalletTopupOrderStatusResponse,
    summary="Get wallet top-up order status",
)
def get_wallet_topup_order_status(
    topup_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WalletTopupOrderStatusResponse:
    return WalletTopupService.get_topup_status(db=db, user=current_user, topup_id=topup_id)
