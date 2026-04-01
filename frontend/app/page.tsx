'use client';

import { useState, useEffect } from 'react';
import { supabase } from '@/lib/supabase';
import { Auth } from '@supabase/auth-ui-react';
import { ThemeSupa } from '@supabase/auth-ui-shared';

export default function Home() {
  const [checking, setChecking] = useState(true);

  const redirectToSession = () => {
    if (typeof window !== 'undefined') {
      window.location.replace('/session');
    }
  };

  useEffect(() => {
    // Check initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        redirectToSession();
      }
      setChecking(false);
    });

    // Listen for auth changes (like signing in via the UI)
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) {
        redirectToSession();
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  if (checking) {
    return (
      <div className='flex min-h-screen items-center justify-center bg-gradient-dynamic'>
        <div className='h-8 w-8 animate-spin rounded-full border-4 border-(--brand) border-t-transparent'></div>
      </div>
    );
  }

  return (
    <div className='flex min-h-screen items-center justify-center bg-gradient-dynamic px-4'>
      <div className='glass-panel w-full max-w-md p-8 sm:p-10 space-y-6 relative overflow-hidden'>
        {/* Decorative elements */}
        <div className='absolute top-0 right-0 -mr-8 -mt-8 w-32 h-32 rounded-full bg-(--brand) opacity-10 blur-2xl'></div>
        <div className='absolute bottom-0 left-0 -ml-8 -mb-8 w-32 h-32 rounded-full bg-(--brand-accent) opacity-10 blur-2xl'></div>

        <div className='text-center relative z-10'>
          <h1 className='text-3xl font-bold tracking-tight text-foreground drop-shadow-sm'>
            Lecture Captioning
          </h1>
        </div>

        <div className='relative z-10 mt-8'>
          <Auth
            supabaseClient={supabase}
            providers={[]}
            appearance={{
              theme: ThemeSupa,
              variables: {
                default: {
                  colors: {
                    brand: 'var(--brand)',
                    brandAccent: 'var(--brand-accent)',
                    brandButtonText: 'var(--brand-text)',
                    defaultButtonBackground: 'transparent',
                    defaultButtonBackgroundHover: 'var(--card-bg)',
                    inputBackground: 'var(--input-bg)',
                    inputBorder: 'var(--input-border)',
                    inputBorderHover: 'var(--brand)',
                    inputBorderFocus: 'var(--brand)',
                    inputText: 'var(--text-primary)',
                    messageText: 'var(--text-primary)',
                    anchorTextColor: 'var(--brand)',
                    anchorTextHoverColor: 'var(--brand-accent)',
                    dividerBackground: 'var(--card-border)',
                  },
                  space: {
                    inputPadding: '0.875rem',
                    buttonPadding: '0.875rem',
                  },
                  radii: {
                    borderRadiusButton: '0.75rem',
                    buttonBorderRadius: '0.75rem',
                    inputBorderRadius: '0.75rem',
                  },
                },
              },
              className: {
                container: 'w-full',
                button:
                  'transition-all duration-300 ease-in-out hover:-translate-y-0.5 shadow-sm hover:shadow-md font-medium',
                input:
                  'transition-all duration-300 ease-in-out focus:ring-2 focus:ring-(--brand) focus:ring-opacity-50 shadow-sm',
                label: 'text-sm font-semibold text-(--text-secondary) mb-1.5',
                divider: 'my-6',
                message: 'mt-2 text-sm text-center',
                anchor: 'text-sm font-medium transition-colors hover:underline',
              },
            }}
            redirectTo={
              typeof window !== 'undefined'
                ? `${window.location.origin}/update-password`
                : undefined
            }
          />
        </div>
      </div>
    </div>
  );
}
