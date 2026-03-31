"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const router = useRouter();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Already logged in → go straight to dashboard
  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    const result = await login(username.trim(), password);
    setSubmitting(false);
    if (result.ok) {
      router.push("/dashboard");
    } else {
      setError(result.error || "Access denied");
    }
  }

  if (loading) return null;

  return (
    <div className="min-h-screen flex items-center justify-center overflow-hidden bg-background">
      {/* Ambient background */}
      <div className="fixed inset-0 z-0 overflow-hidden pointer-events-none">
        <div className="absolute inset-0 digital-grid opacity-60" />
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-primary/10 blur-[120px] rounded-full" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-secondary/5 blur-[120px] rounded-full" />
      </div>

      <main className="relative z-10 w-full max-w-md px-6">
        {/* Logo */}
        <div className="text-center mb-12 space-y-4">
          <div className="inline-flex items-center justify-center p-4 bg-surface-container-highest rounded-lg border border-primary/20 mb-4 shadow-[0_0_30px_rgba(0,244,254,0.1)]">
            <span
              className="material-symbols-outlined text-5xl text-primary glow-cyan"
              style={{ fontVariationSettings: "'FILL' 1" }}
            >
              terminal
            </span>
          </div>
          <h1 className="font-headline text-3xl font-bold tracking-tighter text-on-surface uppercase leading-none">
            AI DECODER <span className="text-primary">ACADEMY</span>
          </h1>
          <p className="font-label text-xs tracking-[0.2em] text-on-surface-variant uppercase">
            Neural Link Interface • Secure Terminal
          </p>
        </div>

        {/* Card */}
        <div className="bg-surface-container-low p-8 rounded-lg border border-outline-variant/20 shadow-2xl backdrop-blur-sm">
          <form onSubmit={handleSubmit} className="space-y-8">
            <div className="space-y-2">
              <label className="font-label text-[10px] font-bold tracking-widest text-primary uppercase flex items-center gap-2">
                <span className="material-symbols-outlined text-sm">person</span>
                Student ID
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="DEC-XXXX-XXXX"
                required
                autoComplete="username"
                className="w-full bg-surface-container-highest border-b-2 border-outline-variant focus:border-primary px-4 py-3 text-on-surface placeholder:text-on-surface-variant/40 font-headline tracking-wider transition-all outline-none"
              />
            </div>

            <div className="space-y-2">
              <label className="font-label text-[10px] font-bold tracking-widest text-primary uppercase flex items-center gap-2">
                <span className="material-symbols-outlined text-sm">key</span>
                Access Key
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                required
                autoComplete="current-password"
                className="w-full bg-surface-container-highest border-b-2 border-outline-variant focus:border-primary px-4 py-3 text-on-surface placeholder:text-on-surface-variant/40 font-headline tracking-widest transition-all outline-none"
              />
            </div>

            {error && (
              <div className="flex items-center gap-2 text-error text-xs font-label tracking-wider">
                <span className="material-symbols-outlined text-sm">error</span>
                {error}
              </div>
            )}

            <div className="pt-4 space-y-4">
              <button
                type="submit"
                disabled={submitting}
                className="w-full py-4 bg-gradient-to-r from-primary to-primary-container text-on-primary font-headline font-bold uppercase tracking-widest rounded-lg hover:opacity-90 active:scale-[0.98] transition-all flex items-center justify-center gap-3 group disabled:opacity-60"
              >
                {submitting ? (
                  <>
                    <span className="w-4 h-4 border-2 border-on-primary/40 border-t-on-primary rounded-full animate-spin" />
                    Authenticating...
                  </>
                ) : (
                  <>
                    Enter Academy
                    <span className="material-symbols-outlined group-hover:translate-x-1 transition-transform">bolt</span>
                  </>
                )}
              </button>

              <p className="text-center font-label text-[10px] tracking-wider text-on-surface-variant/50 uppercase">
                Demo: admin / academy123
              </p>

              <p className="text-center font-label text-[10px] tracking-wider text-on-surface-variant/50 uppercase">
                New recruit?{" "}
                <a href="/register" className="text-primary hover:text-primary-container transition-colors">
                  Initialize Identity
                </a>
              </p>
            </div>
          </form>
        </div>
      </main>
    </div>
  );
}
