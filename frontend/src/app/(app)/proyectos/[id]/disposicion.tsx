"use client";

import { Ban, CheckCircle2, Dices, Download, Eye, FileX2, Gavel, Globe, Layers, Plus, ScanLine, Shredder, Undo2 } from "lucide-react";
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
import type { PlanDisposicion, ProcesoDisposicion, Proyecto, TipoDisposicion, UnidadDisposicion } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

const NOMBRE: Record<TipoDisposicion, string> = { eliminacion: "Eliminación", seleccion: "Selección", digitalizacion: "Digitalización" };
const LETRA: Record<TipoDisposicion, string> = { eliminacion: "E", seleccion: "S", digitalizacion: "M/D" };
const ICONO: Record<TipoDisposicion, React.ReactNode> = { eliminacion: <Shredder />, seleccion: <Dices />, digitalizacion: <ScanLine /> };
const PASOS: Record<TipoDisposicion, string[]> = {
  eliminacion: ["borrador", "aprobado", "publicado", "ejecutado"],
  seleccion: ["borrador", "aprobado", "ejecutado"],
  digitalizacion: ["borrador", "aprobado", "ejecutado"],
};
const NOMBRE_PASO: Record<string, string> = { borrador: "Inventario", aprobado: "Comité", publicado: "Publicación", ejecutado: "Ejecución" };
const ESTADO = { borrador: "neutro", aprobado: "info", publicado: "aviso", ejecutado: "ok", anulado: "neutro" } as const;
const ESTADO_UNIDAD = { incluida: "neutro", retirada: "neutro", seleccionada: "ok", no_seleccionada: "aviso", ejecutada: "info" } as const;
const NOMBRE_UNIDAD = { incluida: "Incluida", retirada: "Retirada", seleccionada: "En la muestra", no_seleccionada: "No seleccionada", ejecutada: "Ejecutada" } as const;
const hoy = () => new Date().toISOString().slice(0, 10);

/** Disposición final: eliminación (comité, publicación y acta), selección por muestreo y digitalización. */
export function Disposicion({ proyecto }: { proyecto: Proyecto }) {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const base = `/proyectos/${proyecto.id}/disposicion`;
  const [corte, setCorte] = useState(hoy());
  const plan = useDatos(() => api<PlanDisposicion>(`${base}/plan`, { consulta: { fecha_corte: corte } }), [base, corte]);
  const lista = useDatos(() => api<ProcesoDisposicion[]>(base), [base]);
  const [abierto, setAbierto] = useState<string | null>(null);
  const [creando, setCreando] = useState<string | null>(null);
  const gestiona = puede(PERMISOS.disponer);
  const recargar = () => (void plan.recargar(), void lista.recargar());

  async function crear(tipo: TipoDisposicion, serie = "") {
    setCreando(`${tipo}-${serie}`);
    try {
      const p = await api<ProcesoDisposicion>(base, { metodo: "POST", cuerpo: { tipo, fecha_corte: corte, serie } });
      avisos.exito(`Proceso n.º ${p.numero} creado con ${numero(p.resumen.unidades)} unidades.`);
      recargar();
      setAbierto(p.id);
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
      <Nota tono="aviso">
        Eliminar es irreversible. ARCA prepara el inventario y documenta cada paso, pero no decide: nada se elimina sin la aprobación del comité (registrada por una persona distinta de quien preparó el proceso), la publicación del inventario por el plazo que fije la entidad según la norma vigente y el acta de eliminación. Lo eliminado no se borra de ARCA: queda con su inventario, su historial y el acta.
      </Nota>
      <div className="grid gap-3 sm:grid-cols-3">
        <Indicador etiqueta="Eliminadas" valor={numero(p.eliminadas)} tono="critico" icono={<FileX2 />} />
        <Indicador etiqueta="Seleccionadas (se conservan)" valor={numero(p.seleccionadas)} tono="ok" icono={<Dices />} />
        <Indicador etiqueta="Digitalizadas (medio técnico)" valor={numero(p.digitalizadas)} tono="info" icono={<ScanLine />} />
      </div>
      <Campo etiqueta="Fecha de corte" ayuda="Entra lo que cumplió toda su retención (gestión + central) en esta fecha." className="max-w-xs">
        <Entrada type="date" value={corte} onChange={(e) => setCorte(e.target.value || hoy())} />
      </Campo>
      <div className="grid gap-4 xl:grid-cols-3">
        {(["eliminacion", "seleccion", "digitalizacion"] as const).map((tipo) => {
          const g = p.tipos[tipo];
          return (
            <section key={tipo} className="flex flex-col rounded-xl border border-line bg-surface shadow-xs">
              <header className="border-b border-line px-4 py-3">
                <p className="flex items-center gap-2 font-semibold text-titulo [&_svg]:size-5 [&_svg]:text-marca">{ICONO[tipo]}{NOMBRE[tipo]} <Insignia tono="neutro">{LETRA[tipo]}</Insignia></p>
                <p className="text-[12.5px] text-texto-3">{numero(g.elegibles)} unidades cumplen ({numero(g.folios)} folios) · {numero(g.por_cumplir)} aún no · {numero(g.sin_calendario)} sin calendario</p>
                {gestiona && g.elegibles > 0 && <Boton tamano="sm" variante="primario" className="mt-2" icono={<Plus />} cargando={creando === `${tipo}-`} onClick={() => crear(tipo)}>Preparar con todas</Boton>}
              </header>
              {!g.por_serie.length ? <p className="px-4 py-4 text-[13px] text-texto-3">Nada cumple a esta fecha de corte.</p> : (
                <ul className="divide-y divide-line">
                  {g.por_serie.map((s) => (
                    <li key={s.codigo} className="flex items-start justify-between gap-2 px-4 py-2.5 text-[13px]">
                      <span><Codigo>{s.codigo}</Codigo> <b>{s.nombre}</b> · {numero(s.unidades)}{s.procedimiento && <span className="block text-[11.5px] text-texto-3">{s.procedimiento}</span>}</span>
                      {gestiona && <Boton tamano="sm" variante="fantasma" icono={<Plus />} cargando={creando === `${tipo}-${s.codigo}`} onClick={() => crear(tipo, s.codigo)}>Preparar</Boton>}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
      <div>
        <p className="mb-2 font-semibold text-titulo">Procesos de disposición</p>
        {!lista.datos?.length ? <Vacio icono={<Layers />} titulo="Todavía no hay procesos" /> : (
          <Tabla className="rounded-xl border border-line">
            <thead><tr><th>N.º</th><th>Tipo</th><th>Estado</th><th>Unidades</th><th>Folios</th><th>Comité</th><th>Publicación</th><th>Acta</th><th /></tr></thead>
            <tbody>
              {lista.datos.map((x) => (
                <tr key={x.id}>
                  <td className="font-semibold">{x.numero}</td>
                  <td>{NOMBRE[x.tipo]}{x.origen_id ? <span className="block text-[11.5px] text-texto-3">viene de otro proceso</span> : null}</td>
                  <td><Insignia tono={ESTADO[x.estado]} punto>{x.estado}</Insignia></td>
                  <td className="tabular">{numero(x.resumen.unidades)}</td>
                  <td className="tabular">{numero(x.resumen.folios)}</td>
                  <td className="text-[12.5px]">{x.comite_acta ?? "—"}</td>
                  <td className="text-[12.5px]">{x.publicacion_fin ? `hasta ${fecha(x.publicacion_fin)}` : "—"}</td>
                  <td className="text-[12.5px]">{x.acta_numero ?? "—"}</td>
                  <td><Boton tamano="sm" variante="fantasma" icono={<Eye />} onClick={() => setAbierto(x.id)}>Abrir</Boton></td>
                </tr>
              ))}
            </tbody>
          </Tabla>
        )}
      </div>
      {abierto && <Detalle base={base} proyecto={proyecto} id={abierto} alCerrar={() => setAbierto(null)} alCambiar={recargar} abrirOtro={setAbierto} />}
    </div>
  );
}

function Pasos({ p }: { p: ProcesoDisposicion }) {
  const pasos = PASOS[p.tipo];
  const actual = p.estado === "anulado" ? -1 : pasos.indexOf(p.estado);
  return (
    <ol className="flex flex-wrap items-center gap-2 text-[12.5px]">
      {pasos.map((paso, i) => (
        <li key={paso} className="flex items-center gap-2">
          <span className={`grid size-6 place-items-center rounded-full text-[11px] font-bold ${i <= actual ? "bg-marca text-white" : "bg-surface-muted text-texto-3"}`}>{i + 1}</span>
          <span className={i <= actual ? "font-semibold text-titulo" : "text-texto-3"}>{NOMBRE_PASO[paso]}</span>
          {i < pasos.length - 1 && <span className="text-texto-3">→</span>}
        </li>
      ))}
    </ol>
  );
}

function Detalle({ base, proyecto, id, alCerrar, alCambiar, abrirOtro }: { base: string; proyecto: Proyecto; id: string; alCerrar: () => void; alCambiar: () => void; abrirOtro: (id: string) => void }) {
  const { puede, usuario } = useSesion();
  const avisos = useAvisos();
  const d = useDatos(() => api<{ proceso: ProcesoDisposicion; unidades: UnidadDisposicion[] }>(`${base}/${id}`), [id]);
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set());
  const [modal, setModal] = useState<"retirar" | "anular" | "aprobar" | "publicar" | "ejecutar" | null>(null);
  const [trabajando, setTrabajando] = useState<string | null>(null);
  const [porcentaje, setPorcentaje] = useState("10");
  const [semilla, setSemilla] = useState("");
  const [criterio, setCriterio] = useState("");
  const p = d.datos?.proceso;
  const gestiona = puede(PERMISOS.disponer);
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
  async function documento(cual: "inventario" | "acta") {
    setTrabajando(cual);
    try {
      const e = await api<{ expedicion_id: string; nombre_archivo: string }>(`${base}/${id}/documentos/${cual}`, { metodo: "POST" });
      await descargarArchivo(`/proyectos/${proyecto.id}/entregables/${e.expedicion_id}/archivo`, e.nombre_archivo);
      avisos.exito(cual === "acta" ? "Acta de eliminación expedida en el formato de la entidad." : "Inventario expedido en el FUID de la entidad.");
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setTrabajando(null);
    }
  }
  const muestrear = () =>
    hacer("muestrear", async () => {
      const r = await api<{ propuestas: number; universo: number; semilla: number }>(`${base}/${id}/muestrear`, { metodo: "POST", cuerpo: { porcentaje: Number(porcentaje), semilla: semilla ? Number(semilla) : null, criterio } });
      setSemilla(String(r.semilla));
      return `Muestra propuesta: ${r.propuestas} de ${r.universo} (semilla ${r.semilla}). Ajústela si hace falta.`;
    });
  const marcar = (seleccionada: boolean) =>
    hacer("marcar", async () => `${(await api<{ marcadas: number }>(`${base}/${id}/marcar`, { metodo: "POST", cuerpo: { unidades: [...marcadas], seleccionada } })).marcadas} unidades ${seleccionada ? "agregadas a" : "quitadas de"} la muestra.`);

  if (!d.datos || !p) return <Modal abierto ancho="xl" alCerrar={alCerrar} titulo="Proceso de disposición"><Cargando /></Modal>;
  const editable = gestiona && p.estado === "borrador";
  const retirable = gestiona && (p.estado === "borrador" || p.estado === "publicado");
  const aprueba = puede(PERMISOS.aprobarDisposicion) && p.estado === "borrador" && p.creado_por !== usuario.id;
  const plazoCumplido = !p.publicacion_fin || p.publicacion_fin <= hoy();
  const conAviso = d.datos.unidades.filter((u) => u.aviso && u.estado !== "retirada").length;
  const todas = d.datos.unidades.length > 0 && d.datos.unidades.every((u) => marcadas.has(u.unidad_id));

  return (
    <Modal abierto ancho="xl" alCerrar={alCerrar} titulo={`${NOMBRE[p.tipo]} · proceso n.º ${p.numero}`}
      descripcion={<span className="flex flex-wrap items-center gap-2"><Insignia tono={ESTADO[p.estado]} punto>{p.estado}</Insignia>corte {fecha(p.fecha_corte)} · {numero(p.resumen.unidades)} unidades · {numero(p.resumen.folios)} folios · {p.resumen.cajas === 1 ? "1 caja" : `${numero(p.resumen.cajas)} cajas`}</span>}
      pie={<Boton onClick={alCerrar}>Cerrar</Boton>}>
      <div className="flex flex-col gap-4">
        <Pasos p={p} />
        {p.observaciones && <p className="text-[12.5px] text-texto-3">{p.observaciones}</p>}
        {p.novedad && <Nota tono="info">Anulado: {p.novedad}</Nota>}
        <div className="grid gap-2 text-[12.5px] text-texto-2 sm:grid-cols-3">
          {p.comite_acta && <span><b>Comité:</b> {p.comite_acta} · {fecha(p.comite_fecha)}</span>}
          {p.publicacion_inicio && <span><b>Publicado</b> desde {fecha(p.publicacion_inicio)} hasta {fecha(p.publicacion_fin)} · <a className="text-marca underline" href={p.publicacion_enlace ?? "#"} target="_blank" rel="noreferrer">enlace</a></span>}
          {p.ejecutado_en && <span><b>Ejecutado</b> {fechaHora(p.ejecutado_en)}{p.acta_numero ? ` · acta ${p.acta_numero}` : ""}{p.metodo ? ` · ${p.metodo}` : ""}{p.destino_fisico ? ` · físico: ${p.destino_fisico}` : ""}</span>}
          {p.muestreo?.semilla && <span><b>Muestreo:</b> {p.muestreo.porcentaje} % · semilla {p.muestreo.semilla}{p.muestreo.ajustada ? " · ajustado a mano" : ""}{p.muestreo.criterio ? ` · ${p.muestreo.criterio}` : ""}</span>}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Boton tamano="sm" icono={<Download />} cargando={trabajando === "inventario"} onClick={() => documento("inventario")}>Inventario FUID</Boton>
          {p.tipo === "eliminacion" && p.estado === "ejecutado" && <Boton tamano="sm" variante="primario" icono={<Download />} cargando={trabajando === "acta"} onClick={() => documento("acta")}>Acta de eliminación</Boton>}
          <div className="ml-auto flex flex-wrap gap-2">
            {retirable && marcadas.size > 0 && <Boton tamano="sm" icono={<Undo2 />} onClick={() => setModal("retirar")}>Retirar ({marcadas.size})</Boton>}
            {gestiona && ["borrador", "aprobado", "publicado"].includes(p.estado) && <Boton tamano="sm" icono={<Ban />} onClick={() => setModal("anular")}>Anular</Boton>}
            {aprueba && <Boton tamano="sm" variante="primario" icono={<Gavel />} onClick={() => setModal("aprobar")}>Registrar aprobación del comité</Boton>}
            {gestiona && p.estado === "aprobado" && p.tipo === "eliminacion" && <Boton tamano="sm" variante="primario" icono={<Globe />} onClick={() => setModal("publicar")}>Registrar publicación</Boton>}
            {gestiona && ((p.estado === "aprobado" && p.tipo !== "eliminacion") || p.estado === "publicado") && (
              <Boton tamano="sm" variante="primario" icono={<CheckCircle2 />} disabled={!plazoCumplido} onClick={() => setModal("ejecutar")}>Ejecutar</Boton>
            )}
          </div>
        </div>
        {p.estado === "borrador" && !aprueba && puede(PERMISOS.aprobarDisposicion) && <Nota tono="aviso">La aprobación del comité la registra otra persona (usted preparó el proceso).</Nota>}
        {p.estado === "publicado" && !plazoCumplido && <Nota tono="aviso">El inventario está publicado hasta el {fecha(p.publicacion_fin)}. Mientras tanto pueden llegar observaciones: retire las unidades que correspondan, con el motivo. La ejecución se habilita al terminar el plazo.</Nota>}
        {p.tipo === "digitalizacion" && p.estado === "borrador" && conAviso > 0 && <Nota tono="critico">{conAviso} unidades no tienen la digitalización aprobada. Retírelas o termine de digitalizarlas para poder aprobar.</Nota>}

        {editable && p.tipo === "seleccion" && (
          <div className="rounded-xl border border-line bg-surface-muted p-3">
            <p className="mb-2 text-[13px] font-semibold text-titulo">Muestreo</p>
            <div className="grid gap-2 sm:grid-cols-[120px_160px_1fr_auto] sm:items-end">
              <Campo etiqueta="Porcentaje"><Entrada type="number" min={1} max={100} value={porcentaje} onChange={(e) => setPorcentaje(e.target.value)} /></Campo>
              <Campo etiqueta="Semilla" ayuda="Vacío = ARCA la elige"><Entrada type="number" value={semilla} onChange={(e) => setSemilla(e.target.value)} /></Campo>
              <Campo etiqueta="Criterio"><Entrada value={criterio} onChange={(e) => setCriterio(e.target.value)} placeholder="Según el procedimiento de la TRD" /></Campo>
              <Boton icono={<Dices />} cargando={trabajando === "muestrear"} onClick={muestrear}>Proponer muestra</Boton>
            </div>
            <p className="mt-2 text-[12px] text-texto-3">La misma semilla da la misma muestra, para que se pueda verificar. Después ajuste por criterio cualitativo: marque unidades y agréguelas o quítelas de la muestra.</p>
            {marcadas.size > 0 && (
              <div className="mt-2 flex gap-2">
                <Boton tamano="sm" icono={<Plus />} cargando={trabajando === "marcar"} onClick={() => marcar(true)}>Agregar a la muestra</Boton>
                <Boton tamano="sm" icono={<Undo2 />} cargando={trabajando === "marcar"} onClick={() => marcar(false)}>Quitar de la muestra</Boton>
              </div>
            )}
          </div>
        )}

        <Tabla className="rounded-xl border border-line">
          <thead>
            <tr>
              {(retirable || editable) && <th className="w-8"><input type="checkbox" aria-label="Marcar todas" checked={todas} onChange={() => setMarcadas(todas ? new Set() : new Set(d.datos!.unidades.map((u) => u.unidad_id)))} /></th>}
              <th>Unidad</th><th>Caja · carpeta</th><th>Fechas</th><th>Folios</th><th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {d.datos.unidades.map((u) => (
              <tr key={u.unidad_id} className={u.estado === "retirada" ? "opacity-60" : ""}>
                {(retirable || editable) && <td><input type="checkbox" aria-label={`Marcar ${u.identificador}`} disabled={u.estado === "retirada"} checked={marcadas.has(u.unidad_id)} onChange={() => setMarcadas((m) => { const n = new Set(m); if (n.has(u.unidad_id)) n.delete(u.unidad_id); else n.add(u.unidad_id); return n; })} /></td>}
                <td className="min-w-52"><p className="font-semibold text-titulo">{u.identificador}</p><p className="text-[12.5px]">{u.nombre}</p>{u.aviso && <p className="text-[11.5px] text-aviso">{u.aviso}</p>}</td>
                <td className="whitespace-nowrap">{u.caja ?? "—"} · {u.carpeta ?? "—"}</td>
                <td className="text-[12.5px]">{fecha(u.fecha_inicial)} – {fecha(u.fecha_final)}</td>
                <td className="tabular">{u.folios ?? "—"}</td>
                <td><Insignia tono={u.estado === "ejecutada" && p.tipo === "eliminacion" ? "neutro" : ESTADO_UNIDAD[u.estado]}>{u.estado === "ejecutada" && p.tipo === "eliminacion" ? "Eliminada" : NOMBRE_UNIDAD[u.estado]}</Insignia>{u.observacion && <p className="text-[11.5px] text-texto-3">{u.observacion}</p>}</td>
              </tr>
            ))}
          </tbody>
        </Tabla>
      </div>

      <ModalMotivo
        abierto={modal === "retirar" || modal === "anular"}
        titulo={modal === "retirar" ? `Retirar ${marcadas.size} unidades del proceso` : "Anular el proceso"}
        descripcion={modal === "retirar" ? "Las unidades salen del proceso y quedan libres; queda la constancia con el motivo (por ejemplo, una observación recibida durante la publicación)." : "Las unidades quedan libres. El proceso queda como evidencia."}
        boton={modal === "retirar" ? "Retirar" : "Anular"}
        peligro={modal === "anular"}
        alCerrar={() => setModal(null)}
        alConfirmar={async (motivo) => {
          if (modal === "retirar") await api(`${base}/${id}/retirar`, { metodo: "POST", cuerpo: { unidades: [...marcadas], motivo } });
          else await api(`${base}/${id}/anular`, { metodo: "POST", cuerpo: { motivo } });
          avisos.exito(modal === "retirar" ? "Unidades retiradas." : "Proceso anulado.");
          recargar();
        }}
      />
      {modal === "aprobar" && <Formulario titulo="Registrar la aprobación del comité" boton="Registrar aprobación" alCerrar={() => setModal(null)}
        campos={[{ clave: "acta_comite", etiqueta: "Acta del comité", requerido: true }, { clave: "fecha_acta", etiqueta: "Fecha del acta", tipo: "date", requerido: true }, { clave: "motivo", etiqueta: "Observaciones", requerido: true, area: true }]}
        enviar={async (v) => { await api(`${base}/${id}/aprobar`, { metodo: "POST", cuerpo: v }); avisos.exito("Aprobación registrada."); recargar(); }} />}
      {modal === "publicar" && <Formulario titulo="Registrar la publicación del inventario" boton="Registrar publicación" alCerrar={() => setModal(null)}
        descripcion="Registre la publicación cuando ya esté publicada. El plazo lo fija la entidad según la norma vigente."
        campos={[{ clave: "inicio", etiqueta: "Publicado desde", tipo: "date", requerido: true, inicial: hoy() }, { clave: "dias", etiqueta: "Plazo (días)", tipo: "number", requerido: true, inicial: "60" }, { clave: "enlace", etiqueta: "Dónde se publicó (enlace)", requerido: true }]}
        enviar={async (v) => { await api(`${base}/${id}/publicar`, { metodo: "POST", cuerpo: { ...v, dias: Number(v.dias) } }); avisos.exito("Publicación registrada."); recargar(); }} />}
      {modal === "ejecutar" && <Formulario titulo={`Ejecutar: ${NOMBRE[p.tipo].toLowerCase()}`} boton="Ejecutar" peligro={p.tipo === "eliminacion"} alCerrar={() => setModal(null)}
        descripcion={p.tipo === "eliminacion" ? "Las unidades quedan como eliminadas. No se puede deshacer." : p.tipo === "seleccion" ? `Las ${p.resumen.seleccionada} seleccionadas quedan listas para la transferencia secundaria; las ${p.resumen.no_seleccionada} no seleccionadas pasan a un proceso de eliminación nuevo.` : "Elija qué pasa con el físico después de digitalizar."}
        campos={p.tipo === "eliminacion" ? [{ clave: "acta_numero", etiqueta: "Número del acta de eliminación", requerido: true }, { clave: "metodo", etiqueta: "Método de eliminación", requerido: true }]
          : p.tipo === "digitalizacion" ? [{ clave: "destino_fisico", etiqueta: "El físico", opciones: [["conservar", "Se conserva"], ["eliminar", "Pasa a un proceso de eliminación"]], requerido: true, inicial: "conservar" }] : []}
        enviar={async (v) => {
          const r = await api<{ ejecutadas: number; nuevo_proceso: { id: string; numero: number; unidades: number } | null }>(`${base}/${id}/ejecutar`, { metodo: "POST", cuerpo: v });
          avisos.exito(`${numero(r.ejecutadas)} unidades procesadas.${r.nuevo_proceso ? ` ${r.nuevo_proceso.unidades} pasan al proceso de eliminación n.º ${r.nuevo_proceso.numero}.` : ""}`);
          recargar();
          if (r.nuevo_proceso) abrirOtro(r.nuevo_proceso.id);
        }} />}
    </Modal>
  );
}

type CampoForm = { clave: string; etiqueta: string; tipo?: string; requerido?: boolean; area?: boolean; inicial?: string; opciones?: [string, string][] };

function Formulario({ titulo, descripcion, boton, peligro, campos, alCerrar, enviar }: { titulo: string; descripcion?: string; boton: string; peligro?: boolean; campos: CampoForm[]; alCerrar: () => void; enviar: (v: Record<string, string>) => Promise<void> }) {
  const [valores, setValores] = useState<Record<string, string>>(Object.fromEntries(campos.map((c) => [c.clave, c.inicial ?? ""])));
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const completo = campos.every((c) => !c.requerido || (valores[c.clave] ?? "").trim());
  async function confirmar() {
    setEnviando(true);
    setError(null);
    try {
      await enviar(valores);
      alCerrar();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }
  return (
    <Modal abierto alCerrar={alCerrar} titulo={titulo} descripcion={descripcion}
      pie={<><Boton onClick={alCerrar}>Cancelar</Boton><Boton variante={peligro ? "peligro" : "primario"} cargando={enviando} disabled={!completo} onClick={confirmar}>{boton}</Boton></>}>
      <div className="flex flex-col gap-3">
        {campos.map((c) => (
          <Campo key={c.clave} etiqueta={c.etiqueta} requerido={c.requerido}>
            {c.opciones ? (
              <Selector value={valores[c.clave]} onChange={(e) => setValores((v) => ({ ...v, [c.clave]: e.target.value }))}>{c.opciones.map(([k, t]) => <option key={k} value={k}>{t}</option>)}</Selector>
            ) : c.area ? (
              <Area value={valores[c.clave]} onChange={(e) => setValores((v) => ({ ...v, [c.clave]: e.target.value }))} />
            ) : (
              <Entrada type={c.tipo ?? "text"} value={valores[c.clave]} onChange={(e) => setValores((v) => ({ ...v, [c.clave]: e.target.value }))} />
            )}
          </Campo>
        ))}
        {error && <Nota tono="critico">{error}</Nota>}
      </div>
    </Modal>
  );
}
