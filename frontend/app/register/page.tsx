"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/hooks/useAuth";

// ─── Step indicator ───────────────────────────────────────────────────────────

function StepIndicator({ current }: { current: 1 | 2 | 3 }) {
  const steps = [
    { n: 1, label: "Create Account", icon: "person_add" },
    { n: 2, label: "Upload Photos",  icon: "photo_camera" },
    { n: 3, label: "Generate Avatar",icon: "auto_awesome" },
  ];
  return (
    <div className="flex items-center gap-0 mb-10">
      {steps.map((s, i) => (
        <div key={s.n} className="flex items-center">
          <div className={`flex flex-col items-center gap-1 ${s.n <= current ? "opacity-100" : "opacity-30"}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center border text-xs font-headline font-bold transition-all ${
              s.n < current  ? "bg-primary/30 border-primary text-primary" :
              s.n === current ? "bg-primary border-primary text-on-primary shadow-[0_0_12px_rgba(161,250,255,0.5)]" :
                               "bg-surface-container-highest border-outline-variant text-on-surface-variant"
            }`}>
              {s.n < current
                ? <span className="material-symbols-outlined text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>check</span>
                : s.n}
            </div>
            <span className="font-label text-[9px] tracking-widest uppercase text-on-surface-variant whitespace-nowrap hidden sm:block">
              {s.label}
            </span>
          </div>
          {i < steps.length - 1 && (
            <div className={`w-12 sm:w-20 h-px mx-1 transition-all ${s.n < current ? "bg-primary/50" : "bg-outline-variant/30"}`} />
          )}
        </div>
      ))}
    </div>
  );
}

// ─── Register Page ────────────────────────────────────────────────────────────

export default function RegisterPage() {
  const router = useRouter();
  const { login } = useAuth();

  const [form, setForm] = useState({
    fullName: "", username: "", email: "", password: "", confirmPassword: "",
  });
  const [error, setError]       = useState("");
  const [submitting, setSubmitting] = useState(false);

  function set(field: string, value: string) {
    setForm((f) => ({ ...f, [field]: value }));
    setError("");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (form.password !== form.confirmPassword) {
      setError("Passwords do not match"); return;
    }
    if (form.password.length < 6) {
      setError("Password must be at least 6 characters"); return;
    }
    setSubmitting(true);
    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fullName: form.fullName,
          username: form.username.trim().toLowerCase(),
          email: form.email,
          password: form.password,
        }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "Registration failed"); setSubmitting(false); return; }

      // Auto-login and go to avatar creation
      await login(form.username.trim().toLowerCase(), form.password);
      router.push(`/avatar?username=${encodeURIComponent(form.username.trim().toLowerCase())}&name=${encodeURIComponent(form.fullName)}`);
    } catch {
      setError("Backend offline — start it: uvicorn backend.server:app --port 8000 --reload"); setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-background overflow-hidden">
      {/* Ambient background */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        <div className="absolute inset-0 digital-grid opacity-50" />
        <div className="absolute top-[-10%] right-[-5%] w-[35%] h-[35%] bg-primary/8 blur-[120px] rounded-full" />
        <div className="absolute bottom-[-5%] left-[-5%] w-[30%] h-[30%] bg-secondary/5 blur-[100px] rounded-full" />
      </div>

      {/* Header */}
      <header className="relative z-10 flex items-center justify-between px-6 py-4 bg-[#0e0e13] border-b border-outline-variant/10">
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-primary" style={{ fontVariationSettings: "'FILL' 1" }}>terminal</span>
          <span className="font-headline font-bold text-xl tracking-tighter text-primary uppercase">AI DECODER ACADEMY</span>
        </div>
        <div className="px-3 py-1 bg-surface-container-highest rounded border border-outline-variant/20">
          <span className="font-label text-[10px] tracking-widest text-primary uppercase">Step 1 of 3</span>
        </div>
      </header>

      {/* Main */}
      <main className="relative z-10 flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-md">

          {/* Step indicator */}
          <StepIndicator current={1} />

          {/* Title */}
          <div className="mb-8">
            <h1 className="font-headline text-4xl font-bold tracking-tight uppercase leading-none mb-2">
              Initialize<br /><span className="text-primary">Identity</span>
            </h1>
            <p className="font-label text-[10px] tracking-[0.25em] uppercase text-on-surface-variant">
              Protocol: New_Recruit_Registration
            </p>
            <div className="h-px w-12 bg-primary mt-3" />
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-5">

            {[
              { id: "fullName",        label: "[01] Full Name",       type: "text",     placeholder: "DECODER_NAME",    icon: "badge" },
              { id: "username",        label: "[02] Student ID",      type: "text",     placeholder: "DEC-XXXX",        icon: "person" },
              { id: "email",           label: "[03] Neural Uplink",   type: "email",    placeholder: "agent@network.io", icon: "alternate_email" },
              { id: "password",        label: "[04] Access Key",      type: "password", placeholder: "••••••••",        icon: "key" },
              { id: "confirmPassword", label: "[05] Confirm Key",     type: "password", placeholder: "••••••••",        icon: "lock" },
            ].map(({ id, label, type, placeholder, icon }) => (
              <div key={id} className="space-y-1.5">
                <label className="font-label text-[10px] font-bold tracking-widest uppercase text-primary flex items-center gap-2">
                  <span className="material-symbols-outlined text-sm">{icon}</span>
                  {label}
                </label>
                <input
                  type={type}
                  value={(form as Record<string, string>)[id]}
                  onChange={(e) => set(id, e.target.value)}
                  placeholder={placeholder}
                  required
                  className="w-full bg-surface-container-highest border-b-2 border-outline-variant focus:border-primary px-4 py-2.5 text-on-surface placeholder:text-on-surface-variant/30 font-label tracking-wider text-sm outline-none transition-all"
                />
              </div>
            ))}

            {error && (
              <div className="flex items-start gap-2 text-error font-label tracking-wider py-2 px-3 bg-error/5 border border-error/20 rounded">
                <span className="material-symbols-outlined text-sm mt-0.5 shrink-0">error</span>
                <span className="text-xs leading-relaxed">{error}</span>
              </div>
            )}

            <div className="pt-4 space-y-4">
              <button
                type="submit"
                disabled={submitting}
                className="w-full py-4 bg-gradient-to-r from-primary to-primary-container text-on-primary font-headline font-bold uppercase tracking-widest rounded hover:opacity-90 active:scale-[0.98] transition-all flex items-center justify-center gap-3 group disabled:opacity-60"
              >
                {submitting ? (
                  <>
                    <span className="w-4 h-4 border-2 border-on-primary/40 border-t-on-primary rounded-full animate-spin" />
                    Registering...
                  </>
                ) : (
                  <>
                    Register Agent
                    <span className="material-symbols-outlined group-hover:translate-x-1 transition-transform">arrow_forward</span>
                  </>
                )}
              </button>

              <p className="text-center font-label text-[10px] tracking-wider text-on-surface-variant/50 uppercase">
                Already have access?{" "}
                <Link href="/" className="text-primary hover:text-primary-container transition-colors">
                  Login here
                </Link>
              </p>
            </div>
          </form>
        </div>
      </main>
    </div>
  );
}
