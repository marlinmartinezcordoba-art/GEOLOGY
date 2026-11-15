"use client";

import { Archive, Download, FileCheck2, FileOutput, FileStack, Tags } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { useAvisos } from "@/components/ui/avisos";
import { Boton, Cargando, Codigo, Insignia, Nota, Tabla, Vacio } from "@/components/ui/basicos";
import { Campo, Casilla, Entrada, Selector } from "@/components/ui/campos";
import { api, apiSubir } from "@/lib/api";
import { descargarArchivo } from "@/lib/descargas";
import { fechaHora, numero } from "@/lib/formato";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { Expedicion, PaqueteEntrega, Plantilla, Proyecto, TipoPlantilla, ValidacionPdfa } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

const ICONO = { fuid: <FileOutput />, rotulo_caja: <Tags />, rotulo_carpeta: <Tags /> } as Record<string, React.ReactNode>;

/** Expedición de FUID de salida y rótulos sobre las plantillas vigentes de la entidad. */
export function Entregables({ proyecto }: { proyecto: Proyecto }) {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const base = `/proyectos/${proyecto.id}/entregables`;
  const tipos = useDatos(() => api<Record<string, TipoPlantilla>>("/plantillas/tipos"), []);
  const plantillas = useDatos(() => api<Plantilla[]>("/plantillas", { consulta: { proyecto_id: proyecto.id } }), [proyecto.id]);
  const historial = useDatos(() => api<Expedicion[]>(base), [base]);
  const [cajas, setCajas] = useState("");
  const [lote, setLote] = useState("");
  const [enviando, setEnviando] = useState<string | null>(null);
  const puedeExpedir = puede(PERMISOS.expedir);
  const rutaPaquetes = `/proyectos/${proyecto.id}/entrega/paquetes`;
  const paquetes = useDatos(() => api<PaqueteEntrega[]>(rutaPaquetes), [rutaPaquetes]);
  const [soloListos, setSoloListos] = useState(true);
  const enCola = (paquetes.datos ?? []).some((p) => p.estado === "en_cola");
  const refrescar = useRef(() => {});
  refrescar.current = () => void paquetes.recargar();
  useEffect(() => {
    if (!enCola) return;
    const t = setInterval(() => refrescar.current(), 4000);  // el paquete se arma en la cola: se mira hasta que esté listo
    return () => clearInterval(t);
  }, [enCola]);

  async function armarPaquete() {
    setEnviando("paquete");
    try {
      const lista = cajas.split(/[,;\n]/).map((x) => x.trim()).filter(Boolean);
      const r = await api<{ numero: number; unidades: number; pendientes: number }>(rutaPaquetes, { metodo: "POST", cuerpo: { cajas: lista, lote: lote.trim(), solo_listos: soloListos } });
      avisos.exito(`Paquete n.º ${r.numero} en preparación: ${numero(r.unidades)} expedientes${r.pendientes ? ` · ${numero(r.pendientes)} quedan pendientes` : ""}.`);
      void paquetes.recargar();
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setEnviando(null);
    }
  }

  const vigente = (tipo: string) => {
    const candidatas = (plantillas.datos ?? []).filter((p) => p.tipo === tipo).sort((a, b) => (a.proyecto_id ? 0 : 1) - (b.proyecto_id ? 0 : 1));
    for (const p of candidatas) {
      const v = p.versiones.find((x) => x.estado === "vigente");
      if (v) return { plantilla: p, version: v };
    }
    return null;
  };

  async function expedir(tipo: string) {
    setEnviando(tipo);
    try {
      const lista = cajas.split(/[,;\n]/).map((x) => x.trim()).filter(Boolean);
      const e = await api<Expedicion>(base, { metodo: "POST", cuerpo: { tipo, cajas: lista.length ? lista : null, lote: lote.trim() || null } });
      avisos.exito(`${tipos.datos?.[tipo]?.nombre}: ${numero(e.elementos)} ${tipo === "fuid" ? "unidades" : "rótulos"}. Descargando…`);
      await descargarArchivo(`${base}/${e.id}/archivo`, e.nombre_archivo);
      void historial.recargar();
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setEnviando(null);
    }
  }

  if (tipos.cargando && !tipos.datos) return <Cargando />;
  return (
    <div className="flex flex-col gap-5 p-5">
      <Nota tono="info">Los documentos salen sobre las plantillas vigentes de la entidad: primero la del proyecto y, si no hay, la de la organización. Cada expedición queda guardada con su huella y con la versión de la plantilla usada. <Link href="/plantillas" className="font-semibold underline">Administrar plantillas</Link></Nota>
      {puedeExpedir && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo etiqueta="Solo estas cajas" ayuda="Separadas por coma. Vacío = todas."><Entrada value={cajas} onChange={(e) => setCajas(e.target.value)} placeholder="C-0001, C-0002" /></Campo>
          <Campo etiqueta="Solo este lote" ayuda="Según la base de cajas del proyecto."><Entrada value={lote} onChange={(e) => setLote(e.target.value)} /></Campo>
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-3">{/* El acta de eliminación se expide desde su proceso, en Disposición final. */}
        {Object.entries(tipos.datos ?? {}).filter(([clave]) => !["acta_eliminacion", "hoja_control", "descripcion_isadg", "lista_chequeo"].includes(clave)).map(([clave, t]) => {
          const v = vigente(clave);
          return (
            <div key={clave} className="flex flex-col rounded-xl border border-line bg-surface p-4 shadow-xs">
              <span className="flex items-center gap-2 font-semibold text-titulo [&_svg]:size-5 [&_svg]:text-marca">{ICONO[clave]}{t.nombre}</span>
              <span className="mt-1 flex-1 text-[12.5px] text-texto-3">
                {v ? <>Plantilla «{v.plantilla.nombre}» v{v.version.version}{v.version.codigo_formato ? ` · ${v.version.codigo_formato}` : ""}{v.plantilla.proyecto_id ? " · del proyecto" : " · de la organización"}</> : "Sin plantilla vigente."}
              </span>
              <div className="mt-3">
                {v ? (
                  puedeExpedir && <Boton variante="primario" icono={<Download />} cargando={enviando === clave} onClick={() => expedir(clave)}>Expedir</Boton>
                ) : (
                  <Link href="/plantillas" className="text-[13px] font-semibold text-marca hover:underline">Subir la plantilla de la entidad →</Link>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <div className="rounded-xl border border-line bg-surface p-4 shadow-xs">
        <div className="flex flex-col gap-3">
          <div className="max-w-3xl">
            <span className="flex items-center gap-2 font-semibold text-titulo [&_svg]:size-5 [&_svg]:text-marca"><Archive />Paquete de entrega digital</span>
            <p className="mt-1 text-[12.5px] text-texto-3">Un ZIP para cargar en el SGDEA de la entidad: por cada expediente, el PDF/A-2b validado con las páginas derechas y el texto del OCR (se puede buscar), sus metadatos (FUID, TRD, hoja de control y descripción) y la hoja de control; con el manifiesto de huellas SHA-256 y la lista de lo que quedó pendiente. Usa los filtros de cajas y de lote de arriba.</p>
          </div>
          {puedeExpedir && (
            <div className="flex w-full flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
              <Casilla etiqueta="Solo lo que está listo (hoja verificada y descripción aprobada, si su lote las lleva)" checked={soloListos} onChange={(e) => setSoloListos(e.target.checked)} />
              <Boton variante="primario" icono={<Archive />} cargando={enviando === "paquete"} onClick={armarPaquete}>Armar paquete</Boton>
            </div>
          )}
        </div>
        {!!paquetes.datos?.length && (
          <Tabla className="mt-3 rounded-xl border border-line">
            <thead><tr><th>N.º</th><th>Pedido</th><th>Estado</th><th>Expedientes</th><th>PDF/A-2b</th><th>Pendientes</th><th>Tamaño</th><th>Huella SHA-256</th><th /></tr></thead>
            <tbody>
              {paquetes.datos.map((p) => (
                <tr key={p.id}>
                  <td className="tabular font-semibold">{p.numero}</td>
                  <td className="whitespace-nowrap">{fechaHora(p.creado_en)}</td>
                  <td>{p.estado === "listo" ? <Insignia tono="ok" punto>Listo</Insignia> : p.estado === "error" ? <Insignia tono="critico" punto>Error</Insignia> : <Insignia tono="info" punto>Armándose…</Insignia>}{p.error && <p className="mt-1 max-w-xs text-[11.5px] text-critico">{p.error}</p>}</td>
                  <td className="tabular">{numero(p.unidades)}</td>
                  <td>{p.resumen?.pdfa ? <Insignia tono={p.resumen.pdfa.conformes === p.resumen.pdfa.total ? "ok" : "aviso"}>{numero(p.resumen.pdfa.conformes)} de {numero(p.resumen.pdfa.total)}</Insignia> : "—"}</td>
                  <td className="tabular" title={p.pendientes.slice(0, 20).map((x) => `${x.identificador}: ${x.motivo}`).join("\n")}>{numero(p.pendientes.length)}</td>
                  <td className="tabular whitespace-nowrap">{p.tamano ? `${numero(Math.max(1, Math.round(p.tamano / 1024)))} KB` : "—"}</td>
                  <td>{p.sha256 ? <Codigo className="text-[11px]">{p.sha256.slice(0, 16)}…</Codigo> : "—"}</td>
                  <td>{p.estado === "listo" && p.nombre_archivo && puedeExpedir && <Boton tamano="sm" variante="fantasma" icono={<Download />} onClick={() => descargarArchivo(`${rutaPaquetes}/${p.id}/archivo`, p.nombre_archivo!).catch((err) => avisos.error(err.message))}>Descargar</Boton>}</td>
                </tr>
              ))}
            </tbody>
          </Tabla>
        )}
      </div>
      <ValidarPdfa ruta={`/proyectos/${proyecto.id}/entrega/validar-pdfa`} />
      <div>
        <p className="mb-2 font-semibold text-titulo">Documentos expedidos</p>
        {!historial.datos?.length ? <Vacio icono={<FileStack />} titulo="Todavía no se ha expedido nada" /> : (
          <Tabla className="rounded-xl border border-line">
            <thead><tr><th>Fecha</th><th>Documento</th><th>Elementos</th><th>Plantilla</th><th>Filtro</th><th>Huella SHA-256</th><th /></tr></thead>
            <tbody>
              {historial.datos.map((e) => (
                <tr key={e.id}>
                  <td className="whitespace-nowrap">{fechaHora(e.creado_en)}</td>
                  <td>{tipos.datos?.[e.tipo]?.nombre ?? e.tipo}</td>
                  <td className="tabular">{numero(e.elementos)}</td>
                  <td><Insignia tono="marca">v{e.plantilla_version}{e.codigo_formato ? ` · ${e.codigo_formato}` : ""}</Insignia></td>
                  <td className="text-[12px] text-texto-3">{[e.filtro.cajas?.length ? `cajas ${e.filtro.cajas.join(", ")}` : "", e.filtro.lote ? `lote ${e.filtro.lote}` : ""].filter(Boolean).join(" · ") || "Todo"}</td>
                  <td><Codigo className="text-[11px]">{e.sha256.slice(0, 16)}…</Codigo></td>
                  <td><Boton tamano="sm" variante="fantasma" icono={<Download />} onClick={() => descargarArchivo(`${base}/${e.id}/archivo`, e.nombre_archivo).catch((err) => avisos.error(err.message))}>Descargar</Boton></td>
                </tr>
              ))}
            </tbody>
          </Tabla>
        )}
      </div>
    </div>
  );
}

/** Valida un PDF contra PDF/A (por ejemplo, el que entregó un proveedor de digitalización). No lo guarda. */
function ValidarPdfa({ ruta }: { ruta: string }) {
  const avisos = useAvisos();
  const [nivel, setNivel] = useState("2b");
  const [validando, setValidando] = useState(false);
  const [resultado, setResultado] = useState<ValidacionPdfa | null>(null);
  const entrada = useRef<HTMLInputElement>(null);

  async function validar(archivo: File) {
    setValidando(true);
    try {
      const datos = new FormData();
      datos.append("archivo", archivo);
      datos.append("nivel", nivel);
      setResultado(await apiSubir<ValidacionPdfa>(ruta, datos));
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setValidando(false);
      if (entrada.current) entrada.current.value = "";
    }
  }

  return (
    <div className="rounded-xl border border-line bg-surface p-4 shadow-xs">
      <span className="flex items-center gap-2 font-semibold text-titulo [&_svg]:size-5 [&_svg]:text-marca"><FileCheck2 />Validar un PDF/A</span>
      <p className="mt-1 max-w-3xl text-[12.5px] text-texto-3">Compruebe si un PDF cumple la norma PDF/A (ISO 19005), por ejemplo el que entregó un proveedor. El validador solo aprueba lo que reconoce como conforme. El archivo no se guarda.</p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <Campo etiqueta="Nivel" className="w-40">
          <Selector value={nivel} onChange={(e) => setNivel(e.target.value)}>
            <option value="1b">PDF/A-1b</option>
            <option value="2b">PDF/A-2b</option>
            <option value="3b">PDF/A-3b</option>
          </Selector>
        </Campo>
        <input ref={entrada} type="file" accept=".pdf,application/pdf" hidden onChange={(e) => e.target.files?.[0] && validar(e.target.files[0])} />
        <Boton icono={<FileCheck2 />} cargando={validando} onClick={() => entrada.current?.click()}>Elegir el PDF y validar</Boton>
      </div>
      {resultado && (
        <div className="mt-3 rounded-lg border border-line p-3">
          <div className="flex flex-wrap items-center gap-2 text-[13px]">
            <span className="font-semibold text-titulo">{resultado.archivo}</span>
            {resultado.veredicto === "conforme" ? <Insignia tono="ok" punto>Cumple {resultado.nivel}</Insignia> : resultado.veredicto === "no_conforme" ? <Insignia tono="critico" punto>No cumple {resultado.nivel}</Insignia> : <Insignia tono="aviso" punto>No se pudo verificar todo</Insignia>}
            <span className="text-[12px] text-texto-3">{numero(Math.max(1, Math.round(resultado.bytes / 1024)))} KB · {resultado.validado_con}</span>
          </div>
          {!!resultado.hallazgos.length && (
            <ul className="mt-2 flex flex-col gap-1 text-[12.5px]">
              {resultado.hallazgos.map((h, i) => (
                <li key={i} className={h.tipo === "incumple" ? "text-critico" : "text-aviso"}>
                  <span className="font-semibold">{h.explicacion || h.area || "Regla de la norma"}</span>{h.explicacion && h.area ? ` · ${h.area}` : ""}
                  <span className="block text-[11.5px] text-texto-3"><Codigo className="text-[11px]">{h.regla}</Codigo> {h.mensaje}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
