"use client";

import { BookCheck, CheckCircle2, Download, Eye, FileSpreadsheet, GitCompare, Library, Plus, Trash2, Upload } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { ModalMotivo } from "@/components/ui/acciones";
import { useAvisos } from "@/components/ui/avisos";
import { Boton, Cargando, Codigo, Insignia, Modal, Nota, Tabla, Vacio } from "@/components/ui/basicos";
import { Area, Campo, Entrada, Selector } from "@/components/ui/campos";
import { api, apiSubir } from "@/lib/api";
import { descargarArchivo } from "@/lib/descargas";
import { fecha, fechaHora, numero } from "@/lib/formato";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { ComparacionInstrumento, DetalleVersionInstrumento, Instrumento, Proyecto, VersionInstrumento } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

const NOMBRE_TIPO = { TRD: "Tabla de Retención Documental", TVD: "Tabla de Valoración Documental", CCD: "Cuadro de Clasificación Documental" } as const;
const TONO = { borrador: "neutro", programada: "aviso", vigente: "ok", reemplazada: "info", descartada: "critico" } as const;
const DISPOSICION: Record<string, string> = { CT: "Conservación total", E: "Eliminación", S: "Selección", D: "Digitalización" };
const CAMPO: Record<string, string> = {
  nombre: "Nombre", padre: "Serie", tipos_documentales: "Tipos documentales", retencion_gestion: "Retención en gestión", retencion_central: "Retención en central",
  disposicion: "Disposición", soporte: "Soporte", procedimiento: "Procedimiento", acceso: "Acceso",
};

const SOPORTE: Record<string, string> = { fisico: "Físico", electronico: "Electrónico", hibrido: "Físico y electrónico" };
const titulo = (i: Instrumento) => (i.nombre.toUpperCase().startsWith(i.tipo) ? i.nombre : `${i.tipo} · ${i.nombre}`);
const texto = (v: unknown) => (Array.isArray(v) ? v.join("; ") : v === null || v === undefined || v === "" ? "—" : String(v));

/** M04 · TRD, TVD y CCD del proyecto: se importan, se revisan, se aprueban con el acto administrativo y se versionan. */
export function Instrumentos({ proyecto }: { proyecto: Proyecto }) {
  const { puede, usuario } = useSesion();
  const avisos = useAvisos();
  const base = `/proyectos/${proyecto.id}/instrumentos`;
  const lista = useDatos(() => api<Instrumento[]>(base), [base]);
  const [nuevo, setNuevo] = useState(false);
  const [importando, setImportando] = useState<Instrumento | null>(null);
  const [detalle, setDetalle] = useState<{ instrumento: Instrumento; version: VersionInstrumento } | null>(null);
  const [aprobando, setAprobando] = useState<{ instrumento: Instrumento; version: VersionInstrumento } | null>(null);
  const [descartando, setDescartando] = useState<{ instrumento: Instrumento; version: VersionInstrumento } | null>(null);
  const [comparando, setComparando] = useState<Instrumento | null>(null);
  const gestiona = puede(PERMISOS.instrumentos);
  const aprueba = puede(PERMISOS.instrumentosAprobar);

  if (lista.cargando && !lista.datos) return <Cargando />;
  const instrumentos = lista.datos ?? [];
  return (
    <div className="flex flex-col gap-5 p-5">
      <Nota tono="info">
        Los instrumentos son de la entidad. ARCA los lee tal como llegan y no inventa códigos, tiempos ni disposiciones: lo que falta es un error y bloquea la aprobación. Quien importa no aprueba. Con fecha futura la versión queda programada; la anterior se conserva como evidencia. El FUID avisa los códigos que no estén en la TRD o TVD vigente.
      </Nota>
      <div className="flex flex-wrap items-center gap-2">
        {gestiona && <Boton variante="primario" icono={<Plus />} onClick={() => setNuevo(true)}>Nuevo instrumento</Boton>}
        {(["TRD", "TVD", "CCD"] as const).map((t) => (
          <Boton key={t} variante="fantasma" icono={<FileSpreadsheet />} onClick={() => descargarArchivo(`${base}/plantilla?tipo=${t}`, `Plantilla_${t}.xlsx`).catch((e) => avisos.error(e.message))}>Plantilla {t}</Boton>
        ))}
      </div>
      {!instrumentos.length ? (
        <Vacio icono={<Library />} titulo="El proyecto no tiene instrumentos" descripcion="Cree la TRD, la TVD o el CCD de la entidad e importe el archivo que entregó." />
      ) : (
        instrumentos.map((i) => {
          const vigente = i.versiones.find((v) => v.estado === "vigente");
          const borrador = i.versiones.find((v) => v.estado === "borrador");
          return (
            <section key={i.id} className="rounded-xl border border-line bg-surface shadow-xs">
              <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3">
                <div>
                  <p className="flex items-center gap-2 font-semibold text-titulo"><BookCheck className="size-5 text-marca" />{titulo(i)}</p>
                  <p className="text-[12.5px] text-texto-3">
                    {NOMBRE_TIPO[i.tipo]}
                    {i.periodo_desde || i.periodo_hasta ? ` · periodo ${fecha(i.periodo_desde)} – ${fecha(i.periodo_hasta)}` : ""}
                    {vigente ? ` · vigente la v${vigente.version} (${vigente.acto_administrativo})` : " · sin versión vigente"}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {i.versiones.filter((v) => v.vigente_desde).length >= 1 && i.versiones.length >= 2 && (
                    <Boton tamano="sm" variante="fantasma" icono={<GitCompare />} onClick={() => setComparando(i)}>Comparar versiones</Boton>
                  )}
                  {gestiona && !borrador && <Boton tamano="sm" icono={<Upload />} onClick={() => setImportando(i)}>Importar versión</Boton>}
                </div>
              </header>
              {!i.versiones.length ? (
                <p className="px-4 py-4 text-[13px] text-texto-3">Todavía no se ha importado ninguna versión.</p>
              ) : (
                <Tabla>
                  <thead><tr><th>Versión</th><th>Estado</th><th>Contenido</th><th>Validación</th><th>Acto administrativo</th><th>Vigente desde</th><th /></tr></thead>
                  <tbody>
                    {[...i.versiones].reverse().map((v) => (
                      <tr key={v.id}>
                        <td className="font-semibold">v{v.version}</td>
                        <td><Insignia tono={TONO[v.estado]} punto>{v.estado}</Insignia></td>
                        <td className="text-[12.5px]">{numero(v.totales.dependencias ?? 0)} dependencias · {numero(v.totales.series ?? 0)} series · {numero(v.totales.subseries ?? 0)} subseries</td>
                        <td>
                          {v.errores.length ? <Insignia tono="critico">{v.errores.length} errores</Insignia> : <Insignia tono="ok">Sin errores</Insignia>}
                          {v.avisos.length ? <Insignia tono="aviso" className="ml-1">{v.avisos.length} avisos</Insignia> : null}
                        </td>
                        <td className="text-[12.5px]">{v.acto_administrativo ? <>{v.acto_administrativo}<br /><span className="text-texto-3">{fecha(v.fecha_acto)}</span></> : "—"}</td>
                        <td className="whitespace-nowrap text-[12.5px]">{v.vigente_desde ? fechaHora(v.vigente_desde) : "—"}</td>
                        <td>
                          <div className="flex justify-end gap-1">
                            <Boton tamano="sm" variante="fantasma" icono={<Eye />} onClick={() => setDetalle({ instrumento: i, version: v })}>Revisar</Boton>
                            {v.estado === "borrador" && aprueba && v.creado_por !== usuario.id && !v.errores.length && (
                              <Boton tamano="sm" variante="primario" icono={<CheckCircle2 />} onClick={() => setAprobando({ instrumento: i, version: v })}>Aprobar</Boton>
                            )}
                            {v.estado === "borrador" && gestiona && (
                              <Boton tamano="sm" variante="fantasma" icono={<Trash2 />} onClick={() => setDescartando({ instrumento: i, version: v })}>Descartar</Boton>
                            )}
                          </div>
                          {v.estado === "borrador" && aprueba && v.creado_por === usuario.id && <p className="text-right text-[11.5px] text-texto-3">La aprueba otra persona</p>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Tabla>
              )}
            </section>
          );
        })
      )}

      <NuevoInstrumento abierto={nuevo} base={base} alCerrar={() => setNuevo(false)} alCrear={() => void lista.recargar()} />
      {importando && <ImportarVersion instrumento={importando} base={base} alCerrar={() => setImportando(null)} alImportar={(v) => { void lista.recargar(); setDetalle({ instrumento: importando, version: v }); }} />}
      {detalle && <DetalleVersion base={base} {...detalle} alCerrar={() => setDetalle(null)} />}
      {aprobando && <Aprobar base={base} {...aprobando} alCerrar={() => setAprobando(null)} alAprobar={() => void lista.recargar()} />}
      <ModalMotivo
        abierto={!!descartando}
        titulo={`Descartar la v${descartando?.version.version ?? ""}`}
        descripcion="El borrador queda como evidencia, pero no se podrá aprobar. Después puede importar el archivo corregido."
        boton="Descartar"
        peligro
        alCerrar={() => setDescartando(null)}
        alConfirmar={async (motivo) => {
          await api(`${base}/${descartando!.instrumento.id}/versiones/${descartando!.version.id}/descartar`, { metodo: "POST", cuerpo: { motivo } });
          avisos.exito("Borrador descartado.");
          void lista.recargar();
        }}
      />
      {comparando && <Comparar base={base} instrumento={comparando} alCerrar={() => setComparando(null)} />}
    </div>
  );
}

function NuevoInstrumento({ abierto, base, alCerrar, alCrear }: { abierto: boolean; base: string; alCerrar: () => void; alCrear: () => void }) {
  const avisos = useAvisos();
  const [tipo, setTipo] = useState<"TRD" | "TVD" | "CCD">("TRD");
  const [nombre, setNombre] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  async function crear() {
    setEnviando(true);
    setError(null);
    try {
      await api(base, { metodo: "POST", cuerpo: { tipo, nombre: nombre.trim(), descripcion, periodo_desde: desde || null, periodo_hasta: hasta || null } });
      avisos.exito(`${tipo} creada. Ahora importe el archivo de la entidad.`);
      setNombre("");
      setDescripcion("");
      alCrear();
      alCerrar();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }
  return (
    <Modal abierto={abierto} alCerrar={alCerrar} titulo="Nuevo instrumento" pie={<><Boton onClick={alCerrar}>Cancelar</Boton><Boton variante="primario" cargando={enviando} disabled={nombre.trim().length < 3} onClick={crear}>Crear</Boton></>}>
      <div className="flex flex-col gap-3">
        <Campo etiqueta="Tipo" requerido>
          <Selector value={tipo} onChange={(e) => setTipo(e.target.value as typeof tipo)}>
            {Object.entries(NOMBRE_TIPO).map(([k, v]) => <option key={k} value={k}>{k} · {v}</option>)}
          </Selector>
        </Campo>
        <Campo etiqueta="Nombre" requerido ayuda="Como lo identifica la entidad."><Entrada value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder={`${tipo} de la entidad`} /></Campo>
        <Campo etiqueta="Descripción"><Area value={descripcion} onChange={(e) => setDescripcion(e.target.value)} /></Campo>
        {tipo === "TVD" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Campo etiqueta="Periodo valorado desde"><Entrada type="date" value={desde} onChange={(e) => setDesde(e.target.value)} /></Campo>
            <Campo etiqueta="Hasta"><Entrada type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} /></Campo>
          </div>
        )}
        {error && <Nota tono="critico">{error}</Nota>}
      </div>
    </Modal>
  );
}

function ImportarVersion({ instrumento, base, alCerrar, alImportar }: { instrumento: Instrumento; base: string; alCerrar: () => void; alImportar: (v: VersionInstrumento) => void }) {
  const avisos = useAvisos();
  const entrada = useRef<HTMLInputElement>(null);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  async function importar() {
    if (!archivo) return;
    setEnviando(true);
    setError(null);
    try {
      const datos = new FormData();
      datos.append("archivo", archivo);
      datos.append("motivo", motivo.trim());
      const v = await apiSubir<VersionInstrumento>(`${base}/${instrumento.id}/versiones`, datos);
      if (v.errores.length) avisos.error(`v${v.version} leída con ${v.errores.length} errores: revíselos y corrija el archivo.`);
      else avisos.exito(`v${v.version} leída: ${v.totales.series} series y ${v.totales.subseries} subseries. Queda en borrador para aprobar.`);
      alImportar(v);
      alCerrar();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }
  return (
    <Modal abierto alCerrar={alCerrar} titulo={`Importar versión · ${titulo(instrumento)}`} descripcion="Excel o CSV. Se acepta el formato tabular de la plantilla y el formato oficial del AGN (una hoja por dependencia)."
      pie={<><Boton onClick={alCerrar}>Cancelar</Boton><Boton variante="primario" icono={<Upload />} cargando={enviando} disabled={!archivo || motivo.trim().length < 5} onClick={importar}>Importar</Boton></>}>
      <div className="flex flex-col gap-3">
        <Campo etiqueta="Archivo" requerido>
          <div className="flex items-center gap-2">
            <input ref={entrada} type="file" accept=".xlsx,.csv" hidden onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
            <Boton icono={<FileSpreadsheet />} onClick={() => entrada.current?.click()}>Elegir archivo</Boton>
            <span className="text-[13px] text-texto-2">{archivo?.name ?? "Ninguno"}</span>
          </div>
        </Campo>
        <Campo etiqueta="Motivo" requerido ayuda="Por qué llega esta versión (entrega inicial, actualización aprobada por la entidad…)."><Area value={motivo} onChange={(e) => setMotivo(e.target.value)} /></Campo>
        {error && <Nota tono="critico">{error}</Nota>}
      </div>
    </Modal>
  );
}

function DetalleVersion({ base, instrumento, version, alCerrar }: { base: string; instrumento: Instrumento; version: VersionInstrumento; alCerrar: () => void }) {
  const avisos = useAvisos();
  const d = useDatos(() => api<DetalleVersionInstrumento>(`${base}/${instrumento.id}/versiones/${version.id}`), [version.id]);
  const [filtro, setFiltro] = useState("");
  const elementos = useMemo(() => {
    const q = filtro.trim().toLowerCase();
    const todos = d.datos?.elementos ?? [];
    if (!q) return todos;
    return todos.filter((e) => e.nivel === "dependencia" || `${e.codigo} ${e.nombre} ${e.tipos_documentales.join(" ")}`.toLowerCase().includes(q));
  }, [d.datos, filtro]);
  const conRetencion = instrumento.tipo !== "CCD";
  return (
    <Modal abierto ancho="xl" alCerrar={alCerrar} titulo={`${titulo(instrumento)} · v${version.version}`} descripcion={<Insignia tono={TONO[version.estado]} punto>{version.estado}</Insignia>}
      pie={<Boton onClick={alCerrar}>Cerrar</Boton>}>
      {!d.datos ? <Cargando /> : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2 text-[12.5px] text-texto-3">
            Fuente: <b className="text-texto-2">{d.datos.nombre_archivo}</b> · SHA-256 <Codigo className="text-[11px]">{d.datos.sha256.slice(0, 16)}…</Codigo>
            <Boton tamano="sm" variante="fantasma" icono={<Download />} onClick={() => descargarArchivo(`${base}/${instrumento.id}/versiones/${version.id}/archivo`, d.datos!.nombre_archivo).catch((e) => avisos.error(e.message))}>Archivo original</Boton>
            {d.datos.motivo && <span>· Motivo: {d.datos.motivo}</span>}
          </div>
          {d.datos.errores.length > 0 && <Hallazgos tono="critico" titulo={`Errores (${d.datos.errores.length}) · bloquean la aprobación`} lista={d.datos.errores} />}
          {d.datos.avisos.length > 0 && <Hallazgos tono="aviso" titulo={`Avisos (${d.datos.avisos.length})`} lista={d.datos.avisos} />}
          {d.datos.correcciones.length > 0 && <Hallazgos tono="info" titulo={`Normalizaciones aplicadas (${d.datos.correcciones.length})`} lista={d.datos.correcciones} />}
          <Entrada value={filtro} onChange={(e) => setFiltro(e.target.value)} placeholder="Buscar por código, serie o tipo documental" className="max-w-md" />
          <Tabla className="rounded-xl border border-line">
            <thead>
              <tr><th>Código</th><th>Serie / subserie</th><th>Tipos documentales</th>{conRetencion && <><th>AG</th><th>AC</th><th>Disposición</th></>}<th>Soporte</th><th>Origen</th></tr>
            </thead>
            <tbody>
              {elementos.map((e) =>
                e.nivel === "dependencia" ? (
                  <tr key={`d-${e.codigo}`} className="bg-surface-muted">
                    <td colSpan={conRetencion ? 8 : 5} className="font-semibold text-titulo">{e.codigo} · {e.nombre}</td>
                  </tr>
                ) : (
                  <tr key={`${e.nivel}-${e.codigo}`}>
                    <td className="whitespace-nowrap"><Codigo>{e.codigo}</Codigo></td>
                    <td className={e.nivel === "subserie" ? "pl-8" : "font-medium"}>{e.nombre}{e.procedimiento && <p className="text-[11.5px] text-texto-3">{e.procedimiento}</p>}</td>
                    <td className="text-[12.5px]">{e.tipos_documentales.join("; ") || "—"}</td>
                    {conRetencion && (
                      <>
                        <td className="tabular">{e.retencion_gestion ?? "—"}</td>
                        <td className="tabular">{e.retencion_central ?? "—"}</td>
                        <td>{e.disposicion ? <span title={DISPOSICION[e.disposicion]}>{e.disposicion}</span> : "—"}</td>
                      </>
                    )}
                    <td>{e.soporte ? (SOPORTE[e.soporte] ?? e.soporte) : "—"}</td>
                    <td className="whitespace-nowrap text-[11.5px] text-texto-3">{e.hoja}{e.fila ? ` · fila ${e.fila}` : ""}</td>
                  </tr>
                ),
              )}
            </tbody>
          </Tabla>
        </div>
      )}
    </Modal>
  );
}

function Hallazgos({ tono, titulo, lista }: { tono: "critico" | "aviso" | "info"; titulo: string; lista: string[] }) {
  return (
    <Nota tono={tono}>
      <p className="font-semibold">{titulo}</p>
      <ul className="mt-1 max-h-40 list-disc overflow-auto pl-5 text-[12.5px]">{lista.map((x, n) => <li key={n}>{x}</li>)}</ul>
    </Nota>
  );
}

function Aprobar({ base, instrumento, version, alCerrar, alAprobar }: { base: string; instrumento: Instrumento; version: VersionInstrumento; alCerrar: () => void; alAprobar: () => void }) {
  const avisos = useAvisos();
  const [acto, setActo] = useState("");
  const [fechaActo, setFechaActo] = useState("");
  const [convalidacion, setConvalidacion] = useState("");
  const [vigencia, setVigencia] = useState("");
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  async function aprobar() {
    setEnviando(true);
    setError(null);
    try {
      const r = await api<Instrumento>(`${base}/${instrumento.id}/versiones/${version.id}/aprobar`, {
        metodo: "POST",
        cuerpo: { acto_administrativo: acto.trim(), fecha_acto: fechaActo, convalidacion, vigente_desde: vigencia ? new Date(vigencia).toISOString() : null, motivo: motivo.trim() },
      });
      const estado = r.versiones.find((v) => v.id === version.id)?.estado;
      avisos.exito(estado === "programada" ? `v${version.version} aprobada y programada.` : `v${version.version} aprobada: ya está vigente.`);
      alAprobar();
      alCerrar();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }
  return (
    <Modal abierto alCerrar={alCerrar} titulo={`Aprobar ${instrumento.tipo} v${version.version}`} descripcion="Desde su vigencia reemplaza la versión actual, que queda como evidencia. Lo ya clasificado conserva el instrumento con que se hizo."
      pie={<><Boton onClick={alCerrar}>Cancelar</Boton><Boton variante="primario" icono={<CheckCircle2 />} cargando={enviando} disabled={acto.trim().length < 3 || !fechaActo || motivo.trim().length < 5} onClick={aprobar}>Aprobar</Boton></>}>
      <div className="flex flex-col gap-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo etiqueta="Acto administrativo" requerido ayuda="Resolución o acuerdo que adopta el instrumento."><Entrada value={acto} onChange={(e) => setActo(e.target.value)} /></Campo>
          <Campo etiqueta="Fecha del acto" requerido><Entrada type="date" value={fechaActo} onChange={(e) => setFechaActo(e.target.value)} /></Campo>
        </div>
        <Campo etiqueta="Convalidación" ayuda="Concepto o certificado del consejo de archivos, si ya existe."><Entrada value={convalidacion} onChange={(e) => setConvalidacion(e.target.value)} /></Campo>
        <Campo etiqueta="Vigente desde" ayuda="Vacío = desde ahora. Una fecha futura deja la versión programada."><Entrada type="datetime-local" value={vigencia} onChange={(e) => setVigencia(e.target.value)} /></Campo>
        <Campo etiqueta="Motivo" requerido><Area value={motivo} onChange={(e) => setMotivo(e.target.value)} /></Campo>
        {error && <Nota tono="critico">{error}</Nota>}
      </div>
    </Modal>
  );
}

function Comparar({ base, instrumento, alCerrar }: { base: string; instrumento: Instrumento; alCerrar: () => void }) {
  const opciones = instrumento.versiones.filter((v) => v.estado !== "descartada");
  const [desde, setDesde] = useState(opciones[Math.max(0, opciones.length - 2)]?.id ?? "");
  const [hasta, setHasta] = useState(opciones[opciones.length - 1]?.id ?? "");
  const c = useDatos(() => (desde && hasta && desde !== hasta ? api<ComparacionInstrumento>(`${base}/${instrumento.id}/comparar`, { consulta: { desde, hasta } }) : Promise.resolve(null)), [desde, hasta]);
  return (
    <Modal abierto ancho="xl" alCerrar={alCerrar} titulo={`Comparar versiones · ${titulo(instrumento)}`} pie={<Boton onClick={alCerrar}>Cerrar</Boton>}>
      <div className="flex flex-col gap-4">
        <div className="grid gap-3 sm:grid-cols-2">
          {[["Desde", desde, setDesde], ["Hasta", hasta, setHasta]].map(([etiqueta, valor, cambiar]) => (
            <Campo key={etiqueta as string} etiqueta={etiqueta as string}>
              <Selector value={valor as string} onChange={(e) => (cambiar as (v: string) => void)(e.target.value)}>
                {opciones.map((v) => <option key={v.id} value={v.id}>v{v.version} · {v.estado}</option>)}
              </Selector>
            </Campo>
          ))}
        </div>
        {desde === hasta ? <Nota tono="aviso">Elija dos versiones distintas.</Nota> : !c.datos ? <Cargando /> : (
          <>
            <p className="text-[13px] text-texto-2">
              <b>{numero(c.datos.nuevas.length)}</b> nuevas · <b>{numero(c.datos.retiradas.length)}</b> retiradas · <b>{numero(c.datos.modificadas.length)}</b> modificadas
            </p>
            {!c.datos.nuevas.length && !c.datos.retiradas.length && !c.datos.modificadas.length && <Nota tono="ok">Las dos versiones dicen lo mismo.</Nota>}
            <Tabla className="rounded-xl border border-line">
              <thead><tr><th>Cambio</th><th>Código</th><th>Serie / subserie</th><th>Detalle</th></tr></thead>
              <tbody>
                {c.datos.nuevas.map((e) => <tr key={`n-${e.codigo}`}><td><Insignia tono="ok">Nueva</Insignia></td><td><Codigo>{e.codigo}</Codigo></td><td>{e.nombre}</td><td className="text-[12.5px]">{e.disposicion ? `Disposición ${e.disposicion}` : ""}</td></tr>)}
                {c.datos.retiradas.map((e) => <tr key={`r-${e.codigo}`}><td><Insignia tono="critico">Retirada</Insignia></td><td><Codigo>{e.codigo}</Codigo></td><td>{e.nombre}</td><td /></tr>)}
                {c.datos.modificadas.map((e) => (
                  <tr key={`m-${e.codigo}`}>
                    <td><Insignia tono="aviso">Modificada</Insignia></td><td><Codigo>{e.codigo}</Codigo></td><td>{e.nombre}</td>
                    <td className="text-[12.5px]">{Object.entries(e.cambios).map(([campo, [antes, despues]]) => <div key={campo}><b>{CAMPO[campo] ?? campo}:</b> {texto(antes)} → {texto(despues)}</div>)}</td>
                  </tr>
                ))}
              </tbody>
            </Tabla>
          </>
        )}
      </div>
    </Modal>
  );
}
