"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type AudioState = "idle" | "loading" | "playing" | "paused" | "ended" | "error";

interface UseAudioPlayerOptions {
  onEnded?: () => void;
}

export function useAudioPlayer({ onEnded }: UseAudioPlayerOptions = {}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [state, setState] = useState<AudioState>("idle");
  const [currentUrl, setCurrentUrl] = useState<string | null>(null);

  // Create audio element once
  useEffect(() => {
    const audio = new Audio();
    audioRef.current = audio;

    audio.addEventListener("ended", () => {
      setState("ended");
      onEnded?.();
    });
    audio.addEventListener("error", () => setState("error"));
    audio.addEventListener("playing", () => setState("playing"));
    audio.addEventListener("pause", () => setState("paused"));
    audio.addEventListener("waiting", () => setState("loading"));

    return () => {
      audio.pause();
      audio.src = "";
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const play = useCallback((url: string) => {
    const audio = audioRef.current;
    if (!audio) return;

    if (url === currentUrl && state === "paused") {
      audio.play().catch(console.error);
      return;
    }

    audio.pause();
    audio.src = url;
    setCurrentUrl(url);
    setState("loading");
    audio.play().catch((e) => {
      console.error("[AudioPlayer] play error:", e);
      setState("error");
    });
  }, [currentUrl, state]);

  const pause = useCallback(() => {
    audioRef.current?.pause();
  }, []);

  const stop = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    audio.currentTime = 0;
    setState("idle");
  }, []);

  return { play, pause, stop, state, currentUrl };
}
