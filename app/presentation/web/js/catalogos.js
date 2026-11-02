/* Textos para la persona y reglas de seleccion. Las reglas repiten app/domain/administracion.py
   solo para ofrecer opciones validas: el servidor las vuelve a comprobar en cada peticion. */

export const ENTIDADES = [
  { id: 'hospital_general', nombre: 'Hospital General', corto: 'Hospital', tema: 'hospital', motor: 'PostgreSQL', emblema: 'hospital' },
  { id: 'centro_pediatrico', nombre: 'Centro Pediátrico', corto: 'Pediátrico', tema: 'pediatrico', motor: 'MySQL', emblema: 'baby' },
  { id: 'laboratorio_clinico', nombre: 'Laboratorio Clínico', corto: 'Laboratorio', tema: 'laboratorio', motor: 'MongoDB', emblema: 'flask-conical' },
  { id: 'clinica_odontologica', nombre: 'Clínica Odontológica', corto: 'Clínica', tema: 'dental', motor: 'Firestore', emblema: 'diente' },
];
export const entidad = (id) => ENTIDADES.find((e) => e.id === id);

export const ROLES = {
  medico: 'Médico/a',
  enfermeria: 'Enfermería',
  laboratorista: 'Laboratorista',
  odontologo: 'Odontólogo/a',
  secretaria: 'Secretaría',
  administrador: 'Administrador/a',
  superusuario: 'Superusuario',
};
export const ROLES_POR_ENTIDAD = {
  hospital_general: ['medico', 'enfermeria'],
  centro_pediatrico: ['medico', 'enfermeria'],
  laboratorio_clinico: ['laboratorista', 'medico'],
  clinica_odontologica: ['odontologo', 'secretaria'],
};
export const textoRol = (rol) => ROLES[rol] || rol;

export const PERMISOS = {
  'pacientes:leer': { texto: 'Ver pacientes', ayuda: 'Base de todo el personal.' },
  'pacientes:registrar': { texto: 'Registrar y corregir pacientes' },
  'historiales:leer': { texto: 'Ver historiales y alergias' },
  'consultas:registrar': { texto: 'Registrar consultas y adendas' },
  'historiales:archivar': { texto: 'Archivar historiales' },
  'citas:leer': { texto: 'Ver citas' },
  'citas:gestionar': { texto: 'Agendar y cambiar citas' },
  'camas:gestionar': { texto: 'Gestionar camas', ayuda: 'Limpieza, mantenimiento y disponibilidad.' },
  'pagos:ver': { texto: 'Ver montos de cobros y pagos' },
  'pagos:registrar': { texto: 'Registrar pagos' },
  'laboratorio:resultados': { texto: 'Tomar muestras y registrar resultados' },
  'laboratorio:validar': { texto: 'Validar órdenes', ayuda: 'Una orden validada ya no se modifica.' },
};
const COMUNES = ['pacientes:leer', 'pacientes:registrar', 'historiales:leer', 'consultas:registrar', 'historiales:archivar', 'citas:leer', 'citas:gestionar'];
export const PERMISOS_ASIGNABLES = {
  hospital_general: [...COMUNES, 'camas:gestionar', 'pagos:ver', 'pagos:registrar'],
  centro_pediatrico: [...COMUNES, 'pagos:ver', 'pagos:registrar'],
  laboratorio_clinico: [...COMUNES, 'laboratorio:resultados', 'laboratorio:validar'],
  clinica_odontologica: COMUNES,
};
export const VEDADOS_SECRETARIA = ['historiales:leer', 'consultas:registrar', 'historiales:archivar', 'laboratorio:resultados', 'laboratorio:validar'];
export const PERMISOS_SUGERIDOS = {
  medico: ['pacientes:leer', 'pacientes:registrar', 'historiales:leer', 'consultas:registrar', 'citas:leer', 'citas:gestionar'],
  enfermeria: ['pacientes:leer', 'historiales:leer', 'citas:leer'],
  odontologo: ['pacientes:leer', 'pacientes:registrar', 'historiales:leer', 'consultas:registrar', 'citas:leer', 'citas:gestionar'],
  laboratorista: ['pacientes:leer', 'laboratorio:resultados', 'laboratorio:validar'],
  secretaria: ['pacientes:leer', 'pacientes:registrar', 'citas:leer', 'citas:gestionar'],
};

export const ESTADOS_CUENTA = {
  activa: { clase: 'ok', icono: 'circle-check', texto: 'Activa' },
  bloqueada: { clase: 'crit', icono: 'ban', texto: 'Bloqueada' },
  inactiva: { clase: '', icono: 'ban', texto: 'Deshabilitada' },
  eliminada: { clase: '', icono: 'trash-2', texto: 'Eliminada' },
};

export const ACCIONES_BITACORA = {
  alta: { clase: 'ok', icono: 'user-plus', texto: 'Alta', filtro: 'Altas' },
  cambio: { clase: 'info', icono: 'pencil', texto: 'Cambio', filtro: 'Cambios' },
  restablecer_contrasena: { clase: 'aviso', icono: 'key-round', texto: 'Contraseña restablecida', filtro: 'Restablecidas' },
  cambiar_contrasena: { clase: '', icono: 'key-round', texto: 'Cambió su contraseña', filtro: 'Cambió la suya' },
  eliminar: { clase: 'crit', icono: 'trash-2', texto: 'Eliminación', filtro: 'Eliminaciones' },
};

export const ESTADOS_COBRO = {
  abierto: { clase: 'aviso', icono: 'clock', texto: 'Abierto' },
  cerrado: { clase: 'info', icono: 'lock', texto: 'Cerrado' },
  pagado: { clase: 'ok', icono: 'circle-check', texto: 'Pagado' },
  anulado: { clase: '', icono: 'ban', texto: 'Anulado' },
};
export const METODOS_PAGO = { efectivo: 'Efectivo', tarjeta: 'Tarjeta', transferencia: 'Transferencia', cheque: 'Cheque' };
