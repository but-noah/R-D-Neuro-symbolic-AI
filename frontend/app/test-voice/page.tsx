"use client";

import { useState, useRef, useEffect } from "react";

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

interface STTResult {
  transcript: string;
  latency: number;
  method: string;
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
  order_details: {
    order_id: string;
    customer_name: string;
    product_name: string;
    product_category: string;
    price: number;
    order_date: string;
    delivery_date: string | null;
    actual_condition: string;
    defect_description: string | null;
    within_return_window: boolean;
  } | null;
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

export default function TestVoicePage() {
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
  const [ttsStreaming, setTTSStreaming] = useState(false);
  const [ttsChunkCount, setTTSChunkCount] = useState(0);
  const [ttsTTFB, setTTSTTFB] = useState<number | null>(null);

  // Test configuration
  const [selectedAudio, setSelectedAudio] = useState(TEST_AUDIO_FILES[0].value);

  // Pipeline results
  const [sttResult, setSTTResult] = useState<STTResult | null>(null);
  const [emotionResult, setEmotionResult] = useState<EmotionResult | null>(null);
  const [emotionLLMResult, setEmotionLLMResult] = useState<EmotionResult | null>(null);
  const [fillerResult, setFillerResult] = useState<FillerResult | null>(null);
  const [logicResult, setLogicResult] = useState<LogicResult | null>(null);
  const [responseResult, setResponseResult] = useState<ResponseResult | null>(null);
  const [responseAudioResult, setResponseAudioResult] = useState<ResponseAudioResult | null>(null);
  const [metricsResult, setMetricsResult] = useState<MetricsResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ttrsUpdate, setTTRSUpdate] = useState<{ttrs: number; ttrs_met: boolean} | null>(null);

  // Audio playback queue management
  const playAudioQueue = async () => {
    if (isPlayingRef.current || audioQueueRef.current.length === 0) {
      return;
    }

    isPlayingRef.current = true;

    while (audioQueueRef.current.length > 0) {
      const audio = audioQueueRef.current.shift()!;

      // Play audio and wait for it to finish
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
      // Convert base64 to blob
      const binaryString = atob(audioB64);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      const blob = new Blob([bytes], { type: "audio/mp3" });
      const url = URL.createObjectURL(blob);

      // Create audio element
      const audio = new Audio(url);
      audioQueueRef.current.push(audio);

      // Start playing queue
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

      // Decode base64 to ArrayBuffer
      const binaryString = atob(audioB64);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Convert PCM int16 to float32
      const pcmData = new Int16Array(bytes.buffer);
      const audioBuffer = audioContextRef.current!.createBuffer(
        1, // mono
        pcmData.length,
        sampleRate
      );

      const channelData = audioBuffer.getChannelData(0);
      for (let i = 0; i < pcmData.length; i++) {
        channelData[i] = pcmData[i] / 32768.0; // Convert int16 to float32
      }

      // Add to buffer queue
      pcmBuffersRef.current.push(audioBuffer);

      // Start playing if not already
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
      console.log("✅ Connected to test voice pipeline");
      setConnected(true);
      setError(null);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log("Received:", data.type, data);

      switch (data.type) {
        case "stt":
          setSTTResult({
            transcript: data.transcript,
            latency: data.latency,
            method: data.method,
          });
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
          break;

        case "filler":
          setFillerResult({
            category: data.category,
            audio_b64: data.audio_b64,
            size_kb: data.size_kb,
            latency: data.latency,
          });
          // Add filler audio to queue
          addToAudioQueue(data.audio_b64);
          break;

        case "logic":
          setLogicResult({
            decision: data.decision,
            order_details: data.order_details,
            latency: data.latency,
          });
          break;

        case "response_text":
          setResponseResult({
            text: data.text,
            latency: data.latency,
            method: data.method,
          });
          break;

        case "response_audio":
          setResponseAudioResult({
            audio_b64: data.audio_b64,
            size_kb: data.size_kb,
            latency: data.latency,
          });
          // Add response audio to queue
          addToAudioQueue(data.audio_b64);
          break;

        case "tts_chunk":
          // Handle streaming PCM audio chunk
          if (data.chunk_number === 1) {
            setTTSStreaming(true);
            setTTSTTFB(null);
            console.log("🎵 TTS streaming started...");
          }
          setTTSChunkCount(data.chunk_number);
          handlePCMChunk(data.audio_b64, data.sample_rate);
          break;

        case "tts_complete":
          // TTS streaming complete
          setTTSStreaming(false);
          setTTSTTFB(data.ttfb);
          setResponseAudioResult({
            audio_b64: "", // Not applicable for streaming
            size_kb: data.total_bytes / 1024,
            latency: data.total_latency,
          });
          console.log(`✅ TTS streaming complete: ${data.chunk_count} chunks, TTFB: ${data.ttfb}ms, Total: ${data.total_latency}ms`);
          break;

        case "tts_error":
          setTTSStreaming(false);
          console.error("❌ TTS error:", data.error);
          setError(`TTS error: ${data.error}`);
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
      console.log("🔌 Disconnected from test voice pipeline");
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

    // Reset results
    setSTTResult(null);
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

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 text-white p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold mb-2 bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
            🧪 Voice Pipeline Test Lab
          </h1>
          <p className="text-gray-400">
            Test the complete voice pipeline with realistic scenarios
          </p>
        </div>

        {/* Controls */}
        <div className="bg-gray-800 rounded-lg p-6 mb-6 border border-gray-700">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Audio Selection */}
            <div>
              <label className="block text-sm font-medium mb-2 text-gray-300">
                Test Scenario
              </label>
              <select
                value={selectedAudio}
                onChange={(e) => setSelectedAudio(e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                disabled={testing}
              >
                {TEST_AUDIO_FILES.map((file) => (
                  <option key={file.value} value={file.value}>
                    {file.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Connection Status */}
            <div>
              <label className="block text-sm font-medium mb-2 text-gray-300">
                Connection
              </label>
              <div className="flex items-center space-x-2">
                <div
                  className={`w-3 h-3 rounded-full ${
                    connected ? "bg-green-500" : "bg-red-500"
                  }`}
                />
                <span className="text-sm">
                  {connected ? "Connected" : "Disconnected"}
                </span>
              </div>
            </div>

            {/* Actions */}
            <div>
              <label className="block text-sm font-medium mb-2 text-gray-300">
                Actions
              </label>
              <div className="flex space-x-2">
                {!connected ? (
                  <button
                    onClick={handleConnect}
                    className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg font-medium transition-colors"
                  >
                    Connect
                  </button>
                ) : (
                  <>
                    <button
                      onClick={handleTest}
                      disabled={testing}
                      className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                        testing
                          ? "bg-gray-600 cursor-not-allowed"
                          : "bg-green-600 hover:bg-green-700"
                      }`}
                    >
                      {testing ? "Testing..." : "Run Test"}
                    </button>
                    <button
                      onClick={handleDisconnect}
                      className="bg-red-600 hover:bg-red-700 px-4 py-2 rounded-lg font-medium transition-colors"
                    >
                      Disconnect
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Error Display */}
          {error && (
            <div className="mt-4 bg-red-900/50 border border-red-500 rounded-lg p-4">
              <p className="text-red-200">❌ Error: {error}</p>
            </div>
          )}

          {/* TTRS Live Update */}
          {ttrsUpdate && !metricsResult && (
            <div className="mt-4 bg-gradient-to-r from-blue-900/50 to-purple-900/50 border-2 border-blue-500 rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="animate-pulse">
                    <div className="w-3 h-3 bg-green-500 rounded-full"></div>
                  </div>
                  <span className="text-lg font-semibold">Time-To-Respond-Start (TTRS)</span>
                </div>
                <div className="flex items-center space-x-3">
                  <span className={`text-3xl font-bold ${
                    ttrsUpdate.ttrs_met ? "text-green-400" : "text-yellow-400"
                  }`}>
                    {ttrsUpdate.ttrs}ms
                  </span>
                  <span className="text-gray-400">
                    {ttrsUpdate.ttrs_met ? "✅ Target Met!" : "⏱️ Processing..."}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Results Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Phase 1: STT */}
          {sttResult && (
            <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <h2 className="text-xl font-semibold mb-4 flex items-center">
                <span className="text-2xl mr-2">🎤</span>
                Phase 1: Speech-to-Text
              </h2>
              <div className="space-y-3">
                <div className="bg-gray-900 rounded-lg p-4">
                  <p className="text-gray-300 italic">"{sttResult.transcript}"</p>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Latency:</span>
                  <span className="font-mono text-green-400">{sttResult.latency}ms</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Method:</span>
                  <span className="text-gray-300">{sttResult.method}</span>
                </div>
              </div>
            </div>
          )}

          {/* Phase 2: Emotion */}
          {emotionResult && (
            <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <h2 className="text-xl font-semibold mb-4 flex items-center">
                <span className="text-2xl mr-2">😡</span>
                Phase 2: Emotion Detection
              </h2>

              {/* Fast Emotion (Keyword) */}
              <div className="bg-gradient-to-r from-blue-900/30 to-purple-900/30 rounded-lg p-4 mb-4 border border-blue-500/30">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-blue-300 uppercase">⚡ Fast (Keyword)</span>
                  <span className="text-xs text-gray-400">For TTRS</span>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-gray-400 text-sm">Category:</span>
                    <span className={`font-semibold text-sm ${
                      emotionResult.category === "angry_high"
                        ? "text-red-400"
                        : emotionResult.category === "angry_medium"
                        ? "text-orange-400"
                        : "text-green-400"
                    }`}>
                      {emotionResult.category.replace("_", " ").toUpperCase()}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400 text-sm">Anger:</span>
                    <span className="font-mono text-yellow-400 text-sm">
                      {emotionResult.anger.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400 text-sm">Latency:</span>
                    <span className="font-mono text-green-400 text-sm">{emotionResult.latency}ms</span>
                  </div>
                </div>
              </div>

              {/* LLM Emotion (Accurate) */}
              {emotionLLMResult ? (
                <div className="bg-gradient-to-r from-purple-900/30 to-pink-900/30 rounded-lg p-4 border border-purple-500/30">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold text-purple-300 uppercase">🎯 Accurate (LLM)</span>
                    <span className="text-xs text-gray-400">For Response</span>
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span className="text-gray-400 text-sm">Category:</span>
                      <span className={`font-semibold text-sm ${
                        emotionLLMResult.category === "angry_high"
                          ? "text-red-400"
                          : emotionLLMResult.category === "angry_medium"
                          ? "text-orange-400"
                          : "text-green-400"
                      }`}>
                        {emotionLLMResult.category.replace("_", " ").toUpperCase()}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400 text-sm">Anger:</span>
                      <span className="font-mono text-yellow-400 text-sm">
                        {emotionLLMResult.anger.toFixed(2)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400 text-sm">Latency:</span>
                      <span className="font-mono text-orange-400 text-sm">{emotionLLMResult.latency}ms</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                  <div className="flex items-center justify-center text-gray-500 text-sm">
                    <span className="animate-pulse">⏳ LLM emotion processing...</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Phase 3: Filler */}
          {fillerResult && (
            <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <h2 className="text-xl font-semibold mb-4 flex items-center">
                <span className="text-2xl mr-2">🎵</span>
                Phase 3: Filler Selection
              </h2>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-400">Category:</span>
                  <span className="font-semibold text-purple-400">
                    {fillerResult.category}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Audio Size:</span>
                  <span className="font-mono text-gray-300">
                    {fillerResult.size_kb.toFixed(1)} KB
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Latency:</span>
                  <span className="font-mono text-green-400">
                    {fillerResult.latency.toFixed(2)}ms
                  </span>
                </div>
                <div className="mt-4 flex items-center justify-center">
                  <div className="text-blue-400 flex items-center space-x-2">
                    <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                    <span className="text-sm">Playing filler audio...</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Phase 4: Logic */}
          {logicResult && (
            <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <h2 className="text-xl font-semibold mb-4 flex items-center">
                <span className="text-2xl mr-2">🧠</span>
                Phase 4: Logic Execution
              </h2>
              <div className="space-y-4">
                {/* Decision */}
                <div className="bg-gray-900 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold">Decision:</span>
                    <span className={`px-3 py-1 rounded-full text-sm font-semibold ${
                      logicResult.decision.allowed
                        ? "bg-green-900/50 text-green-300"
                        : "bg-red-900/50 text-red-300"
                    }`}>
                      {logicResult.decision.allowed ? "✅ APPROVED" : "❌ DENIED"}
                    </span>
                  </div>
                  {logicResult.decision.allowed && (
                    <div className="text-2xl font-bold text-green-400 mb-2">
                      ${logicResult.decision.amount.toFixed(2)}
                    </div>
                  )}
                  <p className="text-sm text-gray-400">{logicResult.decision.reason}</p>
                </div>

                {/* Order Details */}
                {logicResult.order_details && (
                  <div className="bg-gray-900 rounded-lg p-4">
                    <h3 className="font-semibold mb-2">Order Details:</h3>
                    <div className="space-y-1 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-400">Order ID:</span>
                        <span className="font-mono">{logicResult.order_details.order_id}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Product:</span>
                        <span>{logicResult.order_details.product_name}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Price:</span>
                        <span className="font-mono">${logicResult.order_details.price.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Condition:</span>
                        <span>{logicResult.order_details.actual_condition}</span>
                      </div>
                    </div>
                  </div>
                )}

                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Latency:</span>
                  <span className="font-mono text-green-400">{logicResult.latency}ms</span>
                </div>
              </div>
            </div>
          )}

          {/* Phase 5: Response */}
          {responseResult && (
            <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 lg:col-span-2">
              <h2 className="text-xl font-semibold mb-4 flex items-center">
                <span className="text-2xl mr-2">💬</span>
                Phase 5: Generated Response
              </h2>
              <div className="space-y-3">
                <div className="bg-gray-900 rounded-lg p-4">
                  <p className="text-gray-300">{responseResult.text}</p>
                </div>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-400">Text Generation:</span>
                    <span className="font-mono text-green-400 ml-2">{responseResult.latency}ms</span>
                  </div>
                  {responseAudioResult && (
                    <div>
                      <span className="text-gray-400">TTS:</span>
                      <span className="font-mono text-green-400 ml-2">{responseAudioResult.latency}ms</span>
                    </div>
                  )}
                  <div>
                    <span className="text-gray-400">Method:</span>
                    <span className="text-gray-300 ml-2">{responseResult.method}</span>
                  </div>
                  {responseAudioResult && (
                    <div>
                      <span className="text-gray-400">Audio Size:</span>
                      <span className="text-gray-300 ml-2">{responseAudioResult.size_kb.toFixed(1)} KB</span>
                    </div>
                  )}
                </div>
                {responseAudioResult && (
                  <div className="mt-4 flex items-center justify-center">
                    <div className="text-blue-400 flex items-center space-x-2">
                      <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                      <span className="text-sm">Playing response audio...</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Metrics */}
          {metricsResult && (
            <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 lg:col-span-2">
              <h2 className="text-xl font-semibold mb-4 flex items-center">
                <span className="text-2xl mr-2">⏱️</span>
                Performance Metrics
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {/* TTRS */}
                <div className="bg-gray-900 rounded-lg p-4">
                  <div className="text-xs text-gray-400 mb-1">Time-to-Respond-Start</div>
                  <div className={`text-2xl font-bold ${
                    metricsResult.ttrs_met ? "text-green-400" : "text-red-400"
                  }`}>
                    {metricsResult.ttrs}ms
                  </div>
                  <div className="text-xs text-gray-500">
                    Target: {metricsResult.ttrs_target}ms {metricsResult.ttrs_met ? "✅" : "❌"}
                  </div>
                </div>

                {/* STT */}
                <div className="bg-gray-900 rounded-lg p-4">
                  <div className="text-xs text-gray-400 mb-1">STT Latency</div>
                  <div className="text-2xl font-bold text-blue-400">
                    {metricsResult.stt_latency}ms
                  </div>
                </div>

                {/* Emotion */}
                <div className="bg-gray-900 rounded-lg p-4">
                  <div className="text-xs text-gray-400 mb-1">Emotion Detection</div>
                  <div className="text-2xl font-bold text-purple-400">
                    {metricsResult.emotion_latency}ms
                  </div>
                </div>

                {/* Filler */}
                <div className="bg-gray-900 rounded-lg p-4">
                  <div className="text-xs text-gray-400 mb-1">Filler Retrieval</div>
                  <div className="text-2xl font-bold text-pink-400">
                    {metricsResult.filler_latency.toFixed(2)}ms
                  </div>
                </div>

                {/* Logic */}
                <div className="bg-gray-900 rounded-lg p-4">
                  <div className="text-xs text-gray-400 mb-1">Logic Execution</div>
                  <div className="text-2xl font-bold text-yellow-400">
                    {metricsResult.logic_latency}ms
                  </div>
                </div>

                {/* Response */}
                <div className="bg-gray-900 rounded-lg p-4">
                  <div className="text-xs text-gray-400 mb-1">Response Generation</div>
                  <div className="text-2xl font-bold text-orange-400">
                    {metricsResult.response_latency}ms
                  </div>
                </div>

                {/* TTS */}
                <div className="bg-gray-900 rounded-lg p-4">
                  <div className="text-xs text-gray-400 mb-1">Text-to-Speech</div>
                  <div className="text-2xl font-bold text-indigo-400">
                    {metricsResult.tts_latency}ms
                  </div>
                </div>

                {/* Total */}
                <div className="bg-gray-900 rounded-lg p-4 md:col-span-2">
                  <div className="text-xs text-gray-400 mb-1">Total Pipeline</div>
                  <div className="text-2xl font-bold text-cyan-400">
                    {metricsResult.total_latency}ms
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
