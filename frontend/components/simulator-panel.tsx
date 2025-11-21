"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { RefundRequest, CustomerEmotion } from "@/lib/types";
import { format } from "date-fns";
import { CalendarIcon } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { cn } from "@/lib/utils";

interface SimulatorPanelProps {
    userData: RefundRequest;
    setUserData: (data: RefundRequest) => void;
    emotionData: CustomerEmotion;
    setEmotionData: (data: CustomerEmotion) => void;
}

export function SimulatorPanel({ userData, setUserData, emotionData, setEmotionData }: SimulatorPanelProps) {

    const handleQuickScenario = (type: "angry_late" | "calm_valid") => {
        if (type === "angry_late") {
            setUserData({
                ...userData,
                purchase_date: "2022-01-01T00:00:00",
                reason: "changed mind",
                price: 120.0,
            });
            setEmotionData({
                anger_level: 0.9,
                sentiment: "negative",
            });
        } else {
            setUserData({
                ...userData,
                purchase_date: new Date().toISOString(), // Today
                reason: "defective",
                price: 45.0,
            });
            setEmotionData({
                anger_level: 0.1,
                sentiment: "neutral",
            });
        }
    };

    return (
        <div className="space-y-6">
            <Card>
                <CardHeader>
                    <CardTitle>Quick Scenarios</CardTitle>
                </CardHeader>
                <CardContent className="flex gap-2">
                    <Button variant="destructive" onClick={() => handleQuickScenario("angry_late")}>
                        😡 Angry & Late
                    </Button>
                    <Button variant="outline" onClick={() => handleQuickScenario("calm_valid")}>
                        😇 Calm & Valid
                    </Button>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>Customer Emotion</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="space-y-2">
                        <div className="flex justify-between">
                            <Label>Anger Level</Label>
                            <span className="text-sm text-muted-foreground">{(emotionData.anger_level * 100).toFixed(0)}%</span>
                        </div>
                        <Slider
                            value={[emotionData.anger_level]}
                            max={1}
                            step={0.1}
                            onValueChange={(vals) => setEmotionData({ ...emotionData, anger_level: vals[0] })}
                            className={cn(emotionData.anger_level > 0.7 ? "text-red-500" : "text-primary")}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label>Sentiment</Label>
                        <Select
                            value={emotionData.sentiment}
                            onValueChange={(val: any) => setEmotionData({ ...emotionData, sentiment: val })}
                        >
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="positive">Positive</SelectItem>
                                <SelectItem value="neutral">Neutral</SelectItem>
                                <SelectItem value="negative">Negative</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>Transaction Data</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="space-y-2">
                        <Label>Product Name</Label>
                        <Input
                            value={userData.product_name}
                            onChange={(e) => setUserData({ ...userData, product_name: e.target.value })}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label>Price ($)</Label>
                        <Input
                            type="number"
                            value={userData.price}
                            onChange={(e) => setUserData({ ...userData, price: parseFloat(e.target.value) })}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label>Purchase Date</Label>
                        <Popover>
                            <PopoverTrigger asChild>
                                <Button
                                    variant={"outline"}
                                    className={cn(
                                        "w-full justify-start text-left font-normal",
                                        !userData.purchase_date && "text-muted-foreground"
                                    )}
                                >
                                    <CalendarIcon className="mr-2 h-4 w-4" />
                                    {userData.purchase_date ? format(new Date(userData.purchase_date), "PPP") : <span>Pick a date</span>}
                                </Button>
                            </PopoverTrigger>
                            <PopoverContent className="w-auto p-0">
                                <Calendar
                                    mode="single"
                                    selected={new Date(userData.purchase_date)}
                                    onSelect={(date) => date && setUserData({ ...userData, purchase_date: date.toISOString() })}
                                    initialFocus
                                />
                            </PopoverContent>
                        </Popover>
                    </div>
                    <div className="space-y-2">
                        <Label>Reason</Label>
                        <Input
                            value={userData.reason}
                            onChange={(e) => setUserData({ ...userData, reason: e.target.value })}
                        />
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
