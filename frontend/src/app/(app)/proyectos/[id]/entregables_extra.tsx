"use client";

import { FileBarChart2, ImageUp, ListOrdered, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useAvisos } from "@/components/ui/avisos";
import { Boton, Insignia } from "@/components/ui/basicos";
import { Campo, Entrada, Selector } from "@/components/ui/campos";
import { api, apiSubir, urlLocal } from "@/lib/api";
import { descargarArchivo } from "@/lib/descargas";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import { useDatos } from "@/lib/use-datos";

const tarjeta = "rounded-xl border border-line bg-surface p-4 shadow-xs";
const titulo = "flex items-center gap-2 font-semibold text-titulo [&_svg]:size-5 [&_svg]:text-marca";

/** El logo de la entidad: va en el encabezado de los PDF (entregables e informe de avance). */
export function LogoEntidad({ proyectoId }: { proyectoId: string }) {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const [url, setUrl] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [subiendo, setSubiendo] = useState(false);
  const entrada = useRef<HTMLInputElement>(null);
  useEffect(() => {
    let vivo = true;
    let actual: string | null = null;
    urlLocal(`/proyectos/${proyectoId}/logo`).then((u) => (vivo ? (actual = u, setUrl(u)) : URL.revokeObjectURL(u))).catch(() => vivo && setUrl(null));
    return () => {
      vivo = false;
      if (actual) URL.revokeObjectURL(actual);
    };
  }, [proyectoId, version]);

  async function subir(archivo: File) {
    setSubiendo(true);
    try {
      const datos = new FormData();
      datos.append("archivo", archivo);
      await apiSubir(`/proyectos/${proyectoId}/logo`, datos);
      avisos.exito("Logo guardado. Saldrá en los PDF del proyecto.");
      setVersion((v) => v + 1);
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setSubiendo(false);
      if (entrada.current) entrada.current.value = "";
    }
  }

  return (
    <div className={tarjeta}>
      <span className={titulo}><ImageUp />Logo de la entidad</span>
      <div className="mt-2 flex flex-wrap items-center gap-4">
        <div className="grid h-16 w-48 place-items-center rounded-lg border border-dashed border-line bg-canvas">
          {url ? <img src={url} alt="Logo de la entidad" className="max-h-14 max-w-44 object-contain" /> : <span className="text-[12px] text-texto-3">Sin logo</span>}
        </div>
        <p className="max-w-md text-[12.5px] text-texto-3">Va en el encabezado de los PDF: los entregables descargados en PDF y el informe de avance. PNG o JPEG de hasta 2 MB.</p>
        {puede(PERMISOS.proyectos) && (
          <>
            <input ref={entrada} type="file" accept="image/png,image/jpeg" hidden onChange={(e) => e.target.files?.[0] && subir(e.target.files[0])} />
            <Boton icono={<ImageUp />} cargando={subiendo} onClick={() => entrada.current?.click()}>{url ? "Cambiar el logo" : "Subir el logo"}</Boton>
          </>
        )}
      </div>
    </div>
  );
}

/** El informe de avance para la interventoría, del periodo elegido, en PDF/A o Excel. */
export function InformeAvance({ proyectoId, codigo }: { proyectoId: string; codigo: string }) {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const hoy = new Date().toISOString().slice(0, 10);
  const [desde, setDesde] = useState(`${hoy.slice(0, 8)}01`);
  const [hasta, setHasta] = useState(hoy);
  const [generando, setGenerando] = useState<string | null>(null);
  if (!puede(PERMISOS.productividadLeer)) return null;

  async function generar(formato: "pdf" | "xlsx") {
    setGenerando(formato);
    try {
      await descargarArchivo(`/proyectos/${proyectoId}/informe-avance?desde=${desde}&hasta=${hasta}&formato=${formato}`, `Informe_avance_${codigo}_${desde}_${hasta}.${formato}`);
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setGenerando(null);
    }
  }

  return (
    <div className={tarjeta}>
      <span className={titulo}><FileBarChart2 />Informe de avance para la interventoría</span>
      <p className="mt-1 max-w-3xl text-[12.5px] text-texto-3">Lo arma ARCA con los datos del periodo: avance por frente, digitalización y OCR, alistamiento y conservación, hojas de control, inspección por lote, historias laborales, entregas, novedades abiertas y la verificación de la auditoría. El mismo periodo da los mismos números.</p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <Campo etiqueta="Desde"><Entrada type="date" value={desde} onChange={(e) => setDesde(e.target.value)} /></Campo>
        <Campo etiqueta="Hasta"><Entrada type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} /></Campo>
        <Boton variante="primario" icono={<FileBarChart2 />} cargando={generando === "pdf"} onClick={() => generar("pdf")}>PDF/A</Boton>
        <Boton icono={<FileBarChart2 />} cargando={generando === "xlsx"} onClick={() => generar("xlsx")}>Excel</Boton>
      </div>
    </div>
  );
}

type Columna = { nombre: string; campo: string };
type ConfigIndice = { por: "expediente" | "documento"; separador: string; nombre_archivo: string; columnas: Columna[] };

/** El archivo de indexación que pide el SGDEA de la entidad: columnas configurables, va en el paquete de entrega. */
export function Indexacion({ proyectoId }: { proyectoId: string }) {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const datos = useDatos(() => api<{ campos: Record<string, string>; config: ConfigIndice | null }>(`/proyectos/${proyectoId}/entrega/indexacion`), [proyectoId]);
  const [editando, setEditando] = useState(false);
  const [config, setConfig] = useState<ConfigIndice>({ por: "expediente", separador: ";", nombre_archivo: "indice.csv", columnas: [{ nombre: "EXPEDIENTE", campo: "unidad.identificador" }, { nombre: "RUTA", campo: "pdf.ruta" }] });
  const [motivo, setMotivo] = useState("");
  const [guardando, setGuardando] = useState(false);
  useEffect(() => { if (datos.datos?.config) setConfig(datos.datos.config); }, [datos.datos]);
  const campos = datos.datos?.campos ?? {};
  const cambiar = (i: number, c: Partial<Columna>) => setConfig({ ...config, columnas: config.columnas.map((x, j) => (j === i ? { ...x, ...c } : x)) });

  async function guardar() {
    setGuardando(true);
    try {
      await api("/configuracion/parametros", { metodo: "POST", cuerpo: { clave: "entrega.indexacion", proyecto_id: proyectoId, valor: config, motivo } });
      avisos.exito("Archivo de indexación configurado. Saldrá en los próximos paquetes de entrega.");
      setEditando(false);
      setMotivo("");
      datos.recargar();
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setGuardando(false);
    }
  }

  const vigente = datos.datos?.config;
  return (
    <div className={tarjeta}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className={titulo}><ListOrdered />Archivo de indexación para el SGDEA</span>
        {vigente ? <Insignia tono="ok" punto>Configurado · {vigente.nombre_archivo}</Insignia> : <Insignia tono="neutro" punto>Sin configurar</Insignia>}
      </div>
      <p className="mt-1 max-w-3xl text-[12.5px] text-texto-3">Las columnas con los nombres que pida el SGDEA de la entidad para cargar los expedientes. Va dentro del paquete de entrega, con su huella en el manifiesto.</p>
      {vigente && !editando && <p className="mt-2 text-[12.5px] text-texto-2">Una fila por {vigente.por} · {vigente.columnas.map((c) => c.nombre).join(" · ")}</p>}
      {puede(PERMISOS.proyectos) && !editando && <div className="mt-2"><Boton tamano="sm" onClick={() => setEditando(true)}>{vigente ? "Cambiar" : "Configurar"}</Boton></div>}
      {editando && (
        <div className="mt-3 flex flex-col gap-2">
          <div className="grid gap-3 sm:grid-cols-3">
            <Campo etiqueta="Una fila por"><Selector value={config.por} onChange={(e) => setConfig({ ...config, por: e.target.value as ConfigIndice["por"] })}><option value="expediente">Expediente</option><option value="documento">Documento de la hoja de control</option></Selector></Campo>
            <Campo etiqueta="Separador"><Selector value={config.separador} onChange={(e) => setConfig({ ...config, separador: e.target.value })}><option value=";">Punto y coma</option><option value=",">Coma</option><option value="|">Barra |</option><option value={"\t"}>Tabulador</option></Selector></Campo>
            <Campo etiqueta="Nombre del archivo"><Entrada value={config.nombre_archivo} onChange={(e) => setConfig({ ...config, nombre_archivo: e.target.value })} /></Campo>
          </div>
          {config.columnas.map((c, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <Entrada className="w-56" aria-label={`Nombre de la columna ${i + 1}`} value={c.nombre} onChange={(e) => cambiar(i, { nombre: e.target.value })} />
              <Selector className="min-w-72 flex-1" aria-label={`Campo de la columna ${i + 1}`} value={c.campo.startsWith("fijo:") ? "fijo" : c.campo} onChange={(e) => cambiar(i, { campo: e.target.value === "fijo" ? "fijo:" : e.target.value })}>
                {Object.entries(campos).filter(([k]) => config.por === "documento" || !k.startsWith("documento.")).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                <option value="fijo">Texto fijo…</option>
              </Selector>
              {c.campo.startsWith("fijo:") && <Entrada className="w-48" aria-label={`Texto fijo de la columna ${i + 1}`} value={c.campo.slice(5)} onChange={(e) => cambiar(i, { campo: `fijo:${e.target.value}` })} />}
              <Boton tamano="sm" variante="fantasma" icono={<Trash2 />} aria-label="Quitar columna" onClick={() => setConfig({ ...config, columnas: config.columnas.filter((_, j) => j !== i) })} />
            </div>
          ))}
          <div><Boton tamano="sm" variante="fantasma" icono={<Plus />} onClick={() => setConfig({ ...config, columnas: [...config.columnas, { nombre: "", campo: "unidad.identificador" }] })}>Agregar columna</Boton></div>
          <div className="flex flex-wrap items-end gap-3">
            <Campo etiqueta="Motivo" className="min-w-72 flex-1" requerido><Entrada value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Ej.: formato de cargue entregado por la entidad" /></Campo>
            <Boton variante="primario" icono={<Save />} cargando={guardando} disabled={motivo.trim().length < 5 || !config.columnas.length} onClick={guardar}>Guardar</Boton>
            <Boton variante="fantasma" onClick={() => setEditando(false)}>Cancelar</Boton>
          </div>
        </div>
      )}
    </div>
  );
}
