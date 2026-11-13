"use client";

import { AlertTriangle, CheckCheck, CircleAlert, Eye, Plus, RefreshCw, RotateCcw, Send, ShieldCheck, Undo2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ModalMotivo } from "@/components/ui/acciones";
import { useAvisos } from "@/components/ui/avisos";
import { Boton, CajaError, Cargando, EncabezadoPagina, Insignia, Nota, Tarjeta } from "@/components/ui/basicos";
import { Area, Entrada } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { Tono } from "@/lib/tonos";
import type { DetalleDescripcion, OrigenDato } from "@/lib/tipos";

import { NOMBRE_ESTADO_DESC, TONO_ESTADO_DESC } from "../../descripciones";

const FUENTE: Record<string, { etiqueta: string; tono: Tono }> = {
  persona: { etiqueta: "Persona", tono: "marca" }, calculado: { etiqueta: "Calculado", tono: "motor" }, trd: { etiqueta: "TRD", tono: "info" },
  clasificacion: { etiqueta: "Clasificación", tono: "info" }, fuid: { etiqueta: "FUID", tono: "neutro" }, hoja_control: { etiqueta: "Hoja de control verificada", tono: "ok" },
  ocr: { etiqueta: "OCR · por confirmar", tono: "ia" }, propuesta: { etiqueta: "Propuesta · por confirmar", tono: "ia" }, digitalizacion: { etiqueta: "Digitalización", tono: "motor" },
};

function Origen({ o }: { o?: OrigenDato }) {
  if (!o) return <span className="text-[11px] text-texto-3">sin origen registrado</span>;
  const f = FUENTE[o.fuente] ?? { etiqueta: o.fuente, tono: "neutro" as Tono };
  return <span className="inline-flex flex-wrap items-center gap-1 text-[11px] text-texto-3"><Insignia tono={f.tono}>{f.etiqueta}</Insignia><span>{o.detalle}</span></span>;
}

/** Descripción ISAD(G) de un expediente: elementos por área con su origen, revisión según la norma y aprobación por otra persona. */
export default function DescripcionIsad() {
  const { id, unidad } = useParams<{ id: string; unidad: string }>();
  const { puede, usuario } = useSesion();
  const avisos = useAvisos();
  const base = `/proyectos/${id}/descripciones/unidades/${unidad}`;
  const [d, setD] = useState<DetalleDescripcion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [trabajando, setTrabajando] = useState<string | null>(null);
  const [observaciones, setObservaciones] = useState<Record<string, string>>({});
  const [motivo, setMotivo] = useState<"devolver" | "reabrir" | null>(null);

  const cargar = useCallback(() => api<DetalleDescripcion>(base).then(setD).catch((e) => setError(e.message)), [base]);
  useEffect(() => {
    void cargar();
  }, [cargar]);
  const areas = useMemo(() => {
    const salida: Record<string, DetalleDescripcion["elementos"]> = {};
    for (const e of d?.elementos ?? []) (salida[e.area] ??= []).push(e);
    return salida;
  }, [d]);

  async function hacer(clave: string, fn: () => Promise<DetalleDescripcion>, mensaje?: string) {
    setTrabajando(clave);
    try {
      setD(await fn());
      if (mensaje) avisos.exito(mensaje);
    } catch (e) {
      avisos.error((e as Error).message);
    } finally {
      setTrabajando(null);
    }
  }
  const post = (ruta: string, cuerpo?: unknown) => api<DetalleDescripcion>(`${base}${ruta}`, { metodo: "POST", cuerpo });

  if (error) return <CajaError mensaje={error} reintentar={() => (setError(null), void cargar())} />;
  if (!d) return <Cargando />;
  const desc = d.descripcion;
  const editable = !!desc && (desc.estado === "borrador" || desc.estado === "devuelta") && puede(PERMISOS.describir);
  const aprueba = !!desc && desc.estado === "en_revision" && puede(PERMISOS.aprobarDescripcion) && usuario.id !== desc.enviada_por && usuario.id !== desc.creado_por;
  const r = d.revision;
  const bloqueada = !!r && (r.devuelve > 0 || r.por_confirmar.length > 0);

  return (
    <div className="flex flex-col gap-5">
      <EncabezadoPagina
        volver={{ href: `/proyectos/${id}`, texto: "Proyecto" }}
        titulo={<span className="flex flex-wrap items-center gap-3">Descripción ISAD(G) · {d.unidad.identificador}{desc && <Insignia tono={TONO_ESTADO_DESC[desc.estado]} punto>{NOMBRE_ESTADO_DESC[desc.estado]}</Insignia>}</span>}
        descripcion={`${d.unidad.nombre} · caja ${d.unidad.caja ?? "—"} · carpeta ${d.unidad.carpeta ?? "—"} · ${d.procesos.lote ? `lote ${d.procesos.lote}` : "sin lote"} (${d.procesos.origen})`}
        acciones={
          <div className="flex flex-wrap gap-2">
            <Link href={`/proyectos/${id}/hojas/${unidad}`} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-[13px] font-semibold text-marca hover:bg-marca-suave"><Eye className="size-4" />Ver los documentos</Link>
            {editable && <Boton icono={<RefreshCw />} cargando={trabajando === "recalcular"} onClick={() => hacer("recalcular", () => post("/recalcular"), "Recalculado. Lo que usted escribió se conservó.")}>Recalcular lo deducido</Boton>}
            {editable && <Boton variante="primario" icono={<Send />} cargando={trabajando === "enviar"} disabled={bloqueada} onClick={() => hacer("enviar", () => post("/enviar"), "Enviada a revisión.")}>Enviar a revisión</Boton>}
            {aprueba && <Boton icono={<Undo2 />} onClick={() => setMotivo("devolver")}>Devolver</Boton>}
            {aprueba && <Boton variante="primario" icono={<ShieldCheck />} cargando={trabajando === "aprobar"} onClick={() => hacer("aprobar", () => post("/aprobar"), "Descripción aprobada.")}>Aprobar</Boton>}
            {desc?.estado === "aprobada" && puede(PERMISOS.aprobarDescripcion) && <Boton icono={<RotateCcw />} onClick={() => setMotivo("reabrir")}>Reabrir</Boton>}
          </div>
        }
      />
      {d.avisos.map((a) => <Nota key={a} tono="aviso">{a}</Nota>)}
      {desc?.novedad && <Nota tono={desc.estado === "devuelta" ? "critico" : "info"}>{desc.estado === "devuelta" ? "Devuelta: " : ""}{desc.novedad}</Nota>}
      {aprueba && <Nota tono="info">Revise cada elemento con los documentos a la vista («Ver los documentos»). Escriba una observación en los que haya que corregir y devuelva; si todo está bien, apruebe.</Nota>}

      {!desc ? (
        <Tarjeta className="p-5">
          <p className="font-semibold text-titulo">Esta unidad todavía no está descrita</p>
          <p className="mt-1 text-[13px] text-texto-2">
            {d.procesos.isadg ? "ARCA calcula lo deducible (código, fechas, volumen, productor, valoración, acceso, copias) y propone el título y el alcance a partir de lo digitalizado." : `Esta unidad no lleva descripción ISAD(G) según la ${d.procesos.origen}.`}
          </p>
          {d.procesos.isadg && puede(PERMISOS.describir) && <Boton className="mt-3" variante="primario" icono={<Plus />} cargando={trabajando === "crear"} onClick={() => hacer("crear", () => post(""), "Descripción creada.")}>Describir</Boton>}
        </Tarjeta>
      ) : (
        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <div className="flex min-w-0 flex-col gap-4">
            {Object.entries(areas).map(([area, elementos]) => (
              <Tarjeta key={area} className="p-4">
                <p className="mb-2 font-semibold text-titulo">Área de {area.toLowerCase()}</p>
                <div className="divide-y divide-line">
                  {elementos.map((e) => {
                    const valor = desc.campos[e.clave] ?? "";
                    const o = desc.origen[e.clave];
                    const porConfirmar = o && (o.fuente === "propuesta" || o.fuente === "ocr");
                    const largo = ["titulo", "alcance", "historia_archivistica", "valoracion", "notas", "organizacion", "volumen", "productor"].includes(e.clave);
                    return (
                      <div key={e.clave} className="grid gap-1 py-2.5 md:grid-cols-[190px_minmax(0,1fr)]">
                        <div><p className="text-[12.5px] font-semibold text-titulo">{e.etiqueta}</p><p className="text-[11px] text-texto-3">{e.numero}</p></div>
                        <div className="min-w-0">
                          {editable && e.editable ? (
                            largo ? <Area key={valor} defaultValue={valor} aria-label={e.etiqueta} className="min-h-16" onBlur={(ev) => ev.target.value !== valor && hacer(`g-${e.clave}`, () => api<DetalleDescripcion>(base, { metodo: "PATCH", cuerpo: { campos: { [e.clave]: ev.target.value } } }))} />
                              : <Entrada key={valor} defaultValue={valor} aria-label={e.etiqueta} onBlur={(ev) => ev.target.value !== valor && hacer(`g-${e.clave}`, () => api<DetalleDescripcion>(base, { metodo: "PATCH", cuerpo: { campos: { [e.clave]: ev.target.value } } }))} />
                          ) : <p className="text-[13.5px] whitespace-pre-wrap text-titulo">{valor || <span className="text-texto-3">—</span>}</p>}
                          <div className="mt-1 flex flex-wrap items-center gap-2">
                            <Origen o={o} />
                            {editable && porConfirmar && <Boton tamano="sm" variante="motor" icono={<CheckCheck />} onClick={() => hacer(`c-${e.clave}`, () => post("/confirmar", { elemento: e.clave }), `${e.etiqueta}: confirmado.`)}>Confirmar</Boton>}
                          </div>
                          {desc.observaciones[e.clave] && <p className="mt-1 flex items-center gap-1 rounded-lg bg-critico-suave px-2 py-1 text-[12.5px] text-critico"><CircleAlert className="size-4" />Observación de la revisión: {desc.observaciones[e.clave]}</p>}
                          {aprueba && <Entrada className="mt-1" placeholder="Observación (opcional)" aria-label={`Observación ${e.etiqueta}`} value={observaciones[e.clave] ?? ""} onChange={(ev) => setObservaciones((x) => ({ ...x, [e.clave]: ev.target.value }))} />}
                        </div>
                      </div>
                    );
                  })}
                  {desc.campos.nota_archivero && (
                    <div className="grid gap-1 py-2.5 md:grid-cols-[190px_minmax(0,1fr)]">
                      <div><p className="text-[12.5px] font-semibold text-titulo">Nota del archivero</p><p className="text-[11px] text-texto-3">3.7.1 · 3.7.3</p></div>
                      <p className="text-[13.5px] text-titulo">{desc.campos.nota_archivero} {desc.campos.fecha_descripcion}</p>
                    </div>
                  )}
                </div>
              </Tarjeta>
            ))}
          </div>
          <div className="flex min-w-0 flex-col gap-4 xl:sticky xl:top-4">
            <Tarjeta className="p-4">
              <p className="mb-2 font-semibold text-titulo">Revisión según la norma</p>
              {r && (
                <>
                  <p className="mb-2 text-[12.5px] text-texto-2">{r.devuelve ? `${r.devuelve} incumplimientos (impiden enviar)` : "Sin incumplimientos"} · {r.revise} para mirar{r.por_confirmar.length ? ` · ${r.por_confirmar.length} propuestas por confirmar` : ""}</p>
                  {!r.hallazgos.length && !r.por_confirmar.length && <Nota tono="ok">La descripción cumple las reglas de revisión.</Nota>}
                  {r.por_confirmar.length > 0 && <Nota tono="aviso">Por confirmar: {r.por_confirmar.map((k) => d.elementos.find((e) => e.clave === k)?.etiqueta ?? k).join(", ")}. Escríbalos o confírmelos.</Nota>}
                  <ul className="mt-2 flex flex-col gap-2">
                    {r.hallazgos.map((h, i) => (
                      <li key={i} className={`rounded-lg border px-3 py-2 text-[12.5px] ${h.gravedad === "DEVUELVE" ? "border-critico/40 bg-critico-suave" : "border-aviso/40 bg-aviso-suave"}`}>
                        <p className="flex items-center gap-1 font-semibold"><AlertTriangle className="size-3.5" />{h.gravedad === "DEVUELVE" ? "Incumple" : "Revise"} · {h.regla}</p>
                        <p className="mt-0.5">{h.que_pasa}</p>
                        <p className="mt-0.5 text-texto-2">{h.como_se_arregla}</p>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </Tarjeta>
          </div>
        </div>
      )}

      <ModalMotivo
        abierto={motivo !== null}
        titulo={motivo === "devolver" ? "Devolver la descripción" : "Reabrir la descripción aprobada"}
        descripcion={motivo === "devolver" ? `Se envían también las observaciones que escribió en ${Object.values(observaciones).filter((x) => x.trim()).length} elementos.` : "Vuelve a elaboración. La aprobación anterior queda en la auditoría."}
        boton={motivo === "devolver" ? "Devolver" : "Reabrir"}
        alCerrar={() => setMotivo(null)}
        alConfirmar={async (m) => {
          setD(await post(motivo === "devolver" ? "/devolver" : "/reabrir", motivo === "devolver" ? { motivo: m, observaciones } : { motivo: m }));
          setObservaciones({});
          avisos.exito(motivo === "devolver" ? "Descripción devuelta." : "Descripción reabierta.");
        }}
      />
    </div>
  );
}
