"use client";

import { useState, useEffect } from "react";
import { supabase } from "@/lib/supabase";
import { useRouter } from "next/navigation";

export default function SessionDashboard() {
  const router = useRouter();
  const [inputValue, setInputValue] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [user, setUser] = useState<any>(null);
  const [captions, setCaptions] = useState<{id: string, content: string, created_at: string}[]>([]);

  // Check session and listen for auth changes
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) {
        router.push("/");
      } else {
        setUser(session.user);
        fetchCaptions();
      }
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!session) {
        router.push("/");
      } else {
        setUser(session.user);
        fetchCaptions();
      }
    });

    return () => subscription.unsubscribe();
  }, [router]);

  const fetchCaptions = async () => {
    const { data, error } = await supabase
      .from('captions')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(6);
    
    if (data) setCaptions(data);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || !user) return;
    
    setIsSubmitting(true);
    setMessage("");

    try {
      const { data, error } = await supabase
        .from("captions")
        .insert([
          { 
            content: inputValue,
            user_id: user.id 
          }
        ]);

      if (error) throw error;
      
      setInputValue("");
      fetchCaptions(); // Refresh the list dynamically!
    } catch (error: any) {
      console.error("Error saving data:", error);
      setMessage(`Error: ${error.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!user) return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-dynamic">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-[var(--brand)] border-t-transparent"></div>
    </div>
  );

  return (
    <div className="min-h-screen flex flex-col bg-gradient-dynamic p-4 sm:p-6 lg:p-8">
      {/* Top Navigation Bar */}
      <header className="w-full max-w-7xl mx-auto flex items-center justify-between mb-8 glass-panel px-6 py-4 rounded-2xl relative z-20">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-[var(--brand)] to-[var(--brand-accent)] flex items-center justify-center text-white font-bold text-xl shadow-lg">
            C
          </div>
          <h1 className="text-xl font-bold tracking-tight text-[var(--foreground)] hidden sm:block">
            Caption Workspace
          </h1>
        </div>
        <div className="flex items-center gap-4">
          <div className="hidden sm:flex flex-col text-right">
            <span className="text-sm font-semibold text-[var(--foreground)]">{user.email}</span>
            <span className="text-xs text-[var(--text-secondary)]">Active Session</span>
          </div>
          <div className="h-8 w-px bg-[var(--card-border)] hidden sm:block"></div>
          <button 
            onClick={() => supabase.auth.signOut()}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-[var(--text-secondary)] hover:text-white hover:bg-black/80 dark:hover:bg-white/10 transition-all duration-300"
          >
            Sign Out
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="w-full max-w-7xl mx-auto flex-1 grid grid-cols-1 lg:grid-cols-12 gap-8 relative z-10">
        
        {/* Left Column: Input Control */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          <div className="glass-panel p-6 sm:p-8 h-full flex flex-col relative overflow-hidden group shadow-xl">
            <div className="absolute -top-12 -left-12 w-32 h-32 rounded-full bg-[var(--brand)] opacity-10 blur-2xl group-hover:opacity-20 transition-opacity duration-700"></div>
            
            <h2 className="text-2xl font-bold mb-2 text-[var(--foreground)] tracking-tight">Add Context</h2>
            <p className="text-sm text-[var(--text-secondary)] mb-6">
              Enter specialized jargon, speaker names, or exact lecture notes to improve captioning accuracy.
            </p>
            
            <form onSubmit={handleSubmit} className="flex flex-col flex-1 gap-5">
              <div className="flex-1 flex flex-col min-h-[200px]">
                <textarea
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  disabled={isSubmitting}
                  className="flex-1 w-full p-5 rounded-2xl border border-[var(--input-border)] bg-[var(--input-bg)] text-[var(--text-primary)] focus:border-[var(--brand)] focus:ring-2 focus:ring-[var(--brand)] focus:ring-opacity-50 outline-none resize-none transition-all shadow-inner text-lg leading-relaxed"
                  placeholder="E.g., The protagonist of this novel is Raskolnikov..."
                  required
                />
              </div>

              {message && (
                <div className={`p-3 rounded-lg text-sm font-medium ${message.includes("Error") ? "bg-red-50 text-red-600 border border-red-100" : "bg-green-50 text-green-600 border border-green-100"}`}>
                  {message}
                </div>
              )}

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full py-4 rounded-xl bg-gradient-to-r from-[var(--brand)] to-[var(--brand-accent)] text-white font-bold text-lg hover:-translate-y-1 shadow-lg hover:shadow-xl disabled:opacity-50 disabled:hover:translate-y-0 transition-all duration-300 ease-out"
              >
                {isSubmitting ? "Processing..." : "Inject Context"}
              </button>
            </form>
          </div>
        </div>

        {/* Right Column: Live Data feed */}
        <div className="lg:col-span-7 flex flex-col gap-6">
          <div className="glass-panel p-6 sm:p-8 h-full flex flex-col shadow-xl">
            <div className="flex items-center justify-between mb-6 border-b border-[var(--card-border)] pb-4">
              <h2 className="text-2xl font-bold text-[var(--foreground)] tracking-tight flex items-center gap-3">
                <span className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
                </span>
                Active Database Flow
              </h2>
              <span className="text-xs font-bold uppercase tracking-wider text-[var(--brand)] bg-[var(--brand)]/10 px-3 py-1.5 rounded-full">
                Live Server
              </span>
            </div>

            <div className="flex-1 flex flex-col gap-4 overflow-y-auto pr-2 pb-4">
              {captions.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center text-[var(--text-secondary)] opacity-50 space-y-4">
                  <div className="w-16 h-16 rounded-full border-2 border-dashed border-[var(--text-secondary)] flex items-center justify-center">
                    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                    </svg>
                  </div>
                  <p>Database is waiting for notes...</p>
                </div>
              ) : (
                captions.map((caption) => (
                  <div key={caption.id} className="p-5 rounded-2xl bg-[var(--input-bg)] border border-[var(--input-border)] shadow-sm hover:shadow-md transition-all duration-300 transform hover:-translate-x-1 group">
                    <p className="text-[var(--text-primary)] font-medium leading-relaxed mb-3 text-lg">
                      {caption.content}
                    </p>
                    <div className="flex items-center justify-between text-xs text-[var(--text-secondary)] font-medium">
                      <span className="truncate max-w-[200px] font-mono bg-[var(--background)] px-2 py-1 rounded-md border border-[var(--input-border)] shadow-inner">
                        id: {caption.id.substring(0, 8)}
                      </span>
                      <span>
                        {new Date(caption.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'})}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
