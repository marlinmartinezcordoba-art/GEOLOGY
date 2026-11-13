"use client";

import { BookText, Download, Layers3, Save, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useAvisos } from "@/components/ui/avisos";
import { Boton, Cargando, Indicador, Insignia, Modal, Nota, Paginador, Pestanas, Tabla, Vacio } from "@/components/ui/basicos";
import { Area, Campo, Entrada } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { descargarArchivo } from "@/lib/descargas";
import { numero } from "@/lib/formato";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { EstadoDescripcion, FilaDescripcion, ProcesoLote, Proyecto } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

export const NOMBRE_ESTADO_DESC: Record<EstadoDescripcion, string> = {
  no_aplica: "No aplica (lote sin ISAD(G))", sin_descripcion: "Sin describir", borrador: "En elaboración", en_revision: "En revisión", devuelta: "Devuelta", aprobada: "Aprobada",
};
export const TONO_ESTADO_DESC = { no_aplica: "neutro", sin_descripcion: "neutro", borrador: "info", en_revision: "aviso", devuelta: "critico", aprobada: "ok" } as const;
const POR_PAGINA = 100;

/** Qué lleva cada lote (hoja de control, ISAD(G) o ambas) y la bandeja de descripción ISAD(G). */
export function Descripciones({ proyecto }: { proyecto: Proyecto }) {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const base = `/proyectos/${proyecto.id}`;
  const [estado, setEstado] = useState<EstadoDescripcion | "todas">("todas");
  const [q, setQ] = useState("");
  const [pagina, setPagina] = useState(1);
  const [expidiendo, setExpidiendo] = useState(false);
  const datos = useDatos(
    () => api<{ total: number; filas: FilaDescripcion[]; cuenta: Record<EstadoDescripcion, number> }>(`${base}/descripciones`, { consulta: { estado: estado === "todas" ? null : estado, q, desplazamiento: (pagina - 1) * POR_PAGINA, limite: POR_PAGINA } }),
    [base, estado, q, pagina],
  );
  const c = datos.datos?.cuenta;
  async function expedir() {
    setExpidiendo(true);
    try {
      const e = await api<{ expedicion_id: string; nombre_archivo: string; elementos: number }>(`${base}/descripciones/expedir`, { metodo: "POST" });
      await descargarArchivo(`${base}/entregables/${e.expedicion_id}/archivo`, e.nombre_archivo);
      avisos.exito(`Base de descripción expedida con ${numero(e.elementos)} unidades aprobadas.`);
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setExpidiendo(false);
    }
  }
  return (
    <div className="flex flex-col gap-5 p-5">
      <Nota tono="info">
        La descripción ISAD(G) no depende de la fase del ciclo vital: se hace donde esté la unidad. Sí depende de la digitalización: solo se describe lo digitalizado, con la hoja de control verificada si el lote la lleva, o con lo que leyó el OCR si no. Lo deducible lo calcula ARCA con su origen; el título y el alcance los propone y una persona los escribe o los confirma. La aprueba otra persona.
      </Nota>
      <ProcesosPorLote proyecto={proyecto} alCambiar={() => void datos.recargar()} />
      {!c ? <Cargando /> : (
        <>
          <div className="grid gap-3 sm:grid-cols-5">
            <Indicador etiqueta="Por describir" valor={numero(c.sin_descripcion)} tono="neutro" icono={<BookText />} />
            <Indicador etiqueta="En elaboración" valor={numero(c.borrador)} tono="info" icono={<BookText />} />
            <Indicador etiqueta="En revisión" valor={numero(c.en_revision)} tono="aviso" icono={<BookText />} />
            <Indicador etiqueta="Devueltas" valor={numero(c.devuelta)} tono="critico" icono={<BookText />} />
            <Indicador etiqueta="Aprobadas" valor={numero(c.aprobada)} tono="ok" icono={<BookText />} />
          </div>
          <div className="rounded-xl border border-line">
            <div className="px-4 pt-1">
              <Pestanas valor={estado} alCambiar={(v) => (setEstado(v), setPagina(1))} opciones={[
                { valor: "todas", etiqueta: "Todas" },
                ...(["sin_descripcion", "borrador", "en_revision", "devuelta", "aprobada", "no_aplica"] as const).map((k) => ({ valor: k, etiqueta: `${NOMBRE_ESTADO_DESC[k]} (${numero(c[k])})` })),
              ]} />
            </div>
            <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
              <div className="relative w-full max-w-sm">
                <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-texto-3" />
                <Entrada className="pl-9" value={q} onChange={(e) => (setQ(e.target.value), setPagina(1))} placeholder="Buscar expediente, título o caja" aria-label="Buscar" />
              </div>
              {puede(PERMISOS.expedir) && c.aprobada > 0 && <Boton className="ml-auto" variante="primario" icono={<Download />} cargando={expidiendo} onClick={expedir}>Expedir base ISAD(G) ({numero(c.aprobada)})</Boton>}
            </div>
            {!datos.datos?.filas.length ? <Vacio icono={<BookText />} titulo="No hay unidades con este filtro" /> : (
              <Tabla>
                <thead><tr><th>Expediente</th><th>Lote</th><th>Título</th><th>Hoja de control</th><th>Estado</th><th /></tr></thead>
                <tbody>
                  {datos.datos.filas.map((f) => (
                    <tr key={f.unidad_id}>
                      <td className="max-w-xs"><p className="font-semibold text-titulo">{f.identificador}</p><p className="text-[12.5px]">{f.nombre}</p>{f.novedad && <p className="text-[11.5px] text-critico">{f.novedad}</p>}</td>
                      <td>{f.lote || <span className="text-texto-3">—</span>}</td>
                      <td className="max-w-sm text-[12.5px]">{f.titulo || <span className="text-texto-3">—</span>}</td>
                      <td className="text-[12.5px]">{f.hoja_control === "no_aplica" ? <span className="text-texto-3">no lleva</span> : f.hoja_control ?? <span className="text-texto-3">sin hoja</span>}</td>
                      <td><Insignia tono={TONO_ESTADO_DESC[f.estado]} punto>{NOMBRE_ESTADO_DESC[f.estado]}</Insignia></td>
                      <td className="text-right">{f.estado !== "no_aplica" && <Link className="text-[13px] font-semibold text-marca hover:underline" href={`/proyectos/${proyecto.id}/descripciones/${f.unidad_id}`}>{f.estado === "sin_descripcion" ? "Describir" : f.estado === "en_revision" ? "Revisar" : "Abrir"} →</Link>}</td>
                    </tr>
                  ))}
                </tbody>
              </Tabla>
            )}
            <Paginador total={datos.datos?.total ?? 0} pagina={pagina} porPagina={POR_PAGINA} alCambiar={setPagina} />
          </div>
        </>
      )}
    </div>
  );
}

function ProcesosPorLote({ proyecto, alCambiar }: { proyecto: Proyecto; alCambiar: () => void }) {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const lotes = useDatos(() => api<ProcesoLote[]>(`/proyectos/${proyecto.id}/procesos-por-lote`), [proyecto.id]);
  const [editando, setEditando] = useState<ProcesoLote | null>(null);
  const [hoja, setHoja] = useState(true);
  const [isadg, setIsadg] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [guardando, setGuardando] = useState(false);
  const gestiona = puede(PERMISOS.proyectos);
  const abrir = (l: ProcesoLote) => (setEditando(l), setHoja(l.hoja_control), setIsadg(l.isadg), setMotivo(""));
  async function guardar() {
    if (!editando) return;
    setGuardando(true);
    try {
      await api(`/proyectos/${proyecto.id}/procesos-por-lote`, { metodo: "PUT", cuerpo: { lote: editando.lote, hoja_control: hoja, isadg, motivo: motivo.trim() } });
      avisos.exito("Configuración guardada.");
      setEditando(null);
      void lotes.recargar();
      alCambiar();
    } catch (e) {
      avisos.error((e as Error).message);
    } finally {
      setGuardando(false);
    }
  }
  return (
    <section className="rounded-xl border border-line bg-surface shadow-xs">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
        <div>
          <p className="flex items-center gap-2 font-semibold text-titulo"><Layers3 className="size-5 text-marca" />Qué lleva cada lote</p>
          <p className="text-[12.5px] text-texto-3">El lote es el de la base de cajas (Productividad). Lo que no se configure para un lote toma lo del proyecto.</p>
        </div>
      </header>
      {!lotes.datos ? <Cargando /> : (
        <Tabla>
          <thead><tr><th>Lote</th><th>Cajas</th><th>Unidades</th><th>Hoja de control</th><th>Descripción ISAD(G)</th><th /></tr></thead>
          <tbody>
            {lotes.datos.map((l) => (
              <tr key={l.lote || "-"}>
                <td>{l.nombre}{!l.configurado && <span className="block text-[11.5px] text-texto-3">{l.lote ? "toma lo del proyecto" : "valor por defecto"}</span>}{l.motivo && <span className="block text-[11.5px] text-texto-3">{l.motivo}</span>}</td>
                <td className="tabular">{numero(l.cajas)}</td>
                <td className="tabular">{numero(l.unidades)}</td>
                <td><Insignia tono={l.hoja_control ? "ok" : "neutro"}>{l.hoja_control ? "Sí" : "No"}</Insignia></td>
                <td><Insignia tono={l.isadg ? "ok" : "neutro"}>{l.isadg ? "Sí" : "No"}</Insignia></td>
                <td className="text-right">{gestiona && <Boton tamano="sm" variante="fantasma" onClick={() => abrir(l)}>Configurar</Boton>}</td>
              </tr>
            ))}
          </tbody>
        </Tabla>
      )}
      {editando && (
        <Modal abierto alCerrar={() => setEditando(null)} titulo={`Configurar · ${editando.nombre}`} descripcion="Al menos uno de los dos procesos. El cambio queda en la auditoría con su motivo."
          pie={<><Boton onClick={() => setEditando(null)}>Cancelar</Boton><Boton variante="primario" icono={<Save />} cargando={guardando} disabled={motivo.trim().length < 5 || (!hoja && !isadg)} onClick={guardar}>Guardar</Boton></>}>
          <div className="flex flex-col gap-3">
            <label className="flex items-center gap-2 text-[13.5px]"><input type="checkbox" checked={hoja} onChange={(e) => setHoja(e.target.checked)} /> Lleva hoja de control</label>
            <label className="flex items-center gap-2 text-[13.5px]"><input type="checkbox" checked={isadg} onChange={(e) => setIsadg(e.target.checked)} /> Lleva descripción ISAD(G)</label>
            {!hoja && isadg && <Nota tono="info">Sin hoja de control, la descripción se arma con lo que lea el OCR de las páginas digitalizadas.</Nota>}
            <Campo etiqueta="Motivo" requerido><Area value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Lo definió la entidad en el acta de inicio…" /></Campo>
          </div>
        </Modal>
      )}
    </section>
  );
}
