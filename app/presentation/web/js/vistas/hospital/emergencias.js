/* Emergencias: ingresos de emergencia abiertos. El tiempo de estancia lo calcula el cliente. */
import { api } from '../../api.js';
import { sesion } from '../../sesion.js';
import { enlace } from '../../enrutador.js';
import { fFechaHora } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import { cabeza, cargando, cifras, estadoDeError, vacio } from '../../ui/componentes.js';
import { duracion, horasDesde } from './comun.js';
import { abrirIngreso, abrirNuevoIngreso } from './ingreso.js';

const LARGA_HORAS = 4;

function tarjeta(ing, repintar) {
  const larga = horasDesde(ing.ingreso_en) >= LARGA_HORAS;
  return h('article', { class: `emergencia ${larga ? 'larga' : ''}` },
    h('div', { class: 'emergencia-cama' }, h('b', { text: ing.cama }), h('small', { text: ing.departamento })),
    h('div', { class: 'emergencia-datos' },
      h('a', { class: 'enlace emergencia-nombre', href: enlace(`pacientes/${encodeURIComponent(ing.id_paciente)}`, { origen: 'emergencias' }), text: ing.nombre_paciente }),
      h('p', { class: 'con-saltos', text: ing.motivo }),
      h('div', { class: 'medida', role: 'img', 'aria-label': `Lleva ${duracion(ing.ingreso_en)}` },
        h('i', { estilo: { width: `${Math.min(horasDesde(ing.ingreso_en) / (LARGA_HORAS * 2), 1) * 100}%` } })),
      h('div', { class: 'fila-datos' },
        h('span', { class: larga ? 'texto-aviso' : 'hint', text: `Lleva ${duracion(ing.ingreso_en)}` }),
        h('span', { class: 'hint', text: `desde ${fFechaHora(ing.ingreso_en)}` })),
      ing.diagnosticos.length > 0 && h('div', { class: 'etiquetas' }, ing.diagnosticos.slice(0, 3).map((d) => h('span', { class: 'chip info', text: d.descripcion }))),
      h('div', { class: 'fila' },
        h('button', { class: 'btn sec sm', type: 'button', onclick: () => abrirIngreso(ing, { alCambiar: repintar }) }, ic('bed-double', 14), 'Ver ingreso'))));
}

export async function vistaEmergencias({ contenedor, repintar }) {
  const zona = h('div', { class: 'pila', 'aria-live': 'polite' }, cargando(5));
  contenedor.append(
    cabeza('Emergencias', 'Pacientes en emergencia ahora, del que más tiempo lleva al más reciente.',
      sesion.tiene('consultas:registrar') && h('button', { class: 'btn', type: 'button', onclick: () => abrirNuevoIngreso({ tipo: 'emergencia', alGuardar: repintar }) }, ic('siren', 16), 'Ingreso de emergencia')),
    zona);
  try {
    const lista = await api('/ingresos', { params: { tipo: 'emergencia', abiertos: true, limite: 100 } });
    if (!lista.length) {
      zona.replaceChildren(vacio('siren', 'No hay emergencias activas', 'Cuando ingrese un paciente por emergencia aparecerá aquí.'));
      return;
    }
    const ordenada = [...lista].sort((a, b) => a.ingreso_en.localeCompare(b.ingreso_en));
    const horas = ordenada.map((i) => horasDesde(i.ingreso_en));
    zona.replaceChildren(
      cifras([
        { etiqueta: 'Emergencias activas', valor: ordenada.length },
        { etiqueta: `Más de ${LARGA_HORAS} horas`, valor: horas.filter((x) => x >= LARGA_HORAS).length, clase: horas.some((x) => x >= LARGA_HORAS) ? 'aviso' : '' },
        { etiqueta: 'Estancia promedio', valor: duracion(Date.now() - (horas.reduce((s, x) => s + x, 0) / horas.length) * 3600000) },
      ]),
      h('div', { class: 'emergencias' }, ordenada.map((ing) => tarjeta(ing, repintar))));
  } catch (error) {
    zona.replaceChildren(estadoDeError(error, repintar));
  }
}
