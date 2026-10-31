'use client';

import { useState, useEffect } from 'react';
import { supabase } from '@/lib/supabase';
import { Auth } from '@supabase/auth-ui-react';
import { ThemeSupa } from '@supabase/auth-ui-shared';
import { Brand, Loading, Notice } from '@/components/ui';

export default function Home() {
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    void supabase.auth.getSession().then(({ data: { session }, error }) => {
      if (cancelled) return;
      if (error) setError('We couldn’t restore your session. Please sign in below.');
      if (session) window.location.replace('/session');
      else setChecking(false);
    }).catch(() => { if (!cancelled) { setError('We couldn’t restore your session. Please sign in below.'); setChecking(false); } });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (session) window.location.replace(event === 'PASSWORD_RECOVERY' ? '/update-password' : '/session');
    });
    return () => { cancelled = true; subscription.unsubscribe(); };
  }, []);

  if (checking) return <div className="password-page"><Loading>Opening your workspace…</Loading></div>;

  return <main className="auth-shell">
    <section className="auth-story" aria-labelledby="welcome-title"><Brand />
      <div className="auth-story-content"><p className="eyebrow">Made for the way you teach</p><h2 id="welcome-title" className="story-title">Your knowledge.<br />Every word, clearer.</h2><p>Bring your lectures to life with live captions. Add your notes, teach as you normally would, and take a transcript with you.</p>
        <div className="caption-preview" aria-label="Example lecture captions"><div className="preview-heading"><span />A glimpse of your lecture</div><p>“Today, we’ll explore how <mark>small ideas</mark> can lead to a deeper understanding.”</p></div>
      </div><p className="story-footer">Prepare your lecture. Start speaking. Keep the transcript.</p>
    </section>
    <section className="auth-form-side" aria-labelledby="sign-in-title"><div className="auth-form"><Brand /><h1 id="sign-in-title">Your lecture starts here.</h1><p className="muted">Sign in to prepare your next captioning session.</p>
      {error && <Notice tone="error">{error}</Notice>}
      <Auth supabaseClient={supabase} providers={[]} appearance={{
        theme: ThemeSupa,
        variables: { default: {
          colors: { brand: 'var(--brand)', brandAccent: 'var(--brand-accent)', brandButtonText: 'var(--brand-text)', defaultButtonBackground: 'transparent', defaultButtonBackgroundHover: '#f3f7f4', inputBackground: 'var(--input-bg)', inputBorder: 'var(--input-border)', inputBorderHover: '#92b0a4', inputBorderFocus: 'var(--brand)', inputText: 'var(--text-primary)', inputLabelText: 'var(--text-primary)', inputPlaceholder: '#65737d', messageText: 'var(--text-primary)', anchorTextColor: 'var(--brand)', anchorTextHoverColor: 'var(--brand-accent)', dividerBackground: 'var(--card-border)' },
          fonts: { bodyFontFamily: 'inherit', buttonFontFamily: 'inherit', inputFontFamily: 'inherit', labelFontFamily: 'inherit' },
          fontSizes: { baseBodySize: '14px', baseInputSize: '14px', baseLabelSize: '13px', baseButtonSize: '14px' },
          space: { inputPadding: '13px 14px', buttonPadding: '13px 14px' },
          radii: { borderRadiusButton: '8px', buttonBorderRadius: '8px', inputBorderRadius: '8px' },
        } },
        className: { button: 'auth-button', input: 'auth-input', label: 'auth-label', message: 'auth-message', anchor: 'auth-anchor' },
      }} localization={{ variables: { sign_in: { email_label: 'Email address', email_input_placeholder: 'you@university.edu', password_label: 'Password', button_label: 'Sign in', loading_button_label: 'Signing in…' }, sign_up: { email_label: 'Email address', email_input_placeholder: 'you@university.edu', password_label: 'Create a password', button_label: 'Create account' } } }} redirectTo={typeof window !== 'undefined' ? `${window.location.origin}/update-password` : undefined} />
      <p className="auth-footnote">Live captions during class.<br />A transcript to return to afterward.</p>
    </div></section>
  </main>;
}
