import sys
import os

# Add current directory to sys.path so we can import 'app'
sys.path.append(os.getcwd())

from app.models.schemas import RefundRequest, CustomerEmotion
from app.services.orchestrator import orchestrator

def test_backend():
    print("Testing Backend Services...")
    
    # Test Data
    request = RefundRequest(
        product_name="Gaming Mouse",
        purchase_date="2022-01-01T10:00:00",
        reason="changed mind",
        price=60.0,
        customer_id="CUST-001"
    )
    emotion = CustomerEmotion(
        anger_level=0.9,
        sentiment="negative"
    )
    user_text = "I want my money back!"

    # Test Orchestrator Logic (Prompt Generation)
    prompt = orchestrator.process_interaction(user_text, request, emotion)
    
    if "DECISION: DENIED" in prompt:
        print("SUCCESS: Logic Layer correctly denied refund.")
    else:
        print("FAILURE: Logic Layer did not deny refund.")
        
    if "The customer is FURIOUS" in prompt:
        print("SUCCESS: Empathy Layer correctly detected anger.")
    else:
        print("FAILURE: Empathy Layer did not detect anger.")

    print("\nGenerated Prompt Preview:")
    print(prompt[:200] + "...")

if __name__ == "__main__":
    test_backend()
