"use client";

import { ClipboardCheck, Plus, Save, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAvisos } from "@/components/ui/avisos";
import { Boton, Cargando, Insignia, Nota, Tabla, Vacio } from "@/components/ui/basicos";
import { Campo, Casilla, Entrada, Selector } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { fechaHora, numero } from "@/lib/formato";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { Tono } from "@/lib/tonos";
import type { InspeccionResumen, LoteInspeccion, PlanMuestreo, Proyecto, VistaPlanMuestreo } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

export const ESTADO_INSPECCION: Record<string, { etiqueta: string; tono: Tono }> = {
  abierta: { etiqueta: "Abierta", tono: "info" }, aceptada: { etiqueta: "Lote aceptado", tono: "ok" },
  rechazada: { etiqueta: "Lote rechazado", tono: "critico" }, anulada: { etiqueta: "Anulada", tono: "neutro" },
};
export const SEVERIDAD: Record<string, { etiqueta: string; tono: Tono }> = {
  critico: { etiqueta: "Crítico", tono: "critico" }, mayor: { etiqueta: "Mayor", tono: "aviso" }, menor: { etiqueta: "Menor", tono: "info" },
  limitacion: { etiqueta: "Limitación del original", tono: "neutro" },
};

export const PLURAL: Record<string, string> = { critico: "críticos", mayor: "mayores", menor: "menores", limitacion: "limitaciones del original" };

/** Inspección de calidad por lote: plan de muestreo (dirección), lotes por inspeccionar e inspecciones hechas. */
export function Inspeccion({ proyecto }: { proyecto: Proyecto }) {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const router = useRouter();
  const base = `/proyectos/${proyecto.id}/inspeccion`;
  const plan = useDatos(() => api<VistaPlanMuestreo>(`${base}/plan`), [base]);
  const lotes = useDatos(() => api<LoteInspeccion[]>(`${base}/lotes`), [base]);
  const inspecciones = useDatos(() => api<InspeccionResumen[]>(`${base}/inspecciones`), [base]);
  const [abriendo, setAbriendo] = useState<string | null>(null);
  const inspecciona = puede(PERMISOS.calidad);

  async function inspeccionar(lote: string) {
    setAbriendo(lote);
    try {
      const d = await api<{ id: string; muestra: number; tamano: number }>(`${base}/inspecciones`, { metodo: "POST", cuerpo: { lote } });
      avisos.exito(`Muestra de ${numero(d.muestra)} de ${numero(d.tamano)}. Abriendo la inspección…`);
      router.push(`/proyectos/${proyecto.id}/inspecciones/${d.id}`);
    } catch (err) {
      avisos.error((err as Error).message);
      setAbriendo(null);
    }
  }

  if (plan.cargando && !plan.datos) return <Cargando />;
  const unidad = plan.datos?.plan.unidad === "imagenes" ? "imágenes" : "expedientes";
  return (
    <div className="flex flex-col gap-5 p-5">
      <Nota tono="info">ARCA elige la muestra de cada lote al azar con una semilla registrada (la misma semilla da la misma muestra), quien inspecciona anota los defectos y ARCA acepta o rechaza el lote según el plan. Quien cargó un archivo no lo puede inspeccionar. Cada inspección cerrada queda en el registro de calidad de productividad y tiene su acta.</Nota>
      {plan.datos && <PlanCard base={base} vista={plan.datos} alGuardar={() => (plan.recargar(), lotes.recargar())} />}
      <div>
        <p className="mb-2 font-semibold text-titulo">Lotes</p>
        {!lotes.datos?.length ? <Vacio icono={<ClipboardCheck />} titulo="No hay lotes con material digitalizado" /> : (
          <Tabla className="rounded-xl border border-line">
            <thead><tr><th>Lote</th><th>Cajas</th><th>Expedientes</th><th>Imágenes</th><th>Última inspección</th><th /></tr></thead>
            <tbody>
              {lotes.datos.map((l) => (
                <tr key={l.lote}>
                  <td className="font-semibold">{l.lote || "Sin lote"}</td>
                  <td className="tabular">{numero(l.cajas)}</td>
                  <td className="tabular">{numero(l.expedientes)}</td>
                  <td className="tabular">{numero(l.imagenes)}</td>
                  <td>{l.ultima ? <Insignia tono={ESTADO_INSPECCION[l.ultima.estado].tono} punto>n.º {l.ultima.numero} · {ESTADO_INSPECCION[l.ultima.estado].etiqueta}</Insignia> : <span className="text-[12px] text-texto-3">Sin inspeccionar</span>}</td>
                  <td className="text-right">
                    {l.abierta ? <Link className="text-[13px] font-semibold text-marca hover:underline" href={`/proyectos/${proyecto.id}/inspecciones/${l.abierta.id}`}>Continuar la n.º {l.abierta.numero} →</Link>
                      : inspecciona && plan.datos?.vigente && (l.expedientes > 0) && <Boton tamano="sm" variante="primario" icono={<ClipboardCheck />} cargando={abriendo === l.lote} onClick={() => inspeccionar(l.lote)}>{l.ultima?.estado === "rechazada" ? "Reinspeccionar" : "Inspeccionar"}</Boton>}
                  </td>
                </tr>
              ))}
            </tbody>
          </Tabla>
        )}
        {!plan.datos?.vigente && <p className="mt-2 text-[12.5px] text-texto-3">Para inspeccionar, la dirección debe guardar el plan de muestreo.</p>}
      </div>
      <div>
        <p className="mb-2 font-semibold text-titulo">Inspecciones</p>
        {!inspecciones.datos?.length ? <p className="text-[13px] text-texto-3">Todavía no hay inspecciones.</p> : (
          <Tabla className="rounded-xl border border-line">
            <thead><tr><th>N.º</th><th>Lote</th><th>Estado</th><th>Muestra</th><th>Críticos · mayores · menores</th><th>Abierta</th><th>Cerrada</th><th /></tr></thead>
            <tbody>
              {inspecciones.datos.map((i) => (
                <tr key={i.id}>
                  <td className="tabular font-semibold">{i.numero}{i.reinspeccion_de && <span className="ml-1 text-[11px] font-normal text-texto-3">reinspección</span>}</td>
                  <td>{i.lote || "Sin lote"}</td>
                  <td><Insignia tono={ESTADO_INSPECCION[i.estado].tono} punto>{ESTADO_INSPECCION[i.estado].etiqueta}</Insignia></td>
                  <td className="tabular">{numero(i.revisados)} de {numero(i.muestra)} {i.unidad === "imagenes" ? "imágenes" : "expedientes"} · lote de {numero(i.tamano)}</td>
                  <td className="tabular">{i.estado === "abierta" || i.estado === "anulada" ? "—" : `${i.criticos} · ${i.mayores} · ${i.menores}`}</td>
                  <td className="whitespace-nowrap">{fechaHora(i.creado_en)}</td>
                  <td className="whitespace-nowrap">{i.cerrada_en ? fechaHora(i.cerrada_en) : "—"}</td>
                  <td><Link className="text-[13px] font-semibold text-marca hover:underline" href={`/proyectos/${proyecto.id}/inspecciones/${i.id}`}>Abrir →</Link></td>
                </tr>
              ))}
            </tbody>
          </Tabla>
        )}
      </div>
      <p className="text-[12px] text-texto-3">Unidad de inspección del plan vigente: {unidad}.</p>
    </div>
  );
}

function PlanCard({ base, vista, alGuardar }: { base: string; vista: VistaPlanMuestreo; alGuardar: () => void }) {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const dirige = puede(PERMISOS.proyectos);
  const [editando, setEditando] = useState(!vista.vigente && dirige);
  const [plan, setPlan] = useState<PlanMuestreo>(vista.plan);
  const [motivo, setMotivo] = useState("");
  const [guardando, setGuardando] = useState(false);
  useEffect(() => setPlan(vista.plan), [vista.plan]);
  const p = vista.plan;
  const cambiar = (c: Partial<PlanMuestreo>) => setPlan((x) => ({ ...x, ...c }));

  async function guardar() {
    setGuardando(true);
    try {
      await api(`${base}/plan`, { metodo: "PUT", cuerpo: { ...plan, motivo } });
      avisos.exito("Plan de muestreo guardado.");
      setEditando(false);
      setMotivo("");
      alGuardar();
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="rounded-xl border border-line bg-surface p-4 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-semibold text-titulo">Plan de muestreo {vista.vigente ? `· versión ${p.version}` : ""}</span>
        {vista.vigente ? <Insignia tono="ok" punto>Vigente</Insignia> : <Insignia tono="aviso" punto>Sin plan: propuesta de ejemplo</Insignia>}
      </div>
      {!editando ? (
        <div className="mt-2 grid gap-1 text-[13px] text-texto-2 sm:grid-cols-2">
          <span>Se inspeccionan: <b>{p.unidad === "imagenes" ? "imágenes" : "expedientes"}</b></span>
          <span>Muestra: <b>{p.metodo === "porcentaje" ? `${p.porcentaje} % con mínimo de ${p.minimo}` : `tabla de ${p.tabla.length} rangos`}</b></span>
          <span>Defectos que se aceptan: <b>críticos {p.aceptacion.critico} · mayores {p.aceptacion.mayor} · menores {p.aceptacion.menor}</b></span>
          <span>Defectos en el catálogo: <b>{p.defectos.length}</b>{p.frente ? ` · frente ${p.frente}` : ""}{p.exigir_para_entrega ? " · se exige para entregar" : ""}</span>
          {vista.motivo && <span className="text-[12px] text-texto-3 sm:col-span-2">Motivo: {vista.motivo}</span>}
          {vista.aviso && <span className="text-[12.5px] text-aviso sm:col-span-2">{vista.aviso}</span>}
          {dirige && <div className="mt-2 sm:col-span-2"><Boton tamano="sm" onClick={() => setEditando(true)}>{vista.vigente ? "Cambiar el plan" : "Revisar y guardar el plan"}</Boton></div>}
        </div>
      ) : (
        <div className="mt-3 flex flex-col gap-3">
          {vista.aviso && <Nota tono="aviso">{vista.aviso}</Nota>}
          <div className="grid gap-3 sm:grid-cols-4">
            <Campo etiqueta="Se inspeccionan"><Selector value={plan.unidad} onChange={(e) => cambiar({ unidad: e.target.value as PlanMuestreo["unidad"] })}><option value="expedientes">Expedientes</option><option value="imagenes">Imágenes</option></Selector></Campo>
            <Campo etiqueta="Tamaño de la muestra"><Selector value={plan.metodo} onChange={(e) => cambiar({ metodo: e.target.value as PlanMuestreo["metodo"] })}><option value="porcentaje">Porcentaje con mínimo</option><option value="tabla">Tabla de tamaños</option></Selector></Campo>
            {plan.metodo === "porcentaje" && <>
              <Campo etiqueta="Porcentaje (%)"><Entrada type="number" min={0} max={100} step="0.5" value={plan.porcentaje} onChange={(e) => cambiar({ porcentaje: Number(e.target.value) })} /></Campo>
              <Campo etiqueta="Mínimo"><Entrada type="number" min={1} value={plan.minimo} onChange={(e) => cambiar({ minimo: Number(e.target.value) })} /></Campo>
            </>}
          </div>
          {plan.metodo === "tabla" && (
            <div>
              <p className="mb-1 text-[12.5px] font-semibold text-texto-2">Tamaño del lote → tamaño de la muestra</p>
              {plan.tabla.map((f, i) => (
                <div key={i} className="mb-1 flex items-center gap-2 text-[13px]">
                  <span>De</span><Entrada className="w-24" type="number" aria-label={`Desde, fila ${i + 1}`} value={f.desde} onChange={(e) => cambiar({ tabla: plan.tabla.map((x, j) => (j === i ? { ...x, desde: Number(e.target.value) } : x)) })} />
                  <span>a</span><Entrada className="w-24" type="number" aria-label={`Hasta, fila ${i + 1}`} value={f.hasta} onChange={(e) => cambiar({ tabla: plan.tabla.map((x, j) => (j === i ? { ...x, hasta: Number(e.target.value) } : x)) })} />
                  <span>→ muestra</span><Entrada className="w-24" type="number" aria-label={`Muestra, fila ${i + 1}`} value={f.muestra} onChange={(e) => cambiar({ tabla: plan.tabla.map((x, j) => (j === i ? { ...x, muestra: Number(e.target.value) } : x)) })} />
                  <Boton tamano="sm" variante="fantasma" icono={<Trash2 />} aria-label="Quitar fila" onClick={() => cambiar({ tabla: plan.tabla.filter((_, j) => j !== i) })} />
                </div>
              ))}
              <Boton tamano="sm" variante="fantasma" icono={<Plus />} onClick={() => cambiar({ tabla: [...plan.tabla, { desde: (plan.tabla.at(-1)?.hasta ?? 0) + 1, hasta: (plan.tabla.at(-1)?.hasta ?? 0) + 100, muestra: 5 }] })}>Agregar rango</Boton>
            </div>
          )}
          <div className="grid gap-3 sm:grid-cols-4">
            {(["critico", "mayor", "menor"] as const).map((s) => (
              <Campo key={s} etiqueta={`Defectos ${PLURAL[s]} que se aceptan`}><Entrada type="number" min={0} value={plan.aceptacion[s]} onChange={(e) => cambiar({ aceptacion: { ...plan.aceptacion, [s]: Number(e.target.value) } })} /></Campo>
            ))}
            <Campo etiqueta="Frente de productividad" ayuda="Donde se cuenta la inspección"><Entrada value={plan.frente} onChange={(e) => cambiar({ frente: e.target.value })} placeholder="F1" /></Campo>
          </div>
          <div>
            <p className="mb-1 text-[12.5px] font-semibold text-texto-2">Catálogo de defectos</p>
            {plan.defectos.map((d, i) => (
              <div key={i} className="mb-1 flex items-center gap-2">
                <Entrada className="flex-1" aria-label={`Defecto ${i + 1}`} value={d.nombre} onChange={(e) => cambiar({ defectos: plan.defectos.map((x, j) => (j === i ? { ...x, nombre: e.target.value } : x)) })} />
                <Selector className="w-56" aria-label={`Severidad del defecto ${i + 1}`} value={d.severidad} onChange={(e) => cambiar({ defectos: plan.defectos.map((x, j) => (j === i ? { ...x, severidad: e.target.value } : x)) })}>
                  {Object.entries(SEVERIDAD).map(([k, v]) => <option key={k} value={k}>{v.etiqueta}</option>)}
                </Selector>
                <Boton tamano="sm" variante="fantasma" icono={<Trash2 />} aria-label="Quitar defecto" onClick={() => cambiar({ defectos: plan.defectos.filter((_, j) => j !== i) })} />
              </div>
            ))}
            <Boton tamano="sm" variante="fantasma" icono={<Plus />} onClick={() => cambiar({ defectos: [...plan.defectos, { codigo: `defecto_${plan.defectos.length + 1}`, nombre: "", severidad: "menor" }] })}>Agregar defecto</Boton>
          </div>
          <Casilla etiqueta="Solo se entregan expedientes de lotes aceptados en la inspección" checked={plan.exigir_para_entrega} onChange={(e) => cambiar({ exigir_para_entrega: e.target.checked })} />
          <div className="flex flex-wrap items-end gap-3">
            <Campo etiqueta="Motivo" className="min-w-72 flex-1" requerido><Entrada value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Ej.: numeral de calidad del pliego" /></Campo>
            <Boton variante="primario" icono={<Save />} cargando={guardando} disabled={motivo.trim().length < 5} onClick={guardar}>Guardar el plan</Boton>
            {vista.vigente && <Boton variante="fantasma" onClick={() => (setPlan(vista.plan), setEditando(false))}>Cancelar</Boton>}
          </div>
        </div>
      )}
    </div>
  );
}
