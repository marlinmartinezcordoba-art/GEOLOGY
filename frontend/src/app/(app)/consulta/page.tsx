"use client";

import { Download, FileSearch, Lock, Search, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useAvisos } from "@/components/ui/avisos";
import { Boton, Cargando, EncabezadoPagina, Insignia, Nota, Paginador, Tarjeta, Vacio } from "@/components/ui/basicos";
import { Campo, Entrada, Selector } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { descargarArchivo } from "@/lib/descargas";
import { fecha, numero } from "@/lib/formato";
import type { FuenteConsulta, ResultadoConsulta } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

const POR_PAGINA = 25;
const FUENTE: Record<FuenteConsulta, string> = { metadatos: "FUID y clasificación", ocr: "Texto OCR", hoja: "Hoja de control", descripcion: "Descripción ISAD(G)" };
const FASE: Record<string, string> = { gestion: "Archivo de gestión", central: "Archivo central", historico: "Archivo histórico", eliminada: "Eliminada" };
type Filtros = { q: string; proyecto_id: string; codigo: string; dependencia: string; caja: string; fase: string; desde: string; hasta: string; digitalizadas: boolean; con_hoja: boolean; descritas: boolean; fuentes: FuenteConsulta[] };
const VACIO: Filtros = { q: "", proyecto_id: "", codigo: "", dependencia: "", caja: "", fase: "", desde: "", hasta: "", digitalizadas: false, con_hoja: false, descritas: false, fuentes: [] };

function consulta(f: Filtros, extra: Record<string, string | number> = {}): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) {
    if (k === "fuentes") (v as string[]).forEach((x) => p.append("fuentes", x));
    else if (typeof v === "boolean") { if (v) p.set(k, "true"); }
    else if (v) p.set(k, String(v));
  }
  for (const [k, v] of Object.entries(extra)) p.set(k, String(v));
  return p.toString();
}

/** Resalta en el fragmento las palabras buscadas, sin importar tildes ni mayúsculas. */
function Resaltado({ texto, terminos }: { texto: string; terminos: string[] }) {
  const sin = (t: string) => Array.from(t).map((c) => c.normalize("NFD").replace(/[̀-ͯ]/g, "")[0]?.toLowerCase() ?? " ").join("");
  const normal = sin(texto);
  const marcas: [number, number][] = [];
  for (const t of terminos) {
    let i = normal.indexOf(t);
    while (t && i >= 0) {
      marcas.push([i, i + t.length]);
      i = normal.indexOf(t, i + t.length);
    }
  }
  marcas.sort((a, b) => a[0] - b[0]);
  const partes: React.ReactNode[] = [];
  let cursor = 0;
  marcas.forEach(([a, b], k) => {
    if (a < cursor) return;
    partes.push(texto.slice(cursor, a), <mark key={k} className="rounded-sm bg-aviso-suave text-titulo">{texto.slice(a, b)}</mark>);
    cursor = b;
  });
  partes.push(texto.slice(cursor));
  return <>{partes}</>;
}

/** M23 · Consulta en los expedientes de los proyectos del alcance: metadatos, texto OCR, hoja de control verificada y descripción aprobada. */
export default function Consulta() {
  const avisos = useAvisos();
  const proyectos = useDatos(() => api<{ id: string; codigo: string; nombre: string }[]>("/consulta/proyectos"), []);
  const [borrador, setBorrador] = useState<Filtros>(VACIO);
  const [filtros, setFiltros] = useState<Filtros | null>(null);
  const [pagina, setPagina] = useState(1);
  const [verFiltros, setVerFiltros] = useState(false);
  const [r, setR] = useState<ResultadoConsulta | null>(null);
  const [cargando, setCargando] = useState(false);
  const [exportando, setExportando] = useState(false);

  useEffect(() => {
    if (!filtros) return;
    let vivo = true;
    setCargando(true);
    api<ResultadoConsulta>(`/consulta/buscar?${consulta(filtros, { desplazamiento: (pagina - 1) * POR_PAGINA, limite: POR_PAGINA })}`)
      .then((x) => vivo && setR(x))
      .catch((e) => avisos.error(e.message))
      .finally(() => vivo && setCargando(false));
    return () => {
      vivo = false;
    };
  }, [filtros, pagina, avisos]);

  const buscar = () => (setPagina(1), setFiltros({ ...borrador }));
  const cambia = <K extends keyof Filtros>(k: K, v: Filtros[K]) => setBorrador((f) => ({ ...f, [k]: v }));
  async function exportar() {
    if (!filtros) return;
    setExportando(true);
    try {
      await descargarArchivo(`/consulta/exportar?${consulta(filtros)}`, "Consulta_ARCA.xlsx");
    } catch (e) {
      avisos.error((e as Error).message);
    } finally {
      setExportando(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <EncabezadoPagina titulo="Consulta" descripcion="Busque en los expedientes de sus proyectos: en el FUID y la clasificación, en el texto leído de los documentos, en la hoja de control verificada y en la descripción aprobada." />
      <Tarjeta className="p-4">
        <form className="flex flex-col gap-3" onSubmit={(e) => (e.preventDefault(), buscar())}>
          <div className="flex flex-wrap gap-2">
            <div className="relative min-w-72 flex-1">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-texto-3" />
              <Entrada className="pl-9" value={borrador.q} onChange={(e) => cambia("q", e.target.value)} placeholder='Palabras o "frase exacta"; sin importar tildes ni mayúsculas' aria-label="Buscar" />
            </div>
            <Selector className="w-auto" aria-label="Proyecto" value={borrador.proyecto_id} onChange={(e) => cambia("proyecto_id", e.target.value)}>
              <option value="">Todos mis proyectos</option>
              {proyectos.datos?.map((p) => <option key={p.id} value={p.id}>{p.codigo} · {p.nombre}</option>)}
            </Selector>
            <Boton type="button" icono={<SlidersHorizontal />} onClick={() => setVerFiltros((v) => !v)}>Filtros</Boton>
            <Boton type="submit" variante="primario" icono={<FileSearch />}>Buscar</Boton>
          </div>
          {verFiltros && (
            <div className="grid gap-3 rounded-xl border border-line bg-surface-muted p-3 sm:grid-cols-2 lg:grid-cols-4">
              <Campo etiqueta="Serie o subserie (código)"><Entrada value={borrador.codigo} onChange={(e) => cambia("codigo", e.target.value)} placeholder="100-02" /></Campo>
              <Campo etiqueta="Dependencia (código)"><Entrada value={borrador.dependencia} onChange={(e) => cambia("dependencia", e.target.value)} placeholder="100" /></Campo>
              <Campo etiqueta="Caja"><Entrada value={borrador.caja} onChange={(e) => cambia("caja", e.target.value)} /></Campo>
              <Campo etiqueta="Fase">
                <Selector value={borrador.fase} onChange={(e) => cambia("fase", e.target.value)}><option value="">Todas</option>{Object.entries(FASE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Selector>
              </Campo>
              <Campo etiqueta="Fechas desde"><Entrada type="date" value={borrador.desde} onChange={(e) => cambia("desde", e.target.value)} /></Campo>
              <Campo etiqueta="Hasta"><Entrada type="date" value={borrador.hasta} onChange={(e) => cambia("hasta", e.target.value)} /></Campo>
              <Campo etiqueta="Buscar en" className="lg:col-span-2">
                <div className="flex flex-wrap gap-3 pt-1 text-[13px]">
                  {(Object.keys(FUENTE) as FuenteConsulta[]).map((k) => (
                    <label key={k} className="flex items-center gap-1.5"><input type="checkbox" checked={borrador.fuentes.length === 0 || borrador.fuentes.includes(k)}
                      onChange={(e) => { const actual = borrador.fuentes.length ? borrador.fuentes : (Object.keys(FUENTE) as FuenteConsulta[]); cambia("fuentes", e.target.checked ? [...new Set([...actual, k])] : actual.filter((x) => x !== k)); }} />{FUENTE[k]}</label>
                  ))}
                </div>
              </Campo>
              <div className="flex flex-wrap gap-3 text-[13px] lg:col-span-4">
                <label className="flex items-center gap-1.5"><input type="checkbox" checked={borrador.digitalizadas} onChange={(e) => cambia("digitalizadas", e.target.checked)} />Solo digitalizadas</label>
                <label className="flex items-center gap-1.5"><input type="checkbox" checked={borrador.con_hoja} onChange={(e) => cambia("con_hoja", e.target.checked)} />Solo con hoja de control verificada</label>
                <label className="flex items-center gap-1.5"><input type="checkbox" checked={borrador.descritas} onChange={(e) => cambia("descritas", e.target.checked)} />Solo con descripción aprobada</label>
                <button type="button" className="ml-auto text-marca hover:underline" onClick={() => setBorrador({ ...VACIO, q: borrador.q, proyecto_id: borrador.proyecto_id })}>Limpiar filtros</button>
              </div>
            </div>
          )}
        </form>
      </Tarjeta>

      {!filtros ? (
        <Vacio icono={<Search />} titulo="Escriba qué busca o use los filtros" descripcion="Se consulta lo validado: la hoja de control verificada y la descripción aprobada, además del FUID, la clasificación y el texto de los documentos." />
      ) : cargando && !r ? <Cargando /> : r && (
        <Tarjeta>
          <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
            <p className="text-[13.5px] text-titulo"><b>{numero(r.total)}</b> {r.total === 1 ? "expediente" : "expedientes"}{r.terminos.length ? <> con <span className="text-texto-2">{r.terminos.join(" · ")}</span></> : null}</p>
            {r.indice.pendientes > 0 && <Insignia tono="aviso">Índice actualizándose: faltan {numero(r.indice.pendientes)}</Insignia>}
            {r.total > 0 && <Boton className="ml-auto" tamano="sm" icono={<Download />} cargando={exportando} onClick={exportar}>Exportar a Excel</Boton>}
          </div>
          {!r.filas.length ? <Vacio icono={<FileSearch />} titulo="No se encontró nada" descripcion="Pruebe con menos palabras o quite algún filtro." /> : (
            <ul className="divide-y divide-line">
              {r.filas.map((x) => (
                <li key={x.unidad_id} className="px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link href={`/consulta/${x.proyecto_id}/${x.unidad_id}${x.coincidencias.find((c) => c.pagina)?.pagina ? `?pagina=${x.coincidencias.find((c) => c.pagina)!.pagina}` : ""}`} className="text-[14.5px] font-semibold text-marca hover:underline">{x.identificador}</Link>
                    <span className="text-[13.5px] text-titulo">{x.titulo || x.nombre}</span>
                    {x.reservada && <Insignia tono={x.contenido_visible ? "aviso" : "critico"}><Lock className="mr-1 inline size-3" />{x.acceso === "reservada" ? "Reservada" : "Clasificada"}{x.contenido_visible ? "" : " · solo metadatos"}</Insignia>}
                  </div>
                  <p className="mt-0.5 text-[12px] text-texto-3">
                    {[x.proyecto, x.clasificacion, x.caja && `caja ${x.caja}${x.carpeta ? ` · carpeta ${x.carpeta}` : ""}`, (x.fecha_inicial || x.fecha_final) && `${fecha(x.fecha_inicial)} – ${fecha(x.fecha_final)}`, FASE[x.fase], x.imagenes ? `${numero(x.imagenes)} imágenes` : "sin digitalizar", x.hoja_verificada && "hoja verificada"].filter(Boolean).join(" · ")}
                  </p>
                  {x.coincidencias.map((c, i) => (
                    <p key={i} className="mt-1 text-[12.5px] text-texto-2">
                      <Insignia tono={c.fuente === "ocr" ? "ia" : c.fuente === "metadatos" ? "neutro" : "info"}>{c.donde === FUENTE[c.fuente] ? FUENTE[c.fuente] : `${FUENTE[c.fuente]} · ${c.donde}`}</Insignia>{" "}
                      <Resaltado texto={c.fragmento} terminos={r.terminos} />
                    </p>
                  ))}
                </li>
              ))}
            </ul>
          )}
          <Paginador total={r.total} pagina={pagina} porPagina={POR_PAGINA} alCambiar={setPagina} />
        </Tarjeta>
      )}
      <Nota tono="info">Cada ficha que se abre queda en la auditoría. En los expedientes con acceso clasificado o reservado según la TRD, solo quien tiene el permiso de consulta reservada ve el contenido.</Nota>
    </div>
  );
}
