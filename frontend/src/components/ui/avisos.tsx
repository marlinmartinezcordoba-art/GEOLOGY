"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import { createContext, type ReactNode, useCallback, useContext, useState } from "react";

import { cn } from "@/lib/formato";

type Aviso = { id: number; tipo: "ok" | "error"; texto: string };

const Contexto = createContext<{ exito: (t: string) => void; error: (t: string) => void } | null>(null);

export function useAvisos() {
  const valor = useContext(Contexto);
  if (!valor) throw new Error("useAvisos requiere ProveedorAvisos");
  return valor;
}

export function ProveedorAvisos({ children }: { children: ReactNode }) {
  const [avisos, setAvisos] = useState<Aviso[]>([]);
  const agregar = useCallback((tipo: Aviso["tipo"], texto: string) => {
    const id = Date.now() + Math.random();
    setAvisos((a) => [...a, { id, tipo, texto }]);
    setTimeout(() => setAvisos((a) => a.filter((x) => x.id !== id)), tipo === "error" ? 7000 : 4000);
  }, []);
  const [valor] = useState(() => ({ exito: (t: string) => agregar("ok", t), error: (t: string) => agregar("error", t) }));
  return (
    <Contexto.Provider value={valor}>
      {children}
      <div className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-[min(24rem,calc(100%-2rem))] flex-col gap-2" aria-live="polite">
        {avisos.map((a) => (
          <div
            key={a.id}
            className={cn(
              "pointer-events-auto flex animate-desde-derecha items-start gap-2.5 rounded-lg border bg-surface px-4 py-3 text-sm shadow-lg",
              a.tipo === "ok" ? "border-ok/30" : "border-critico/30",
            )}
          >
            {a.tipo === "ok" ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-ok-vivo" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-critico-vivo" />}
            <span>
              {a.texto}
            </span>
          </div>
        ))}
      </div>
    </Contexto.Provider>
  );
}
