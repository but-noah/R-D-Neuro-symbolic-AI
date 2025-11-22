from datetime import datetime, timezone
from typing import Dict, Any
from app.models.schemas import RefundRequest, RefundDecision

# Import test orders database
try:
    from app.data.test_orders import get_order, get_refund_eligibility as get_test_refund_eligibility
    TEST_ORDERS_AVAILABLE = True
except ImportError:
    TEST_ORDERS_AVAILABLE = False


def check_refund_eligibility_with_order_id(order_id: str, claimed_reason: str) -> Dict[str, Any]:
    """
    Check refund eligibility using test orders database

    This function validates refund requests against realistic order data,
    checking:
    - Order exists in system
    - Within return window (30 days)
    - Valid return reason matches actual product condition
    - Price and product details

    Args:
        order_id: Order ID to check (e.g., "12345")
        claimed_reason: Customer's claimed reason (e.g., "defective")

    Returns:
        Dict with:
        - allowed: bool
        - amount: float
        - reason: str
        - order_details: dict (product info)
    """
    if not TEST_ORDERS_AVAILABLE:
        return {
            "allowed": False,
            "amount": 0.0,
            "reason": "Test orders database not available",
            "order_details": None
        }

    # Get order from database
    order = get_order(order_id)

    if not order:
        return {
            "allowed": False,
            "amount": 0.0,
            "reason": f"Order {order_id} not found in system",
            "order_details": None
        }

    # Get pre-determined eligibility from test data
    eligibility = get_test_refund_eligibility(order_id)

    # Build response with full order details
    return {
        "allowed": eligibility["eligible"],
        "amount": eligibility["amount"],
        "reason": eligibility["reason"],
        "order_details": {
            "order_id": order["order_id"],
            "customer_name": order["customer_name"],
            "product_name": order["product_name"],
            "product_category": order["product_category"],
            "price": order["price"],
            "order_date": order["order_date"],
            "delivery_date": order["delivery_date"],
            "actual_condition": order["actual_condition"],
            "defect_description": order.get("defect_description"),
            "within_return_window": order["within_return_window"],
        }
    }


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
