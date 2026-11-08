/* Catalogo de pruebas vigente; cada prueba muestra sus versiones publicadas. Las ordenes guardan
   copia de la version con que se pidieron, asi un cambio de rango no altera resultados viejos. */
import { api } from '../../api.js';
import { accionesFicha, bloqueDatos } from '../compartido/ficha.js';
import { h, ic } from '../../ui/dom.js';
import { cabeza, cargando, chip, entrada, estadoDeError, lateral, tabla, vacio } from '../../ui/componentes.js';
import { TIPOS_VALOR, textoReferencia } from './comun.js';

const tablaParametros = (parametros) => tabla(['Parámetro', 'Tipo', 'Referencia'], parametros.map((param) => h('tr', null,
  h('td', { class: 'ajustar' }, h('b', { text: param.nombre }), h('small', { class: 'hint bloque codigo', text: param.codigo })),
  h('td', { text: TIPOS_VALOR[param.tipo_valor] || param.tipo_valor }),
  h('td', { class: 'ajustar', text: textoReferencia(param.referencia, param.unidad) }))));

async function abrirVersiones(prueba) {
  const panel = lateral(prueba.nombre, [cargando(5)]);
  const cuerpo = panel.nodo.querySelector('.cuerpo');
  try {
    const versiones = await api(`/laboratorio/pruebas/${encodeURIComponent(prueba.codigo)}/versiones`);
    cuerpo.replaceChildren(
      h('p', { class: 'muted', text: 'Las órdenes nuevas usan la versión vigente; las anteriores conservan la suya.' }),
      ...[...versiones].sort((a, b) => b.prueba.version - a.prueba.version).map((v) => h('section', { class: 'pila-s' },
        h('div', { class: 'fila' }, h('h3', { text: `Versión ${v.prueba.version}` }),
          v.vigente ? chip('ok', 'circle-check', 'Vigente') : chip('', null, v.activa ? 'Activa' : 'Retirada')),
        v.prueba.indicaciones && h('p', { class: 'hint', text: v.prueba.indicaciones }),
        tablaParametros(v.prueba.parametros))));
  } catch (error) {
    cuerpo.replaceChildren(estadoDeError(error));
  }
}

export async function vistaCatalogo({ contenedor, repintar }) {
  const buscar = entrada('catalogo-buscar', { type: 'search', placeholder: 'Buscar por nombre o código', 'aria-label': 'Buscar prueba' });
  const zona = h('div', { class: 'pila', 'aria-live': 'polite' }, cargando(5));
  contenedor.append(cabeza('Catálogo de pruebas', 'Pruebas que se pueden pedir en una orden, con sus rangos de referencia.'),
    h('div', { class: 'buscador' }, ic('search', 18), buscar), zona);
  let pruebas;
  try {
    pruebas = await api('/laboratorio/pruebas');
  } catch (error) {
    zona.replaceChildren(estadoDeError(error, repintar));
    return;
  }
  const pintar = () => {
    const q = buscar.value.trim().toLowerCase();
    const visibles = pruebas.filter((p) => !q || p.nombre.toLowerCase().includes(q) || p.codigo.toLowerCase().includes(q));
    zona.replaceChildren(...(visibles.length
      ? visibles.map((p) => h('article', { class: 'papel pila-s prueba-catalogo' },
        h('h3', { text: p.nombre }),
        bloqueDatos('Datos de la prueba',
          h('small', { class: 'hint codigo', text: `${p.codigo} · versión ${p.version}${p.tipo_muestra ? ` · ${p.tipo_muestra}` : ''}` }),
          p.indicaciones && h('p', { class: 'hint', text: p.indicaciones })),
        tablaParametros(p.parametros),
        accionesFicha([h('button', { class: 'btn sec sm', type: 'button', onclick: () => abrirVersiones(p) }, ic('history', 14), 'Ver versiones')])))
      : [vacio('flask-conical', 'Sin pruebas', q ? `Ninguna prueba coincide con «${buscar.value.trim()}».` : 'El catálogo está vacío.')]));
  };
  buscar.addEventListener('input', pintar);
  pintar();
}
