from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.response import StandardListResponse, list_response
from app.schemas.wallet import (
    AdminWalletAdjustRequest,
    AdminWalletAdjustResponse,
    PlatformWalletResponse,
    SaleQRCreateRequest,
    SaleQRCreateResponse,
    SaleQRMerchantStatusResponse,
    SaleQRPreviewResponse,
    SaleRedeemRequest,
    SaleRedeemResponse,
    WalletMeResponse,
    WalletRewardClaimResponse,
    WalletTransactionListResponse,
    WalletTopUpRequest,
    WalletTopUpResponse,
    WalletTransferRequest,
    WalletTransferResponse,
    WalletWithdrawalRequest,
    WalletWithdrawalResponse,
    AdminWalletTransactionListResponse,
)
from app.services.wallet_service import WalletService

router = APIRouter(prefix="/wallet", tags=["Wallet"])


@router.post("/withdrawals", response_model=WalletWithdrawalResponse, status_code=status.HTTP_202_ACCEPTED,
             summary="Withdraw wallet balance to a bank account")
def withdraw_wallet(payload: WalletWithdrawalRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WalletService.create_wallet_withdrawal(db, current_user, payload)


@router.get("/withdrawals/{transaction_group_id}", response_model=WalletWithdrawalResponse,
            summary="Get bank withdrawal status")
def withdrawal_status(transaction_group_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WalletService.get_withdrawal_status(db, current_user, transaction_group_id)


@router.post("/webhooks/razorpayx", status_code=status.HTTP_200_OK, include_in_schema=False)
async def razorpayx_webhook(request: Request, db: Session = Depends(get_db),
                            signature: str = Header("", alias="X-Razorpay-Signature")):
    WalletService.process_razorpayx_webhook(db, await request.body(), signature)
    return {"success": True}


@router.get("/admin/transactions", response_model=AdminWalletTransactionListResponse,
            summary="Admin: list complete wallet transactions")
def admin_wallet_transactions(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                              admin_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    items, total = WalletService.admin_list_transactions(db, page, page_size)
    return AdminWalletTransactionListResponse(data=items, total=total, page=page, page_size=page_size)


@router.get(
    "/platform",
    response_model=PlatformWalletResponse,
    summary="Admin: platform company wallet and fee ledger",
    description=(
        "Fills the Platform Wallet screen: company balance, default 3/2/5 split, "
        "platform revenue, cashback paid, gross sales, QR redemption count, "
        "and the company ledger of fee credits."
    ),
)
def get_platform_wallet(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PlatformWalletResponse:
    return WalletService.get_platform_wallet(db=db, page=page, page_size=page_size)


@router.get(
    "/company",
    response_model=PlatformWalletResponse,
    summary="Admin: platform company wallet and fee ledger",
    include_in_schema=False,
)
@router.get(
    "/company/overview",
    response_model=PlatformWalletResponse,
    summary="Admin: platform company wallet overview alias",
    include_in_schema=False,
)
def get_company_wallet_alias(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PlatformWalletResponse:
    return WalletService.get_platform_wallet(db=db, page=page, page_size=page_size)


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
    summary="Admin: credit or debit a user/merchant wallet",
)
def admin_adjust_wallet(
    payload: AdminWalletAdjustRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminWalletAdjustResponse:
    wallet, group_id, txn_type, claim_id, claim_status = WalletService.admin_adjust_wallet(
        db=db,
        admin_user=admin_user,
        target_user_id=payload.user_id,
        amount=payload.amount,
        operation=payload.operation,
        note=payload.note,
        merchant_id=payload.merchant_id,
        claim_mode=payload.claim_mode,
    )
    msg = (
        f"₹{payload.amount} sent to user's Redeem section (Pending Claim)"
        if claim_id
        else f"Wallet {payload.operation} successful"
    )
    return AdminWalletAdjustResponse(
        message=msg,
        wallet=wallet,
        transaction_group_id=group_id,
        transaction_type=txn_type,
        claim_id=claim_id,
        claim_status=claim_status,
    )


@router.get(
    "/rewards/pending",
    response_model=StandardListResponse[WalletRewardClaimResponse],
    summary="List pending redeemable rewards and admin cash grants",
)
def list_pending_rewards(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StandardListResponse[WalletRewardClaimResponse]:
    rewards = WalletService.list_pending_rewards(db=db, user=current_user)
    data = [WalletRewardClaimResponse.model_validate(r) for r in rewards]
    return list_response(
        data=data,
        total_items=len(data),
        message=f"Retrieved {len(data)} pending reward(s)",
    )


@router.post(
    "/rewards/{claim_id}/redeem",
    summary="Redeem pending admin cash grant into wallet",
)
def redeem_reward(
    claim_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wallet, claim, group_id = WalletService.redeem_reward_claim(
        db=db, user=current_user, claim_id=claim_id
    )
    return {
        "success": True,
        "message": f"🎉 ₹{claim.amount} redeemed to your wallet successfully!",
        "wallet": wallet,
        "claim": WalletRewardClaimResponse.model_validate(claim),
        "transaction_group_id": group_id,
    }

