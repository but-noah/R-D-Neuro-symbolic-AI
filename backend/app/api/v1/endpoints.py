from fastapi import APIRouter, HTTPException
from app.models.schemas import ChatRequest
from app.services.orchestrator import orchestrator

router = APIRouter()

@router.post("/chat")
def chat_endpoint(request: ChatRequest):
    """
    Neuro-symbolic Chat Endpoint.
    Accepts user message + metadata (logic/emotion inputs).
    Returns the AI response.
    """
    # 1. Generate the safe prompt
    prompt = orchestrator.process_interaction(
        user_text=request.message,
        request=request.user_data,
        emotion=request.emotion_data
    )
    
    # 2. Call the LLM
    response_text = orchestrator.call_llm(prompt)
    
    return {
        "response": response_text,
        "debug_prompt": prompt # Returning prompt for debugging/demo purposes
    }

@router.post("/compare")
def compare_endpoint(request: ChatRequest):
    """
    Comparison Endpoint.
    Runs BOTH the Engine and the Raw LLM.
    """
    # 1. Engine Run
    engine_prompt = orchestrator.process_interaction(
        user_text=request.message,
        request=request.user_data,
        emotion=request.emotion_data
    )
    engine_response = orchestrator.call_llm(engine_prompt)

    # 2. Raw LLM Run
    raw_response, raw_prompt = orchestrator.call_raw_llm(
        user_text=request.message,
        request=request.user_data
    )

    return {
        "engine_response": engine_response,
        "raw_response": raw_response,
        "engine_prompt": engine_prompt,
        "raw_prompt": raw_prompt
    }

from fastapi.responses import StreamingResponse
import json

@router.post("/chat/stream")
async def stream_chat_endpoint(request: ChatRequest):
    """
    Streaming Chat Endpoint.
    Uses Server-Sent Events (SSE) to stream the response.
    """
    engine_prompt = orchestrator.process_interaction(
        user_text=request.message,
        request=request.user_data,
        emotion=request.emotion_data
    )

    async def event_generator():
        # 1. Send the Debug Prompt first
        yield f"event: debug\ndata: {json.dumps({'prompt': engine_prompt})}\n\n"

        # 2. Stream the LLM tokens
        for token in orchestrator.stream_llm(engine_prompt):
            # Escape newlines for SSE data payload if necessary, 
            # but for simple tokens usually raw is fine if we wrap in JSON or just send raw text.
            # Let's send raw text for simplicity, but handle newlines carefully.
            # Actually, standard SSE data payload handles newlines if we prefix each line with data:.
            # But for simplicity, let's just JSON encode the token to be safe.
            yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

from fastapi import WebSocket, WebSocketDisconnect

@router.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # 1. Receive Message
            data = await websocket.receive_json()
            
            # Parse input (manually validation for now, or use Pydantic)
            user_text = data.get("message")
            user_data_dict = data.get("user_data")
            emotion_data_dict = data.get("emotion_data")
            
            # Convert dicts back to Pydantic models
            from app.models.schemas import RefundRequest, CustomerEmotion
            user_data = RefundRequest(**user_data_dict)
            emotion_data = CustomerEmotion(**emotion_data_dict)

            # 2. Process Logic (Neuro-symbolic)
            engine_prompt = orchestrator.process_interaction(
                user_text=user_text,
                request=user_data,
                emotion=emotion_data
            )

            # 3. Send Debug Event
            await websocket.send_json({
                "type": "debug",
                "prompt": engine_prompt
            })

            # 4. Stream LLM Tokens
            full_response = ""
            for token in orchestrator.stream_llm(engine_prompt):
                full_response += token
                await websocket.send_json({
                    "type": "token",
                    "content": token
                })
            
            # Optional: Send "Done" event or just let the client infer
            
    except WebSocketDisconnect:
        print("Client disconnected")
