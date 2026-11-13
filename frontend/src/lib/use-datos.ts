"use client";

import { type DependencyList, useCallback, useEffect, useRef, useState } from "react";

/** Carga datos de la API y expone estado de carga, error y recarga. */
export function useDatos<T>(cargar: () => Promise<T>, dependencias: DependencyList) {
  const [datos, setDatos] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  const vigente = useRef(0);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const funcion = useCallback(cargar, dependencias);

  const recargar = useCallback(async () => {
    const turno = ++vigente.current;
    setCargando(true);
    try {
      const resultado = await funcion();
      if (turno === vigente.current) {
        setDatos(resultado);
        setError(null);
      }
    } catch (e) {
      if (turno === vigente.current) setError((e as Error).message);
    } finally {
      if (turno === vigente.current) setCargando(false);
    }
  }, [funcion]);

  useEffect(() => {
    void recargar();
  }, [recargar]);

  return { datos, error, cargando, recargar, setDatos };
}
