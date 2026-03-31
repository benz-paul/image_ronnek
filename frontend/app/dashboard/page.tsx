"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/hooks/useAuth";
import { LatestRunButton } from "@/components/LatestRunButton";

interface RunSummary {
  run_id: string;
  timestamp: string;
  chapter: string;
  subject: string;
  class_level: string;
  image_model: string;
  image_count: number;
  audio_count: number;
  has_audio: boolean;
  has_ppt: boolean;
}

function formatTimestamp(ts: string) {
  const m = ts.match(/(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
  if (!m) return ts;
  const [, y, mo, d, h, mi] = m;
  return `${d}/${mo}/${y} · ${h}:${mi}`;
}

export default function DashboardPage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [fetching, setFetching] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [loading, user, router]);

  useEffect(() => {
    fetch("/api/runs")
      .then((r) => r.json())
      .then((d) => { setRuns(d); setFetching(false); })
      .catch(() => { setFetchError("Cannot reach backend. Start uvicorn on port 8000."); setFetching(false); });
  }, []);

  const filtered = runs.filter((r) =>
    search === "" ||
    r.chapter?.toLowerCase().includes(search.toLowerCase()) ||
    r.subject?.toLowerCase().includes(search.toLowerCase()) ||
    r.run_id.toLowerCase().includes(search.toLowerCase())
  );

  function handleLogout() {
    logout();
    router.push("/");
  }

  if (loading || (!user && !loading)) return null;

  return (
    <div className="min-h-screen bg-background text-on-surface font-body overflow-x-hidden">

      {/* ── Top Nav ── */}
      <nav className="fixed top-0 left-0 right-0 z-50 flex justify-between items-center px-6 py-4 bg-gradient-to-b from-[#131319] to-transparent">
        <div className="flex items-center gap-8">
          <span className="text-xl font-headline font-bold tracking-tighter text-primary uppercase">
            AI DECODER ACADEMY
          </span>
        </div>
        <div className="flex items-center gap-4">
          <div className="hidden md:flex items-center bg-surface-container-highest px-4 py-1.5 rounded-lg border border-outline-variant/20">
            <span className="material-symbols-outlined text-sm text-primary mr-2">search</span>
            <input
              className="bg-transparent border-none outline-none text-xs font-label tracking-widest text-on-surface placeholder:text-outline w-48 uppercase"
              placeholder="QUERY SYSTEM..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <LatestRunButton compact />
          <button className="text-on-surface-variant hover:text-primary transition-colors">
            <span className="material-symbols-outlined">notifications</span>
          </button>
          <Link href="/profile" className="text-on-surface-variant hover:text-primary transition-colors" title="Profile">
            <span className="material-symbols-outlined">account_circle</span>
          </Link>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 text-xs font-label tracking-widest uppercase text-on-surface-variant hover:text-error transition-colors"
            title="Logout"
          >
            <span className="material-symbols-outlined text-sm">logout</span>
            <span className="hidden md:inline">Exit</span>
          </button>
        </div>
      </nav>

      {/* ── Sidebar ── */}
      <aside className="hidden md:flex flex-col h-screen fixed left-0 top-0 pt-20 pb-6 bg-[#131319] w-64 shadow-[4px_0px_20px_rgba(0,0,0,0.5)] z-40">
        {/* Agent card — click to go to profile */}
        <Link href="/profile" className="px-6 py-8 flex flex-col items-center border-b border-outline-variant/10 mb-4 group hover:bg-surface-container-high/30 transition-colors">
          <div className="w-16 h-16 rounded-lg bg-surface-container-highest flex items-center justify-center mb-3 shadow-[0_0_15px_rgba(0,245,255,0.2)] group-hover:shadow-[0_0_25px_rgba(0,245,255,0.3)] transition-shadow">
            <span
              className="material-symbols-outlined text-3xl text-primary"
              style={{ fontVariationSettings: "'FILL' 1" }}
            >
              account_circle
            </span>
          </div>
          <h3 className="font-headline font-bold text-lg tracking-tight">{user?.displayName}</h3>
          <p className="font-label text-[10px] text-primary tracking-[0.2em] uppercase mt-1">
            View Profile
          </p>
        </Link>

        {/* Nav items */}
        <nav className="flex-1 space-y-1 px-2">
          {[
            { icon: "terminal", label: "Command Center", active: false },
            { icon: "play_circle", label: "Mission Briefs", active: true },
            { icon: "library_books", label: "Knowledge Base", active: false },
            { icon: "emoji_events", label: "Achievements", active: false },
          ].map(({ icon, label, active }) => (
            <button
              key={label}
              className={`w-full flex items-center gap-4 px-4 py-3 font-label text-sm uppercase tracking-widest transition-all rounded-sm ${
                active
                  ? "bg-gradient-to-r from-primary/20 to-transparent text-primary"
                  : "text-on-surface-variant/60 hover:bg-surface-container-high hover:text-primary"
              }`}
            >
              <span className="material-symbols-outlined text-lg">{icon}</span>
              {label}
              {active && (
                <span className="ml-auto w-1.5 h-1.5 rounded-full bg-primary" />
              )}
            </button>
          ))}
        </nav>

        {/* Progress widget */}
        <div className="mx-4 p-4 bg-surface-container rounded-lg border border-primary/10">
          <p className="font-label text-[10px] tracking-widest uppercase text-on-surface-variant mb-3">
            Decoding Progress
          </p>
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <div className="h-1 bg-surface-container-highest progress-track">
                <div className="h-full bg-primary w-[72%] progress-indicator" />
              </div>
            </div>
            <span className="font-headline text-sm font-bold text-primary">72%</span>
          </div>
        </div>
      </aside>

      {/* ── Main content ── */}
      <main className="md:ml-64 pt-20 px-6 pb-12">

        {/* Mission status hero */}
        <div className="mb-10 p-6 bg-surface-container-low rounded-lg border border-primary/10 flex items-start gap-6">
          <div className="w-12 h-12 rounded-lg bg-surface-container-highest flex items-center justify-center shrink-0 shadow-[0_0_20px_rgba(0,245,255,0.15)]">
            <span
              className="material-symbols-outlined text-2xl text-primary"
              style={{ fontVariationSettings: "'FILL' 1" }}
            >
              psychology
            </span>
          </div>
          <div className="flex-1">
            <p className="font-label text-[10px] tracking-[0.2em] uppercase text-on-surface-variant mb-1">
              Active Mission
            </p>
            <h2 className="font-headline text-xl font-bold tracking-tight">
              Neural Architecture Optimization
            </h2>
            <p className="font-body text-sm text-on-surface-variant mt-1 line-clamp-2">
              Select a mission brief below to begin your immersive learning session.
            </p>
          </div>
          <div className="text-right shrink-0">
            <div className="font-headline text-2xl font-bold text-primary">{runs.length}</div>
            <div className="font-label text-[10px] tracking-widest uppercase text-on-surface-variant">
              Runs Available
            </div>
          </div>
        </div>

        {/* Section header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <p className="font-label text-[10px] tracking-[0.2em] uppercase text-on-surface-variant">
              Mission Library
            </p>
            <h3 className="font-headline text-lg font-bold tracking-tight">Mission Briefs</h3>
          </div>
          {/* mobile search */}
          <div className="flex md:hidden items-center bg-surface-container-highest px-3 py-1.5 rounded-lg border border-outline-variant/20">
            <span className="material-symbols-outlined text-sm text-primary mr-1">search</span>
            <input
              className="bg-transparent border-none outline-none text-xs font-label w-28 text-on-surface placeholder:text-outline"
              placeholder="Search..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        {/* Run grid */}
        {fetching ? (
          <div className="flex items-center justify-center py-20">
            <div className="text-center">
              <div className="w-10 h-10 border-2 border-primary/30 border-t-primary rounded-full animate-spin mx-auto mb-4" />
              <p className="font-label text-xs tracking-widest uppercase text-on-surface-variant">
                Loading missions...
              </p>
            </div>
          </div>
        ) : fetchError ? (
          <div className="p-6 bg-error-container/20 border border-error/30 rounded-lg max-w-lg">
            <p className="font-label text-xs text-error tracking-wider">{fetchError}</p>
            <code className="block mt-3 text-xs text-primary/70 font-label">
              uvicorn backend.server:app --port 8000 --reload
            </code>
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-20 text-on-surface-variant/40">
            <span className="material-symbols-outlined text-4xl mb-3 block">inventory_2</span>
            <p className="font-label text-sm tracking-widest uppercase">No missions found</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filtered.map((run, i) => (
              <button
                key={run.run_id}
                onClick={() => router.push(`/player/${run.run_id}`)}
                className="run-card text-left bg-surface-container-low border border-outline-variant/20 hover:border-primary/30 rounded-lg overflow-hidden group"
              >
                {/* Card thumbnail area */}
                <div className="relative h-32 bg-surface-container-highest flex items-center justify-center overflow-hidden">
                  <div className="absolute inset-0 digital-grid opacity-30" />
                  <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-secondary/5" />
                  <span
                    className="material-symbols-outlined text-5xl text-primary/20 group-hover:text-primary/40 transition-colors"
                    style={{ fontVariationSettings: "'FILL' 1" }}
                  >
                    play_circle
                  </span>
                  {/* Image count badge */}
                  <div className="absolute top-3 right-3 px-2 py-0.5 bg-surface-container-highest/80 backdrop-blur-sm rounded font-label text-[10px] tracking-widest uppercase text-primary border border-primary/20">
                    {run.image_count} scenes
                  </div>
                  {/* Mission number */}
                  <div className="absolute bottom-3 left-3 font-headline text-xs text-on-surface-variant/40 tracking-widest uppercase">
                    Mission {String(i + 1).padStart(2, "0")}
                  </div>
                </div>

                {/* Card body */}
                <div className="p-5">
                  <h4 className="font-headline font-bold text-base tracking-tight text-on-surface group-hover:text-primary transition-colors line-clamp-2 mb-1">
                    {run.chapter || run.run_id}
                  </h4>
                  {run.subject || run.class_level ? (
                    <p className="font-label text-[10px] tracking-wider uppercase text-on-surface-variant mb-3">
                      {run.class_level && `Class ${run.class_level}`}
                      {run.class_level && run.subject && " · "}
                      {run.subject}
                    </p>
                  ) : null}

                  <div className="flex items-center justify-between">
                    <div className="flex gap-2 flex-wrap">
                      {run.has_audio ? (
                        <span className="px-2 py-0.5 text-[10px] font-label tracking-wider uppercase bg-primary/10 text-primary border border-primary/20 rounded">
                          Audio
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 text-[10px] font-label tracking-wider uppercase bg-surface-container text-on-surface-variant/50 rounded">
                          Silent
                        </span>
                      )}
                      {run.has_ppt && (
                        <span className="px-2 py-0.5 text-[10px] font-label tracking-wider uppercase bg-secondary/10 text-secondary border border-secondary/20 rounded">
                          PPT
                        </span>
                      )}
                    </div>
                    <span className="font-label text-[10px] tracking-wider text-on-surface-variant/40 uppercase">
                      {formatTimestamp(run.timestamp)}
                    </span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
