"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type AudioState = "idle" | "loading" | "playing" | "paused" | "ended" | "error";

export interface QueueItem {
  url: string;
  speaker?: string;
  duration_ms?: number;
}

interface UseAudioPlayerOptions {
  onEnded?: () => void;
  onSegmentStart?: (index: number, speaker: string) => void;
  onQueueEnd?: () => void;
}

export function useAudioPlayer({
  onEnded,
  onSegmentStart,
  onQueueEnd,
}: UseAudioPlayerOptions = {}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [state, setState] = useState<AudioState>("idle");
  const [currentUrl, setCurrentUrl] = useState<string | null>(null);
  const queueRef = useRef<QueueItem[]>([]);
  const queueIndexRef = useRef(-1);
  const isPausedRef = useRef(false);

  // Create audio element once
  useEffect(() => {
    const audio = new Audio();
    audioRef.current = audio;

    const handleEnded = () => {
      setState("ended");
      onEnded?.();
      // If queue has more items, play next
      const nextIdx = queueIndexRef.current + 1;
      if (nextIdx < queueRef.current.length && !isPausedRef.current) {
        _playQueueItem(nextIdx);
      } else if (nextIdx >= queueRef.current.length) {
        queueIndexRef.current = -1;
        queueRef.current = [];
        onQueueEnd?.();
      }
    };

    audio.addEventListener("ended", handleEnded);
    audio.addEventListener("error", () => setState("error"));
    audio.addEventListener("playing", () => setState("playing"));
    audio.addEventListener("pause", () => {
      if (!isPausedRef.current) return; // ignore pause from src change
      setState("paused");
    });
    audio.addEventListener("waiting", () => setState("loading"));

    return () => {
      audio.pause();
      audio.src = "";
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const _playQueueItem = useCallback(
    (index: number) => {
      const audio = audioRef.current;
      if (!audio || index >= queueRef.current.length) return;

      const item = queueRef.current[index];
      queueIndexRef.current = index;

      audio.pause();
      audio.src = item.url;
      setCurrentUrl(item.url);
      setState("loading");

      onSegmentStart?.(index, item.speaker ?? "narrator");

      audio.play().catch((e) => {
        console.error("[AudioPlayer] play error:", e);
        setState("error");
      });
    },
    [onSegmentStart]
  );

  /** Play a single URL (backwards compatible). */
  const play = useCallback(
    (url: string) => {
      queueRef.current = [{ url, speaker: "narrator" }];
      queueIndexRef.current = -1;
      isPausedRef.current = false;
      _playQueueItem(0);
    },
    [_playQueueItem]
  );

  /** Play an ordered queue: narrator first, then dialogues. */
  const playQueue = useCallback(
    (items: QueueItem[]) => {
      if (items.length === 0) return;
      queueRef.current = items;
      queueIndexRef.current = -1;
      isPausedRef.current = false;
      _playQueueItem(0);
    },
    [_playQueueItem]
  );

  const pause = useCallback(() => {
    isPausedRef.current = true;
    audioRef.current?.pause();
    setState("paused");
  }, []);

  const resume = useCallback(() => {
    isPausedRef.current = false;
    audioRef.current?.play().catch(console.error);
  }, []);

  const stop = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    isPausedRef.current = false;
    audio.pause();
    audio.currentTime = 0;
    queueRef.current = [];
    queueIndexRef.current = -1;
    setState("idle");
  }, []);

  return {
    play,
    playQueue,
    pause,
    resume,
    stop,
    state,
    currentUrl,
    queueIndex: queueIndexRef.current,
  };
}
