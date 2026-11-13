"use client";

import { FolderPlus, Search, Waypoints } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Boton, CajaError, Cargando, Codigo, EncabezadoPagina, Insignia, Pestanas, Tabla, Tarjeta, Vacio } from "@/components/ui/basicos";
import { Entrada } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { NOMBRE_ESTADO, TONO_ESTADO } from "@/lib/estados";
import { fecha, normalizar, numero } from "@/lib/formato";
import { nombreUnidad, PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { EstadoProyecto, Proyecto } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

import { FormularioProyecto } from "./formulario";

export default function Proyectos() {
  const router = useRouter();
  const { puede } = useSesion();
  const { datos, error, cargando, recargar } = useDatos(() => api<Proyecto[]>("/proyectos"), []);
  const [filtro, setFiltro] = useState<"todos" | EstadoProyecto>("todos");
  const [texto, setTexto] = useState("");
  const [nuevo, setNuevo] = useState(false);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("nuevo")) setNuevo(true);
  }, []);

  const visibles = useMemo(() => {
    const t = normalizar(texto.trim());
    return (datos ?? []).filter((p) => (filtro === "todos" || p.estado === filtro) && (!t || normalizar(`${p.codigo} ${p.nombre} ${p.entidad_cliente} ${p.numero_contrato ?? ""}`).includes(t)));
  }, [datos, filtro, texto]);
  const cuenta = (e: EstadoProyecto) => (datos ?? []).filter((p) => p.estado === e).length;

  return (
    <>
      <EncabezadoPagina
        titulo="Proyectos"
        descripcion="Cada proyecto responde a un contrato con una entidad cliente: alcance, metas, sedes y equipo, con su historial de versiones."
        acciones={puede(PERMISOS.proyectos) && <Boton variante="primario" icono={<FolderPlus />} onClick={() => setNuevo(true)}>Nuevo proyecto</Boton>}
      />
      <Tarjeta>
        <div className="flex flex-wrap items-end justify-between gap-3 px-5 pt-3">
          <Pestanas
            valor={filtro}
            alCambiar={setFiltro}
            opciones={[
              { valor: "todos", etiqueta: `Todos (${datos?.length ?? 0})` },
              { valor: "activo", etiqueta: `Activos (${cuenta("activo")})` },
              { valor: "borrador", etiqueta: `En preparación (${cuenta("borrador")})` },
              { valor: "cerrado", etiqueta: `Cerrados (${cuenta("cerrado")})` },
            ]}
          />
          <div className="relative mb-2 w-full sm:w-72">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-texto-3" />
            <Entrada value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Código, nombre, entidad o contrato" className="pl-9" aria-label="Buscar proyecto" />
          </div>
        </div>
        {cargando && !datos ? (
          <Cargando />
        ) : error ? (
          <div className="p-5"><CajaError mensaje={error} reintentar={recargar} /></div>
        ) : !visibles.length ? (
          <Vacio
            icono={<Waypoints />}
            titulo={datos?.length ? "Ningún proyecto coincide" : "Todavía no hay proyectos"}
            descripcion={datos?.length ? "Pruebe con otro filtro o texto." : "Cree el primero con su contrato, entidad cliente y metas."}
            accion={!datos?.length && puede(PERMISOS.proyectos) ? <Boton variante="primario" icono={<FolderPlus />} onClick={() => setNuevo(true)}>Nuevo proyecto</Boton> : undefined}
          />
        ) : (
          <Tabla>
            <thead>
              <tr>
                <th>Código</th>
                <th>Proyecto</th>
                <th>Contrato</th>
                <th>Vigencia</th>
                <th>Metas</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {visibles.map((p) => (
                <tr key={p.id} className="cursor-pointer" onClick={() => router.push(`/proyectos/${p.id}`)}>
                  <td><Codigo>{p.codigo}</Codigo></td>
                  <td>
                    <span className="block font-semibold text-texto">{p.nombre}</span>
                    <span className="block text-texto-3">{p.entidad_cliente}</span>
                  </td>
                  <td>{p.numero_contrato ?? "—"}</td>
                  <td className="whitespace-nowrap">{p.fecha_inicio ? `${fecha(p.fecha_inicio)} – ${fecha(p.fecha_fin)}` : "—"}</td>
                  <td>
                    <span className="flex flex-wrap gap-1">
                      {Object.entries(p.metas).map(([u, c]) => <Insignia key={u} tono="marca">{numero(c)} {nombreUnidad(u).toLowerCase()}</Insignia>)}
                      {!Object.keys(p.metas).length && <span className="text-texto-3">—</span>}
                    </span>
                  </td>
                  <td><Insignia tono={TONO_ESTADO[p.estado]} punto>{NOMBRE_ESTADO[p.estado]}</Insignia></td>
                </tr>
              ))}
            </tbody>
          </Tabla>
        )}
      </Tarjeta>
      {nuevo && <FormularioProyecto alCerrar={() => setNuevo(false)} alGuardar={(p) => router.push(`/proyectos/${p.id}`)} />}
    </>
  );
}
