"use client";

import { Archive, ArrowRightLeft, Ban, Building2, CheckCheck, Download, Eye, Landmark, MapPin, Plus, Send, Trash2, Undo2 } from "lucide-react";
import { useState } from "react";

import { ModalMotivo } from "@/components/ui/acciones";
import { useAvisos } from "@/components/ui/avisos";
import { Boton, Cargando, Codigo, Indicador, Insignia, Modal, Nota, Tabla, Vacio } from "@/components/ui/basicos";
import { Area, Campo, Entrada, Selector } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { descargarArchivo } from "@/lib/descargas";
import { fecha, fechaHora, numero } from "@/lib/formato";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { CandidataTransferencia, PlanTransferencias, Proyecto, Transferencia, UnidadTransferencia } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

const TIPO = { primaria: "Primaria · gestión → central", secundaria: "Secundaria · central → histórico" } as const;
const FASE = { gestion: "Archivo de gestión", central: "Archivo central", historico: "Archivo histórico" } as const;
const ESTADO = { borrador: "neutro", enviada: "aviso", devuelta: "critico", recibida: "ok", anulada: "neutro" } as const;
const hoy = () => new Date().toISOString().slice(0, 10);

/** Transferencias documentales: plan a la fecha de corte, preparación, envío, recepción por unidad e inventario FUID. */
export function Transferencias({ proyecto }: { proyecto: Proyecto }) {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const base = `/proyectos/${proyecto.id}/transferencias`;
  const [corte, setCorte] = useState(hoy());
  const plan = useDatos(() => api<PlanTransferencias>(`${base}/plan`, { consulta: { fecha_corte: corte } }), [base, corte]);
  const lista = useDatos(() => api<Transferencia[]>(base), [base]);
  const [abierta, setAbierta] = useState<string | null>(null);
  const [partida, setPartida] = useState(false);
  const [creando, setCreando] = useState<string | null>(null);
  const gestiona = puede(PERMISOS.transferir);
  const recargar = () => (void plan.recargar(), void lista.recargar());

  async function crear(tipo: "primaria" | "secundaria", codigo = "") {
    setCreando(`${tipo}-${codigo}`);
    try {
      const t = await api<Transferencia>(base, { metodo: "POST", cuerpo: { tipo, fecha_corte: corte, codigo_dependencia: codigo } });
      avisos.exito(`Transferencia n.º ${t.numero} creada con ${numero(t.resumen.unidades)} unidades.`);
      recargar();
      setAbierta(t.id);
    } catch (e) {
      avisos.error((e as Error).message);
    } finally {
      setCreando(null);
    }
  }

  const p = plan.datos;
  if (!p) return <Cargando />;
  return (
    <div className="flex flex-col gap-5 p-5">
      <Nota tono="info">
        Se transfiere lo clasificado y confirmado que cumplió la retención a la fecha de corte: la primaria cuenta el tiempo en gestión (AG); la secundaria suma el de central (AC) y solo lleva lo que tiene conservación total, selección o digitalización. Quien envía no recibe. Lo recibido cambia de fase; lo devuelto se queda con su observación.
      </Nota>
      <div className="grid gap-3 sm:grid-cols-4">
        <Indicador etiqueta="Archivo de gestión" valor={numero(p.fases.gestion)} icono={<Building2 />} />
        <Indicador etiqueta="Archivo central" valor={numero(p.fases.central)} tono="info" icono={<Archive />} />
        <Indicador etiqueta="Archivo histórico" valor={numero(p.fases.historico)} tono="ok" icono={<Landmark />} />
        <Indicador etiqueta="Sin clasificación confirmada" valor={numero(p.sin_clasificar)} tono="neutro" detalle="No se pueden transferir todavía" icono={<ArrowRightLeft />} />
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <Campo etiqueta="Fecha de corte" ayuda="Se transfiere lo que cumplió su retención en esta fecha."><Entrada type="date" value={corte} onChange={(e) => setCorte(e.target.value || hoy())} /></Campo>
        {gestiona && <Boton icono={<MapPin />} onClick={() => setPartida(true)}>Registrar fase de partida</Boton>}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {(["primaria", "secundaria"] as const).map((tipo) => {
          const g = p.tipos[tipo];
          return (
            <section key={tipo} className="rounded-xl border border-line bg-surface shadow-xs">
              <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
                <div>
                  <p className="font-semibold text-titulo">Transferencia {TIPO[tipo].toLowerCase()}</p>
                  <p className="text-[12.5px] text-texto-3">{numero(g.elegibles)} unidades cumplen · {numero(g.anticipables)} aún no cumplen · {numero(g.sin_calendario)} sin calendario</p>
                </div>
                {gestiona && g.elegibles > 0 && <Boton tamano="sm" variante="primario" icono={<Plus />} cargando={creando === `${tipo}-`} onClick={() => crear(tipo)}>Preparar con todas</Boton>}
              </header>
              {!g.por_dependencia.length ? <p className="px-4 py-4 text-[13px] text-texto-3">Nada por transferir a esta fecha de corte.</p> : (
                <Tabla>
                  <thead><tr><th>Dependencia</th><th>Unidades</th><th>Folios</th><th /></tr></thead>
                  <tbody>
                    {g.por_dependencia.map((d) => (
                      <tr key={d.codigo}>
                        <td><Codigo>{d.codigo}</Codigo> {d.dependencia}</td>
                        <td className="tabular">{numero(d.elegibles)}</td>
                        <td className="tabular">{numero(d.folios)}</td>
                        <td className="text-right">{gestiona && <Boton tamano="sm" variante="fantasma" icono={<Plus />} cargando={creando === `${tipo}-${d.codigo}`} onClick={() => crear(tipo, d.codigo)}>Preparar</Boton>}</td>
                      </tr>
                    ))}
                  </tbody>
                </Tabla>
              )}
            </section>
          );
        })}
      </div>
      <div>
        <p className="mb-2 font-semibold text-titulo">Transferencias</p>
        {!lista.datos?.length ? <Vacio icono={<ArrowRightLeft />} titulo="Todavía no hay transferencias" /> : (
          <Tabla className="rounded-xl border border-line">
            <thead><tr><th>N.º</th><th>Tipo</th><th>Dependencia</th><th>Corte</th><th>Estado</th><th>Unidades</th><th>Folios</th><th>Cajas</th><th /></tr></thead>
            <tbody>
              {lista.datos.map((t) => (
                <tr key={t.id}>
                  <td className="font-semibold">{t.numero}</td>
                  <td>{TIPO[t.tipo]}</td>
                  <td>{t.dependencia || <span className="text-texto-3">Todas</span>}</td>
                  <td className="whitespace-nowrap">{fecha(t.fecha_corte)}</td>
                  <td><Insignia tono={ESTADO[t.estado]} punto>{t.estado}</Insignia></td>
                  <td className="tabular">{numero(t.resumen.unidades)}{t.resumen.anticipadas ? <span className="text-[11.5px] text-aviso"> · {t.resumen.anticipadas} anticipadas</span> : null}</td>
                  <td className="tabular">{numero(t.resumen.folios)}</td>
                  <td className="tabular">{numero(t.resumen.cajas)}</td>
                  <td><Boton tamano="sm" variante="fantasma" icono={<Eye />} onClick={() => setAbierta(t.id)}>Abrir</Boton></td>
                </tr>
              ))}
            </tbody>
          </Tabla>
        )}
      </div>
      {abierta && <Detalle base={base} proyecto={proyecto} id={abierta} alCerrar={() => setAbierta(null)} alCambiar={recargar} />}
      {partida && <FaseDePartida base={base} alCerrar={() => setPartida(false)} alRegistrar={recargar} />}
    </div>
  );
}

function Detalle({ base, proyecto, id, alCerrar, alCambiar }: { base: string; proyecto: Proyecto; id: string; alCerrar: () => void; alCambiar: () => void }) {
  const { puede, usuario } = useSesion();
  const avisos = useAvisos();
  const d = useDatos(() => api<{ transferencia: Transferencia; unidades: UnidadTransferencia[] }>(`${base}/${id}`), [id]);
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set());
  const [devolver, setDevolver] = useState<Record<string, string>>({});
  const [agregando, setAgregando] = useState(false);
  const [motivoModal, setMotivoModal] = useState<"anular" | "devolver" | null>(null);
  const [trabajando, setTrabajando] = useState<string | null>(null);
  const [nota, setNota] = useState("");
  const t = d.datos?.transferencia;
  const editable = t && (t.estado === "borrador" || t.estado === "devuelta") && puede(PERMISOS.transferir);
  const recibe = t?.estado === "enviada" && puede(PERMISOS.recibirTransferencia) && t.enviada_por !== usuario.id;
  const recargar = () => (setMarcadas(new Set()), void d.recargar(), alCambiar());

  async function hacer(clave: string, fn: () => Promise<string>) {
    setTrabajando(clave);
    try {
      avisos.exito(await fn());
      recargar();
    } catch (e) {
      avisos.error((e as Error).message);
    } finally {
      setTrabajando(null);
    }
  }
  const quitar = () => hacer("quitar", async () => `${(await api<{ quitadas: number }>(`${base}/${id}/quitar`, { metodo: "POST", cuerpo: { unidades: [...marcadas] } })).quitadas} unidades quitadas.`);
  const enviar = () => hacer("enviar", async () => (await api(`${base}/${id}/enviar`, { metodo: "POST" }), "Transferencia enviada. Ahora la recibe el archivo receptor."));
  const recibir = () =>
    hacer("recibir", async () => {
      const r = await api<{ recibidas: number; devueltas: number }>(`${base}/${id}/recibir`, {
        metodo: "POST", cuerpo: { devueltas: Object.entries(devolver).map(([unidad_id, observacion]) => ({ unidad_id, observacion })), motivo: nota },
      });
      setDevolver({});
      return `${numero(r.recibidas)} recibidas · ${numero(r.devueltas)} devueltas.`;
    });
  async function inventario() {
    setTrabajando("inventario");
    try {
      const e = await api<{ expedicion_id: string; nombre_archivo: string }>(`${base}/${id}/inventario`, { metodo: "POST" });
      await descargarArchivo(`/proyectos/${proyecto.id}/entregables/${e.expedicion_id}/archivo`, e.nombre_archivo);
      avisos.exito("Inventario expedido en el FUID de la entidad. Queda también en Entregables.");
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setTrabajando(null);
    }
  }

  const todas = !!d.datos?.unidades.length && d.datos.unidades.every((u) => marcadas.has(u.unidad_id));
  return (
    <Modal abierto ancho="xl" alCerrar={alCerrar} titulo={t ? `Transferencia n.º ${t.numero} · ${TIPO[t.tipo]}` : "Transferencia"}
      descripcion={t && <span className="flex flex-wrap items-center gap-2"><Insignia tono={ESTADO[t.estado]} punto>{t.estado}</Insignia>{t.dependencia || "Todas las dependencias"} · corte {fecha(t.fecha_corte)}{t.enviada_en ? ` · enviada ${fechaHora(t.enviada_en)}` : ""}{t.recibida_en ? ` · recibida ${fechaHora(t.recibida_en)}` : ""}</span>}
      pie={<Boton onClick={alCerrar}>Cerrar</Boton>}>
      {!d.datos || !t ? <Cargando /> : (
        <div className="flex flex-col gap-4">
          {t.novedad && <Nota tono={t.estado === "devuelta" ? "critico" : "info"}>{t.estado === "devuelta" ? "Devuelta: " : "Novedad: "}{t.novedad}</Nota>}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] text-texto-2"><b>{numero(t.resumen.unidades)}</b> unidades · <b>{numero(t.resumen.folios)}</b> folios · <b>{numero(t.resumen.cajas)}</b> {t.resumen.cajas === 1 ? "caja" : "cajas"}</span>
            <div className="ml-auto flex flex-wrap gap-2">
              <Boton tamano="sm" icono={<Download />} cargando={trabajando === "inventario"} disabled={!t.resumen.unidades} onClick={inventario}>Inventario FUID</Boton>
              {editable && <Boton tamano="sm" icono={<Plus />} onClick={() => setAgregando(true)}>Agregar unidades</Boton>}
              {editable && marcadas.size > 0 && <Boton tamano="sm" icono={<Trash2 />} cargando={trabajando === "quitar"} onClick={quitar}>Quitar ({marcadas.size})</Boton>}
              {editable && <Boton tamano="sm" icono={<Ban />} onClick={() => setMotivoModal("anular")}>Anular</Boton>}
              {editable && <Boton tamano="sm" variante="primario" icono={<Send />} cargando={trabajando === "enviar"} disabled={!t.resumen.unidades} onClick={enviar}>Enviar</Boton>}
              {recibe && <Boton tamano="sm" icono={<Undo2 />} onClick={() => setMotivoModal("devolver")}>Devolver completa</Boton>}
            </div>
          </div>
          {t.estado === "enviada" && !recibe && <Nota tono="aviso">La recibe otra persona con el permiso de recibir transferencias (quien envía no recibe).</Nota>}
          {recibe && (
            <Nota tono="info">Revise cada unidad. Marque «Devolver» y escriba la observación en las que no recibe (faltan folios, sin rótulo…); todas las demás quedan recibidas y pasan a {FASE[t.tipo === "primaria" ? "central" : "historico"].toLowerCase()}.</Nota>
          )}
          <Tabla className="rounded-xl border border-line">
            <thead>
              <tr>
                {editable && <th className="w-8"><input type="checkbox" aria-label="Marcar todas" checked={todas} onChange={() => setMarcadas(todas ? new Set() : new Set(d.datos!.unidades.map((u) => u.unidad_id)))} /></th>}
                <th>Unidad</th><th>Caja · carpeta</th><th>Fechas</th><th>Folios</th><th>Estado</th>{recibe && <th>Devolver</th>}
              </tr>
            </thead>
            <tbody>
              {d.datos.unidades.map((u) => (
                <tr key={u.unidad_id}>
                  {editable && <td><input type="checkbox" aria-label={`Marcar ${u.identificador}`} checked={marcadas.has(u.unidad_id)} onChange={() => setMarcadas((m) => { const n = new Set(m); if (n.has(u.unidad_id)) n.delete(u.unidad_id); else n.add(u.unidad_id); return n; })} /></td>}
                  <td className="min-w-52"><p className="font-semibold text-titulo">{u.identificador}</p><p className="text-[12.5px]">{u.nombre}</p>{u.aviso && <p className="text-[11.5px] text-aviso">{u.aviso}</p>}</td>
                  <td className="whitespace-nowrap">{u.caja ?? "—"} · {u.carpeta ?? "—"}</td>
                  <td className="text-[12.5px]">{fecha(u.fecha_inicial)} – {fecha(u.fecha_final)}</td>
                  <td className="tabular">{u.folios ?? <span className="text-critico">falta</span>}</td>
                  <td>
                    <Insignia tono={u.estado === "recibida" ? "ok" : u.estado === "devuelta" ? "critico" : "neutro"}>{u.estado === "incluida" ? FASE[u.fase] : u.estado}</Insignia>
                    {u.observacion && <p className="text-[11.5px] text-texto-3">{u.observacion}</p>}
                  </td>
                  {recibe && (
                    <td className="min-w-44">
                      <label className="flex items-center gap-1.5 text-[12.5px]">
                        <input type="checkbox" aria-label={`Devolver ${u.identificador}`} checked={u.unidad_id in devolver} onChange={(e) => setDevolver((v) => { const n = { ...v }; if (e.target.checked) n[u.unidad_id] = ""; else delete n[u.unidad_id]; return n; })} />
                        Devolver
                      </label>
                      {u.unidad_id in devolver && <Entrada className="mt-1" placeholder="Observación" aria-label={`Observación ${u.identificador}`} value={devolver[u.unidad_id]} onChange={(e) => setDevolver((v) => ({ ...v, [u.unidad_id]: e.target.value }))} />}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </Tabla>
          {recibe && (
            <div className="flex flex-wrap items-end gap-3">
              <Campo etiqueta="Novedad de la recepción" className="min-w-80 flex-1"><Entrada value={nota} onChange={(e) => setNota(e.target.value)} placeholder="Opcional" /></Campo>
              <Boton variante="primario" icono={<CheckCheck />} cargando={trabajando === "recibir"} disabled={Object.values(devolver).some((o) => o.trim().length < 5)} onClick={recibir}>
                Recibir {numero(d.datos.unidades.length - Object.keys(devolver).length)} unidades
              </Boton>
            </div>
          )}
        </div>
      )}
      {agregando && t && <Agregar base={base} t={t} alCerrar={() => setAgregando(false)} alAgregar={recargar} />}
      <ModalMotivo
        abierto={motivoModal !== null}
        titulo={motivoModal === "anular" ? "Anular la transferencia" : "Devolver la transferencia completa"}
        descripcion={motivoModal === "anular" ? "Las unidades quedan libres para otra transferencia." : "Vuelve a quien la preparó para corregirla y reenviarla. Ninguna unidad cambia de fase."}
        boton={motivoModal === "anular" ? "Anular" : "Devolver"}
        peligro={motivoModal === "anular"}
        alCerrar={() => setMotivoModal(null)}
        alConfirmar={async (motivo) => {
          await api(`${base}/${id}/${motivoModal === "anular" ? "anular" : "devolver"}`, { metodo: "POST", cuerpo: { motivo } });
          avisos.exito(motivoModal === "anular" ? "Transferencia anulada." : "Transferencia devuelta.");
          recargar();
        }}
      />
    </Modal>
  );
}

function Agregar({ base, t, alCerrar, alAgregar }: { base: string; t: Transferencia; alCerrar: () => void; alAgregar: () => void }) {
  const avisos = useAvisos();
  const [q, setQ] = useState("");
  const c = useDatos(() => api<CandidataTransferencia[]>(`${base}/${t.id}/candidatas`, { consulta: { q } }), [q]);
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set());
  const [enviando, setEnviando] = useState(false);
  async function agregar() {
    setEnviando(true);
    try {
      const r = await api<{ agregadas: number; rechazadas: string[] }>(`${base}/${t.id}/agregar`, { metodo: "POST", cuerpo: { unidades: [...marcadas] } });
      if (r.rechazadas.length) avisos.error(`${r.rechazadas.length} no se agregaron: ${r.rechazadas[0]}`);
      avisos.exito(`${numero(r.agregadas)} unidades agregadas.`);
      alAgregar();
      alCerrar();
    } catch (e) {
      avisos.error((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }
  return (
    <Modal abierto ancho="lg" alCerrar={alCerrar} titulo="Agregar unidades" descripcion="Solo aparecen unidades clasificadas, en la fase de origen y libres. Las que aún no cumplen la retención entran como anticipadas."
      pie={<><Boton onClick={alCerrar}>Cancelar</Boton><Boton variante="primario" icono={<Plus />} cargando={enviando} disabled={!marcadas.size} onClick={agregar}>Agregar ({marcadas.size})</Boton></>}>
      <div className="flex flex-col gap-3">
        <Entrada value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar por identificador, nombre o caja" aria-label="Buscar unidad" />
        {!c.datos ? <Cargando /> : !c.datos.length ? <Vacio icono={<ArrowRightLeft />} titulo="No hay más unidades que se puedan agregar" /> : (
          <div className="max-h-96 overflow-auto rounded-xl border border-line">
            {c.datos.map((u) => (
              <label key={u.unidad_id} className="flex cursor-pointer items-start gap-2 border-b border-line px-3 py-2 text-[13px] last:border-0 hover:bg-marca-suave">
                <input type="checkbox" className="mt-1" checked={marcadas.has(u.unidad_id)} onChange={() => setMarcadas((m) => { const n = new Set(m); if (n.has(u.unidad_id)) n.delete(u.unidad_id); else n.add(u.unidad_id); return n; })} />
                <span><b>{u.identificador}</b> · {u.nombre} <span className="text-texto-3">· caja {u.caja ?? "—"}</span>{u.aviso && <span className="block text-[11.5px] text-aviso">{u.aviso}</span>}</span>
              </label>
            ))}
          </div>
        )}
      </div>
    </Modal>
  );
}

function FaseDePartida({ base, alCerrar, alRegistrar }: { base: string; alCerrar: () => void; alRegistrar: () => void }) {
  const avisos = useAvisos();
  const [cajas, setCajas] = useState("");
  const [fase, setFase] = useState<"central" | "historico" | "gestion">("central");
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const lista = cajas.split(/[,;\n]/).map((x) => x.trim()).filter(Boolean);
  async function registrar() {
    setEnviando(true);
    setError(null);
    try {
      const r = await api<{ registradas: number }>(`${base}/fase-de-partida`, { metodo: "POST", cuerpo: { cajas: lista, fase, motivo: motivo.trim() } });
      avisos.exito(`${numero(r.registradas)} unidades registradas en ${FASE[fase].toLowerCase()}.`);
      alRegistrar();
      alCerrar();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }
  return (
    <Modal abierto alCerrar={alCerrar} titulo="Registrar fase de partida" descripcion="Para un fondo que ya está en el archivo central o histórico y no llega por transferencia. Se registra una sola vez por unidad; después la fase solo cambia por transferencia."
      pie={<><Boton onClick={alCerrar}>Cancelar</Boton><Boton variante="primario" icono={<MapPin />} cargando={enviando} disabled={!lista.length || motivo.trim().length < 5} onClick={registrar}>Registrar</Boton></>}>
      <div className="flex flex-col gap-3">
        <Campo etiqueta="Cajas" requerido ayuda="Separadas por coma o en líneas. Se registran todas las unidades de esas cajas."><Area value={cajas} onChange={(e) => setCajas(e.target.value)} placeholder="C-0001, C-0002" /></Campo>
        <Campo etiqueta="Dónde están hoy" requerido>
          <Selector value={fase} onChange={(e) => setFase(e.target.value as typeof fase)}>
            {Object.entries(FASE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Selector>
        </Campo>
        <Campo etiqueta="Motivo" requerido><Area value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Fondo acumulado recibido en el archivo central (acta de entrega…)" /></Campo>
        {error && <Nota tono="critico">{error}</Nota>}
      </div>
    </Modal>
  );
}
