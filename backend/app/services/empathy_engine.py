from app.models.schemas import CustomerEmotion

def get_empathy_instruction(emotion: CustomerEmotion) -> str:
    """
    Maps the emotional state to a specific System Prompt instruction.
    This is the 'Empathy Layer'.
    """
    base_instruction = "You are a helpful customer support agent."

    if emotion.anger_level > 0.7:
        return (
            f"{base_instruction} The customer is FURIOUS (Anger: {emotion.anger_level}). "
            "Your goal is de-escalation. "
            "1. Use short, clear sentences. "
            "2. Do NOT use flowery language or excessive apologies. "
            "3. Validate their frustration immediately (e.g., 'I understand why this is upsetting'). "
            "4. Get straight to the solution."
        )
    elif emotion.anger_level > 0.3:
        return (
            f"{base_instruction} The customer is annoyed. "
            "Be professional and efficient. "
            "Acknowledge the issue but remain calm and objective."
        )
    else:
        return (
            f"{base_instruction} The customer is calm. "
            "Be friendly, warm, and engaging. "
            "Feel free to use a conversational tone."
        )
