"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";

const MODEL_URL = "https://pp7lqaiyjk9iw0-8000.proxy.runpod.net/v1";
const MODEL_API_KEY = "23sdU7e83dcx90ysR6t";

export default function SessionDashboard() {
  const router = useRouter();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);

  // Updated states for live rewrites
  const [finalizedTranscript, setFinalizedTranscript] = useState<string>("");
  const [activeTranscript, setActiveTranscript] = useState<string>("");
  
  // Audio state refs
  const audioCtxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const audioBufferRef = useRef<Float32Array[]>([]);
  const chunkIndexRef = useRef(0);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  // User state (Mocked for demo)
  const [user] = useState<any>({ id: "123", email: "demo.user@example.com" }); 

  // Native encoder 16kHz Mono
  const exportWAV = (buffers: Float32Array[], sampleRate: number) => {
    const totalLength = buffers.reduce((acc, b) => acc + b.length, 0);
    const result = new Float32Array(totalLength);
    let offset = 0;
    for (const b of buffers) {
      result.set(b, offset);
      offset += b.length;
    }

    const buffer = new ArrayBuffer(44 + result.length * 2);
    const view = new DataView(buffer);
    const writeString = (view: DataView, offset: number, string: string) => {
      for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
      }
    };

    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + result.length * 2, true);
    writeString(view, 8, 'WAVE');
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); 
    view.setUint16(22, 1, true); 
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(view, 36, 'data');
    view.setUint32(40, result.length * 2, true);

    let dataOffset = 44;
    for (let i = 0; i < result.length; i++, dataOffset += 2) {
      const s = Math.max(-1, Math.min(1, result[i]));
      view.setInt16(dataOffset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    return new Blob([view], { type: 'audio/wav' });
  };

  // updated send logic for rewrites
  const processAndSendChunk = async (currentSessionId: string, buffersToProcess: Float32Array[]) => {
    if (buffersToProcess.length === 0) return;
    
    const wavBlob = exportWAV(buffersToProcess, 16000);
    const reader = new FileReader();
    reader.readAsDataURL(wavBlob);
    reader.onloadend = async () => {
      const base64Audio = (reader.result as string).split(',')[1];
      try {
        const res = await fetch(`${MODEL_URL}/transcribe-chunk`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Authorization": `Bearer ${MODEL_API_KEY}` },
          body: JSON.stringify({
            session_id: currentSessionId,
            chunk_index: chunkIndexRef.current++,
            audio_b64: base64Audio,
            mode: selectedFile ? "context" : "baseline"
          })
        });
        
        const data = await res.json();
        
        // Handle the rewrite logic based on is_final
        if (data.is_final) {
          setFinalizedTranscript(prev => (prev + " " + data.partial_text).trim());
          setActiveTranscript(""); // Clear active buffer line
        } else if (data.partial_text) {
          setActiveTranscript(data.partial_text); // Overwrite active line with latest context
        }
      } catch (err) {
        console.error("Chunk error", err);
      }
    };
  };

  const startSession = async () => {
    try {
      setFinalizedTranscript("");
      setActiveTranscript("");
      setMessage("Initializing session...");
      const newSessionId = crypto.randomUUID();
      setSessionId(newSessionId);

      await fetch(`${MODEL_URL}/init`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${MODEL_API_KEY}` },
        body: JSON.stringify({ session_id: newSessionId, mode: selectedFile ? "context" : "baseline" })
      });

      if (selectedFile) {
        setMessage("Processing lecture notes...");
        const formData = new FormData();
        formData.append("session_id", newSessionId);
        formData.append("pdf_file", selectedFile);
        await fetch(`${MODEL_URL}/process-notes`, {
          method: "POST",
          headers: { "Authorization": `Bearer ${MODEL_API_KEY}` },
          body: formData
        });
      }

      setMessage("Recording started...");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      
      const AudioContext = window.AudioContext || (window as any).webkitAudioContext;
      const audioCtx = new AudioContext({ sampleRate: 16000 });
      audioCtxRef.current = audioCtx;
      
      const source = audioCtx.createMediaStreamSource(stream);
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      audioBufferRef.current = [];
      chunkIndexRef.current = 0;

      processor.onaudioprocess = (e) => {
        const channelData = e.inputBuffer.getChannelData(0);
        audioBufferRef.current.push(new Float32Array(channelData));
      };

      source.connect(processor);
      processor.connect(audioCtx.destination);

      intervalRef.current = setInterval(() => {
        const buffersToProcess = [...audioBufferRef.current];
        audioBufferRef.current = [];
        processAndSendChunk(newSessionId, buffersToProcess);
      }, 1500); //3000

      setIsRecording(true);
    } catch (error: any) {
      setMessage(`Error starting session: ${error.message}`);
      setIsRecording(false);
    }
  };

  const stopSession = async () => {
    if (!sessionId) return;
    setMessage("Finalizing transcript...");
    setIsRecording(false);

    if (intervalRef.current) clearInterval(intervalRef.current);
    if (processorRef.current) processorRef.current.disconnect();
    if (audioCtxRef.current) audioCtxRef.current.close();
    if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());

    try {
      const res = await fetch(`${MODEL_URL}/finalize`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${MODEL_API_KEY}` },
        body: JSON.stringify({ session_id: sessionId })
      });
      
      const data = await res.json();
      setFinalizedTranscript(data.final_transcript || "Transcript finalized.");
      setActiveTranscript("");
      setMessage("Session complete! You can copy your transcript.");
      setSessionId(null);
    } catch (err) {
      setMessage("Error finalizing session.");
    }
  };

  const downloadTranscript = () => {
    if (!finalizedTranscript) return;
    
    // Create a blob from the finalized text
    const blob = new Blob([finalizedTranscript], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    
    // Create a temporary anchor element to trigger the download
    const a = document.createElement("a");
    a.href = url;
    a.download = `Lecture_Transcript_${new Date().toISOString().split('T')[0]}.txt`;
    document.body.appendChild(a);
    a.click();
    
    // Cleanup
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="min-h-screen flex flex-col bg-gradient-dynamic p-4 sm:p-6 lg:p-8">
      <header className="w-full max-w-7xl mx-auto flex items-center justify-between mb-8 glass-panel px-6 py-4 rounded-2xl relative z-20 shadow-lg">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-[var(--brand)] to-[var(--brand-accent)] flex items-center justify-center text-white font-bold text-xl shadow-lg">C</div>
          <h1 className="text-xl font-bold tracking-tight text-[var(--foreground)] hidden sm:block">Caption Workspace</h1>
        </div>
        <div className="flex items-center gap-4">
          <div className="hidden sm:flex flex-col text-right">
            <span className="text-sm font-semibold text-[var(--foreground)]">{user.email}</span>
            <span className="text-xs text-[var(--text-secondary)]">Active Session</span>
          </div>
        </div>
      </header>

      <main className="w-full max-w-7xl mx-auto flex-1 grid grid-cols-1 lg:grid-cols-12 gap-8 relative z-10">
        <div className="lg:col-span-5 flex flex-col gap-6">
          <div className="glass-panel p-6 sm:p-8 h-full flex flex-col relative overflow-hidden group shadow-xl">
            <div className="absolute -top-12 -left-12 w-32 h-32 rounded-full bg-[var(--brand)] opacity-10 blur-2xl group-hover:opacity-20 transition-opacity duration-700"></div>
            <h2 className="text-2xl font-bold mb-2 text-[var(--foreground)] tracking-tight">1. Add Context</h2>
            <p className="text-sm text-[var(--text-secondary)] mb-6">Upload lecture notes to bias the ASR.</p>
            
            <div className="flex flex-col flex-1 gap-5">
              <div className="flex-1 flex flex-col items-center justify-center border-2 border-dashed border-[var(--input-border)] rounded-2xl bg-[var(--input-bg)] p-8 transition-all hover:border-[var(--brand)] group/upload">
                <input type="file" id="file-upload" className="hidden" accept=".pdf" onChange={(e) => setSelectedFile(e.target.files?.[0] || null)} disabled={isRecording} />
                <label htmlFor="file-upload" className={`cursor-pointer flex flex-col items-center gap-4 text-center ${isRecording ? 'opacity-50' : ''}`}>
                  <div className="w-16 h-16 rounded-full bg-[var(--brand)]/10 flex items-center justify-center text-[var(--brand)] group-hover/upload:scale-110 transition-transform">
                    <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
                  </div>
                  <div>
                    <p className="text-lg font-semibold text-[var(--foreground)]">{selectedFile ? selectedFile.name : "Click to upload lecture notes"}</p>
                    <p className="text-sm text-[var(--text-secondary)]">PDF Format</p>
                  </div>
                </label>
              </div>
              {message && <div className={`p-3 rounded-lg text-sm font-medium ${message.includes("Error") ? "bg-red-50 text-red-600 border border-red-100" : "bg-blue-50 text-blue-600 border border-blue-100"}`}>{message}</div>}
              <h2 className="text-2xl font-bold mt-2 mb-2 text-[var(--foreground)]">2. Record</h2>
              {!isRecording ? (
                <button onClick={startSession} className="w-full py-4 rounded-xl bg-gradient-to-r from-[var(--brand)] to-[var(--brand-accent)] text-white font-bold text-lg hover:-translate-y-1 shadow-lg transition-all duration-300">Start Live Captioning</button>
              ) : (
                <button onClick={stopSession} className="w-full py-4 rounded-xl bg-red-600 text-white font-bold text-lg hover:bg-red-500 hover:-translate-y-1 shadow-lg transition-all duration-300 flex items-center justify-center gap-3">
                  <span className="animate-pulse h-3 w-3 bg-white rounded-full"></span>Stop & Finalize
                </button>
              )}
              {(!isRecording && finalizedTranscript) && (
                 <button onClick={downloadTranscript} className="w-full py-4 rounded-xl bg-slate-700 text-white font-bold text-lg hover:bg-slate-600 hover:-translate-y-1 shadow-lg transition-all duration-300 flex items-center justify-center gap-3 mt-4 border border-slate-600">
                   <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                   Download .TXT Transcript
                 </button>
              )}
            </div>
          </div>
        </div>

        {/* --- UPDATED TRANSCRIPT VIEW --- */}
        <div className="lg:col-span-7 flex flex-col gap-6">
          <div className="glass-panel p-6 sm:p-8 h-full flex flex-col shadow-xl">
            <div className="flex items-center justify-between mb-6 border-b border-[var(--card-border)] pb-4">
              <h2 className="text-2xl font-bold text-[var(--foreground)] tracking-tight flex items-center gap-3">
                {isRecording && <span className="relative flex h-3 w-3"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span><span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span></span>}
                Live Transcript
              </h2>
              <span className="text-xs font-bold uppercase tracking-wider text-[var(--brand)] bg-[var(--brand)]/10 px-3 py-1.5 rounded-full">{isRecording ? "Streaming" : "Standby"}</span>
            </div>

            <div className="flex-1 bg-[var(--input-bg)] rounded-xl p-6 overflow-y-auto whitespace-pre-wrap font-medium text-lg leading-relaxed text-[var(--text-primary)] border border-[var(--input-border)] shadow-inner min-h-[400px]">
              {/* Finalized text in standard color */}
              <span>{finalizedTranscript}</span>
              {/* Active text in the brand color to show it's "live" */}
              <span className="text-[var(--brand)] transition-all duration-200">{" " + activeTranscript}</span>
              
              {(!finalizedTranscript && !activeTranscript) && (
                <div className="flex h-full items-center justify-center text-[var(--text-secondary)] opacity-50">
                  <p>Ready to transcribe. Click start to begin.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}