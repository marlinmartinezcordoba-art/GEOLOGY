"use client";

import { CheckCircle2, ChevronDown, FileSpreadsheet, Search, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { ModalMotivo } from "@/components/ui/acciones";
import { useAvisos } from "@/components/ui/avisos";
import { Boton, CajaError, Cargando, Codigo, Insignia, Modal, Nota, Tabla, Vacio } from "@/components/ui/basicos";
import { Area, Campo, Entrada, Selector } from "@/components/ui/campos";
import { api, apiSubir } from "@/lib/api";
import { fecha, fechaHora, numero } from "@/lib/formato";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { FilaFuid, Lote, Proyecto, Unidad } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

const ESTADO_LOTE: Record<Lote["estado"], { texto: string; tono: "ok" | "aviso" | "info" | "neutro" }> = {
  validado: { texto: "Listo para integrar", tono: "ok" },
  con_errores: { texto: "Con errores", tono: "aviso" },
  integrado: { texto: "Integrado", tono: "info" },
  descartado: { texto: "Descartado", tono: "neutro" },
};

/** M08 · Inventario FUID del proyecto: importar, mapear columnas, revisar errores, integrar y consultar unidades. */
export function Inventario({ proyecto }: { proyecto: Proyecto }) {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const base = `/proyectos/${proyecto.id}/inventario`;
  const lotes = useDatos(() => api<Lote[]>(`${base}/lotes`), [base]);
  const campos = useDatos(() => api<Record<string, string>>(`${base}/campos`), [base]);
  const [abierto, setAbierto] = useState<string | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recarga, setRecarga] = useState(0);
  const entrada = useRef<HTMLInputElement>(null);
  const gestiona = puede(PERMISOS.inventario) && proyecto.estado !== "cerrado";

  async function importar(archivo: File) {
    setSubiendo(true);
    setError(null);
    try {
      const datos = new FormData();
      datos.append("archivo", archivo);
      const lote = await apiSubir<Lote>(`${base}/lotes`, datos);
      avisos.exito(lote.filas_con_error ? `FUID leído: ${lote.filas_con_error === 1 ? "1 fila" : `${lote.filas_con_error} filas`} con errores para revisar.` : `FUID leído: ${lote.total_filas} filas listas para integrar.`);
      await lotes.recargar();
      setAbierto(lote.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubiendo(false);
      if (entrada.current) entrada.current.value = "";
    }
  }

  return (
    <div className="flex flex-col gap-5 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-2xl text-[13px] text-texto-2">
          <p className="font-semibold text-titulo">Formato Único de Inventario Documental</p>
          <p>Suba el FUID en Excel o CSV. ARCA ubica el encabezado (también el de dos niveles del AGN), reconoce las columnas y valida fila por fila. El archivo original queda guardado tal cual llegó.</p>
        </div>
        {gestiona && (
          <>
            <input ref={entrada} type="file" accept=".xlsx,.csv" hidden onChange={(e) => e.target.files?.[0] && importar(e.target.files[0])} />
            <Boton variante="primario" icono={<Upload />} cargando={subiendo} onClick={() => entrada.current?.click()}>Importar FUID</Boton>
          </>
        )}
      </div>
      {error && <CajaError mensaje={error} />}
      {lotes.cargando && !lotes.datos ? (
        <Cargando />
      ) : !lotes.datos?.length ? (
        <Vacio icono={<FileSpreadsheet />} titulo="Sin inventario" descripcion="Importe el FUID del proyecto: sus filas se vuelven las unidades documentales que luego se digitalizan." />
      ) : (
        <ul className="flex flex-col gap-2">
          {lotes.datos.map((l) => (
            <li key={l.id} className="rounded-xl border border-line">
              <button className="flex w-full flex-wrap items-center gap-3 px-4 py-3 text-left" onClick={() => setAbierto(abierto === l.id ? null : l.id)}>
                <FileSpreadsheet className="size-5 text-marca" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold text-texto">{l.nombre_archivo}</span>
                  <span className="block text-[12.5px] text-texto-3">{fechaHora(l.creado_en)} · {numero(l.total_filas)} filas · {numero(l.filas_validas)} válidas · {numero(l.filas_con_error)} con errores{l.estado === "integrado" ? ` · ${numero(l.filas_integradas)} integradas` : ""}</span>
                </span>
                <Insignia tono={ESTADO_LOTE[l.estado].tono} punto>{ESTADO_LOTE[l.estado].texto}</Insignia>
                <ChevronDown className={`size-4 text-texto-3 transition-transform ${abierto === l.id ? "" : "-rotate-90"}`} />
              </button>
              {abierto === l.id && (
                <DetalleLote base={base} lote={l} campos={campos.datos ?? {}} gestiona={gestiona} alCambiar={async () => (await lotes.recargar(), setRecarga((n) => n + 1))} />
              )}
            </li>
          ))}
        </ul>
      )}
      <Unidades base={base} recarga={recarga} />
    </div>
  );
}

function DetalleLote({ base, lote, campos, gestiona, alCambiar }: { base: string; lote: Lote; campos: Record<string, string>; gestiona: boolean; alCambiar: () => Promise<void> }) {
  const avisos = useAvisos();
  const [soloErrores, setSoloErrores] = useState(lote.filas_con_error > 0);
  const filas = useDatos(() => api<FilaFuid[]>(`${base}/lotes/${lote.id}/filas`, { consulta: { solo_errores: soloErrores ? "true" : undefined, limite: 300 } }), [base, lote.id, soloErrores, lote.mapeo]);
  const [mapeo, setMapeo] = useState(false);
  const [integrar, setIntegrar] = useState(false);
  const [descartar, setDescartar] = useState(false);
  const abierto = lote.estado === "validado" || lote.estado === "con_errores";

  return (
    <div className="border-t border-line px-4 py-4">
      {lote.motivo_estado && <div className="mb-3"><Nota tono={lote.estado === "con_errores" ? "aviso" : "info"}>{lote.motivo_estado}</Nota></div>}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-[12.5px] text-texto-3">Encabezado en la fila {lote.fila_encabezado}{lote.hoja ? ` de la hoja «${lote.hoja}»` : ""}. Columnas reconocidas: {Object.keys(lote.mapeo).length}.</span>
        <span className="flex-1" />
        <Boton tamano="sm" variante="fantasma" onClick={() => setSoloErrores(!soloErrores)}>{soloErrores ? "Ver todas las filas" : "Ver solo filas con errores"}</Boton>
        {gestiona && abierto && (
          <>
            <Boton tamano="sm" onClick={() => setMapeo(true)}>Ajustar columnas</Boton>
            <Boton tamano="sm" variante="fantasma" icono={<Trash2 />} onClick={() => setDescartar(true)}>Descartar</Boton>
            <Boton tamano="sm" variante="primario" icono={<CheckCircle2 />} disabled={!lote.filas_validas} onClick={() => setIntegrar(true)}>Integrar {numero(lote.filas_validas)} unidades</Boton>
          </>
        )}
      </div>
      {filas.cargando && !filas.datos ? <Cargando /> : filas.error ? <CajaError mensaje={filas.error} /> : !filas.datos?.length ? (
        <p className="py-6 text-center text-[13px] text-texto-3">{soloErrores ? "Ninguna fila tiene errores." : "Sin filas."}</p>
      ) : (
        <Tabla className="max-h-[28rem] overflow-y-auto rounded-lg border border-line">
          <thead><tr><th>Fila</th><th>Identificador</th><th>Nombre</th><th>Fechas</th><th>Folios</th><th>Resultado</th></tr></thead>
          <tbody>
            {filas.datos.map((f) => (
              <tr key={f.numero_fila}>
                <td className="tabular text-texto-3">{f.numero_fila}</td>
                <td><Codigo>{String(f.normalizado.identificador ?? "—")}</Codigo></td>
                <td className="max-w-72"><span className="line-clamp-2">{String(f.normalizado.nombre ?? "")}</span></td>
                <td className="whitespace-nowrap">{f.normalizado.fecha_inicial ? `${fecha(String(f.normalizado.fecha_inicial))} – ${fecha(String(f.normalizado.fecha_final))}` : "s.f."}</td>
                <td className="tabular">{f.normalizado.folios ?? "—"}</td>
                <td className="max-w-80">
                  {f.errores.map((e) => <span key={e} className="block text-[12.5px] text-critico">✕ {e}</span>)}
                  {f.avisos.map((a) => <span key={a} className="block text-[12.5px] text-aviso">! {a}</span>)}
                  {!f.errores.length && !f.avisos.length && <span className="text-[12.5px] text-ok">✓ Correcta</span>}
                  {f.unidad_id && <span className="block text-[12px] text-info">Integrada</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </Tabla>
      )}
      {mapeo && <ModalMapeo base={base} lote={lote} campos={campos} alCerrar={() => setMapeo(false)} alGuardar={async () => (setMapeo(false), avisos.exito("Columnas aplicadas y filas validadas de nuevo."), await alCambiar())} />}
      <ModalIntegrar abierto={integrar} lote={lote} base={base} alCerrar={() => setIntegrar(false)} alGuardar={async (n) => (avisos.exito(`${n} unidades documentales integradas al proyecto.`), await alCambiar())} />
      <ModalMotivo
        abierto={descartar}
        titulo="Descartar este FUID"
        descripcion="El archivo y su validación se conservan como evidencia, pero no se integra nada."
        boton="Descartar"
        peligro
        alCerrar={() => setDescartar(false)}
        alConfirmar={async (motivo) => {
          await api(`${base}/lotes/${lote.id}/descartar`, { metodo: "POST", cuerpo: { motivo } });
          await alCambiar();
        }}
      />
    </div>
  );
}

function ModalMapeo({ base, lote, campos, alCerrar, alGuardar }: { base: string; lote: Lote; campos: Record<string, string>; alCerrar: () => void; alGuardar: () => Promise<void> }) {
  const [mapeo, setMapeo] = useState<Record<string, number>>(lote.mapeo);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  return (
    <Modal
      abierto
      ancho="lg"
      alCerrar={alCerrar}
      titulo="Asignar las columnas del FUID"
      descripcion="Diga en qué columna del archivo está cada dato. Lo obligatorio es el nombre y el número de orden o el identificador de la unidad."
      pie={
        <>
          <Boton onClick={alCerrar}>Cancelar</Boton>
          <Boton
            variante="primario"
            cargando={enviando}
            onClick={async () => {
              setEnviando(true);
              setError(null);
              try {
                await api(`${base}/lotes/${lote.id}/mapeo`, { metodo: "PUT", cuerpo: { mapeo } });
                await alGuardar();
              } catch (e) {
                setError((e as Error).message);
                setEnviando(false);
              }
            }}
          >
            Aplicar y validar
          </Boton>
        </>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {Object.entries(campos).map(([campo, nombre]) => (
          <Campo key={campo} etiqueta={nombre} requerido={campo === "nombre"}>
            <Selector
              value={mapeo[campo] ?? ""}
              onChange={(e) => {
                const copia = { ...mapeo };
                if (e.target.value === "") delete copia[campo];
                else copia[campo] = Number(e.target.value);
                setMapeo(copia);
              }}
            >
              <option value="">— No está en el archivo —</option>
              {lote.encabezados.map((h, i) => <option key={i} value={i}>Columna {i + 1}{h ? `: ${h}` : ""}</option>)}
            </Selector>
          </Campo>
        ))}
        {error && <div className="sm:col-span-2"><CajaError mensaje={error} /></div>}
      </div>
    </Modal>
  );
}

function ModalIntegrar({ abierto, lote, base, alCerrar, alGuardar }: { abierto: boolean; lote: Lote; base: string; alCerrar: () => void; alGuardar: (n: number) => Promise<void> }) {
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const exigeMotivo = lote.filas_con_error > 0;
  return (
    <Modal
      abierto={abierto}
      alCerrar={alCerrar}
      titulo="Integrar al proyecto"
      descripcion={`${numero(lote.filas_validas)} filas se vuelven unidades documentales.${exigeMotivo ? ` ${numero(lote.filas_con_error)} filas con errores NO se integran.` : ""}`}
      pie={
        <>
          <Boton onClick={alCerrar}>Cancelar</Boton>
          <Boton
            variante="primario"
            cargando={enviando}
            disabled={exigeMotivo && motivo.trim().length < 5}
            onClick={async () => {
              setEnviando(true);
              setError(null);
              try {
                const r = await api<Lote>(`${base}/lotes/${lote.id}/integrar`, { metodo: "POST", cuerpo: { motivo: motivo.trim() || null } });
                alCerrar();
                await alGuardar(r.filas_integradas);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setEnviando(false);
              }
            }}
          >
            Integrar
          </Boton>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        {exigeMotivo && (
          <Campo etiqueta="Motivo" requerido ayuda="Por qué se integra sin las filas con errores. Queda en la auditoría y en la conciliación del lote.">
            <Area value={motivo} onChange={(e) => setMotivo(e.target.value)} autoFocus />
          </Campo>
        )}
        {!exigeMotivo && <Nota tono="ok">Todas las filas pasaron la validación.</Nota>}
        {error && <CajaError mensaje={error} />}
      </div>
    </Modal>
  );
}

function Unidades({ base, recarga }: { base: string; recarga: number }) {
  const [texto, setTexto] = useState("");
  const [buscar, setBuscar] = useState("");
  const [desde, setDesde] = useState(0);
  const datos = useDatos(() => api<{ total: number; unidades: Unidad[] }>(`${base}/unidades`, { consulta: { q: buscar, desplazamiento: desde, limite: 50 } }), [base, buscar, desde, recarga]);
  return (
    <div className="mt-2">
      <div className="mb-2 flex flex-wrap items-end justify-between gap-3">
        <p className="font-semibold text-titulo">Unidades documentales del inventario <span className="font-normal text-texto-3">({numero(datos.datos?.total ?? 0)})</span></p>
        <form className="relative w-full sm:w-72" onSubmit={(e) => (e.preventDefault(), setDesde(0), setBuscar(texto))}>
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-texto-3" />
          <Entrada value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Identificador o nombre" className="pl-9" aria-label="Buscar unidad" />
        </form>
      </div>
      {!datos.datos?.unidades.length ? (
        <p className="rounded-xl border border-dashed border-line py-6 text-center text-[13px] text-texto-3">{buscar ? "Ninguna unidad coincide." : "Todavía no hay unidades integradas."}</p>
      ) : (
        <>
          <Tabla className="rounded-xl border border-line">
            <thead><tr><th>Identificador</th><th>Nombre</th><th>Serie</th><th>Fechas extremas</th><th>Caja / carpeta</th><th>Folios</th></tr></thead>
            <tbody>
              {datos.datos.unidades.map((u) => (
                <tr key={u.id}>
                  <td><Codigo>{u.identificador}</Codigo></td>
                  <td className="max-w-80"><span className="line-clamp-2">{u.nombre}</span></td>
                  <td>{u.codigo_serie ?? "—"}</td>
                  <td className="whitespace-nowrap">{u.fecha_inicial ? `${fecha(u.fecha_inicial)} – ${fecha(u.fecha_final)}` : "s.f."}</td>
                  <td>{[u.caja, u.carpeta, u.tomo, u.otro].filter(Boolean).join(" / ") || "—"}</td>
                  <td className="tabular">{u.folios ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </Tabla>
          <div className="mt-2 flex justify-end gap-2">
            <Boton tamano="sm" disabled={desde === 0} onClick={() => setDesde(Math.max(0, desde - 50))}>Anteriores</Boton>
            <Boton tamano="sm" disabled={desde + 50 >= (datos.datos?.total ?? 0)} onClick={() => setDesde(desde + 50)}>Siguientes</Boton>
          </div>
        </>
      )}
    </div>
  );
}
