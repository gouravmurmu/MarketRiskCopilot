"use client";

import useSWR from "swr";

const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");
// The free-tier API sleeps when idle; give the first request time to wake it.
const TIMEOUT_MS = 20_000;

export const apiConfigured = BASE !== "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!BASE) throw new Error("NEXT_PUBLIC_API_URL is not set");
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(BASE + path, { ...init, signal: ctrl.signal, headers: { "Content-Type": "application/json", ...init?.headers } });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

export const apiGet = <T,>(path: string) => request<T>(path);
export const apiPost = <T,>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export type Loaded<T> = { data: T | undefined; demo: boolean; loading: boolean };

/** Fetch from the API, falling back to deterministic demo data if it is unreachable. */
export function useApi<T>(path: string | null, demo: () => T): Loaded<T> {
  const { data, error, isLoading } = useSWR<T>(path && apiConfigured ? path : null, apiGet, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
  if (!path) return { data: undefined, demo: false, loading: false };
  if (!apiConfigured || error) return { data: demo(), demo: true, loading: false };
  return { data, demo: false, loading: isLoading };
}
