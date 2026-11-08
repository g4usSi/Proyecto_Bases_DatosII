import { h, ic } from '../../ui/dom.js';

export const indicadorFicha = (clase, icono, titulo, valor) => h('div', { class: `mosaico ${clase}` },
  h('dt', null, ic(icono, 15), titulo), h('dd', { text: valor }));

export const bloqueDatos = (titulo, ...contenido) => h('div', { class: 'ficha-resumen pila-s' },
  h('h3', { class: 'ficha-etiqueta', text: titulo }), contenido);

export const resumenFicha = (indicadores, titulo = 'Datos del paciente') =>
  bloqueDatos(titulo, h('dl', { class: 'mosaicos' }, indicadores));

export const accionesFicha = (acciones) => acciones.some(Boolean) && h('div', { class: 'ficha-acciones' },
  h('h3', { class: 'ficha-etiqueta', text: 'Acciones' }), h('div', { class: 'fila' }, acciones));
