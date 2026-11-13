"use client";

import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/formato";

const BASE =
  "rounded-lg border border-line-strong bg-surface px-3 text-sm text-texto transition-colors placeholder:text-texto-3 hover:border-marca-borde focus:border-marca focus:outline-none focus:ring-3 focus:ring-marca/20 disabled:bg-surface-muted disabled:text-texto-3";

export function Campo({ etiqueta, ayuda, error, requerido, children, className }: { etiqueta: ReactNode; ayuda?: ReactNode; error?: string | null; requerido?: boolean; children: ReactNode; className?: string }) {
  return (
    <label className={cn("flex flex-col gap-1", className)}>
      <span className="text-[13px] font-medium text-texto-2">
        {etiqueta}
        {requerido && <span className="text-critico"> *</span>}
      </span>
      {children}
      {error ? <span className="text-xs text-critico">{error}</span> : ayuda ? <span className="text-xs text-texto-3">{ayuda}</span> : null}
    </label>
  );
}

/** Ancho completo salvo que la pantalla indique otro ancho (w-40, w-64…). */
function ancho(className?: string) {
  return /(^|\s)(w-|min-w-|flex-1)/.test(className ?? "") ? "" : "w-full";
}

export function Entrada({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(BASE, ancho(className), "h-9", className)} {...props} />;
}

export function Area({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(BASE, ancho(className), "min-h-20 py-2", className)} {...props} />;
}

export function Selector({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <select className={cn(BASE, ancho(className), "h-9 pr-8", className)} {...props}>
      {children}
    </select>
  );
}

export function Casilla({ etiqueta, className, ...props }: ComponentProps<"input"> & { etiqueta: ReactNode }) {
  return (
    <label className={cn("inline-flex cursor-pointer items-center gap-2 text-sm text-texto-2", className)}>
      <input type="checkbox" className="size-4 accent-marca" {...props} />
      {etiqueta}
    </label>
  );
}

export function Interruptor({ activo, alCambiar, etiqueta, deshabilitado }: { activo: boolean; alCambiar: (v: boolean) => void; etiqueta?: string; deshabilitado?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={activo}
      aria-label={etiqueta}
      disabled={deshabilitado}
      onClick={() => alCambiar(!activo)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:opacity-50",
        activo ? "bg-marca" : "bg-line-strong",
      )}
    >
      <span className={cn("inline-block size-4 rounded-full bg-white shadow-sm transition-transform", activo ? "translate-x-4.5" : "translate-x-0.5")} />
    </button>
  );
}
