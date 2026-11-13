"use client";

import { AlertTriangle, Bot, ChevronLeft, ChevronRight, Inbox, Loader2, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { type ComponentProps, type ReactNode, useEffect, useRef } from "react";

import { type Tono } from "@/lib/tonos";
import { cn } from "@/lib/formato";

// ---------------------------------------------------------------- Botón

type Variante = "primario" | "acento" | "secundario" | "fantasma" | "peligro" | "suave" | "motor";

const VARIANTES: Record<Variante, string> = {
  primario: "bg-marca text-white shadow-xs hover:bg-marca-hover active:translate-y-px",
  // Turquesa: crear algo nuevo o lanzar una automatización. Fondo oscuro del turquesa para contraste AA con blanco.
  acento: "bg-motor text-white shadow-xs hover:bg-motor-vivo active:translate-y-px",
  secundario: "bg-surface text-marca border border-line-strong shadow-xs hover:border-marca-borde hover:bg-marca-suave/50 active:translate-y-px",
  fantasma: "text-texto-2 hover:bg-surface-muted hover:text-marca",
  peligro: "bg-critico text-white shadow-xs hover:brightness-95 active:translate-y-px",
  suave: "bg-marca-suave text-marca hover:bg-marca-borde/50",
  motor: "bg-motor text-white shadow-xs hover:bg-motor-vivo active:translate-y-px",
};

interface PropsBoton extends ComponentProps<"button"> {
  variante?: Variante;
  tamano?: "sm" | "md";
  icono?: ReactNode;
  cargando?: boolean;
}

export function Boton({ variante = "secundario", tamano = "md", icono, cargando, className, children, disabled, type = "button", ...props }: PropsBoton) {
  return (
    <button
      type={type}
      disabled={disabled || cargando}
      className={cn(
        "inline-flex shrink-0 items-center justify-center gap-2 rounded-lg font-semibold whitespace-nowrap transition-[background-color,border-color,color,filter,transform] duration-150",
        "disabled:cursor-not-allowed disabled:opacity-55 [&_svg]:size-4 [&_svg]:shrink-0",
        tamano === "sm" ? "h-8 px-3 text-[13px]" : "h-9 px-3.5 text-sm",
        VARIANTES[variante],
        className,
      )}
      {...props}
    >
      {cargando ? <Loader2 className="animate-spin" /> : icono}
      {children}
    </button>
  );
}

export function BotonEnlace({ href, variante = "secundario", icono, children, className }: { href: string; variante?: Variante; icono?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <Link
      href={href}
      className={cn("inline-flex h-9 items-center gap-2 rounded-lg px-3.5 text-sm font-semibold transition-colors [&_svg]:size-4", VARIANTES[variante], className)}
    >
      {icono}
      {children}
    </Link>
  );
}

// ---------------------------------------------------------------- Insignia

export const TONOS: Record<Tono, string> = {
  marca: "bg-marca-suave text-marca",
  motor: "bg-motor-suave text-motor",
  ia: "bg-ia-suave text-ia",
  ok: "bg-ok-suave text-ok",
  aviso: "bg-aviso-suave text-aviso",
  critico: "bg-critico-suave text-critico",
  naranja: "bg-naranja-suave text-naranja",
  info: "bg-info-suave text-info",
  neutro: "bg-neutro-suave text-neutro",
};

export const PUNTOS: Record<Tono, string> = {
  marca: "bg-marca",
  motor: "bg-motor-vivo",
  ia: "bg-ia-vivo",
  ok: "bg-ok-vivo",
  aviso: "bg-aviso-vivo",
  critico: "bg-critico-vivo",
  naranja: "bg-naranja-vivo",
  info: "bg-info-vivo",
  neutro: "bg-neutro",
};

export function Insignia({ tono = "neutro", punto, children, className }: { tono?: Tono; punto?: boolean; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap", TONOS[tono], className)}>
      {punto && <span className={cn("size-1.5 rounded-full", PUNTOS[tono])} />}
      {children}
    </span>
  );
}

/** Marca de lo que hizo una regla o automatización (determinístico). */
export function InsigniaMotor({ children = "Automático" }: { children?: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-motor-suave px-2 py-0.5 text-xs font-medium text-motor">
      <Bot className="size-3" />
      {children}
    </span>
  );
}

// ---------------------------------------------------------------- Tarjeta

export function Tarjeta({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cn("rounded-xl border border-line bg-surface shadow-xs", className)}>{children}</section>;
}

export function CabeceraTarjeta({ titulo, descripcion, acciones }: { titulo: ReactNode; descripcion?: ReactNode; acciones?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line/80 px-5 py-4">
      <div className="min-w-0">
        <h2 className="text-[15.5px] font-semibold tracking-tight text-titulo">{titulo}</h2>
        {descripcion && <p className="mt-0.5 text-[13px] text-texto-3">{descripcion}</p>}
      </div>
      {acciones && <div className="flex flex-wrap items-center gap-2">{acciones}</div>}
    </div>
  );
}

// ---------------------------------------------------------------- Encabezado de página

export function EncabezadoPagina({ titulo, descripcion, acciones, volver }: { titulo: ReactNode; descripcion?: ReactNode; acciones?: ReactNode; volver?: { href: string; texto: string } }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {volver && (
          <Link href={volver.href} className="mb-1 inline-block text-[13px] font-semibold text-marca hover:underline">
            ← {volver.texto}
          </Link>
        )}
        <h1 className="text-[24px] leading-tight font-bold tracking-tight text-titulo">{titulo}</h1>
        {descripcion && <p className="mt-1 max-w-3xl text-[14px] text-texto-3">{descripcion}</p>}
      </div>
      {acciones && <div className="flex flex-wrap items-center gap-2">{acciones}</div>}
    </header>
  );
}

// ---------------------------------------------------------------- Estados

export function Cargando({ texto = "Cargando…" }: { texto?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-texto-3">
      <Loader2 className="size-4 animate-spin" />
      {texto}
    </div>
  );
}

export function Vacio({ titulo, descripcion, accion, icono }: { titulo: string; descripcion?: ReactNode; accion?: ReactNode; icono?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      <div className="grid size-14 place-items-center rounded-2xl bg-marca-suave text-marca ring-8 ring-marca-suave/40 [&_svg]:size-6">{icono ?? <Inbox />}</div>
      <p className="font-semibold text-texto">{titulo}</p>
      {descripcion && <p className="max-w-md text-[13px] text-texto-3">{descripcion}</p>}
      {accion && <div className="mt-2">{accion}</div>}
    </div>
  );
}

export function CajaError({ mensaje, reintentar }: { mensaje: string; reintentar?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-critico/25 bg-critico-suave px-4 py-3 text-critico">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      <div className="flex-1 text-sm">
        {mensaje}
      </div>
      {reintentar && (
        <button className="text-sm font-semibold underline" onClick={reintentar}>
          Reintentar
        </button>
      )}
    </div>
  );
}

export function Nota({ tono = "info", children, icono }: { tono?: Tono; children: ReactNode; icono?: ReactNode }) {
  return <div className={cn("flex items-start gap-2.5 rounded-md px-3.5 py-2.5 text-[13px] [&_svg]:mt-0.5 [&_svg]:size-4 [&_svg]:shrink-0", TONOS[tono])}>{icono}{<div>{children}</div>}</div>;
}

// ---------------------------------------------------------------- Indicador

export function Indicador({ etiqueta, valor, detalle, tono, icono, href, accion }: { etiqueta: string; valor: ReactNode; detalle?: ReactNode; tono?: Tono; icono?: ReactNode; href?: string; accion?: string }) {
  const contenido = (
    <div className="group flex h-full flex-col gap-1.5 rounded-xl border border-line bg-surface p-4 shadow-xs transition-[border-color,box-shadow] hover:border-marca-borde hover:shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13px] font-medium text-texto-3">{etiqueta}</span>
        {icono && <span className={cn("grid size-9 place-items-center rounded-xl [&_svg]:size-[18px]", tono && tono !== "marca" ? TONOS[tono] : "bg-marca-suave text-marca")}>{icono}</span>}
      </div>
      <span className="tabular text-[28px] leading-tight font-bold tracking-tight text-titulo">{valor}</span>
      {detalle && <span className="text-[13px] text-texto-3">{detalle}</span>}
      {href && accion && <span className="mt-auto pt-1 text-[13px] font-semibold text-marca group-hover:underline">{accion} →</span>}
    </div>
  );
  return href ? <Link href={href}>{contenido}</Link> : contenido;
}

// ---------------------------------------------------------------- Barra de progreso

export function Progreso({ valor, tono = "marca", className }: { valor: number; tono?: Tono; className?: string }) {
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-surface-muted", className)}>
      <div className={cn("h-full rounded-full", PUNTOS[tono])} style={{ width: `${Math.max(0, Math.min(100, valor))}%` }} />
    </div>
  );
}

// ---------------------------------------------------------------- Tabla

export function Tabla({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("overflow-x-auto", className)}>
      <table className="w-full border-collapse text-left text-[13px] [&_td]:border-b [&_td]:border-line [&_td]:px-4 [&_td]:py-3 [&_th]:border-b [&_th]:border-line [&_th]:px-4 [&_th]:py-2.5 [&_th]:text-xs [&_th]:font-semibold [&_th]:text-texto-3 [&_tbody_tr:last-child_td]:border-b-0 [&_tbody_tr]:transition-colors [&_tbody_tr:hover]:bg-canvas">
        {children}
      </table>
    </div>
  );
}

// ---------------------------------------------------------------- Modal

export function Modal({ abierto, alCerrar, titulo, descripcion, children, pie, ancho = "md" }: { abierto: boolean; alCerrar: () => void; titulo: ReactNode; descripcion?: ReactNode; children: ReactNode; pie?: ReactNode; ancho?: "md" | "lg" | "xl" }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialogo = ref.current;
    if (!dialogo) return;
    if (abierto && !dialogo.open) dialogo.showModal();
    if (!abierto && dialogo.open) dialogo.close();
  }, [abierto]);
  return (
    <dialog
      ref={ref}
      onClose={alCerrar}
      onCancel={(e) => {
        e.preventDefault();
        alCerrar();
      }}
      className={cn(
        "m-auto max-h-[90vh] w-[calc(100%-2rem)] animate-subir rounded-2xl border border-line bg-surface p-0 text-texto shadow-lg",
        ancho === "md" ? "max-w-lg" : ancho === "lg" ? "max-w-2xl" : "max-w-4xl",
      )}
    >
      {abierto && (
        <div className="flex max-h-[90vh] flex-col">
          <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
            <div>
              <h2 className="text-lg font-semibold text-titulo">{titulo}</h2>
              {descripcion && <p className="text-[13px] text-texto-3">{descripcion}</p>}
            </div>
            <button onClick={alCerrar} className="rounded-md p-1 text-texto-3 hover:bg-surface-muted" aria-label="Cerrar">
              <X className="size-4" />
            </button>
          </div>
          <div className="overflow-y-auto px-5 py-4">{children}</div>
          {pie && <div className="flex flex-wrap justify-end gap-2 border-t border-line bg-canvas px-5 py-3">{pie}</div>}
        </div>
      )}
    </dialog>
  );
}

// ---------------------------------------------------------------- Pestañas

export function Pestanas<T extends string>({ opciones, valor, alCambiar }: { opciones: { valor: T; etiqueta: ReactNode }[]; valor: T; alCambiar: (v: T) => void }) {
  return (
    <div className="flex gap-1 overflow-x-auto overflow-y-hidden border-b border-line" role="tablist">
      {opciones.map((o) => (
        <button
          key={o.valor}
          role="tab"
          aria-selected={o.valor === valor}
          onClick={() => alCambiar(o.valor)}
          className={cn(
            "-mb-px border-b-2 px-3 py-2.5 text-sm whitespace-nowrap transition-colors",
            o.valor === valor ? "border-marca font-semibold text-marca" : "border-transparent font-medium text-texto-3 hover:text-marca",
          )}
        >
          {o.etiqueta}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- Inteligencia artificial

/**
 * Todo lo que PROPONE la IA se marca así, con su confianza. Nunca se escribe «la IA determinó»:
 * la IA propone, el profesional valida y ARCA registra.
 */
export function InsigniaIA({ confianza, children = "Sugerencia automática" }: { confianza?: number; children?: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-ia-borde bg-ia-suave px-2 py-0.5 text-xs font-medium whitespace-nowrap text-ia">
      <Sparkles className="size-3" />
      {children}
      {confianza !== undefined && <span className="tabular font-semibold">· {confianza} %</span>}
    </span>
  );
}

/** Nivel de confianza de una propuesta de IA u OCR: alto (≥ 85), medio (≥ 65) o bajo. */
export function nivelConfianza(valor: number): { etiqueta: string; tono: Tono } {
  if (valor >= 85) return { etiqueta: "Alta", tono: "ok" };
  if (valor >= 65) return { etiqueta: "Media", tono: "aviso" };
  return { etiqueta: "Baja", tono: "critico" };
}

export function Confianza({ valor, compacta }: { valor: number; compacta?: boolean }) {
  const nivel = nivelConfianza(valor);
  return (
    <span className="inline-flex shrink-0 items-center gap-2 whitespace-nowrap" title={`Confianza ${nivel.etiqueta.toLowerCase()}: ${valor} %`}>
      <span className={cn("h-1.5 overflow-hidden rounded-full bg-surface-muted", compacta ? "w-10" : "w-16")}>
        <span className={cn("block h-full rounded-full", PUNTOS[nivel.tono])} style={{ width: `${valor}%` }} />
      </span>
      <span className="tabular text-xs font-medium whitespace-nowrap text-texto-2">{valor} %</span>
    </span>
  );
}

// ---------------------------------------------------------------- Paginación

export function Paginador({ total, pagina, porPagina, alCambiar }: { total: number; pagina: number; porPagina: number; alCambiar: (p: number) => void }) {
  const paginas = Math.max(1, Math.ceil(total / porPagina));
  if (total <= porPagina) return <p className="px-5 py-3 text-xs text-texto-3">{total} {total === 1 ? "registro" : "registros"}</p>;
  return (
    <div className="flex items-center justify-between gap-3 border-t border-line px-5 py-2.5 text-xs text-texto-3">
      <span className="tabular">
        {(pagina - 1) * porPagina + 1}–{Math.min(total, pagina * porPagina)} de {total}
      </span>
      <div className="flex items-center gap-1">
        <button className="grid size-7 place-items-center rounded-md hover:bg-surface-muted disabled:opacity-40" disabled={pagina <= 1} onClick={() => alCambiar(pagina - 1)} aria-label="Página anterior">
          <ChevronLeft className="size-4" />
        </button>
        <span className="tabular px-1">
          {pagina} / {paginas}
        </span>
        <button className="grid size-7 place-items-center rounded-md hover:bg-surface-muted disabled:opacity-40" disabled={pagina >= paginas} onClick={() => alCambiar(pagina + 1)} aria-label="Página siguiente">
          <ChevronRight className="size-4" />
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Datos en pares

export function Datos({ filas, columnas = 2 }: { filas: [ReactNode, ReactNode][]; columnas?: 1 | 2 | 3 }) {
  return (
    <dl className={cn("grid gap-x-6 gap-y-3", columnas === 1 ? "grid-cols-1" : columnas === 2 ? "sm:grid-cols-2" : "sm:grid-cols-3")}>
      {filas.map(([k, v], i) => (
        <div key={i} className="min-w-0">
          <dt className="text-xs text-texto-3">{k}</dt>
          <dd className="truncate text-[13.5px] font-medium text-texto">{v ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Código de radicado, expediente, hash o documento en fuente monoespaciada. */
export function Codigo({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("font-mono text-[12.5px] text-texto-2", className)}>{children}</span>;
}
