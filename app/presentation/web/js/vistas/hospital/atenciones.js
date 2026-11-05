/* Atenciones: consultas e ingresos del hospital, con su recorrido y su cobro. No muestra montos:
   esos los consulta quien tiene pagos:ver, desde el cobro. */
import { api } from '../../api.js';
import { ESTADOS_COBRO } from '../../catalogos.js';
import { sesion } from '../../sesion.js';
import { enlace, irA } from '../../enrutador.js';
import { fFechaHora } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import { aviso, cabeza, cargando, chip, estadoDeError, lateral, segmento, tabla, vacio } from '../../ui/componentes.js';
import { chipDe, rutaPaciente, TIPOS_INGRESO } from './comun.js';
import { abrirIngreso } from './ingreso.js';
import { abrirCobroDeAtencion, abrirCobroPorId } from './pagos.js';

const POR_PAGINA = 50;
const cuenta = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;
const TIPOS = {
  CONSULTA: { clase: '', icono: 'stethoscope', texto: 'Consulta' },
  INGRESO: { clase: 'info', icono: 'bed-double', texto: 'Ingreso' },
};
export const chipAtencion = (tipo) => chipDe(TIPOS, tipo);

function seccionConsulta(c) {
  return h('section', { class: 'pila-s' },
    h('h3', { text: 'Consulta' }),
    c.notas && h('p', { class: 'con-saltos', text: c.notas }),
    c.diagnosticos.length > 0 && h('div', null, h('div', { class: 'subtitulo', text: 'Diagnósticos' }),
      h('div', { class: 'etiquetas' }, c.diagnosticos.map((d) => h('span', { class: 'chip info' }, d.descripcion, d.codigo && h('span', { class: 'codigo', text: ` ${d.codigo}` }))))),
    c.tratamientos.length > 0 && h('div', null, h('div', { class: 'subtitulo', text: 'Tratamientos' }),
      h('ul', { class: 'lista-simple' }, c.tratamientos.map((t) => h('li', { text: t.descripcion })))),
    c.recetas.length > 0 && h('div', null, h('div', { class: 'subtitulo', text: 'Recetas' }),
      tabla(['Medicamento', 'Dosis', 'Frecuencia'], c.recetas.map((r) => h('tr', null,
        h('td', { class: 'ajustar' }, h('b', { text: r.medicamento })), h('td', { text: r.dosis }), h('td', { text: r.frecuencia }))))),
    !c.notas && !c.diagnosticos.length && !c.tratamientos.length && !c.recetas.length && h('p', { class: 'muted', text: 'La consulta no tiene notas ni indicaciones.' }));
}

function seccionCobro(a, panel, alCambiar) {
  const accion = [];
  if (a.id_cobro && sesion.tiene('pagos:ver')) {
    accion.push(h('button', { class: 'btn sec sm', type: 'button', onclick: () => { panel.cerrar(); abrirCobroPorId(a.id_paciente, a.id_cobro, alCambiar); } }, ic('banknote', 14), 'Ver cobro'));
  }
  /* Sin cobro vigente (ninguno o anulado) la atencion se puede cobrar. */
  if ((!a.id_cobro || a.estado_cobro === 'anulado') && sesion.tiene('pagos:registrar')) {
    const boton = h('button', { class: 'btn sm', type: 'button' }, ic('plus', 14), 'Abrir cobro');
    const zona = h('div');
    boton.addEventListener('click', async () => {
      boton.disabled = true;
      try {
        panel.cerrar();
        await abrirCobroDeAtencion(a, alCambiar);
      } catch (error) {
        boton.disabled = false;
        zona.replaceChildren(aviso('crit', 'circle-alert', h('b', { text: error.message })));
      }
    });
    accion.push(boton, zona);
  }
  return h('section', { class: 'pila-s' }, h('h3', { text: 'Cobro' }),
    h('div', { class: 'fila' }, a.id_cobro ? chipDe(ESTADOS_COBRO, a.estado_cobro) : chip('', 'circle-help', 'Sin cobro'), ...accion));
}

/* Recorrido de una atencion: la consulta completa o el ingreso, mas su cobro. */
export async function abrirAtencion(idPaciente, idAtencion, { alCambiar } = {}) {
  const panel = lateral(`Atención ${idAtencion}`, [cargando(5)]);
  const cuerpo = panel.nodo.querySelector('.cuerpo');
  let detalle;
  try {
    detalle = await api(`${rutaPaciente(idPaciente)}/atenciones/${encodeURIComponent(idAtencion)}`);
  } catch (error) {
    cuerpo.replaceChildren(estadoDeError(error));
    return;
  }
  const a = detalle.atencion;
  /* replaceChildren convierte null en el texto «null»: se filtran las secciones ausentes. */
  cuerpo.replaceChildren(...[
    h('div', { class: 'fila' }, chipAtencion(a.tipo), a.tipo_ingreso && chipDe(TIPOS_INGRESO, a.tipo_ingreso),
      a.tipo === 'INGRESO' && (a.alta_en ? chip('ok', 'door-open', 'Con alta') : chip('aviso', 'clock', 'Internado'))),
    h('dl', { class: 'lista-datos' },
      h('dt', { text: 'Paciente' }), h('dd', null, h('a', { class: 'enlace', href: enlace(`pacientes/${encodeURIComponent(a.id_paciente)}`, { origen: 'atenciones' }), text: a.nombre_paciente, onclick: () => panel.cerrar() })),
      h('dt', { text: 'Fecha' }), h('dd', { text: fFechaHora(a.fecha_hora) }),
      h('dt', { text: 'Profesional' }), h('dd', { text: a.nombre_profesional }),
      h('dt', { text: 'Motivo' }), h('dd', { class: 'con-saltos', text: a.motivo }),
      a.cama && [h('dt', { text: 'Cama' }), h('dd', { text: a.cama })],
      a.alta_en && [h('dt', { text: 'Alta' }), h('dd', { text: fFechaHora(a.alta_en) })]),
    detalle.consulta && seccionConsulta(detalle.consulta),
    detalle.ingreso && h('section', { class: 'pila-s' }, h('h3', { text: 'Ingreso' }),
      h('p', { class: 'muted', text: `${cuenta(detalle.ingreso.diagnosticos.length, 'diagnóstico', 'diagnósticos')} · ${cuenta(detalle.ingreso.ordenes.length, 'orden médica', 'órdenes médicas')}` }),
      h('div', null, h('button', { class: 'btn sec sm', type: 'button', onclick: () => { panel.cerrar(); abrirIngreso(detalle.ingreso, { alCambiar }); } }, ic('bed-double', 14), 'Ver el ingreso completo'))),
    seccionCobro(a, panel, alCambiar),
  ].filter(Boolean));
}

const filaAtencion = (a, alCambiar) => {
  const abrir = () => abrirAtencion(a.id_paciente, a.id_atencion, { alCambiar });
  return h('tr', { class: 'clic', onclick: abrir },
    h('td', null, h('button', { class: 'enlace num', type: 'button', text: a.id_atencion, onclick: (e) => { e.stopPropagation(); abrir(); } })),
    h('td', null, chipAtencion(a.tipo)),
    h('td', { class: 'ajustar' }, h('a', { class: 'enlace', href: enlace(`pacientes/${encodeURIComponent(a.id_paciente)}`, { origen: 'atenciones' }), text: a.nombre_paciente, onclick: (e) => e.stopPropagation() })),
    h('td', { class: 'ajustar', text: a.nombre_profesional }),
    h('td', { class: 'num', text: fFechaHora(a.fecha_hora) }),
    h('td', { class: 'ajustar', text: a.motivo }),
    h('td', { text: a.cama || '—' }),
    h('td', null, a.estado_cobro ? chipDe(ESTADOS_COBRO, a.estado_cobro) : h('span', { class: 'hint', text: 'Sin cobro' })));
};

export async function vistaAtenciones({ contenedor, params, repintar }) {
  const tipo = TIPOS[params.tipo] ? params.tipo : '';
  const zona = h('div', { class: 'pila', 'aria-live': 'polite' }, cargando(6));
  contenedor.append(
    cabeza('Atenciones', 'Consultas e ingresos del hospital, de la más reciente a la más antigua.'),
    segmento('Filtrar atenciones', [{ valor: '', texto: 'Todas' }, { valor: 'CONSULTA', texto: 'Consultas' }, { valor: 'INGRESO', texto: 'Ingresos' }], tipo,
      (v) => irA('atenciones', { tipo: v })),
    zona);

  const cuerpo = h('tbody');
  const zonaMas = h('div', { class: 'mas' });
  async function pagina(antes) {
    const lista = await api('/atenciones', { params: { tipo, limite: POR_PAGINA, antes_de: antes } });
    cuerpo.append(...lista.map((a) => filaAtencion(a, repintar)));
    zonaMas.replaceChildren();
    if (lista.length === POR_PAGINA) {
      const boton = h('button', {
        class: 'btn sec', type: 'button',
        onclick: async () => {
          boton.disabled = true;
          try {
            await pagina(lista[lista.length - 1].id_atencion);
          } catch (error) {
            zonaMas.replaceChildren(estadoDeError(error));
          }
        },
      }, ic('chevron-down', 16), 'Cargar atenciones anteriores');
      zonaMas.append(boton);
    }
    return lista.length;
  }

  try {
    const n = await pagina(null);
    if (!n) {
      zona.replaceChildren(vacio('activity', 'Sin atenciones', tipo ? 'No hay atenciones de este tipo.' : 'Las consultas e ingresos aparecerán aquí.'));
      return;
    }
    const t = tabla(['Atención', 'Tipo', 'Paciente', 'Profesional', 'Fecha', 'Motivo', 'Cama', 'Cobro'], []);
    t.querySelector('tbody').replaceWith(cuerpo);
    zona.replaceChildren(t, zonaMas);
  } catch (error) {
    zona.replaceChildren(estadoDeError(error, repintar));
  }
}
