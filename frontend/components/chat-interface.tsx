"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { RefundRequest, CustomerEmotion, ChatResponse } from "@/lib/types";
import { Send, Bot, User, Terminal } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

interface ChatInterfaceProps {
    userData: RefundRequest;
    emotionData: CustomerEmotion;
    comparisonMode: boolean;
}

interface Message {
    role: "user" | "assistant" | "raw_assistant";
    content: string;
}

export function ChatInterface({ userData, emotionData, comparisonMode }: ChatInterfaceProps) {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [lastDebugPrompt, setLastDebugPrompt] = useState<string | null>(null);
    const [lastRawPrompt, setLastRawPrompt] = useState<string | null>(null);

    // WebSocket State
    const [socket, setSocket] = useState<WebSocket | null>(null);
    const [isConnected, setIsConnected] = useState(false);

    const handleConnect = () => {
        if (socket) {
            socket.close();
            setSocket(null);
            setIsConnected(false);
            return;
        }

        const ws = new WebSocket("ws://127.0.0.1:8000/api/v1/ws/chat");

        ws.onopen = () => {
            setIsConnected(true);
            console.log("Connected to WebSocket");
        };

        ws.onclose = () => {
            setIsConnected(false);
            setSocket(null);
            console.log("Disconnected from WebSocket");
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === "debug") {
                setLastDebugPrompt(data.prompt);
            } else if (data.type === "token") {
                setMessages((prev) => {
                    const newMsgs = [...prev];
                    const lastMsg = newMsgs[newMsgs.length - 1];

                    // Ensure we are appending to the assistant's message
                    if (lastMsg && lastMsg.role === "assistant") {
                        // IMMUTABLE UPDATE to prevent double-text bug
                        const updatedMsg = { ...lastMsg, content: lastMsg.content + data.content };
                        newMsgs[newMsgs.length - 1] = updatedMsg;
                        return newMsgs;
                    }
                    return prev;
                });
                setLoading(false); // Start showing as soon as first token arrives
            }
        };

        setSocket(ws);
    };

    const handleSend = async () => {
        if (!input.trim()) return;

        const userMsg: Message = { role: "user", content: input };
        setMessages((prev) => [...prev, userMsg]);
        setInput("");
        setLoading(true);

        if (comparisonMode) {
            // Comparison Mode (HTTP)
            try {
                const res = await fetch("http://127.0.0.1:8000/api/v1/compare", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        message: userMsg.content,
                        user_data: userData,
                        emotion_data: emotionData,
                    }),
                });
                const data = await res.json();
                setMessages((prev) => [
                    ...prev,
                    { role: "assistant", content: data.engine_response },
                    { role: "raw_assistant", content: data.raw_response }
                ]);
                setLastDebugPrompt(data.engine_prompt);
                setLastRawPrompt(data.raw_prompt);
                setLoading(false);
            } catch (e) {
                setMessages((prev) => [...prev, { role: "assistant", content: "Error connecting to backend." }]);
                setLoading(false);
            }
        } else {
            // WebSocket Mode
            if (!socket || !isConnected) {
                setMessages((prev) => [...prev, { role: "assistant", content: "Please connect to the server first." }]);
                setLoading(false);
                return;
            }

            // Add placeholder for assistant
            setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

            socket.send(JSON.stringify({
                message: userMsg.content,
                user_data: userData,
                emotion_data: emotionData
            }));
        }
    };

    return (
        <div className="flex flex-col h-full gap-4">
            {/* Header with Connect Button */}
            <div className="flex justify-between items-center">
                <CardTitle>{comparisonMode ? "Comparison Mode: Engine vs. Raw LLM" : "Live Interaction"}</CardTitle>
                {!comparisonMode && (
                    <Button
                        variant={isConnected ? "destructive" : "default"}
                        onClick={handleConnect}
                        size="sm"
                    >
                        {isConnected ? "Disconnect" : "Connect Server"}
                    </Button>
                )}
            </div>

            {/* Chat Area */}
            <Card className="flex-1 flex flex-col min-h-[500px]">
                <CardContent className="flex-1 flex flex-col gap-4">
                    <ScrollArea className="flex-1 h-[400px] pr-4">
                        <div className="space-y-4">
                            {messages.map((m, i) => (
                                <div key={i} className={`flex gap-3 ${m.role === "user" ? "justify-end" : "justify-start"}`}>

                                    {/* Avatar Logic */}
                                    {m.role === "assistant" && (
                                        <div className="w-8 h-8 rounded-full bg-green-500/10 flex items-center justify-center border border-green-500/20" title="Neuro-Symbolic Engine">
                                            <Bot className="w-5 h-5 text-green-500" />
                                        </div>
                                    )}
                                    {m.role === "raw_assistant" && (
                                        <div className="w-8 h-8 rounded-full bg-red-500/10 flex items-center justify-center border border-red-500/20" title="Raw LLM Wrapper">
                                            <Bot className="w-5 h-5 text-red-500" />
                                        </div>
                                    )}

                                    {/* Message Bubble Logic */}
                                    <div
                                        className={`p-3 rounded-lg max-w-[80%] ${m.role === "user"
                                            ? "bg-primary text-primary-foreground"
                                            : m.role === "assistant"
                                                ? "bg-green-500/10 border border-green-500/20 text-foreground"
                                                : "bg-red-500/10 border border-red-500/20 text-foreground"
                                            }`}
                                    >
                                        {m.role === "assistant" && <div className="text-xs font-bold text-green-500 mb-1">ENGINE</div>}
                                        {m.role === "raw_assistant" && <div className="text-xs font-bold text-red-500 mb-1">RAW LLM</div>}
                                        {m.content}
                                    </div>

                                    {m.role === "user" && (
                                        <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center">
                                            <User className="w-5 h-5 text-primary-foreground" />
                                        </div>
                                    )}
                                </div>
                            ))}
                            {loading && (
                                <div className="flex gap-3">
                                    <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center">
                                        <Bot className="w-5 h-5 text-muted-foreground" />
                                    </div>
                                    <div className="bg-muted p-3 rounded-lg animate-pulse">Thinking...</div>
                                </div>
                            )}
                        </div>
                    </ScrollArea>

                    <div className="flex gap-2 mt-auto">
                        <Input
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && handleSend()}
                            placeholder="Type your message..."
                        />
                        <Button onClick={handleSend} disabled={loading}>
                            <Send className="w-4 h-4" />
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* Debug Panel */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Collapsible className="border rounded-lg bg-card">
                    <CollapsibleTrigger className="flex items-center gap-2 p-4 w-full hover:bg-muted/50 transition-colors">
                        <Terminal className="w-4 h-4 text-green-500" />
                        <span className="font-semibold text-green-500">Engine Prompt (Neuro-Symbolic)</span>
                    </CollapsibleTrigger>
                    <CollapsibleContent className="p-4 pt-0 border-t bg-black/90 text-green-400 font-mono text-xs overflow-x-auto max-h-[200px]">
                        <pre className="whitespace-pre-wrap">
                            {lastDebugPrompt || "// Waiting for interaction..."}
                        </pre>
                    </CollapsibleContent>
                </Collapsible>

                {comparisonMode && (
                    <Collapsible className="border rounded-lg bg-card">
                        <CollapsibleTrigger className="flex items-center gap-2 p-4 w-full hover:bg-muted/50 transition-colors">
                            <Terminal className="w-4 h-4 text-red-500" />
                            <span className="font-semibold text-red-500">Raw Prompt (Naive RAG)</span>
                        </CollapsibleTrigger>
                        <CollapsibleContent className="p-4 pt-0 border-t bg-black/90 text-red-400 font-mono text-xs overflow-x-auto max-h-[200px]">
                            <pre className="whitespace-pre-wrap">
                                {lastRawPrompt || "// Waiting for interaction..."}
                            </pre>
                        </CollapsibleContent>
                    </Collapsible>
                )}
            </div>
        </div>
    );
}
