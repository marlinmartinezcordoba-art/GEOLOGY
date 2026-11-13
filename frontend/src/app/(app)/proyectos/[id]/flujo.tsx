"use client";

import { Bot, Cog, ListRestart, Play, RotateCcw, UserRound } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { useAvisos } from "@/components/ui/avisos";
import { Boton, Cargando, Insignia, Nota, Paginador, Tabla, Vacio } from "@/components/ui/basicos";
import { api } from "@/lib/api";
import { fechaHora, numero } from "@/lib/formato";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { Proyecto, TableroFlujo, UnidadFlujo } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

const POR_PAGINA = 50;

function enlace(proyectoId: string, f: UnidadFlujo): string | null {
  if (f.etapa.startsWith("hoja")) return `/proyectos/${proyectoId}/hojas/${f.unidad_id}`;
  if (f.etapa.startsWith("descripcion")) return `/proyectos/${proyectoId}/descripciones/${f.unidad_id}`;
  return null;
}

/** Flujo automático: ARCA avanza sola cada expediente (calidad, OCR, hoja de control, descripción) hasta donde decide una persona. */
export function Flujo({ proyecto }: { proyecto: Proyecto }) {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const base = `/proyectos/${proyecto.id}/flujo`;
  const [etapa, setEtapa] = useState<string | null>(null);
  const [pagina, setPagina] = useState(1);
  const [trabajando, setTrabajando] = useState<string | null>(null);
  const tablero = useDatos(() => api<TableroFlujo>(base), [base]);
  const lista = useDatos(() => api<{ total: number; filas: UnidadFlujo[] }>(`${base}/unidades`, { consulta: { etapa, desplazamiento: (pagina - 1) * POR_PAGINA, limite: POR_PAGINA } }), [base, etapa, pagina]);
  const errores = useDatos(() => api<{ id: string; unidad: string | null; motivo: string; error: string; intentos: number; terminado_en: string | null }[]>(`${base}/errores`), [base]);
  const opera = puede(PERMISOS.capturar);

  const refrescar = useRef(() => {});
  refrescar.current = () => (void tablero.recargar(), void lista.recargar());
  useEffect(() => {
    const t = setInterval(() => refrescar.current(), 6000);  // el trabajador avanza solo: el tablero se actualiza
    return () => clearInterval(t);
  }, []);

  async function hacer(clave: string, ruta: string, mensaje: (r: Record<string, number>) => string) {
    setTrabajando(clave);
    try {
      const r = await api<Record<string, number>>(`${base}/${ruta}`, { metodo: "POST" });
      avisos.exito(mensaje(r));
      void tablero.recargar();
      void lista.recargar();
      void errores.recargar();
    } catch (e) {
      avisos.error((e as Error).message);
    } finally {
      setTrabajando(null);
    }
  }

  const t = tablero.datos;
  if (!t) return <Cargando />;
  const esperan = t.etapas.filter((e) => e.espera_persona).reduce((a, e) => a + e.unidades, 0);
  return (
    <div className="flex flex-col gap-5 p-5">
      <Nota tono="info">
        Al cargar lo digitalizado, ARCA avanza sola cada expediente: espera la calidad, lee con OCR, crea y propone la hoja de control y la descripción, según lo que lleve el lote. Se detiene donde decide una persona y sigue sola cuando esa persona actúa. Nunca decide por nadie: solo calcula y propone, y todo queda en la auditoría.
      </Nota>
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-[13px] shadow-xs">
        <Cog className="size-5 text-marca" />
        <span><b>{numero(t.cola.pendientes)}</b> en cola · <b>{numero(t.cola.en_curso)}</b> en curso · {numero(t.cola.hechos)} hechos{t.cola.errores ? <> · <span className="text-critico">{numero(t.cola.errores)} con error</span></> : null}</span>
        <span className="text-texto-3">· trabajador: {t.trabajador}{t.ultimo ? ` · último: ${fechaHora(t.ultimo)}` : ""}</span>
        {opera && (
          <div className="ml-auto flex gap-2">
            <Boton tamano="sm" icono={<ListRestart />} cargando={trabajando === "iniciar"} onClick={() => hacer("iniciar", "iniciar", (r) => `${numero(r.encoladas)} expedientes en cola.`)}>Poner en cola lo digitalizado</Boton>
            <Boton tamano="sm" variante="primario" icono={<Play />} cargando={trabajando === "procesar"} disabled={!t.cola.pendientes} onClick={() => hacer("procesar", "procesar", (r) => `${numero(r.procesados)} trabajos procesados.`)}>Procesar ahora</Boton>
          </div>
        )}
      </div>
      <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {t.etapas.filter((e) => e.clave !== "en_cola").map((e) => (
          <button key={e.clave} onClick={() => (setEtapa(etapa === e.clave ? null : e.clave), setPagina(1))}
            className={`rounded-xl border px-3 py-2 text-left transition-colors ${etapa === e.clave ? "border-marca bg-marca-suave" : "border-line bg-surface hover:border-marca-borde"}`}>
            <span className="flex items-center gap-1 text-[11.5px] text-texto-3">{e.espera_persona ? <UserRound className="size-3.5" /> : <Bot className="size-3.5" />}{e.nombre}</span>
            <span className={`tabular text-[22px] font-bold ${e.espera_persona && e.unidades ? "text-aviso" : "text-titulo"}`}>{numero(e.unidades)}</span>
          </button>
        ))}
      </div>
      {esperan > 0 && !etapa && <p className="text-[13px] text-texto-2"><b>{numero(esperan)}</b> expedientes esperan a una persona. Toque una etapa para verlos.</p>}
      <div className="rounded-xl border border-line">
        {!lista.datos?.filas.length ? <Vacio icono={<Bot />} titulo={etapa ? "No hay expedientes en esta etapa" : "El flujo todavía no ha procesado expedientes"} descripcion="Cargue lo digitalizado en «Digitalización y calidad» o ponga en cola lo que ya está cargado." /> : (
          <Tabla>
            <thead><tr><th>Expediente</th><th>Etapa</th><th>Qué falta</th><th>Lo que hizo ARCA</th><th>Actualizado</th><th /></tr></thead>
            <tbody>
              {lista.datos.filas.map((f) => {
                const ir = enlace(proyecto.id, f);
                return (
                  <tr key={f.unidad_id}>
                    <td className="max-w-xs"><p className="font-semibold text-titulo">{f.identificador}</p><p className="text-[12.5px]">{f.nombre}</p></td>
                    <td><Insignia tono={f.etapa === "listo" ? "ok" : f.etapa === "error" ? "critico" : f.espera_persona ? "aviso" : "motor"}>{f.etapa_nombre}</Insignia></td>
                    <td className="max-w-sm text-[12.5px]">{f.detalle}</td>
                    <td className="max-w-sm text-[11.5px] text-texto-3">{f.hechos.slice(-2).map((h) => <p key={h.fecha}>{h.que}</p>)}</td>
                    <td className="whitespace-nowrap text-[12px] text-texto-3">{fechaHora(f.actualizado_en)}</td>
                    <td className="text-right">{ir && f.espera_persona && <Link className="text-[13px] font-semibold text-marca hover:underline" href={ir}>Atender →</Link>}</td>
                  </tr>
                );
              })}
            </tbody>
          </Tabla>
        )}
        <Paginador total={lista.datos?.total ?? 0} pagina={pagina} porPagina={POR_PAGINA} alCambiar={setPagina} />
      </div>
      {!!errores.datos?.length && (
        <div>
          <p className="mb-2 font-semibold text-titulo">Trabajos con error</p>
          <Tabla className="rounded-xl border border-line">
            <thead><tr><th>Expediente</th><th>Originado por</th><th>Error</th><th>Intentos</th><th /></tr></thead>
            <tbody>
              {errores.datos.map((e) => (
                <tr key={e.id}>
                  <td>{e.unidad ?? "—"}</td><td className="text-[12.5px]">{e.motivo}</td><td className="max-w-md text-[12px] text-critico">{e.error}</td><td className="tabular">{e.intentos}</td>
                  <td>{opera && <Boton tamano="sm" variante="fantasma" icono={<RotateCcw />} onClick={() => hacer(`r-${e.id}`, `errores/${e.id}/reintentar`, () => "Vuelve a la cola.")}>Reintentar</Boton>}</td>
                </tr>
              ))}
            </tbody>
          </Tabla>
        </div>
      )}
    </div>
  );
}
