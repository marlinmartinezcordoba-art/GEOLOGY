/** Contratos de la API de ARCA (Etapa 1). Mismos nombres de campo que el backend. */

export type MembresiaResumen = { organizacion_id: string; organizacion: string; rol: string; permisos: string[] };

export type Yo = {
  id: string;
  correo: string;
  nombre_completo: string;
  es_operador: boolean;
  debe_cambiar_clave: boolean;
  mfa_activo: boolean;
  organizaciones: MembresiaResumen[];
};

export type Token = { access_token: string; token_type: string; debe_cambiar_clave: boolean };

export type Organizacion = {
  id: string;
  nombre: string;
  razon_social: string;
  tipo_identificacion: string;
  identificacion: string;
  estado: "activa" | "suspendida";
  motivo_estado: string | null;
  zona_horaria: string;
  idioma: string;
  limites: Record<string, number>;
  creado_en: string;
};

export type PerfilOrganizacion = Organizacion & { uso: Record<string, number> };

export type Miembro = {
  usuario_id: string;
  correo: string;
  nombre_completo: string;
  rol_id: string;
  rol: string;
  activa: boolean;
  proyectos: string[] | null;
  mfa_activo: boolean;
  bloqueado: boolean;
};

export type Persona = { usuario_id: string; nombre_completo: string; correo: string; rol: string };

export type Rol = { id: string; nombre: string; descripcion: string; permisos: string[]; es_base: boolean; creado_en: string };

export type EstadoProyecto = "borrador" | "activo" | "cerrado";

export type Proyecto = {
  id: string;
  codigo: string;
  nombre: string;
  entidad_cliente: string;
  numero_contrato: string | null;
  objeto: string;
  fecha_inicio: string | null;
  fecha_fin: string | null;
  metas: Record<string, number>;
  responsable_id: string | null;
  estado: EstadoProyecto;
  motivo_estado: string | null;
  version: number;
  creado_en: string;
};

export type VersionProyecto = { version: number; instantanea: Record<string, unknown>; motivo: string; creado_en: string; creado_por: string | null };
export type Sede = { id: string; nombre: string; ciudad: string; direccion: string; activa: boolean };
export type MiembroProyecto = { id: string; usuario_id: string; funcion: string; activo: boolean };

export type Parametro = {
  id: string;
  clave: string;
  version: number;
  valor: unknown;
  vigente_desde: string;
  proyecto_id: string | null;
  motivo: string;
  creado_en: string;
  creado_por: string | null;
};

export type EventoAuditoria = {
  secuencia: number;
  fecha: string;
  usuario_id: string | null;
  usuario_nombre: string;
  accion: string;
  objeto: string;
  objeto_id: string | null;
  detalle: string;
  motivo: string | null;
  cambios: Record<string, unknown> | null;
  resultado: string;
  ip: string | null;
  correlacion_id: string | null;
  hash_evento: string;
};

export type Verificacion = { integra: boolean; revisados: number; sellos_verificados: number; problema: string | null; secuencia: number | null };

export type Lote = {
  id: string;
  nombre_archivo: string;
  hoja: string | null;
  fila_encabezado: number;
  encabezados: string[];
  mapeo: Record<string, number>;
  estado: "validado" | "con_errores" | "integrado" | "descartado";
  total_filas: number;
  filas_validas: number;
  filas_con_error: number;
  filas_integradas: number;
  motivo_estado: string | null;
  creado_en: string;
};

export type FilaFuid = { numero_fila: number; original: string[]; normalizado: Record<string, string | number | null>; errores: string[]; avisos: string[]; unidad_id: string | null };

export type Unidad = {
  id: string;
  identificador: string;
  numero_orden: string | null;
  codigo_serie: string | null;
  nombre: string;
  fecha_inicial: string | null;
  fecha_final: string | null;
  caja: string | null;
  carpeta: string | null;
  tomo: string | null;
  otro: string | null;
  folios: number | null;
  soporte: string;
  notas: string | null;
};

export type Hallazgo = { codigo: string; gravedad: "error" | "revisar" | "aviso"; mensaje: string; pagina: number | null };

export type EstadoRecurso = "aprobado" | "en_revision" | "rechazado" | "recaptura" | "reemplazado" | "sin_identificar";

export type Recurso = {
  id: string;
  unidad_id: string | null;
  unidad_identificador: string | null;
  ruta_original: string;
  modalidad: "pdf" | "imagen";
  parte: number;
  pagina: number | null;
  paginas: number;
  ficha: { dpi_minimo?: number | null; color?: number; proporcion_blanco?: number | null; capa_de_texto?: boolean; error?: string };
  hallazgos: Hallazgo[];
  estado: EstadoRecurso;
  perfil_version: number | null;
  reemplaza_id: string | null;
  decidido_por: string | null;
  motivo_decision: string | null;
  creado_en: string;
};

export type UnidadAvance = { id: string; identificador: string; nombre: string; folios: number | null; caja: string | null; carpeta: string | null; archivos: number; imagenes: number; estado: "sin_imagenes" | "en_revision" | "recaptura" | "aprobada"; alertas: Hallazgo[] };

export type ResumenDigitalizacion = { por_estado: Record<string, number>; unidades: number; unidades_con_imagenes: number; unidades_con_pendientes: number; unidades_aprobadas: number; imagenes: number };

export type PerfilDigitalizacion = {
  modalidades: ("pdf" | "imagenes")[];
  formatos: string[];
  dpi_minimo: number;
  color_minimo: "cualquiera" | "grises" | "color";
  detectar_blancos: boolean;
  umbral_blanco: number;
  comparar_folios: boolean;
  identificar_por: "archivo_o_carpeta" | "carpeta" | "archivo";
  rechazo_automatico: string[];
};

export type RespuestaPerfil = { perfil: PerfilDigitalizacion; version: number | null; por_defecto: PerfilDigitalizacion; hallazgos: Record<string, string> };

export type ReporteCarga = { ruta: string; resultado: "recibido" | "duplicado" | "ignorado" | "rechazado"; recurso_id?: string; unidad?: string | null; estado?: EstadoRecurso; hallazgos?: string[]; detalle?: string };

export type TipoPlantilla = { nombre: string; encabezado: Record<string, string>; fila: Record<string, string> };
export type VersionPlantilla = { id: string; version: number; codigo_formato: string; campos: string[]; valores_fijos: Record<string, string>; vigente_desde: string; estado: "vigente" | "reemplazada" | "programada"; motivo: string; creado_en: string };
export type Plantilla = { id: string; tipo: string; nombre: string; descripcion: string; proyecto_id: string | null; creado_en: string; versiones: VersionPlantilla[] };
export type PaqueteEntrega = {
  id: string; numero: number; estado: "en_cola" | "listo" | "error"; filtro: { cajas?: string[]; lote?: string; solo_listos?: boolean }; unidades: number;
  pendientes: { identificador: string; motivo: string }[]; error: string; resumen?: { pdfa?: { nivel: string; conformes: number; total: number }; con_texto?: boolean }; creado_en: string; terminado_en: string | null; nombre_archivo: string | null; tamano: number | null; sha256: string | null;
};
export type ValidacionPdfa = {
  archivo: string; bytes: number; nivel: string; conforme: boolean; veredicto: "conforme" | "no_conforme" | "no_verificado"; validado_con: string; aviso?: string;
  hallazgos: { regla: string; area: string; explicacion: string; donde: string; mensaje: string; tipo: "incumple" | "no verificado" }[];
};
export type Expedicion = { id: string; tipo: string; elementos: number; filtro: { cajas?: string[]; lote?: string }; creado_en: string; plantilla_version: number; codigo_formato: string; nombre_archivo: string; sha256: string };

export type EstadoVersionInstrumento = "borrador" | "programada" | "vigente" | "reemplazada" | "descartada";
export type VersionInstrumento = {
  id: string; version: number; estado: EstadoVersionInstrumento; totales: { dependencias?: number; series?: number; subseries?: number; tipos_documentales?: number };
  errores: string[]; avisos: string[]; correcciones: string[]; motivo: string; acto_administrativo: string | null; fecha_acto: string | null; convalidacion: string | null;
  vigente_desde: string | null; creado_en: string; creado_por: string | null; aprobado_en: string | null; aprobado_por: string | null;
};
export type Instrumento = { id: string; tipo: "TRD" | "TVD" | "CCD"; nombre: string; descripcion: string; periodo_desde: string | null; periodo_hasta: string | null; creado_en: string; versiones: VersionInstrumento[] };
export type ElementoInstrumento = {
  nivel: "dependencia" | "serie" | "subserie"; codigo: string; nombre: string; codigo_dependencia: string; padre: string | null; tipos_documentales: string[];
  retencion_gestion: number | null; retencion_central: number | null; disposicion: string | null; soporte: string | null; procedimiento: string; acceso: string; hoja: string; fila: number | null;
};
export type DetalleVersionInstrumento = VersionInstrumento & { nombre_archivo: string; sha256: string; elementos: ElementoInstrumento[] };
type ResumenElemento = { nivel: string; codigo: string; nombre: string; disposicion: string | null };
export type ComparacionInstrumento = { desde: number; hasta: number; nuevas: ResumenElemento[]; retiradas: ResumenElemento[]; modificadas: { nivel: string; codigo: string; nombre: string; cambios: Record<string, [unknown, unknown]> }[] };

export type SituacionClasificacion = "pendiente" | "propuesta" | "confirmada" | "version_anterior";
export type CalendarioRetencion = { fin_gestion: string | null; fin_central: string | null; fase: "gestion" | "central" | "cumplida" | null; disposicion: string | null; nota: string };
export type FilaClasificacion = {
  unidad: { id: string; identificador: string; numero_orden: string | null; nombre: string; codigo_serie: string | null; fecha_inicial: string | null; fecha_final: string | null; caja: string | null; carpeta: string | null; folios: number | null };
  clasificacion: null | {
    id: string; estado: "propuesta" | "confirmada"; origen: "inventario" | "codigo" | "motor" | "manual" | "actualizacion"; confianza: "alta" | "media" | "baja" | null; porque: string;
    elemento_id: string; codigo: string; nombre: string; nivel: string; serie: string | null; dependencia: string; instrumento: string; version: number; version_vigente: boolean;
    calendario: CalendarioRetencion; creado_en: string; decidido_en: string | null;
  };
  situacion: SituacionClasificacion;
  alertas: string[];
};
export type ResumenClasificacion = {
  unidades: number; pendiente: number; propuesta: number; confirmada: number; version_anterior: number; con_alertas: number;
  fases: { gestion: number; central: number; cumplida: number };
  instrumentos: { instrumento: string; version: number; acto: string | null; periodo_desde: string | null; periodo_hasta: string | null }[];
};
export type OpcionesClasificacion = { instrumento_id: string; instrumento: string; version: number; elementos: { id: string; codigo: string; nombre: string; nivel: string; serie: string | null; serie_nombre: string | null; dependencia: string; disposicion: string | null }[] }[];

export type FaseCiclo = "gestion" | "central" | "historico";
export type PlanTransferencias = {
  fecha_corte: string; fases: Record<FaseCiclo, number>; sin_clasificar: number;
  tipos: Record<"primaria" | "secundaria", { elegibles: number; anticipables: number; sin_calendario: number; por_dependencia: { codigo: string; dependencia: string; elegibles: number; folios: number }[] }>;
};
export type Transferencia = {
  id: string; numero: number; tipo: "primaria" | "secundaria"; estado: "borrador" | "enviada" | "devuelta" | "recibida" | "anulada"; codigo_dependencia: string; dependencia: string;
  fecha_corte: string; observaciones: string; novedad: string; creado_en: string; creado_por: string | null; enviada_en: string | null; enviada_por: string | null;
  recibida_en: string | null; recibida_por: string | null; resumen: { unidades: number; folios: number; anticipadas: number; recibidas: number; devueltas: number; cajas: number };
};
export type UnidadTransferencia = {
  unidad_id: string; identificador: string; nombre: string; caja: string | null; carpeta: string | null; folios: number | null; fecha_inicial: string | null; fecha_final: string | null;
  fase: FaseCiclo; elegible: boolean; aviso: string; estado: "incluida" | "recibida" | "devuelta"; observacion: string;
};
export type CandidataTransferencia = { unidad_id: string; identificador: string; nombre: string; caja: string | null; folios: number | null; elegible: boolean; aviso: string };

export type TipoDisposicion = "eliminacion" | "seleccion" | "digitalizacion";
export type PlanDisposicion = {
  fecha_corte: string; eliminadas: number; seleccionadas: number; digitalizadas: number;
  tipos: Record<TipoDisposicion, { elegibles: number; folios: number; por_cumplir: number; sin_calendario: number; por_serie: { codigo: string; nombre: string; unidades: number; procedimiento: string }[] }>;
};
export type ProcesoDisposicion = {
  id: string; numero: number; tipo: TipoDisposicion; estado: "borrador" | "aprobado" | "publicado" | "ejecutado" | "anulado"; fecha_corte: string; observaciones: string;
  origen_id: string | null; comite_acta: string | null; comite_fecha: string | null; aprobado_en: string | null; publicacion_inicio: string | null; publicacion_dias: number | null;
  publicacion_fin: string | null; publicacion_enlace: string | null; muestreo: { porcentaje?: number; semilla?: number; criterio?: string; propuestas?: number; universo?: number; ajustada?: boolean };
  destino_fisico: string | null; metodo: string | null; acta_numero: string | null; ejecutado_en: string | null; novedad: string; creado_en: string; creado_por: string | null;
  resumen: { unidades: number; folios: number; cajas: number; incluida: number; retirada: number; seleccionada: number; no_seleccionada: number; ejecutada: number };
};
export type UnidadDisposicion = {
  unidad_id: string; identificador: string; nombre: string; caja: string | null; carpeta: string | null; folios: number | null; fecha_inicial: string | null; fecha_final: string | null;
  fase: string; estado: "incluida" | "retirada" | "seleccionada" | "no_seleccionada" | "ejecutada"; aviso: string; observacion: string;
};

export type OrigenDato = { fuente: "persona" | "calculado" | "trd" | "importado" | string; detalle: string };
export type TramiteHoja = {
  id: string; orden: number; fecha: string | null; fecha_texto: string | null; tipo_documental: string; detalle: string; folio_desde: number | null; folio_hasta: number | null;
  pagina_desde: number | null; pagina_hasta: number | null; no_radicado: string; observaciones: string; origen: Record<string, OrigenDato>;
  metadatos: Partial<Record<"asunto" | "remitente" | "destinatario" | "firmantes" | "lugar" | "numero", string>>;
  revision: "pendiente" | "conforme" | "observada"; observacion_revision: string;
};
export type MetadatoHoja = { campo: string; etiqueta: string; valor: string | number | null; fuente: string; detalle: string; alerta?: string | null };
export type EstadoHoja = "sin_hoja" | "borrador" | "en_revision" | "devuelta" | "verificada" | "no_aplica";
export type DetalleHoja = {
  unidad: { id: string; identificador: string; nombre: string; caja: string | null; carpeta: string | null; folios: number | null };
  hoja: null | { id: string; estado: Exclude<EstadoHoja, "sin_hoja">; imagenes_por_folio: number; origen: string; importacion: { archivo?: string; pestana?: string; sha256?: string }; novedad: string;
    total_folios: number | null; creado_por: string | null; enviada_por: string | null; enviada_en: string | null; verificada_en: string | null; verificada_por: string | null };
  tramites: TramiteHoja[];
  validacion: null | { errores: { tramite_id: string | null; orden: number | null; campo: string; mensaje: string }[]; avisos: string[]; correcciones: string[]; total_folios: number;
    fecha_inicial: string | null; fecha_final: string | null; sin_fecha: number; diferencia_folios: string; paginas: number };
  metadatos: MetadatoHoja[];
  paginas: { n: number; recurso_id: string; pagina_en_archivo: number; archivo: string; estado: string; modalidad: string }[];
  tipos_documentales: string[];
};
export type FilaBandejaHoja = { unidad_id: string; identificador: string; nombre: string; caja: string | null; carpeta: string | null; folios_fuid: number | null; imagenes: number;
  estado: EstadoHoja; hoja_id: string | null; tramites: number; total_folios: number | null; novedad: string };

export type TextoOcr = { n: number; estado: "pendiente" | "leida" | "sin_texto" | "error"; texto: string; confianza: number | null; palabras: number; lineas: [string, number][]; motor: string; detalle: string };
export type ResumenOcr = { disponible: boolean; motor: string; idiomas: string[]; paginas: number; leidas: number; sin_texto: number; errores: number; pendientes: number; confianza_media: number | null; confianza_baja: number };

export type ProcesoLote = { lote: string; nombre: string; hoja_control: boolean; isadg: boolean; configurado: boolean; cajas: number; unidades: number; motivo: string };
export type EstadoDescripcion = "no_aplica" | "sin_descripcion" | "borrador" | "en_revision" | "devuelta" | "aprobada";
export type FilaDescripcion = { unidad_id: string; identificador: string; nombre: string; caja: string | null; lote: string; estado: EstadoDescripcion; titulo: string; hoja_control: string | null; fase: string; novedad: string };
export type HallazgoIsad = { gravedad: "DEVUELVE" | "REVISE"; regla: string; que_pasa: string; como_se_arregla: string };
export type DetalleDescripcion = {
  unidad: { id: string; identificador: string; nombre: string; caja: string | null; carpeta: string | null; fase: string };
  procesos: { lote: string; hoja_control: boolean; isadg: boolean; origen: string };
  elementos: { clave: string; numero: string; etiqueta: string; area: string; editable: boolean }[];
  descripcion: null | { id: string; estado: Exclude<EstadoDescripcion, "no_aplica" | "sin_descripcion">; campos: Record<string, string>; origen: Record<string, OrigenDato>;
    observaciones: Record<string, string>; novedad: string; creado_por: string | null; enviada_por: string | null; aprobada_en: string | null };
  revision: null | { hallazgos: HallazgoIsad[]; devuelve: number; revise: number; por_confirmar: string[] };
  avisos: string[];
};

export type FuenteConsulta = "metadatos" | "ocr" | "hoja" | "descripcion";
export type FilaConsulta = {
  unidad_id: string; proyecto_id: string; proyecto: string; identificador: string; nombre: string; caja: string | null; carpeta: string | null; fecha_inicial: string | null;
  fecha_final: string | null; folios: number | null; fase: string; clasificacion: string | null; dependencia: string | null; acceso: string; reservada: boolean;
  contenido_visible: boolean; imagenes: number; hoja_verificada: boolean; titulo: string | null; coincidencias: { fuente: FuenteConsulta; donde: string; pagina: number | null; fragmento: string }[];
};
export type ResultadoConsulta = { total: number; filas: FilaConsulta[]; terminos: string[]; indice: { reindexadas: number; pendientes: number } };
export type FichaConsulta = {
  proyecto: { id: string; codigo: string; nombre: string; entidad: string };
  unidad: { id: string; identificador: string; numero_orden: string | null; nombre: string; codigo_serie: string | null; fecha_inicial: string | null; fecha_final: string | null; caja: string | null;
    carpeta: string | null; tomo: string | null; folios: number | null; soporte: string; notas: string | null; fase: string; fase_nombre: string; disposicion_aplicada: string | null };
  clasificacion: null | { codigo: string; nombre: string; nivel: string; serie: string; dependencia: string; instrumento: string; acceso: string; disposicion: string | null; calendario: CalendarioRetencion | null };
  reservada: boolean; contenido_visible: boolean;
  historial: { desde: string | null; hasta: string; motivo: string; fecha: string }[];
  hoja_control: { verificada: boolean; total_folios: number | null; tramites: { orden: number; fecha: string | null; tipo_documental: string; detalle: string; folio_desde: number | null; folio_hasta: number | null; pagina_desde: number | null; no_radicado: string; observaciones: string }[] };
  descripcion: Record<string, string> | null;
  paginas: { n: number; archivo: string; pagina_en_archivo: number }[];
};

export type TableroFlujo = {
  etapas: { clave: string; nombre: string; espera_persona: boolean; unidades: number }[];
  cola: { pendientes: number; en_curso: number; hechos: number; errores: number };
  ultimo: string | null; trabajador: string; procesados?: number;
};
export type UnidadFlujo = { unidad_id: string; identificador: string; nombre: string; caja: string | null; etapa: string; etapa_nombre: string; espera_persona: boolean; detalle: string; hechos: { fecha: string; que: string }[]; actualizado_en: string };

export type DefectoCatalogo = { codigo: string; nombre: string; severidad: string };
export type PlanMuestreo = {
  unidad: "expedientes" | "imagenes"; metodo: "porcentaje" | "tabla"; porcentaje: number; minimo: number; tabla: { desde: number; hasta: number; muestra: number }[];
  aceptacion: { critico: number; mayor: number; menor: number }; defectos: DefectoCatalogo[]; frente: string; exigir_para_entrega: boolean; version?: number;
};
export type VistaPlanMuestreo = { vigente: boolean; plan: PlanMuestreo; aviso?: string; motivo?: string; actualizado_en?: string };
export type LoteInspeccion = {
  lote: string; cajas: number; expedientes: number; imagenes: number;
  ultima: { id: string; numero: number; estado: "aceptada" | "rechazada"; cerrada_en: string | null } | null; abierta: { id: string; numero: number } | null;
};
export type InspeccionResumen = {
  id: string; numero: number; lote: string; estado: "abierta" | "aceptada" | "rechazada" | "anulada"; unidad: string; tamano: number; muestra: number; revisados: number;
  semilla: number; criticos: number; mayores: number; menores: number; limitaciones: number; reinspeccion_de: string | null; creado_en: string; cerrada_en: string | null;
};
export type ItemMuestra = {
  id: string; orden: number; unidad_id: string; identificador: string; nombre: string; caja: string | null; pagina: number | null; paginas: number;
  estado: "pendiente" | "revisado"; defectos: { codigo: string; nombre: string; severidad: string; pagina: number | null; nota: string }[]; revisado_por: string | null; revisado_en: string | null;
};
export type DetalleInspeccion = {
  id: string; numero: number; lote: string; estado: InspeccionResumen["estado"]; plan: PlanMuestreo; tamano: number; muestra: number; semilla: number;
  reinspeccion_de: string | null; observaciones: string; creado_en: string; creado_por: string | null; cerrada_en: string | null; cerrada_por: string | null;
  conteo: { critico: number; mayor: number; menor: number; limitacion: number }; revisados: number; resultado_previsto: string; razones: string[]; items: ItemMuestra[];
};

export type ConfigHistorias = {
  configurado: boolean; activo: boolean; series: string[]; tipos_obligatorios: string[]; motivo?: string; tipos_de_la_trd: string[]; aviso: string; tipos_documento: Record<string, string>;
};
export type TitularHistoria = {
  tipo_documento: string; numero_documento: string; nombres: string; cargo: string; dependencia: string; fecha_vinculacion: string | null; fecha_retiro: string | null;
  estado: "propuesto" | "confirmado"; origen: Record<string, { fuente: string; detalle: string }>; confirmado_en: string | null;
};
export type ExpedienteHistoria = {
  unidad_id: string; identificador: string; nombre: string; caja: string | null; titular: TitularHistoria | null;
  completitud: { obligatorios: number; presentes: number; faltan: string[]; hoja: string | null }; documentos_encontrados: { numero: string; paginas: number[] }[];
  paginas_leidas: number; alertas: { clase: string; paginas: number[]; mensaje: string }[];
};

export type ActividadAlistamiento = { codigo: string; nombre: string; cantidad: "ninguna" | "folios" | "unidades"; obligatoria: boolean };
export type PlanAlistamientoVista = { vigente: boolean; actividades: ActividadAlistamiento[]; exigir_para_entrega: boolean; version?: number; motivo?: string; aviso?: string };
export type AvanceAlistamiento = {
  actividades: ActividadAlistamiento[]; resumen: { expedientes: number; completos: number; por_actividad: Record<string, number> };
  cajas: { caja: string; expedientes: number; hechas: Record<string, number>; completos: number }[];
};
export type ExpedienteAlistamiento = {
  unidad_id: string; identificador: string; nombre: string; carpeta: string | null; folios_fuid: number | null;
  hechas: Record<string, { cantidad: number | null; observacion: string; hecho_en: string; hecho_por: string | null }>;
};
