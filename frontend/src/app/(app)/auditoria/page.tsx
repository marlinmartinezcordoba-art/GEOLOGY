"use client";

import { ScrollText, Search, ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { Boton, CajaError, Cargando, Codigo, EncabezadoPagina, Insignia, Modal, Tabla, Tarjeta, Vacio } from "@/components/ui/basicos";
import { Campo, Entrada } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { fechaHora } from "@/lib/formato";
import type { EventoAuditoria, Verificacion } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

const TONO_RESULTADO = { exito: "ok", bloqueado: "aviso", error: "critico" } as const;

export default function Auditoria() {
  const [filtros, setFiltros] = useState({ accion: "", objeto: "", correlacion_id: "" });
  const [aplicados, setAplicados] = useState(filtros);
  const [antesDe, setAntesDe] = useState<number | null>(null);
  const eventos = useDatos(() => api<EventoAuditoria[]>("/auditoria/eventos", { consulta: { ...aplicados, antes_de: antesDe, limite: 50 } }), [aplicados, antesDe]);
  const [verificacion, setVerificacion] = useState<Verificacion | null>(null);
  const [verificando, setVerificando] = useState(false);
  const [detalle, setDetalle] = useState<EventoAuditoria | null>(null);

  async function verificar() {
    setVerificando(true);
    try {
      setVerificacion(await api<Verificacion>("/auditoria/verificar"));
    } finally {
      setVerificando(false);
    }
  }

  return (
    <>
      <EncabezadoPagina
        titulo="Auditoría"
        descripcion="Cada evento se encadena al anterior con SHA-256 y se sella periódicamente. Consultarla y verificarla también queda registrado."
        acciones={<Boton variante="acento" icono={<ShieldCheck />} cargando={verificando} onClick={verificar}>Verificar integridad</Boton>}
      />
      {verificacion && (
        <div className={`mb-5 flex items-start gap-3 rounded-xl border p-4 ${verificacion.integra ? "border-ok/30 bg-ok-suave text-ok" : "border-critico/30 bg-critico-suave text-critico"}`}>
          {verificacion.integra ? <ShieldCheck className="mt-0.5 size-5" /> : <ShieldAlert className="mt-0.5 size-5" />}
          <div className="text-[13.5px]">
            <p className="font-semibold">{verificacion.integra ? "La cadena está íntegra" : "ALERTA: la cadena fue alterada"}</p>
            <p>{verificacion.integra ? `${verificacion.revisados} eventos revisados y ${verificacion.sellos_verificados} sellos verificados.` : verificacion.problema}</p>
          </div>
        </div>
      )}
      <Tarjeta>
        <form
          className="grid gap-3 border-b border-line px-5 py-4 sm:grid-cols-[1fr_1fr_1fr_auto] sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            setAntesDe(null);
            setAplicados({ ...filtros });
          }}
        >
          <Campo etiqueta="Acción"><Entrada value={filtros.accion} onChange={(e) => setFiltros({ ...filtros, accion: e.target.value })} placeholder="CREAR_PROYECTO" /></Campo>
          <Campo etiqueta="Objeto"><Entrada value={filtros.objeto} onChange={(e) => setFiltros({ ...filtros, objeto: e.target.value })} placeholder="Proyecto, Membresia, Parametro…" /></Campo>
          <Campo etiqueta="Correlación"><Entrada value={filtros.correlacion_id} onChange={(e) => setFiltros({ ...filtros, correlacion_id: e.target.value })} /></Campo>
          <Boton type="submit" icono={<Search />}>Filtrar</Boton>
        </form>
        {eventos.cargando && !eventos.datos ? (
          <Cargando />
        ) : eventos.error ? (
          <div className="p-5"><CajaError mensaje={eventos.error} reintentar={eventos.recargar} /></div>
        ) : !eventos.datos?.length ? (
          <Vacio icono={<ScrollText />} titulo="Sin eventos para estos filtros" />
        ) : (
          <>
            <Tabla>
              <thead><tr><th>#</th><th>Fecha</th><th>Persona</th><th>Acción</th><th>Detalle</th><th>Resultado</th></tr></thead>
              <tbody>
                {eventos.datos.map((e) => (
                  <tr key={e.secuencia} className="cursor-pointer" onClick={() => setDetalle(e)}>
                    <td className="tabular text-texto-3">{e.secuencia}</td>
                    <td className="whitespace-nowrap">{fechaHora(e.fecha)}</td>
                    <td>{e.usuario_nombre}</td>
                    <td><Codigo>{e.accion}</Codigo><span className="block text-[12px] text-texto-3">{e.objeto}</span></td>
                    <td className="max-w-80"><span className="line-clamp-2">{e.detalle || e.motivo || "—"}</span></td>
                    <td><Insignia tono={TONO_RESULTADO[e.resultado as keyof typeof TONO_RESULTADO] ?? "neutro"} punto>{e.resultado}</Insignia></td>
                  </tr>
                ))}
              </tbody>
            </Tabla>
            <div className="flex justify-between border-t border-line px-5 py-3">
              <Boton tamano="sm" disabled={antesDe === null} onClick={() => setAntesDe(null)}>Más recientes</Boton>
              <Boton tamano="sm" disabled={eventos.datos.length < 50} onClick={() => setAntesDe(eventos.datos![eventos.datos!.length - 1].secuencia)}>Anteriores</Boton>
            </div>
          </>
        )}
      </Tarjeta>
      {detalle && (
        <Modal abierto ancho="lg" alCerrar={() => setDetalle(null)} titulo={`Evento ${detalle.secuencia} · ${detalle.accion}`} descripcion={fechaHora(detalle.fecha)}>
          <dl className="grid gap-3 text-[13px] sm:grid-cols-2">
            {[
              ["Persona", detalle.usuario_nombre],
              ["Objeto", `${detalle.objeto}${detalle.objeto_id ? ` · ${detalle.objeto_id}` : ""}`],
              ["Resultado", detalle.resultado],
              ["IP", detalle.ip ?? "—"],
              ["Correlación", detalle.correlacion_id ?? "—"],
              ["Motivo", detalle.motivo ?? "—"],
            ].map(([k, v]) => (
              <div key={k}><dt className="text-xs text-texto-3">{k}</dt><dd className="font-medium break-all">{v}</dd></div>
            ))}
            <div className="sm:col-span-2"><dt className="text-xs text-texto-3">Detalle</dt><dd>{detalle.detalle || "—"}</dd></div>
            {detalle.cambios && (
              <div className="sm:col-span-2">
                <dt className="mb-1 text-xs text-texto-3">Cambios (anterior → nuevo)</dt>
                <dd className="flex flex-col gap-1">
                  {Object.entries(detalle.cambios).map(([campo, par]) => (
                    <span key={campo} className="rounded-md bg-canvas px-2.5 py-1.5 font-mono text-[12px] break-all">
                      {campo}: {Array.isArray(par) ? `${JSON.stringify(par[0])} → ${JSON.stringify(par[1])}` : JSON.stringify(par)}
                    </span>
                  ))}
                </dd>
              </div>
            )}
            <div className="sm:col-span-2"><dt className="text-xs text-texto-3">Huella SHA-256</dt><dd className="font-mono text-[11.5px] break-all text-texto-2">{detalle.hash_evento}</dd></div>
          </dl>
        </Modal>
      )}
    </>
  );
}
