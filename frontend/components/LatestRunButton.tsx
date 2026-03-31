"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

/**
 * A floating "Play Latest Run" button that fetches /api/runs/latest
 * and navigates to the player. Used across dashboard, player header, avatar pages.
 */
export function LatestRunButton({ compact = false }: { compact?: boolean }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function handleClick() {
    setLoading(true);
    try {
      const res = await fetch("/api/runs/latest");
      if (!res.ok) throw new Error("No runs");
      const data = await res.json();
      router.push(`/player/${data.run_id}`);
    } catch {
      alert("No pipeline runs found. Run the pipeline first.");
    } finally {
      setLoading(false);
    }
  }

  if (compact) {
    return (
      <button
        onClick={handleClick}
        disabled={loading}
        title="Play latest run"
        className="flex items-center gap-1.5 px-3 py-1.5 bg-primary/15 hover:bg-primary/25 text-primary border border-primary/30 rounded font-label text-[10px] tracking-widest uppercase transition-all disabled:opacity-50"
      >
        {loading ? (
          <span className="w-3 h-3 border border-primary/40 border-t-primary rounded-full animate-spin" />
        ) : (
          <span className="material-symbols-outlined text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>play_circle</span>
        )}
        {!loading && <span>Latest Run</span>}
      </button>
    );
  }

  return (
    <button
      onClick={handleClick}
      disabled={loading}
      className="fixed bottom-6 right-6 z-50 flex items-center gap-3 px-5 py-3 bg-primary text-on-primary font-headline font-bold text-sm uppercase tracking-widest rounded-full shadow-[0_0_30px_rgba(161,250,255,0.35)] hover:shadow-[0_0_50px_rgba(161,250,255,0.5)] active:scale-95 transition-all disabled:opacity-60"
    >
      {loading ? (
        <span className="w-5 h-5 border-2 border-on-primary/40 border-t-on-primary rounded-full animate-spin" />
      ) : (
        <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 1" }}>play_circle</span>
      )}
      {loading ? "Loading..." : "Play Latest"}
    </button>
  );
}
