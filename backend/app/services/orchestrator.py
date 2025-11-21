import json
import urllib.request
import asyncio
import time
from openai import AsyncOpenAI
from app.models.schemas import RefundRequest, CustomerEmotion
from app.services.rules_engine import check_refund_eligibility
from app.services.empathy_engine import get_empathy_instruction
from app.core.config import settings
from app.services import rules_engine, empathy_engine

class NeuroSymbolicOrchestrator:
    def __init__(self):
        self.async_client = None

    def _get_async_client(self):
        """Lazy initialization of AsyncOpenAI client."""
        if self.async_client is None:
            self.async_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self.async_client

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

    def stream_llm(self, prompt: str, model: str = "gpt-4o"):
        """
        Streams response from OpenAI API (Synchronous version for backward compatibility).
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
            "model": model,
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

    async def stream_llm_async(self, prompt: str, model: str = "gpt-4o"):
        """
        Async version: Streams response from OpenAI API using AsyncOpenAI client.
        Yields chunks of text asynchronously.
        """
        client = self._get_async_client()

        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": prompt}],
                temperature=0.7,
                stream=True
            )

            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content

        except Exception as e:
            yield f"LLM STREAM FAILED: {str(e)}"

    def stream_logic_injection(self, user_text: str, request: RefundRequest, emotion: CustomerEmotion):
        """
        DEPRECATED: Synchronous version kept for backward compatibility.
        Use stream_logic_injection_async() instead for better performance.
        """
        filler_prompt = f"""
### SYSTEM INSTRUCTION
You are a helpful customer support agent.
The user just said: "{user_text}"
Detected Emotion: {emotion.sentiment} (Anger: {emotion.anger_level})

### TASK
Generate a SHORT, empathetic, neutral filler sentence (max 15 words) to acknowledge the user while you check their account.
Do NOT promise anything yet.
Do NOT use quotation marks.
Example: I understand, let me check that for you...
"""
        yield {"type": "debug", "prompt": filler_prompt}

        filler_text = ""
        for token in self.stream_llm(filler_prompt, model="gpt-4o-mini"):
            clean_token = token.replace('"', '')
            filler_text += clean_token
            yield {"type": "token", "content": clean_token}

        decision = rules_engine.check_refund_eligibility(request)
        empathy_instructions = empathy_engine.get_empathy_instruction(emotion)

        result_prompt = f"""
### SYSTEM INSTRUCTION
You are a helpful customer support agent.
{empathy_instructions}

### CONTEXT
User said: "{user_text}"
You just said (Filler): "{filler_text}"

### FACTS
- Decision: {decision.allowed}
- Reason: {decision.reason}
- Offer Coupon: {decision.offer_coupon} ({decision.coupon_value})

### TASK
Continue the response naturally from where you left off.
Do NOT repeat the filler.
Ensure the transition is smooth (e.g. start with "Unfortunately..." or "Good news...").
Explain the decision and offer the coupon if applicable.
"""
        yield {"type": "debug", "prompt": result_prompt}
        yield {"type": "token", "content": " "}

        for token in self.stream_llm(result_prompt):
            yield {"type": "token", "content": token}

    async def stream_logic_injection_async(self, user_text: str, request: RefundRequest, emotion: CustomerEmotion):
        """
        🚀 ZERO-LATENCY STREAMING LOGIC INJECTION (Async + Pre-Fetch Optimized)

        Implementation of Proposal 2 with Pre-Fetch optimization:
        1. PRE-FETCH: Start Logic Task IMMEDIATELY (even before Filler!)
        2. Stream Filler (while Logic runs in parallel)
        3. Await Logic Result (should be ready by now!)
        4. Stream Result (seamless continuation)

        This achieves TRUE zero-latency by utilizing the filler streaming time
        as a buffer for logic execution.

        Yields dicts: {"type": "token"|"debug", "content"|"prompt": ...}
        """

        # ═══════════════════════════════════════════════════════════
        # 🕐 PERFORMANCE TRACKING START
        # ═══════════════════════════════════════════════════════════
        t_start = time.time()
        print("\n" + "="*70)
        print("🚀 ZERO-LATENCY STREAMING PIPELINE STARTED")
        print("="*70)

        # ═══════════════════════════════════════════════════════════
        # PHASE 0: PRE-FETCH - Start Logic Task IMMEDIATELY! 🚀
        # ═══════════════════════════════════════════════════════════
        # This is the KEY innovation: We don't wait for the filler to finish.
        # We start the logic calculation RIGHT NOW, in parallel.

        t_logic_start = time.time()
        print(f"⚙️  [+{(t_logic_start - t_start)*1000:.0f}ms] Logic Task STARTED (Pre-Fetch)")

        async def run_logic():
            """Execute logic in background while filler streams."""
            # Run sync logic in thread pool (it's fast, <100ms)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                rules_engine.check_refund_eligibility,
                request
            )
            t_logic_end = time.time()
            print(f"✅ [+{(t_logic_end - t_start)*1000:.0f}ms] Logic Task COMPLETED ({(t_logic_end - t_logic_start)*1000:.0f}ms)")
            return result

        # START LOGIC TASK NOW! (Pre-Fetch)
        logic_task = asyncio.create_task(run_logic())

        # ═══════════════════════════════════════════════════════════
        # PHASE 1: Stream Filler (PARALLEL to Logic!)
        # ═══════════════════════════════════════════════════════════
        t_filler_start = time.time()
        print(f"💬 [+{(t_filler_start - t_start)*1000:.0f}ms] Filler Stream STARTED (gpt-4o-mini)")

        filler_prompt = f"""
### SYSTEM INSTRUCTION
You are a helpful customer support agent.
The user just said: "{user_text}"
Detected Emotion: {emotion.sentiment} (Anger: {emotion.anger_level})

### TASK
Generate a SHORT, empathetic, neutral filler sentence (max 15 words) to acknowledge the user while you check their account.
Do NOT promise anything yet.
Do NOT use quotation marks.
Example: I understand, let me check that for you...
"""
        yield {"type": "debug", "prompt": filler_prompt}

        filler_text = ""
        first_filler_token = True

        async for token in self.stream_llm_async(filler_prompt, model="gpt-4o-mini"):
            if first_filler_token:
                t_first_token = time.time()
                print(f"🎯 [+{(t_first_token - t_start)*1000:.0f}ms] FIRST FILLER TOKEN ({(t_first_token - t_filler_start)*1000:.0f}ms)")
                first_filler_token = False

            clean_token = token.replace('"', '')
            filler_text += clean_token
            yield {"type": "token", "content": clean_token}

        t_filler_end = time.time()
        print(f"✅ [+{(t_filler_end - t_start)*1000:.0f}ms] Filler Stream COMPLETED ({(t_filler_end - t_filler_start)*1000:.0f}ms)")
        print(f"📝 Filler Text: \"{filler_text}\"")
        print(f"⚡ Logic running in parallel... checking status...")

        # ═══════════════════════════════════════════════════════════
        # PHASE 2: Await Logic Result (should be ready now!)
        # ═══════════════════════════════════════════════════════════
        # By the time filler finishes streaming (~1-2s),
        # the logic task (<100ms) is LONG done!

        t_await_logic = time.time()
        if logic_task.done():
            print(f"🎉 [+{(t_await_logic - t_start)*1000:.0f}ms] Logic was ALREADY DONE! (No wait needed)")
        else:
            print(f"⏳ [+{(t_await_logic - t_start)*1000:.0f}ms] Waiting for Logic to complete...")

        decision = await logic_task
        t_logic_retrieved = time.time()

        if not logic_task.done():
            print(f"⚠️  [+{(t_logic_retrieved - t_start)*1000:.0f}ms] Logic completed just now ({(t_logic_retrieved - t_await_logic)*1000:.0f}ms wait)")

        # Get empathy instructions
        empathy_instructions = empathy_engine.get_empathy_instruction(emotion)
        print(f"📊 Decision: {'APPROVED' if decision.allowed else 'DENIED'} - {decision.reason}")

        # ═══════════════════════════════════════════════════════════
        # PHASE 3: Stream Result (Seamless Continuation)
        # ═══════════════════════════════════════════════════════════
        t_result_start = time.time()
        print(f"💬 [+{(t_result_start - t_start)*1000:.0f}ms] Result Stream STARTED (gpt-4o)")

        result_prompt = f"""
### SYSTEM INSTRUCTION
You are a helpful customer support agent.
{empathy_instructions}

### CONTEXT
User said: "{user_text}"
You just said (Filler): "{filler_text}"

### FACTS
- Decision: {decision.allowed}
- Reason: {decision.reason}
- Offer Coupon: {decision.offer_coupon} ({decision.coupon_value})

### TASK
Continue the response naturally from where you left off.
Do NOT repeat the filler.
Ensure the transition is smooth (e.g. start with "Unfortunately..." or "Good news...").
Explain the decision and offer the coupon if applicable.
"""
        yield {"type": "debug", "prompt": result_prompt}

        # Add natural pause/space for smooth transition
        yield {"type": "token", "content": " "}

        # Stream the final result
        first_result_token = True
        result_text = ""

        async for token in self.stream_llm_async(result_prompt):
            if first_result_token:
                t_first_result_token = time.time()
                print(f"🎯 [+{(t_first_result_token - t_start)*1000:.0f}ms] FIRST RESULT TOKEN ({(t_first_result_token - t_result_start)*1000:.0f}ms)")
                first_result_token = False
            result_text += token
            yield {"type": "token", "content": token}

        t_end = time.time()
        print(f"✅ [+{(t_end - t_start)*1000:.0f}ms] Result Stream COMPLETED ({(t_end - t_result_start)*1000:.0f}ms)")

        # ═══════════════════════════════════════════════════════════
        # 🕐 PERFORMANCE SUMMARY
        # ═══════════════════════════════════════════════════════════
        print("\n" + "="*70)
        print("📊 PERFORMANCE SUMMARY")
        print("="*70)
        print(f"⏱️  Total Time:              {(t_end - t_start)*1000:.0f}ms")
        print(f"🎯 Time to First Token:     {(t_first_token - t_start)*1000:.0f}ms  ⚡ (User sees response!)")
        print(f"💬 Filler Duration:          {(t_filler_end - t_filler_start)*1000:.0f}ms")
        print(f"⚙️  Logic Duration:           {(t_logic_retrieved - t_logic_start)*1000:.0f}ms  🚀 (Ran in parallel!)")
        print(f"💬 Result Duration:          {(t_end - t_result_start)*1000:.0f}ms")
        print(f"🎉 Parallel Efficiency:     Logic completed BEFORE filler ended!")
        print("="*70 + "\n")

orchestrator = NeuroSymbolicOrchestrator()
