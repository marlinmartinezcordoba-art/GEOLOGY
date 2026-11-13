"use client";

import { AlertTriangle, ArrowUpCircle, CheckCheck, FolderTree, ListChecks, Search, Tag, Wand2, X } from "lucide-react";
import { useMemo, useState } from "react";

import { ModalMotivo } from "@/components/ui/acciones";
import { useAvisos } from "@/components/ui/avisos";
import { Boton, Cargando, Codigo, Indicador, Insignia, InsigniaMotor, Modal, Nota, Paginador, Pestanas, Tabla, Vacio } from "@/components/ui/basicos";
import { Area, Campo, Entrada } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { fecha, numero } from "@/lib/formato";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { FilaClasificacion, OpcionesClasificacion, Proyecto, ResumenClasificacion, SituacionClasificacion } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

const POR_PAGINA = 100;
const TONO_CONFIANZA = { alta: "ok", media: "aviso", baja: "critico" } as const;
const FASE = { gestion: "Archivo de gestión", central: "Archivo central", cumplida: "Retención cumplida" } as const;
type Filtro = "todas" | SituacionClasificacion | "alertas";

function Origen({ c }: { c: NonNullable<FilaClasificacion["clasificacion"]> }) {
  if (c.origen === "inventario") return <InsigniaMotor>Del FUID</InsigniaMotor>;
  if (c.origen === "manual") return <Insignia tono="marca">Asignada</Insignia>;
  if (c.origen === "actualizacion") return <Insignia tono="info">Versión actualizada</Insignia>;
  if (c.origen === "codigo") return <InsigniaMotor>Por el código del FUID</InsigniaMotor>;
  return <InsigniaMotor>Por el nombre</InsigniaMotor>;
}

/** M04 · Clasificación de las unidades del FUID con la TRD o TVD vigente, y su calendario de retención. */
export function Clasificacion({ proyecto }: { proyecto: Proyecto }) {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const base = `/proyectos/${proyecto.id}/clasificacion`;
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [q, setQ] = useState("");
  const [pagina, setPagina] = useState(1);
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set());
  const [asignando, setAsignando] = useState(false);
  const [rechazando, setRechazando] = useState(false);
  const [actualizando, setActualizando] = useState(false);
  const [trabajando, setTrabajando] = useState(false);
  const clasifica = puede(PERMISOS.clasificar);

  const resumen = useDatos(() => api<ResumenClasificacion>(`${base}/resumen`), [base]);
  const consulta = { situacion: filtro === "todas" || filtro === "alertas" ? null : filtro, alertas: filtro === "alertas" ? "true" : null, q, desplazamiento: (pagina - 1) * POR_PAGINA, limite: POR_PAGINA };
  const filas = useDatos(() => api<{ total: number; filas: FilaClasificacion[] }>(base, { consulta }), [base, filtro, q, pagina]);

  const recargar = () => {
    setMarcadas(new Set());
    void resumen.recargar();
    void filas.recargar();
  };
  const visibles = filas.datos?.filas ?? [];
  const seleccion = visibles.filter((f) => marcadas.has(f.unidad.id));
  const propuestasMarcadas = seleccion.filter((f) => f.clasificacion?.estado === "propuesta" && f.clasificacion.version_vigente);
  const confirmadasMarcadas = seleccion.filter((f) => f.clasificacion?.estado === "confirmada").length;

  async function accion<T>(fn: () => Promise<T>, mensaje: (r: T) => string) {
    setTrabajando(true);
    try {
      avisos.exito(mensaje(await fn()));
      recargar();
    } catch (e) {
      avisos.error((e as Error).message);
    } finally {
      setTrabajando(false);
    }
  }

  const proponer = () =>
    accion(
      () => api<{ confirmadas: number; propuestas: number; sin_propuesta: number; sin_instrumento: number }>(`${base}/proponer`, { metodo: "POST" }),
      (r) => `${numero(r.confirmadas)} clasificadas por el código del FUID · ${numero(r.propuestas)} propuestas por revisar · ${numero(r.sin_propuesta + r.sin_instrumento)} quedan pendientes.`,
    );
  const confirmar = () =>
    accion(() => api<{ confirmadas: number }>(`${base}/confirmar`, { metodo: "POST", cuerpo: { clasificaciones: propuestasMarcadas.map((f) => f.clasificacion!.id) } }), (r) => `${numero(r.confirmadas)} propuestas confirmadas.`);

  const r = resumen.datos;
  if (resumen.cargando && !r) return <Cargando />;
  if (!r) return null;
  const todas = visibles.length > 0 && visibles.every((f) => marcadas.has(f.unidad.id));

  return (
    <div className="flex flex-col gap-5 p-5">
      {!r.instrumentos.length ? (
        <Nota tono="aviso">El proyecto no tiene TRD ni TVD vigente. Apruebe una en la pestaña «TRD · TVD · CCD» para poder clasificar.</Nota>
      ) : (
        <Nota tono="info">
          Se clasifica con {r.instrumentos.map((i) => `${i.instrumento} v${i.version}${i.periodo_desde || i.periodo_hasta ? ` (fondo ${fecha(i.periodo_desde)} – ${fecha(i.periodo_hasta)})` : ""}`).join(" y ")}.
          Si el código del FUID está en la tabla, la unidad queda clasificada; lo que se deduce del nombre queda como propuesta para confirmar. Si nada coincide, no se propone nada.
          Cada unidad conserva la versión con que se clasificó.
        </Nota>
      )}
      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Indicador etiqueta="Unidades" valor={numero(r.unidades)} icono={<FolderTree />} />
        <Indicador etiqueta="Pendientes" valor={numero(r.pendiente)} tono="neutro" icono={<ListChecks />} />
        <Indicador etiqueta="Propuestas" valor={numero(r.propuesta)} tono="aviso" icono={<Wand2 />} />
        <Indicador etiqueta="Confirmadas" valor={numero(r.confirmada)} tono="ok" icono={<CheckCheck />} />
        <Indicador etiqueta="Versión anterior" valor={numero(r.version_anterior)} tono="info" icono={<ArrowUpCircle />} />
        <Indicador etiqueta="Con alertas" valor={numero(r.con_alertas)} tono="critico" icono={<AlertTriangle />} />
      </div>
      {r.confirmada + r.propuesta + r.version_anterior > 0 && (
        <p className="text-[13px] text-texto-2">
          Según la retención: <b>{numero(r.fases.gestion)}</b> en archivo de gestión · <b>{numero(r.fases.central)}</b> en archivo central · <b>{numero(r.fases.cumplida)}</b> con la retención cumplida (aplicar disposición final).
        </p>
      )}
      {clasifica && r.instrumentos.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <Boton variante="primario" icono={<Wand2 />} cargando={trabajando} disabled={!r.pendiente} onClick={proponer}>Clasificar automáticamente ({numero(r.pendiente)} pendientes)</Boton>
          {r.version_anterior > 0 && <Boton icono={<ArrowUpCircle />} onClick={() => setActualizando(true)}>Pasar a la versión vigente</Boton>}
        </div>
      )}

      <div className="rounded-xl border border-line">
        <div className="px-4 pt-1">
          <Pestanas
            valor={filtro}
            alCambiar={(v) => (setFiltro(v), setPagina(1), setMarcadas(new Set()))}
            opciones={[
              { valor: "todas", etiqueta: `Todas (${numero(r.unidades)})` },
              { valor: "pendiente", etiqueta: `Sin clasificar (${numero(r.pendiente)})` },
              { valor: "propuesta", etiqueta: `Por confirmar (${numero(r.propuesta)})` },
              { valor: "confirmada", etiqueta: `Clasificadas (${numero(r.confirmada)})` },
              { valor: "version_anterior", etiqueta: `Con versión anterior (${numero(r.version_anterior)})` },
              { valor: "alertas", etiqueta: `Alertas (${numero(r.con_alertas)})` },
            ]}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-texto-3" />
            <Entrada className="pl-9" value={q} onChange={(e) => (setQ(e.target.value), setPagina(1))} placeholder="Buscar expediente, caja o código" aria-label="Buscar" />
          </div>
          {clasifica && seleccion.length > 0 && (
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <span className="text-[13px] text-texto-2">{numero(seleccion.length)} marcadas</span>
              {propuestasMarcadas.length > 0 && <Boton tamano="sm" variante="primario" icono={<CheckCheck />} cargando={trabajando} onClick={confirmar}>Confirmar propuestas ({propuestasMarcadas.length})</Boton>}
              {propuestasMarcadas.length > 0 && <Boton tamano="sm" icono={<X />} onClick={() => setRechazando(true)}>Rechazar</Boton>}
              <Boton tamano="sm" icono={<Tag />} onClick={() => setAsignando(true)}>Asignar serie o subserie</Boton>
            </div>
          )}
        </div>
        {filas.cargando && !filas.datos ? <Cargando /> : !visibles.length ? (
          <Vacio icono={<FolderTree />} titulo={r.unidades ? "No hay unidades con este filtro" : "El proyecto no tiene inventario"} descripcion={r.unidades ? undefined : "Integre el FUID en la pestaña «Inventario FUID»."} />
        ) : (
          <Tabla>
            <thead>
              <tr>
                {clasifica && <th className="w-8"><input type="checkbox" aria-label="Marcar todas" checked={todas} onChange={() => setMarcadas(todas ? new Set() : new Set(visibles.map((f) => f.unidad.id)))} /></th>}
                <th>Unidad</th><th>Código en el FUID</th><th>Clasificación</th><th>Calendario de retención</th>
              </tr>
            </thead>
            <tbody>
              {visibles.map((f) => {
                const c = f.clasificacion;
                return (
                  <tr key={f.unidad.id}>
                    {clasifica && (
                      <td><input type="checkbox" aria-label={`Marcar ${f.unidad.identificador}`} checked={marcadas.has(f.unidad.id)} onChange={() => setMarcadas((m) => { const n = new Set(m); if (n.has(f.unidad.id)) n.delete(f.unidad.id); else n.add(f.unidad.id); return n; })} /></td>
                    )}
                    <td className="max-w-xs">
                      <p className="font-semibold text-titulo">{f.unidad.identificador}</p>
                      <p className="text-[12.5px]">{f.unidad.nombre}</p>
                      <p className="text-[11.5px] text-texto-3">{[f.unidad.caja && `Caja ${f.unidad.caja}`, f.unidad.carpeta && `carpeta ${f.unidad.carpeta}`, f.unidad.fecha_inicial && `${fecha(f.unidad.fecha_inicial)} – ${fecha(f.unidad.fecha_final)}`].filter(Boolean).join(" · ")}</p>
                    </td>
                    <td>{f.unidad.codigo_serie ? <Codigo>{f.unidad.codigo_serie}</Codigo> : <span className="text-texto-3">—</span>}</td>
                    <td className="max-w-sm">
                      {!c ? <Insignia tono="neutro">Sin clasificar</Insignia> : (
                        <>
                          <div className="flex flex-wrap items-center gap-1.5">
                            <Codigo>{c.codigo}</Codigo>
                            <span className="font-medium">{c.nombre}</span>
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-1.5">
                            <Origen c={c} />
                            <Insignia tono={c.estado === "confirmada" ? "ok" : "aviso"} punto>{c.estado === "confirmada" ? "Confirmada" : "Por confirmar"}</Insignia>
                            {c.confianza && c.estado === "propuesta" && <Insignia tono={TONO_CONFIANZA[c.confianza]}>confianza {c.confianza}</Insignia>}
                            <span className="text-[11.5px] text-texto-3">{c.instrumento} v{c.version}{c.version_vigente ? "" : " (no vigente)"}</span>
                          </div>
                          {(c.origen === "motor" || c.origen === "codigo") && <p className="mt-1 text-[11.5px] text-texto-3">Por qué: {c.porque}</p>}
                        </>
                      )}
                      {f.alertas.map((a) => <p key={a} className="mt-1 flex items-center gap-1 text-[12px] text-critico"><AlertTriangle className="size-3.5" />{a}</p>)}
                    </td>
                    <td className="text-[12.5px]">
                      {c ? (
                        <>
                          {c.calendario.fase && <Insignia tono={c.calendario.fase === "cumplida" ? "critico" : c.calendario.fase === "central" ? "info" : "ok"}>{FASE[c.calendario.fase]}</Insignia>}
                          <p className="mt-1">{c.calendario.nota}</p>
                          {c.calendario.disposicion && <p className="text-texto-3">Disposición: {c.calendario.disposicion}</p>}
                        </>
                      ) : <span className="text-texto-3">—</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </Tabla>
        )}
        <Paginador total={filas.datos?.total ?? 0} pagina={pagina} porPagina={POR_PAGINA} alCambiar={setPagina} />
      </div>

      {asignando && <Asignar base={base} unidades={seleccion.map((f) => f.unidad.id)} confirmadas={confirmadasMarcadas} alCerrar={() => setAsignando(false)} alAsignar={recargar} />}
      <ModalMotivo
        abierto={rechazando}
        titulo={`Rechazar ${propuestasMarcadas.length} propuestas`}
        descripcion="Las unidades vuelven a quedar sin clasificar. La propuesta rechazada queda registrada."
        boton="Rechazar"
        alCerrar={() => setRechazando(false)}
        alConfirmar={async (motivo) => {
          const res = await api<{ rechazadas: number }>(`${base}/rechazar`, { metodo: "POST", cuerpo: { clasificaciones: propuestasMarcadas.map((f) => f.clasificacion!.id), motivo } });
          avisos.exito(`${numero(res.rechazadas)} propuestas rechazadas.`);
          recargar();
        }}
      />
      <ModalMotivo
        abierto={actualizando}
        titulo="Pasar a la versión vigente"
        descripcion="Las unidades clasificadas con una versión anterior pasan a la vigente solo si la misma serie o subserie sigue existiendo con el mismo código. Las demás quedan como están, para que una persona las reclasifique."
        boton="Actualizar"
        alCerrar={() => setActualizando(false)}
        alConfirmar={async (motivo) => {
          const res = await api<{ actualizadas: number; sin_equivalente: number }>(`${base}/actualizar-version`, { metodo: "POST", cuerpo: { motivo } });
          avisos.exito(`${numero(res.actualizadas)} actualizadas · ${numero(res.sin_equivalente)} sin equivalente en la versión vigente.`);
          recargar();
        }}
      />
    </div>
  );
}

function Asignar({ base, unidades, confirmadas, alCerrar, alAsignar }: { base: string; unidades: string[]; confirmadas: number; alCerrar: () => void; alAsignar: () => void }) {
  const avisos = useAvisos();
  const opciones = useDatos(() => api<OpcionesClasificacion>(`${base}/opciones`), [base]);
  const [buscar, setBuscar] = useState("");
  const [elegido, setElegido] = useState<string | null>(null);
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const grupos = useMemo(() => {
    const t = buscar.trim().toLowerCase();
    return (opciones.datos ?? []).map((g) => ({ ...g, elementos: g.elementos.filter((e) => !t || `${e.codigo} ${e.nombre} ${e.serie_nombre ?? ""}`.toLowerCase().includes(t)) }));
  }, [opciones.datos, buscar]);
  async function asignar() {
    setEnviando(true);
    setError(null);
    try {
      const r = await api<{ clasificadas: number }>(`${base}/asignar`, { metodo: "POST", cuerpo: { unidades, elemento_id: elegido, motivo: motivo.trim() } });
      avisos.exito(`${numero(r.clasificadas)} unidades clasificadas.`);
      alAsignar();
      alCerrar();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }
  const faltaMotivo = confirmadas > 0 && motivo.trim().length < 5;
  return (
    <Modal abierto ancho="lg" alCerrar={alCerrar} titulo={`Asignar serie o subserie a ${unidades.length} unidades`} descripcion="Solo se ofrecen las series sin subseries y las subseries de las tablas vigentes."
      pie={<><Boton onClick={alCerrar}>Cancelar</Boton><Boton variante="primario" icono={<Tag />} cargando={enviando} disabled={!elegido || faltaMotivo} onClick={asignar}>Asignar</Boton></>}>
      {!opciones.datos ? <Cargando /> : (
        <div className="flex flex-col gap-3">
          <Entrada value={buscar} onChange={(e) => setBuscar(e.target.value)} placeholder="Buscar por código o nombre" aria-label="Buscar serie" />
          <div className="max-h-80 overflow-auto rounded-xl border border-line">
            {grupos.map((g) => (
              <div key={g.instrumento_id}>
                <p className="sticky top-0 bg-surface-muted px-3 py-1.5 text-[12px] font-semibold text-texto-2">{g.instrumento} · v{g.version}</p>
                {g.elementos.map((e) => (
                  <label key={e.id} className="flex cursor-pointer items-start gap-2 border-t border-line px-3 py-2 text-[13px] hover:bg-marca-suave">
                    <input type="radio" name="elemento" className="mt-1" checked={elegido === e.id} onChange={() => setElegido(e.id)} />
                    <span>
                      <Codigo>{e.codigo}</Codigo> <b>{e.nombre}</b>
                      {e.serie_nombre && <span className="block text-[11.5px] text-texto-3">Serie {e.serie} · {e.serie_nombre}</span>}
                    </span>
                  </label>
                ))}
              </div>
            ))}
          </div>
          <Campo etiqueta={confirmadas ? "Motivo (obligatorio: hay unidades ya clasificadas)" : "Motivo"} requerido={confirmadas > 0}>
            <Area value={motivo} onChange={(e) => setMotivo(e.target.value)} />
          </Campo>
          {error && <Nota tono="critico">{error}</Nota>}
        </div>
      )}
    </Modal>
  );
}
