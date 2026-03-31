"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { LatestRunButton } from "@/components/LatestRunButton";

// ─── Types ───────────────────────────────────────────────────────────────────

type Step = "upload" | "generating" | "done";
type ExpressionKey = "neutral" | "happy" | "sad" | "angry" | "surprised" | "talking_open" | "talking_closed";

interface AvatarJson {
  avatar_id: string;
  name: string;
  version: string;
  visual: {
    base_face: string;
    expressions: Record<string, string | null>;
    style: { type: string };
  };
  voice: { engine: string; voice_id: string };
  character: { personality: string };
  metadata: { status: string };
}

// ─── Step indicator ───────────────────────────────────────────────────────────

function StepIndicator({ current }: { current: 1 | 2 | 3 }) {
  const steps = [
    { n: 1, label: "Create Account",  icon: "person_add" },
    { n: 2, label: "Upload Photos",   icon: "photo_camera" },
    { n: 3, label: "Generate Avatar", icon: "auto_awesome" },
  ];
  return (
    <div className="flex items-center gap-0 mb-10">
      {steps.map((s, i) => (
        <div key={s.n} className="flex items-center">
          <div className={`flex flex-col items-center gap-1 ${s.n <= current ? "opacity-100" : "opacity-30"}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center border text-xs font-headline font-bold transition-all ${
              s.n < current  ? "bg-primary/30 border-primary text-primary" :
              s.n === current ? "bg-primary border-primary text-on-primary shadow-[0_0_12px_rgba(161,250,255,0.5)]" :
                               "bg-surface-container-highest border-outline-variant text-on-surface-variant"
            }`}>
              {s.n < current
                ? <span className="material-symbols-outlined text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>check</span>
                : s.n}
            </div>
            <span className="font-label text-[9px] tracking-widest uppercase text-on-surface-variant whitespace-nowrap hidden sm:block">
              {s.label}
            </span>
          </div>
          {i < steps.length - 1 && (
            <div className={`w-12 sm:w-20 h-px mx-1 transition-all ${s.n < current ? "bg-primary/50" : "bg-outline-variant/30"}`} />
          )}
        </div>
      ))}
    </div>
  );
}

// ─── Photo upload slot ────────────────────────────────────────────────────────

function PhotoSlot({
  label, icon, file, onSelect, onRemove,
}: {
  label: string; icon: string; file: File | null;
  onSelect: (f: File) => void; onRemove: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const preview = file ? URL.createObjectURL(file) : null;

  return (
    <div className="relative aspect-square">
      {preview ? (
        <div className="w-full h-full rounded border border-primary/40 overflow-hidden relative group">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={preview} alt={label} className="w-full h-full object-cover" />
          <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
            <button onClick={onRemove} className="text-error">
              <span className="material-symbols-outlined text-2xl">delete</span>
            </button>
          </div>
          <div className="absolute bottom-0 inset-x-0 py-1 bg-surface-container-highest/80 backdrop-blur-sm">
            <p className="font-label text-[9px] tracking-wider uppercase text-primary text-center">{label}</p>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="w-full h-full rounded border-2 border-dashed border-outline-variant/40 hover:border-primary/50 bg-surface-container/50 hover:bg-primary/5 flex flex-col items-center justify-center gap-2 transition-all group"
        >
          <span className="material-symbols-outlined text-3xl text-on-surface-variant/40 group-hover:text-primary transition-colors">{icon}</span>
          <p className="font-label text-[9px] tracking-wider uppercase text-on-surface-variant/50 group-hover:text-primary transition-colors">{label}</p>
        </button>
      )}
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => { if (e.target.files?.[0]) onSelect(e.target.files[0]); }}
      />
    </div>
  );
}

// ─── Avatar preview ───────────────────────────────────────────────────────────

function AvatarPreview({
  avatar, activeExpr, onExprChange,
}: {
  avatar: AvatarJson; activeExpr: ExpressionKey; onExprChange: (e: ExpressionKey) => void;
}) {
  const expressions: { key: ExpressionKey; icon: string; label: string }[] = [
    { key: "neutral",  icon: "sentiment_neutral",    label: "Neutral"  },
    { key: "happy",    icon: "sentiment_very_satisfied", label: "Happy"  },
    { key: "sad",      icon: "sentiment_dissatisfied", label: "Sad"     },
    { key: "angry",    icon: "mood_bad",              label: "Angry"   },
    { key: "surprised",icon: "sentiment_excited",     label: "Surprised"},
    { key: "talking_open", icon: "record_voice_over", label: "Talking" },
  ];

  const imgUrl = avatar.visual.expressions[activeExpr] || avatar.visual.base_face;

  return (
    <div className="flex flex-col items-center gap-4">
      {/* Avatar display */}
      <div className="relative w-64 h-64 rounded-lg border border-primary/20 overflow-hidden bg-surface-container-lowest shadow-[0_0_40px_rgba(161,250,255,0.1)]">
        {imgUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={imgUrl}
            src={imgUrl}
            alt={`Avatar ${activeExpr}`}
            className="w-full h-full object-contain animate-fadeIn"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center digital-grid">
            <span className="material-symbols-outlined text-6xl text-on-surface-variant/20" style={{ fontVariationSettings: "'FILL' 1" }}>
              face
            </span>
          </div>
        )}
        {/* Scanline overlay */}
        <div className="absolute inset-0 scanline opacity-10 pointer-events-none" />
        {/* Status badge */}
        <div className="absolute top-3 right-3 px-2 py-0.5 bg-surface-container-highest/80 backdrop-blur-sm rounded font-label text-[9px] tracking-widest uppercase text-primary border border-primary/20">
          {activeExpr.replace("_", " ")}
        </div>
      </div>

      {/* Avatar name + type */}
      <div className="text-center">
        <p className="font-headline font-bold text-lg tracking-tight text-on-surface">{avatar.name}</p>
        <p className="font-label text-[10px] tracking-widest uppercase text-primary/60">{avatar.visual.style.type}</p>
      </div>

      {/* Expression switcher */}
      <div className="flex gap-2 flex-wrap justify-center">
        {expressions.map(({ key, icon, label }) => (
          <button
            key={key}
            onClick={() => onExprChange(key)}
            title={label}
            className={`w-9 h-9 rounded flex items-center justify-center border transition-all ${
              activeExpr === key
                ? "bg-primary text-on-primary border-primary shadow-[0_0_10px_rgba(161,250,255,0.4)]"
                : "bg-surface-container border-outline-variant/20 text-on-surface-variant hover:border-primary/40 hover:text-primary"
            }`}
          >
            <span className="material-symbols-outlined text-lg">{icon}</span>
          </button>
        ))}
      </div>

      {/* Voice info */}
      <div className="w-full bg-surface-container/60 rounded border border-outline-variant/10 px-4 py-3 space-y-1.5">
        <p className="font-label text-[9px] tracking-widest uppercase text-on-surface-variant/50">Voice Config</p>
        <div className="flex justify-between">
          <span className="font-label text-[10px] text-on-surface-variant">Engine</span>
          <span className="font-label text-[10px] text-primary uppercase">{avatar.voice.engine} / {avatar.voice.voice_id}</span>
        </div>
        <div className="flex justify-between">
          <span className="font-label text-[10px] text-on-surface-variant">Personality</span>
          <span className="font-label text-[10px] text-primary/80 text-right max-w-[60%] truncate">{avatar.character.personality}</span>
        </div>
        <div className="flex justify-between">
          <span className="font-label text-[10px] text-on-surface-variant">Status</span>
          <span className="font-label text-[10px] text-green-400 uppercase">{avatar.metadata.status}</span>
        </div>
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function AvatarPageInner({ editMode = false }: { editMode?: boolean }) {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const usernameParam = searchParams.get("username") || user?.username || "";
  const nameParam = searchParams.get("name") || user?.displayName || "";

  const [step, setStep] = useState<Step>("upload");
  const [slots, setSlots] = useState<(File | null)[]>([null, null, null, null]);
  const [extraFiles, setExtraFiles] = useState<File[]>([]);
  const [progress, setProgress] = useState<string[]>([]);
  const [avatar, setAvatar] = useState<AvatarJson | null>(null);
  const [activeExpr, setActiveExpr] = useState<ExpressionKey>("neutral");
  const [genError, setGenError] = useState("");
  const extraInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!authLoading && !user) router.replace("/");
  }, [authLoading, user, router]);

  // If editing, try loading existing avatar
  useEffect(() => {
    if (editMode && usernameParam) {
      fetch(`/api/avatar/${usernameParam}`)
        .then((r) => r.ok ? r.json() : null)
        .then((data) => { if (data) setAvatar(data); })
        .catch(() => {});
    }
  }, [editMode, usernameParam]);

  const allFiles = [...slots.filter(Boolean) as File[], ...extraFiles];
  const hasEnoughPhotos = allFiles.length >= 1;

  function setSlotFile(i: number, f: File) { setSlots((s) => { const n=[...s]; n[i]=f; return n; }); }
  function clearSlot(i: number) { setSlots((s) => { const n=[...s]; n[i]=null; return n; }); }

  async function handleGenerate() {
    if (!hasEnoughPhotos) return;
    setStep("generating");
    setGenError("");
    setProgress(["Uploading reference photos..."]);

    const formData = new FormData();
    formData.append("username", usernameParam);
    allFiles.forEach((f) => formData.append("photos", f));

    try {
      setProgress((p) => [...p, "Generating semi-realistic anime avatar with Flux Kontext..."]);
      const res = await fetch("/api/avatar/generate", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Generation failed");

      setProgress((p) => [...p, "Generating expressions: neutral, talking...", "Polishing remaining expressions in background...", "Finalising avatar..."]);
      setAvatar(data.avatar_json);
      setStep("done");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setGenError(message);
      setStep("upload");
    }
  }

  if (authLoading || !user) return null;

  const isEdit = editMode || searchParams.get("edit") === "1";

  return (
    <div className="min-h-screen flex flex-col bg-background overflow-x-hidden">
      {/* Ambient */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        <div className="absolute inset-0 digital-grid opacity-40" />
        <div className="absolute top-[-5%] right-[-5%] w-[40%] h-[40%] bg-primary/6 blur-[150px] rounded-full" />
        <div className="absolute bottom-[-5%] left-[-5%] w-[30%] h-[30%] bg-secondary/6 blur-[120px] rounded-full" />
      </div>

      {/* Header */}
      <header className="relative z-10 flex items-center justify-between px-6 py-4 bg-[#0e0e13] border-b border-outline-variant/10 shrink-0">
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-primary" style={{ fontVariationSettings: "'FILL' 1" }}>terminal</span>
          <span className="font-headline font-bold text-xl tracking-tighter text-primary uppercase hidden sm:block">AI DECODER ACADEMY</span>
        </div>
        <div className="flex items-center gap-3">
          <LatestRunButton compact />
          {isEdit && (
            <button onClick={() => router.push("/dashboard")} className="font-label text-xs tracking-widest uppercase text-on-surface-variant hover:text-primary transition-colors flex items-center gap-1">
              <span className="material-symbols-outlined text-sm">arrow_back</span>
              Dashboard
            </button>
          )}
          <div className="px-3 py-1 bg-surface-container-highest rounded border border-outline-variant/20">
            <span className="font-label text-[10px] tracking-widest text-primary uppercase">
              {isEdit ? "Edit Avatar" : step === "done" ? "Step 3 of 3" : "Step 2 of 3"}
            </span>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="relative z-10 flex-1 max-w-6xl w-full mx-auto px-6 py-10">

        {!isEdit && <StepIndicator current={step === "done" ? 3 : 2} />}

        {/* Title row */}
        <div className="flex items-end justify-between mb-10">
          <div>
            <p className="font-label text-[10px] tracking-[0.3em] uppercase text-primary/60 mb-2">
              {isEdit ? "Modify Protocol / Update Agent" : "Initialize Protocol / Phase 02"}
            </p>
            <h2 className="font-headline text-4xl font-bold tracking-tight uppercase leading-none">
              {isEdit ? "Edit Your" : step === "done" ? "Agent" : "Create Your"}
              <br /><span className="text-primary">Digital Agent</span>
            </h2>
          </div>
          <div className="hidden md:block text-right font-label text-[10px] tracking-widest uppercase text-on-surface-variant/40">
            <div>ID: {usernameParam}</div>
            <div>Model: flux-2-pro</div>
          </div>
        </div>

        {/* ── DONE STATE: Show avatar ── */}
        {step === "done" && avatar && (
          <div className="flex flex-col lg:flex-row gap-8">
            {/* Avatar preview */}
            <div className="lg:w-80 shrink-0">
              <AvatarPreview avatar={avatar} activeExpr={activeExpr} onExprChange={setActiveExpr} />
            </div>

            {/* Right: actions */}
            <div className="flex-1 space-y-6">
              <div className="p-6 bg-surface-container-low rounded-lg border border-primary/15">
                <div className="flex items-center gap-3 mb-4">
                  <span className="material-symbols-outlined text-primary text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>check_circle</span>
                  <div>
                    <h3 className="font-headline font-bold tracking-tight">Avatar Generated Successfully</h3>
                    <p className="font-label text-[10px] tracking-widest uppercase text-primary/60">ID: {avatar.avatar_id}</p>
                  </div>
                </div>
                <p className="font-body text-sm text-on-surface-variant leading-relaxed mb-4">
                  Your digital agent is ready with {Object.values(avatar.visual.expressions).filter(Boolean).length} expressions.
                  Use the buttons below to switch expressions or head to the dashboard.
                </p>

                {/* JSON viewer */}
                <details className="group">
                  <summary className="font-label text-[10px] tracking-widest uppercase text-on-surface-variant/60 cursor-pointer hover:text-primary transition-colors flex items-center gap-2">
                    <span className="material-symbols-outlined text-sm group-open:rotate-90 transition-transform">chevron_right</span>
                    View Avatar JSON
                  </summary>
                  <pre className="mt-3 text-[10px] font-mono text-primary/80 bg-surface-container-lowest rounded p-4 overflow-auto max-h-64 border border-outline-variant/20">
                    {JSON.stringify(avatar, null, 2)}
                  </pre>
                </details>
              </div>

              <div className="flex flex-col sm:flex-row gap-3">
                <button
                  onClick={() => router.push("/dashboard")}
                  className="flex-1 py-4 bg-gradient-to-r from-primary to-primary-container text-on-primary font-headline font-bold uppercase tracking-widest rounded hover:opacity-90 transition-all flex items-center justify-center gap-2"
                >
                  <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 1" }}>dashboard</span>
                  Enter Academy
                </button>
                <button
                  onClick={() => { setStep("upload"); setSlots([null,null,null,null]); setExtraFiles([]); setAvatar(null); }}
                  className="flex-1 py-4 bg-surface-container border border-outline-variant/30 hover:border-primary/40 text-on-surface font-headline font-bold uppercase tracking-widest rounded transition-all flex items-center justify-center gap-2"
                >
                  <span className="material-symbols-outlined">refresh</span>
                  Regenerate
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── UPLOAD STATE ── */}
        {(step === "upload") && (
          <div className="flex flex-col lg:flex-row gap-8">

            {/* Left: Avatar preview (edit mode shows existing) */}
            {isEdit && avatar && (
              <div className="lg:w-72 shrink-0">
                <p className="font-label text-[10px] tracking-widest uppercase text-on-surface-variant/60 mb-4">Current Avatar</p>
                <AvatarPreview avatar={avatar} activeExpr={activeExpr} onExprChange={setActiveExpr} />
                <p className="font-body text-xs text-on-surface-variant/60 mt-4 leading-relaxed">
                  Upload new photos below to regenerate your avatar. Your current avatar will be replaced.
                </p>
              </div>
            )}

            {/* Right (or full-width in registration): Upload zone */}
            <div className="flex-1 space-y-8">

              {/* Required angle slots */}
              <div>
                <p className="font-label text-[10px] tracking-widest uppercase text-on-surface-variant/60 mb-4 flex items-center gap-2">
                  <span className="material-symbols-outlined text-sm">photo_camera</span>
                  Reference Photos — Upload 1+ photos for best results
                </p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {[
                    { label: "Front Face",    icon: "face" },
                    { label: "Left Profile",  icon: "face_retouching_natural" },
                    { label: "Right Profile", icon: "face_3" },
                    { label: "45° Angle",     icon: "face_4" },
                  ].map(({ label, icon }, i) => (
                    <PhotoSlot
                      key={i}
                      label={label}
                      icon={icon}
                      file={slots[i]}
                      onSelect={(f) => setSlotFile(i, f)}
                      onRemove={() => clearSlot(i)}
                    />
                  ))}
                </div>
              </div>

              {/* Extra photos */}
              <div>
                <p className="font-label text-[10px] tracking-widest uppercase text-on-surface-variant/60 mb-3 flex items-center gap-2">
                  <span className="material-symbols-outlined text-sm">add_photo_alternate</span>
                  Additional Photos (optional)
                </p>
                <div className="flex flex-wrap gap-3">
                  {extraFiles.map((f, i) => (
                    <div key={i} className="relative w-16 h-16 rounded border border-outline-variant/30 overflow-hidden group">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={URL.createObjectURL(f)} alt={`extra ${i}`} className="w-full h-full object-cover" />
                      <button
                        onClick={() => setExtraFiles((ef) => ef.filter((_, j) => j !== i))}
                        className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity"
                      >
                        <span className="material-symbols-outlined text-error text-lg">close</span>
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() => extraInputRef.current?.click()}
                    className="w-16 h-16 rounded border-2 border-dashed border-outline-variant/30 hover:border-primary/40 flex items-center justify-center text-on-surface-variant/40 hover:text-primary transition-all"
                  >
                    <span className="material-symbols-outlined">add</span>
                  </button>
                  <input ref={extraInputRef} type="file" accept="image/*" multiple className="hidden"
                    onChange={(e) => setExtraFiles((ef) => [...ef, ...Array.from(e.target.files || [])])} />
                </div>
              </div>

              {/* Info box */}
              <div className="p-4 bg-surface-container-low rounded border border-outline-variant/20">
                <div className="flex gap-3">
                  <span className="material-symbols-outlined text-primary shrink-0" style={{ fontVariationSettings: "'FILL' 1" }}>info</span>
                  <div className="space-y-1">
                    <p className="font-label text-[10px] font-bold tracking-widest uppercase text-primary">Generation Notes</p>
                    <p className="font-body text-xs text-on-surface-variant leading-relaxed">
                      Flux 2 Pro will generate 7 expression variants (neutral, happy, sad, angry, surprised, talking open/closed)
                      as 2D cartoon images, consistent hairstyle and outfit across all frames.
                      Generation takes ~2–3 minutes. Photos are used as reference for style — not directly embedded.
                    </p>
                  </div>
                </div>
              </div>

              {genError && (
                <div className="flex items-center gap-2 text-error text-xs font-label tracking-wider py-1">
                  <span className="material-symbols-outlined text-sm">error</span>
                  {genError}
                </div>
              )}

              {/* Generate button */}
              <button
                onClick={handleGenerate}
                disabled={!hasEnoughPhotos}
                className="w-full py-4 bg-gradient-to-r from-primary to-primary-container text-on-primary font-headline font-bold uppercase tracking-widest rounded hover:opacity-90 active:scale-[0.98] transition-all flex items-center justify-center gap-3 group disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <span className="material-symbols-outlined group-hover:rotate-12 transition-transform" style={{ fontVariationSettings: "'FILL' 1" }}>auto_awesome</span>
                {isEdit ? "Regenerate My Avatar" : "Generate My Avatar"}
                {!hasEnoughPhotos && <span className="font-label text-[10px] normal-case tracking-normal opacity-70">(upload at least 1 photo)</span>}
              </button>
            </div>
          </div>
        )}

        {/* ── GENERATING STATE ── */}
        {step === "generating" && (
          <div className="flex flex-col items-center justify-center py-20 space-y-8">
            <div className="relative w-32 h-32">
              <div className="absolute inset-0 border-2 border-primary/20 rounded-full animate-ping" />
              <div className="absolute inset-4 border-2 border-primary/40 rounded-full animate-pulse" />
              <div className="w-full h-full rounded-full bg-surface-container-highest flex items-center justify-center shadow-[0_0_40px_rgba(161,250,255,0.2)]">
                <span className="material-symbols-outlined text-4xl text-primary animate-spin"
                  style={{ fontVariationSettings: "'FILL' 1", animationDuration: "3s" }}>
                  auto_awesome
                </span>
              </div>
            </div>

            <div className="text-center space-y-2">
              <h3 className="font-headline text-2xl font-bold tracking-tight uppercase">Generating Agent</h3>
              <p className="font-label text-xs tracking-[0.2em] uppercase text-on-surface-variant">Flux 2 Pro · 7 Expression Variants</p>
            </div>

            <div className="w-full max-w-md space-y-2">
              {progress.map((msg, i) => (
                <div key={i} className="flex items-center gap-3 animate-slideUp" style={{ animationDelay: `${i * 0.3}s` }}>
                  <span className="material-symbols-outlined text-sm text-primary" style={{ fontVariationSettings: "'FILL' 1" }}>check_circle</span>
                  <p className="font-label text-[11px] tracking-wider text-on-surface-variant">{msg}</p>
                </div>
              ))}
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 border border-primary/30 border-t-primary rounded-full animate-spin shrink-0" />
                <p className="font-label text-[11px] tracking-wider text-primary">Processing with AI...</p>
              </div>
            </div>

            <div className="w-full max-w-md h-0.5 bg-surface-container-highest progress-track">
              <div className="h-full bg-primary progress-indicator animate-pulse" style={{ width: "60%" }} />
            </div>
          </div>
        )}
      </main>

      <LatestRunButton />
    </div>
  );
}
