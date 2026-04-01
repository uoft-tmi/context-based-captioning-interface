'use client';

import { useState } from 'react';
import { supabase } from '@/lib/supabase';

export default function UpdatePasswordPage() {
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState('');

  const handleUpdatePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password.length < 6) {
      setMessage('Error: Password must be at least 6 characters.');
      return;
    }

    setIsSubmitting(true);
    setMessage('Updating password...');

    try {
      const { error } = await supabase.auth.updateUser({
        password: password,
      });

      if (error) throw error;

      setMessage('Success! Your password has been updated. Redirecting...');

      // Automatically redirect them to the session page after a short delay
      setTimeout(() => {
        if (typeof window !== 'undefined') {
          window.location.replace('/session');
        }
      }, 2000);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      console.error('Error updating password:', error);
      setMessage(`Error: ${message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className='flex min-h-screen flex-col items-center justify-center p-4 sm:p-8 bg-gradient-dynamic'>
      <div className='w-full max-w-md p-8 glass-panel rounded-2xl shadow-lg relative overflow-hidden'>
        {/* Decorative elements */}
        <div className='absolute -top-8 -right-8 w-24 h-24 rounded-full bg-(--brand) opacity-20 blur-xl pointer-events-none'></div>
        <div className='absolute -bottom-8 -left-8 w-24 h-24 rounded-full bg-(--brand-accent) opacity-20 blur-xl pointer-events-none'></div>

        <div className='relative z-10'>
          <h1 className='text-2xl font-bold mb-2 text-foreground tracking-tight'>
            Update Password
          </h1>
          <p className='text-sm text-(--text-secondary) mb-6'>
            Please enter your new password below.
          </p>

          <form onSubmit={handleUpdatePassword} className='flex flex-col gap-5'>
            <div>
              <label
                htmlFor='passwordInput'
                className='block text-sm font-semibold text-(--text-secondary) mb-1.5'
              >
                New Password
              </label>
              <input
                id='passwordInput'
                type='password'
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isSubmitting}
                className='w-full p-4 rounded-xl border border-(--input-border) bg-(--input-bg) text-(--text-primary) focus:border-(--brand) focus:ring-1 focus:ring-(--brand) outline-none transition-all'
                placeholder='••••••••'
                required
              />
            </div>

            <button
              type='submit'
              disabled={isSubmitting}
              className='w-full py-3.5 rounded-xl bg-(--brand) text-(--brand-text) font-semibold hover:-translate-y-0.5 shadow-sm hover:shadow-md disabled:opacity-50 disabled:hover:translate-y-0 transition-all duration-300 ease-in-out'
            >
              {isSubmitting ? 'Updating...' : 'Update Password'}
            </button>

            {message && (
              <div
                className={`p-3 rounded-lg text-sm text-center font-medium ${message.includes('Error') ? 'bg-red-50 text-red-600 border border-red-100' : 'bg-green-50 text-green-600 border border-green-100'}`}
              >
                {message}
              </div>
            )}
          </form>
        </div>
      </div>
    </div>
  );
}
