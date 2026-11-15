"use client";

import { Ban, CheckCircle2, ChevronLeft, ChevronRight, Download, Lock, Save } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ModalMotivo } from "@/components/ui/acciones";
import { useAvisos } from "@/components/ui/avisos";
import { Boton, CajaError, Cargando, EncabezadoPagina, Insignia, Nota, Tarjeta } from "@/components/ui/basicos";
import { Area, Campo, Casilla, Entrada } from "@/components/ui/campos";
import { api, urlLocal } from "@/lib/api";
import { descargarArchivo } from "@/lib/descargas";
import { fechaHora, numero } from "@/lib/formato";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { DetalleInspeccion, ItemMuestra } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

import { ESTADO_INSPECCION, PLURAL, SEVERIDAD } from "../../inspeccion";

/** Una inspección de calidad por lote: la muestra a la izquierda, el visor y los defectos del elemento elegido a la derecha. */
export default function PaginaInspeccion() {
  const { id, inspeccion } = useParams<{ id: string; inspeccion: string }>();
  const { puede } = useSesion();
  const avisos = useAvisos();
  const base = `/proyectos/${id}/inspeccion/inspecciones/${inspeccion}`;
  const datos = useDatos(() => api<DetalleInspeccion>(base), [base]);
  const [elegido, setElegido] = useState<string | null>(null);
  const [cerrando, setCerrando] = useState(false);
  const [observaciones, setObservaciones] = useState("");
  const [anular, setAnular] = useState(false);

  if (datos.error) return <CajaError mensaje={datos.error} />;
  if (!datos.datos) return <Cargando />;
  const d = datos.datos;
  const item = d.items.find((x) => x.id === elegido) ?? d.items.find((x) => x.estado === "pendiente") ?? d.items[0];
  const abierta = d.estado === "abierta";
  const inspecciona = puede(PERMISOS.calidad) && abierta;
  const estado = ESTADO_INSPECCION[d.estado];

  async function cerrar() {
    setCerrando(true);
    try {
      const r = await api<DetalleInspeccion>(`${base}/cerrar`, { metodo: "POST", cuerpo: { observaciones } });
      avisos.exito(r.estado === "aceptada" ? "Lote aceptado." : `Lote rechazado: ${r.razones.join("; ")}.`);
      datos.recargar();
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setCerrando(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <EncabezadoPagina
        volver={{ href: `/proyectos/${id}`, texto: "Proyecto" }}
        titulo={`Inspección n.º ${d.numero} · lote ${d.lote || "sin lote"}`}
        descripcion={`${numero(d.muestra)} de ${numero(d.tamano)} ${d.plan.unidad === "imagenes" ? "imágenes" : "expedientes"} · semilla ${d.semilla}${d.reinspeccion_de ? " · reinspección" : ""} · abrió ${d.creado_por ?? "—"} el ${fechaHora(d.creado_en)}`}
        acciones={<div className="flex items-center gap-2">
          <Insignia tono={estado.tono} punto>{estado.etiqueta}</Insignia>
          {!abierta && d.estado !== "anulada" && <Boton icono={<Download />} onClick={() => descargarArchivo(`${base}/acta`, `Acta_inspeccion_n${d.numero}.xlsx`).catch((e) => avisos.error(e.message))}>Acta</Boton>}
          {abierta && puede(PERMISOS.proyectos) && <Boton variante="fantasma" icono={<Ban />} onClick={() => setAnular(true)}>Anular</Boton>}
        </div>}
      />
      <Tarjeta className="p-4">
        <div className="grid gap-3 sm:grid-cols-4">
          {(["critico", "mayor", "menor"] as const).map((s) => {
            const pasa = d.conteo[s] > d.plan.aceptacion[s];
            return (
              <div key={s} className={`rounded-lg border px-3 py-2 ${pasa ? "border-critico/50 bg-critico-suave" : "border-line"}`}>
                <p className="text-[12px] text-texto-3">Defectos {PLURAL[s]}</p>
                <p className="tabular text-lg font-bold text-titulo">{d.conteo[s]} <span className="text-[12px] font-normal text-texto-3">de {d.plan.aceptacion[s]} aceptados</span></p>
              </div>
            );
          })}
          <div className="rounded-lg border border-line px-3 py-2">
            <p className="text-[12px] text-texto-3">Limitaciones del original</p>
            <p className="tabular text-lg font-bold text-titulo">{d.conteo.limitacion} <span className="text-[12px] font-normal text-texto-3">no cuentan</span></p>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-[13px]">
          <span>Revisados: <b className="tabular">{d.revisados} de {d.muestra}</b></span>
          {abierta && <span>· Si se cerrara ahora: <Insignia tono={d.resultado_previsto === "aceptada" ? "ok" : "critico"}>{d.resultado_previsto === "aceptada" ? "se acepta" : "se rechaza"}</Insignia></span>}
          {d.razones.length > 0 && <span className="text-critico">{d.razones.join("; ")}</span>}
          {d.cerrada_en && <span className="text-texto-3">· {d.estado === "anulada" ? "anuló" : "cerró"} {d.cerrada_por} el {fechaHora(d.cerrada_en)}</span>}
        </div>
        {d.observaciones && <p className="mt-2 text-[12.5px] text-texto-2">{d.estado === "anulada" ? "Motivo" : "Observaciones"}: {d.observaciones}</p>}
        {inspecciona && d.revisados === d.muestra && (
          <div className="mt-3 flex flex-wrap items-end gap-3 border-t border-line pt-3">
            <Campo etiqueta="Observaciones del cierre" className="min-w-72 flex-1"><Entrada value={observaciones} onChange={(e) => setObservaciones(e.target.value)} /></Campo>
            <Boton variante="primario" icono={<Lock />} cargando={cerrando} onClick={cerrar}>Cerrar la inspección</Boton>
          </div>
        )}
      </Tarjeta>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <Tarjeta className="flex flex-col divide-y divide-line">
          {d.items.map((x) => (
            <button key={x.id} onClick={() => setElegido(x.id)} className={`flex flex-wrap items-center gap-2 px-4 py-2.5 text-left text-[13px] hover:bg-canvas ${item?.id === x.id ? "bg-marca-suave/40" : ""}`}>
              <span className="tabular w-7 font-semibold text-titulo">{x.orden}</span>
              <span className="font-semibold">{x.identificador}</span>
              {x.pagina != null && <span className="text-texto-3">p. {x.pagina}</span>}
              <span className="truncate text-texto-3">{x.nombre}</span>
              <span className="ml-auto flex flex-wrap gap-1">
                {x.estado === "pendiente" ? <Insignia tono="neutro">Por revisar</Insignia> : !x.defectos.length ? <Insignia tono="ok">Sin defectos</Insignia>
                  : x.defectos.map((f, i) => <Insignia key={i} tono={SEVERIDAD[f.severidad].tono}>{f.nombre}</Insignia>)}
              </span>
            </button>
          ))}
        </Tarjeta>
        {item && <Elemento key={item.id} proyecto={id} base={base} item={item} catalogo={d.plan.defectos} editable={inspecciona} alGuardar={(siguiente) => (datos.recargar(), setElegido(siguiente))} siguiente={d.items.find((x) => x.orden > item.orden && x.estado === "pendiente")?.id ?? null} />}
      </div>
      <ModalMotivo abierto={anular} titulo="Anular la inspección" descripcion="La muestra se descarta. Queda en la auditoría con el motivo." boton="Anular" peligro
        alCerrar={() => setAnular(false)} alConfirmar={async (motivo) => { await api(`${base}/anular`, { metodo: "POST", cuerpo: { motivo } }); setAnular(false); datos.recargar(); }} />
      <Nota tono="info">Quien cargó los archivos de un expediente no puede inspeccionarlo. Al cerrar, ARCA cuenta los defectos y decide con el plan: nadie acepta ni rechaza a mano.</Nota>
    </div>
  );
}

function Elemento({ proyecto, base, item, catalogo, editable, alGuardar, siguiente }: {
  proyecto: string; base: string; item: ItemMuestra; catalogo: DetalleInspeccion["plan"]["defectos"]; editable: boolean;
  alGuardar: (siguiente: string | null) => void; siguiente: string | null;
}) {
  const avisos = useAvisos();
  const [pagina, setPagina] = useState(item.pagina ?? 1);
  const [url, setUrl] = useState<string | null>(null);
  const [marcados, setMarcados] = useState<Record<string, string>>(Object.fromEntries(item.defectos.map((d) => [d.codigo, d.nota])));
  const [guardando, setGuardando] = useState(false);
  useEffect(() => {
    if (!item.paginas) return;
    let vivo = true;
    let actual: string | null = null;
    setUrl(null);
    urlLocal(`/proyectos/${proyecto}/hojas-control/unidades/${item.unidad_id}/paginas/${pagina}/imagen`).then((u) => (vivo ? (actual = u, setUrl(u)) : URL.revokeObjectURL(u))).catch(() => undefined);
    return () => {
      vivo = false;
      if (actual) URL.revokeObjectURL(actual);
    };
  }, [proyecto, item.unidad_id, item.paginas, pagina]);

  async function guardar() {
    setGuardando(true);
    try {
      await api(`${base}/items/${item.id}`, { metodo: "PUT", cuerpo: { defectos: Object.entries(marcados).map(([codigo, nota]) => ({ codigo, nota, pagina: item.pagina ?? pagina })) } });
      avisos.exito(`Elemento ${item.orden} revisado.`);
      alGuardar(siguiente);
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setGuardando(false);
    }
  }

  const porImagen = item.pagina != null;
  return (
    <Tarjeta className="flex flex-col overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2 text-[13px]">
        <span className="font-semibold text-titulo">{item.orden}. {item.identificador}</span>
        <span className="text-texto-3">caja {item.caja ?? "—"}</span>
        {!porImagen && <>
          <Boton tamano="sm" variante="fantasma" icono={<ChevronLeft />} disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)} aria-label="Página anterior" />
          <span>Página {pagina} de {item.paginas}</span>
          <Boton tamano="sm" variante="fantasma" icono={<ChevronRight />} disabled={pagina >= item.paginas} onClick={() => setPagina(pagina + 1)} aria-label="Página siguiente" />
        </>}
        {porImagen && <span>· imagen de la página {item.pagina} de {item.paginas}</span>}
      </div>
      <div className="flex min-h-80 items-center justify-center bg-canvas p-3">
        {url ? <img src={url} alt={`Página ${pagina} de ${item.identificador}`} className="max-h-[60vh] w-auto shadow-sm" /> : <Cargando />}
      </div>
      <div className="flex flex-col gap-2 border-t border-line p-3">
        <p className="text-[12.5px] font-semibold text-texto-2">Defectos {porImagen ? "de esta imagen" : "del expediente"}</p>
        <div className="grid gap-1.5 sm:grid-cols-2">
          {catalogo.map((c) => (
            <div key={c.codigo} className="flex flex-col gap-1">
              <Casilla etiqueta={<span>{c.nombre} <Insignia tono={SEVERIDAD[c.severidad].tono}>{SEVERIDAD[c.severidad].etiqueta}</Insignia></span>} disabled={!editable} checked={c.codigo in marcados}
                onChange={(e) => setMarcados((m) => { const n = { ...m }; if (e.target.checked) n[c.codigo] = ""; else delete n[c.codigo]; return n; })} />
              {c.codigo in marcados && <Area className="min-h-10 text-[12.5px]" disabled={!editable} placeholder="Nota (opcional)" aria-label={`Nota de ${c.nombre}`} value={marcados[c.codigo]} onChange={(e) => setMarcados((m) => ({ ...m, [c.codigo]: e.target.value }))} />}
            </div>
          ))}
        </div>
        {item.revisado_por && <p className="text-[11.5px] text-texto-3">Revisó {item.revisado_por} el {fechaHora(item.revisado_en)}</p>}
        {editable && (
          <div className="flex gap-2">
            <Boton variante="primario" icono={Object.keys(marcados).length ? <Save /> : <CheckCircle2 />} cargando={guardando} onClick={guardar}>
              {Object.keys(marcados).length ? `Guardar ${Object.keys(marcados).length} defecto(s)` : "Sin defectos"}{siguiente ? " y seguir" : ""}
            </Boton>
          </div>
        )}
      </div>
    </Tarjeta>
  );
}
