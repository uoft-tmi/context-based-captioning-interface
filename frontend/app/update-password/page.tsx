'use client';

import { useEffect, useRef, useState } from 'react';
import { supabase } from '@/lib/supabase';
import { Brand, Notice } from '@/components/ui';

export default function UpdatePasswordPage() {
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const redirect = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (redirect.current) clearTimeout(redirect.current); }, []);

  async function handleUpdatePassword(event: React.FormEvent) {
    event.preventDefault();
    if (isSubmitting || success) return;
    setError('');
    setIsSubmitting(true);
    try {
      const { error } = await supabase.auth.updateUser({ password });
      if (error) throw error;
      setSuccess(true);
      redirect.current = setTimeout(() => window.location.replace('/session'), 2000);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Unable to update your password. Please try again.');
    } finally { setIsSubmitting(false); }
  }

  return <main className="password-page"><div className="panel password-card"><Brand /><h1>Set a new password</h1><p className="muted">Choose a password to get back to your lecture workspace.</p>
    <form className="password-form" onSubmit={(event) => void handleUpdatePassword(event)}>
      <div><label htmlFor="password" className="field-label">New password</label><input id="password" className="text-input" type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} disabled={isSubmitting || success} placeholder="Enter your new password" minLength={6} aria-describedby="password-hint" required /><p id="password-hint" className="field-hint">Use at least 6 characters.</p></div>
      {error && <Notice tone="error">{error}</Notice>}
      {success && <Notice>Password updated. Opening your workspace…</Notice>}
      <button className="btn btn-primary" disabled={isSubmitting || success}>{isSubmitting ? 'Updating password…' : success ? 'Password updated' : 'Update password'}</button>
    </form>
  </div></main>;
}
