"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import DialogueBubble from "@/components/DialogueBubble";
import InteractionOverlay from "@/components/InteractionOverlay";
import ProgressBar from "@/components/ProgressBar";
import { useAudioPlayer, QueueItem } from "@/hooks/useAudioPlayer";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CharacterDialogue {
  character_id: string;
  voice_id: string;
  dialogue: string;
  audio_text?: string;
}

interface DialogueUrl {
  url: string;
  speaker: string;
  duration_ms?: number;
  start_ms?: number;
}

interface SceneAudio {
  combined_url?: string | null;
  combined_duration_ms?: number;
  narrator_url: string | null;
  narrator_duration_ms?: number;
  dialogue_urls?: DialogueUrl[];
  total_duration_ms?: number;
}

interface Scene {
  scene_id: string;
  phase: string;
  setting?: string;
  action?: string;
  narrator_audio_text?: string;
  character_dialogues?: CharacterDialogue[];
  image_url?: string;
  audio?: SceneAudio;
  transition_hint?: string;
  student_interaction?: {
    type: string;
    prompt_text?: string;
    pause_seconds?: number;
    reveal_text?: string;
  };
}

interface RunData {
  run_id: string;
  config: Record<string, string>;
  story_backbone: Record<string, unknown>;
  learning_steps: Array<{ learning_step_id: string; title: string }>;
  scenes: Record<string, Scene[]>;
  has_audio: boolean;
}

// ---------------------------------------------------------------------------
// Flat scene list helper
// ---------------------------------------------------------------------------

interface FlatScene extends Scene {
  ls_id: string;
  ls_index: number;
  scene_index: number;
}

function flattenScenes(scenesMap: Record<string, Scene[]>): FlatScene[] {
  const flat: FlatScene[] = [];
  const lsIds = Object.keys(scenesMap).sort();
  lsIds.forEach((ls_id, ls_index) => {
    const scenes = scenesMap[ls_id] || [];
    scenes.forEach((scene, scene_index) => {
      flat.push({ ...scene, ls_id, ls_index, scene_index });
    });
  });
  return flat;
}

// ---------------------------------------------------------------------------
// Player Page
// ---------------------------------------------------------------------------

export default function PlayerPage() {
  const params = useParams();
  const router = useRouter();
  const runId = params.runId as string;

  const [runData, setRunData] = useState<RunData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Flat scene list and current index
  const [flatScenes, setFlatScenes] = useState<FlatScene[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);

  // UI state
  const [imageLoaded, setImageLoaded] = useState(false);
  const [showDialogue, setShowDialogue] = useState(false);
  const [activeDialogueIndex, setActiveDialogueIndex] = useState(-1);
  const [isPaused, setIsPaused] = useState(false);
  const [audioMode, setAudioMode] = useState<"narrator" | "silent">("narrator");
  const [showInteraction, setShowInteraction] = useState(false);

  // Audio callbacks
  const advanceScene = useCallback(() => {
    setCurrentIndex((prev) => {
      if (prev < flatScenes.length - 1) return prev + 1;
      return prev;
    });
  }, [flatScenes.length]);

  const handleSegmentStart = useCallback((index: number, speaker: string) => {
    if (speaker === "narrator") {
      // Narrator is playing — show dialogue after a beat
    } else {
      // A character dialogue started — reveal that bubble
      setShowDialogue(true);
      setActiveDialogueIndex(index - 1); // index 0 = narrator, so dialogue 0 = index 1
    }
  }, []);

  const handleQueueEnd = useCallback(() => {
    if (isPaused) return;
    // Check if current scene has a student interaction
    const scene = flatScenes[currentIndex];
    const interaction = scene?.student_interaction;
    if (interaction && interaction.type && interaction.type !== "none") {
      // Show interaction overlay instead of advancing
      setTimeout(() => setShowInteraction(true), 500);
    } else {
      // Small delay before advancing to let the last bubble be read
      setTimeout(() => advanceScene(), 1500);
    }
  }, [isPaused, advanceScene, flatScenes, currentIndex]);

  const { play, playQueue, pause: audioPause, resume, stop, state: audioState } =
    useAudioPlayer({
      onSegmentStart: handleSegmentStart,
      onQueueEnd: handleQueueEnd,
    });

  // ---------------------------------------------------------------------------
  // Load run data
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!runId) return;
    fetch(`/api/runs/${runId}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: RunData) => {
        setRunData(data);
        const flat = flattenScenes(data.scenes);
        setFlatScenes(flat);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, [runId]);

  // ---------------------------------------------------------------------------
  // Scene navigation
  // ---------------------------------------------------------------------------

  const currentScene = flatScenes[currentIndex] ?? null;

  const goToPrev = useCallback(() => {
    stop();
    setCurrentIndex((prev) => Math.max(0, prev - 1));
  }, [stop]);

  const goToNext = useCallback(() => {
    stop();
    advanceScene();
  }, [stop, advanceScene]);

  // ---------------------------------------------------------------------------
  // When scene changes: build audio queue and play
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!currentScene) return;
    setImageLoaded(false);
    setShowDialogue(false);
    setActiveDialogueIndex(-1);
    setShowInteraction(false);

    const timer = setTimeout(() => {
      if (isPaused || audioMode === "silent") {
        if (audioMode === "silent" && !isPaused) {
          const autoTimer = setTimeout(() => advanceScene(), 5000);
          return () => clearTimeout(autoTimer);
        }
        return;
      }

      const audio = currentScene.audio;

      if (audio?.combined_url) {
        // Single combined audio file (narrator + all dialogues merged)
        play(audio.combined_url);
        // Show all dialogue bubbles at 60% through the combined audio
        const combinedDur = audio.combined_duration_ms ?? 5000;
        setTimeout(() => {
          setShowDialogue(true);
          setActiveDialogueIndex(999);
        }, Math.max(500, combinedDur * 0.6));
      } else if (audio?.narrator_url || (audio?.dialogue_urls?.length ?? 0) > 0) {
        // Fallback: queue narrator + individual dialogue files
        const queue: QueueItem[] = [];
        if (audio?.narrator_url) {
          queue.push({ url: audio.narrator_url, speaker: "narrator", duration_ms: audio.narrator_duration_ms ?? 0 });
        }
        if (audio?.dialogue_urls) {
          for (const d of audio.dialogue_urls) {
            queue.push({ url: d.url, speaker: d.speaker, duration_ms: d.duration_ms ?? 0 });
          }
        }
        playQueue(queue);
        const narratorDur = audio?.narrator_duration_ms ?? 3000;
        setTimeout(() => setShowDialogue(true), Math.max(500, narratorDur * 0.6));
      } else {
        // No audio at all — show dialogue immediately, auto-advance
        setShowDialogue(true);
        setActiveDialogueIndex(999);
        setTimeout(() => advanceScene(), 5000);
      }
    }, 300);

    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIndex]);

  // ---------------------------------------------------------------------------
  // Keyboard shortcuts
  // ---------------------------------------------------------------------------

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === "l") goToNext();
      if (e.key === "ArrowLeft" || e.key === "j") goToPrev();
      if (e.key === " ") {
        e.preventDefault();
        setIsPaused((prev) => {
          if (prev) resume();
          else audioPause();
          return !prev;
        });
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [goToNext, goToPrev, audioPause, resume]);

  // ---------------------------------------------------------------------------
  // Loading / error states
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-400">Loading presentation...</p>
        </div>
      </div>
    );
  }

  if (error || !runData || flatScenes.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center p-8 bg-red-900/20 border border-red-800 rounded-2xl max-w-md">
          <h2 className="text-xl font-bold text-red-400 mb-2">Error</h2>
          <p className="text-gray-300 text-sm">{error || "No scenes found for this run."}</p>
          <button
            onClick={() => router.push("/")}
            className="mt-4 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm"
          >
            Back to runs
          </button>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const lsIds = Object.keys(runData.scenes).sort();
  const totalLS = lsIds.length;
  const lsScenesCount = currentScene
    ? (runData.scenes[currentScene.ls_id]?.length ?? 0)
    : 0;

  // Phase color mapping
  const phaseColors: Record<string, string> = {
    HOOK: "bg-red-600/80",
    SETUP: "bg-yellow-600/80",
    CONFUSION: "bg-orange-600/80",
    DISCOVERY: "bg-green-600/80",
    GUIDANCE: "bg-blue-600/80",
    MICRO_LEARN: "bg-purple-600/80",
    VALIDATION: "bg-emerald-600/80",
    APPLICATION: "bg-cyan-600/80",
    REFLECTION: "bg-indigo-600/80",
    PAYOFF: "bg-pink-600/80",
    TRANSITION: "bg-gray-600/80",
    RESOLUTION: "bg-green-700/80",
  };

  return (
    <div className="flex flex-col min-h-screen bg-[#0f0f1a]">
      {/* Top bar */}
      <div className="flex items-center justify-between px-6 py-3 bg-black/60 backdrop-blur-sm border-b border-white/10">
        <button
          onClick={() => { stop(); router.push("/"); }}
          className="text-gray-400 hover:text-white text-sm transition-colors"
        >
          Back
        </button>

        <div className="text-center">
          <h1 className="text-sm font-semibold text-white line-clamp-1">
            {runData.config?.chapter || runId}
          </h1>
          <p className="text-xs text-gray-500">
            {runData.config?.class_level && `Class ${runData.config.class_level} · `}
            {runData.config?.subject}
          </p>
        </div>

        {/* Audio toggle */}
        <button
          onClick={() => {
            const next = audioMode === "narrator" ? "silent" : "narrator";
            setAudioMode(next);
            if (next === "silent") stop();
          }}
          className={`text-xs px-3 py-1 rounded-full transition-all ${
            audioMode === "narrator"
              ? "bg-indigo-600 text-white"
              : "bg-white/10 text-gray-400"
          }`}
        >
          {audioMode === "narrator" ? "Audio ON" : "Audio OFF"}
        </button>
      </div>

      {/* Main scene display */}
      <div className="flex-1 flex items-center justify-center p-4">
        <div className="relative w-full max-w-4xl aspect-[3/2] bg-black rounded-2xl overflow-hidden shadow-2xl">
          {/* Scene image */}
          {currentScene?.image_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={currentScene.scene_id}
              src={currentScene.image_url}
              alt={`Scene ${currentScene.scene_id}`}
              onLoad={() => setImageLoaded(true)}
              onError={() => setImageLoaded(true)}
              className={`w-full h-full object-cover transition-opacity duration-500 ${
                imageLoaded ? "opacity-100" : "opacity-0"
              }`}
            />
          )}

          {/* No image placeholder */}
          {!currentScene?.image_url && (
            <div className="w-full h-full flex items-center justify-center bg-gray-900 text-gray-600 text-lg">
              {currentScene?.scene_id} — Image not found
            </div>
          )}

          {/* Dialogue bubbles with staggered reveal */}
          <DialogueBubble
            dialogues={currentScene?.character_dialogues ?? []}
            visible={showDialogue}
            activeIndex={activeDialogueIndex}
          />

          {/* Phase badge with color */}
          {currentScene?.phase && (
            <div className={`absolute top-3 right-3 px-3 py-1 text-xs text-white rounded-full backdrop-blur-sm ${
              phaseColors[currentScene.phase] ?? "bg-gray-600/80"
            }`}>
              {currentScene.phase}
            </div>
          )}

          {/* Pause overlay */}
          {isPaused && (
            <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
              <span className="text-white text-5xl opacity-80">||</span>
            </div>
          )}

          {/* Student interaction overlay */}
          {showInteraction && currentScene?.student_interaction && (
            <InteractionOverlay
              type={currentScene.student_interaction.type ?? "think_prompt"}
              promptText={currentScene.student_interaction.prompt_text ?? ""}
              pauseSeconds={currentScene.student_interaction.pause_seconds ?? 5}
              revealText={currentScene.student_interaction.reveal_text ?? ""}
              onContinue={() => {
                setShowInteraction(false);
                advanceScene();
              }}
            />
          )}

          {/* Audio loading indicator */}
          {audioState === "loading" && (
            <div className="absolute bottom-3 right-3 w-5 h-5 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
          )}
        </div>
      </div>

      {/* Narrator text as subtitle */}
      {currentScene?.narrator_audio_text && (
        <div className="mx-auto max-w-3xl px-6 py-3 text-center">
          <p className="text-sm text-gray-400 italic leading-relaxed line-clamp-3">
            {currentScene.narrator_audio_text}
          </p>
        </div>
      )}

      {/* Progress bar */}
      <ProgressBar
        currentScene={currentScene?.scene_index ?? 0}
        totalScenes={lsScenesCount}
        currentLS={currentScene?.ls_index ?? 0}
        totalLS={totalLS}
        lsId={currentScene?.ls_id ?? ""}
      />

      {/* Navigation controls */}
      <div className="flex items-center justify-center gap-6 py-4 bg-black/40 backdrop-blur-sm">
        <button
          onClick={goToPrev}
          disabled={currentIndex === 0}
          className="w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center transition-all"
          title="Previous"
        >
          &lt;
        </button>

        <button
          onClick={() => {
            setIsPaused((prev) => {
              if (prev) resume();
              else audioPause();
              return !prev;
            });
          }}
          className="w-12 h-12 rounded-full bg-indigo-600 hover:bg-indigo-500 flex items-center justify-center transition-all shadow-lg text-lg"
          title="Pause/Resume (Space)"
        >
          {isPaused ? ">" : "||"}
        </button>

        <button
          onClick={goToNext}
          disabled={currentIndex === flatScenes.length - 1}
          className="w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center transition-all"
          title="Next"
        >
          &gt;
        </button>
      </div>

      {/* Scene counter */}
      <div className="text-center text-xs text-gray-600 pb-3">
        Scene {currentIndex + 1} / {flatScenes.length} ·{" "}
        <span className="text-gray-500">Space=pause, arrows=navigate</span>
      </div>
    </div>
  );
}
