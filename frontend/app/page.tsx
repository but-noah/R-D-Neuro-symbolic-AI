"use client";

import { useState } from "react";
import { SimulatorPanel } from "@/components/simulator-panel";
import { ChatInterface } from "@/components/chat-interface";
import { RefundRequest, CustomerEmotion } from "@/lib/types";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";

export default function Home() {
  // Default State
  const [userData, setUserData] = useState<RefundRequest>({
    product_name: "Gaming Mouse",
    purchase_date: "2022-01-01T00:00:00",
    reason: "changed mind",
    price: 60.0,
    customer_id: "CUST-001",
  });

  const [emotionData, setEmotionData] = useState<CustomerEmotion>({
    anger_level: 0.5,
    sentiment: "negative",
  });

  const [comparisonMode, setComparisonMode] = useState(false);

  return (
    <main className="min-h-screen bg-background p-8">
      <div className="max-w-7xl mx-auto space-y-8">
        <div className="flex flex-col gap-2">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-4xl font-bold tracking-tight">Anti-Hallucination Empathy Engine</h1>
              <p className="text-muted-foreground text-lg">
                Neuro-symbolic AI Research Prototype
              </p>
            </div>
            <div className="flex items-center space-x-2 bg-card p-4 rounded-lg border">
              <Switch id="compare-mode" checked={comparisonMode} onCheckedChange={setComparisonMode} />
              <Label htmlFor="compare-mode" className="font-semibold">Comparison Mode</Label>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Left Column: Simulator Config */}
          <div className="lg:col-span-4">
            <SimulatorPanel
              userData={userData}
              setUserData={setUserData}
              emotionData={emotionData}
              setEmotionData={setEmotionData}
            />
          </div>

          {/* Right Column: Chat Interface */}
          <div className="lg:col-span-8">
            <ChatInterface userData={userData} emotionData={emotionData} comparisonMode={comparisonMode} />
          </div>
        </div>
      </div>
    </main>
  );
}
