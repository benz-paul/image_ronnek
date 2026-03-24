"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

interface RunSummary {
  run_id: string;
  timestamp: string;
  chapter: string;
  subject: string;
  class_level: string;
  image_model: string;
  image_count: number;
  audio_count: number;
  has_audio: boolean;
  has_ppt: boolean;
}

export default function HomePage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    fetch("/api/runs")
      .then((r) => r.json())
      .then((data) => {
        setRuns(data);
        setLoading(false);
      })
      .catch((e) => {
        setError("Could not connect to backend. Make sure uvicorn is running on port 8000.");
        setLoading(false);
      });
  }, []);

  const formatTimestamp = (ts: string) => {
    if (!ts) return "";
    // YYYYMMDD_HHMMSS → readable date
    const match = ts.match(/(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
    if (!match) return ts;
    const [, y, mo, d, h, mi] = match;
    return `${d}/${mo}/${y} ${h}:${mi}`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-400">Loading presentations...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="max-w-md text-center p-8 bg-red-900/20 border border-red-800 rounded-2xl">
          <h2 className="text-xl font-bold text-red-400 mb-2">Connection Error</h2>
          <p className="text-gray-300 text-sm">{error}</p>
          <code className="block mt-4 text-xs bg-black/40 p-3 rounded text-green-400">
            uvicorn backend.server:app --port 8000 --reload
          </code>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen p-8">
      {/* Header */}
      <div className="max-w-6xl mx-auto">
        <div className="mb-10">
          <h1 className="text-3xl font-bold text-white mb-2">
            📚 Storytelling Pipeline
          </h1>
          <p className="text-gray-400">
            Select a presentation to start the interactive slideshow
          </p>
        </div>

        {runs.length === 0 ? (
          <div className="text-center py-20 text-gray-500">
            <p className="text-xl mb-2">No presentations found</p>
            <p className="text-sm">Run the pipeline first to generate content</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {runs.map((run) => (
              <button
                key={run.run_id}
                onClick={() => router.push(`/player/${run.run_id}`)}
                className="text-left p-6 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-indigo-500/50 rounded-2xl transition-all duration-200 group"
              >
                {/* Chapter info */}
                <div className="mb-4">
                  <h2 className="text-lg font-semibold text-white group-hover:text-indigo-300 transition-colors line-clamp-2">
                    {run.chapter || run.run_id}
                  </h2>
                  <p className="text-sm text-gray-400 mt-1">
                    {run.subject && run.class_level
                      ? `Class ${run.class_level} · ${run.subject}`
                      : run.run_id}
                  </p>
                  <p className="text-xs text-gray-600 mt-1">
                    {formatTimestamp(run.timestamp)}
                  </p>
                </div>

                {/* Stats */}
                <div className="flex flex-wrap gap-2">
                  <span className="px-2 py-1 text-xs bg-indigo-900/50 text-indigo-300 rounded-full">
                    🖼 {run.image_count} images
                  </span>
                  {run.has_audio ? (
                    <span className="px-2 py-1 text-xs bg-green-900/50 text-green-300 rounded-full">
                      🔊 {run.audio_count} audio
                    </span>
                  ) : (
                    <span className="px-2 py-1 text-xs bg-gray-800 text-gray-500 rounded-full">
                      🔇 no audio
                    </span>
                  )}
                  {run.has_ppt && (
                    <span className="px-2 py-1 text-xs bg-orange-900/50 text-orange-300 rounded-full">
                      📊 PPT
                    </span>
                  )}
                </div>

                {/* Model badge */}
                {run.image_model && (
                  <p className="text-xs text-gray-600 mt-3">{run.image_model}</p>
                )}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
