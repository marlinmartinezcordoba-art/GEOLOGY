"use client";

import { AlertTriangle, CheckCheck, CheckCircle2, FileText, ScanText, ChevronLeft, ChevronRight, Download, ExternalLink, Merge, MessageSquareWarning, Plus, RotateCcw, Scissors, Send, ShieldCheck, Trash2, Undo2 } from "lucide-react";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ModalMotivo } from "@/components/ui/acciones";
import { useAvisos } from "@/components/ui/avisos";
import { Boton, CajaError, Cargando, EncabezadoPagina, Insignia, Modal, Nota, Tarjeta } from "@/components/ui/basicos";
import { Area, Campo, Entrada, Selector } from "@/components/ui/campos";
import { abrirArchivo, api, ErrorApi, urlLocal } from "@/lib/api";
import { descargarArchivo } from "@/lib/descargas";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { Tono } from "@/lib/tonos";
import type { DetalleHoja, OrigenDato, TextoOcr, TramiteHoja } from "@/lib/tipos";

import { NOMBRE_ESTADO_HOJA, TONO_ESTADO_HOJA } from "../../hojas";

const FUENTE: Record<string, { etiqueta: string; tono: Tono }> = {
  persona: { etiqueta: "Persona", tono: "marca" }, calculado: { etiqueta: "Calculado", tono: "motor" }, trd: { etiqueta: "TRD", tono: "info" },
  importado: { etiqueta: "Importado", tono: "naranja" }, fuid: { etiqueta: "FUID", tono: "neutro" }, clasificacion: { etiqueta: "Clasificación", tono: "info" },
  proyecto: { etiqueta: "Proyecto", tono: "neutro" }, ocr: { etiqueta: "OCR · por confirmar", tono: "ia" }, digitalizacion: { etiqueta: "Digitalización", tono: "motor" }, falta: { etiqueta: "Falta", tono: "critico" },
};

function Origen({ o }: { o?: OrigenDato | null }) {
  if (!o) return <span className="text-[11px] text-texto-3">sin origen registrado</span>;
  const f = FUENTE[o.fuente] ?? { etiqueta: o.fuente, tono: "neutro" as Tono };
  return (
    <span className="inline-flex flex-wrap items-center gap-1 text-[11px] text-texto-3" title={o.detalle}>
      <Insignia tono={f.tono}>{f.etiqueta}</Insignia>
      <span>{o.detalle}</span>
    </span>
  );
}

/** Hoja de control de un expediente: trámites con el origen de cada dato a la izquierda, documentos a la derecha. */
export default function HojaDeControl() {
  const { id, unidad } = useParams<{ id: string; unidad: string }>();
  const { puede, usuario } = useSesion();
  const avisos = useAvisos();
  const base = `/proyectos/${id}/hojas-control/unidades/${unidad}`;
  const [d, setD] = useState<DetalleHoja | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pagina, setPagina] = useState(1);
  const [elegido, setElegido] = useState<string | null>(null);
  const [trabajando, setTrabajando] = useState<string | null>(null);
  const [motivo, setMotivo] = useState<"devolver" | "reabrir" | null>(null);
  const [ipf, setIpf] = useState("1");
  const [ocr, setOcr] = useState<TextoOcr[]>([]);
  const [leyendo, setLeyendo] = useState<string | null>(null);
  const [reemplazar, setReemplazar] = useState(false);
  const cargarOcr = useCallback(() => api<TextoOcr[]>(`/proyectos/${id}/ocr/unidades/${unidad}`).then(setOcr).catch(() => setOcr([])), [id, unidad]);
  useEffect(() => {
    void cargarOcr();
  }, [cargarOcr]);

  async function leerYProponer(conReemplazo = false) {
    setLeyendo("Leyendo con OCR…");
    try {
      for (let vuelta = 0; vuelta < 200; vuelta++) {
        const r = await api<{ procesadas: number; pendientes: number; paginas: number }>(`/proyectos/${id}/ocr/unidades/${unidad}/leer`, { metodo: "POST", cuerpo: { limite: 10 } });
        setLeyendo(`Leyendo con OCR: ${r.paginas - r.pendientes} de ${r.paginas} páginas…`);
        if (!r.pendientes || !r.procesadas) break;
      }
      await cargarOcr();
      setLeyendo("Proponiendo documentos…");
      setD(await post("/proponer-ocr", { reemplazar: conReemplazo }));
      avisos.exito("Propuesta lista. Revise cada trámite contra el documento y confirme o corrija.");
    } catch (e) {
      if (e instanceof ErrorApi && e.status === 409) setReemplazar(true);
      else avisos.error((e as Error).message);
    } finally {
      setLeyendo(null);
    }
  }

  const cargar = useCallback(() => api<DetalleHoja>(base).then(setD).catch((e) => setError(e.message)), [base]);
  useEffect(() => {
    void cargar();
  }, [cargar]);

  async function hacer(clave: string, fn: () => Promise<DetalleHoja>, mensaje?: string) {
    setTrabajando(clave);
    try {
      setD(await fn());
      if (mensaje) avisos.exito(mensaje);
    } catch (e) {
      avisos.error((e as Error).message);
    } finally {
      setTrabajando(null);
    }
  }
  const post = (ruta: string, cuerpo?: unknown) => api<DetalleHoja>(`${base}${ruta}`, { metodo: "POST", cuerpo });

  if (error) return <CajaError mensaje={error} reintentar={() => (setError(null), void cargar())} />;
  if (!d) return <Cargando />;
  const h = d.hoja;
  const editable = !!h && (h.estado === "borrador" || h.estado === "devuelta") && puede(PERMISOS.hojaControl);
  const verifica = !!h && h.estado === "en_revision" && puede(PERMISOS.verificarHoja) && usuario.id !== h.enviada_por && usuario.id !== h.creado_por;
  const seleccionado = d.tramites.find((t) => t.id === elegido) ?? d.tramites.find((t) => t.pagina_desde != null && pagina >= t.pagina_desde && pagina <= (t.pagina_hasta ?? 0)) ?? null;
  const elegir = (t: TramiteHoja) => (setElegido(t.id), t.pagina_desde && setPagina(t.pagina_desde));
  const v = d.validacion;
  const conforme = d.tramites.length > 0 && d.tramites.every((t) => t.revision === "conforme");

  return (
    <div className="flex flex-col gap-5">
      <EncabezadoPagina
        volver={{ href: `/proyectos/${id}`, texto: "Proyecto" }}
        titulo={<span className="flex flex-wrap items-center gap-3">Hoja de control · {d.unidad.identificador}{h && <Insignia tono={TONO_ESTADO_HOJA[h.estado]} punto>{NOMBRE_ESTADO_HOJA[h.estado]}</Insignia>}</span>}
        descripcion={`${d.unidad.nombre} · caja ${d.unidad.caja ?? "—"} · carpeta ${d.unidad.carpeta ?? "—"}`}
        acciones={h && (
          <div className="flex flex-wrap gap-2">
            {editable && d.paginas.length > 0 && <Boton icono={<ScanText />} cargando={!!leyendo} onClick={() => leerYProponer()}>{leyendo ?? "Leer con OCR y proponer"}</Boton>}
            {editable && <Boton variante="primario" icono={<Send />} cargando={trabajando === "enviar"} disabled={!!v?.errores.length} onClick={() => hacer("enviar", () => post("/enviar"), "Enviada a verificación.")}>Enviar a verificación</Boton>}
            {verifica && <Boton icono={<Undo2 />} onClick={() => setMotivo("devolver")}>Devolver</Boton>}
            {verifica && <Boton variante="primario" icono={<ShieldCheck />} cargando={trabajando === "verificar"} disabled={!conforme} onClick={() => hacer("verificar", () => post("/verificar"), "Hoja verificada.")}>Verificar hoja</Boton>}
            {h.estado === "verificada" && puede(PERMISOS.verificarHoja) && <Boton icono={<RotateCcw />} onClick={() => setMotivo("reabrir")}>Reabrir</Boton>}
            {h.estado === "verificada" && puede(PERMISOS.expedir) && (
              <Boton variante="primario" icono={<Download />} cargando={trabajando === "expedir"} onClick={async () => {
                setTrabajando("expedir");
                try {
                  const e = await api<{ expedicion_id: string; nombre_archivo: string }>(`${base}/expedir`, { metodo: "POST" });
                  await descargarArchivo(`/proyectos/${id}/entregables/${e.expedicion_id}/archivo`, e.nombre_archivo);
                  avisos.exito("Hoja expedida en el formato de la entidad. Queda también en Entregables.");
                } catch (err) {
                  avisos.error((err as Error).message);
                } finally {
                  setTrabajando(null);
                }
              }}>Expedir hoja de control</Boton>
            )}
          </div>
        )}
      />

      {!h ? (
        <Tarjeta className="p-5">
          <p className="font-semibold text-titulo">Este expediente todavía no tiene hoja de control</p>
          <p className="mt-1 text-[13px] text-texto-2">
            {d.paginas.length ? `Tiene ${d.paginas.length} imágenes digitalizadas. ARCA arranca con un solo trámite que las cubre todas; usted marca dónde empieza cada documento.` : "No está digitalizado: los trámites y los folios se escriben a mano."}
          </p>
          {puede(PERMISOS.hojaControl) && (
            <div className="mt-3 flex flex-wrap items-end gap-3">
              {d.paginas.length > 0 && (
                <Campo etiqueta="Imágenes por folio">
                  <Selector value={ipf} onChange={(e) => setIpf(e.target.value)}><option value="1">1 · cada imagen es un folio</option><option value="2">2 · recto y verso</option></Selector>
                </Campo>
              )}
              <Boton variante="primario" icono={<Plus />} cargando={trabajando === "crear"} onClick={() => hacer("crear", () => post("", { imagenes_por_folio: Number(ipf) }), "Hoja creada.")}>Elaborar hoja de control</Boton>
            </div>
          )}
        </Tarjeta>
      ) : (
        <>
          {h.novedad && <Nota tono={h.estado === "devuelta" ? "critico" : "info"}>{h.estado === "devuelta" ? "Devuelta: " : ""}{h.novedad}</Nota>}
          {h.estado === "en_revision" && !verifica && <Nota tono="aviso">La hoja está en verificación. La verifica otra persona con el permiso de verificar hojas (quien la elabora no la verifica).</Nota>}
          {verifica && <Nota tono="info">Revise cada trámite con el documento a la vista y márquelo conforme o con observación. Cuando todos estén conformes, verifique la hoja; si alguno tiene observación, devuélvala.</Nota>}
        </>
      )}

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Tarjeta className="p-4">
            <p className="mb-2 font-semibold text-titulo">Datos del expediente y de dónde salen</p>
            <dl className="divide-y divide-line">
              {d.metadatos.map((m) => (
                <div key={m.campo} className="grid gap-1 py-2 sm:grid-cols-[150px_minmax(0,1fr)]">
                  <dt className="text-[12.5px] font-medium text-texto-3">{m.etiqueta}</dt>
                  <dd className="min-w-0">
                    <p className="text-[13.5px] text-titulo">{m.valor ?? <span className="text-texto-3">—</span>}</p>
                    <Origen o={{ fuente: m.fuente, detalle: m.detalle }} />
                    {m.alerta && <p className="mt-0.5 flex items-center gap-1 text-[12px] text-aviso"><AlertTriangle className="size-3.5" />{m.alerta}</p>}
                  </dd>
                </div>
              ))}
            </dl>
            {h?.importacion?.archivo && <p className="mt-2 text-[11.5px] text-texto-3">Importada de «{h.importacion.archivo}», pestaña «{h.importacion.pestana}»{h.importacion.sha256 ? ` · SHA-256 ${h.importacion.sha256.slice(0, 16)}…` : ""}</p>}
          </Tarjeta>

          {v && (v.errores.length > 0 || v.avisos.length > 0 || v.correcciones.length > 0) && (
            <Tarjeta className="flex flex-col gap-2 p-4">
              {v.errores.length > 0 && (
                <Nota tono="critico">
                  <p className="font-semibold">Errores ({v.errores.length}) · impiden enviar la hoja</p>
                  <ul className="mt-1 list-disc pl-5 text-[12.5px]">{v.errores.map((e, i) => <li key={i}><button className="text-left hover:underline" onClick={() => { const t = d.tramites.find((x) => x.id === e.tramite_id); if (t) elegir(t); }}>{e.orden ? `Trámite ${e.orden}: ` : ""}{e.mensaje}</button></li>)}</ul>
                </Nota>
              )}
              {v.avisos.length > 0 && <Nota tono="aviso"><p className="font-semibold">Avisos</p><ul className="mt-1 list-disc pl-5 text-[12.5px]">{v.avisos.map((a) => <li key={a}>{a}</li>)}</ul></Nota>}
              {v.correcciones.length > 0 && <Nota tono="info"><ul className="list-disc pl-5 text-[12.5px]">{v.correcciones.map((a) => <li key={a}>{a}</li>)}</ul></Nota>}
            </Tarjeta>
          )}

          {h && (
            <Tarjeta className="p-4">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <p className="font-semibold text-titulo">Trámites ({d.tramites.length})</p>
                <span className="text-[12.5px] text-texto-3">· {v?.total_folios ?? 0} folios · fechas {v?.fecha_inicial ?? "S. F."} a {v?.fecha_final ?? "S. F."}</span>
                {editable && d.paginas.length > 0 && (
                  <Selector className="ml-auto w-auto" aria-label="Imágenes por folio" value={String(h.imagenes_por_folio)} onChange={(e) => hacer("ipf", () => api<DetalleHoja>(`${base}/imagenes-por-folio`, { metodo: "PUT", cuerpo: { valor: Number(e.target.value) } }))}>
                    <option value="1">1 imagen por folio</option><option value="2">2 imágenes por folio (recto y verso)</option>
                  </Selector>
                )}
                {editable && !d.paginas.length && <Boton className="ml-auto" tamano="sm" icono={<Plus />} onClick={() => hacer("agregar", () => post("/tramites"))}>Agregar trámite</Boton>}
              </div>
              <div className="flex flex-col gap-3">
                {d.tramites.map((t, i) => (
                  <TramiteFila key={t.id} t={t} ultimo={i === d.tramites.length - 1} activo={seleccionado?.id === t.id} editable={editable} verifica={verifica} tipos={d.tipos_documentales}
                    conPaginas={d.paginas.length > 0} errores={v?.errores.filter((e) => e.tramite_id === t.id).map((e) => e.mensaje) ?? []}
                    alElegir={() => elegir(t)}
                    alGuardar={(campo, valor) => hacer(`g-${t.id}`, () => api<DetalleHoja>(`${base}/tramites/${t.id}`, { metodo: "PATCH", cuerpo: { [campo]: valor } }))}
                    alUnir={() => hacer(`u-${t.id}`, () => post(`/tramites/${t.id}/unir`), "Trámites unidos.")}
                    alQuitar={() => hacer(`q-${t.id}`, () => api<DetalleHoja>(`${base}/tramites/${t.id}`, { metodo: "DELETE" }))}
                    alConfirmar={() => hacer(`c-${t.id}`, () => post(`/tramites/${t.id}/confirmar`), `Trámite ${t.orden} confirmado.`)}
                    alRevisar={(conforme, observacion) => hacer(`r-${t.id}`, () => post(`/tramites/${t.id}/revisar`, { conforme, observacion }))} />
                ))}
                {!d.tramites.length && <p className="text-[13px] text-texto-3">Sin trámites todavía.</p>}
              </div>
            </Tarjeta>
          )}
        </div>

        <div className="min-w-0 xl:sticky xl:top-4">
          <Visor base={base} total={d.paginas.length} pagina={pagina} alCambiar={(n) => (setPagina(n), setElegido(null))} info={d.paginas[pagina - 1]} tramite={seleccionado}
            texto={ocr[pagina - 1]}
            puedeDividir={editable && !!seleccionado && seleccionado.pagina_desde != null && pagina > seleccionado.pagina_desde && pagina <= (seleccionado.pagina_hasta ?? 0)}
            dividiendo={trabajando === "dividir"}
            alDividir={() => seleccionado && hacer("dividir", () => post(`/tramites/${seleccionado.id}/dividir`, { pagina }), `Nuevo documento desde la página ${pagina}.`)} />
        </div>
      </div>

      <Modal abierto={reemplazar} alCerrar={() => setReemplazar(false)} titulo="¿Reemplazar los trámites que ya trabajó?"
        descripcion="La hoja ya tiene trámites con datos. La propuesta del OCR los reemplaza todos; lo que usted escribió se pierde de la hoja (queda en la auditoría)."
        pie={<><Boton onClick={() => setReemplazar(false)}>Cancelar</Boton><Boton variante="peligro" onClick={() => (setReemplazar(false), void leerYProponer(true))}>Reemplazar con la propuesta</Boton></>}>
        <p className="text-[13px] text-texto-2">Si solo quiere ver lo que leyó el OCR, use «Texto OCR» en el visor: no cambia nada.</p>
      </Modal>
      <ModalMotivo
        abierto={motivo !== null}
        titulo={motivo === "devolver" ? "Devolver la hoja a quien la elaboró" : "Reabrir la hoja verificada"}
        descripcion={motivo === "devolver" ? "Las observaciones de cada trámite quedan a la vista de quien la corrige." : "Vuelve a elaboración. La verificación anterior queda en la auditoría."}
        boton={motivo === "devolver" ? "Devolver" : "Reabrir"}
        alCerrar={() => setMotivo(null)}
        alConfirmar={async (m) => {
          setD(await post(motivo === "devolver" ? "/devolver" : "/reabrir", { motivo: m }));
          avisos.exito(motivo === "devolver" ? "Hoja devuelta." : "Hoja reabierta.");
        }}
      />
    </div>
  );
}

const METADATOS = [["asunto", "Asunto"], ["remitente", "Remitente"], ["destinatario", "Destinatario"], ["firmantes", "Firmantes"], ["lugar", "Lugar"]] as const;

function TramiteFila({ t, ultimo, activo, editable, verifica, tipos, conPaginas, errores, alElegir, alGuardar, alUnir, alQuitar, alRevisar, alConfirmar }: {
  t: TramiteHoja; ultimo: boolean; activo: boolean; editable: boolean; verifica: boolean; tipos: string[]; conPaginas: boolean; errores: string[];
  alElegir: () => void; alGuardar: (campo: string, valor: string | number | null | Record<string, string>) => void; alUnir: () => void; alQuitar: () => void; alRevisar: (conforme: boolean, observacion: string) => void; alConfirmar: () => void;
}) {
  const propuesto = Object.values(t.origen).some((o) => o.fuente === "ocr");
  const [obs, setObs] = useState("");
  const [observando, setObservando] = useState(false);
  const listaId = `tipos-${t.id}`;
  const campo = (nombre: keyof TramiteHoja, etiqueta: string, props: { tipo?: string; lista?: boolean; area?: boolean; valor?: string } = {}) => {
    const actual = props.valor ?? String(t[nombre] ?? "");
    const guardar = (nuevo: string) => nuevo !== actual && alGuardar(nombre, props.tipo === "number" ? (nuevo === "" ? null : Number(nuevo)) : nuevo);
    return (
      <Campo etiqueta={etiqueta}>
        {props.area ? (
          <Area key={actual} defaultValue={actual} disabled={!editable} onBlur={(e) => guardar(e.target.value)} className="min-h-14" />
        ) : (
          <Entrada key={actual} type={props.tipo ?? "text"} defaultValue={actual} disabled={!editable} list={props.lista ? listaId : undefined} onBlur={(e) => guardar(e.target.value)} />
        )}
      </Campo>
    );
  };
  const revisionTono = t.revision === "conforme" ? "ok" : t.revision === "observada" ? "critico" : "neutro";
  return (
    <div className={`rounded-xl border p-3 transition-colors ${activo ? "border-marca bg-marca-suave/40" : errores.length ? "border-critico/50" : "border-line"}`} onClick={alElegir}>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="grid size-7 place-items-center rounded-full bg-marca text-[12px] font-bold text-white">{t.orden}</span>
        <span className="text-[13px] font-semibold text-titulo">Folios {t.folio_desde ?? "?"}–{t.folio_hasta ?? "?"}</span>
        {t.pagina_desde != null && <span className="text-[12px] text-texto-3">· páginas {t.pagina_desde}–{t.pagina_hasta}</span>}
        <Insignia tono={revisionTono}>{t.revision === "pendiente" ? "Sin revisar" : t.revision === "conforme" ? "Conforme" : "Con observación"}</Insignia>
        <div className="ml-auto flex gap-1" onClick={(e) => e.stopPropagation()}>
          {editable && propuesto && <Boton tamano="sm" variante="motor" icono={<CheckCheck />} onClick={alConfirmar}>Confirmar lo propuesto</Boton>}
          {editable && conPaginas && !ultimo && <Boton tamano="sm" variante="fantasma" icono={<Merge />} onClick={alUnir}>Unir con el siguiente</Boton>}
          {editable && !conPaginas && <Boton tamano="sm" variante="fantasma" icono={<Trash2 />} onClick={alQuitar}>Quitar</Boton>}
        </div>
      </div>
      <div className="grid gap-2 sm:grid-cols-[170px_minmax(0,1fr)]" onClick={(e) => e.stopPropagation()}>
        {campo("fecha", "Fecha", { valor: t.fecha_texto ?? "" })}
        <div>
          {campo("tipo_documental", "Tipo documental", { lista: true })}
          <datalist id={listaId}>{tipos.map((x) => <option key={x} value={x} />)}</datalist>
        </div>
      </div>
      <div className="mt-1 grid gap-x-3 text-[11px] sm:grid-cols-[170px_minmax(0,1fr)]">
        <Origen o={t.origen.fecha} />
        <Origen o={t.origen.tipo_documental} />
      </div>
      <div className="mt-2" onClick={(e) => e.stopPropagation()}>{campo("detalle", "Detalle (asunto, número, remitente…)", { area: true })}</div>
      <div className="mt-2 grid gap-2 sm:grid-cols-3" onClick={(e) => e.stopPropagation()}>
        {!conPaginas && campo("folio_desde", "Folio desde", { tipo: "number" })}
        {!conPaginas && campo("folio_hasta", "Folio hasta", { tipo: "number" })}
        {campo("no_radicado", "Radicado")}
        <div className={conPaginas ? "sm:col-span-2" : "sm:col-span-3"}>{campo("observaciones", "Observaciones")}</div>
      </div>
      <div className="mt-2 rounded-lg border border-line bg-canvas/60 p-2" onClick={(e) => e.stopPropagation()}>
        <p className="mb-1 text-[11.5px] font-semibold text-texto-3">Metadatos del documento{t.metadatos?.numero ? ` · n.º ${t.metadatos.numero}` : ""}</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {METADATOS.map(([clave, etiqueta]) => {
            const actual = t.metadatos?.[clave] ?? "";
            return (
              <div key={clave} className={clave === "asunto" ? "sm:col-span-2" : ""}>
                <Campo etiqueta={etiqueta}>
                  <Entrada key={actual} defaultValue={actual} disabled={!editable} aria-label={`${etiqueta} del trámite ${t.orden}`} onBlur={(e) => e.target.value !== actual && alGuardar("metadatos", { [clave]: e.target.value })} />
                </Campo>
                {t.origen[`metadatos.${clave}`] && <div className="mt-0.5 text-[11px]"><Origen o={t.origen[`metadatos.${clave}`]} /></div>}
              </div>
            );
          })}
        </div>
      </div>
      <div className="mt-1 flex flex-col gap-0.5 text-[11px]"><Origen o={t.origen.folios} />{t.origen.corte && <Origen o={t.origen.corte} />}{t.origen.detalle && <Origen o={t.origen.detalle} />}</div>
      {errores.map((e) => <p key={e} className="mt-1 flex items-center gap-1 text-[12px] text-critico"><AlertTriangle className="size-3.5" />{e}</p>)}
      {t.observacion_revision && <p className="mt-2 flex items-center gap-1 rounded-lg bg-critico-suave px-2 py-1 text-[12.5px] text-critico"><MessageSquareWarning className="size-4" />Observación de la verificación: {t.observacion_revision}</p>}
      {verifica && (
        <div className="mt-2 flex flex-wrap items-end gap-2 border-t border-line pt-2" onClick={(e) => e.stopPropagation()}>
          <Boton tamano="sm" variante={t.revision === "conforme" ? "primario" : "secundario"} icono={<CheckCircle2 />} onClick={() => alRevisar(true, "")}>Conforme</Boton>
          {!observando ? <Boton tamano="sm" icono={<MessageSquareWarning />} onClick={() => setObservando(true)}>Con observación</Boton> : (
            <>
              <Entrada className="max-w-sm" placeholder="Qué hay que corregir" aria-label={`Observación del trámite ${t.orden}`} value={obs} onChange={(e) => setObs(e.target.value)} />
              <Boton tamano="sm" variante="peligro" disabled={obs.trim().length < 5} onClick={() => (alRevisar(false, obs), setObservando(false))}>Registrar</Boton>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Visor({ base, total, pagina, alCambiar, info, tramite, texto, puedeDividir, dividiendo, alDividir }: {
  base: string; total: number; pagina: number; alCambiar: (n: number) => void; info?: DetalleHoja["paginas"][number]; tramite: TramiteHoja | null; texto?: TextoOcr;
  puedeDividir: boolean; dividiendo: boolean; alDividir: () => void;
}) {
  const avisos = useAvisos();
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [verTexto, setVerTexto] = useState(false);
  useEffect(() => {
    if (!total) return;
    let vivo = true;
    let actual: string | null = null;
    setUrl(null);
    setError(null);
    urlLocal(`${base}/paginas/${pagina}/imagen`).then((u) => (vivo ? (actual = u, setUrl(u)) : URL.revokeObjectURL(u))).catch((e) => vivo && setError(e.message));
    return () => {
      vivo = false;
      if (actual) URL.revokeObjectURL(actual);
    };
  }, [base, pagina, total]);
  if (!total) return <Tarjeta className="p-6 text-center text-[13px] text-texto-3">Este expediente no tiene imágenes digitalizadas. Los folios se escriben a mano.</Tarjeta>;
  return (
    <Tarjeta className="flex flex-col overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <Boton tamano="sm" variante="fantasma" icono={<ChevronLeft />} disabled={pagina <= 1} onClick={() => alCambiar(pagina - 1)} aria-label="Página anterior" />
        <span className="text-[13px]">Página</span>
        <Entrada key={pagina} className="w-16 text-center" type="number" min={1} max={total} defaultValue={pagina} aria-label="Número de página"
          onKeyDown={(e) => e.key === "Enter" && alCambiar(Math.min(total, Math.max(1, Number((e.target as HTMLInputElement).value) || 1)))} />
        <span className="text-[13px] text-texto-3">de {total}</span>
        <Boton tamano="sm" variante="fantasma" icono={<ChevronRight />} disabled={pagina >= total} onClick={() => alCambiar(pagina + 1)} aria-label="Página siguiente" />
        {tramite && <span className="text-[12px] text-texto-3">· trámite {tramite.orden}{tramite.tipo_documental ? ` · ${tramite.tipo_documental}` : ""}</span>}
        <div className="ml-auto flex gap-1">
          {puedeDividir && <Boton tamano="sm" variante="primario" icono={<Scissors />} cargando={dividiendo} onClick={alDividir}>Aquí empieza otro documento</Boton>}
          <Boton tamano="sm" variante={verTexto ? "suave" : "fantasma"} icono={<FileText />} onClick={() => setVerTexto((v) => !v)}>Texto OCR</Boton>
          <Boton tamano="sm" variante="fantasma" icono={<ExternalLink />} onClick={() => abrirArchivo(`${base}/paginas/${pagina}/original`).catch((e) => avisos.error(e.message))}>Original</Boton>
        </div>
      </div>
      {verTexto && (
        <div className="max-h-64 overflow-auto border-b border-line bg-surface px-4 py-3">
          {!texto || texto.estado === "pendiente" ? <p className="text-[12.5px] text-texto-3">Esta página aún no se ha leído con OCR.</p> : texto.estado === "error" ? <p className="text-[12.5px] text-critico">El OCR no pudo leerla: {texto.detalle}</p> : (
            <>
              <p className="mb-1 text-[11.5px] text-texto-3">{texto.motor} · {texto.palabras} palabras · confianza {texto.confianza ?? "—"} %{(texto.confianza ?? 100) < 60 ? " · baja: revise contra la imagen" : ""}</p>
              {texto.lineas.map(([l, c], i) => <p key={i} className={`font-mono text-[12px] ${c < 60 ? "text-aviso" : "text-texto-2"}`} title={`confianza ${c} %`}>{l}</p>)}
            </>
          )}
        </div>
      )}
      <div className="grid min-h-[60vh] place-items-center bg-surface-muted p-3">
        {error ? <p className="text-[13px] text-critico">{error}</p> : url ? <img src={url} alt={`Página ${pagina} del expediente`} className="max-h-[78vh] w-auto max-w-full rounded-md bg-white shadow-sm" /> : <Cargando texto="Abriendo la página…" />}
      </div>
      {info && <p className="border-t border-line px-3 py-1.5 text-[11.5px] text-texto-3">Archivo «{info.archivo}», página {info.pagina_en_archivo} · calidad: {info.estado}</p>}
    </Tarjeta>
  );
}

