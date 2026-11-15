"use client";

import { ClipboardCheck, IdCard, Save, Sparkles, UserCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useAvisos } from "@/components/ui/avisos";
import { Boton, Cargando, Insignia, Modal, Nota, Tabla, Vacio } from "@/components/ui/basicos";
import { Area, Campo, Casilla, Entrada, Selector } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { descargarArchivo } from "@/lib/descargas";
import { numero } from "@/lib/formato";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { ConfigHistorias, ExpedienteHistoria, Proyecto } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

const ALERTAS: Record<string, string> = {
  otra_persona: "Documentos de otra persona", duplicado: "Titular repetido", faltan_tipos: "Faltan tipos mínimos",
  sin_titular: "El número no aparece", sin_numero: "Sin número de documento",
};
const FUENTE: Record<string, string> = { fuid: "FUID", ocr: "OCR", persona: "Persona" };

/** Historias laborales: el titular de cada expediente, documentos de otra persona, tipos mínimos y duplicados. */
export function Historias({ proyecto }: { proyecto: Proyecto }) {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const base = `/proyectos/${proyecto.id}/historias`;
  const [alerta, setAlerta] = useState("");
  const config = useDatos(() => api<ConfigHistorias>(`${base}/config`), [base]);
  const lista = useDatos(() => api<{ resumen: { expedientes: number; confirmados: number; con_alertas: number; por_clase: Record<string, number> }; total: number; filas: ExpedienteHistoria[] }>(
    `${base}/expedientes`, { consulta: { alerta: alerta || undefined, limite: 200 } }), [base, alerta]);
  const [editando, setEditando] = useState<ExpedienteHistoria | null>(null);
  const [proponiendo, setProponiendo] = useState(false);
  const elabora = puede(PERMISOS.hojaControl);
  const expide = puede(PERMISOS.expedir);
  const [expidiendo, setExpidiendo] = useState<string | null>(null);

  async function listaChequeo(f: ExpedienteHistoria) {
    setExpidiendo(f.unidad_id);
    try {
      const r = await api<{ expedicion_id: string; nombre_archivo: string }>(`${base}/expedientes/${f.unidad_id}/lista-chequeo`, { metodo: "POST" });
      await descargarArchivo(`/proyectos/${proyecto.id}/entregables/${r.expedicion_id}/archivo`, r.nombre_archivo);
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setExpidiendo(null);
    }
  }

  async function proponer() {
    setProponiendo(true);
    try {
      const r = await api<{ propuestos: number }>(`${base}/expedientes/proponer`, { metodo: "POST" });
      avisos.exito(`${numero(r.propuestos)} titulares propuestos del FUID y del OCR.`);
      lista.recargar();
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setProponiendo(false);
    }
  }

  if (config.cargando && !config.datos) return <Cargando />;
  const r = lista.datos?.resumen;
  return (
    <div className="flex flex-col gap-5 p-5">
      <Nota tono="info">Cada historia laboral es el expediente de una persona (Acuerdo AGN 001 de 2024, título 9, capítulo 5). ARCA propone el titular desde el FUID o el OCR y señala las páginas con el número de documento de otra persona, los tipos documentales mínimos que faltan, los documentos fuera de orden cronológico y los titulares repetidos. Una persona confirma.</Nota>
      {config.datos && <ConfigCard base={base} datos={config.datos} alGuardar={() => (config.recargar(), lista.recargar())} />}
      {config.datos?.activo && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            {r && <span className="text-[13px] text-texto-2"><b>{numero(r.expedientes)}</b> historias · <b>{numero(r.confirmados)}</b> con titular confirmado · <b>{numero(r.con_alertas)}</b> con alertas</span>}
            <Selector className="w-64" value={alerta} onChange={(e) => setAlerta(e.target.value)} aria-label="Filtrar por alerta">
              <option value="">Todas</option>
              {Object.entries(ALERTAS).map(([k, v]) => <option key={k} value={k}>{v}{r?.por_clase[k] ? ` (${r.por_clase[k]})` : ""}</option>)}
            </Selector>
            {elabora && <Boton className="ml-auto" icono={<Sparkles />} cargando={proponiendo} onClick={proponer}>Proponer titulares</Boton>}
          </div>
          {!lista.datos?.filas.length ? <Vacio icono={<IdCard />} titulo="No hay historias laborales con ese filtro" /> : (
            <Tabla className="rounded-xl border border-line">
              <thead><tr><th>Expediente</th><th>Titular</th><th>Tipos mínimos</th><th>Alertas</th><th /></tr></thead>
              <tbody>
                {lista.datos.filas.map((f) => (
                  <tr key={f.unidad_id}>
                    <td><span className="font-semibold">{f.identificador}</span><span className="block text-[12px] text-texto-3">caja {f.caja ?? "—"}</span></td>
                    <td>
                      {f.titular ? <>
                        <span className="font-semibold">{f.titular.tipo_documento} {f.titular.numero_documento || "—"}</span> · {f.titular.nombres || "—"}
                        <span className="mt-0.5 flex flex-wrap gap-1">
                          {f.titular.estado === "confirmado" ? <Insignia tono="ok">Confirmado</Insignia> : <Insignia tono="ia">Propuesto · {FUENTE[f.titular.origen.numero_documento?.fuente ?? ""] ?? "—"}</Insignia>}
                          {f.titular.cargo && <span className="text-[12px] text-texto-3">{f.titular.cargo}</span>}
                        </span>
                      </> : <span className="text-[12px] text-texto-3">Sin titular</span>}
                    </td>
                    <td className="tabular">{f.completitud.obligatorios ? (f.completitud.hoja ? `${f.completitud.presentes} de ${f.completitud.obligatorios}` : "sin hoja") : "—"}</td>
                    <td className="max-w-md">
                      {f.alertas.length ? <ul className="flex flex-col gap-0.5 text-[12px]">{f.alertas.map((a, i) => <li key={i} className={a.clase === "otra_persona" || a.clase === "duplicado" ? "text-critico" : "text-aviso"}>{a.mensaje}</li>)}</ul> : <span className="text-[12px] text-ok">Sin alertas</span>}
                    </td>
                    <td className="whitespace-nowrap text-right">
                      <Link href={`/proyectos/${proyecto.id}/hojas/${f.unidad_id}`} className="mr-3 text-[13px] font-semibold text-marca hover:underline">Hoja →</Link>
                      {expide && f.completitud.hoja && <Boton tamano="sm" variante="fantasma" icono={<ClipboardCheck />} cargando={expidiendo === f.unidad_id} onClick={() => listaChequeo(f)} className="mr-1">Lista de chequeo</Boton>}
                      {elabora && <Boton tamano="sm" icono={<UserCheck />} onClick={() => setEditando(f)}>{f.titular?.estado === "confirmado" ? "Editar" : "Confirmar"}</Boton>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Tabla>
          )}
        </>
      )}
      {editando && <ModalTitular base={base} expediente={editando} alCerrar={() => setEditando(null)} alGuardar={() => (setEditando(null), lista.recargar())} />}
    </div>
  );
}

function ConfigCard({ base, datos, alGuardar }: { base: string; datos: ConfigHistorias; alGuardar: () => void }) {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const dirige = puede(PERMISOS.proyectos);
  const [editando, setEditando] = useState(!datos.configurado && dirige);
  const [activo, setActivo] = useState(datos.configurado ? datos.activo : true);
  const [restringido, setRestringido] = useState(datos.acceso_restringido);
  const [series, setSeries] = useState(datos.series.join(", "));
  const [tipos, setTipos] = useState(datos.tipos_obligatorios.join("\n"));
  const [motivo, setMotivo] = useState("");
  const [guardando, setGuardando] = useState(false);

  async function guardar() {
    setGuardando(true);
    try {
      await api(`${base}/config`, { metodo: "PUT", cuerpo: { activo, acceso_restringido: restringido, series: series.split(/[,;\n]/).map((x) => x.trim()).filter(Boolean), tipos_obligatorios: tipos.split("\n").map((x) => x.trim()).filter(Boolean), motivo } });
      avisos.exito("Configuración de historias laborales guardada.");
      setEditando(false);
      alGuardar();
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="rounded-xl border border-line bg-surface p-4 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-semibold text-titulo">Configuración del proyecto</span>
        {datos.activo ? <Insignia tono="ok" punto>Historias laborales activas</Insignia> : <Insignia tono="neutro" punto>{datos.configurado ? "Inactivo" : "Sin configurar"}</Insignia>}
      </div>
      {!editando ? (
        <div className="mt-2 flex flex-col gap-1 text-[13px] text-texto-2">
          <span>Series de la TRD: <b>{datos.series.join(", ") || "todo el proyecto"}</b></span>
          <span>Acceso: <b>{datos.acceso_restringido ? "restringido (solo con permiso de consulta reservada se ve el contenido)" : "según la TRD"}</b></span>
          <span>Tipos documentales mínimos ({datos.tipos_obligatorios.length}): {datos.tipos_obligatorios.join(" · ") || "ninguno"}</span>
          {dirige && <div className="mt-1"><Boton tamano="sm" onClick={() => setEditando(true)}>Cambiar</Boton></div>}
        </div>
      ) : (
        <div className="mt-3 flex flex-col gap-3">
          <Nota tono="aviso">{datos.aviso}</Nota>
          <Casilla etiqueta="Este proyecto es de historias laborales" checked={activo} onChange={(e) => setActivo(e.target.checked)} />
          <Casilla etiqueta="Acceso restringido a las historias laborales aunque la TRD no lo marque (datos sensibles, artículo 9.5.3)" checked={restringido} onChange={(e) => setRestringido(e.target.checked)} />
          <Campo etiqueta="Códigos de la TRD que son historias laborales" ayuda="Separados por coma. Vacío = todo el proyecto."><Entrada value={series} onChange={(e) => setSeries(e.target.value)} placeholder="Ej.: 100-15" /></Campo>
          <Campo etiqueta="Tipos documentales mínimos" ayuda={datos.tipos_de_la_trd.length ? `Uno por renglón. En la TRD del proyecto: ${datos.tipos_de_la_trd.slice(0, 12).join(", ")}${datos.tipos_de_la_trd.length > 12 ? "…" : ""}` : "Uno por renglón."}>
            <Area className="min-h-32" value={tipos} onChange={(e) => setTipos(e.target.value)} />
          </Campo>
          <div className="flex flex-wrap items-end gap-3">
            <Campo etiqueta="Motivo" className="min-w-72 flex-1" requerido><Entrada value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Ej.: tipos mínimos del BANTER y de la TRD de la entidad" /></Campo>
            <Boton variante="primario" icono={<Save />} cargando={guardando} disabled={motivo.trim().length < 5} onClick={guardar}>Guardar</Boton>
            {datos.configurado && <Boton variante="fantasma" onClick={() => setEditando(false)}>Cancelar</Boton>}
          </div>
        </div>
      )}
    </div>
  );
}

function ModalTitular({ base, expediente, alCerrar, alGuardar }: { base: string; expediente: ExpedienteHistoria; alCerrar: () => void; alGuardar: () => void }) {
  const avisos = useAvisos();
  const t = expediente.titular;
  const [v, setV] = useState({
    tipo_documento: t?.tipo_documento ?? "CC", numero_documento: t?.numero_documento ?? "", nombres: t?.nombres ?? "", cargo: t?.cargo ?? "",
    dependencia: t?.dependencia ?? "", fecha_vinculacion: t?.fecha_vinculacion ?? "", fecha_retiro: t?.fecha_retiro ?? "",
  });
  const [guardando, setGuardando] = useState(false);
  const campo = (k: keyof typeof v) => ({ value: v[k], onChange: (e: { target: { value: string } }) => setV({ ...v, [k]: e.target.value }) });

  async function guardar() {
    setGuardando(true);
    try {
      await api(`${base}/expedientes/${expediente.unidad_id}/titular`, { metodo: "PUT", cuerpo: { ...v, fecha_vinculacion: v.fecha_vinculacion || null, fecha_retiro: v.fecha_retiro || null } });
      avisos.exito(`Titular de ${expediente.identificador} confirmado.`);
      alGuardar();
    } catch (err) {
      avisos.error((err as Error).message);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Modal abierto titulo={`Titular de ${expediente.identificador}`} descripcion={expediente.nombre} alCerrar={alCerrar} ancho="lg"
      pie={<><Boton variante="fantasma" onClick={alCerrar}>Cancelar</Boton><Boton variante="primario" icono={<UserCheck />} cargando={guardando} onClick={guardar}>Confirmar titular</Boton></>}>
      <div className="grid gap-3 sm:grid-cols-[140px_minmax(0,1fr)]">
        <Campo etiqueta="Tipo"><Selector {...campo("tipo_documento")}><option value="CC">C.C.</option><option value="CE">C.E.</option><option value="TI">T.I.</option><option value="PA">Pasaporte</option><option value="PEP">PEP</option></Selector></Campo>
        <Campo etiqueta="Número de documento" ayuda={t?.origen.numero_documento ? `${FUENTE[t.origen.numero_documento.fuente] ?? ""}: ${t.origen.numero_documento.detalle}` : undefined}><Entrada {...campo("numero_documento")} /></Campo>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Campo etiqueta="Nombres y apellidos"><Entrada {...campo("nombres")} /></Campo>
        <Campo etiqueta="Cargo"><Entrada {...campo("cargo")} /></Campo>
        <Campo etiqueta="Dependencia"><Entrada {...campo("dependencia")} /></Campo>
        <div className="grid grid-cols-2 gap-3">
          <Campo etiqueta="Vinculación"><Entrada type="date" {...campo("fecha_vinculacion")} /></Campo>
          <Campo etiqueta="Retiro"><Entrada type="date" {...campo("fecha_retiro")} /></Campo>
        </div>
      </div>
      {expediente.documentos_encontrados.length > 0 && (
        <p className="mt-3 text-[12.5px] text-texto-3">Números de documento en el texto leído: {expediente.documentos_encontrados.map((d) => `${d.numero} (p. ${d.paginas.slice(0, 6).join(", ")})`).join(" · ")}</p>
      )}
    </Modal>
  );
}
