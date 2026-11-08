/* Camas: mapa por area y habitacion. camas:gestionar marca limpieza, mantenimiento o disponible;
   ocupar una cama solo ocurre al ingresar a un paciente. */
import { api } from '../../api.js';
import { accionesFicha, bloqueDatos } from '../compartido/ficha.js';
import { sesion } from '../../sesion.js';
import { enlace, irA } from '../../enrutador.js';
import { fFechaHora } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import { aviso_flotante, cabeza, cargando, cifras, confirmar, estadoDeError, lateral, segmento, seleccion, vacio } from '../../ui/componentes.js';
import { chipDe, duracion, ESTADOS_CAMA, TIPOS_INGRESO } from './comun.js';
import { abrirIngresoPorId, abrirNuevoIngreso } from './ingreso.js';

const MANUALES = ['disponible', 'limpieza', 'mantenimiento'];
const disponibles = (n) => (n === 1 ? '1 disponible' : `${n} disponibles`);
const ocupadas = (n) => (n === 1 ? '1 ocupada' : `${n} ocupadas`);

const estadoEnCambio = (etiqueta, estado) => h('dl', null,
  h('dt', { class: 'hint', text: etiqueta }), h('dd', null, chipDe(ESTADOS_CAMA, estado)));

function abrirCama(cama, repintar) {
  const ocupante = cama.ocupante;
  const acciones = [];
  if (cama.estado === 'disponible' && sesion.tiene('consultas:registrar')) {
    acciones.push(h('button', { class: 'btn', type: 'button', onclick: () => { panel.cerrar(); abrirNuevoIngreso({ cama, alGuardar: repintar }); } }, ic('bed-double', 16), 'Ingresar paciente aquí'));
  }
  if (sesion.tiene('camas:gestionar') && cama.estado !== 'ocupada') {
    for (const estado of MANUALES.filter((e) => e !== cama.estado)) {
      acciones.push(h('button', {
        class: 'btn sec', type: 'button', text: `Marcar ${ESTADOS_CAMA[estado].texto.toLowerCase()}`,
        onclick: () => confirmar({
          titulo: `Cambiar estado · Cama ${cama.codigo}`,
          accion: `Marcar ${ESTADOS_CAMA[estado].texto.toLowerCase()}`,
          cuerpo: [h('p', { class: 'hint', text: `${cama.departamento} · Habitación ${cama.habitacion}` }),
            h('div', { class: 'cama-cambio' }, estadoEnCambio('Estado actual', cama.estado),
              ic('chevron-right', 18), estadoEnCambio('Nuevo estado', estado))],
          alConfirmar: async () => {
            await api(`/camas/${cama.id_cama}/estado`, { metodo: 'POST', cuerpo: { estado } });
            panel.cerrar();
            aviso_flotante(`Cama ${cama.codigo}: ${ESTADOS_CAMA[estado].texto.toLowerCase()}`);
            repintar();
          },
        }),
      }));
    }
  }
  if (ocupante && sesion.tiene('historiales:leer')) acciones.push(h('button', {
    class: 'btn sec', type: 'button',
    onclick: () => { panel.cerrar(); abrirIngresoPorId(ocupante.id_paciente, ocupante.id_ingreso, { alCambiar: repintar }); },
  }, ic('bed-double', 16), 'Ver ingreso'));

  const panel = lateral(`Cama ${cama.codigo}`, [
    bloqueDatos('Datos de la cama',
      h('div', { class: 'fila' }, chipDe(ESTADOS_CAMA, cama.estado)),
      h('dl', { class: 'lista-datos' },
        h('dt', { text: 'Área' }), h('dd', { text: cama.departamento }),
        h('dt', { text: 'Habitación' }), h('dd', { text: cama.habitacion }))),
    ocupante && bloqueDatos('Ocupación',
      h('div', { class: 'fila' }, chipDe(TIPOS_INGRESO, ocupante.tipo)),
      h('dl', { class: 'lista-datos' },
        h('dt', { text: 'Paciente' }), h('dd', null, h('a', { class: 'enlace', href: enlace(`pacientes/${encodeURIComponent(ocupante.id_paciente)}`, { origen: 'camas' }), text: ocupante.nombre_paciente, onclick: () => panel.cerrar() })),
        h('dt', { text: 'Desde' }), h('dd', { text: `${fFechaHora(ocupante.desde)} (${duracion(ocupante.desde)})` }))),
    cama.estado === 'ocupada' && h('p', { class: 'hint', text: 'La cama se libera al dar de alta al paciente: pasa a limpieza.' }),
  ], accionesFicha(acciones));
}

function botonCama(c, repintar) {
  const emergencia = c.estado === 'ocupada' && c.ocupante?.tipo === 'emergencia';
  const estado = ESTADOS_CAMA[c.estado];
  const texto = emergencia ? 'Ocupada · Emergencia' : estado.texto;
  return h('button', {
    class: `cama ${c.estado}${emergencia ? ' emergencia-activa' : ''}`, type: 'button',
    onclick: () => abrirCama(c, repintar),
    'aria-label': `Cama ${c.codigo}, ${texto}${c.ocupante ? `, ${c.ocupante.nombre_paciente}` : ''}`,
  },
  h('span', { class: 'cama-cod' },
    h('span', { class: 'cama-icono' }, ic(emergencia ? 'siren' : estado.icono, 15)),
    h('span', { text: c.codigo }), ic('chevron-right', 13)),
  h('small', { class: 'cama-est', text: texto }),
  c.ocupante && h('small', { class: 'cama-ocupa', text: c.ocupante.nombre_paciente }));
}

export async function vistaCamas({ contenedor, params, repintar }) {
  const estado = ESTADOS_CAMA[params.estado] ? params.estado : '';
  const area = params.area || '';
  const ir = (cambios) => irA('camas', { estado: estado || null, area: area || null, ...cambios });
  const zona = h('div', { class: 'pila', 'aria-live': 'polite' }, cargando(6));
  contenedor.append(cabeza('Camas', 'Consulta la ocupación por área y habitación. Selecciona una cama para ver su detalle.'), zona);

  let camas;
  let departamentos;
  try {
    [camas, departamentos] = await Promise.all([api('/camas'), api('/departamentos')]);
  } catch (error) {
    zona.replaceChildren(estadoDeError(error, repintar));
    return;
  }
  const cuenta = (e) => camas.filter((c) => c.estado === e).length;
  const selectorArea = seleccion('camas-area', [{ valor: '', texto: 'Todas las áreas' }, ...departamentos.map((d) => ({ valor: String(d.id_departamento), texto: d.nombre }))],
    { value: area, onchange: (e) => ir({ area: e.target.value || null }), 'aria-label': 'Área' });
  const visibles = camas.filter((c) => (!estado || c.estado === estado) && (!area || String(c.id_departamento) === area));

  const porArea = new Map();
  for (const c of visibles) {
    if (!porArea.has(c.departamento)) porArea.set(c.departamento, new Map());
    const habs = porArea.get(c.departamento);
    if (!habs.has(c.habitacion)) habs.set(c.habitacion, []);
    habs.get(c.habitacion).push(c);
  }

  zona.replaceChildren(
    cifras([
      { etiqueta: 'Disponibles', valor: cuenta('disponible'), nota: `de ${camas.length} camas` },
      { etiqueta: 'Ocupadas', valor: cuenta('ocupada'), clase: cuenta('ocupada') ? 'info' : '' },
      { etiqueta: 'En limpieza', valor: cuenta('limpieza'), clase: cuenta('limpieza') ? 'aviso' : '' },
      { etiqueta: 'Mantenimiento', valor: cuenta('mantenimiento') },
    ]),
    h('div', { class: 'fila filtros' },
      segmento('Filtrar por estado', [{ valor: '', texto: 'Todas' }, ...Object.entries(ESTADOS_CAMA).map(([k, e]) => ({ valor: k, texto: e.filtro }))], estado,
        (v) => ir({ estado: v || null })),
      selectorArea),
    ...(visibles.length
      ? [...porArea].map(([dep, habs]) => {
        const camasArea = camas.filter((c) => c.departamento === dep);
        const totalOcupadas = camasArea.filter((c) => c.estado === 'ocupada').length;
        return h('section', { class: 'papel area-camas' },
          h('div', { class: 'papel-cab' }, h('h3', { text: dep }),
            h('div', { class: 'fila' },
              totalOcupadas > 0 && h('span', { class: 'chip info', text: ocupadas(totalOcupadas) }),
              h('span', { class: 'hint', text: disponibles(camasArea.filter((c) => c.estado === 'disponible').length) }))),
          h('div', { class: 'habitaciones' }, [...habs].map(([hab, lista]) => h('div', { class: 'habitacion' },
            h('small', { class: 'habitacion-nombre', text: `Habitación ${hab}` }),
            h('div', { class: 'camas' }, lista.sort((a, b) => a.codigo.localeCompare(b.codigo)).map((c) => botonCama(c, repintar)))))));
      })
      : [vacio('bed-double', 'Sin camas', 'No hay camas con estos filtros.')]));
}
