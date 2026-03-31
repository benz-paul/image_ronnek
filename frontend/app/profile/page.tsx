"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/hooks/useAuth";
import { LatestRunButton } from "@/components/LatestRunButton";

interface AvatarJson {
  avatar_id: string;
  name: string;
  version: string;
  visual: {
    base_face: string;
    expressions: Record<string, string | null>;
    style: { type: string; consistency_rules?: Record<string, string> };
  };
  voice: { engine: string; voice_id: string; language_code?: string };
  character: { personality: string };
  animation: { lip_sync: { enabled: boolean } };
  metadata: { created_at: string; updated_at: string; status: string };
}

const EXPRESSIONS: Array<{ key: string; label: string; icon: string }> = [
  { key: "neutral",      label: "Neutral",   icon: "face" },
  { key: "happy",        label: "Happy",     icon: "mood" },
  { key: "sad",          label: "Sad",       icon: "mood_bad" },
  { key: "surprised",    label: "Surprised", icon: "mystery" },
  { key: "angry",        label: "Angry",     icon: "sentiment_very_dissatisfied" },
];

export default function ProfilePage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  const [avatar, setAvatar] = useState<AvatarJson | null>(null);
  const [avatarLoading, setAvatarLoading] = useState(true);
  const [activeExpr, setActiveExpr] = useState("neutral");
  const [runCount, setRunCount] = useState<number | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [loading, user, router]);

  useEffect(() => {
    if (!user) return;
    fetch(`/api/avatar/${user.username}`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { setAvatar(d); setAvatarLoading(false); })
      .catch(() => setAvatarLoading(false));
    fetch("/api/runs")
      .then((r) => r.ok ? r.json() : [])
      .then((d: unknown[]) => setRunCount(d.length))
      .catch(() => {});
  }, [user]);

  function handleLogout() {
    logout();
    router.push("/");
  }

  if (loading || (!user && !loading)) return null;

  const avatarImgUrl = avatar
    ? (activeExpr === "neutral"
        ? `/api/avatar/${user!.username}/base_face.png`
        : `/api/avatar/${user!.username}/expressions/${activeExpr}.png`)
    : null;

  const avatarId = avatar?.avatar_id ?? "—";
  const activatedAt = avatar?.metadata?.created_at
    ? new Date(avatar.metadata.created_at).toLocaleDateString("en-GB", { month: "short", year: "numeric" })
    : "—";

  return (
    <div className="min-h-screen bg-background text-on-background pb-24">
      {/* Ambient scanline overlay */}
      <div className="fixed inset-0 pointer-events-none z-[100] terminal-scanline opacity-[0.03]" />

      {/* ── Header ── */}
      <header className="bg-[#0e0e13] flex justify-between items-center px-6 py-4 w-full sticky top-0 z-50 border-b border-outline-variant/10">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary" style={{ fontVariationSettings: "'FILL' 1" }}>terminal</span>
          <h1 className="text-xl font-bold tracking-widest text-primary uppercase font-headline">AI DECODER ACADEMY</h1>
        </div>
        <div className="flex items-center gap-4">
          <Link
            href="/dashboard"
            className="font-label text-xs tracking-widest uppercase text-on-surface-variant hover:text-primary transition-colors"
          >
            Dashboard
          </Link>
          <button
            onClick={handleLogout}
            className="font-label text-xs tracking-tight uppercase text-on-surface-variant/60 hover:text-secondary transition-colors duration-300 active:scale-95"
          >
            LOGOUT
          </button>
        </div>
      </header>

      {/* ── Content ── */}
      <main className="relative px-6 pt-8 max-w-md mx-auto overflow-x-hidden">

        {/* Profile header */}
        <section className="flex flex-col items-center text-center mb-10">
          <div className="relative mb-6">
            {/* Rings */}
            <div className="absolute -inset-2 rounded-full border border-primary/20 animate-pulse" />
            <div className="absolute -inset-4 rounded-full border border-primary/5" />
            {/* Avatar image */}
            <div className="relative w-32 h-32 rounded-full overflow-hidden border-2 border-primary shadow-[0_0_20px_rgba(161,250,255,0.3)] bg-surface-container-highest">
              {avatarLoading ? (
                <div className="w-full h-full flex items-center justify-center">
                  <span className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                </div>
              ) : avatarImgUrl ? (
                <img
                  src={avatarImgUrl}
                  alt={avatar?.name ?? "Avatar"}
                  className="w-full h-full object-cover brightness-110 contrast-125"
                  key={activeExpr}
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <span className="material-symbols-outlined text-4xl text-primary/40" style={{ fontVariationSettings: "'FILL' 1" }}>
                    account_circle
                  </span>
                </div>
              )}
            </div>
            {/* Online badge */}
            <div className="absolute bottom-1 right-1 bg-tertiary text-on-tertiary px-2 py-0.5 rounded-full text-[10px] font-bold font-label flex items-center gap-1 shadow-lg">
              <span className="w-1.5 h-1.5 bg-on-tertiary rounded-full animate-ping" />
              ONLINE
            </div>
          </div>

          <h2 className="font-headline text-3xl font-bold tracking-tight text-on-background mb-1">
            {user?.displayName || user?.username}
          </h2>
          <p className="font-label text-xs tracking-widest text-primary-dim uppercase mb-1">
            {avatar ? `${user?.username}@decoder.academy` : user?.username}
          </p>
          <p className="font-label text-[10px] text-outline uppercase tracking-tighter">
            Activated: {activatedAt}
          </p>
        </section>

        {/* Expression switcher (only when avatar exists) */}
        {avatar && (
          <section className="mb-8">
            <div className="grid grid-cols-5 gap-1 bg-surface-container p-1 rounded">
              {EXPRESSIONS.map((e) => (
                <button
                  key={e.key}
                  onClick={() => setActiveExpr(e.key)}
                  className={`py-2 flex flex-col items-center justify-center gap-1 transition-all ${
                    activeExpr === e.key
                      ? "bg-surface-container-highest text-primary border-b-2 border-primary"
                      : "text-on-surface-variant hover:text-primary"
                  }`}
                >
                  <span className="material-symbols-outlined text-lg">{e.icon}</span>
                  <span className="font-label text-[8px] uppercase tracking-tighter">{e.label}</span>
                </button>
              ))}
            </div>
          </section>
        )}

        {/* Stats row */}
        <section className="grid grid-cols-2 gap-4 mb-8">
          <div className="bg-surface-container-low p-4 rounded-lg border-l-2 border-primary shadow-sm">
            <p className="font-label text-[10px] text-outline uppercase mb-1">MISSIONS COMPLETED</p>
            <p className="font-headline text-2xl font-bold text-on-background">{runCount ?? "—"}</p>
          </div>
          <div className="bg-surface-container-low p-4 rounded-lg border-l-2 border-secondary shadow-sm">
            <p className="font-label text-[10px] text-outline uppercase mb-1">AVATAR_ID</p>
            <p className="font-headline text-lg font-bold text-on-background truncate">{avatarId}</p>
          </div>
        </section>

        {/* Action buttons */}
        <section className="flex flex-col gap-3 mb-8">
          <button
            onClick={() => router.push("/dashboard")}
            className="w-full py-4 bg-gradient-to-r from-primary to-primary-container text-on-primary font-headline font-bold uppercase tracking-widest rounded shadow-[0_0_20px_rgba(0,244,254,0.3)] active:scale-95 transition-all"
          >
            ENTER ACADEMY
          </button>
          <button
            onClick={() => router.push("/avatar/edit")}
            className="w-full py-4 border border-primary text-primary font-headline font-bold uppercase tracking-widest rounded hover:bg-primary/5 active:scale-95 transition-all flex items-center justify-center gap-2"
          >
            <span className="material-symbols-outlined text-lg">edit</span>
            {avatar ? "EDIT AVATAR" : "CREATE AVATAR"}
          </button>
        </section>

        {/* Jump to latest run */}
        <section className="mb-10">
          <button
            onClick={() =>
              fetch("/api/runs/latest")
                .then((r) => r.ok ? r.json() : Promise.reject())
                .then((d) => router.push(`/player/${d.run_id}`))
                .catch(() => alert("No pipeline runs found. Run the pipeline first."))
            }
            className="w-full p-6 bg-surface-container-highest border border-outline-variant rounded-lg flex items-center justify-between group active:translate-y-1 transition-transform overflow-hidden relative hover:border-secondary/40"
          >
            <div className="absolute inset-0 bg-secondary/5 opacity-0 group-hover:opacity-100 transition-opacity" />
            <div className="relative z-10 flex flex-col items-start text-left">
              <span className="font-label text-[10px] text-secondary uppercase tracking-widest mb-1">CONTINUE OPERATIONS</span>
              <span className="font-headline text-lg font-bold text-on-surface">JUMP TO LATEST RUN</span>
            </div>
            <span className="material-symbols-outlined text-secondary text-3xl transition-transform group-hover:translate-x-2">
              rocket_launch
            </span>
          </button>
        </section>

        {/* Avatar JSON viewer */}
        {avatar && (
          <section className="mb-12">
            <div className="flex items-center justify-between mb-3 px-1">
              <h3 className="font-label text-xs font-bold text-outline uppercase tracking-widest">AVATAR JSON DATA</h3>
              <span className="w-2 h-2 bg-primary rounded-full shadow-[0_0_8px_rgba(161,250,255,0.8)]" />
            </div>
            <div className="bg-surface-container-lowest p-5 rounded-lg border border-outline-variant font-mono text-[11px] leading-relaxed shadow-inner">
              <div className="flex gap-2"><span className="text-secondary">{"{"}</span></div>
              <div className="pl-4 space-y-0.5">
                <p><span className="text-primary-dim">"avatar_id"</span>: <span className="text-tertiary">"{avatar.avatar_id}"</span>,</p>
                <p><span className="text-primary-dim">"voice_engine"</span>: <span className="text-tertiary">"{avatar.voice?.engine?.toUpperCase()}"</span>,</p>
                <p><span className="text-primary-dim">"voice_id"</span>: <span className="text-tertiary">"{avatar.voice?.voice_id}"</span>,</p>
                <p><span className="text-primary-dim">"personality"</span>: <span className="text-tertiary">"{avatar.character?.personality}"</span>,</p>
                <p><span className="text-primary-dim">"style_type"</span>: <span className="text-tertiary">"{avatar.visual?.style?.type}"</span>,</p>
                <p><span className="text-primary-dim">"lip_sync"</span>: <span className="text-tertiary">{avatar.animation?.lip_sync?.enabled ? "true" : "false"}</span>,</p>
                <p><span className="text-primary-dim">"status"</span>: <span className="text-tertiary">"{avatar.metadata?.status}"</span></p>
              </div>
              <div className="flex gap-2"><span className="text-secondary">{"}"}</span></div>
              <div className="mt-4 pt-4 border-t border-outline-variant/30 flex items-center gap-2">
                <span className="text-primary-dim animate-pulse">_</span>
                <span className="text-[9px] text-outline uppercase tracking-tighter">System stable. All nodes active.</span>
              </div>
            </div>
          </section>
        )}

        {/* No avatar prompt */}
        {!avatarLoading && !avatar && (
          <section className="mb-12 p-6 bg-surface-container-low border border-dashed border-outline-variant rounded-lg text-center">
            <span className="material-symbols-outlined text-3xl text-on-surface-variant/40 mb-2 block">face</span>
            <p className="font-label text-xs text-on-surface-variant uppercase tracking-widest mb-4">No avatar generated yet</p>
            <button
              onClick={() => router.push("/avatar")}
              className="px-6 py-2 border border-primary text-primary font-label text-xs tracking-widest uppercase rounded hover:bg-primary/5 transition-all"
            >
              Generate Avatar
            </button>
          </section>
        )}
      </main>

      {/* Floating latest run button */}
      <LatestRunButton />
    </div>
  );
}
