"use client";

import { AlertTriangle, CheckCircle2, Eye, FileQuestion, FolderOpen, FolderUp, Images, RotateCcw, ScanLine, Settings2, ShieldCheck, Upload } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";

import { ModalMotivo } from "@/components/ui/acciones";
import { useAvisos } from "@/components/ui/avisos";
import { Boton, CajaError, Cargando, Codigo, Insignia, Modal, Nota, Pestanas, Progreso, Tabla, Vacio } from "@/components/ui/basicos";
import { Area, Campo, Casilla, Entrada, Interruptor, Selector } from "@/components/ui/campos";
import { abrirArchivo, api, apiSubir } from "@/lib/api";
import { cn, fechaHora, numero } from "@/lib/formato";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { EstadoRecurso, PerfilDigitalizacion, Proyecto, Recurso, ReporteCarga, ResumenDigitalizacion, RespuestaPerfil, Unidad, UnidadAvance } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

const ESTADOS: Record<EstadoRecurso, { texto: string; tono: "ok" | "aviso" | "critico" | "info" | "neutro" | "naranja" }> = {
  aprobado: { texto: "Aprobado", tono: "ok" },
  en_revision: { texto: "Por revisar", tono: "aviso" },
  rechazado: { texto: "Rechazado", tono: "critico" },
  recaptura: { texto: "Recaptura pedida", tono: "naranja" },
  reemplazado: { texto: "Reemplazado", tono: "neutro" },
  sin_identificar: { texto: "Sin identificar", tono: "info" },
};
const ESTADO_UNIDAD: Record<UnidadAvance["estado"], { texto: string; tono: "ok" | "aviso" | "critico" | "neutro" }> = {
  sin_imagenes: { texto: "Sin imágenes", tono: "neutro" },
  en_revision: { texto: "Por revisar", tono: "aviso" },
  recaptura: { texto: "Recaptura", tono: "critico" },
  aprobada: { texto: "Aprobada", tono: "ok" },
};
const ACEPTADOS = /\.(pdf|tiff?|jpe?g|png)$/i;
const MAX_ARCHIVOS = 40;
const MAX_BYTES = 80 * 1024 * 1024;

type Bandeja = "en_revision" | "rechazado" | "sin_identificar" | "recaptura" | "aprobado" | "expedientes";

/** Reparte los archivos en envíos pequeños: una carpeta de miles de imágenes no viaja en una sola petición. */
function enLotes(archivos: File[]): File[][] {
  const lotes: File[][] = [];
  let actual: File[] = [];
  let peso = 0;
  for (const a of archivos) {
    if (actual.length && (actual.length >= MAX_ARCHIVOS || peso + a.size > MAX_BYTES)) {
      lotes.push(actual);
      actual = [];
      peso = 0;
    }
    actual.push(a);
    peso += a.size;
  }
  if (actual.length) lotes.push(actual);
  return lotes;
}

const rutaDe = (a: File) => (a as File & { webkitRelativePath?: string }).webkitRelativePath || a.name;

export function Digitalizacion({ proyecto }: { proyecto: Proyecto }) {
  const { puede } = useSesion();
  const base = `/proyectos/${proyecto.id}/digitalizacion`;
  const resumen = useDatos(() => api<ResumenDigitalizacion>(`${base}/resumen`), [base]);
  const perfil = useDatos(() => api<RespuestaPerfil>(`${base}/perfil`), [base]);
  const [bandeja, setBandeja] = useState<Bandeja>("en_revision");
  const [recarga, setRecarga] = useState(0);
  const [configurar, setConfigurar] = useState(false);
  const abierto = proyecto.estado !== "cerrado";
  const refrescar = () => (void resumen.recargar(), setRecarga((n) => n + 1));
  const r = resumen.datos;
  const pe = r?.por_estado ?? {};

  return (
    <div className="flex flex-col gap-5 p-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Cifra icono={<FolderOpen />} tono="bg-marca-suave text-marca" valor={numero(r?.unidades ?? 0)} etiqueta="Expedientes del FUID" />
        <Cifra icono={<Images />} tono="bg-motor-suave text-motor" valor={numero(r?.unidades_con_imagenes ?? 0)} etiqueta="Con imágenes" barra={r?.unidades ? (100 * r.unidades_con_imagenes) / r.unidades : 0} />
        <Cifra icono={<CheckCircle2 />} tono="bg-ok-suave text-ok" valor={numero(r?.unidades_aprobadas ?? 0)} etiqueta="Aprobados" />
        <Cifra icono={<AlertTriangle />} tono="bg-aviso-suave text-aviso" valor={numero((pe.en_revision ?? 0) + (pe.rechazado ?? 0))} etiqueta="Archivos con alertas" />
        <Cifra icono={<ScanLine />} tono="bg-neutro-suave text-neutro" valor={numero(r?.imagenes ?? 0)} etiqueta="Imágenes recibidas" />
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-canvas px-4 py-3">
        <Settings2 className="size-4 text-texto-3" />
        <span className="text-[13px] text-texto-2">
          Perfil de digitalización {perfil.datos?.version ? <b>v{perfil.datos.version}</b> : <b>por defecto</b>}
          {perfil.datos && ` · ${perfil.datos.perfil.formatos.join(", ")} · ${perfil.datos.perfil.dpi_minimo ? `mínimo ${perfil.datos.perfil.dpi_minimo} ppp` : "resolución sin mínimo"} · ${perfil.datos.perfil.detectar_blancos ? "detecta blancos" : "sin detección de blancos"}`}
        </span>
        <span className="flex-1" />
        {puede(PERMISOS.proyectos) && abierto && <Boton tamano="sm" icono={<Settings2 />} onClick={() => setConfigurar(true)}>Configurar</Boton>}
      </div>

      {puede(PERMISOS.capturar) && abierto && (
        <Carga base={base} hayInventario={!!r?.unidades} alTerminar={refrescar} />
      )}

      <div>
        <Pestanas
          valor={bandeja}
          alCambiar={setBandeja}
          opciones={[
            { valor: "en_revision", etiqueta: `Por revisar (${pe.en_revision ?? 0})` },
            { valor: "rechazado", etiqueta: `Rechazados (${pe.rechazado ?? 0})` },
            { valor: "sin_identificar", etiqueta: `Sin identificar (${pe.sin_identificar ?? 0})` },
            { valor: "recaptura", etiqueta: `Recaptura pedida (${pe.recaptura ?? 0})` },
            { valor: "aprobado", etiqueta: `Aprobados (${pe.aprobado ?? 0})` },
            { valor: "expedientes", etiqueta: "Por expediente" },
          ]}
        />
        {bandeja === "expedientes" ? (
          <Expedientes base={base} recarga={recarga} />
        ) : (
          <ListaRecursos base={base} proyectoId={proyecto.id} estado={bandeja} recarga={recarga} puedeDecidir={puede(PERMISOS.calidad) && abierto} alCambiar={refrescar} />
        )}
      </div>

      {configurar && perfil.datos && (
        <ModalPerfil base={base} actual={perfil.datos} alCerrar={() => setConfigurar(false)} alGuardar={() => (setConfigurar(false), void perfil.recargar())} />
      )}
    </div>
  );
}

function Cifra({ icono, tono, valor, etiqueta, barra }: { icono: ReactNode; tono: string; valor: string; etiqueta: string; barra?: number }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-line bg-surface p-3.5 shadow-xs">
      <span className={cn("grid size-10 shrink-0 place-items-center rounded-xl [&_svg]:size-5", tono)}>{icono}</span>
      <span className="min-w-0 flex-1">
        <span className="tabular block text-[22px] leading-none font-bold text-titulo">{valor}</span>
        <span className="mt-1 block truncate text-[12.5px] text-texto-2">{etiqueta}</span>
        {barra !== undefined && <Progreso valor={barra} tono="motor" className="mt-1.5" />}
      </span>
    </div>
  );
}

/** Cargar una carpeta completa (cada subcarpeta o cada archivo es un expediente) o archivos sueltos. */
function Carga({ base, hayInventario, alTerminar }: { base: string; hayInventario: boolean; alTerminar: () => void }) {
  const avisos = useAvisos();
  const carpeta = useRef<HTMLInputElement>(null);
  const sueltos = useRef<HTMLInputElement>(null);
  const [progreso, setProgreso] = useState<{ hechos: number; total: number } | null>(null);
  const [reporte, setReporte] = useState<ReporteCarga[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [verDetalle, setVerDetalle] = useState(false);

  useEffect(() => {
    // Selección de carpeta completa: atributo no estándar que todos los navegadores de escritorio admiten.
    carpeta.current?.setAttribute("webkitdirectory", "");
    carpeta.current?.setAttribute("directory", "");
  }, []);

  async function subir(lista: FileList | null) {
    if (!lista?.length) return;
    const archivos = Array.from(lista).filter((a) => ACEPTADOS.test(a.name));
    const ignorados = lista.length - archivos.length;
    setReporte(null);
    setError(null);
    if (!archivos.length) return setError("La carpeta no tiene PDF ni imágenes (TIFF, JPG o PNG).");
    const lotes = enLotes(archivos);
    const acumulado: ReporteCarga[] = [];
    setProgreso({ hechos: 0, total: archivos.length });
    try {
      for (const lote of lotes) {
        const datos = new FormData();
        for (const a of lote) {
          datos.append("archivos", a, a.name);
          datos.append("rutas_relativas", rutaDe(a));
        }
        acumulado.push(...(await apiSubir<ReporteCarga[]>(`${base}/archivos`, datos)));
        setProgreso({ hechos: acumulado.length, total: archivos.length });
      }
      setReporte(acumulado);
      const recibidos = acumulado.filter((x) => x.resultado === "recibido").length;
      avisos.exito(`${recibidos} de ${archivos.length} archivos recibidos${ignorados ? ` · ${ignorados} omitidos por no ser PDF ni imagen` : ""}.`);
    } catch (e) {
      setReporte(acumulado.length ? acumulado : null);
      setError(`${(e as Error).message} (se alcanzaron a recibir ${acumulado.length} de ${archivos.length}).`);
    } finally {
      setProgreso(null);
      if (carpeta.current) carpeta.current.value = "";
      if (sueltos.current) sueltos.current.value = "";
      alTerminar();
    }
  }

  const cuenta = (f: (x: ReporteCarga) => boolean) => reporte?.filter(f).length ?? 0;

  return (
    <div className="rounded-xl border-2 border-dashed border-marca-borde bg-marca-suave/30 p-5">
      <div className="flex flex-wrap items-center gap-4">
        <span className="grid size-12 place-items-center rounded-xl bg-marca text-white"><FolderUp className="size-6" /></span>
        <div className="min-w-0 flex-1 text-[13px] text-texto-2">
          <p className="text-[15px] font-semibold text-titulo">Cargar lo digitalizado</p>
          <p>Escoja la carpeta de la entrega. ARCA reconoce cada expediente por el nombre del archivo (<Codigo>CP-00374.pdf</Codigo>, <Codigo>CARPETA_00374-2.pdf</Codigo>) o por su subcarpeta (<Codigo>CP-00374/0001.tif</Codigo>), ordena las páginas, descarta duplicados y revisa la calidad.</p>
        </div>
        <input ref={carpeta} type="file" multiple hidden onChange={(e) => subir(e.target.files)} />
        <input ref={sueltos} type="file" multiple hidden accept=".pdf,.tif,.tiff,.jpg,.jpeg,.png" onChange={(e) => subir(e.target.files)} />
        <div className="flex flex-wrap gap-2">
          <Boton variante="primario" icono={<FolderUp />} disabled={!!progreso || !hayInventario} onClick={() => carpeta.current?.click()}>Cargar carpeta</Boton>
          <Boton icono={<Upload />} disabled={!!progreso || !hayInventario} onClick={() => sueltos.current?.click()}>Archivos sueltos</Boton>
        </div>
      </div>
      {!hayInventario && <div className="mt-3"><Nota tono="aviso">Primero integre el FUID en la pestaña Inventario: sin inventario no hay con qué reconocer los expedientes.</Nota></div>}
      {progreso && (
        <div className="mt-4">
          <p className="mb-1 text-[12.5px] text-texto-2">Recibiendo y revisando… {numero(progreso.hechos)} de {numero(progreso.total)}</p>
          <Progreso valor={(100 * progreso.hechos) / progreso.total} />
        </div>
      )}
      {error && <div className="mt-3"><CajaError mensaje={error} /></div>}
      {reporte && (
        <div className="mt-4 rounded-lg border border-line bg-surface p-3.5">
          <div className="flex flex-wrap gap-2">
            <Insignia tono="ok">{cuenta((x) => x.estado === "aprobado")} aprobados</Insignia>
            <Insignia tono="aviso">{cuenta((x) => x.estado === "en_revision")} por revisar</Insignia>
            <Insignia tono="critico">{cuenta((x) => x.estado === "rechazado" || x.resultado === "rechazado")} rechazados</Insignia>
            <Insignia tono="info">{cuenta((x) => x.estado === "sin_identificar")} sin identificar</Insignia>
            <Insignia tono="neutro">{cuenta((x) => x.resultado === "duplicado")} duplicados</Insignia>
            <Insignia tono="neutro">{cuenta((x) => x.resultado === "ignorado")} ignorados</Insignia>
            <button className="ml-auto text-[12.5px] font-semibold text-marca hover:underline" onClick={() => setVerDetalle(!verDetalle)}>{verDetalle ? "Ocultar detalle" : "Ver detalle"}</button>
          </div>
          {verDetalle && (
            <ul className="mt-3 max-h-64 overflow-y-auto text-[12.5px]">
              {reporte.map((x, i) => (
                <li key={i} className="flex gap-2 border-t border-line py-1.5">
                  <span className="min-w-0 flex-1 truncate font-mono text-[12px]" title={x.ruta}>{x.ruta}</span>
                  <span className="shrink-0 text-texto-3">{x.unidad ?? ""}</span>
                  <span className="shrink-0">{x.estado ? ESTADOS[x.estado].texto : x.detalle}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function ListaRecursos({ base, proyectoId, estado, recarga, puedeDecidir, alCambiar }: { base: string; proyectoId: string; estado: EstadoRecurso; recarga: number; puedeDecidir: boolean; alCambiar: () => void }) {
  const avisos = useAvisos();
  const [desde, setDesde] = useState(0);
  const datos = useDatos(() => api<{ total: number; recursos: Recurso[] }>(`${base}/archivos`, { consulta: { estado, desplazamiento: desde, limite: 50 } }), [base, estado, desde, recarga]);
  const [decision, setDecision] = useState<{ recurso: Recurso; tipo: "aprobar" | "recaptura" } | null>(null);
  const [asignar, setAsignar] = useState<Recurso | null>(null);
  useEffect(() => setDesde(0), [estado]);

  if (datos.cargando && !datos.datos) return <Cargando />;
  if (datos.error) return <div className="pt-4"><CajaError mensaje={datos.error} reintentar={datos.recargar} /></div>;
  if (!datos.datos?.recursos.length) {
    const vacios: Record<string, string> = { en_revision: "Nada por revisar.", rechazado: "Ningún archivo rechazado.", sin_identificar: "Todos los archivos se reconocieron.", recaptura: "No hay recapturas pendientes.", aprobado: "Todavía no hay archivos aprobados." };
    return <Vacio icono={estado === "aprobado" ? <ShieldCheck /> : <CheckCircle2 />} titulo={vacios[estado] ?? "Sin archivos"} />;
  }
  return (
    <>
      <Tabla className="mt-2">
        <thead><tr><th>Archivo</th><th>Expediente</th><th>Páginas</th><th>Ficha técnica</th><th>Hallazgos</th><th>Estado</th><th className="w-56" /></tr></thead>
        <tbody>
          {datos.datos.recursos.map((r) => (
            <tr key={r.id}>
              <td className="max-w-64"><span className="block truncate font-mono text-[12px]" title={r.ruta_original}>{r.ruta_original}</span><span className="block text-[11.5px] text-texto-3">{fechaHora(r.creado_en)}{r.reemplaza_id ? " · recaptura" : ""}</span></td>
              <td>{r.unidad_identificador ? <Codigo>{r.unidad_identificador}</Codigo> : <span className="text-texto-3">—</span>}{r.parte > 0 && <span className="block text-[11.5px] text-texto-3">parte {r.parte}</span>}{r.pagina != null && <span className="block text-[11.5px] text-texto-3">página {r.pagina}</span>}</td>
              <td className="tabular">{r.paginas}</td>
              <td className="text-[12px] text-texto-2">{r.ficha.error ? "Ilegible" : `${r.ficha.dpi_minimo ? `${r.ficha.dpi_minimo} ppp` : "ppp sin declarar"} · ${["bitonal", "grises", "color"][r.ficha.color ?? 0]}`}</td>
              <td className="max-w-72">{r.hallazgos.length ? r.hallazgos.map((h, i) => <span key={i} className={cn("block text-[12.5px]", h.gravedad === "error" ? "text-critico" : "text-aviso")}>{h.gravedad === "error" ? "✕" : "!"} {h.mensaje}</span>) : <span className="text-[12.5px] text-ok">✓ Sin hallazgos</span>}{r.motivo_decision && <span className="block text-[12px] text-texto-3">Decisión: {r.motivo_decision}</span>}</td>
              <td><Insignia tono={ESTADOS[r.estado].tono} punto>{ESTADOS[r.estado].texto}</Insignia></td>
              <td className="whitespace-nowrap">
                <Boton tamano="sm" variante="fantasma" icono={<Eye />} onClick={() => abrirArchivo(`${base}/archivos/${r.id}/contenido`).catch((e) => avisos.error((e as Error).message))}>Ver</Boton>
                {puedeDecidir && r.estado === "sin_identificar" && <Boton tamano="sm" variante="fantasma" icono={<FileQuestion />} onClick={() => setAsignar(r)}>Asignar</Boton>}
                {puedeDecidir && (r.estado === "en_revision" || r.estado === "rechazado") && (
                  <>
                    {r.estado === "en_revision" && <Boton tamano="sm" variante="fantasma" icono={<CheckCircle2 />} onClick={() => setDecision({ recurso: r, tipo: "aprobar" })}>Aprobar</Boton>}
                    <Boton tamano="sm" variante="fantasma" icono={<RotateCcw />} onClick={() => setDecision({ recurso: r, tipo: "recaptura" })}>Recaptura</Boton>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </Tabla>
      <div className="flex items-center justify-between border-t border-line px-1 pt-3 text-[12.5px] text-texto-3">
        <span>{numero(datos.datos.total)} archivos</span>
        <span className="flex gap-2">
          <Boton tamano="sm" disabled={desde === 0} onClick={() => setDesde(Math.max(0, desde - 50))}>Anteriores</Boton>
          <Boton tamano="sm" disabled={desde + 50 >= datos.datos.total} onClick={() => setDesde(desde + 50)}>Siguientes</Boton>
        </span>
      </div>
      <ModalMotivo
        abierto={!!decision}
        titulo={decision?.tipo === "aprobar" ? "Aprobar a pesar de las alertas" : "Pedir recaptura"}
        descripcion={decision?.tipo === "aprobar" ? "Usted confirma que la imagen sirve aunque las reglas la señalaron. Quien la cargó no puede aprobarla." : "El archivo queda como evidencia. Cuando llegue la nueva digitalización de esta misma parte o página, la reemplaza."}
        boton={decision?.tipo === "aprobar" ? "Aprobar" : "Pedir recaptura"}
        peligro={decision?.tipo === "recaptura"}
        alCerrar={() => setDecision(null)}
        alConfirmar={async (motivo) => {
          await api(`${base}/archivos/${decision!.recurso.id}/decidir`, { metodo: "POST", cuerpo: { decision: decision!.tipo, motivo } });
          avisos.exito(decision!.tipo === "aprobar" ? "Archivo aprobado." : "Recaptura pedida.");
          alCambiar();
        }}
      />
      {asignar && <ModalAsignar base={base} proyectoId={proyectoId} recurso={asignar} alCerrar={() => setAsignar(null)} alGuardar={() => (setAsignar(null), avisos.exito("Archivo asignado al expediente."), alCambiar())} />}
    </>
  );
}

function ModalAsignar({ base, proyectoId, recurso, alCerrar, alGuardar }: { base: string; proyectoId: string; recurso: Recurso; alCerrar: () => void; alGuardar: () => void }) {
  const [texto, setTexto] = useState("");
  const [buscar, setBuscar] = useState("");
  const [unidad, setUnidad] = useState<string>("");
  const [parte, setParte] = useState(String(recurso.parte || ""));
  const [pagina, setPagina] = useState(recurso.pagina != null ? String(recurso.pagina) : "");
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const unidades = useDatos(() => api<{ total: number; unidades: Unidad[] }>(`/proyectos/${proyectoId}/inventario/unidades`, { consulta: { q: buscar, limite: 30 } }), [proyectoId, buscar]);
  return (
    <Modal
      abierto
      ancho="lg"
      alCerrar={alCerrar}
      titulo="Asignar a un expediente"
      descripcion={<span className="font-mono text-[12px]">{recurso.ruta_original}</span>}
      pie={
        <>
          <Boton onClick={alCerrar}>Cancelar</Boton>
          <Boton
            variante="primario"
            cargando={enviando}
            disabled={!unidad || motivo.trim().length < 5}
            onClick={async () => {
              setEnviando(true);
              setError(null);
              try {
                await api(`${base}/archivos/${recurso.id}/asignar`, { metodo: "POST", cuerpo: { unidad_id: unidad, parte: Number(parte || 0), pagina: pagina ? Number(pagina) : null, motivo: motivo.trim() } });
                alGuardar();
              } catch (e) {
                setError((e as Error).message);
                setEnviando(false);
              }
            }}
          >
            Asignar
          </Boton>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <form className="flex gap-2" onSubmit={(e) => (e.preventDefault(), setBuscar(texto))}>
          <Entrada value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Buscar por identificador o nombre" autoFocus />
          <Boton type="submit">Buscar</Boton>
        </form>
        <div className="max-h-56 overflow-y-auto rounded-lg border border-line">
          {unidades.datos?.unidades.map((u) => (
            <label key={u.id} className={cn("flex cursor-pointer items-center gap-3 border-b border-line px-3 py-2 text-[13px] last:border-b-0", unidad === u.id && "bg-marca-suave")}>
              <input type="radio" name="unidad" checked={unidad === u.id} onChange={() => setUnidad(u.id)} className="accent-marca" />
              <Codigo>{u.identificador}</Codigo>
              <span className="truncate">{u.nombre}</span>
            </label>
          ))}
          {!unidades.datos?.unidades.length && <p className="px-3 py-4 text-center text-[13px] text-texto-3">Sin resultados.</p>}
        </div>
        <div className="grid grid-cols-2 gap-3">
          {recurso.modalidad === "pdf" ? (
            <Campo etiqueta="Parte" ayuda="0 si el expediente viene completo"><Entrada type="number" min={0} value={parte} onChange={(e) => setParte(e.target.value)} /></Campo>
          ) : (
            <Campo etiqueta="Página"><Entrada type="number" min={0} value={pagina} onChange={(e) => setPagina(e.target.value)} /></Campo>
          )}
        </div>
        <Campo etiqueta="Motivo" requerido ayuda="Ej.: identificado por el rótulo de la carpeta."><Area value={motivo} onChange={(e) => setMotivo(e.target.value)} /></Campo>
        {error && <CajaError mensaje={error} />}
      </div>
    </Modal>
  );
}

function Expedientes({ base, recarga }: { base: string; recarga: number }) {
  const [filtro, setFiltro] = useState("");
  const [desde, setDesde] = useState(0);
  const datos = useDatos(() => api<{ total: number; unidades: UnidadAvance[] }>(`${base}/unidades`, { consulta: { filtro, desplazamiento: desde, limite: 50 } }), [base, filtro, desde, recarga]);
  return (
    <div className="pt-3">
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <Campo etiqueta="Mostrar" className="w-64">
          <Selector value={filtro} onChange={(e) => (setDesde(0), setFiltro(e.target.value))}>
            <option value="">Todos los expedientes</option>
            <option value="con_alertas">Con alertas de completitud</option>
            <option value="sin_imagenes">Sin imágenes todavía</option>
            <option value="en_revision">Por revisar</option>
            <option value="recaptura">Con recaptura</option>
            <option value="aprobada">Aprobados</option>
          </Selector>
        </Campo>
        <p className="max-w-xl text-[12.5px] text-texto-3">La completitud se revisa por expediente: partes o páginas que faltan e imágenes contra los folios del FUID. Lo que hoy falta puede llegar en la siguiente carga.</p>
      </div>
      {datos.cargando && !datos.datos ? <Cargando /> : !datos.datos?.unidades.length ? <Vacio icono={<FolderOpen />} titulo="Ningún expediente en este filtro" /> : (
        <>
          <Tabla>
            <thead><tr><th>Expediente</th><th>Nombre</th><th>Folios FUID</th><th>Imágenes</th><th>Alertas</th><th>Estado</th></tr></thead>
            <tbody>
              {datos.datos.unidades.map((u) => (
                <tr key={u.id}>
                  <td><Codigo>{u.identificador}</Codigo></td>
                  <td className="max-w-72"><span className="line-clamp-2">{u.nombre}</span></td>
                  <td className="tabular">{u.folios ?? "—"}</td>
                  <td className="tabular">{numero(u.imagenes)}<span className="block text-[11.5px] text-texto-3">{u.archivos} archivos</span></td>
                  <td className="max-w-72">{u.alertas.length ? u.alertas.map((a, i) => <span key={i} className="block text-[12.5px] text-aviso">! {a.mensaje}</span>) : <span className="text-texto-3">—</span>}</td>
                  <td><Insignia tono={ESTADO_UNIDAD[u.estado].tono} punto>{ESTADO_UNIDAD[u.estado].texto}</Insignia></td>
                </tr>
              ))}
            </tbody>
          </Tabla>
          <div className="flex justify-end gap-2 pt-3">
            <Boton tamano="sm" disabled={desde === 0} onClick={() => setDesde(Math.max(0, desde - 50))}>Anteriores</Boton>
            <Boton tamano="sm" disabled={desde + 50 >= datos.datos.total} onClick={() => setDesde(desde + 50)}>Siguientes</Boton>
          </div>
        </>
      )}
    </div>
  );
}

function ModalPerfil({ base, actual, alCerrar, alGuardar }: { base: string; actual: RespuestaPerfil; alCerrar: () => void; alGuardar: () => void }) {
  const avisos = useAvisos();
  const [p, setP] = useState<PerfilDigitalizacion>(actual.perfil);
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const alternar = <K extends "modalidades" | "formatos" | "rechazo_automatico">(campo: K, valor: string, activo: boolean) =>
    setP((x) => ({ ...x, [campo]: activo ? [...(x[campo] as string[]), valor] : (x[campo] as string[]).filter((v) => v !== valor) }));
  return (
    <Modal
      abierto
      ancho="xl"
      alCerrar={alCerrar}
      titulo="Perfil de digitalización del proyecto"
      descripcion={`Rige la recepción y el control de calidad. ${actual.version ? `Versión vigente: ${actual.version}.` : "Hoy se usan los valores por defecto."} Cada cambio queda como versión nueva y cada archivo anota la versión que se le aplicó.`}
      pie={
        <>
          <Boton onClick={() => setP(actual.por_defecto)} variante="fantasma">Valores por defecto</Boton>
          <span className="flex-1" />
          <Boton onClick={alCerrar}>Cancelar</Boton>
          <Boton
            variante="primario"
            cargando={enviando}
            disabled={motivo.trim().length < 5}
            onClick={async () => {
              setEnviando(true);
              setError(null);
              try {
                await api(`${base}/perfil`, { metodo: "PUT", cuerpo: { perfil: p, motivo: motivo.trim() } });
                avisos.exito("Perfil publicado. Aplica a lo que se cargue desde ahora.");
                alGuardar();
              } catch (e) {
                setError((e as Error).message);
                setEnviando(false);
              }
            }}
          >
            Publicar versión
          </Boton>
        </>
      }
    >
      <div className="grid gap-6 md:grid-cols-2">
        <section className="flex flex-col gap-4">
          <p className="text-[13px] font-semibold text-titulo">Entrega</p>
          <fieldset className="flex flex-col gap-1.5">
            <legend className="mb-1 text-[13px] font-medium text-texto-2">Formas de entrega admitidas</legend>
            <Casilla etiqueta="Un PDF por expediente (o por partes)" checked={p.modalidades.includes("pdf")} onChange={(e) => alternar("modalidades", "pdf", e.target.checked)} />
            <Casilla etiqueta="Una imagen por página (TIFF, JPG o PNG)" checked={p.modalidades.includes("imagenes")} onChange={(e) => alternar("modalidades", "imagenes", e.target.checked)} />
          </fieldset>
          <fieldset className="flex flex-wrap gap-x-5 gap-y-1.5">
            <legend className="mb-1 w-full text-[13px] font-medium text-texto-2">Formatos</legend>
            {["PDF", "TIFF", "JPEG", "PNG"].map((f) => <Casilla key={f} etiqueta={f} checked={p.formatos.includes(f)} onChange={(e) => alternar("formatos", f, e.target.checked)} />)}
          </fieldset>
          <Campo etiqueta="Cómo se reconoce el expediente" ayuda="Por el nombre del archivo, por la subcarpeta, o lo primero que funcione.">
            <Selector value={p.identificar_por} onChange={(e) => setP({ ...p, identificar_por: e.target.value as PerfilDigitalizacion["identificar_por"] })}>
              <option value="archivo_o_carpeta">Nombre del archivo o subcarpeta</option>
              <option value="archivo">Solo el nombre del archivo</option>
              <option value="carpeta">Solo la subcarpeta</option>
            </Selector>
          </Campo>
        </section>
        <section className="flex flex-col gap-4">
          <p className="text-[13px] font-semibold text-titulo">Calidad</p>
          <div className="grid grid-cols-2 gap-3">
            <Campo etiqueta="Resolución mínima (ppp)" ayuda="0 = se mide pero no se exige">
              <Entrada type="number" min={0} max={1200} value={p.dpi_minimo} onChange={(e) => setP({ ...p, dpi_minimo: Number(e.target.value || 0) })} />
            </Campo>
            <Campo etiqueta="Color mínimo">
              <Selector value={p.color_minimo} onChange={(e) => setP({ ...p, color_minimo: e.target.value as PerfilDigitalizacion["color_minimo"] })}>
                <option value="cualquiera">Cualquiera (incluso bitonal)</option>
                <option value="grises">Escala de grises</option>
                <option value="color">Color</option>
              </Selector>
            </Campo>
          </div>
          <div className="flex items-center justify-between gap-3 rounded-lg border border-line px-3 py-2.5">
            <span className="text-[13px] text-texto-2">Detectar páginas en blanco</span>
            <Interruptor activo={p.detectar_blancos} alCambiar={(v) => setP({ ...p, detectar_blancos: v })} etiqueta="Detectar páginas en blanco" />
          </div>
          {p.detectar_blancos && (
            <Campo etiqueta={`Umbral de blanco: ${(p.umbral_blanco * 100).toFixed(1)} %`} ayuda="Proporción de píxeles casi blancos para considerar la imagen en blanco.">
              <input type="range" min={0.9} max={1} step={0.001} value={p.umbral_blanco} onChange={(e) => setP({ ...p, umbral_blanco: Number(e.target.value) })} className="accent-marca" />
            </Campo>
          )}
          <div className="flex items-center justify-between gap-3 rounded-lg border border-line px-3 py-2.5">
            <span className="text-[13px] text-texto-2">Comparar imágenes con los folios del FUID</span>
            <Interruptor activo={p.comparar_folios} alCambiar={(v) => setP({ ...p, comparar_folios: v })} etiqueta="Comparar con folios" />
          </div>
        </section>
        <fieldset className="md:col-span-2">
          <legend className="mb-1 text-[13px] font-semibold text-titulo">Rechazo automático</legend>
          <p className="mb-2 text-[12.5px] text-texto-3">Lo marcado se rechaza sin intervención y pide recaptura. Lo demás pasa a la bandeja de revisión para que decida una persona.</p>
          <div className="grid gap-1.5 sm:grid-cols-2">
            {Object.entries(actual.hallazgos).filter(([c]) => !["salto_secuencia", "folios_no_coinciden"].includes(c)).map(([codigo, texto]) => (
              <Casilla key={codigo} etiqueta={texto} checked={p.rechazo_automatico.includes(codigo)} onChange={(e) => alternar("rechazo_automatico", codigo, e.target.checked)} />
            ))}
          </div>
        </fieldset>
        <Campo etiqueta="Motivo del cambio" requerido className="md:col-span-2" ayuda="Ej.: parámetros de digitalización del anexo técnico del contrato.">
          <Area value={motivo} onChange={(e) => setMotivo(e.target.value)} />
        </Campo>
        {error && <div className="md:col-span-2"><CajaError mensaje={error} /></div>}
      </div>
    </Modal>
  );
}
