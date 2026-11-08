/* Cobros en solo lectura para el superusuario: los registra el personal de cada institucion. */
import { api } from '../../api.js';
import { bloqueDatos } from '../compartido/ficha.js';
import { ESTADOS_COBRO, METODOS_PAGO, entidad } from '../../catalogos.js';
import { fEntero, fFechaHora, fMoneda } from '../../formato.js';
import { h } from '../../ui/dom.js';
import { aviso, cabeza, cargando, chip, cifras, estadoDeError, lateral, segmento, tabla, vacio } from '../../ui/componentes.js';

const chipCobro = (estado) => {
  const e = ESTADOS_COBRO[estado] || { clase: '', texto: estado };
  return chip(e.clase, e.icono, e.texto);
};

function abrirCobro(cobro, inst) {
  const cargos = cobro.cargos.length
    ? tabla(['Concepto', { texto: 'Cant.', clase: 'der' }, { texto: 'Monto', clase: 'der' }], cobro.cargos.map((c) => h('tr', null,
      h('td', { class: 'ajustar', text: c.concepto }), h('td', { class: 'der', text: c.cantidad }), h('td', { class: 'der', text: fMoneda(c.monto) }))))
    : h('p', { class: 'muted', text: 'Sin cargos.' });
  const pagos = cobro.pagos.length
    ? tabla(['Fecha', 'Método', { texto: 'Monto', clase: 'der' }, 'Estado'], cobro.pagos.map((p) => h('tr', null,
      h('td', { class: 'num', text: fFechaHora(p.fecha_hora) }), h('td', { text: METODOS_PAGO[p.metodo] || p.metodo }), h('td', { class: 'der', text: fMoneda(p.monto) }),
      h('td', null, p.anulado ? chip('', 'ban', 'Anulado') : chip('ok', 'circle-check', 'Confirmado')))))
    : h('p', { class: 'muted', text: 'Sin pagos.' });
  lateral(`Cobro ${cobro.id_cobro}`, [
    aviso('info', 'eye', `Solo lectura: lo registra el personal de ${inst.nombre}.`),
    bloqueDatos('Datos del cobro',
      h('div', { class: 'fila' }, chipCobro(cobro.estado)),
      h('dl', { class: 'lista-datos' },
        h('dt', { text: 'Paciente' }), h('dd', { text: cobro.nombre_paciente }),
        h('dt', { text: 'Abierto' }), h('dd', { text: fFechaHora(cobro.abierto_en) }),
        cobro.cerrado_en && [h('dt', { text: 'Cerrado' }), h('dd', { text: fFechaHora(cobro.cerrado_en) })],
        cobro.descripcion && [h('dt', { text: 'Descripción' }), h('dd', { text: cobro.descripcion })],
        h('dt', { text: 'Total' }), h('dd', { class: 'num', text: fMoneda(cobro.total) }),
        h('dt', { text: 'Pagado' }), h('dd', { class: 'num', text: fMoneda(cobro.pagado) }),
        h('dt', { text: 'Saldo' }), h('dd', { class: 'num', text: fMoneda(cobro.saldo) }))),
    h('section', { class: 'pila-s' }, h('h3', { text: 'Cargos' }), cargos),
    h('section', { class: 'pila-s' }, h('h3', { text: 'Pagos' }), pagos),
  ]);
}

export async function vistaCobros({ contenedor, args, repintar }) {
  const id = args[0];
  const inst = entidad(id);
  const titulo = id === 'centro_pediatrico' ? 'Facturación' : 'Pagos';
  const encabezado = cabeza(`${titulo} de ${inst.nombre}`, `Solo lectura: los cobros los registra el personal de ${inst.nombre}.`);
  contenedor.replaceChildren(encabezado, cargando(6));
  contenedor.querySelector('h1').focus({ preventScroll: true });

  let filtro = '';
  const zona = h('div', { class: 'pila', 'aria-live': 'polite' });
  const params = { establecimiento: id };

  async function cargarTabla() {
    zona.replaceChildren(cargando(4));
    try {
      const cobros = await api('/cobros', { params: { ...params, estado: filtro, limite: 100 } });
      zona.replaceChildren(!cobros.length
        ? vacio('receipt', 'Sin cobros', filtro ? 'No hay cobros en este estado.' : 'Todavía no hay cobros registrados.')
        : tabla(['Cobro', 'Paciente', 'Abierto', 'Estado', { texto: 'Total', clase: 'der' }, { texto: 'Pagado', clase: 'der' }, { texto: 'Saldo', clase: 'der' }],
          cobros.map((c) => {
            const abrir = () => abrirCobro(c, inst);
            return h('tr', { class: 'clic', onclick: abrir },
              h('td', null, h('button', { class: 'enlace num', type: 'button', text: c.id_cobro, onclick: (e) => { e.stopPropagation(); abrir(); } })),
              h('td', { text: c.nombre_paciente }), h('td', { class: 'num', text: fFechaHora(c.abierto_en) }), h('td', null, chipCobro(c.estado)),
              h('td', { class: 'der', text: fMoneda(c.total) }), h('td', { class: 'der', text: fMoneda(c.pagado) }), h('td', { class: 'der', text: fMoneda(c.saldo) }));
          })));
    } catch (error) {
      zona.replaceChildren(estadoDeError(error, cargarTabla));
    }
  }

  try {
    const resumen = await api('/cobros/resumen', { params });
    const metodos = Object.entries(resumen.cobrado_hoy_por_metodo).filter(([, v]) => Number(v) > 0).map(([k, v]) => `${METODOS_PAGO[k] || k}: ${fMoneda(v)}`).join(', ');
    const barra = h('div');
    const pintarBarra = () => barra.replaceChildren(segmento('Filtrar por estado', [{ valor: '', texto: 'Todos' }, ...Object.entries(ESTADOS_COBRO).map(([k, e]) => ({ valor: k, texto: `${e.texto} ${fEntero(resumen.cobros_por_estado[k] || 0)}` }))], filtro, (v) => {
      filtro = v;
      pintarBarra();
      cargarTabla();
    }));
    pintarBarra();
    contenedor.replaceChildren(encabezado,
      cifras([
        { etiqueta: 'Saldo pendiente', valor: fMoneda(resumen.saldo_pendiente) },
        { etiqueta: 'Cobrado hoy', valor: fMoneda(resumen.cobrado_hoy), nota: metodos || 'Sin pagos hoy' },
        { etiqueta: 'Cobros abiertos', valor: fEntero(resumen.cobros_por_estado.abierto || 0) },
        id === 'hospital_general' && { etiqueta: 'Pagos anulados', valor: fEntero(resumen.pagos_anulados) },
      ]),
      barra, zona);
    await cargarTabla();
  } catch (error) {
    contenedor.replaceChildren(encabezado, estadoDeError(error, repintar));
  }
}
