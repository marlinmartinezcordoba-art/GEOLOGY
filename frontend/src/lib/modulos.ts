/**
 * Menú de ARCA. Los módulos construidos navegan; los que vienen en los siguientes incrementos se
 * muestran en el recorrido del Inicio con su etapa, para que el equipo vea hacia dónde va la plataforma.
 */
import { PERMISOS } from "@/lib/permisos";

export type Modulo = { clave: string; nombre: string; href: string; permiso: string; grupo: "operacion" | "administracion"; codigo: string };

export const MODULOS: Modulo[] = [
  { clave: "inicio", nombre: "Inicio", href: "/inicio", permiso: "", grupo: "operacion", codigo: "M24" },
  { clave: "proyectos", nombre: "Proyectos", href: "/proyectos", permiso: PERMISOS.proyectosLeer, grupo: "operacion", codigo: "M06" },
  { clave: "consulta", nombre: "Consulta", href: "/consulta", permiso: PERMISOS.consultar, grupo: "operacion", codigo: "M23" },
  { clave: "usuarios", nombre: "Usuarios", href: "/usuarios", permiso: PERMISOS.usuarios, grupo: "administracion", codigo: "M02" },
  { clave: "roles", nombre: "Roles y permisos", href: "/roles", permiso: PERMISOS.roles, grupo: "administracion", codigo: "M02" },
  { clave: "plantillas", nombre: "Plantillas", href: "/plantillas", permiso: PERMISOS.plantillas, grupo: "administracion", codigo: "ARC-18" },
  { clave: "configuracion", nombre: "Configuración", href: "/configuracion", permiso: PERMISOS.configuracionLeer, grupo: "administracion", codigo: "M03" },
  { clave: "auditoria", nombre: "Auditoría", href: "/auditoria", permiso: PERMISOS.auditoria, grupo: "administracion", codigo: "M25" },
];

/** Recorrido del producto (Instrucciones §11). */
export const RECORRIDO: { codigo: string; nombre: string; etapa: string; listo: boolean }[] = [
  { codigo: "M01–M06", nombre: "Organización, usuarios y proyectos", etapa: "Etapa 1", listo: true },
  { codigo: "M04", nombre: "Instrumentos CCD, TRD y TVD", etapa: "Etapa 2", listo: true },
  { codigo: "M08", nombre: "Inventarios y FUID", etapa: "Incremento 2A", listo: true },
  { codigo: "M04", nombre: "Clasificación con la TRD o TVD vigente y calendario de retención", etapa: "Etapa 2", listo: true },
  { codigo: "M10–M11", nombre: "Carga desde carpeta y control de calidad", etapa: "Incremento 2A", listo: true },
  { codigo: "D-24", nombre: "Transferencias primarias y secundarias (gestión → central → histórico)", etapa: "Etapa 2", listo: true },
  { codigo: "D-33", nombre: "Disposición final: eliminación con comité y acta, selección por muestreo y digitalización", etapa: "Etapa 2", listo: true },
  { codigo: "D-25", nombre: "Hoja de control sobre lo digitalizado, con visor y origen de cada dato", etapa: "Incremento 2", listo: true },
  { codigo: "M13", nombre: "OCR local y propuesta de la hoja de control", etapa: "Incremento 2", listo: true },
  { codigo: "D-26", nombre: "Procesos por lote y descripción ISAD(G) sobre lo digitalizado", etapa: "Incremento 2", listo: true },
  { codigo: "M23", nombre: "Consulta: búsqueda en metadatos, OCR, hoja y descripción, con acceso según la TRD", etapa: "Etapa 5", listo: true },
  { codigo: "Flujo", nombre: "Flujo automático: al cargar, calidad, OCR, hoja de control y descripción propuestos sin intervención", etapa: "Incremento 2", listo: true },
  { codigo: "Entrega", nombre: "Paquete de entrega digital por expediente (PDF/A, índice, metadatos y huellas) para el SGDEA", etapa: "Siguiente", listo: false },
  { codigo: "ARC-18", nombre: "FUID de salida y rótulos con plantillas versionadas", etapa: "Incremento 2", listo: true },
  { codigo: "M24", nombre: "Productividad, cajas pendientes y Power BI", etapa: "Incremento 2", listo: true },
  { codigo: "M14–M16", nombre: "Segmentación, clasificación y metadatos con IA", etapa: "Etapa 4", listo: false },
];
