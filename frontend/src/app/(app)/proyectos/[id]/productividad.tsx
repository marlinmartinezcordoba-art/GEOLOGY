"use client";

import { BarChart3, Boxes, Check, ClipboardPen, Copy, Download, FileSpreadsheet, KeyRound, RefreshCw, Settings2, Upload } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";

import { ClaveTemporal, ModalMotivo } from "@/components/ui/acciones";
import { useAvisos } from "@/components/ui/avisos";
import { Boton, CajaError, Cargando, Codigo, Insignia, Nota, Pestanas, Progreso, Tabla, Vacio } from "@/components/ui/basicos";
import { Area, Campo, Entrada, Selector } from "@/components/ui/campos";
import { api, apiSubir, sesionGuardada } from "@/lib/api";
import { cn, fechaHora, numero } from "@/lib/formato";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { Proyecto } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

type FilaTablero = { Frente: string; Nombre: string; Sede: string; Unidad: string; Volumen_Total: number; Acumulado: number; Pct_Avance: number; Meta_Diaria: number; Producido_Fecha_Corte: number; Pct_Cumplimiento_Dia: number; Dias_Operativos_Restantes: number; Ritmo_Requerido_Dia: number; Estado: string };
type FilaCalidad = { Frente: string; Lotes_Inspeccionados: number; Lotes_Rechazados: number; Pct_Rechazo: number; Defectos_Criticos: number; Novedades_Abiertas: number; Novedades_Totales: number; Cantidad_Aceptada: number; Pct_Volumen_Aceptado: number };
type DatosTablero = { fecha_corte: string; frentes: FilaTablero[]; calidad: FilaCalidad[]; por_turno: { Frente: string; turnos: { Turno: string; Producido: number; Meta: number }[] }[]; turnos: string[]; calculado_en: string };
type Caja = { Caja: string; Cod_Frente: string | null; Lote: string; Sede: string; Ubicacion: string; Carpetas: number | null; Estado: "procesada" | "en_proceso" | "pendiente"; Actividades_Hechas: string[]; Actividades_Pendientes: string[]; Ultima_Fecha: string | null };
type ResumenCajas = { Cod_Frente: string; total: number; procesada: number; en_proceso: number; pendiente: number; carpetas: number; carpetas_procesadas: number };
type Diseno = { tablas: { nombre: string; hoja: string; registro: boolean; columnas: { nombre: string; tipo: string; obligatoria: boolean }[] }[]; listas: Record<string, string[] | Record<string, string>>; tablas_disponibles: string[] };
type Clave = { id: string; nombre: string; prefijo: string; activa: boolean; creado_en: string; ultimo_uso: string | null };

const TONO_ESTADO: Record<string, "ok" | "aviso" | "critico" | "info" | "neutro"> = { Terminado: "info", "En ritmo": "ok", Atención: "aviso", "En riesgo": "critico", "Por iniciar": "neutro" };
const TONO_CAJA = { procesada: "ok", en_proceso: "aviso", pendiente: "neutro" } as const;
const NOMBRE_CAJA = { procesada: "Procesada", en_proceso: "En proceso", pendiente: "Pendiente" };
const pct = (v: number) => `${(v * 100).toLocaleString("es-CO", { maximumFractionDigits: 1 })} %`;

type Vista = "tablero" | "cajas" | "registrar" | "configurar" | "powerbi";

/** M24 · Productividad del proyecto con el diseño de Power BI: tablero en tiempo real, cajas, registro diario y conexión. */
export function Productividad({ proyecto }: { proyecto: Proyecto }) {
  const { puede } = useSesion();
  const base = `/proyectos/${proyecto.id}/productividad`;
  const [vista, setVista] = useState<Vista>("tablero");
  const [recarga, setRecarga] = useState(0);
  const refrescar = () => setRecarga((n) => n + 1);
  const opciones: { valor: Vista; etiqueta: ReactNode }[] = [
    { valor: "tablero", etiqueta: <span className="inline-flex items-center gap-1.5"><BarChart3 className="size-4" />Tablero</span> },
    { valor: "cajas", etiqueta: <span className="inline-flex items-center gap-1.5"><Boxes className="size-4" />Cajas</span> },
    ...(puede(PERMISOS.productividadRegistrar) ? [{ valor: "registrar" as const, etiqueta: <span className="inline-flex items-center gap-1.5"><ClipboardPen className="size-4" />Registrar</span> }] : []),
    ...(puede(PERMISOS.productividadConfigurar)
      ? [
          { valor: "configurar" as const, etiqueta: <span className="inline-flex items-center gap-1.5"><Settings2 className="size-4" />Configuración</span> },
          { valor: "powerbi" as const, etiqueta: <span className="inline-flex items-center gap-1.5"><KeyRound className="size-4" />Power BI</span> },
        ]
      : []),
  ];
  return (
    <div className="flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1"><Pestanas valor={vista} alCambiar={setVista} opciones={opciones} /></div>
      </div>
      {vista === "tablero" && <Tablero base={base} recarga={recarga} />}
      {vista === "cajas" && <Cajas base={base} recarga={recarga} puedeConfigurar={puede(PERMISOS.productividadConfigurar)} alCambiar={refrescar} />}
      {vista === "registrar" && <Registrar base={base} alGuardar={refrescar} />}
      {vista === "configurar" && <Configurar base={base} proyecto={proyecto} alCambiar={refrescar} />}
      {vista === "powerbi" && <PowerBI base={base} />}
    </div>
  );
}

function Tablero({ base, recarga }: { base: string; recarga: number }) {
  const [corte, setCorte] = useState("");
  const [vivo, setVivo] = useState(true);
  const datos = useDatos(() => api<DatosTablero>(`${base}/tablero`, { consulta: { fecha_corte: corte || undefined } }), [base, corte, recarga]);
  const { recargar } = datos;
  useEffect(() => {
    if (!vivo || corte) return;
    const t = setInterval(() => void recargar(), 30_000);
    return () => clearInterval(t);
  }, [vivo, corte, recargar]);
  const d = datos.datos;
  if (datos.cargando && !d) return <Cargando />;
  if (datos.error) return <CajaError mensaje={datos.error} reintentar={recargar} />;
  if (!d?.frentes.length) return <Vacio icono={<BarChart3 />} titulo="Sin frentes configurados" descripcion="Importe el libro con el diseño en Configuración (descargue antes la plantilla vacía) para ver el tablero." />;
  const riesgo = d.frentes.filter((f) => f.Estado === "En riesgo").length;
  return (
    <>
      <div className="flex flex-wrap items-end gap-3">
        <Campo etiqueta="Fecha de corte" ayuda={corte ? "Viendo un corte fijo" : "Última fecha con producción"} className="w-48">
          <Entrada type="date" value={corte || d.fecha_corte} onChange={(e) => setCorte(e.target.value)} />
        </Campo>
        {corte && <Boton tamano="sm" variante="fantasma" onClick={() => setCorte("")}>Volver al corte actual</Boton>}
        <span className="flex-1" />
        <span className="flex items-center gap-2 pb-2 text-[12.5px] text-texto-3">
          <span className={cn("size-2 rounded-full", vivo && !corte ? "animate-pulse bg-ok-vivo" : "bg-line-strong")} />
          {vivo && !corte ? "En vivo · se actualiza cada 30 s" : "En pausa"} · calculado {fechaHora(d.calculado_en)}
        </span>
        <Boton tamano="sm" icono={<RefreshCw />} onClick={() => void recargar()}>Actualizar</Boton>
        <Boton tamano="sm" variante="fantasma" onClick={() => setVivo(!vivo)}>{vivo ? "Pausar" : "En vivo"}</Boton>
      </div>
      {riesgo > 0 && <Nota tono="critico">{riesgo === 1 ? "1 frente está en riesgo" : `${riesgo} frentes están en riesgo`}: el ritmo requerido supera en más de 15 % la meta diaria.</Nota>}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {d.frentes.map((f) => (
          <div key={f.Frente} className="rounded-xl border border-line bg-surface p-4 shadow-xs">
            <div className="flex items-start gap-2">
              <span className="min-w-0 flex-1">
                <span className="block font-semibold text-titulo">{f.Frente} · {f.Nombre}</span>
                <span className="block text-[12px] text-texto-3">{f.Sede} · {f.Unidad}</span>
              </span>
              <Insignia tono={TONO_ESTADO[f.Estado] ?? "neutro"} punto>{f.Estado}</Insignia>
            </div>
            <div className="mt-3 flex items-end justify-between gap-2">
              <span className="tabular text-[26px] leading-none font-bold text-titulo">{pct(f.Pct_Avance)}</span>
              <span className="tabular text-right text-[12px] text-texto-3">{numero(f.Acumulado)} de {numero(f.Volumen_Total)}</span>
            </div>
            <Progreso valor={f.Pct_Avance * 100} tono={TONO_ESTADO[f.Estado] === "critico" ? "critico" : TONO_ESTADO[f.Estado] === "aviso" ? "aviso" : "ok"} className="mt-2" />
            <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-[12.5px]">
              <dt className="text-texto-3">Producido en el corte</dt><dd className="tabular text-right">{numero(f.Producido_Fecha_Corte)}</dd>
              <dt className="text-texto-3">Meta diaria</dt><dd className="tabular text-right">{numero(f.Meta_Diaria)} · {pct(f.Pct_Cumplimiento_Dia)}</dd>
              <dt className="text-texto-3">Días operativos restantes</dt><dd className="tabular text-right">{f.Dias_Operativos_Restantes}</dd>
              <dt className="text-texto-3">Ritmo requerido por día</dt><dd className="tabular text-right font-semibold">{numero(Math.ceil(f.Ritmo_Requerido_Dia))}</dd>
            </dl>
          </div>
        ))}
      </div>
      <div>
        <p className="mb-2 font-semibold text-titulo">Calidad, novedades y entregas (acumulado)</p>
        <Tabla className="rounded-xl border border-line">
          <thead><tr><th>Frente</th><th>Lotes inspeccionados</th><th>Rechazados</th><th>% rechazo</th><th>Críticos</th><th>Novedades abiertas</th><th>Novedades</th><th>Aceptado por la entidad</th><th>% del volumen</th></tr></thead>
          <tbody>
            {d.calidad.map((c) => (
              <tr key={c.Frente}>
                <td className="font-semibold">{c.Frente}</td><td className="tabular">{c.Lotes_Inspeccionados}</td><td className="tabular">{c.Lotes_Rechazados}</td>
                <td className={cn("tabular", c.Pct_Rechazo > 0 && "text-critico")}>{pct(c.Pct_Rechazo)}</td><td className="tabular">{c.Defectos_Criticos}</td>
                <td className={cn("tabular", c.Novedades_Abiertas > 0 && "font-semibold text-aviso")}>{c.Novedades_Abiertas}</td><td className="tabular">{c.Novedades_Totales}</td>
                <td className="tabular">{numero(c.Cantidad_Aceptada)}</td><td className="tabular">{pct(c.Pct_Volumen_Aceptado)}</td>
              </tr>
            ))}
          </tbody>
        </Tabla>
      </div>
      {d.turnos.length > 0 && (
        <div>
          <p className="mb-2 font-semibold text-titulo">Producción de la actividad de avance por turno · {d.fecha_corte}</p>
          <Tabla className="rounded-xl border border-line">
            <thead><tr><th>Frente</th>{d.turnos.map((t) => <th key={t}>Turno {t} · producido / meta</th>)}</tr></thead>
            <tbody>
              {d.por_turno.map((p) => (
                <tr key={p.Frente}>
                  <td className="font-semibold">{p.Frente}</td>
                  {p.turnos.map((t) => <td key={t.Turno} className={cn("tabular", t.Meta > 0 && t.Producido < t.Meta && "text-aviso")}>{numero(t.Producido)} / {numero(t.Meta)}</td>)}
                </tr>
              ))}
            </tbody>
          </Tabla>
        </div>
      )}
    </>
  );
}

function Cajas({ base, recarga, puedeConfigurar, alCambiar }: { base: string; recarga: number; puedeConfigurar: boolean; alCambiar: () => void }) {
  const avisos = useAvisos();
  const [estado, setEstado] = useState("pendiente");
  const [frente, setFrente] = useState("");
  const [texto, setTexto] = useState("");
  const [buscar, setBuscar] = useState("");
  const entrada = useRef<HTMLInputElement>(null);
  const [enviando, setEnviando] = useState(false);
  const datos = useDatos(() => api<{ cajas: Caja[]; resumen: ResumenCajas[] }>(`${base}/cajas`, { consulta: { estado: estado || undefined, frente: frente || undefined, q: buscar || undefined } }), [base, estado, frente, buscar, recarga]);
  const todas = useDatos(() => api<{ resumen: ResumenCajas[] }>(`${base}/cajas`), [base, recarga]);
  async function cargar(archivo: File) {
    setEnviando(true);
    try {
      const datosForm = new FormData();
      datosForm.append("archivo", archivo);
      const r = await apiSubir<{ nuevas: number; actualizadas: number; errores: string[] }>(`${base}/cajas/listado`, datosForm);
      avisos.exito(`${r.nuevas} cajas nuevas y ${r.actualizadas} actualizadas${r.errores.length ? ` · ${r.errores.length} filas con error` : ""}.`);
      r.errores.slice(0, 3).forEach((e) => avisos.error(e));
      alCambiar();
    } catch (e) {
      avisos.error((e as Error).message);
    } finally {
      setEnviando(false);
      if (entrada.current) entrada.current.value = "";
    }
  }
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-[13px] text-texto-2">La base de cajas que entregó la entidad. Cada registro de producción con <b>Caja desde</b> y <b>Caja hasta</b> marca las cajas que pasaron por esa actividad. Una caja está <b>procesada</b> cuando pasó por la actividad que mide el avance de su frente.</p>
        {puedeConfigurar && (
          <div className="flex flex-wrap gap-2">
            <input ref={entrada} type="file" accept=".xlsx,.csv" hidden onChange={(e) => e.target.files?.[0] && cargar(e.target.files[0])} />
            <Boton icono={<Upload />} cargando={enviando} onClick={() => entrada.current?.click()}>Cargar listado de cajas</Boton>
            <Boton icono={<FileSpreadsheet />} onClick={async () => {
              try {
                const r = await api<{ nuevas: number; actualizadas: number }>(`${base}/cajas/desde-fuid`, { metodo: "POST", consulta: { frente: frente || undefined } });
                avisos.exito(`Desde el FUID: ${r.nuevas} cajas nuevas y ${r.actualizadas} actualizadas.`);
                alCambiar();
              } catch (e) {
                avisos.error((e as Error).message);
              }
            }}>Tomar del FUID</Boton>
          </div>
        )}
      </div>
      {puedeConfigurar && <p className="text-[12px] text-texto-3">Columnas del listado (Excel o CSV): <Codigo>Caja</Codigo> obligatoria; opcionales <Codigo>Carpetas</Codigo>, <Codigo>Cod_Frente</Codigo>, <Codigo>Lote</Codigo>, <Codigo>Sede</Codigo>, <Codigo>Ubicacion</Codigo> y <Codigo>Notas</Codigo>.</p>}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {todas.datos?.resumen.map((r) => (
          <button key={r.Cod_Frente} onClick={() => setFrente(r.Cod_Frente === "Sin frente" ? "" : r.Cod_Frente)} className={cn("rounded-xl border bg-surface p-3.5 text-left shadow-xs transition-colors hover:border-marca-borde", frente === r.Cod_Frente ? "border-marca" : "border-line")}>
            <span className="block font-semibold text-titulo">{r.Cod_Frente}</span>
            <span className="tabular block text-[22px] leading-tight font-bold text-titulo">{numero(r.pendiente)} <span className="text-[13px] font-medium text-texto-3">pendientes de {numero(r.total)}</span></span>
            <Progreso valor={r.total ? (100 * r.procesada) / r.total : 0} className="mt-1.5" />
            <span className="mt-1 block text-[12px] text-texto-3">{numero(r.procesada)} procesadas · {numero(r.en_proceso)} en proceso{r.carpetas ? ` · ${numero(r.carpetas_procesadas)} de ${numero(r.carpetas)} carpetas` : ""}</span>
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <Campo etiqueta="Estado" className="w-48">
          <Selector value={estado} onChange={(e) => setEstado(e.target.value)}>
            <option value="pendiente">Pendientes</option><option value="en_proceso">En proceso</option><option value="procesada">Procesadas</option><option value="">Todas</option>
          </Selector>
        </Campo>
        <Campo etiqueta="Frente" className="w-40"><Entrada value={frente} onChange={(e) => setFrente(e.target.value)} placeholder="Todos" /></Campo>
        <form className="flex items-end gap-2" onSubmit={(e) => (e.preventDefault(), setBuscar(texto))}>
          <Campo etiqueta="Caja" className="w-40"><Entrada value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="C-0458" /></Campo>
          <Boton type="submit">Buscar</Boton>
        </form>
      </div>
      {datos.cargando && !datos.datos ? <Cargando /> : !datos.datos?.cajas.length ? (
        <Vacio icono={<Boxes />} titulo={estado === "pendiente" ? "No hay cajas pendientes en este filtro" : "Sin cajas en este filtro"} descripcion="Cargue el listado de cajas de la entidad o tómelo del FUID." />
      ) : (
        <Tabla className="max-h-[32rem] overflow-y-auto rounded-xl border border-line">
          <thead><tr><th>Caja</th><th>Frente</th><th>Lote</th><th>Ubicación</th><th>Carpetas</th><th>Hecho</th><th>Pendiente</th><th>Estado</th></tr></thead>
          <tbody>
            {datos.datos.cajas.map((c) => (
              <tr key={c.Caja}>
                <td><Codigo>{c.Caja}</Codigo></td><td>{c.Cod_Frente ?? "—"}</td><td>{c.Lote || "—"}</td><td>{c.Ubicacion || c.Sede || "—"}</td><td className="tabular">{c.Carpetas ?? "—"}</td>
                <td className="max-w-56 text-[12px]">{c.Actividades_Hechas.join(" · ") || "—"}{c.Ultima_Fecha && <span className="block text-texto-3">última: {c.Ultima_Fecha}</span>}</td>
                <td className="max-w-56 text-[12px] text-texto-3">{c.Actividades_Pendientes.join(" · ") || "—"}</td>
                <td><Insignia tono={TONO_CAJA[c.Estado]} punto>{NOMBRE_CAJA[c.Estado]}</Insignia></td>
              </tr>
            ))}
          </tbody>
        </Tabla>
      )}
    </>
  );
}

const FORMULARIOS: { tabla: string; nombre: string; campos: { col: string; etiqueta: string; tipo?: "date" | "number" | "texto"; lista?: string; ref?: "actividad" | "frente" | "turno" }[] }[] = [
  { tabla: "fProduccion", nombre: "Producción del turno", campos: [
    { col: "Fecha", etiqueta: "Fecha", tipo: "date" }, { col: "Turno", etiqueta: "Turno", ref: "turno" }, { col: "Actividad", etiqueta: "Actividad", ref: "actividad" },
    { col: "Lote", etiqueta: "Lote" }, { col: "Caja_Desde", etiqueta: "Caja desde" }, { col: "Caja_Hasta", etiqueta: "Caja hasta" }, { col: "Cantidad", etiqueta: "Cantidad", tipo: "number" },
    { col: "Personas_Presentes", etiqueta: "Personas presentes", tipo: "number" }, { col: "Horas_Efectivas", etiqueta: "Horas efectivas", tipo: "number" },
    { col: "Supervisor", etiqueta: "Supervisor" }, { col: "Observaciones", etiqueta: "Observaciones" },
  ] },
  { tabla: "fCalidad", nombre: "Inspección de calidad", campos: [
    { col: "Fecha", etiqueta: "Fecha", tipo: "date" }, { col: "Cod_Frente", etiqueta: "Frente", ref: "frente" }, { col: "Lote", etiqueta: "Lote" },
    { col: "Unidad_Inspeccion", etiqueta: "Unidad de inspección", lista: "unidades" }, { col: "Tamano_Lote", etiqueta: "Tamaño del lote", tipo: "number" }, { col: "Muestra", etiqueta: "Muestra", tipo: "number" },
    { col: "Criticos", etiqueta: "Críticos", tipo: "number" }, { col: "Mayores", etiqueta: "Mayores", tipo: "number" }, { col: "Menores", etiqueta: "Menores", tipo: "number" },
    { col: "Limitaciones_Original", etiqueta: "Limitaciones del original", tipo: "number" }, { col: "Resultado", etiqueta: "Resultado", lista: "resultados_calidad" },
    { col: "Analista", etiqueta: "Analista" }, { col: "Observaciones", etiqueta: "Observaciones" },
  ] },
  { tabla: "fNovedades", nombre: "Novedad", campos: [
    { col: "Fecha", etiqueta: "Fecha", tipo: "date" }, { col: "Turno", etiqueta: "Turno", ref: "turno" }, { col: "Cod_Frente", etiqueta: "Frente", ref: "frente" }, { col: "Lote", etiqueta: "Lote" },
    { col: "Caja", etiqueta: "Caja" }, { col: "Tipo_Novedad", etiqueta: "Tipo de novedad", lista: "tipos_novedad" }, { col: "Descripcion", etiqueta: "Descripción" },
    { col: "Accion_Tomada", etiqueta: "Acción tomada" }, { col: "Responsable", etiqueta: "Responsable" }, { col: "Estado", etiqueta: "Estado", lista: "estados_novedad" },
  ] },
  { tabla: "fEntregas", nombre: "Entrega a la entidad", campos: [
    { col: "Fecha_Entrega", etiqueta: "Fecha de entrega", tipo: "date" }, { col: "Cod_Frente", etiqueta: "Frente", ref: "frente" }, { col: "Lote", etiqueta: "Lote" },
    { col: "Cantidad", etiqueta: "Cantidad", tipo: "number" }, { col: "Unidad", etiqueta: "Unidad", lista: "unidades" }, { col: "Numero_Acta", etiqueta: "Número de acta" },
    { col: "Estado_Entrega", etiqueta: "Estado", lista: "estados_entrega" }, { col: "Fecha_Aceptacion", etiqueta: "Fecha de aceptación", tipo: "date" }, { col: "Observaciones", etiqueta: "Observaciones" },
  ] },
];

function Registrar({ base, alGuardar }: { base: string; alGuardar: () => void }) {
  const avisos = useAvisos();
  const [tipo, setTipo] = useState("fProduccion");
  const [valores, setValores] = useState<Record<string, string>>({ Fecha: new Date().toISOString().slice(0, 10), Fecha_Entrega: new Date().toISOString().slice(0, 10) });
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const diseno = useDatos(() => api<Diseno>(`${base}/diseno`), [base]);
  const actividades = useDatos(() => api<{ Actividad_Clave: string; Cod_Frente: string }[]>(`${base}/tablas/dActividades`), [base]);
  const frentes = useDatos(() => api<{ Cod_Frente: string; Frente: string }[]>(`${base}/tablas/dFrentes`), [base]);
  const turnos = useDatos(() => api<{ Turno: string; Horario: string }[]>(`${base}/tablas/dTurnos`), [base]);
  const form = FORMULARIOS.find((f) => f.tabla === tipo)!;
  const opcionesRef = (ref: string) =>
    ref === "actividad" ? (actividades.datos ?? []).map((a) => a.Actividad_Clave) : ref === "frente" ? (frentes.datos ?? []).map((f) => f.Cod_Frente) : (turnos.datos ?? []).map((t) => t.Turno);
  const lista = (nombre: string) => (diseno.datos?.listas[nombre] as string[] | undefined) ?? [];
  return (
    <div className="grid gap-5 lg:grid-cols-[16rem_1fr]">
      <div className="flex flex-col gap-1.5">
        {FORMULARIOS.map((f) => (
          <button key={f.tabla} onClick={() => (setTipo(f.tabla), setError(null))} className={cn("rounded-lg px-3 py-2 text-left text-[13.5px]", tipo === f.tabla ? "bg-marca font-semibold text-white" : "text-texto-2 hover:bg-surface-muted")}>{f.nombre}</button>
        ))}
        <p className="mt-2 text-[12px] text-texto-3">Las imágenes que entran a ARCA y los expedientes que se inventarían se cuentan solos en las actividades que lo tengan configurado.</p>
      </div>
      <form
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3"
        onSubmit={async (e) => {
          e.preventDefault();
          setEnviando(true);
          setError(null);
          try {
            const cuerpo = Object.fromEntries(form.campos.map((c) => [c.col, valores[c.col] === "" || valores[c.col] === undefined ? null : c.tipo === "number" ? Number(valores[c.col]) : valores[c.col]]));
            await api(`${base}/registros/${tipo}`, { metodo: "POST", cuerpo });
            avisos.exito(`${form.nombre}: registrado. El tablero ya lo incluye.`);
            setValores((v) => ({ Fecha: v.Fecha, Fecha_Entrega: v.Fecha_Entrega, Turno: v.Turno, Actividad: v.Actividad, Cod_Frente: v.Cod_Frente, Supervisor: v.Supervisor }));
            alGuardar();
          } catch (err) {
            setError((err as Error).message);
          } finally {
            setEnviando(false);
          }
        }}
      >
        {form.campos.map((c) => (
          <Campo key={c.col} etiqueta={c.etiqueta} className={c.col === "Observaciones" || c.col === "Descripcion" ? "sm:col-span-2 xl:col-span-3" : undefined}>
            {c.ref || c.lista ? (
              <Selector value={valores[c.col] ?? ""} onChange={(e) => setValores({ ...valores, [c.col]: e.target.value })}>
                <option value="">Elija…</option>
                {(c.ref ? opcionesRef(c.ref) : lista(c.lista!)).map((o) => <option key={o} value={o}>{o}</option>)}
              </Selector>
            ) : c.col === "Observaciones" || c.col === "Descripcion" ? (
              <Area value={valores[c.col] ?? ""} onChange={(e) => setValores({ ...valores, [c.col]: e.target.value })} />
            ) : (
              <Entrada type={c.tipo === "number" ? "number" : c.tipo === "date" ? "date" : "text"} step="any" value={valores[c.col] ?? ""} onChange={(e) => setValores({ ...valores, [c.col]: e.target.value })} />
            )}
          </Campo>
        ))}
        {error && <div className="sm:col-span-2 xl:col-span-3"><CajaError mensaje={error} /></div>}
        <div className="sm:col-span-2 xl:col-span-3"><Boton type="submit" variante="primario" cargando={enviando}>Registrar</Boton></div>
      </form>
    </div>
  );
}

async function descargar(ruta: string, nombre: string) {
  const r = await fetch(`/api/v1${ruta}`, { headers: { Authorization: `Bearer ${sesionGuardada.token()}`, "X-Organizacion": sesionGuardada.organizacion() ?? "" } });
  if (!r.ok) throw new Error("No se pudo descargar");
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

function Configurar({ base, proyecto, alCambiar }: { base: string; proyecto: Proyecto; alCambiar: () => void }) {
  const avisos = useAvisos();
  const entrada = useRef<HTMLInputElement>(null);
  const [enviando, setEnviando] = useState(false);
  const [reporte, setReporte] = useState<{ hoja: string; accion: string; filas: number; omitidas?: number; errores: string[] }[] | null>(null);
  const diseno = useDatos(() => api<Diseno>(`${base}/diseno`), [base]);
  async function importar(archivo: File) {
    setEnviando(true);
    try {
      const datos = new FormData();
      datos.append("archivo", archivo);
      setReporte(await apiSubir(`${base}/libro`, datos));
      avisos.exito("Libro importado.");
      alCambiar();
    } catch (e) {
      avisos.error((e as Error).message);
    } finally {
      setEnviando(false);
      if (entrada.current) entrada.current.value = "";
    }
  }
  return (
    <div className="flex flex-col gap-4">
      <Nota tono="info">ARCA usa el diseño del reporte de productividad (las mismas hojas, columnas y cálculos del modelo de Power BI) y ningún dato de otros proyectos. Descargue la plantilla vacía, diligencie la configuración de este proyecto y súbala.</Nota>
      <div className="flex flex-wrap gap-2">
        <Boton icono={<Download />} onClick={() => descargar(`${base}/plantilla`, "ARCA_Productividad_plantilla.xlsx").catch((e) => avisos.error(e.message))}>Plantilla vacía</Boton>
        <input ref={entrada} type="file" accept=".xlsx" hidden onChange={(e) => e.target.files?.[0] && importar(e.target.files[0])} />
        <Boton variante="primario" icono={<Upload />} cargando={enviando} onClick={() => entrada.current?.click()}>Importar libro</Boton>
        <Boton icono={<FileSpreadsheet />} onClick={() => descargar(`${base}/libro`, `Productividad_${proyecto.codigo}.xlsx`).catch((e) => avisos.error(e.message))}>Descargar libro con los datos</Boton>
      </div>
      {reporte && (
        <Tabla className="rounded-xl border border-line">
          <thead><tr><th>Hoja</th><th>Resultado</th><th>Filas</th><th>Omitidas</th><th>Errores</th></tr></thead>
          <tbody>
            {reporte.map((r) => (
              <tr key={r.hoja}><td className="font-semibold">{r.hoja}</td><td>{r.accion}</td><td className="tabular">{r.filas}</td><td className="tabular">{r.omitidas ?? 0}</td>
                <td className="max-w-96 text-[12px] text-critico">{r.errores.slice(0, 5).join(" · ")}{r.errores.length > 5 ? ` · y ${r.errores.length - 5} más` : ""}</td></tr>
            ))}
          </tbody>
        </Tabla>
      )}
      <div>
        <p className="mb-2 font-semibold text-titulo">Las tablas del diseño</p>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {diseno.datos?.tablas.map((t) => (
            <div key={t.nombre} className="rounded-xl border border-line p-3">
              <p className="flex items-center gap-2 font-semibold text-titulo"><Codigo>{t.nombre}</Codigo><Insignia tono={t.registro ? "motor" : "marca"}>{t.registro ? "registro diario" : "configuración"}</Insignia></p>
              <p className="mt-1 text-[12px] text-texto-3">Hoja «{t.hoja}». {t.registro ? "Se agregan filas sin duplicar." : "Al importar se reemplaza."}</p>
              <p className="mt-1.5 text-[12px] text-texto-2">{t.columnas.map((c) => c.nombre + (c.obligatoria ? "*" : "")).join(" · ")}</p>
            </div>
          ))}
        </div>
        <p className="mt-2 text-[12px] text-texto-3">En <Codigo>dActividades</Codigo>, la columna <Codigo>Fuente_Automatica</Codigo> hace que ARCA cuente sola: <Codigo>imagenes_recibidas</Codigo>, <Codigo>imagenes_aprobadas</Codigo> o <Codigo>expedientes_inventariados</Codigo>.</p>
      </div>
    </div>
  );
}

function PowerBI({ base }: { base: string }) {
  const avisos = useAvisos();
  const claves = useDatos(() => api<Clave[]>(`${base}/claves`), [base]);
  const [nombre, setNombre] = useState("Power BI de la dirección");
  const [token, setToken] = useState<string | null>(null);
  const [revocar, setRevocar] = useState<Clave | null>(null);
  const [copiado, setCopiado] = useState(false);
  const origen = typeof window !== "undefined" ? window.location.origin : "https://su-arca";
  const consulta = `let
    Base = "${origen}/api/v1/powerbi/",
    Llave = "${token ?? "PEGUE AQUÍ LA LLAVE"}",
    Leer = (tabla as text) => Table.FromRecords(Json.Document(
        Web.Contents(Base, [RelativePath = tabla, Headers = [Authorization = "Bearer " & Llave]]))),
    Tablas = #table({"Nombre"}, {{"dFrentes"}, {"dActividades"}, {"dMetas"}, {"dPersonal"}, {"dTurnos"},
        {"dCalendario"}, {"dCajas"}, {"fProduccion"}, {"fCalidad"}, {"fNovedades"}, {"fEntregas"}, {"Tablero"}}),
    ConDatos = Table.AddColumn(Tablas, "Datos", each Leer([Nombre]))
in
    ConDatos`;
  return (
    <div className="flex flex-col gap-4">
      <Nota tono="info">Power BI lee las mismas tablas del diseño (dFrentes, dActividades, dMetas, dPersonal, dTurnos, dCalendario, fProduccion, fCalidad, fNovedades, fEntregas), más dCajas y el Tablero calculado. Usa una llave de solo lectura de este proyecto: no ve nada más, y se puede revocar en cualquier momento.</Nota>
      <div className="flex flex-wrap items-end gap-2">
        <Campo etiqueta="Nombre de la llave" className="w-72"><Entrada value={nombre} onChange={(e) => setNombre(e.target.value)} /></Campo>
        <Boton variante="primario" icono={<KeyRound />} disabled={nombre.trim().length < 3} onClick={async () => {
          try {
            const r = await api<{ token: string }>(`${base}/claves`, { metodo: "POST", cuerpo: { nombre } });
            setToken(r.token);
            void claves.recargar();
          } catch (e) {
            avisos.error((e as Error).message);
          }
        }}>Crear llave</Boton>
      </div>
      {token && <ClaveTemporal correo="Power BI" clave={token} />}
      {!!claves.datos?.length && (
        <Tabla className="rounded-xl border border-line">
          <thead><tr><th>Llave</th><th>Inicia con</th><th>Creada</th><th>Último uso</th><th>Estado</th><th /></tr></thead>
          <tbody>
            {claves.datos.map((c) => (
              <tr key={c.id}><td className="font-semibold">{c.nombre}</td><td><Codigo>{c.prefijo}…</Codigo></td><td>{fechaHora(c.creado_en)}</td><td>{fechaHora(c.ultimo_uso)}</td>
                <td><Insignia tono={c.activa ? "ok" : "neutro"} punto>{c.activa ? "Activa" : "Revocada"}</Insignia></td>
                <td>{c.activa && <Boton tamano="sm" variante="fantasma" onClick={() => setRevocar(c)}>Revocar</Boton>}</td></tr>
            ))}
          </tbody>
        </Tabla>
      )}
      <div className="rounded-xl border border-line">
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <p className="font-semibold text-titulo">Conectar Power BI Desktop</p>
          <Boton tamano="sm" icono={copiado ? <Check /> : <Copy />} onClick={async () => (await navigator.clipboard?.writeText(consulta), setCopiado(true))}>{copiado ? "Copiada" : "Copiar consulta"}</Boton>
        </div>
        <ol className="list-decimal space-y-1 px-8 py-3 text-[13px] text-texto-2">
          <li>En Power BI Desktop: <b>Obtener datos › Consulta en blanco › Editor avanzado</b> y pegue la consulta.</li>
          <li>Expanda la columna <b>Datos</b> de cada tabla, o use <b>Leer(&quot;fProduccion&quot;)</b> en una consulta por tabla. Las relaciones van por Cod_Frente, Actividad_Clave, Turno y Fecha, como en el diseño.</li>
          <li>Para la actualización programada en el servicio de Power BI: credencial <b>Anónima</b> y <b>Omitir la prueba de conexión</b>; la llave viaja en el encabezado.</li>
          <li>Para ver el tablero en tiempo real sin esperar la actualización de Power BI, use la pestaña Tablero de ARCA: se recalcula cada 30 segundos.</li>
        </ol>
        <pre className="overflow-x-auto bg-canvas px-4 py-3 font-mono text-[12px] leading-relaxed text-texto">{consulta}</pre>
      </div>
      <ModalMotivo
        abierto={!!revocar}
        titulo={`Revocar «${revocar?.nombre}»`}
        descripcion="Power BI dejará de poder leer con esta llave de inmediato."
        boton="Revocar"
        peligro
        alCerrar={() => setRevocar(null)}
        alConfirmar={async (motivo) => {
          await api(`${base}/claves/${revocar!.id}/revocar`, { metodo: "POST", cuerpo: { motivo } });
          avisos.exito("Llave revocada.");
          await claves.recargar();
        }}
      />
    </div>
  );
}
