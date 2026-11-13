"use client";

import { ClipboardList, FileSearch, FileSpreadsheet, FileText, ScanText, Search, Square, Upload } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { useAvisos } from "@/components/ui/avisos";
import { Boton, Cargando, Indicador, Insignia, Modal, Nota, Paginador, Pestanas, Progreso, Tabla, Vacio } from "@/components/ui/basicos";
import { Campo, Entrada, Selector } from "@/components/ui/campos";
import { api, apiSubir } from "@/lib/api";
import { numero } from "@/lib/formato";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { EstadoHoja, FilaBandejaHoja, Proyecto, ResumenOcr } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

export const NOMBRE_ESTADO_HOJA: Record<EstadoHoja, string> = { sin_hoja: "Sin hoja", borrador: "En elaboración", en_revision: "En verificación", devuelta: "Devuelta", verificada: "Verificada", no_aplica: "No aplica (lote sin hoja)" };
export const TONO_ESTADO_HOJA = { sin_hoja: "neutro", borrador: "info", en_revision: "aviso", devuelta: "critico", verificada: "ok", no_aplica: "neutro" } as const;
const POR_PAGINA = 100;

/** Bandeja de hojas de control: qué expedientes tienen hoja, en qué estado, y lo digitalizado que aún no la tiene. */
export function HojasControl({ proyecto }: { proyecto: Proyecto }) {
  const { puede } = useSesion();
  const base = `/proyectos/${proyecto.id}/hojas-control`;
  const [estado, setEstado] = useState<EstadoHoja | "todas">("todas");
  const [q, setQ] = useState("");
  const [pagina, setPagina] = useState(1);
  const [importando, setImportando] = useState(false);
  const datos = useDatos(
    () => api<{ total: number; filas: FilaBandejaHoja[]; cuenta: Record<EstadoHoja | "digitalizadas_sin_hoja", number> }>(base, { consulta: { estado: estado === "todas" ? null : estado, q, desplazamiento: (pagina - 1) * POR_PAGINA, limite: POR_PAGINA } }),
    [base, estado, q, pagina],
  );
  const c = datos.datos?.cuenta;
  if (!c) return <Cargando />;
  const total = Object.entries(c).filter(([k]) => k !== "digitalizadas_sin_hoja").reduce((a, [, v]) => a + v, 0);
  return (
    <div className="flex flex-col gap-5 p-5">
      <Nota tono="info">
        La hoja de control se elabora sobre lo digitalizado: cada trámite queda amarrado a sus páginas, los folios se calculan solos y cada dato dice de dónde salió. La verifica otra persona, trámite por trámite, con los documentos al lado. Las hojas que el equipo ya tiene en Excel se importan.
      </Nota>
      <div className="grid gap-3 sm:grid-cols-5">
        <Indicador etiqueta="Digitalizadas sin hoja" valor={numero(c.digitalizadas_sin_hoja)} tono="neutro" icono={<FileText />} />
        <Indicador etiqueta="En elaboración" valor={numero(c.borrador)} tono="info" icono={<ClipboardList />} />
        <Indicador etiqueta="En verificación" valor={numero(c.en_revision)} tono="aviso" icono={<ClipboardList />} />
        <Indicador etiqueta="Devueltas" valor={numero(c.devuelta)} tono="critico" icono={<ClipboardList />} />
        <Indicador etiqueta="Verificadas" valor={numero(c.verificada)} tono="ok" icono={<ClipboardList />} />
      </div>
      <PanelOcr proyecto={proyecto} />
      <div className="rounded-xl border border-line">
        <div className="px-4 pt-1">
          <Pestanas valor={estado} alCambiar={(v) => (setEstado(v), setPagina(1))} opciones={[
            { valor: "todas", etiqueta: `Todas (${numero(total)})` },
            ...(Object.keys(NOMBRE_ESTADO_HOJA) as EstadoHoja[]).map((k) => ({ valor: k, etiqueta: `${NOMBRE_ESTADO_HOJA[k]} (${numero(c[k])})` })),
          ]} />
        </div>
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-texto-3" />
            <Entrada className="pl-9" value={q} onChange={(e) => (setQ(e.target.value), setPagina(1))} placeholder="Buscar expediente o caja" aria-label="Buscar" />
          </div>
          {puede(PERMISOS.hojaControl) && <Boton className="ml-auto" icono={<Upload />} onClick={() => setImportando(true)}>Importar hojas de Excel</Boton>}
        </div>
        {!datos.datos?.filas.length ? <Vacio icono={<ClipboardList />} titulo="No hay expedientes con este filtro" /> : (
          <Tabla>
            <thead><tr><th>Expediente</th><th>Caja · carpeta</th><th>Imágenes</th><th>Folios (FUID)</th><th>Trámites</th><th>Folios (hoja)</th><th>Estado</th><th /></tr></thead>
            <tbody>
              {datos.datos.filas.map((f) => (
                <tr key={f.unidad_id}>
                  <td className="max-w-xs"><p className="font-semibold text-titulo">{f.identificador}</p><p className="text-[12.5px]">{f.nombre}</p>{f.novedad && <p className="text-[11.5px] text-critico">{f.novedad}</p>}</td>
                  <td className="whitespace-nowrap">{f.caja ?? "—"} · {f.carpeta ?? "—"}</td>
                  <td className="tabular">{f.imagenes ? numero(f.imagenes) : <span className="text-texto-3">sin digitalizar</span>}</td>
                  <td className="tabular">{f.folios_fuid ?? "—"}</td>
                  <td className="tabular">{f.estado === "sin_hoja" ? "—" : numero(f.tramites)}</td>
                  <td className="tabular">{f.total_folios ?? "—"}{f.total_folios != null && f.folios_fuid != null && f.total_folios !== f.folios_fuid && <span className="ml-1 text-[11.5px] text-aviso">≠ FUID</span>}</td>
                  <td><Insignia tono={TONO_ESTADO_HOJA[f.estado]} punto>{NOMBRE_ESTADO_HOJA[f.estado]}</Insignia></td>
                  <td className="text-right"><Link className="text-[13px] font-semibold text-marca hover:underline" href={`/proyectos/${proyecto.id}/hojas/${f.unidad_id}`}>{f.estado === "sin_hoja" ? "Elaborar" : f.estado === "en_revision" ? "Verificar" : "Abrir"} →</Link></td>
                </tr>
              ))}
            </tbody>
          </Tabla>
        )}
        <Paginador total={datos.datos?.total ?? 0} pagina={pagina} porPagina={POR_PAGINA} alCambiar={setPagina} />
      </div>
      {importando && <Importar base={base} alCerrar={() => setImportando(false)} alImportar={() => void datos.recargar()} />}
    </div>
  );
}

function Importar({ base, alCerrar, alImportar }: { base: string; alCerrar: () => void; alImportar: () => void }) {
  const avisos = useAvisos();
  const entrada = useRef<HTMLInputElement>(null);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [ipf, setIpf] = useState("1");
  const [reporte, setReporte] = useState<{ pestana: string; carpeta: string; tramites: number; resultado: string; unidad: string | null; avisos: string[] }[] | null>(null);
  const [enviando, setEnviando] = useState(false);
  async function importar() {
    if (!archivo) return;
    setEnviando(true);
    try {
      const datos = new FormData();
      datos.append("archivo", archivo);
      datos.append("imagenes_por_folio", ipf);
      const r = await apiSubir<typeof reporte>(base + "/importar", datos);
      setReporte(r);
      avisos.exito(`${r!.filter((x) => x.resultado === "importada").length} de ${r!.length} hojas importadas.`);
      alImportar();
    } catch (e) {
      avisos.error((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }
  return (
    <Modal abierto ancho="lg" alCerrar={alCerrar} titulo="Importar hojas de control de Excel"
      descripcion="Una hoja por pestaña. ARCA reconoce la carpeta por el nombre de la pestaña, del archivo o por lo que diga el encabezado, y la confirma contra el inventario. Nunca inventa una fecha ni un folio que no estén escritos."
      pie={<><Boton onClick={alCerrar}>Cerrar</Boton>{!reporte && <Boton variante="primario" icono={<Upload />} cargando={enviando} disabled={!archivo} onClick={importar}>Importar</Boton>}</>}>
      {!reporte ? (
        <div className="flex flex-col gap-3">
          <Campo etiqueta="Libro de Excel (.xlsx)" requerido>
            <div className="flex items-center gap-2">
              <input ref={entrada} type="file" accept=".xlsx" hidden onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
              <Boton icono={<FileSpreadsheet />} onClick={() => entrada.current?.click()}>Elegir archivo</Boton>
              <span className="text-[13px] text-texto-2">{archivo?.name ?? "Ninguno"}</span>
            </div>
          </Campo>
          <Campo etiqueta="Imágenes por folio" ayuda="Para relacionar después los folios con lo digitalizado.">
            <Selector value={ipf} onChange={(e) => setIpf(e.target.value)}><option value="1">1 · cada imagen es un folio</option><option value="2">2 · recto y verso</option></Selector>
          </Campo>
        </div>
      ) : (
        <Tabla className="rounded-xl border border-line">
          <thead><tr><th>Pestaña</th><th>Trámites</th><th>Resultado</th></tr></thead>
          <tbody>
            {reporte.map((r, i) => (
              <tr key={i}>
                <td>{r.pestana || "—"}</td>
                <td className="tabular">{r.tramites}</td>
                <td>{r.resultado === "importada" ? <Insignia tono="ok">Importada en {r.unidad}</Insignia> : <span className="text-[12.5px] text-critico">{r.resultado}</span>}{r.avisos.map((a) => <p key={a} className="text-[11.5px] text-aviso">{a}</p>)}</td>
              </tr>
            ))}
          </tbody>
        </Tabla>
      )}
    </Modal>
  );
}

/** OCR local del proyecto: avance, lectura por tandas (hasta que exista la cola de procesos) y búsqueda en el contenido. */
function PanelOcr({ proyecto }: { proyecto: Proyecto }) {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const base = `/proyectos/${proyecto.id}/ocr`;
  const r = useDatos(() => api<ResumenOcr>(`${base}/resumen`), [base]);
  const [leyendo, setLeyendo] = useState(false);
  const detener = useRef(false);
  const [q, setQ] = useState("");
  const [hallados, setHallados] = useState<{ unidad_id: string; identificador: string; nombre: string; pagina_en_archivo: number; fragmento: string; confianza: number | null }[] | null>(null);
  async function leer() {
    setLeyendo(true);
    detener.current = false;
    try {
      for (let vuelta = 0; vuelta < 500 && !detener.current; vuelta++) {
        const x = await api<{ procesadas: number; pendientes: number }>(`${base}/leer`, { metodo: "POST", consulta: { limite: 10 } });
        await r.recargar();
        if (!x.pendientes || !x.procesadas) break;
      }
      avisos.exito(detener.current ? "Lectura detenida. Puede continuar cuando quiera." : "OCR al día.");
    } catch (e) {
      avisos.error((e as Error).message);
    } finally {
      setLeyendo(false);
    }
  }
  async function buscar() {
    try {
      setHallados(await api(`${base}/buscar`, { consulta: { q: q.trim() } }));
    } catch (e) {
      avisos.error((e as Error).message);
    }
  }
  const x = r.datos;
  if (!x) return null;
  const hechas = x.leidas + x.sin_texto + x.errores;
  return (
    <section className="rounded-xl border border-line bg-surface p-4 shadow-xs">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 font-semibold text-titulo"><ScanText className="size-5 text-marca" />OCR local</p>
          <p className="text-[12.5px] text-texto-3">
            {x.disponible ? `${x.motor} · idiomas: ${x.idiomas.filter((i) => i !== "osd").join(", ")} · en el servidor: los documentos no salen de él` : "No disponible en este servidor: instale tesseract-ocr y tesseract-ocr-spa."}
          </p>
        </div>
        {x.disponible && puede(PERMISOS.capturar) && x.pendientes > 0 && (
          leyendo ? <Boton icono={<Square />} onClick={() => (detener.current = true)}>Detener</Boton> : <Boton variante="primario" icono={<ScanText />} onClick={leer}>Leer {numero(x.pendientes)} páginas pendientes</Boton>
        )}
      </div>
      {x.paginas > 0 && (
        <div className="mt-3">
          <Progreso valor={Math.round((hechas / x.paginas) * 100)} />
          <p className="mt-1 text-[12.5px] text-texto-2">
            {numero(x.leidas)} de {numero(x.paginas)} páginas leídas{x.confianza_media != null ? ` · confianza media ${x.confianza_media} %` : ""}{x.confianza_baja ? ` · ${numero(x.confianza_baja)} con confianza baja` : ""}{x.sin_texto ? ` · ${numero(x.sin_texto)} sin texto` : ""}{x.errores ? ` · ${numero(x.errores)} con error` : ""}
          </p>
        </div>
      )}
      {x.leidas > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Entrada className="max-w-sm" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && q.trim().length >= 3 && buscar()} placeholder="Buscar en el contenido de los documentos" aria-label="Buscar en el contenido" />
          <Boton icono={<FileSearch />} disabled={q.trim().length < 3} onClick={buscar}>Buscar</Boton>
        </div>
      )}
      {hallados && (
        <ul className="mt-2 divide-y divide-line rounded-xl border border-line">
          {!hallados.length && <li className="px-3 py-2 text-[13px] text-texto-3">No aparece en el texto leído.</li>}
          {hallados.map((h, i) => (
            <li key={i} className="px-3 py-2 text-[13px]">
              <Link className="font-semibold text-marca hover:underline" href={`/proyectos/${proyecto.id}/hojas/${h.unidad_id}`}>{h.identificador}</Link> · {h.nombre} <span className="text-texto-3">· página {h.pagina_en_archivo} del archivo</span>
              <p className="font-mono text-[12px] text-texto-2">…{h.fragmento}…</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
