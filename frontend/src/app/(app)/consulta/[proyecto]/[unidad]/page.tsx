"use client";

import { ChevronLeft, ChevronRight, ExternalLink, Lock } from "lucide-react";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useAvisos } from "@/components/ui/avisos";
import { Boton, CajaError, Cargando, Datos, EncabezadoPagina, Insignia, Nota, Tabla, Tarjeta } from "@/components/ui/basicos";
import { Entrada } from "@/components/ui/campos";
import { abrirArchivo, api, urlLocal } from "@/lib/api";
import { fecha, fechaHora } from "@/lib/formato";
import type { FichaConsulta } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

const ACCESO: Record<string, string> = { publica: "Pública", clasificada: "Clasificada (Ley 1712 de 2014)", reservada: "Reservada (Ley 1712 de 2014)" };
const DESCRIPCION: [string, string][] = [
  ["codigo_referencia", "3.1.1 Código de referencia"], ["titulo", "3.1.2 Título"], ["volumen", "3.1.5 Volumen y soporte"], ["productor", "3.2.1 Productor"],
  ["historia_archivistica", "3.2.3 Historia archivística"], ["alcance", "3.3.1 Alcance y contenido"], ["valoracion", "3.3.2 Valoración"], ["organizacion", "3.3.4 Organización"],
  ["acceso", "3.4.1 Condiciones de acceso"], ["notas", "3.6.1 Notas"], ["nota_archivero", "3.7.1 Nota del archivero"],
];

/** Ficha de consulta: todo lo validado del expediente y sus documentos, en un solo lugar. Solo lectura. */
export default function FichaDeConsulta() {
  const { proyecto, unidad } = useParams<{ proyecto: string; unidad: string }>();
  const pedida = Number(useSearchParams().get("pagina") || 1);
  const base = `/consulta/proyectos/${proyecto}/unidades/${unidad}`;
  const f = useDatos(() => api<FichaConsulta>(base), [base]);
  const [pagina, setPagina] = useState(pedida);

  if (f.error) return <CajaError mensaje={f.error} reintentar={() => void f.recargar()} />;
  const d = f.datos;
  if (!d) return <Cargando />;
  const u = d.unidad;
  const c = d.clasificacion;
  return (
    <div className="flex flex-col gap-5">
      <EncabezadoPagina volver={{ href: "/consulta", texto: "Consulta" }}
        titulo={<span className="flex flex-wrap items-center gap-3">{u.identificador}{d.reservada && <Insignia tono={d.contenido_visible ? "aviso" : "critico"}><Lock className="mr-1 inline size-3" />{ACCESO[c?.acceso ?? "publica"]}</Insignia>}</span>}
        descripcion={`${d.descripcion?.titulo || u.nombre} · ${d.proyecto.codigo} · ${d.proyecto.entidad}`} />
      {!d.contenido_visible && <Nota tono="critico">Este expediente tiene acceso {c?.acceso === "reservada" ? "reservado" : "clasificado"} según la TRD. Su rol puede ver los metadatos, pero no los documentos ni su contenido.</Nota>}
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Tarjeta className="p-4">
            <p className="mb-2 font-semibold text-titulo">Inventario (FUID)</p>
            <Datos filas={[
              ["Nombre", u.nombre], ["Orden", u.numero_orden ?? "—"], ["Fechas extremas", `${fecha(u.fecha_inicial)} – ${fecha(u.fecha_final)}`], ["Folios", u.folios ?? "—"],
              ["Caja · carpeta", `${u.caja ?? "—"} · ${u.carpeta ?? "—"}${u.tomo ? ` · tomo ${u.tomo}` : ""}`], ["Soporte", u.soporte], ["Notas", u.notas || "—"],
            ]} />
          </Tarjeta>
          <Tarjeta className="p-4">
            <p className="mb-2 font-semibold text-titulo">Clasificación y ciclo vital</p>
            {!c ? <p className="text-[13px] text-texto-3">Sin clasificación confirmada.</p> : (
              <Datos filas={[
                ["Dependencia", c.dependencia], ["Serie", c.serie], ["Clasificada en", `${c.codigo} ${c.nombre} (${c.nivel})`], ["Instrumento", c.instrumento],
                ["Acceso", ACCESO[c.acceso] ?? c.acceso], ["Disposición final", c.disposicion ?? "—"], ["Está en", u.disposicion_aplicada === "eliminada" ? "Eliminada (queda la evidencia)" : u.fase_nombre],
                ["Retención", c.calendario?.nota ?? "—"],
              ]} />
            )}
            {d.historial.length > 0 && (
              <ul className="mt-3 flex flex-col gap-1 border-t border-line pt-2 text-[12.5px]">
                {d.historial.map((m, i) => <li key={i}><span className="text-texto-3">{fechaHora(m.fecha)}</span> · {m.desde ? `${m.desde} → ` : ""}{m.hasta}{m.motivo ? ` · ${m.motivo}` : ""}</li>)}
              </ul>
            )}
          </Tarjeta>
          {d.descripcion && (
            <Tarjeta className="p-4">
              <p className="mb-2 font-semibold text-titulo">Descripción ISAD(G) aprobada</p>
              <Datos columnas={1} filas={DESCRIPCION.filter(([k]) => d.descripcion?.[k]).map(([k, e]) => [e, <span key={k} className="whitespace-pre-wrap">{d.descripcion![k]}</span>])} />
            </Tarjeta>
          )}
          {d.contenido_visible && (
            <Tarjeta className="p-4">
              <p className="mb-2 font-semibold text-titulo">Hoja de control {d.hoja_control.verificada ? `verificada · ${d.hoja_control.total_folios ?? "—"} folios` : ""}</p>
              {!d.hoja_control.verificada ? <p className="text-[13px] text-texto-3">No tiene hoja de control verificada.</p> : (
                <Tabla className="rounded-xl border border-line">
                  <thead><tr><th>N.º</th><th>Fecha</th><th>Documento</th><th>Folios</th></tr></thead>
                  <tbody>
                    {d.hoja_control.tramites.map((t) => (
                      <tr key={t.orden} className={t.pagina_desde ? "cursor-pointer hover:bg-marca-suave" : ""} onClick={() => t.pagina_desde && setPagina(t.pagina_desde)}>
                        <td>{t.orden}</td><td className="whitespace-nowrap">{t.fecha ?? "S. F."}</td>
                        <td><b>{t.tipo_documental}</b>{t.detalle && <span className="block text-[12px] text-texto-2">{t.detalle}</span>}{t.no_radicado && <span className="block text-[11.5px] text-texto-3">Radicado {t.no_radicado}</span>}</td>
                        <td className="whitespace-nowrap">{t.folio_desde}–{t.folio_hasta}</td>
                      </tr>
                    ))}
                  </tbody>
                </Tabla>
              )}
            </Tarjeta>
          )}
        </div>
        <div className="min-w-0 xl:sticky xl:top-4">
          {d.contenido_visible ? <Visor base={base} total={d.paginas.length} pagina={Math.min(Math.max(1, pagina), Math.max(1, d.paginas.length))} alCambiar={setPagina} archivo={d.paginas[pagina - 1]?.archivo} />
            : <Tarjeta className="grid min-h-60 place-items-center p-6 text-center text-[13px] text-texto-3"><Lock className="mb-2 size-6" />Documentos no disponibles para su rol.</Tarjeta>}
        </div>
      </div>
    </div>
  );
}

function Visor({ base, total, pagina, alCambiar, archivo }: { base: string; total: number; pagina: number; alCambiar: (n: number) => void; archivo?: string }) {
  const avisos = useAvisos();
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!total) return;
    let vivo = true;
    let actual: string | null = null;
    setUrl(null);
    setError(null);
    urlLocal(`${base}/paginas/${pagina}/imagen`).then((x) => (vivo ? ((actual = x), setUrl(x)) : URL.revokeObjectURL(x))).catch((e) => vivo && setError(e.message));
    return () => {
      vivo = false;
      if (actual) URL.revokeObjectURL(actual);
    };
  }, [base, pagina, total]);
  if (!total) return <Tarjeta className="p-6 text-center text-[13px] text-texto-3">Este expediente no está digitalizado.</Tarjeta>;
  return (
    <Tarjeta className="flex flex-col overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <Boton tamano="sm" variante="fantasma" icono={<ChevronLeft />} disabled={pagina <= 1} onClick={() => alCambiar(pagina - 1)} aria-label="Página anterior" />
        <span className="text-[13px]">Página</span>
        <Entrada key={pagina} className="w-16 text-center" type="number" min={1} max={total} defaultValue={pagina} aria-label="Número de página"
          onKeyDown={(e) => e.key === "Enter" && alCambiar(Math.min(total, Math.max(1, Number((e.target as HTMLInputElement).value) || 1)))} />
        <span className="text-[13px] text-texto-3">de {total}</span>
        <Boton tamano="sm" variante="fantasma" icono={<ChevronRight />} disabled={pagina >= total} onClick={() => alCambiar(pagina + 1)} aria-label="Página siguiente" />
        <Boton className="ml-auto" tamano="sm" variante="fantasma" icono={<ExternalLink />} onClick={() => abrirArchivo(`${base}/paginas/${pagina}/original`).catch((e) => avisos.error(e.message))}>Original</Boton>
      </div>
      <div className="grid min-h-[60vh] place-items-center bg-surface-muted p-3">
        {error ? <p className="text-[13px] text-critico">{error}</p> : url ? <img src={url} alt={`Página ${pagina} del expediente`} className="max-h-[78vh] w-auto max-w-full rounded-md bg-white shadow-sm" /> : <Cargando texto="Abriendo la página…" />}
      </div>
      {archivo && <p className="border-t border-line px-3 py-1.5 text-[11.5px] text-texto-3">Archivo «{archivo}»</p>}
    </Tarjeta>
  );
}
