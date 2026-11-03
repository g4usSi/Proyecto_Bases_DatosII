/* Piezas compartidas por las pantallas de la clinica. */
import { api } from '../../api.js';
import { sesion } from '../../sesion.js';
import { h, ic } from '../../ui/dom.js';
import { chip, mostrarErrorDeFormulario } from '../../ui/componentes.js';

export const ESTADOS_CITA = {
  programada: { clase: 'info', icono: 'clock', texto: 'Programada' },
  confirmada: { clase: 'info', icono: 'circle-check', texto: 'Confirmada' },
  atendida: { clase: 'ok', icono: 'circle-check', texto: 'Atendida' },
  cancelada: { clase: '', icono: 'ban', texto: 'Cancelada' },
  no_asistio: { clase: 'aviso', icono: 'triangle-alert', texto: 'No asistió' },
};
export const chipCita = (estado) => {
  const e = ESTADOS_CITA[estado] || { clase: '', texto: estado };
  return chip(e.clase, e.icono, e.texto);
};
export const claseCita = (estado) => ({ cancelada: 'cancelada', no_asistio: 'ausente', atendida: 'atendida' })[estado] || '';
export const estaPorAtender = (cita) => cita.estado === 'programada' || cita.estado === 'confirmada';

/* Sin lista (falta citas:leer o el servicio fallo) los nombres caen a la marca corta. */
export const cargarProfesionales = () => (sesion.tiene('citas:leer')
  ? api('/citas/profesionales').catch((error) => {
    if (error.estado === 401) throw error;
    return [];
  })
  : Promise.resolve([]));

/* Las cuentas dadas de baja no vienen en la lista: se muestran con la marca del mockup. */
export function nombreProfesional(lista, id) {
  if (!id) return '—';
  const p = lista.find((x) => x.id_profesional === id);
  return p ? `${p.nombres} ${p.apellidos}`.trim() : `Profesional ·${String(id).slice(0, 4)}`;
}

let secuencia = 0;
export const nuevoId = (prefijo) => `${prefijo}-${++secuencia}`;

export const areaTexto = (id, atributos = {}) => h('textarea', { class: 'in', id, rows: 3, ...atributos });

/* Deshabilita el boton mientras guarda y deja el error junto a su campo o en la zona de aviso. */
export async function enviar(boton, zona, campos, accion) {
  boton.disabled = true;
  zona.replaceChildren();
  Object.values(campos).forEach((c) => c.marcar(null));
  try {
    await accion();
  } catch (error) {
    mostrarErrorDeFormulario(error, campos, zona);
    boton.disabled = false;
  }
}

/* Lista de grupos de campos que se agregan y quitan. Cada fabrica devuelve { nodo, leer, validar }:
   leer -> objeto o null si la fila esta vacia; validar -> false si esta a medias. */
export function repetible(textoAgregar, fabrica, { minimo = 0 } = {}) {
  const lista = h('div', { class: 'repetibles' });
  const filas = [];

  function agregar(enfocar) {
    const fila = fabrica();
    filas.push(fila);
    const caja = h('div', { class: 'repetible' }, fila.nodo);
    if (filas.length > minimo) {
      caja.append(h('button', {
        class: 'btn tenue sm', type: 'button',
        onclick: () => {
          filas.splice(filas.indexOf(fila), 1);
          caja.remove();
        },
      }, ic('trash-2', 14), 'Quitar'));
    }
    lista.append(caja);
    if (enfocar) caja.querySelector('input,textarea')?.focus();
  }

  for (let i = 0; i < minimo; i += 1) agregar(false);
  return {
    nodo: h('div', { class: 'pila-s' }, lista,
      h('div', null, h('button', { class: 'btn sec sm', type: 'button', onclick: () => agregar(true) }, ic('plus', 14), textoAgregar))),
    leer: () => filas.map((f) => f.leer()).filter(Boolean),
    /* No usa every: todas las filas deben marcar sus errores, no solo la primera. */
    validar: () => filas.map((f) => f.validar?.() !== false).every(Boolean),
  };
}
