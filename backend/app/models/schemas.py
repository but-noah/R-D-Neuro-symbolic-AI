from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Literal

class RefundRequest(BaseModel):
    """Data extracted from the user's message."""
    product_name: str
    purchase_date: datetime
    reason: str
    price: float
    customer_id: str

class RefundDecision(BaseModel):
    """The hard logic decision output."""
    allowed: bool
    reason: str
    offer_coupon: bool = False
    coupon_value: Optional[float] = None

class CustomerEmotion(BaseModel):
    """Simulated emotional state."""
    anger_level: float = Field(..., ge=0.0, le=1.0, description="0.0 = Calm, 1.0 = Furious")
    sentiment: Literal["positive", "neutral", "negative"]

class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""
    message: str
    user_data: RefundRequest
    emotion_data: CustomerEmotion
