"use client";

/**
 * useAuth — simple localStorage-based auth hook.
 * Credentials are validated against the backend /api/auth endpoint.
 */

import { useEffect, useState, useCallback } from "react";

export interface AuthUser {
  username: string;
  displayName: string;
}

const STORAGE_KEY = "academy_user";

export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) setUser(JSON.parse(stored));
    } catch {
      // ignore
    }
    setLoading(false);
  }, []);

  const login = useCallback(
    async (username: string, password: string): Promise<{ ok: boolean; error?: string }> => {
      try {
        const res = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password }),
        });
        const data = await res.json();
        if (res.ok && data.user) {
          setUser(data.user);
          localStorage.setItem(STORAGE_KEY, JSON.stringify(data.user));
          return { ok: true };
        }
        return { ok: false, error: data.detail || "Invalid credentials" };
      } catch {
        return { ok: false, error: "Backend offline — run: uvicorn backend.server:app --port 8000 --reload" };
      }
    },
    []
  );

  const logout = useCallback(() => {
    setUser(null);
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  return { user, loading, login, logout };
}
