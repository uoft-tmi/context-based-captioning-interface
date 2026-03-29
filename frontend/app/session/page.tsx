"use client";

import { useState, useEffect } from "react";
import { supabase } from "@/lib/supabase";
import { fetchWithAuth } from "@/lib/api-client";
import NotesUpload from "@/components/notes-upload";

type SessionState =
  | "INIT"
  | "NOTES_PROCESSING"
  | "READY"
  | "STREAMING"
  | "FINALIZING"
  | "COMPLETE"
  | "ERROR";

export default function SessionPage() {
  const [sessionState, setSessionState] = useState<SessionState>("INIT");
  const [mode, setMode] = useState<"baseline" | "context" | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Magic to fix the Chrome Back Button! By listening to popstate, we update the React state internally.
  useEffect(() => {
    const handlePopState = () => {
      const step = new URLSearchParams(window.location.search).get("step") || "INIT";
      setSessionState(step as SessionState);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  // Update React state AND automatically push it to the URL history so the Back Button works perfectly!
  const updateSessionState = (newState: SessionState) => {
    setSessionState(newState);
    
    // Only push state if not already at INIT to avoid useless loops
    if (newState === "INIT") {
       window.history.pushState(null, "", window.location.pathname);
    } else {
       window.history.pushState(null, "", `?step=${newState}`);
    }
  };

  const handleCreateSession = async (selectedMode: "baseline" | "context") => {
    setErrorMsg(null);
    setIsCreating(true);
    setMode(selectedMode);
    
    try {
      const res = await fetchWithAuth("/api/sessions", {
        method: "POST",
        body: JSON.stringify({ mode: selectedMode }),
      });

      if (!res.ok) {
        throw new Error(`Failed to create session: ${res.statusText}`);
      }

      const data = await res.json();
      setSessionId(data.session_id);

      if (selectedMode === "context") {
        updateSessionState("NOTES_PROCESSING");
      } else {
        updateSessionState("READY");
      }
    } catch (err: any) {
      console.error(err);
      setErrorMsg(err.message || "An error occurred while creating the session.");
      updateSessionState("ERROR");
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="glass-panel w-full max-w-2xl p-8 sm:p-12 space-y-8 relative overflow-hidden">
      {/* Decorative elements */}
      <div className="absolute top-0 right-0 -mr-12 -mt-12 w-48 h-48 rounded-full bg-[var(--brand)] opacity-5 blur-3xl"></div>
      <div className="absolute bottom-0 left-0 -ml-12 -mb-12 w-48 h-48 rounded-full bg-[var(--brand-accent)] opacity-5 blur-3xl"></div>

      <div className="relative z-10 w-full">
        {sessionState === "INIT" && (
          <div className="space-y-6 text-center">
            <h2 className="text-2xl font-bold text-[var(--foreground)]">New Session</h2>
            <p className="text-[var(--text-secondary)]">
              Select a captioning mode to begin. Baseline is standard transcription. Context mode uses uploaded notes to improve domain-specific accuracy.
            </p>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-8">
              <button
                onClick={() => handleCreateSession("baseline")}
                disabled={isCreating}
                className="flex flex-col items-center justify-center p-6 border-2 border-[var(--input-border)] rounded-2xl hover:border-[var(--brand)] hover:shadow-md transition-all group bg-[var(--input-bg)] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <div className="h-12 w-12 rounded-full bg-slate-100 flex items-center justify-center mb-4 group-hover:bg-blue-50 transition-colors">
                  <span className="text-2xl">🎙️</span>
                </div>
                <h3 className="font-semibold text-lg">Baseline</h3>
                <p className="text-sm text-[var(--text-secondary)] mt-2">Standard AI captioning without extra context.</p>
              </button>

              <button
                onClick={() => handleCreateSession("context")}
                disabled={isCreating}
                className="flex flex-col items-center justify-center p-6 border-2 border-[var(--input-border)] rounded-2xl hover:border-[var(--brand)] hover:shadow-md transition-all group bg-[var(--input-bg)] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <div className="h-12 w-12 rounded-full bg-slate-100 flex items-center justify-center mb-4 group-hover:bg-blue-50 transition-colors">
                  <span className="text-2xl">📚</span>
                </div>
                <h3 className="font-semibold text-lg">Context-Aware</h3>
                <p className="text-sm text-[var(--text-secondary)] mt-2">Upload notes for improved accuracy.</p>
              </button>
            </div>
            {isCreating && <p className="text-sm text-[var(--brand)] mt-4 animate-pulse">Initializing session...</p>}
          </div>
        )}

        {sessionState === "NOTES_PROCESSING" && sessionId && (
          <NotesUpload 
            sessionId={sessionId}
            onSuccess={() => updateSessionState("READY")}
            onSkip={() => updateSessionState("READY")}
            onBack={() => updateSessionState("INIT")}
          />
        )}

        {sessionState === "READY" && (
          <div className="space-y-6 text-center">
            <h2 className="text-2xl font-bold text-[var(--foreground)]">Ready to Start</h2>
             <p className="text-[var(--text-secondary)]">
              Session is initialized and ready.
            </p>
            <button className="px-8 py-3 bg-[var(--brand)] text-[var(--brand-text)] font-bold rounded-full shadow hover:bg-[var(--brand-accent)] transition-colors mt-8 mx-auto block">
              Start Recording
            </button>

            <div className="mt-8 flex justify-center gap-4">
               <button 
                  onClick={() => updateSessionState("INIT")}
                  className="text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--foreground)] border border-[var(--input-border)] px-6 py-2 rounded-full hover:bg-[var(--card-bg)] transition-colors"
                >
                  ← Cancel Session
                </button>
               {mode === "context" && (
                 <button 
                  onClick={() => updateSessionState("NOTES_PROCESSING")}
                  className="text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--foreground)] border border-[var(--input-border)] px-6 py-2 rounded-full hover:bg-[var(--card-bg)] transition-colors"
                >
                  Edit PDF Notes
                </button>
               )}
            </div>
          </div>
        )}

        {sessionState === "ERROR" && (
          <div className="space-y-6 text-center text-red-600">
            <h2 className="text-2xl font-bold">Error</h2>
             <p className="text-sm bg-red-50 p-4 rounded-xl border border-red-200">
              {errorMsg || "An unknown error occurred."}
            </p>
            <button 
              onClick={() => updateSessionState("INIT")}
              className="px-8 py-3 bg-red-600 text-white font-bold rounded-full shadow hover:bg-red-700 transition-colors mt-8 mx-auto block"
            >
              Try Again
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
