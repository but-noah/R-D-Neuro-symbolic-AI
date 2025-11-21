from datetime import datetime, timezone
from app.models.schemas import RefundRequest, RefundDecision

def check_refund_eligibility(request: RefundRequest) -> RefundDecision:
    """
    The SYMBOLIC LAYER: Hard-coded rules that the LLM cannot override.
    """
    # Use timezone-aware UTC time to match the input format
    now = datetime.now(timezone.utc)
    
    # Ensure purchase_date is also timezone-aware
    purchase_date = request.purchase_date
    if purchase_date.tzinfo is None:
        purchase_date = purchase_date.replace(tzinfo=timezone.utc)
        
    days_since_purchase = (now - purchase_date).days

    # Rule 1: Time Limit (30 days)
    if days_since_purchase > 30:
        return RefundDecision(
            allowed=False,
            reason=f"Purchase was {days_since_purchase} days ago. Policy limit is 30 days.",
            offer_coupon=True, # Business Logic: Offer coupon to retain customer
            coupon_value=10.0
        )

    # Rule 2: Condition (Must be "defective" or "unopened" for full refund)
    # Simple keyword check for this PoC
    valid_reasons = ["defective", "broken", "unopened", "wrong item"]
    reason_lower = request.reason.lower()
    
    if not any(r in reason_lower for r in valid_reasons):
        return RefundDecision(
            allowed=False,
            reason="Refunds are only allowed for defective or unopened items.",
            offer_coupon=False
        )

    # Rule 3: High Value Approval (Simulated)
    if request.price > 500:
        return RefundDecision(
            allowed=False, # Pending manual review
            reason="Items over $500 require manual inspection.",
            offer_coupon=False
        )

    # If all checks pass
    return RefundDecision(
        allowed=True,
        reason="Request meets all policy criteria.",
        offer_coupon=False
    )
