import json

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.database import get_db
from app.db.models.user import User
from app.db.models.wallet import WalletTopupOrder
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


@router.get("/razorpay/checkout", response_class=HTMLResponse, summary="In-app browser checkout page for Razorpay")
def render_razorpay_checkout_page(
    order_id: str = Query(..., description="Razorpay Order ID"),
    amount: int = Query(..., description="Amount in paise"),
    name: str = Query("LOGO Payment", description="Display Name"),
    description: str = Query("Secure Checkout", description="Payment description"),
    prefill_name: str = Query("", description="Customer name"),
    prefill_contact: str = Query("", description="Customer phone number"),
    prefill_email: str = Query("", description="Customer email"),
    redirect_url: str = Query("", description="Deep-link or return URL for app"),
    db: Session = Depends(get_db),
):
    if not RazorpayService.is_configured():
        return HTMLResponse(
            content=_checkout_message(
                "Razorpay is not configured",
                "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to the same test or live key that created the order.",
            ),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    topup = (
        db.query(WalletTopupOrder)
        .filter(WalletTopupOrder.razorpay_order_id == order_id.strip())
        .first()
    )
    try:
        remote = RazorpayService.fetch_order(order_id.strip())
    except Exception as exc:
        detail = getattr(exc, "detail", None) or "Razorpay could not open this order."
        return HTMLResponse(content=_checkout_message("Payment could not start", str(detail)), status_code=400)

    amount_paise = int(remote.get("amount") or 0)
    if amount_paise <= 0:
        amount_paise = RazorpayService.checkout_amount_paise(
            amount, topup.amount_paise if topup else None
        )
    currency = str(remote.get("currency") or (topup.currency if topup else "INR") or "INR")
    contact = RazorpayService.checkout_contact(prefill_contact)
    email = RazorpayService.checkout_email(prefill_email)
    options = {
        "key": settings.RAZORPAY_KEY_ID,
        "amount": amount_paise,
        "currency": currency,
        "name": name[:80],
        "description": description[:120],
        "order_id": order_id.strip(),
        "theme": {"color": "#7C3AED"},
    }
    prefill = {}
    if prefill_name.strip():
        prefill["name"] = prefill_name.strip()[:80]
    if contact:
        prefill["contact"] = contact
    if email:
        prefill["email"] = email
    if prefill:
        options["prefill"] = prefill
    options_json = json.dumps(options)
    redirect_json = json.dumps(redirect_url)
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{name}</title>
  <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background: #0f172a; color: #f8fafc;
      display: flex; align-items: center; justify-content: center;
      min-height: 100vh;
    }}
    .box {{
      background: #1e293b; border: 1px solid #334155;
      padding: 32px 24px; border-radius: 20px; text-align: center;
      max-width: 400px; width: 90%;
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
    }}
    .spinner {{
      width: 44px; height: 44px;
      border: 4px solid #334155; border-top: 4px solid #7c3aed;
      border-radius: 50%;
      animation: spin 0.9s linear infinite;
      margin: 0 auto 20px auto;
    }}
    @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
    h2 {{ margin: 0 0 8px 0; font-size: 20px; font-weight: 700; }}
    p {{ margin: 0 0 20px 0; font-size: 14px; color: #94a3b8; line-height: 1.5; }}
    .btn {{
      background: linear-gradient(135deg, #7c3aed, #6366f1);
      color: #fff; border: none; padding: 12px 24px; border-radius: 12px;
      font-size: 15px; font-weight: 600; cursor: pointer; width: 100%;
    }}
    .success {{ color: #10b981; font-weight: 600; font-size: 16px; margin-top: 12px; }}
  </style>
</head>
<body>
  <div class="box">
    <div class="spinner" id="spinner"></div>
    <h2 id="title">Connecting Razorpay...</h2>
    <p id="desc">Please wait while the secure payment sheet opens.</p>
    <button class="btn" id="retry-btn" style="display: none;" onclick="launchPayment()">Pay Now</button>
    <div id="status"></div>
  </div>

  <script>
    const options = {options_json};
    const redirectUrl = {redirect_json};
    options.handler = function(response) {{
        document.getElementById('spinner').style.display = 'none';
        document.getElementById('title').innerText = 'Payment Successful!';
        document.getElementById('desc').innerText = 'Returning to app...';
        document.getElementById('status').innerHTML = '<div class="success">✓ Verified by Razorpay</div>';

        if (redirectUrl) {{
          const sep = redirectUrl.includes('?') ? '&' : '?';
          const returnUrl = redirectUrl + sep + 'status=success' +
            '&razorpay_payment_id=' + encodeURIComponent(response.razorpay_payment_id || '') +
            '&razorpay_order_id=' + encodeURIComponent(response.razorpay_order_id || '') +
            '&razorpay_signature=' + encodeURIComponent(response.razorpay_signature || '');
          window.location.href = returnUrl;
        }}
      }};
    options.modal = {{
      ondismiss: function() {{
        document.getElementById('spinner').style.display = 'none';
        document.getElementById('title').innerText = 'Payment Cancelled';
        document.getElementById('desc').innerText = 'You can retry payment or return to the app.';
        document.getElementById('retry-btn').style.display = 'block';

        if (redirectUrl) {{
          const sep = redirectUrl.includes('?') ? '&' : '?';
          window.location.href = redirectUrl + sep + 'status=cancelled';
        }}
      }}
    }};

    function launchPayment() {{
      document.getElementById('spinner').style.display = 'block';
      document.getElementById('retry-btn').style.display = 'none';
      try {{
        const rzp = new Razorpay(options);
        rzp.open();
      }} catch (err) {{
        document.getElementById('spinner').style.display = 'none';
        document.getElementById('title').innerText = 'Payment Failed';
        document.getElementById('desc').innerText = err.message || 'Error opening Razorpay.';
        document.getElementById('retry-btn').style.display = 'block';
      }}
    }}

    window.onload = function() {{
      setTimeout(launchPayment, 500);
    }};
  </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)


def _checkout_message(title: str, detail: str) -> str:
    safe_title = json.dumps(title)
    safe_detail = json.dumps(detail)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Payment</title></head>
<body style="font-family: sans-serif; background:#0f172a; color:#f8fafc; display:flex; min-height:100vh; align-items:center; justify-content:center;">
<div style="max-width:420px; padding:24px;"><h2 id="title"></h2><p id="desc"></p></div>
<script>
document.getElementById('title').textContent = {safe_title};
document.getElementById('desc').textContent = {safe_detail};
</script></body></html>"""
