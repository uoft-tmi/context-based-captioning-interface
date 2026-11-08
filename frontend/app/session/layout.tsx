'use client';

import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { supabase } from '@/lib/supabase';
import { Brand, Icon, Loading, Notice } from '@/components/ui';
import { AccountOverview, getAccount } from '@/lib/api';

export default function SessionLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [email, setEmail] = useState<string | null>(null);
  const [signingOut, setSigningOut] = useState(false);
  const [error, setError] = useState('');
  const [account, setAccount] = useState<AccountOverview | null>(null);
  const [accessError, setAccessError] = useState('');

  useEffect(() => {
    void supabase.auth.getUser().then(({ data: { user } }) => setEmail(user?.email ?? null));
    void getAccount().then(setAccount).catch((error) => setAccessError(error instanceof Error ? error.message : 'Unable to check demo access.'));
  }, []);

  async function handleLogout() {
    setSigningOut(true);
    setError('');
    try {
      const { error } = await supabase.auth.signOut();
      if (error) throw error;
      window.location.replace('/');
    } catch {
      setError('Unable to sign out. Please try again.');
      setSigningOut(false);
    }
  }

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <header className="app-header"><div className="header-inner">
      <Brand />
      <div className="account"><span className="account-email">{email}</span>
        {pathname !== '/session/live' && <button className="btn btn-ghost btn-small" onClick={() => void handleLogout()} disabled={signingOut}><Icon name="logout" width="16" height="16" />{signingOut ? 'Signing out…' : 'Sign out'}</button>}
      </div>
    </div><nav className="workspace-tabs" aria-label="Workspace"><Link href="/session" className={pathname !== '/session/library' ? 'selected' : ''} aria-current={pathname === '/session' ? 'page' : undefined}>Dashboard</Link><Link href="/session/library" className={pathname === '/session/library' ? 'selected' : ''} aria-current={pathname === '/session/library' ? 'page' : undefined}>File library</Link></nav></header>
    <main id="main-content" className="workspace" tabIndex={-1}>{error && <Notice tone="error">{error}</Notice>}{accessError ? <Notice tone="error">{accessError}</Notice> : !account ? <Loading>Checking workspace access…</Loading> : <>{account.demo_mode && <Notice>Private demo: recordings are limited to 30 seconds, with a shared daily usage allowance.</Notice>}{account.transcription_enabled === false && <Notice tone="warning">Recording is temporarily disabled. Your saved sessions and transcripts are still available.</Notice>}{children}</>}</main>
    <footer className="app-footer"><span>More accessible lectures. One word at a time.</span><span>Lecture Captioning</span></footer>
  </div>;
}
