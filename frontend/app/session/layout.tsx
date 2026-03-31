"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { useRouter } from "next/navigation";

export default function SessionLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    supabase.auth.getUser().then(({ data: { user } }) => {
      if (user) {
        setEmail(user.email ?? null);
      }
    });
  }, []);

  const handleLogout = async () => {
    await supabase.auth.signOut();
    router.push("/");
  };

  return (
    <div className="flex flex-col min-h-screen bg-gradient-dynamic px-4 pb-12">
      <header className="py-6 flex justify-between items-center max-w-5xl mx-auto w-full">
        <h1 className="text-xl font-bold tracking-tight text-[var(--foreground)] drop-shadow-sm">
          Lecture Captioning
        </h1>
        <div className="flex items-center gap-4">
          <span className="text-sm text-[var(--text-secondary)] hidden sm:inline-block">
            {email}
          </span>
          <button
            onClick={handleLogout}
            className="text-sm px-4 py-2 rounded-full border border-[var(--input-border)] hover:bg-[var(--card-bg)] transition-colors"
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="flex-grow flex flex-col items-center justify-center w-full max-w-5xl mx-auto">
        {children}
      </main>
    </div>
  );
}
