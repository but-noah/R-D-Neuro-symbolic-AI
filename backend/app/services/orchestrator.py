import json
import urllib.request
from app.models.schemas import RefundRequest, CustomerEmotion
from app.services.rules_engine import check_refund_eligibility
from app.services.empathy_engine import get_empathy_instruction
from app.core.config import settings

class NeuroSymbolicOrchestrator:
    def __init__(self):
        pass

    def process_interaction(self, user_text: str, request: RefundRequest, emotion: CustomerEmotion) -> str:
        """
        The Core Loop:
        1. Execute Symbolic Logic (The Truth)
        2. Determine Empathy Strategy (The Vibe)
        3. Construct Final Prompt (The Output)
        """
        
        # Step 1: Symbolic Logic (The Guardrails)
        decision = check_refund_eligibility(request)

        # Step 2: Empathy Layer
        empathy_instruction = get_empathy_instruction(emotion)

        # Step 3: Construct the Neuro-Symbolic Prompt
        prompt = f"""
### SYSTEM INSTRUCTION
{empathy_instruction}

### CURRENT TASK
Respond to the customer's refund request.

### FACTS (DO NOT HALLUCINATE)
- Customer ID: {request.customer_id}
- Item: {request.product_name}
- Purchase Date: {request.purchase_date.strftime('%Y-%m-%d')}
- DECISION: {"APPROVED" if decision.allowed else "DENIED"}
- REASON: {decision.reason}
{f"- OFFER: You MUST offer a coupon of ${decision.coupon_value}." if decision.offer_coupon else ""}

### USER MESSAGE
"{user_text}"

### YOUR RESPONSE
"""
        return prompt

    def call_llm(self, prompt: str) -> str:
        """
        Calls OpenAI API using standard library.
        """
        api_key = settings.OPENAI_API_KEY
        if not api_key:
            return "ERROR: API Key not configured."

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        data = {
            "model": "gpt-4o",
            "messages": [{"role": "system", "content": prompt}],
            "temperature": 0.7
        }

        try:
            req = urllib.request.Request(url, json.dumps(data).encode(), headers)
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode())
                return result["choices"][0]["message"]["content"]
        except Exception as e:
            return f"LLM CALL FAILED: {str(e)}"

    def call_raw_llm(self, user_text: str, request: RefundRequest) -> tuple[str, str]:
        """
        Simulates a 'Naive' LLM Wrapper.
        It gets the raw data but NO pre-calculated decisions and NO empathy instructions.
        Returns: (response_text, prompt_used)
        """
        prompt = f"""
You are a customer support agent for an electronics store.
Use the following customer data to answer the request:
- Customer ID: {request.customer_id}
- Product: {request.product_name}
- Purchase Date: {request.purchase_date.strftime('%Y-%m-%d')}
- Price: ${request.price}
- Policy: Refunds allowed within 30 days of purchase.

User Message: "{user_text}"
"""
        response = self.call_llm(prompt)
        return response, prompt

    def stream_llm(self, prompt: str):
        """
        Streams response from OpenAI API.
        Yields chunks of text.
        """
        api_key = settings.OPENAI_API_KEY
        if not api_key:
            yield "ERROR: API Key not configured."
            return

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        data = {
            "model": "gpt-4o",
            "messages": [{"role": "system", "content": prompt}],
            "temperature": 0.7,
            "stream": True
        }

        try:
            req = urllib.request.Request(url, json.dumps(data).encode(), headers)
            with urllib.request.urlopen(req) as response:
                for line in response:
                    line = line.decode('utf-8').strip()
                    if line.startswith("data: ") and line != "data: [DONE]":
                        json_str = line[6:]  # Remove "data: " prefix
                        try:
                            chunk = json.loads(json_str)
                            content = chunk["choices"][0]["delta"].get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            yield f"LLM STREAM FAILED: {str(e)}"

orchestrator = NeuroSymbolicOrchestrator()
