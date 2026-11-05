/* Ordenes de laboratorio de toda la institucion: abiertas primero, con filtro por estado.
   Los conteos vienen del resumen, no de la pagina visible. */
import { api } from '../../api.js';
import { enlace, irA } from '../../enrutador.js';
import { fEntero, fFechaHora } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import { cabeza, cargando, cifras, estadoDeError, segmento, tabla, vacio } from '../../ui/componentes.js';
import { ABIERTAS, chipOrden, ESTADOS_ORDEN } from './comun.js';
import { abrirOrden } from './orden.js';

const POR_PAGINA = 50;
const FILTROS = {
  abiertas: { texto: 'Abiertas', estados: ABIERTAS },
  ...Object.fromEntries(Object.entries(ESTADOS_ORDEN).map(([k, e]) => [k, { texto: e.filtro, estados: [k] }])),
  todas: { texto: 'Todas', estados: null },
};

function avance(o) {
  const total = o.pruebas.length;
  const listas = total - o.pruebas_pendientes;
  return h('div', { class: 'avance' },
    h('div', { class: 'medida', role: 'img', 'aria-label': `${listas} de ${total} pruebas con resultados` },
      h('i', { estilo: { width: `${(listas / Math.max(total, 1)) * 100}%` } })),
    h('small', { class: 'hint cifra-tabular', text: `${listas}/${total}` }));
}

const filaOrden = (o, repintar) => {
  const abrir = () => abrirOrden(o.id_paciente, o.id_orden, { nombrePaciente: o.nombre_paciente, alCambiar: repintar });
  return h('tr', { class: 'clic', onclick: abrir },
    h('td', null, h('button', { class: 'enlace num sin-corte', type: 'button', text: o.numero_orden, onclick: (e) => { e.stopPropagation(); abrir(); } })),
    h('td', { class: 'ajustar' }, h('a', { class: 'enlace', href: enlace(`pacientes/${encodeURIComponent(o.id_paciente)}`, { origen: 'ordenes' }), text: o.nombre_paciente, onclick: (e) => e.stopPropagation() })),
    h('td', { class: 'ajustar' }, h('div', { class: 'etiquetas' }, o.pruebas.map((p) => h('span', { class: `chip ${p.con_resultados ? 'ok' : ''}`, text: p.nombre })))),
    h('td', null, avance(o)),
    h('td', { class: 'num', text: fEntero(o.muestras) }),
    h('td', { class: 'num', text: fFechaHora(o.solicitada_en) }),
    h('td', null, chipOrden(o.estado)));
};

export async function vistaOrdenes({ contenedor, params, repintar }) {
  const filtro = FILTROS[params.estado] ? params.estado : 'abiertas';
  const zona = h('div', { class: 'pila', 'aria-live': 'polite' }, cargando(6));
  const zonaCifras = h('div');
  contenedor.append(
    cabeza('Órdenes de laboratorio', 'Órdenes de la institución, de la más reciente a la más antigua.'),
    zonaCifras,
    segmento('Filtrar órdenes', Object.entries(FILTROS).map(([valor, f]) => ({ valor, texto: f.texto })), filtro,
      (v) => irA('ordenes', { estado: v === 'abiertas' ? null : v })),
    zona);

  api('/laboratorio/resumen').then((r) => zonaCifras.replaceChildren(cifras([
    { etiqueta: 'Solicitadas', valor: fEntero(r.solicitada || 0) },
    { etiqueta: 'En proceso', valor: fEntero(r.en_proceso || 0) },
    { etiqueta: 'Listas para validar', valor: fEntero(r.listas_para_validar || 0), clase: r.listas_para_validar ? 'aviso' : '' },
    { etiqueta: 'Validadas', valor: fEntero(r.validada || 0) },
  ]))).catch((error) => {
    if (error.estado !== 401) zonaCifras.replaceChildren(estadoDeError(error));
  });

  const cuerpo = h('tbody');
  const zonaMas = h('div', { class: 'mas' });
  async function pagina(ultima) {
    const lista = await api('/laboratorio/ordenes', {
      params: { estado: FILTROS[filtro].estados, limite: POR_PAGINA, antes_de: ultima?.solicitada_en, antes_de_id: ultima?.id_orden },
    });
    cuerpo.append(...lista.map((o) => filaOrden(o, repintar)));
    zonaMas.replaceChildren();
    if (lista.length === POR_PAGINA) {
      const boton = h('button', {
        class: 'btn sec', type: 'button',
        onclick: async () => {
          boton.disabled = true;
          try {
            await pagina(lista[lista.length - 1]);
          } catch (error) {
            zonaMas.replaceChildren(estadoDeError(error));
          }
        },
      }, ic('chevron-down', 16), 'Cargar órdenes anteriores');
      zonaMas.append(boton);
    }
    return lista.length;
  }

  try {
    if (!await pagina(null)) {
      zona.replaceChildren(vacio('flask-conical', 'Sin órdenes', filtro === 'abiertas' ? 'No hay órdenes pendientes. Las nuevas aparecerán aquí.' : 'No hay órdenes con este estado.'));
      return;
    }
    const t = tabla(['Orden', 'Paciente', 'Pruebas', 'Avance', 'Muestras', 'Solicitada', 'Estado'], []);
    t.querySelector('tbody').replaceWith(cuerpo);
    zona.replaceChildren(t, zonaMas);
  } catch (error) {
    zona.replaceChildren(estadoDeError(error, repintar));
  }
}
