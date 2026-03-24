"use client";

interface CharacterDialogue {
  character_id: string;
  voice_id: string;
  dialogue: string;
  audio_text?: string;
}

interface DialogueBubbleProps {
  dialogues: CharacterDialogue[];
  visible: boolean;
}

const BUBBLE_COLORS = [
  "bg-indigo-900/90 border-indigo-400/60 text-indigo-100",
  "bg-violet-900/90 border-violet-400/60 text-violet-100",
  "bg-cyan-900/90 border-cyan-400/60 text-cyan-100",
  "bg-emerald-900/90 border-emerald-400/60 text-emerald-100",
];

export default function DialogueBubble({ dialogues, visible }: DialogueBubbleProps) {
  if (!visible || !dialogues || dialogues.length === 0) return null;

  return (
    <div className="absolute inset-0 pointer-events-none flex flex-col justify-end p-4 gap-2">
      {dialogues.map((d, i) => (
        <div
          key={i}
          className={`dialogue-bubble max-w-xs px-4 py-2 rounded-2xl border backdrop-blur-sm text-sm font-medium shadow-lg ${BUBBLE_COLORS[i % BUBBLE_COLORS.length]}`}
          style={{ animationDelay: `${i * 150}ms` }}
        >
          <span className="text-xs opacity-60 block mb-1 capitalize">
            {d.character_id.replace(/_/g, " ")}
          </span>
          "{d.dialogue}"
        </div>
      ))}
    </div>
  );
}
