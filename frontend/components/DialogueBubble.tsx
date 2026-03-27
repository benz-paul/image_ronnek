"use client";

import { useMemo } from "react";

interface CharacterDialogue {
  character_id: string;
  voice_id: string;
  dialogue: string;
  audio_text?: string;
}

interface DialogueBubbleProps {
  dialogues: CharacterDialogue[];
  visible: boolean;
  activeIndex?: number; // -1 = show none, 999 = show all, N = show up to N
}

// Per-character color palette (deterministic by character_id)
const CHAR_COLORS = [
  { bg: "bg-blue-900/90", border: "border-blue-400/60", text: "text-blue-100", label: "text-blue-300" },
  { bg: "bg-rose-900/90", border: "border-rose-400/60", text: "text-rose-100", label: "text-rose-300" },
  { bg: "bg-emerald-900/90", border: "border-emerald-400/60", text: "text-emerald-100", label: "text-emerald-300" },
  { bg: "bg-amber-900/90", border: "border-amber-400/60", text: "text-amber-100", label: "text-amber-300" },
  { bg: "bg-violet-900/90", border: "border-violet-400/60", text: "text-violet-100", label: "text-violet-300" },
  { bg: "bg-cyan-900/90", border: "border-cyan-400/60", text: "text-cyan-100", label: "text-cyan-300" },
];

// Display name mapping
const DISPLAY_NAMES: Record<string, string> = {
  mrchen: "Mr. Chen",
  mr_chen: "Mr. Chen",
  mraris: "Mr. Aris",
  mr_aris: "Mr. Aris",
};

function displayName(id: string): string {
  const key = id.toLowerCase().replace(/\s+/g, "");
  if (DISPLAY_NAMES[key]) return DISPLAY_NAMES[key];
  // Title-case
  return id
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function hashCharColor(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = ((h << 5) - h + id.charCodeAt(i)) | 0;
  return Math.abs(h) % CHAR_COLORS.length;
}

export default function DialogueBubble({
  dialogues,
  visible,
  activeIndex = 999,
}: DialogueBubbleProps) {
  if (!visible || !dialogues || dialogues.length === 0) return null;

  // Build color map (deterministic per character)
  const colorMap = useMemo(() => {
    const map: Record<string, typeof CHAR_COLORS[0]> = {};
    dialogues.forEach((d) => {
      const key = d.character_id.toLowerCase();
      if (!map[key]) {
        map[key] = CHAR_COLORS[hashCharColor(key)];
      }
    });
    return map;
  }, [dialogues]);

  // Only show up to activeIndex+1 dialogues
  const visibleDialogues = dialogues.filter((_, i) => i <= activeIndex);

  return (
    <div className="absolute bottom-0 left-0 right-0 pointer-events-none flex flex-wrap justify-start items-end p-3 gap-2">
      {visibleDialogues.map((d, i) => {
        const colors = colorMap[d.character_id.toLowerCase()] ?? CHAR_COLORS[0];
        const isActive = i === activeIndex && activeIndex < 999;

        return (
          <div
            key={`${d.character_id}-${i}`}
            className={`
              max-w-[260px] px-3 py-2 rounded-xl border backdrop-blur-md
              text-sm font-medium shadow-lg
              ${colors.bg} ${colors.border} ${colors.text}
              transition-all duration-300
              ${isActive ? "ring-2 ring-white/40 scale-[1.02]" : ""}
              animate-slideUp
            `}
            style={{ animationDelay: `${i * 200}ms`, animationFillMode: "backwards" }}
          >
            <span className={`text-xs font-bold block mb-0.5 ${colors.label}`}>
              {displayName(d.character_id)}
            </span>
            <span className="leading-snug">&ldquo;{d.dialogue}&rdquo;</span>
          </div>
        );
      })}
    </div>
  );
}
