"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import DialogueBubble from "@/components/DialogueBubble";
import ProgressBar from "@/components/ProgressBar";
import { useAudioPlayer } from "@/hooks/useAudioPlayer";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CharacterDialogue {
  character_id: string;
  voice_id: string;
  dialogue: string;
  audio_text?: string;
}

interface SceneAudio {
  narrator_url: string | null;
  characters: Record<string, string>;
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
  const [isPaused, setIsPaused] = useState(false);
  const [audioMode, setAudioMode] = useState<"narrator" | "silent">("narrator");

  // Audio: advances to next scene when narrator ends
  const handleAudioEnded = useCallback(() => {
    if (!isPaused) {
      advanceScene();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPaused, currentIndex, flatScenes.length]);

  const { play, pause, stop, state: audioState } = useAudioPlayer({
    onEnded: handleAudioEnded,
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

  const advanceScene = useCallback(() => {
    setCurrentIndex((prev) => {
      if (prev < flatScenes.length - 1) return prev + 1;
      return prev; // Stay on last scene
    });
  }, [flatScenes.length]);

  const goToPrev = useCallback(() => {
    stop();
    setCurrentIndex((prev) => Math.max(0, prev - 1));
  }, [stop]);

  const goToNext = useCallback(() => {
    stop();
    advanceScene();
  }, [stop, advanceScene]);

  // ---------------------------------------------------------------------------
  // When scene changes: reset UI and play narrator audio
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!currentScene) return;
    setImageLoaded(false);
    setShowDialogue(false);

    // Play narrator audio after a short delay (allows image to start loading)
    const timer = setTimeout(() => {
      const narratorUrl = currentScene.audio?.narrator_url;
      if (narratorUrl && audioMode === "narrator" && !isPaused) {
        play(narratorUrl);
        // Show dialogue bubbles 1s after narrator starts
        setTimeout(() => setShowDialogue(true), 1000);
      } else {
        // No audio → auto-advance after 5s
        if (!isPaused && audioMode === "silent") {
          const autoTimer = setTimeout(() => advanceScene(), 5000);
          return () => clearTimeout(autoTimer);
        }
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
          if (prev) {
            // Resume
            const narratorUrl = currentScene?.audio?.narrator_url;
            if (narratorUrl) play(narratorUrl);
          } else {
            pause();
          }
          return !prev;
        });
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [goToNext, goToPrev, currentScene, play, pause]);

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
            ← Back to runs
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

  return (
    <div className="flex flex-col min-h-screen bg-[#0f0f1a]">
      {/* Top bar */}
      <div className="flex items-center justify-between px-6 py-3 bg-black/60 backdrop-blur-sm border-b border-white/10">
        <button
          onClick={() => { stop(); router.push("/"); }}
          className="text-gray-400 hover:text-white text-sm transition-colors"
        >
          ← Back
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
          {audioMode === "narrator" ? "🔊 Audio" : "🔇 Silent"}
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
              className={`w-full h-full object-cover scene-image ${imageLoaded ? "loaded" : "loading"}`}
            />
          )}

          {/* No image placeholder */}
          {!currentScene?.image_url && (
            <div className="w-full h-full flex items-center justify-center bg-gray-900 text-gray-600 text-lg">
              {currentScene?.scene_id} — Image not found
            </div>
          )}

          {/* Dialogue bubbles */}
          <DialogueBubble
            dialogues={currentScene?.character_dialogues ?? []}
            visible={showDialogue}
          />

          {/* Phase badge */}
          {currentScene?.phase && (
            <div className="absolute top-3 right-3 px-2 py-1 text-xs bg-black/70 text-indigo-300 rounded-full backdrop-blur-sm">
              {currentScene.phase}
            </div>
          )}

          {/* Pause overlay */}
          {isPaused && (
            <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
              <span className="text-white text-5xl opacity-80">⏸</span>
            </div>
          )}

          {/* Audio loading indicator */}
          {audioState === "loading" && (
            <div className="absolute bottom-3 right-3 w-5 h-5 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
          )}
        </div>
      </div>

      {/* Narrator text */}
      {currentScene?.narrator_audio_text && (
        <div className="mx-auto max-w-3xl px-6 py-3 text-center text-sm text-gray-400 italic line-clamp-2">
          {currentScene.narrator_audio_text}
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
          title="Previous (← or J)"
        >
          ◀
        </button>

        {/* Pause/Resume */}
        <button
          onClick={() => {
            setIsPaused((prev) => {
              if (prev) {
                const url = currentScene?.audio?.narrator_url;
                if (url) play(url);
              } else {
                pause();
              }
              return !prev;
            });
          }}
          className="w-12 h-12 rounded-full bg-indigo-600 hover:bg-indigo-500 flex items-center justify-center transition-all shadow-lg"
          title="Pause/Resume (Space)"
        >
          {isPaused ? "▶" : "⏸"}
        </button>

        <button
          onClick={goToNext}
          disabled={currentIndex === flatScenes.length - 1}
          className="w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center transition-all"
          title="Next (→ or L)"
        >
          ▶
        </button>
      </div>

      {/* Scene counter */}
      <div className="text-center text-xs text-gray-600 pb-3">
        Scene {currentIndex + 1} / {flatScenes.length} ·{" "}
        <span className="text-gray-500">Space=pause · ←→=navigate</span>
      </div>
    </div>
  );
}
