from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.wallet import (
    AdminWalletAdjustRequest,
    AdminWalletAdjustResponse,
    SaleQRCreateRequest,
    SaleQRCreateResponse,
    SaleQRMerchantStatusResponse,
    SaleQRPreviewResponse,
    SaleRedeemRequest,
    SaleRedeemResponse,
    WalletMeResponse,
    WalletTransactionListResponse,
    WalletTopUpRequest,
    WalletTopUpResponse,
    WalletTransferRequest,
    WalletTransferResponse,
)
from app.services.wallet_service import WalletService

router = APIRouter(prefix="/wallet", tags=["Wallet"])


@router.get(
    "/me",
    response_model=WalletMeResponse,
    summary="Get my wallet balance",
)
def get_my_wallet(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WalletMeResponse:
    wallet = WalletService.get_my_wallet(db=db, user=current_user)
    return WalletMeResponse(wallet=wallet)


@router.get(
    "/transactions",
    response_model=WalletTransactionListResponse,
    summary="List my wallet transactions",
)
def list_my_wallet_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WalletTransactionListResponse:
    items, total = WalletService.list_transactions(
        db=db, user=current_user, page=page, page_size=page_size
    )
    return WalletTransactionListResponse(
        data=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/transfer",
    response_model=WalletTransferResponse,
    status_code=status.HTTP_200_OK,
    summary="Transfer money wallet to wallet",
)
def wallet_transfer(
    payload: WalletTransferRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WalletTransferResponse:
    return WalletService.transfer_wallet_to_wallet(db=db, sender=current_user, payload=payload)


@router.get(
    "/topup",
    response_model=WalletMeResponse,
    summary="Wallet top-up account",
    description="Returns the authenticated user's wallet. Add money with POST /wallet/topup.",
)
def get_wallet_topup(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WalletMeResponse:
    wallet = WalletService.get_my_wallet(db=db, user=current_user)
    return WalletMeResponse(message="Use POST to add money to this wallet", wallet=wallet)


@router.post(
    "/topup",
    response_model=WalletTopUpResponse,
    status_code=status.HTTP_200_OK,
    summary="Top up / add money to wallet",
    description="Credits the authenticated customer or merchant wallet.",
)
def top_up_wallet(
    payload: WalletTopUpRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WalletTopUpResponse:
    return WalletService.top_up_wallet(db=db, user=current_user, payload=payload)


@router.post(
    "/sales/qr",
    response_model=SaleQRCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Merchant: create sale QR for cashback redemption",
)
def create_sale_qr(
    payload: SaleQRCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SaleQRCreateResponse:
    return WalletService.create_sale_qr(db=db, merchant_user=current_user, payload=payload)


@router.get(
    "/sales/qr/{token}/status",
    response_model=SaleQRMerchantStatusResponse,
    summary="Merchant: poll sale QR payment status",
    description=(
        "For the merchant QR screen: poll every 2–3 seconds while waiting, or use "
        "WebSocket GET /api/v1/wallet/ws?token=<JWT> and listen for event sale_qr.redeemed. "
        "When is_redeemed is true, show success and stop polling."
    ),
)
def merchant_sale_qr_status(
    token: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SaleQRMerchantStatusResponse:
    return WalletService.get_merchant_sale_qr_status(
        db=db, merchant_user=current_user, token=token
    )


@router.get(
    "/sales/qr/{token}",
    response_model=SaleQRPreviewResponse,
    summary="Preview sale QR before redeeming cashback",
)
def preview_sale_qr(
    token: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SaleQRPreviewResponse:
    return WalletService.preview_sale_qr(db=db, token=token)


@router.post(
    "/sales/redeem",
    response_model=SaleRedeemResponse,
    summary="Customer: redeem sale cashback to wallet",
)
def redeem_sale_cashback(
    payload: SaleRedeemRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SaleRedeemResponse:
    return WalletService.redeem_sale_cashback(
        db=db, customer=current_user, token=payload.token.strip()
    )


@router.post(
    "/admin/adjust",
    response_model=AdminWalletAdjustResponse,
    summary="Admin: credit or debit a user wallet (funding / corrections)",
)
def admin_adjust_wallet(
    payload: AdminWalletAdjustRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminWalletAdjustResponse:
    wallet, group_id, txn_type = WalletService.admin_adjust_wallet(
        db=db,
        admin_user=admin_user,
        target_user_id=payload.user_id,
        amount=payload.amount,
        operation=payload.operation,
        note=payload.note,
    )
    return AdminWalletAdjustResponse(
        message=f"Wallet {payload.operation} successful",
        wallet=wallet,
        transaction_group_id=group_id,
        transaction_type=txn_type,
    )
