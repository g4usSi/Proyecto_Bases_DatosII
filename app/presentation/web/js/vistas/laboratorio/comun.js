/* Piezas compartidas por las pantallas del Laboratorio Clinico. */
import { h } from '../../ui/dom.js';
import { chip } from '../../ui/componentes.js';

export const ESTADOS_ORDEN = {
  solicitada: { clase: 'info', icono: 'clock', texto: 'Solicitada', filtro: 'Solicitadas' },
  en_proceso: { clase: 'aviso', icono: 'hourglass', texto: 'En proceso', filtro: 'En proceso' },
  validada: { clase: 'ok', icono: 'badge-check', texto: 'Validada', filtro: 'Validadas' },
  cancelada: { clase: '', icono: 'ban', texto: 'Cancelada', filtro: 'Canceladas' },
};
export const ABIERTAS = ['solicitada', 'en_proceso'];
export const estaAbierta = (orden) => ABIERTAS.includes(orden.estado);

export const chipOrden = (estado) => {
  const e = ESTADOS_ORDEN[estado] || { clase: '', texto: estado };
  return chip(e.clase, e.icono, e.texto);
};

const LECTURAS = {
  bajo: { clase: 'aviso', icono: 'chevron-down', texto: 'Bajo' },
  normal: { clase: 'ok', icono: 'check', texto: 'Normal' },
  alto: { clase: 'crit', icono: 'triangle-alert', texto: 'Alto' },
};
export const chipLectura = (interpretacion) => {
  const l = LECTURAS[interpretacion];
  return l ? chip(l.clase, l.icono, l.texto) : h('span', { class: 'hint', text: '—' });
};

export const rutaOrden = (idPaciente, idOrden) =>
  `/pacientes/${encodeURIComponent(idPaciente)}/ordenes${idOrden ? `/${encodeURIComponent(idOrden)}` : ''}`;

const numero = (n) => (Number.isInteger(n) ? String(n) : String(n).replace('.', ','));

/* Rango o descripcion de referencia, con su unidad y la poblacion a la que aplica. */
export function textoReferencia(ref, unidad) {
  if (!ref) return '—';
  const u = unidad ? ` ${unidad}` : '';
  let rango = ref.descripcion || '';
  if (ref.minimo != null && ref.maximo != null) rango = `${numero(ref.minimo)} – ${numero(ref.maximo)}${u}`;
  else if (ref.minimo != null) rango = `≥ ${numero(ref.minimo)}${u}`;
  else if (ref.maximo != null) rango = `≤ ${numero(ref.maximo)}${u}`;
  return [rango || '—', ref.poblacion && `(${ref.poblacion})`].filter(Boolean).join(' ');
}

export function textoValor(r) {
  if (r.tipo_valor === 'booleano') return r.valor ? 'Positivo' : 'Negativo';
  if (r.tipo_valor === 'numerico') return `${numero(r.valor)}${r.unidad ? ` ${r.unidad}` : ''}`;
  return String(r.valor);
}

export const TIPOS_VALOR = { numerico: 'Numérico', texto: 'Texto', booleano: 'Positivo / negativo' };
