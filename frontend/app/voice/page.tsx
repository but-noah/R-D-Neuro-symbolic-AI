"use client";

import { useState, useRef, useEffect } from "react";

// Event types from backend
interface STTEvent {
  transcript: string;
  is_final: boolean;
}

interface EmotionEvent {
  anger: number;
  category: string;
  latency: number;
  method: string;
}

interface FillerEvent {
  category: string;
  audio_b64: string;
  size_kb: number;
  latency: number;
}

interface LogicEvent {
  decision: {
    allowed: boolean;
    amount: number;
    reason: string;
  };
  order_details: any;
  latency: number;
}

interface ResponseTextEvent {
  text: string;
  latency: number;
}

interface ResponseAudioEvent {
  audio_b64: string;
  size_kb: number;
  latency: number;
}

interface MetricsEvent {
  ttrs: number;
  total_latency: number;
  ttrs_met: boolean;
}

export default function VoicePage() {
  // Connection state
  const [connected, setConnected] = useState(false);
  const [recording, setRecording] = useState(false);
  const [processing, setProcessing] = useState(false);

  // WebSocket and Media
  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioQueueRef = useRef<HTMLAudioElement[]>([]);
  const isPlayingRef = useRef(false);

  // Pipeline state
  const [transcript, setTranscript] = useState("");
  const [finalTranscript, setFinalTranscript] = useState("");
  const [emotionFast, setEmotionFast] = useState<EmotionEvent | null>(null);
  const [emotionLLM, setEmotionLLM] = useState<EmotionEvent | null>(null);
  const [filler, setFiller] = useState<FillerEvent | null>(null);
  const [logic, setLogic] = useState<LogicEvent | null>(null);
  const [responseText, setResponseText] = useState<ResponseTextEvent | null>(null);
  const [responseAudio, setResponseAudio] = useState<ResponseAudioEvent | null>(null);
  const [metrics, setMetrics] = useState<MetricsEvent | null>(null);
  const [ttrsUpdate, setTTRSUpdate] = useState<{ ttrs: number; ttrs_met: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Audio playback queue
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

  // Connect to WebSocket
  const handleConnect = async () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log("Already connected");
      return;
    }

    const ws = new WebSocket("ws://127.0.0.1:8000/api/v1/ws/voice");

    ws.onopen = () => {
      console.log("✅ Connected to voice pipeline");
      setConnected(true);
      setError(null);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log("Received:", data.type, data);

      switch (data.type) {
        case "ready":
          console.log("✅ Pipeline ready");
          break;

        case "stt":
          if (data.is_final) {
            setFinalTranscript(data.transcript);
            setTranscript(data.transcript);
          } else {
            setTranscript(data.transcript);
          }
          break;

        case "emotion_fast":
          setEmotionFast(data);
          break;

        case "emotion_llm":
          setEmotionLLM(data);
          break;

        case "filler":
          setFiller(data);
          // Add filler audio to playback queue
          addToAudioQueue(data.audio_b64);
          break;

        case "ttrs_update":
          setTTRSUpdate({
            ttrs: data.ttrs,
            ttrs_met: data.ttrs_met,
          });
          break;

        case "logic":
          setLogic(data);
          break;

        case "response_text":
          setResponseText(data);
          break;

        case "response_audio":
          setResponseAudio(data);
          // Add response audio to playback queue
          addToAudioQueue(data.audio_b64);
          setProcessing(false);
          break;

        case "metrics":
          setMetrics(data);
          break;

        case "error":
          setError(data.message);
          setProcessing(false);
          break;
      }
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
      setError("WebSocket connection error");
      setConnected(false);
    };

    ws.onclose = () => {
      console.log("🔌 Disconnected from voice pipeline");
      setConnected(false);
    };

    wsRef.current = ws;
  };

  // Start recording
  const handleStartRecording = async () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setError("Not connected to server");
      return;
    }

    try {
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });

      // Create audio context for processing
      const audioContext = new AudioContext({ sampleRate: 16000 });
      audioContextRef.current = audioContext;

      // Create MediaRecorder
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: "audio/webm",
      });

      mediaRecorder.ondataavailable = async (event) => {
        if (event.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
          // Convert to raw PCM for Deepgram
          const arrayBuffer = await event.data.arrayBuffer();
          const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

          // Get raw PCM data (linear16)
          const pcmData = audioBuffer.getChannelData(0);
          const int16Data = new Int16Array(pcmData.length);
          for (let i = 0; i < pcmData.length; i++) {
            int16Data[i] = Math.max(-32768, Math.min(32767, pcmData[i] * 32768));
          }

          // Send binary audio data to backend
          wsRef.current.send(int16Data.buffer);
        }
      };

      mediaRecorder.start(250); // Send chunks every 250ms
      mediaRecorderRef.current = mediaRecorder;

      setRecording(true);
      setProcessing(false);
      setError(null);

      // Reset state
      setTranscript("");
      setFinalTranscript("");
      setEmotionFast(null);
      setEmotionLLM(null);
      setFiller(null);
      setLogic(null);
      setResponseText(null);
      setResponseAudio(null);
      setMetrics(null);
      setTTRSUpdate(null);

      console.log("🎤 Recording started");
    } catch (err) {
      console.error("Error starting recording:", err);
      setError("Failed to access microphone");
    }
  };

  // Stop recording
  const handleStopRecording = () => {
    if (mediaRecorderRef.current && recording) {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop());
      mediaRecorderRef.current = null;

      setRecording(false);
      setProcessing(true);

      // Notify backend
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "stop" }));
      }

      console.log("🛑 Recording stopped");
    }
  };

  // Disconnect
  const handleDisconnect = () => {
    if (recording) {
      handleStopRecording();
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    setConnected(false);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      handleDisconnect();
    };
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 text-white p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold mb-2 bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
            🎙️ Real-Time Voice Agent
          </h1>
          <p className="text-gray-400">
            Live voice interaction with Deepgram STT + Cartesia TTS
          </p>
        </div>

        {/* Controls */}
        <div className="bg-gray-800 rounded-lg p-6 mb-6 border border-gray-700">
          <div className="flex items-center justify-between">
            {/* Connection Status */}
            <div className="flex items-center space-x-4">
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

              {recording && (
                <div className="flex items-center space-x-2">
                  <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse" />
                  <span className="text-sm text-red-400">Recording</span>
                </div>
              )}

              {processing && (
                <div className="flex items-center space-x-2">
                  <div className="w-3 h-3 bg-yellow-500 rounded-full animate-pulse" />
                  <span className="text-sm text-yellow-400">Processing</span>
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div className="flex space-x-2">
              {!connected ? (
                <button
                  onClick={handleConnect}
                  className="bg-blue-600 hover:bg-blue-700 px-6 py-3 rounded-lg font-medium transition-colors"
                >
                  Connect
                </button>
              ) : (
                <>
                  {!recording ? (
                    <button
                      onClick={handleStartRecording}
                      disabled={processing}
                      className={`px-6 py-3 rounded-lg font-medium transition-colors ${
                        processing
                          ? "bg-gray-600 cursor-not-allowed"
                          : "bg-green-600 hover:bg-green-700"
                      }`}
                    >
                      🎤 Start Recording
                    </button>
                  ) : (
                    <button
                      onClick={handleStopRecording}
                      className="bg-red-600 hover:bg-red-700 px-6 py-3 rounded-lg font-medium transition-colors"
                    >
                      ⏹️ Stop Recording
                    </button>
                  )}
                  <button
                    onClick={handleDisconnect}
                    className="bg-gray-600 hover:bg-gray-700 px-6 py-3 rounded-lg font-medium transition-colors"
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
          <div className="mb-6 bg-red-900/50 border border-red-500 rounded-lg p-4">
            <p className="text-red-200">❌ Error: {error}</p>
          </div>
        )}

        {/* Live Transcript */}
        {(transcript || finalTranscript) && (
          <div className="mb-6 bg-gradient-to-r from-purple-900/50 to-blue-900/50 border-2 border-purple-500 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-3 flex items-center">
              <span className="text-2xl mr-2">💬</span>
              Live Transcript
            </h2>
            <div className="bg-gray-900 rounded-lg p-4">
              <p className="text-gray-300 text-lg">
                {finalTranscript && (
                  <span className="text-white font-medium">{finalTranscript}</span>
                )}
                {!finalTranscript && transcript && (
                  <span className="text-gray-400 italic">{transcript}</span>
                )}
              </p>
            </div>
          </div>
        )}

        {/* TTRS Update */}
        {ttrsUpdate && !metrics && (
          <div className="mb-6 bg-gradient-to-r from-blue-900/50 to-purple-900/50 border-2 border-blue-500 rounded-lg p-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <div className="animate-pulse">
                  <div className="w-3 h-3 bg-green-500 rounded-full"></div>
                </div>
                <span className="text-xl font-semibold">
                  Time-To-Respond-Start (TTRS)
                </span>
              </div>
              <div className="flex items-center space-x-3">
                <span
                  className={`text-4xl font-bold ${
                    ttrsUpdate.ttrs_met ? "text-green-400" : "text-yellow-400"
                  }`}
                >
                  {ttrsUpdate.ttrs}ms
                </span>
                <span className="text-gray-400">
                  {ttrsUpdate.ttrs_met ? "✅ Target Met!" : "⏱️ Processing..."}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Results Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Emotion Detection */}
          {emotionFast && (
            <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <h2 className="text-xl font-semibold mb-4 flex items-center">
                <span className="text-2xl mr-2">😊</span>
                Emotion Detection
              </h2>

              {/* Fast Emotion */}
              <div className="bg-gradient-to-r from-blue-900/30 to-purple-900/30 rounded-lg p-4 mb-3 border border-blue-500/30">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-blue-300 uppercase">
                    ⚡ Fast (Keyword)
                  </span>
                  <span className="text-xs text-gray-400">For TTRS</span>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-400">Category:</span>
                    <span
                      className={`text-sm font-semibold ${
                        emotionFast.category === "angry_high"
                          ? "text-red-400"
                          : emotionFast.category === "angry_medium"
                          ? "text-orange-400"
                          : "text-green-400"
                      }`}
                    >
                      {emotionFast.category.replace("_", " ").toUpperCase()}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-400">Anger:</span>
                    <span className="text-sm text-yellow-400 font-mono">
                      {emotionFast.anger.toFixed(2)}
                    </span>
                  </div>
                </div>
              </div>

              {/* LLM Emotion */}
              {emotionLLM ? (
                <div className="bg-gradient-to-r from-purple-900/30 to-pink-900/30 rounded-lg p-4 border border-purple-500/30">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold text-purple-300 uppercase">
                      🎯 Accurate (LLM)
                    </span>
                    <span className="text-xs text-gray-400">For Response</span>
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span className="text-sm text-gray-400">Category:</span>
                      <span
                        className={`text-sm font-semibold ${
                          emotionLLM.category === "angry_high"
                            ? "text-red-400"
                            : emotionLLM.category === "angry_medium"
                            ? "text-orange-400"
                            : "text-green-400"
                        }`}
                      >
                        {emotionLLM.category.replace("_", " ").toUpperCase()}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-gray-400">Anger:</span>
                      <span className="text-sm text-yellow-400 font-mono">
                        {emotionLLM.anger.toFixed(2)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-gray-400">Latency:</span>
                      <span className="text-sm text-orange-400 font-mono">
                        {emotionLLM.latency}ms
                      </span>
                    </div>
                  </div>
                </div>
              ) : emotionFast ? (
                <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                  <div className="flex items-center justify-center text-gray-500 text-sm">
                    <span className="animate-pulse">⏳ LLM emotion processing...</span>
                  </div>
                </div>
              ) : null}
            </div>
          )}

          {/* Filler Audio */}
          {filler && (
            <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <h2 className="text-xl font-semibold mb-4 flex items-center">
                <span className="text-2xl mr-2">🎵</span>
                Filler Audio
              </h2>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-400">Category:</span>
                  <span className="font-semibold text-purple-400">
                    {filler.category}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Size:</span>
                  <span className="font-mono text-gray-300">
                    {filler.size_kb.toFixed(1)} KB
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Latency:</span>
                  <span className="font-mono text-green-400">
                    {filler.latency.toFixed(2)}ms
                  </span>
                </div>
                <div className="mt-4 flex items-center justify-center">
                  <div className="text-green-400 flex items-center space-x-2">
                    <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                    <span className="text-sm">Playing filler...</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Logic Result */}
          {logic && (
            <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <h2 className="text-xl font-semibold mb-4 flex items-center">
                <span className="text-2xl mr-2">🧠</span>
                Logic Decision
              </h2>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-gray-400">Status:</span>
                  <span
                    className={`font-semibold ${
                      logic.decision.allowed ? "text-green-400" : "text-red-400"
                    }`}
                  >
                    {logic.decision.allowed ? "✅ APPROVED" : "❌ DENIED"}
                  </span>
                </div>
                {logic.decision.allowed && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">Amount:</span>
                    <span className="font-bold text-green-400">
                      ${logic.decision.amount.toFixed(2)}
                    </span>
                  </div>
                )}
                <div className="bg-gray-900 rounded-lg p-3 mt-2">
                  <p className="text-sm text-gray-300">{logic.decision.reason}</p>
                </div>
              </div>
            </div>
          )}

          {/* Response */}
          {responseText && (
            <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <h2 className="text-xl font-semibold mb-4 flex items-center">
                <span className="text-2xl mr-2">💬</span>
                Agent Response
              </h2>
              <div className="space-y-3">
                <div className="bg-gray-900 rounded-lg p-4">
                  <p className="text-gray-300">{responseText.text}</p>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Generation:</span>
                  <span className="font-mono text-green-400">
                    {responseText.latency}ms
                  </span>
                </div>
                {responseAudio && (
                  <>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-400">TTS:</span>
                      <span className="font-mono text-green-400">
                        {responseAudio.latency}ms
                      </span>
                    </div>
                    <div className="mt-4 flex items-center justify-center">
                      <div className="text-blue-400 flex items-center space-x-2">
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                        <span className="text-sm">Playing response...</span>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Final Metrics */}
        {metrics && (
          <div className="mt-6 bg-gradient-to-r from-green-900/50 to-blue-900/50 border-2 border-green-500 rounded-lg p-6">
            <h2 className="text-2xl font-semibold mb-4 flex items-center">
              <span className="text-2xl mr-2">⏱️</span>
              Performance Metrics
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-gray-900/50 rounded-lg p-4">
                <div className="text-sm text-gray-400 mb-1">TTRS</div>
                <div
                  className={`text-2xl font-bold ${
                    metrics.ttrs_met ? "text-green-400" : "text-yellow-400"
                  }`}
                >
                  {metrics.ttrs}ms
                </div>
                <div className="text-xs text-gray-500">
                  Target: {metrics.ttrs_met ? "✅" : "❌"} &lt;840ms
                </div>
              </div>
              <div className="bg-gray-900/50 rounded-lg p-4">
                <div className="text-sm text-gray-400 mb-1">Total</div>
                <div className="text-2xl font-bold text-blue-400">
                  {metrics.total_latency}ms
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
