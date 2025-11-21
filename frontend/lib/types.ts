export interface RefundRequest {
    product_name: string;
    purchase_date: string; // ISO string
    reason: string;
    price: number;
    customer_id: string;
}

export interface CustomerEmotion {
    anger_level: number;
    sentiment: "positive" | "neutral" | "negative";
}

export interface ChatRequest {
    message: string;
    user_data: RefundRequest;
    emotion_data: CustomerEmotion;
}

export interface ChatResponse {
    response: string;
    debug_prompt: string;
}

export interface ComparisonResponse {
    engine_response: string;
    raw_response: string;
    engine_prompt: string;
    raw_prompt: string;
}
