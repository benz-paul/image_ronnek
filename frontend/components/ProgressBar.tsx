"use client";

interface ProgressBarProps {
  currentScene: number;
  totalScenes: number;
  currentLS: number;
  totalLS: number;
  lsId: string;
}

export default function ProgressBar({
  currentScene,
  totalScenes,
  currentLS,
  totalLS,
  lsId,
}: ProgressBarProps) {
  const scenePercent = totalScenes > 0 ? ((currentScene + 1) / totalScenes) * 100 : 0;
  const overallPercent =
    totalScenes > 0 && totalLS > 0
      ? ((currentLS * totalScenes + currentScene + 1) / (totalLS * totalScenes)) * 100
      : 0;

  return (
    <div className="w-full px-6 py-3 bg-black/40 backdrop-blur-sm">
      {/* LS label */}
      <div className="flex justify-between items-center text-xs text-gray-400 mb-1">
        <span>
          {lsId} · Scene {currentScene + 1} / {totalScenes}
        </span>
        <span>
          Step {currentLS + 1} / {totalLS}
        </span>
      </div>

      {/* Scene progress within LS */}
      <div className="h-1.5 bg-white/10 rounded-full overflow-hidden mb-1">
        <div
          className="h-full bg-indigo-500 progress-bar rounded-full"
          style={{ width: `${scenePercent}%` }}
        />
      </div>

      {/* Overall progress across all LS */}
      <div className="h-0.5 bg-white/5 rounded-full overflow-hidden">
        <div
          className="h-full bg-indigo-800/60 progress-bar rounded-full"
          style={{ width: `${overallPercent}%` }}
        />
      </div>
    </div>
  );
}
