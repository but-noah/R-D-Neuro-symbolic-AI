"""
Test Order Database
Realistic order data for testing the voice pipeline refund logic

This database simulates a real e-commerce order system with various scenarios:
- Valid refund requests (defective products, wrong items)
- Invalid refund requests (outside return window, normal use)
- Edge cases (delayed delivery, not delivered)

Each order includes:
- Product details (name, price, category)
- Order timeline (purchase, delivery dates)
- Condition assessment (defective, damaged, normal)
- Return eligibility (within window, valid reason)
"""

from datetime import datetime, timedelta
from typing import Dict, Any

# Helper to calculate dates
def days_ago(days: int) -> str:
    """Return date N days ago in ISO format"""
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

def days_future(days: int) -> str:
    """Return date N days in future in ISO format"""
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


# Test Order Database
TEST_ORDERS: Dict[str, Dict[str, Any]] = {
    # ============================================================================
    # VALID REFUND CASES - Should be approved
    # ============================================================================

    "12345": {
        "order_id": "12345",
        "customer_name": "John Smith",
        "product_name": "Sony WH-1000XM5 Wireless Headphones",
        "product_category": "Electronics",
        "price": 399.99,
        "currency": "USD",
        "order_date": days_ago(15),
        "delivery_date": days_ago(10),
        "purchase_method": "credit_card",

        # Product condition
        "actual_condition": "defective",  # Actually defective
        "defect_description": "Left speaker not working, crackling sound",
        "quality_verified": True,

        # Return eligibility
        "within_return_window": True,  # 10 days < 30 days
        "return_window_days": 30,
        "valid_return_reasons": ["defective", "not_as_described", "changed_mind"],

        # Expected outcome
        "refund_eligible": True,
        "refund_amount": 399.99,
        "refund_reason": "Product defect confirmed - speaker malfunction",
    },

    "67890": {
        "order_id": "67890",
        "customer_name": "Sarah Johnson",
        "product_name": "Apple Watch Series 9 GPS 45mm",
        "product_category": "Electronics",
        "price": 429.00,
        "currency": "USD",
        "order_date": days_ago(5),
        "delivery_date": days_ago(2),
        "purchase_method": "debit_card",

        # Product condition
        "actual_condition": "wrong_item",  # Wrong item sent
        "defect_description": "Received 41mm instead of ordered 45mm",
        "quality_verified": True,

        # Return eligibility
        "within_return_window": True,  # 2 days < 30 days
        "return_window_days": 30,
        "valid_return_reasons": ["wrong_item", "defective", "not_as_described"],

        # Expected outcome
        "refund_eligible": True,
        "refund_amount": 429.00,
        "refund_reason": "Wrong item shipped - size mismatch",
    },

    "11111": {
        "order_id": "11111",
        "customer_name": "Michael Chen",
        "product_name": "Dell XPS 15 Laptop",
        "product_category": "Computers",
        "price": 1799.99,
        "currency": "USD",
        "order_date": days_ago(20),
        "delivery_date": days_ago(18),
        "purchase_method": "credit_card",

        # Product condition
        "actual_condition": "not_as_described",
        "defect_description": "Advertised 16GB RAM but received 8GB",
        "quality_verified": True,

        # Return eligibility
        "within_return_window": True,  # 18 days < 30 days
        "return_window_days": 30,
        "valid_return_reasons": ["defective", "not_as_described", "wrong_item"],

        # Expected outcome
        "refund_eligible": True,
        "refund_amount": 1799.99,
        "refund_reason": "Product specifications mismatch - RAM discrepancy",
    },

    # ============================================================================
    # INVALID REFUND CASES - Should be denied
    # ============================================================================

    "99999": {
        "order_id": "99999",
        "customer_name": "Robert Williams",
        "product_name": "Bluetooth Speaker JBL Charge 5",
        "product_category": "Electronics",
        "price": 179.99,
        "currency": "USD",
        "order_date": days_ago(45),
        "delivery_date": days_ago(42),
        "purchase_method": "credit_card",

        # Product condition
        "actual_condition": "normal",  # Working fine
        "defect_description": None,
        "quality_verified": True,

        # Return eligibility
        "within_return_window": False,  # 42 days > 30 days
        "return_window_days": 30,
        "valid_return_reasons": ["defective", "not_as_described"],

        # Expected outcome
        "refund_eligible": False,
        "refund_amount": 0.00,
        "refund_reason": "Outside 30-day return window (42 days since delivery)",
    },

    "88888": {
        "order_id": "88888",
        "customer_name": "Emily Davis",
        "product_name": "Nike Air Max 270 Sneakers",
        "product_category": "Footwear",
        "price": 150.00,
        "currency": "USD",
        "order_date": days_ago(10),
        "delivery_date": days_ago(7),
        "purchase_method": "paypal",

        # Product condition
        "actual_condition": "normal_wear",  # User wore them, normal use
        "defect_description": "Customer claims uncomfortable fit",
        "quality_verified": True,

        # Return eligibility
        "within_return_window": True,  # 7 days < 30 days
        "return_window_days": 30,
        "valid_return_reasons": ["defective", "wrong_item", "not_as_described"],

        # Expected outcome (subjective comfort not valid reason)
        "refund_eligible": False,
        "refund_amount": 0.00,
        "refund_reason": "Personal preference (comfort) is not a valid return reason for worn footwear",
    },

    # ============================================================================
    # EDGE CASES
    # ============================================================================

    "55555": {
        "order_id": "55555",
        "customer_name": "Jessica Martinez",
        "product_name": "Samsung Galaxy S24 Ultra",
        "product_category": "Electronics",
        "price": 1299.99,
        "currency": "USD",
        "order_date": days_ago(25),
        "delivery_date": None,  # Not delivered yet (delayed)
        "purchase_method": "credit_card",

        # Product condition
        "actual_condition": "not_received",
        "defect_description": "Package delayed, not yet delivered",
        "quality_verified": False,

        # Return eligibility (can cancel order)
        "within_return_window": True,
        "return_window_days": 30,
        "valid_return_reasons": ["not_received", "excessive_delay"],

        # Expected outcome
        "refund_eligible": True,
        "refund_amount": 1299.99,
        "refund_reason": "Order cancellation due to excessive delivery delay (25 days)",
    },

    "77777": {
        "order_id": "77777",
        "customer_name": "David Thompson",
        "product_name": "Dyson V15 Detect Vacuum Cleaner",
        "product_category": "Home Appliances",
        "price": 649.99,
        "currency": "USD",
        "order_date": days_ago(28),
        "delivery_date": days_ago(25),
        "purchase_method": "credit_card",

        # Product condition
        "actual_condition": "defective",
        "defect_description": "Motor stopped working after 2 weeks",
        "quality_verified": True,

        # Return eligibility (edge: near end of window)
        "within_return_window": True,  # 25 days < 30 days (just barely!)
        "return_window_days": 30,
        "valid_return_reasons": ["defective", "not_as_described"],

        # Expected outcome
        "refund_eligible": True,
        "refund_amount": 649.99,
        "refund_reason": "Product defect confirmed - motor failure within warranty",
    },

    "33333": {
        "order_id": "33333",
        "customer_name": "Amanda Garcia",
        "product_name": "Kindle Paperwhite (2024)",
        "product_category": "Electronics",
        "price": 139.99,
        "currency": "USD",
        "order_date": days_ago(3),
        "delivery_date": days_ago(1),
        "purchase_method": "amazon_pay",

        # Product condition
        "actual_condition": "damaged_in_shipping",
        "defect_description": "Screen cracked upon arrival, packaging was damaged",
        "quality_verified": True,

        # Return eligibility
        "within_return_window": True,  # 1 day < 30 days
        "return_window_days": 30,
        "valid_return_reasons": ["defective", "damaged_in_shipping", "not_as_described"],

        # Expected outcome
        "refund_eligible": True,
        "refund_amount": 139.99,
        "refund_reason": "Shipping damage - cracked screen confirmed",
    },

    "22222": {
        "order_id": "22222",
        "customer_name": "Christopher Lee",
        "product_name": "LG OLED C3 65-inch TV",
        "product_category": "Electronics",
        "price": 2499.99,
        "currency": "USD",
        "order_date": days_ago(8),
        "delivery_date": days_ago(5),
        "purchase_method": "credit_card",

        # Product condition
        "actual_condition": "defective",
        "defect_description": "Dead pixels in multiple areas, backlight bleeding",
        "quality_verified": True,

        # Return eligibility
        "within_return_window": True,  # 5 days < 30 days
        "return_window_days": 30,
        "valid_return_reasons": ["defective", "not_as_described"],

        # Expected outcome
        "refund_eligible": True,
        "refund_amount": 2499.99,
        "refund_reason": "Manufacturing defect - dead pixels and backlight issues",
    },
}


def get_order(order_id: str) -> Dict[str, Any] | None:
    """
    Get order by ID

    Args:
        order_id: Order ID to lookup

    Returns:
        Order dict or None if not found
    """
    return TEST_ORDERS.get(order_id)


def is_within_return_window(order_id: str) -> bool:
    """
    Check if order is within return window

    Args:
        order_id: Order ID to check

    Returns:
        True if within return window, False otherwise
    """
    order = get_order(order_id)
    if not order:
        return False

    return order.get("within_return_window", False)


def get_refund_eligibility(order_id: str) -> Dict[str, Any]:
    """
    Get refund eligibility decision for an order

    Args:
        order_id: Order ID to check

    Returns:
        Dict with eligibility decision
    """
    order = get_order(order_id)

    if not order:
        return {
            "eligible": False,
            "amount": 0.00,
            "reason": f"Order {order_id} not found in system"
        }

    return {
        "eligible": order.get("refund_eligible", False),
        "amount": order.get("refund_amount", 0.00),
        "reason": order.get("refund_reason", "No reason provided")
    }


def list_all_orders() -> list[str]:
    """
    List all order IDs in the test database

    Returns:
        List of order IDs
    """
    return list(TEST_ORDERS.keys())


def get_order_summary() -> str:
    """
    Get summary of test orders for debugging

    Returns:
        Formatted string with order summary
    """
    summary = "Test Order Database Summary:\n"
    summary += "="*70 + "\n"

    eligible_count = sum(1 for o in TEST_ORDERS.values() if o["refund_eligible"])
    ineligible_count = len(TEST_ORDERS) - eligible_count

    summary += f"Total Orders: {len(TEST_ORDERS)}\n"
    summary += f"Refund Eligible: {eligible_count}\n"
    summary += f"Refund Ineligible: {ineligible_count}\n\n"

    summary += "Orders by Category:\n"
    for order_id, order in TEST_ORDERS.items():
        eligible = "✅" if order["refund_eligible"] else "❌"
        summary += f"  {eligible} {order_id}: {order['product_name']} (${order['price']:.2f})\n"

    return summary


# Print summary when module is imported (for debugging)
if __name__ == "__main__":
    print(get_order_summary())

    # Test a few orders
    print("\n" + "="*70)
    print("Sample Order Details:")
    print("="*70)

    test_ids = ["12345", "99999", "55555"]
    for order_id in test_ids:
        print(f"\nOrder {order_id}:")
        order = get_order(order_id)
        if order:
            print(f"  Product: {order['product_name']}")
            print(f"  Price: ${order['price']:.2f}")
            print(f"  Condition: {order['actual_condition']}")

            eligibility = get_refund_eligibility(order_id)
            print(f"  Eligible: {eligibility['eligible']}")
            print(f"  Reason: {eligibility['reason']}")
