/* Piezas compartidas por las pantallas del Hospital General. */
import { h } from '../../ui/dom.js';
import { chip } from '../../ui/componentes.js';

export const ESTADOS_CAMA = {
  disponible: { clase: 'ok', icono: 'check', texto: 'Disponible', filtro: 'Disponibles' },
  ocupada: { clase: 'info', icono: 'bed-double', texto: 'Ocupada', filtro: 'Ocupadas' },
  limpieza: { clase: 'aviso', icono: 'refresh-cw', texto: 'En limpieza', filtro: 'En limpieza' },
  mantenimiento: { clase: '', icono: 'ban', texto: 'Mantenimiento', filtro: 'Mantenimiento' },
};

export const TIPOS_INGRESO = {
  emergencia: { clase: 'crit', icono: 'siren', texto: 'Emergencia' },
  programado: { clase: 'info', icono: 'calendar-days', texto: 'Programado' },
  traslado: { clase: '', icono: 'building-2', texto: 'Traslado' },
};

export const TIPOS_ORDEN_MEDICA = {
  medicamento: 'Medicamento',
  examen: 'Examen',
  procedimiento: 'Procedimiento',
  interconsulta: 'Interconsulta',
};

export const GRUPOS_SANGUINEOS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];

export const chipDe = (mapa, clave) => {
  const e = mapa[clave] || { clase: '', texto: clave };
  return chip(e.clase, e.icono, e.texto);
};

export const rutaPaciente = (id) => `/pacientes/${encodeURIComponent(id)}`;

/* Tiempo transcurrido: la API entrega el instante de ingreso y el cliente calcula la estancia. */
export function duracion(desde, hasta = Date.now()) {
  const minutos = Math.max(0, Math.floor((new Date(hasta) - new Date(desde)) / 60000));
  if (minutos < 60) return `${minutos} min`;
  const horas = Math.floor(minutos / 60);
  if (horas < 48) return `${horas} h ${minutos % 60} min`;
  return `${Math.floor(horas / 24)} días`;
}
export const horasDesde = (desde) => (Date.now() - new Date(desde)) / 3600000;

/* La pulsera muestra el grupo sanguineo; sin dato se distingue de un grupo conocido. */
export const pulsera = (grupo) => h('span', { class: `grupo-sangre ${grupo ? '' : 'sin-dato'}`, title: 'Grupo sanguíneo' },
  h('b', { text: grupo || '?' }), h('small', { text: grupo ? 'Grupo' : 'Sin dato' }));
