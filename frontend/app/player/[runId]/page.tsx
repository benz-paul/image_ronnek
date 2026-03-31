"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useAudioPlayer, QueueItem } from "@/hooks/useAudioPlayer";
import { LatestRunButton } from "@/components/LatestRunButton";

interface CharacterDialogue { character_id: string; voice_id?: string; dialogue: string; audio_text?: string; }
interface DialogueUrl { url: string; speaker: string; duration_ms?: number; start_ms?: number; }
interface SceneAudio { combined_url?: string | null; combined_duration_ms?: number; narrator_url: string | null; narrator_duration_ms?: number; dialogue_urls?: DialogueUrl[]; total_duration_ms?: number; }
interface Scene { scene_id: string; phase: string; setting?: string; action?: string; narrator_audio_text?: string; character_dialogues?: CharacterDialogue[]; image_url?: string; audio?: SceneAudio; transition_hint?: string; student_interaction?: { type: string; prompt_text?: string; pause_seconds?: number; reveal_text?: string; }; }
interface RunData { run_id: string; config: Record<string, string>; learning_steps: Array<{ learning_step_id: string; title: string }>; scenes: Record<string, Scene[]>; has_audio: boolean; }
interface FlatScene extends Scene { ls_id: string; ls_index: number; scene_index: number; }

function flattenScenes(map: Record<string, Scene[]>): FlatScene[] {
  const flat: FlatScene[] = [];
  Object.keys(map).sort().forEach((ls_id, ls_index) => {
    (map[ls_id] || []).forEach((scene, scene_index) => flat.push({ ...scene, ls_id, ls_index, scene_index }));
  });
  return flat;
}

const PHASE_COLORS: Record<string, string> = {
  HOOK: "text-red-400 border-red-500/40",
  SETUP: "text-yellow-400 border-yellow-500/40",
  CONFUSION: "text-orange-400 border-orange-500/40",
  DISCOVERY: "text-green-400 border-green-500/40",
  GUIDANCE: "text-blue-400 border-blue-500/40",
  MICRO_LEARN: "text-purple-400 border-purple-500/40",
  VALIDATION: "text-emerald-400 border-emerald-500/40",
  APPLICATION: "text-cyan-400 border-cyan-500/40",
  REFLECTION: "text-indigo-400 border-indigo-500/40",
  PAYOFF: "text-pink-400 border-pink-500/40",
  TRANSITION: "text-on-surface-variant border-outline-variant/40",
  RESOLUTION: "text-green-400 border-green-500/40",
};

export default function PlayerPage() {
  const params = useParams();
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const runId = params.runId as string;

  const [runData, setRunData] = useState<RunData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [flatScenes, setFlatScenes] = useState<FlatScene[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [showDialogue, setShowDialogue] = useState(false);
  const [activeDialogueIndex, setActiveDialogueIndex] = useState(-1);
  const [isPaused, setIsPaused] = useState(false);
  const [audioMode, setAudioMode] = useState<"on" | "off">("on");
  const [showInteraction, setShowInteraction] = useState(false);
  const [showSidebar, setShowSidebar] = useState(true);
  const [displayedImageUrl, setDisplayedImageUrl] = useState<string | null>(null);
  const dialogueTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => { if (!authLoading && !user) router.replace("/"); }, [authLoading, user, router]);

  const advanceScene = useCallback(() =>
    setCurrentIndex((p) => Math.min(p + 1, flatScenes.length - 1)), [flatScenes.length]);

  const clearDialogueTimers = useCallback(() => {
    dialogueTimersRef.current.forEach(clearTimeout);
    dialogueTimersRef.current = [];
  }, []);

  const handleSegmentStart = useCallback((_idx: number, speaker: string) => {
    if (speaker !== "narrator") { setShowDialogue(true); setActiveDialogueIndex(_idx - 1); }
  }, []);

  const handleQueueEnd = useCallback(() => {
    if (isPaused) return;
    const scene = flatScenes[currentIndex];
    const inter = scene?.student_interaction;
    if (inter?.type && inter.type !== "none") setTimeout(() => setShowInteraction(true), 500);
    else setTimeout(() => advanceScene(), 2500);
  }, [isPaused, advanceScene, flatScenes, currentIndex]);

  const { play, playQueue, pause: audioPause, resume, stop, state: audioState } =
    useAudioPlayer({ onSegmentStart: handleSegmentStart, onQueueEnd: handleQueueEnd });

  useEffect(() => {
    if (!runId) return;
    fetch(`/api/runs/${runId}`)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((d: RunData) => { setRunData(d); setFlatScenes(flattenScenes(d.scenes)); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, [runId]);

  const goToPrev = useCallback(() => { stop(); setCurrentIndex((p) => Math.max(0, p - 1)); }, [stop]);
  const goToNext = useCallback(() => { stop(); advanceScene(); }, [stop, advanceScene]);

  useEffect(() => {
    const scene = flatScenes[currentIndex];
    if (!scene) return;
    setImageLoaded(false); setShowDialogue(false); setActiveDialogueIndex(-1); setShowInteraction(false);
    clearDialogueTimers();
    const t = setTimeout(() => {
      if (isPaused || audioMode === "off") {
        if (audioMode === "off" && !isPaused) {
          const a = setTimeout(() => advanceScene(), 5000);
          dialogueTimersRef.current.push(a);
        }
        return;
      }
      const audio = scene.audio;
      if (audio?.combined_url) {
        play(audio.combined_url);
        const dlgs = audio.dialogue_urls ?? [];
        const hasStartMs = dlgs.length > 0 && dlgs.some((d) => (d.start_ms ?? 0) > 0);
        if (hasStartMs) {
          // Reveal each dialogue bubble at its exact start time within the combined audio
          dlgs.forEach((d, i) => {
            const dt = setTimeout(() => {
              setShowDialogue(true);
              setActiveDialogueIndex(i);
            }, Math.max(200, d.start_ms ?? 0));
            dialogueTimersRef.current.push(dt);
          });
        } else {
          // Fallback: show all dialogues at 55% of total duration
          const dur = audio.combined_duration_ms ?? 5000;
          const dt = setTimeout(() => { setShowDialogue(true); setActiveDialogueIndex(999); }, Math.max(500, dur * 0.55));
          dialogueTimersRef.current.push(dt);
        }
      } else if (audio?.narrator_url || (audio?.dialogue_urls?.length ?? 0) > 0) {
        const q: QueueItem[] = [];
        if (audio?.narrator_url)
          q.push({ url: audio.narrator_url, speaker: "narrator", duration_ms: audio.narrator_duration_ms ?? 0 });
        for (const d of audio?.dialogue_urls ?? [])
          q.push({ url: d.url, speaker: d.speaker, duration_ms: d.duration_ms ?? 0 });
        playQueue(q);
        const dt = setTimeout(() => setShowDialogue(true), Math.max(500, (audio?.narrator_duration_ms ?? 3000) * 0.55));
        dialogueTimersRef.current.push(dt);
      } else {
        setShowDialogue(true); setActiveDialogueIndex(999);
        const dt = setTimeout(() => advanceScene(), 5000);
        dialogueTimersRef.current.push(dt);
      }
    }, 350);
    return () => { clearTimeout(t); clearDialogueTimers(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIndex]);

  // Preload next scene image to eliminate flash on transition
  useEffect(() => {
    const next = flatScenes[currentIndex + 1];
    if (next?.image_url) {
      const img = new window.Image();
      img.src = next.image_url;
    }
  }, [currentIndex, flatScenes]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === "l") goToNext();
      if (e.key === "ArrowLeft"  || e.key === "j") goToPrev();
      if (e.key === " ") { e.preventDefault(); setIsPaused((p) => { p ? resume() : audioPause(); return !p; }); }
      if (e.key === "Escape") { stop(); router.push("/dashboard"); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [goToNext, goToPrev, audioPause, resume, stop, router]);

  if (authLoading || (!user && !authLoading)) return null;

  if (loading) return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="text-center">
        <div className="w-10 h-10 border-2 border-primary/30 border-t-primary rounded-full animate-spin mx-auto mb-4" />
        <p className="font-label text-xs tracking-widest uppercase text-on-surface-variant">Loading mission...</p>
      </div>
    </div>
  );

  if (error || !runData || flatScenes.length === 0) return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="p-8 bg-error-container/20 border border-error/30 rounded-lg max-w-md text-center">
        <span className="material-symbols-outlined text-3xl text-error mb-3 block">error</span>
        <p className="font-headline font-bold text-error mb-2">Mission Failed to Load</p>
        <p className="font-body text-sm text-on-surface-variant mb-4">{error || "No scenes found."}</p>
        <button onClick={() => router.push("/dashboard")}
          className="px-6 py-2 bg-primary text-on-primary font-headline font-bold text-sm uppercase tracking-widest rounded-lg">
          Return to Base
        </button>
      </div>
    </div>
  );

  const cs = flatScenes[currentIndex];
  if (!cs || !runData?.scenes) return null;
  const lsIds = Object.keys(runData.scenes ?? {}).sort();
  const lsScenesCount = runData.scenes[cs.ls_id]?.length ?? 0;
  const overallProgress = (currentIndex + 1) / flatScenes.length;
  const phaseColor = PHASE_COLORS[cs.phase] ?? "text-on-surface-variant border-outline-variant/40";

  return (
    <div className="h-screen w-screen overflow-hidden bg-background text-on-surface font-body flex flex-col">
      <div className="fixed inset-0 z-0 pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-primary/[0.07] blur-[120px] rounded-full" />
        <div className="absolute bottom-[-5%] right-[-5%] w-[30%] h-[30%] bg-secondary/[0.07] blur-[100px] rounded-full" />
        <div className="absolute inset-0 scanline opacity-10" />
      </div>

      <header className="relative z-50 flex items-center justify-between px-6 py-3 bg-gradient-to-b from-[#131319] to-transparent shrink-0">
        <div className="flex items-center gap-4">
          <button onClick={() => { stop(); router.push("/dashboard"); }}
            className="font-label text-xs tracking-widest uppercase text-on-surface-variant hover:text-primary transition-colors flex items-center gap-1">
            <span className="material-symbols-outlined text-sm">arrow_back</span>
            <span className="hidden sm:inline">Base</span>
          </button>
          <span className="w-px h-4 bg-outline-variant/40" />
          <span className="hidden sm:block text-lg font-headline font-bold tracking-tighter text-primary uppercase">AI DECODER ACADEMY</span>
          <span className="w-px h-4 bg-outline-variant/40 hidden md:block" />
          <span className="hidden md:block font-label text-xs tracking-[0.15em] text-on-surface-variant uppercase line-clamp-1 max-w-xs">{runData.config?.chapter || runId}</span>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={() => { const n = audioMode === "on" ? "off" : "on"; setAudioMode(n); if (n === "off") stop(); }}
            className={"flex items-center gap-1.5 px-3 py-1 rounded-full font-label text-[10px] tracking-widest uppercase transition-all border " + (audioMode === "on" ? "bg-primary/15 text-primary border-primary/30" : "bg-surface-container text-on-surface-variant border-outline-variant/20")}>
            <span className="material-symbols-outlined text-sm">{audioMode === "on" ? "volume_up" : "volume_off"}</span>
            <span className="hidden sm:inline">{audioMode === "on" ? "Audio ON" : "Audio OFF"}</span>
          </button>
          <LatestRunButton compact />
          <button onClick={() => setShowSidebar((s) => !s)} className="text-on-surface-variant hover:text-primary transition-colors" title="Toggle sidebar">
            <span className="material-symbols-outlined text-xl">view_sidebar</span>
          </button>
        </div>
      </header>

      <div className="relative z-10 flex flex-1 min-h-0 gap-3 px-4 pb-2">
        <div className="flex-1 flex flex-col min-w-0 gap-2">
          <div className="relative flex-1 bg-surface-container-lowest/50 backdrop-blur-xl border border-primary/10 rounded-lg overflow-hidden shadow-[0_0_80px_rgba(0,0,0,0.8)]">
            {/* Layer 1: previous image — stays visible during transition to prevent black flash */}
            {displayedImageUrl && !imageLoaded && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={displayedImageUrl} alt="previous scene"
                className="absolute inset-0 w-full h-full object-cover" aria-hidden="true" />
            )}
            {/* Layer 2: new image — fades in on top once loaded */}
            {cs.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img key={cs.scene_id} src={cs.image_url} alt={cs.scene_id}
                onLoad={() => { setImageLoaded(true); setDisplayedImageUrl(cs.image_url ?? null); }}
                onError={() => { setImageLoaded(true); setDisplayedImageUrl(cs.image_url ?? null); }}
                className={"absolute inset-0 w-full h-full object-cover kenburns transition-opacity duration-700 " + (imageLoaded ? "opacity-100" : "opacity-0")} />
            ) : (
              <div className="absolute inset-0 w-full h-full flex items-center justify-center digital-grid">
                <div className="text-center text-on-surface-variant/30">
                  <span className="material-symbols-outlined text-6xl mb-2 block">image</span>
                  <p className="font-label text-xs tracking-widest uppercase">Image generating...</p>
                </div>
              </div>
            )}

            <div className="absolute inset-x-0 bottom-0 h-52 bg-gradient-to-t from-[#0e0e13] via-[#0e0e13]/60 to-transparent pointer-events-none" />

            <div className="absolute bottom-0 left-0 right-0 p-5 pointer-events-none">
              {cs.narrator_audio_text && (
                <p className="font-body text-sm text-on-surface/80 leading-relaxed line-clamp-3 mb-3 italic">{cs.narrator_audio_text}</p>
              )}
              {showDialogue && (cs.character_dialogues ?? []).length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {(cs.character_dialogues ?? []).filter((_, i) => activeDialogueIndex === 999 || i <= activeDialogueIndex).map((d, i) => {
                    const isSpeaking = activeDialogueIndex === 999 ? i === (cs.character_dialogues ?? []).length - 1 : i === activeDialogueIndex;
                    return (
                      <div key={i} className="dialogue-bubble inline-flex items-center gap-2 bg-surface-container-highest/80 backdrop-blur-md px-3 py-2 rounded-full border border-primary/20" style={{ animationDelay: `${i * 120}ms` }}>
                        <div className="w-6 h-6 rounded-full bg-primary/15 border border-primary/30 flex items-center justify-center shrink-0">
                          <span className="font-headline text-[9px] font-bold text-primary uppercase">{d.character_id?.charAt(0) ?? "?"}</span>
                        </div>
                        <span className="font-label text-[10px] tracking-wider uppercase text-primary/80">{d.character_id}</span>
                        {isSpeaking ? (
                          <div className="flex items-end gap-[2px] h-4">
                            {[0.1, 0.3, 0.2].map((delay, j) => (
                              <div key={j} className="w-[3px] rounded-full waveform-bar"
                                style={{ animationDelay: `${delay}s`, backgroundColor: "rgba(161,250,255,0.7)" }} />
                            ))}
                          </div>
                        ) : (
                          <span className="material-symbols-outlined text-[14px] text-primary/40">check</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {cs.phase && (
              <div className={"absolute top-4 right-4 px-3 py-1 text-[10px] font-label tracking-widest uppercase rounded border bg-surface-container-highest/70 backdrop-blur-sm " + phaseColor}>{cs.phase}</div>
            )}

            <div className="absolute top-4 left-4 pointer-events-none opacity-25 font-label text-[9px] tracking-widest uppercase">
              <div className="text-primary">{cs.ls_id}</div>
              <div className="text-on-surface-variant">S{cs.scene_index + 1}/{lsScenesCount}</div>
            </div>

            {isPaused && (
              <div className="absolute inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-10">
                <span className="material-symbols-outlined text-8xl text-primary/70" style={{ fontVariationSettings: "'FILL' 1" }}>pause_circle</span>
              </div>
            )}

            {showInteraction && cs.student_interaction && (
              <div className="absolute inset-0 bg-black/75 backdrop-blur-md flex items-center justify-center p-8 z-20">
                <div className="max-w-md w-full text-center space-y-6">
                  <span className="material-symbols-outlined text-5xl text-primary block" style={{ fontVariationSettings: "'FILL' 1" }}>psychology</span>
                  <h3 className="font-headline text-xl font-bold tracking-tight">{cs.student_interaction.prompt_text || "Think about this..."}</h3>
                  {cs.student_interaction.reveal_text && <p className="font-body text-sm text-on-surface-variant">{cs.student_interaction.reveal_text}</p>}
                  <button onClick={() => { setShowInteraction(false); advanceScene(); }}
                    className="px-8 py-3 bg-gradient-to-r from-primary to-primary-container text-on-primary font-headline font-bold uppercase tracking-widest rounded-lg hover:opacity-90 transition-all">
                    Continue
                  </button>
                </div>
              </div>
            )}

            {audioState === "loading" && (
              <div className="absolute top-4 left-1/2 -translate-x-1/2 w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            )}
          </div>

          <div className="shrink-0 flex items-center gap-3 px-1">
            <span className="font-label text-[10px] tracking-widest uppercase text-on-surface-variant/40 w-8 text-right tabular-nums">{currentIndex + 1}</span>
            <div className="flex-1 h-px bg-surface-container-highest progress-track">
              <div className="h-full bg-primary progress-indicator" style={{ width: `${overallProgress * 100}%` }} />
            </div>
            <span className="font-label text-[10px] tracking-widest uppercase text-on-surface-variant/40 w-8 tabular-nums">{flatScenes.length}</span>
          </div>

          <div className="shrink-0 flex items-center justify-center gap-6 py-1.5">
            {audioState === "playing" && !isPaused && (
              <div className="hidden sm:flex items-end gap-[3px] h-6">
                {[0.1, 0.3, 0.2, 0.5, 0.4, 0.1, 0.6, 0.3, 0.2, 0.1].map((delay, i) => (
                  <div key={i} className="w-1 rounded-full waveform-bar"
                    style={{ animationDelay: `${delay}s`, backgroundColor: `rgba(161,250,255,${0.4 + (i % 3) * 0.2})` }} />
                ))}
              </div>
            )}
            {audioState === "ended" && !isPaused && (
              <div className="hidden sm:flex items-center gap-1 text-on-surface-variant/40 font-label text-[10px] uppercase tracking-widest">
                <div className="w-1 h-1 rounded-full bg-primary/50 animate-ping" />
                Next scene...
              </div>
            )}
            <button onClick={goToPrev} disabled={currentIndex === 0}
              className="w-10 h-10 rounded-full border border-outline-variant/20 bg-surface-container hover:bg-surface-container-high hover:border-primary/30 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center transition-all">
              <span className="material-symbols-outlined text-lg">skip_previous</span>
            </button>
            <button onClick={() => setIsPaused((p) => { p ? resume() : audioPause(); return !p; })}
              className="w-14 h-14 rounded-full bg-primary text-on-primary flex items-center justify-center shadow-[0_0_20px_rgba(161,250,255,0.2)] hover:shadow-[0_0_35px_rgba(161,250,255,0.4)] transition-all active:scale-95">
              <span className="material-symbols-outlined text-3xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                {isPaused ? "play_circle" : "pause_circle"}
              </span>
            </button>
            <button onClick={goToNext} disabled={currentIndex === flatScenes.length - 1}
              className="w-10 h-10 rounded-full border border-outline-variant/20 bg-surface-container hover:bg-surface-container-high hover:border-primary/30 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center transition-all">
              <span className="material-symbols-outlined text-lg">skip_next</span>
            </button>
            <div className="hidden md:block font-label text-[10px] tracking-widest uppercase text-on-surface-variant/40">Space = pause | Esc = exit</div>
          </div>
        </div>

        {showSidebar && (
          <div className="hidden lg:flex flex-col w-72 shrink-0 gap-3 overflow-y-auto">
            <div className="bg-surface-container-low/80 backdrop-blur-sm border border-outline-variant/20 rounded-lg p-4 space-y-3">
              <p className="font-label text-[10px] tracking-widest uppercase text-primary/60">Active Scene</p>
              <h3 className="font-headline font-bold text-sm tracking-tight leading-snug line-clamp-3">{cs.setting || cs.action || cs.scene_id}</h3>
              <div className={"inline-flex px-2 py-0.5 text-[10px] font-label tracking-widest uppercase rounded border " + phaseColor}>{cs.phase}</div>
              {cs.transition_hint && <p className="font-body text-xs text-on-surface-variant/60 italic leading-relaxed">Next: {cs.transition_hint}</p>}
            </div>

            <div className="bg-surface-container-low/80 backdrop-blur-sm border border-outline-variant/20 rounded-lg p-4">
              <p className="font-label text-[10px] tracking-widest uppercase text-on-surface-variant/50 mb-3">Learning Steps</p>
              <div className="space-y-2">
                {lsIds.map((lsId, i) => {
                  const isActive = lsId === cs.ls_id;
                  const isDone = i < cs.ls_index;
                  const cnt = runData.scenes[lsId]?.length ?? 0;
                  return (
                    <div key={lsId} className={"flex items-center gap-2.5 py-1.5 px-2 rounded transition-all " + (isActive ? "bg-primary/10" : "")}>
                      <div className={"w-5 h-5 rounded-full flex items-center justify-center shrink-0 text-[9px] font-headline font-bold " + (isDone ? "bg-primary/25 text-primary" : isActive ? "bg-primary text-on-primary shadow-[0_0_10px_rgba(161,250,255,0.5)]" : "bg-surface-container-highest text-on-surface-variant/30")}>
                        {isDone ? "✓" : i + 1}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className={"font-label text-[10px] tracking-wider truncate " + (isActive ? "text-primary" : isDone ? "text-on-surface-variant/50" : "text-on-surface-variant/30")}>{lsId}</p>
                        {isActive && (
                          <div className="mt-1.5 h-0.5 bg-surface-container-highest progress-track">
                            <div className="h-full bg-primary progress-indicator" style={{ width: `${((cs.scene_index + 1) / cnt) * 100}%` }} />
                          </div>
                        )}
                      </div>
                      <span className="font-label text-[9px] text-on-surface-variant/25 shrink-0">{cnt}s</span>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="bg-surface-container-low/60 border border-outline-variant/10 rounded-lg p-4">
              <p className="font-label text-[10px] tracking-widest uppercase text-on-surface-variant/35 mb-3">Controls</p>
              <div className="space-y-1.5">
                {[["← / →", "Navigate"], ["Space", "Pause/Play"], ["Esc", "Exit"]].map(([k, a]) => (
                  <div key={k} className="flex justify-between items-center">
                    <kbd className="font-label text-[10px] px-1.5 py-0.5 bg-surface-container-highest rounded text-primary border border-primary/20">{k}</kbd>
                    <span className="font-label text-[10px] text-on-surface-variant/35 tracking-wider">{a}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
