"use client";

import { Suspense } from "react";
import AvatarPageInner from "./AvatarPageInner";

export default function AvatarPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="w-10 h-10 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    }>
      <AvatarPageInner />
    </Suspense>
  );
}
