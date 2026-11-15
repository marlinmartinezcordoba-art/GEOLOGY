"use client";

import { Check, ChevronDown, ChevronRight, ClipboardList, Plus, Save, Stethoscope, Trash2, Undo2 } from "lucide-react";
import { Fragment, useState } from "react";

import { ModalMotivo } from "@/components/ui/acciones";
import { useAvisos } from "@/components/ui/avisos";
import { Boton, Cargando, Insignia, Modal, Nota, Tabla, Vacio } from "@/components/ui/basicos";
import { Area, Campo, Casilla, Entrada, Selector } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { fechaHora, numero } from "@/lib/formato";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { ActividadAlistamiento, AvanceAlistamiento, DiagnosticoConservacion, ExpedienteAlistamiento, PlanAlistamientoVista, Proyecto } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

/** Alistamiento físico por expediente: actividades del proyecto, avance por caja y registro por caja o expediente. */
export function Alistamiento({ proyecto }: { proyecto: Proyecto }) {
  const { puede } = useSesion();
  const base = `/proyectos/${proyecto.id}/alistamiento`;
  const plan = useDatos(() => api<PlanAlistamientoVista>(`${base}/plan`), [base]);
  const avance = useDatos(() => api<AvanceAlistamiento>(`${base}/cajas`), [base]);
  const [abierta, setAbierta] = useState<string | null>(null);
  const [registrando, setRegistrando] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const opera = puede(PERMISOS.capturar) && !!plan.datos?.vigente;

  if (plan.cargando && !plan.datos) return <Cargando />;
  const a = avance.datos;
  const recargar = () => (avance.recargar(), setVersion((v) => v + 1));
  return (
    <div className="flex flex-col gap-5 p-5">
      <Nota tono="info">El alistamiento es el trabajo físico sobre cada expediente antes de digitalizarlo. Se registra por caja entera o expediente por expediente, con la cantidad cuando la actividad la pide; queda quién y cuándo. La hoja de control avisa lo que falte y si la foliación no coincide, y el paquete de entrega puede exigir el alistamiento completo.</Nota>
      {plan.datos && <PlanCard base={base} vista={plan.datos} alGuardar={() => (plan.recargar(), recargar())} />}
      {plan.datos?.vigente && a && (
        <>
          <p className="text-[13px] text-texto-2"><b>{numero(a.resumen.completos)}</b> de <b>{numero(a.resumen.expedientes)}</b> expedientes con el alistamiento obligatorio completo · {a.actividades.map((x) => `${x.nombre}: ${numero(a.resumen.por_actividad[x.codigo] ?? 0)}`).join(" · ")}</p>
          <p className="text-[13px] text-texto-2">Diagnóstico de conservación: <b>{numero(a.resumen.diagnostico.registrados)}</b> registrados · bueno {numero(a.resumen.diagnostico.bueno)} · regular {numero(a.resumen.diagnostico.regular)} · malo {numero(a.resumen.diagnostico.malo)}{a.resumen.diagnostico.aislar ? <span className="font-semibold text-critico"> · {numero(a.resumen.diagnostico.aislar)} por aislar (deterioro biológico)</span> : null}</p>
          {!a.cajas.length ? <Vacio icono={<ClipboardList />} titulo="El proyecto no tiene expedientes en el inventario" /> : (
            <Tabla className="rounded-xl border border-line">
              <thead><tr><th>Caja</th><th>Expedientes</th>{a.actividades.map((x) => <th key={x.codigo}>{x.nombre}</th>)}<th>Completos</th><th /></tr></thead>
              <tbody>
                {a.cajas.map((c) => (
                  <Fragment key={c.caja}>
                    <tr>
                      <td><button className="flex items-center gap-1 font-semibold" onClick={() => setAbierta(abierta === c.caja ? null : c.caja)}>{abierta === c.caja ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}{c.caja || "Sin caja"}</button></td>
                      <td className="tabular">{numero(c.expedientes)}</td>
                      {a.actividades.map((x) => {
                        const n = c.hechas[x.codigo] ?? 0;
                        return <td key={x.codigo} className="tabular">{n === c.expedientes ? <Insignia tono="ok">{n} de {c.expedientes}</Insignia> : <span className={n ? "text-texto-2" : "text-texto-3"}>{n} de {c.expedientes}</span>}</td>;
                      })}
                      <td className="tabular font-semibold">{c.completos} de {c.expedientes}</td>
                      <td className="text-right">{opera && <Boton tamano="sm" variante="primario" icono={<Check />} onClick={() => setRegistrando(c.caja)}>Registrar</Boton>}</td>
                    </tr>
                    {abierta === c.caja && (
                      <tr><td colSpan={a.actividades.length + 4} className="bg-canvas"><ExpedientesCaja key={version} base={base} caja={c.caja} actividades={a.actividades} opera={opera} alCambiar={recargar} /></td></tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </Tabla>
          )}
        </>
      )}
      {registrando !== null && a && <ModalRegistro base={base} caja={registrando} actividades={a.actividades} alCerrar={() => setRegistrando(null)} alGuardar={() => (setRegistrando(null), recargar())} />}
    </div>
  );
}

function ExpedientesCaja({ base, caja, actividades, opera, alCambiar }: { base: string; caja: string; actividades: ActividadAlistamiento[]; opera: boolean; alCambiar: () => void }) {
  const lista = useDatos(() => api<ExpedienteAlistamiento[]>(`${base}/expedientes`, { consulta: { caja } }), [base, caja]);
  const [deshaciendo, setDeshaciendo] = useState<{ unidad: string; actividad: string; nombre: string } | null>(null);
  const [diagnosticando, setDiagnosticando] = useState<ExpedienteAlistamiento | null>(null);
  if (!lista.datos) return <Cargando />;
  return (
    <div className="py-1">
      <table className="w-full text-[12.5px]">
        <thead><tr className="text-left text-texto-3"><th className="py-1 pr-3">Expediente</th><th className="py-1 pr-3">Conservación</th>{actividades.map((x) => <th key={x.codigo} className="py-1 pr-3">{x.nombre}</th>)}</tr></thead>
        <tbody>
          {lista.datos.map((e) => (
            <tr key={e.unidad_id} className="border-t border-line">
              <td className="py-1.5 pr-3"><span className="font-semibold">{e.identificador}</span> <span className="text-texto-3">{e.nombre}</span></td>
              <td className="py-1.5 pr-3">
                <button className="inline-flex items-center gap-1 hover:underline" disabled={!opera} onClick={() => setDiagnosticando(e)} title={e.diagnostico ? [...e.diagnostico.nombres, e.diagnostico.observacion].filter(Boolean).join(" · ") : "Registrar el diagnóstico"}>
                  {e.diagnostico ? <Insignia tono={e.diagnostico.aislar ? "critico" : e.diagnostico.estado === "bueno" ? "ok" : e.diagnostico.estado === "regular" ? "aviso" : "critico"}>{e.diagnostico.estado}{e.diagnostico.aislar ? " · aislar" : ""}</Insignia> : opera ? <span className="inline-flex items-center gap-1 text-marca"><Stethoscope className="size-3.5" />Diagnosticar</span> : <span className="text-texto-3">—</span>}
                </button>
              </td>
              {actividades.map((x) => {
                const h = e.hechas[x.codigo];
                return (
                  <td key={x.codigo} className="py-1.5 pr-3" title={h ? `${h.hecho_por ?? ""} · ${fechaHora(h.hecho_en)}${h.observacion ? ` · ${h.observacion}` : ""}` : ""}>
                    {h ? <span className="inline-flex items-center gap-1 text-ok"><Check className="size-3.5" />{h.cantidad != null ? numero(h.cantidad) : "hecho"}
                      {opera && <button className="text-texto-3 hover:text-critico" aria-label={`Deshacer ${x.nombre} de ${e.identificador}`} onClick={() => setDeshaciendo({ unidad: e.unidad_id, actividad: x.codigo, nombre: `${x.nombre} de ${e.identificador}` })}><Undo2 className="size-3.5" /></button>}
                    </span> : <span className="text-texto-3">—</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {diagnosticando && <ModalDiagnostico base={base} expediente={diagnosticando} alCerrar={() => setDiagnosticando(null)} alGuardar={() => (setDiagnosticando(null), lista.recargar(), alCambiar())} />}
      <ModalMotivo abierto={!!deshaciendo} titulo={`Deshacer: ${deshaciendo?.nombre ?? ""}`} descripcion="Queda en la auditoría con el motivo." boton="Deshacer" peligro
        alCerrar={() => setDeshaciendo(null)}
        alConfirmar={async (motivo) => { if (!deshaciendo) return; await api(`${base}/expedientes/${deshaciendo.unidad}/${deshaciendo.actividad}/deshacer`, { metodo: "POST", cuerpo: { motivo } }); setDeshaciendo(null); lista.recargar(); alCambiar(); }} />
    </div>
  );
}

function ModalRegistro({ base, caja, actividades, alCerrar, alGuardar }: { base: string; caja: string; actividades: ActividadAlistamiento[]; alCerrar: () => void; alGuardar: () => void }) {
  const avisos = useAvisos();
  const lista = useDatos(() => api<ExpedienteAlistamiento[]>(`${base}/expedientes`, { consulta: { caja } }), [base, caja]);
  const [actividad, setActividad] = useState(actividades.find((x) => x.obligatoria)?.codigo ?? actividades[0]?.codigo ?? "");
  const [elegidos, setElegidos] = useState<Record<string, boolean>>({});
  const [cantidades, setCantidades] = useState<Record<string, string>>({});
  const [observacion, setObservacion] = useState("");
  const [guardando, setGuardando] = useState(false);
  const a = actividades.find((x) => x.codigo === actividad);
  const filas = lista.datos ?? [];
  const marcado = (id: string) => elegidos[id] ?? true;
  const valor = (e: ExpedienteAlistamiento) => cantidades[e.unidad_id] ?? (e.hechas[actividad]?.cantidad ?? (a?.cantidad === "folios" ? e.folios_fuid : null))?.toString() ?? "";

  async function guardar() {
    setGuardando(true);
    try {
      const unidades = filas.filter((e) => marcado(e.unidad_id)).map((e) => e.unidad_id);
      const cuerpo = { actividad, unidades, observacion, cantidades: a?.cantidad !== "ninguna" ? Object.fromEntries(filas.filter((e) => marcado(e.unidad_id) && valor(e) !== "").map((e) => [e.unidad_id, Number(valor(e))])) : {} };
      const r = await api<{ registrados: number }>(`${base}/registrar`, { metodo: "POST", cuerpo });
      avisos.exito(`${a?.nombre}: ${numero(r.registrados)} expedientes de la caja ${caja || "sin caja"}.`);
      alGuardar();
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Modal abierto titulo={`Registrar alistamiento · caja ${caja || "sin caja"}`} descripcion="Marque los expedientes en los que se hizo la actividad." alCerrar={alCerrar} ancho="lg"
      pie={<><Boton variante="fantasma" onClick={alCerrar}>Cancelar</Boton><Boton variante="primario" icono={<Check />} cargando={guardando} disabled={!filas.some((e) => marcado(e.unidad_id))} onClick={guardar}>Registrar</Boton></>}>
      <Campo etiqueta="Actividad"><Selector value={actividad} onChange={(e) => (setActividad(e.target.value), setCantidades({}))}>{actividades.map((x) => <option key={x.codigo} value={x.codigo}>{x.nombre}</option>)}</Selector></Campo>
      {!lista.datos ? <Cargando /> : (
        <div className="mt-3 max-h-80 overflow-y-auto rounded-lg border border-line">
          {filas.map((e) => (
            <div key={e.unidad_id} className="flex items-center gap-3 border-b border-line px-3 py-1.5 last:border-b-0">
              <Casilla etiqueta={<span><b>{e.identificador}</b> <span className="text-texto-3">{e.nombre}</span></span>} checked={marcado(e.unidad_id)} onChange={(ev) => setElegidos({ ...elegidos, [e.unidad_id]: ev.target.checked })} className="flex-1" />
              {e.hechas[actividad] && <Insignia tono="ok">ya registrado</Insignia>}
              {a && a.cantidad !== "ninguna" && <Entrada className="w-24" type="number" min={0} aria-label={`${a.cantidad === "folios" ? "Folios" : "Unidades"} de ${e.identificador}`} placeholder={a.cantidad === "folios" ? "folios" : "unidades"} value={valor(e)} onChange={(ev) => setCantidades({ ...cantidades, [e.unidad_id]: ev.target.value })} />}
            </div>
          ))}
        </div>
      )}
      {a?.cantidad === "folios" && <p className="mt-1 text-[12px] text-texto-3">Se sugieren los folios del FUID: corríjalos con lo contado al foliar.</p>}
      <Campo etiqueta="Observación" className="mt-3"><Entrada value={observacion} onChange={(e) => setObservacion(e.target.value)} placeholder="Opcional" /></Campo>
    </Modal>
  );
}

function PlanCard({ base, vista, alGuardar }: { base: string; vista: PlanAlistamientoVista; alGuardar: () => void }) {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const dirige = puede(PERMISOS.proyectos);
  const [editando, setEditando] = useState(!vista.vigente && dirige);
  const [actividades, setActividades] = useState<ActividadAlistamiento[]>(vista.actividades);
  const [exigir, setExigir] = useState(vista.exigir_para_entrega);
  const [motivo, setMotivo] = useState("");
  const [guardando, setGuardando] = useState(false);
  const cambiar = (i: number, c: Partial<ActividadAlistamiento>) => setActividades(actividades.map((x, j) => (j === i ? { ...x, ...c } : x)));

  async function guardar() {
    setGuardando(true);
    try {
      await api(`${base}/plan`, { metodo: "PUT", cuerpo: { actividades, exigir_para_entrega: exigir, motivo } });
      avisos.exito("Actividades de alistamiento guardadas.");
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
        <span className="font-semibold text-titulo">Actividades de alistamiento {vista.vigente ? `· versión ${vista.version}` : ""}</span>
        {vista.vigente ? <Insignia tono="ok" punto>Vigente</Insignia> : <Insignia tono="aviso" punto>Sin plan: propuesta de ejemplo</Insignia>}
      </div>
      {!editando ? (
        <div className="mt-2 flex flex-col gap-1 text-[13px] text-texto-2">
          <span>{vista.actividades.map((x) => `${x.nombre}${x.cantidad !== "ninguna" ? ` (${x.cantidad})` : ""}${x.obligatoria ? "" : " · opcional"}`).join(" · ")}</span>
          {vista.exigir_para_entrega && <span className="text-[12px] text-texto-3">Solo se entregan expedientes con el alistamiento obligatorio completo.</span>}
          {vista.aviso && <span className="text-[12.5px] text-aviso">{vista.aviso}</span>}
          {dirige && <div className="mt-1"><Boton tamano="sm" onClick={() => setEditando(true)}>{vista.vigente ? "Cambiar" : "Revisar y guardar"}</Boton></div>}
        </div>
      ) : (
        <div className="mt-3 flex flex-col gap-2">
          {vista.aviso && <Nota tono="aviso">{vista.aviso}</Nota>}
          {actividades.map((x, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <Entrada className="min-w-64 flex-1" aria-label={`Actividad ${i + 1}`} value={x.nombre} onChange={(e) => cambiar(i, { nombre: e.target.value })} />
              <Selector className="w-44" aria-label={`Cantidad de la actividad ${i + 1}`} value={x.cantidad} onChange={(e) => cambiar(i, { cantidad: e.target.value as ActividadAlistamiento["cantidad"] })}>
                <option value="ninguna">Sin cantidad</option><option value="folios">Folios</option><option value="unidades">Unidades</option>
              </Selector>
              <Casilla etiqueta="Obligatoria" checked={x.obligatoria} onChange={(e) => cambiar(i, { obligatoria: e.target.checked })} />
              <Boton tamano="sm" variante="fantasma" icono={<Trash2 />} aria-label="Quitar actividad" onClick={() => setActividades(actividades.filter((_, j) => j !== i))} />
            </div>
          ))}
          <div><Boton tamano="sm" variante="fantasma" icono={<Plus />} onClick={() => setActividades([...actividades, { codigo: `actividad_${actividades.length + 1}`, nombre: "", cantidad: "ninguna", obligatoria: true }])}>Agregar actividad</Boton></div>
          <Casilla etiqueta="Solo se entregan expedientes con el alistamiento obligatorio completo" checked={exigir} onChange={(e) => setExigir(e.target.checked)} />
          <div className="flex flex-wrap items-end gap-3">
            <Campo etiqueta="Motivo" className="min-w-72 flex-1" requerido><Entrada value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Ej.: actividades del anexo técnico" /></Campo>
            <Boton variante="primario" icono={<Save />} cargando={guardando} disabled={motivo.trim().length < 5} onClick={guardar}>Guardar</Boton>
            {vista.vigente && <Boton variante="fantasma" onClick={() => (setActividades(vista.actividades), setEditando(false))}>Cancelar</Boton>}
          </div>
        </div>
      )}
    </div>
  );
}

function ModalDiagnostico({ base, expediente, alCerrar, alGuardar }: { base: string; expediente: ExpedienteAlistamiento; alCerrar: () => void; alGuardar: () => void }) {
  const avisos = useAvisos();
  const catalogo = useDatos(() => api<{ estados: Record<string, string>; hallazgos: Record<string, { nombre: string; aislar: boolean }> }>(`${base}/diagnostico/catalogo`), [base]);
  const d = expediente.diagnostico;
  const [estado, setEstado] = useState<DiagnosticoConservacion["estado"]>(d?.estado ?? "bueno");
  const [hallazgos, setHallazgos] = useState<string[]>(d?.hallazgos ?? []);
  const [folios, setFolios] = useState(d?.folios_afectados?.toString() ?? "");
  const [observacion, setObservacion] = useState(d?.observacion ?? "");
  const [guardando, setGuardando] = useState(false);

  async function guardar() {
    setGuardando(true);
    try {
      await api(`${base}/expedientes/${expediente.unidad_id}/diagnostico`, { metodo: "PUT", cuerpo: { estado, hallazgos: estado === "bueno" ? [] : hallazgos, folios_afectados: folios ? Number(folios) : null, observacion } });
      avisos.exito(`Diagnóstico de ${expediente.identificador} registrado.`);
      alGuardar();
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Modal abierto titulo={`Diagnóstico de conservación · ${expediente.identificador}`} descripcion={expediente.nombre} alCerrar={alCerrar} ancho="lg"
      pie={<><Boton variante="fantasma" onClick={alCerrar}>Cancelar</Boton><Boton variante="primario" icono={<Stethoscope />} cargando={guardando} onClick={guardar}>Registrar</Boton></>}>
      {!catalogo.datos ? <Cargando /> : (
        <div className="flex flex-col gap-3">
          <Campo etiqueta="Estado general">
            <Selector value={estado} onChange={(e) => setEstado(e.target.value as DiagnosticoConservacion["estado"])}>{Object.entries(catalogo.datos.estados).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Selector>
          </Campo>
          {estado !== "bueno" && (
            <div className="grid gap-1.5 sm:grid-cols-2">
              {Object.entries(catalogo.datos.hallazgos).map(([k, v]) => (
                <Casilla key={k} etiqueta={<span>{v.nombre}{v.aislar && <span className="text-critico"> · aislar</span>}</span>} checked={hallazgos.includes(k)}
                  onChange={(e) => setHallazgos(e.target.checked ? [...hallazgos, k] : hallazgos.filter((x) => x !== k))} />
              ))}
            </div>
          )}
          <Campo etiqueta="Folios afectados" className="w-40"><Entrada type="number" min={0} value={folios} onChange={(e) => setFolios(e.target.value)} /></Campo>
          <Campo etiqueta="Observación"><Area className="min-h-16" value={observacion} onChange={(e) => setObservacion(e.target.value)} placeholder="Qué se encontró y dónde" /></Campo>
        </div>
      )}
    </Modal>
  );
}
