"use client";

import { useState, useRef, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";

// Available test audio files
const TEST_AUDIO_FILES = [
  { value: "neutral_test_001.mp3", label: "Neutral 1: Wrong item received" },
  { value: "neutral_test_002.mp3", label: "Neutral 2: Delayed delivery" },
  { value: "neutral_test_003.mp3", label: "Neutral 3: Product doesn't fit needs" },
  { value: "angry_medium_test_001.mp3", label: "Angry Medium 1: Delayed refund (3 weeks)" },
  { value: "angry_medium_test_002.mp3", label: "Angry Medium 2: Damaged item, no help" },
  { value: "angry_medium_test_003.mp3", label: "Angry Medium 3: Second call, broken promise" },
  { value: "angry_high_test_001.mp3", label: "Angry High 1: Month delay, runaround" },
  { value: "angry_high_test_002.mp3", label: "Angry High 2: Broken product, unhelpful support" },
  { value: "angry_high_test_003.mp3", label: "Angry High 3: Fourth call, legal threat" },
];

interface STTMetrics {
  mode?: string;
  eager_eot_triggered?: boolean;
  turn_resumed_count?: number;
  realtime_factor?: number;
  audio_duration_ms?: number;
}

interface STTResult {
  transcript: string;
  latency: number;
  method: string;
  confidence?: number;
  metrics?: STTMetrics;
}

interface EmotionResult {
  anger: number;
  sentiment: string;
  category: string;
  keywords: string[];
  latency: number;
  method: string;
}

interface FillerResult {
  category: string;
  audio_b64: string;
  size_kb: number;
  latency: number;
}

interface LogicResult {
  decision: {
    allowed: boolean;
    amount: number;
    reason: string;
  };
  order_details: any;
  latency: number;
}

interface ResponseResult {
  text: string;
  latency: number;
  method: string;
}

interface ResponseAudioResult {
  audio_b64: string;
  size_kb: number;
  latency: number;
}

interface MetricsResult {
  ttrs: number;
  stt_latency: number;
  emotion_latency: number;
  filler_latency: number;
  logic_latency: number;
  response_latency: number;
  tts_latency: number;
  total_latency: number;
  ttrs_target: number;
  ttrs_met: boolean;
}

export default function OptimizedVoicePage() {
  // Connection state
  const [connected, setConnected] = useState(false);
  const [testing, setTesting] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const audioQueueRef = useRef<HTMLAudioElement[]>([]);
  const isPlayingRef = useRef(false);

  // Web Audio API for PCM streaming
  const audioContextRef = useRef<AudioContext | null>(null);
  const pcmBuffersRef = useRef<AudioBuffer[]>([]);
  const isPlayingPCMRef = useRef(false);

  // Test configuration
  const [selectedAudio, setSelectedAudio] = useState(TEST_AUDIO_FILES[0].value);

  // Pipeline results
  const [sttResult, setSTTResult] = useState<STTResult | null>(null);
  const [interimTranscript, setInterimTranscript] = useState<string>("");
  const [emotionResult, setEmotionResult] = useState<EmotionResult | null>(null);
  const [emotionLLMResult, setEmotionLLMResult] = useState<EmotionResult | null>(null);
  const [fillerResult, setFillerResult] = useState<FillerResult | null>(null);
  const [logicResult, setLogicResult] = useState<LogicResult | null>(null);
  const [responseResult, setResponseResult] = useState<ResponseResult | null>(null);
  const [responseAudioResult, setResponseAudioResult] = useState<ResponseAudioResult | null>(null);
  const [metricsResult, setMetricsResult] = useState<MetricsResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ttrsUpdate, setTTRSUpdate] = useState<{ttrs: number; ttrs_met: boolean} | null>(null);

  // Performance tracking
  const [pipelineStart, setPipelineStart] = useState<number | null>(null);
  const [phaseTimestamps, setPhaseTimestamps] = useState<{[key: string]: number}>({});

  // Audio playback queue management
  const playAudioQueue = async () => {
    if (isPlayingRef.current || audioQueueRef.current.length === 0) {
      return;
    }

    isPlayingRef.current = true;

    while (audioQueueRef.current.length > 0) {
      const audio = audioQueueRef.current.shift()!;

      await new Promise<void>((resolve) => {
        audio.onended = () => resolve();
        audio.onerror = () => resolve();
        audio.play().catch((e) => {
          console.error("Error playing audio:", e);
          resolve();
        });
      });
    }

    isPlayingRef.current = false;
  };

  const addToAudioQueue = (audioB64: string) => {
    try {
      const binaryString = atob(audioB64);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      const blob = new Blob([bytes], { type: "audio/mp3" });
      const url = URL.createObjectURL(blob);

      const audio = new Audio(url);
      audioQueueRef.current.push(audio);

      playAudioQueue();
    } catch (error) {
      console.error("Error adding audio to queue:", error);
    }
  };

  // Initialize Web Audio Context
  const initAudioContext = () => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
    }
  };

  // Handle PCM audio chunk
  const handlePCMChunk = async (audioB64: string, sampleRate: number) => {
    try {
      initAudioContext();

      const binaryString = atob(audioB64);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      const pcmData = new Int16Array(bytes.buffer);
      const audioBuffer = audioContextRef.current!.createBuffer(
        1,
        pcmData.length,
        sampleRate
      );

      const channelData = audioBuffer.getChannelData(0);
      for (let i = 0; i < pcmData.length; i++) {
        channelData[i] = pcmData[i] / 32768.0;
      }

      pcmBuffersRef.current.push(audioBuffer);

      if (!isPlayingPCMRef.current) {
        playPCMBuffers();
      }
    } catch (error) {
      console.error("Error handling PCM chunk:", error);
    }
  };

  // Play PCM audio buffers in sequence
  const playPCMBuffers = () => {
    if (isPlayingPCMRef.current || pcmBuffersRef.current.length === 0 || !audioContextRef.current) {
      return;
    }

    isPlayingPCMRef.current = true;

    const playNextBuffer = () => {
      if (pcmBuffersRef.current.length === 0) {
        isPlayingPCMRef.current = false;
        return;
      }

      const buffer = pcmBuffersRef.current.shift()!;
      const source = audioContextRef.current!.createBufferSource();
      source.buffer = buffer;
      source.connect(audioContextRef.current!.destination);

      source.onended = () => {
        playNextBuffer();
      };

      source.start();
    };

    playNextBuffer();
  };

  // Connect to WebSocket
  const handleConnect = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log("Already connected");
      return;
    }

    const ws = new WebSocket("ws://127.0.0.1:8000/api/v1/ws/test-voice");

    ws.onopen = () => {
      console.log("✅ Connected to optimized voice pipeline");
      setConnected(true);
      setError(null);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const timestamp = Date.now();

      switch (data.type) {
        case "stt_interim":
          setInterimTranscript(data.transcript || "");
          break;

        case "stt":
          setSTTResult({
            transcript: data.transcript,
            latency: data.latency,
            method: data.method,
            confidence: data.confidence,
            metrics: data.metrics,
          });
          setInterimTranscript("");
          setPhaseTimestamps(prev => ({...prev, stt: timestamp}));
          break;

        case "emotion":
          setEmotionResult({
            anger: data.anger,
            sentiment: data.sentiment,
            category: data.category,
            keywords: data.keywords || [],
            latency: data.latency,
            method: data.method,
          });
          setPhaseTimestamps(prev => ({...prev, emotion: timestamp}));
          break;

        case "emotion_llm_update":
          setEmotionLLMResult({
            anger: data.anger,
            sentiment: data.sentiment,
            category: data.category,
            keywords: data.keywords || [],
            latency: data.latency,
            method: data.method,
          });
          setPhaseTimestamps(prev => ({...prev, emotion_llm: timestamp}));
          break;

        case "filler":
          setFillerResult({
            category: data.category,
            audio_b64: data.audio_b64,
            size_kb: data.size_kb,
            latency: data.latency,
          });
          addToAudioQueue(data.audio_b64);
          setPhaseTimestamps(prev => ({...prev, filler: timestamp}));
          break;

        case "logic":
          setLogicResult({
            decision: data.decision,
            order_details: data.order_details,
            latency: data.latency,
          });
          setPhaseTimestamps(prev => ({...prev, logic: timestamp}));
          break;

        case "response_text":
          setResponseResult({
            text: data.text,
            latency: data.latency,
            method: data.method,
          });
          setPhaseTimestamps(prev => ({...prev, response: timestamp}));
          break;

        case "response_audio":
          setResponseAudioResult({
            audio_b64: data.audio_b64,
            size_kb: data.size_kb,
            latency: data.latency,
          });
          addToAudioQueue(data.audio_b64);
          break;

        case "tts_chunk":
          handlePCMChunk(data.audio_b64, data.sample_rate);
          break;

        case "tts_complete":
          setResponseAudioResult({
            audio_b64: "",
            size_kb: data.total_bytes / 1024,
            latency: data.total_latency,
          });
          setPhaseTimestamps(prev => ({...prev, tts: timestamp}));
          break;

        case "ttrs_update":
          setTTRSUpdate({
            ttrs: data.ttrs,
            ttrs_met: data.ttrs_met
          });
          break;

        case "metrics":
          setMetricsResult(data);
          setTesting(false);
          break;

        case "error":
          setError(data.message);
          setTesting(false);
          break;
      }
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
      setError("WebSocket connection error");
      setConnected(false);
    };

    ws.onclose = () => {
      console.log("🔌 Disconnected from optimized voice pipeline");
      setConnected(false);
    };

    wsRef.current = ws;
  };

  // Run test
  const handleTest = () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setError("Not connected to server");
      return;
    }

    // Reset all state
    setPipelineStart(Date.now());
    setPhaseTimestamps({});
    setSTTResult(null);
    setInterimTranscript("");
    setEmotionResult(null);
    setEmotionLLMResult(null);
    setFillerResult(null);
    setLogicResult(null);
    setResponseResult(null);
    setResponseAudioResult(null);
    setMetricsResult(null);
    setTTRSUpdate(null);
    setError(null);
    setTesting(true);

    // Clear audio queue
    audioQueueRef.current = [];
    isPlayingRef.current = false;

    // Send test request
    wsRef.current.send(
      JSON.stringify({
        audio_file: selectedAudio,
      })
    );
  };

  // Disconnect
  const handleDisconnect = () => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  // Calculate latency reduction
  const getLatencyReduction = (optimized: number, baseline: number = 1275) => {
    const reduction = ((baseline - optimized) / baseline) * 100;
    return reduction.toFixed(1);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-white p-8">
      <div className="max-w-[1800px] mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-5xl font-bold mb-2 bg-gradient-to-r from-cyan-400 via-blue-500 to-purple-600 bg-clip-text text-transparent">
              Optimized Voice Pipeline
            </h1>
            <p className="text-slate-400 text-lg">
              Real-time performance monitoring with Deepgram Flux STT streaming
            </p>
          </div>
          <div className="flex items-center space-x-3">
            <div className={`w-4 h-4 rounded-full ${connected ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
            <span className="text-sm font-medium text-slate-300">
              {connected ? "Connected" : "Disconnected"}
            </span>
          </div>
        </div>

        {/* Controls */}
        <Card className="bg-slate-900/50 border-slate-700">
          <CardContent className="pt-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {/* Audio Selection */}
              <div className="md:col-span-2">
                <label className="block text-sm font-medium mb-2 text-slate-300">
                  Test Audio Scenario
                </label>
                <Select value={selectedAudio} onValueChange={setSelectedAudio} disabled={testing}>
                  <SelectTrigger className="bg-slate-800 border-slate-600">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TEST_AUDIO_FILES.map((file) => (
                      <SelectItem key={file.value} value={file.value}>
                        {file.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Actions */}
              <div className="md:col-span-2 flex items-end space-x-2">
                {!connected ? (
                  <Button onClick={handleConnect} className="flex-1 bg-blue-600 hover:bg-blue-700">
                    Connect to Pipeline
                  </Button>
                ) : (
                  <>
                    <Button
                      onClick={handleTest}
                      disabled={testing}
                      className="flex-1 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700"
                    >
                      {testing ? (
                        <span className="flex items-center space-x-2">
                          <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                          <span>Processing...</span>
                        </span>
                      ) : (
                        "Run Test"
                      )}
                    </Button>
                    <Button onClick={handleDisconnect} variant="destructive">
                      Disconnect
                    </Button>
                  </>
                )}
              </div>
            </div>

            {/* Error Display */}
            {error && (
              <div className="mt-4 bg-red-900/30 border border-red-500/50 rounded-lg p-4">
                <p className="text-red-200">❌ {error}</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* TTRS Live Indicator */}
        {ttrsUpdate && !metricsResult && (
          <Card className="bg-gradient-to-r from-blue-900/40 to-purple-900/40 border-2 border-blue-500/50">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-4">
                  <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse" />
                  <span className="text-xl font-semibold">Time-To-Respond-Start (TTRS)</span>
                </div>
                <div className="flex items-center space-x-4">
                  <span className={`text-4xl font-bold ${ttrsUpdate.ttrs_met ? "text-green-400" : "text-yellow-400"}`}>
                    {ttrsUpdate.ttrs}ms
                  </span>
                  <Badge variant={ttrsUpdate.ttrs_met ? "default" : "secondary"} className="text-sm">
                    {ttrsUpdate.ttrs_met ? "✅ Target Met" : "⏱️ Processing"}
                  </Badge>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          {/* Left Column - STT Optimizations */}
          <div className="space-y-6">
            {/* STT Performance Card */}
            <Card className="bg-slate-900/50 border-slate-700">
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <span className="text-2xl">🚀</span>
                  <span>STT: Flux Streaming</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {sttResult ? (
                  <>
                    {/* Transcript */}
                    <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                      <p className="text-sm text-slate-300 italic">"{sttResult.transcript}"</p>
                    </div>

                    {/* Performance Metrics */}
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-slate-400">Latency</span>
                        <div className="flex items-center space-x-2">
                          <Badge variant="outline" className="bg-green-500/20 text-green-400 border-green-500/50">
                            {sttResult.latency}ms
                          </Badge>
                          {sttResult.latency < 1275 && (
                            <Badge className="bg-blue-500/20 text-blue-400 border-blue-500/50">
                              -{getLatencyReduction(sttResult.latency)}%
                            </Badge>
                          )}
                        </div>
                      </div>

                      {sttResult.metrics?.mode && (
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-slate-400">Mode</span>
                          <Badge variant={sttResult.metrics.mode === "flux" ? "default" : "secondary"}>
                            {sttResult.metrics.mode === "flux" ? "⚡ Flux Streaming" : "📡 Nova-3 Fallback"}
                          </Badge>
                        </div>
                      )}

                      {sttResult.metrics?.eager_eot_triggered !== undefined && (
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-slate-400">Eager EOT</span>
                          <Badge variant={sttResult.metrics.eager_eot_triggered ? "default" : "outline"}>
                            {sttResult.metrics.eager_eot_triggered ? "✅ Triggered" : "⏸️ Not Triggered"}
                          </Badge>
                        </div>
                      )}

                      {sttResult.metrics?.turn_resumed_count !== undefined && (
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-slate-400">Turn Resumes</span>
                          <span className="text-sm font-mono text-slate-300">
                            {sttResult.metrics.turn_resumed_count}
                          </span>
                        </div>
                      )}

                      {sttResult.metrics?.realtime_factor !== undefined && (
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-slate-400">Realtime Factor</span>
                          <span className="text-sm font-mono text-slate-300">
                            {sttResult.metrics.realtime_factor.toFixed(2)}x
                          </span>
                        </div>
                      )}

                      {sttResult.confidence !== undefined && (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-slate-400">Confidence</span>
                            <span className="text-sm font-mono text-slate-300">
                              {(sttResult.confidence * 100).toFixed(1)}%
                            </span>
                          </div>
                          <Progress value={sttResult.confidence * 100} className="h-2" />
                        </div>
                      )}
                    </div>

                    <Separator className="bg-slate-700" />

                    {/* Baseline Comparison */}
                    <div className="bg-slate-800/30 rounded-lg p-3 border border-slate-700">
                      <div className="text-xs text-slate-400 mb-2">Baseline Comparison</div>
                      <div className="space-y-1 text-xs">
                        <div className="flex justify-between">
                          <span className="text-slate-500">Nova-3 Prerecorded:</span>
                          <span className="text-slate-400">~1275ms</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-green-400 font-semibold">Flux Streaming:</span>
                          <span className="text-green-400 font-semibold">{sttResult.latency}ms</span>
                        </div>
                        <div className="flex justify-between pt-1 border-t border-slate-700">
                          <span className="text-blue-400">Improvement:</span>
                          <span className="text-blue-400 font-bold">
                            {getLatencyReduction(sttResult.latency)}% faster
                          </span>
                        </div>
                      </div>
                    </div>
                  </>
                ) : interimTranscript ? (
                  <div className="bg-blue-900/20 rounded-lg p-4 border border-blue-500/30">
                    <div className="flex items-center space-x-2 mb-2">
                      <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
                      <span className="text-xs text-blue-400 font-semibold">INTERIM TRANSCRIPT</span>
                    </div>
                    <p className="text-sm text-slate-300 italic">"{interimTranscript}"</p>
                  </div>
                ) : (
                  <div className="text-center text-slate-500 py-8">
                    <p className="text-sm">Waiting for audio input...</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Emotion Detection */}
            {emotionResult && (
              <Card className="bg-slate-900/50 border-slate-700">
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <span className="text-2xl">😡</span>
                    <span>Emotion Detection</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Fast Emotion */}
                  <div className="bg-gradient-to-r from-blue-900/30 to-purple-900/30 rounded-lg p-4 border border-blue-500/30">
                    <div className="flex items-center justify-between mb-3">
                      <Badge variant="outline" className="bg-blue-500/20 text-blue-400">
                        ⚡ Fast (Keyword)
                      </Badge>
                      <span className="text-xs text-slate-400">{emotionResult.latency}ms</span>
                    </div>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-slate-400">Category</span>
                        <Badge className={
                          emotionResult.category === "angry_high" ? "bg-red-500/20 text-red-400" :
                          emotionResult.category === "angry_medium" ? "bg-orange-500/20 text-orange-400" :
                          "bg-green-500/20 text-green-400"
                        }>
                          {emotionResult.category.replace("_", " ").toUpperCase()}
                        </Badge>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-slate-400">Anger Score</span>
                        <span className="text-sm font-mono text-yellow-400">
                          {emotionResult.anger.toFixed(2)}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* LLM Emotion */}
                  {emotionLLMResult && (
                    <div className="bg-gradient-to-r from-purple-900/30 to-pink-900/30 rounded-lg p-4 border border-purple-500/30">
                      <div className="flex items-center justify-between mb-3">
                        <Badge variant="outline" className="bg-purple-500/20 text-purple-400">
                          🎯 Accurate (LLM)
                        </Badge>
                        <span className="text-xs text-slate-400">{emotionLLMResult.latency}ms</span>
                      </div>
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-slate-400">Category</span>
                          <Badge className={
                            emotionLLMResult.category === "angry_high" ? "bg-red-500/20 text-red-400" :
                            emotionLLMResult.category === "angry_medium" ? "bg-orange-500/20 text-orange-400" :
                            "bg-green-500/20 text-green-400"
                          }>
                            {emotionLLMResult.category.replace("_", " ").toUpperCase()}
                          </Badge>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-slate-400">Anger Score</span>
                          <span className="text-sm font-mono text-yellow-400">
                            {emotionLLMResult.anger.toFixed(2)}
                          </span>
                        </div>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>

          {/* Middle Column - Pipeline Flow */}
          <div className="space-y-6">
            {/* Filler */}
            {fillerResult && (
              <Card className="bg-slate-900/50 border-slate-700">
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <span className="text-2xl">🎵</span>
                    <span>Filler Audio</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-400">Category</span>
                    <Badge className="bg-purple-500/20 text-purple-400">
                      {fillerResult.category}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-400">Latency</span>
                    <span className="text-sm font-mono text-green-400">
                      {fillerResult.latency.toFixed(2)}ms
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-400">Size</span>
                    <span className="text-sm font-mono text-slate-300">
                      {fillerResult.size_kb.toFixed(1)} KB
                    </span>
                  </div>
                  <div className="bg-blue-900/20 rounded-lg p-3 border border-blue-500/30 flex items-center justify-center space-x-2">
                    <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
                    <span className="text-xs text-blue-400">Playing...</span>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Logic */}
            {logicResult && (
              <Card className="bg-slate-900/50 border-slate-700">
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <span className="text-2xl">🧠</span>
                    <span>Logic Execution</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className={`rounded-lg p-4 border ${
                    logicResult.decision.allowed
                      ? "bg-green-900/20 border-green-500/50"
                      : "bg-red-900/20 border-red-500/50"
                  }`}>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-semibold">Decision</span>
                      <Badge variant={logicResult.decision.allowed ? "default" : "destructive"}>
                        {logicResult.decision.allowed ? "✅ APPROVED" : "❌ DENIED"}
                      </Badge>
                    </div>
                    {logicResult.decision.allowed && (
                      <div className="text-3xl font-bold text-green-400 mb-2">
                        ${logicResult.decision.amount.toFixed(2)}
                      </div>
                    )}
                    <p className="text-sm text-slate-400">{logicResult.decision.reason}</p>
                  </div>

                  <div className="flex items-center justify-between text-sm">
                    <span className="text-slate-400">Execution Time</span>
                    <span className="font-mono text-green-400">{logicResult.latency}ms</span>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Response */}
            {responseResult && (
              <Card className="bg-slate-900/50 border-slate-700">
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <span className="text-2xl">💬</span>
                    <span>AI Response</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                    <p className="text-sm text-slate-300">{responseResult.text}</p>
                  </div>

                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div className="flex flex-col space-y-1">
                      <span className="text-slate-400">Text Generation</span>
                      <span className="font-mono text-green-400">{responseResult.latency}ms</span>
                    </div>
                    {responseAudioResult && (
                      <div className="flex flex-col space-y-1">
                        <span className="text-slate-400">TTS</span>
                        <span className="font-mono text-green-400">{responseAudioResult.latency}ms</span>
                      </div>
                    )}
                  </div>

                  {responseAudioResult && (
                    <div className="bg-blue-900/20 rounded-lg p-3 border border-blue-500/30 flex items-center justify-center space-x-2">
                      <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
                      <span className="text-xs text-blue-400">Playing response...</span>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>

          {/* Right Column - Performance Metrics */}
          <div className="space-y-6">
            {/* Overall Metrics */}
            {metricsResult && (
              <Card className="bg-slate-900/50 border-slate-700">
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <span className="text-2xl">⚡</span>
                    <span>Performance Metrics</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* TTRS */}
                  <div className={`rounded-lg p-4 border-2 ${
                    metricsResult.ttrs_met
                      ? "bg-green-900/20 border-green-500/50"
                      : "bg-yellow-900/20 border-yellow-500/50"
                  }`}>
                    <div className="text-xs text-slate-400 mb-1">Time-To-Respond-Start</div>
                    <div className={`text-3xl font-bold ${
                      metricsResult.ttrs_met ? "text-green-400" : "text-yellow-400"
                    }`}>
                      {metricsResult.ttrs}ms
                    </div>
                    <div className="flex items-center justify-between mt-2">
                      <span className="text-xs text-slate-500">Target: {metricsResult.ttrs_target}ms</span>
                      <Badge variant={metricsResult.ttrs_met ? "default" : "secondary"}>
                        {metricsResult.ttrs_met ? "✅ Met" : "⏱️ Over"}
                      </Badge>
                    </div>
                  </div>

                  <Separator className="bg-slate-700" />

                  {/* Phase Breakdown */}
                  <div className="space-y-3">
                    <div className="text-sm font-semibold text-slate-300">Phase Breakdown</div>

                    {[
                      { label: "STT", value: metricsResult.stt_latency, color: "text-blue-400" },
                      { label: "Emotion", value: metricsResult.emotion_latency, color: "text-purple-400" },
                      { label: "Filler", value: metricsResult.filler_latency, color: "text-pink-400" },
                      { label: "Logic", value: metricsResult.logic_latency, color: "text-yellow-400" },
                      { label: "Response", value: metricsResult.response_latency, color: "text-orange-400" },
                      { label: "TTS", value: metricsResult.tts_latency, color: "text-indigo-400" },
                    ].map((phase) => (
                      <div key={phase.label} className="flex items-center justify-between">
                        <span className="text-sm text-slate-400">{phase.label}</span>
                        <span className={`text-sm font-mono ${phase.color}`}>
                          {typeof phase.value === 'number' ? phase.value.toFixed(2) : phase.value}ms
                        </span>
                      </div>
                    ))}

                    <Separator className="bg-slate-700" />

                    <div className="flex items-center justify-between pt-2">
                      <span className="text-sm font-semibold text-slate-300">Total Pipeline</span>
                      <span className="text-lg font-bold text-cyan-400">
                        {metricsResult.total_latency}ms
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Optimization Info */}
            <Card className="bg-gradient-to-br from-blue-900/30 to-purple-900/30 border-blue-500/50">
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <span className="text-2xl">📊</span>
                  <span>Optimizations</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-2">
                  <div className="flex items-start space-x-2">
                    <div className="w-2 h-2 bg-green-500 rounded-full mt-1.5" />
                    <div className="flex-1">
                      <div className="text-sm font-semibold text-slate-200">Flux STT Streaming</div>
                      <div className="text-xs text-slate-400">300-400ms vs 1275ms baseline (68-75% faster)</div>
                    </div>
                  </div>

                  <div className="flex items-start space-x-2">
                    <div className="w-2 h-2 bg-green-500 rounded-full mt-1.5" />
                    <div className="flex-1">
                      <div className="text-sm font-semibold text-slate-200">Eager End-of-Turn</div>
                      <div className="text-xs text-slate-400">Speculative logic execution at medium-confidence pauses</div>
                    </div>
                  </div>

                  <div className="flex items-start space-x-2">
                    <div className="w-2 h-2 bg-green-500 rounded-full mt-1.5" />
                    <div className="flex-1">
                      <div className="text-sm font-semibold text-slate-200">Parallel Emotion Detection</div>
                      <div className="text-xs text-slate-400">Fast keyword + accurate LLM running concurrently</div>
                    </div>
                  </div>

                  <div className="flex items-start space-x-2">
                    <div className="w-2 h-2 bg-green-500 rounded-full mt-1.5" />
                    <div className="flex-1">
                      <div className="text-sm font-semibold text-slate-200">Interim Transcripts</div>
                      <div className="text-xs text-slate-400">Real-time streaming feedback during transcription</div>
                    </div>
                  </div>

                  <div className="flex items-start space-x-2">
                    <div className="w-2 h-2 bg-green-500 rounded-full mt-1.5" />
                    <div className="flex-1">
                      <div className="text-sm font-semibold text-slate-200">Graceful Degradation</div>
                      <div className="text-xs text-slate-400">Auto-fallback to Nova-3 with exponential backoff</div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
