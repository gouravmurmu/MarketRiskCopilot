"use client";

import { createContext, useContext, useEffect, useState } from "react";

type Selection = {
  model: string;
  confidence: number;
  setModel: (m: string) => void;
  setConfidence: (c: number) => void;
};

const Ctx = createContext<Selection | null>(null);
const KEY = "mrc.selection";

export function SelectionProvider({ children }: { children: React.ReactNode }) {
  const [model, setModel] = useState("hs_500");
  const [confidence, setConfidence] = useState(0.99);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(KEY) ?? "null");
      if (saved?.model) setModel(saved.model);
      if (saved?.confidence) setConfidence(saved.confidence);
    } catch {
      /* storage unavailable: keep defaults */
    }
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify({ model, confidence }));
    } catch {
      /* ignore */
    }
  }, [model, confidence]);

  return <Ctx.Provider value={{ model, confidence, setModel, setConfidence }}>{children}</Ctx.Provider>;
}

export function useSelection() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useSelection outside SelectionProvider");
  return v;
}
