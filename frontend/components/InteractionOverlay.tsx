"use client";

import { useCallback, useEffect, useState } from "react";

interface InteractionOverlayProps {
  type: string; // "think_prompt" | "prediction" | "mini_quiz"
  promptText: string;
  pauseSeconds: number;
  revealText: string;
  onContinue: () => void;
}

export default function InteractionOverlay({
  type,
  promptText,
  pauseSeconds,
  revealText,
  onContinue,
}: InteractionOverlayProps) {
  const [countdown, setCountdown] = useState(pauseSeconds);
  const [showReveal, setShowReveal] = useState(false);

  useEffect(() => {
    if (countdown <= 0) {
      setShowReveal(true);
      return;
    }
    const timer = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const typeLabel =
    type === "think_prompt"
      ? "Think About It..."
      : type === "prediction"
      ? "Make a Prediction!"
      : "Quick Quiz!";

  const typeColor =
    type === "think_prompt"
      ? "from-indigo-600 to-purple-700"
      : type === "prediction"
      ? "from-amber-600 to-orange-700"
      : "from-emerald-600 to-teal-700";

  return (
    <div className="absolute inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 animate-fadeIn">
      <div className={`max-w-lg w-full mx-4 rounded-2xl p-8 bg-gradient-to-br ${typeColor} shadow-2xl`}>
        {/* Type label */}
        <p className="text-white/70 text-xs font-bold uppercase tracking-widest mb-2">
          {typeLabel}
        </p>

        {/* Question */}
        <h2 className="text-white text-xl font-bold leading-snug mb-6">
          {promptText}
        </h2>

        {/* Countdown or Reveal */}
        {!showReveal ? (
          <div className="text-center">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-white/20 mb-3">
              <span className="text-3xl font-bold text-white">{countdown}</span>
            </div>
            <p className="text-white/60 text-sm">Take a moment to think...</p>
          </div>
        ) : (
          <div className="animate-fadeIn">
            <div className="bg-white/15 rounded-xl p-4 mb-4">
              <p className="text-white text-base font-medium leading-relaxed">
                {revealText}
              </p>
            </div>
            <button
              onClick={onContinue}
              className="w-full py-3 bg-white/20 hover:bg-white/30 text-white font-semibold rounded-xl transition-all"
            >
              Continue &rarr;
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
