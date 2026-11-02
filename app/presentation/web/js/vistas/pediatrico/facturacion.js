/* Facturacion: una factura por consulta, a nombre de un tutor. Pagada = saldo cero. En este
   centro una factura no se cierra y un pago no se anula (la API responde 501): no se ofrecen. */
import { api } from '../../api.js';
import { METODOS_PAGO } from '../../catalogos.js';
import { sesion } from '../../sesion.js';
import { enlace, reflejar } from '../../enrutador.js';
import { fEntero, fFechaHora, fMoneda, nombreDe } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import {
  aviso, aviso_flotante, cabeza, campo, cargando, chip, cifras, confirmar, entrada, estadoDeError, lateral, modal,
  segmento, seleccion, tabla, vacio,
} from '../../ui/componentes.js';
import { enviar } from './comun.js';
import { selectorDePaciente } from './agendar.js';

const ESTADOS = {
  abierto: { clase: 'aviso', icono: 'clock', texto: 'Por cobrar', filtro: 'Por cobrar' },
  pagado: { clase: 'ok', icono: 'check', texto: 'Pagada', filtro: 'Pagadas' },
  anulado: { clase: '', icono: 'ban', texto: 'Anulada', filtro: 'Anuladas' },
};
const chipFactura = (estado) => {
  const e = ESTADOS[estado] || { clase: '', texto: estado };
  return chip(e.clase, e.icono, e.texto);
};
const rutaFactura = (c) => `/pacientes/${encodeURIComponent(c.id_paciente)}/cobros/${encodeURIComponent(c.id_cobro)}`;
const DINERO = /^\d{1,10}(\.\d{1,2})?$/;
/* tipo_de_pago de este centro: el cheque solo existe en el Hospital General (la API daria 422). */
const METODOS = ['efectivo', 'tarjeta', 'transferencia'];

/* ---------- Detalle ---------- */
function abrirFactura(cobro, alCambiar) {
  const registra = sesion.tiene('pagos:registrar');
  const abierta = cobro.estado === 'abierto';
  const refrescar = (nuevo) => {
    panel.cerrar();
    abrirFactura(nuevo, alCambiar);
    alCambiar?.();
  };
  const cargos = cobro.cargos.length
    ? tabla(['Concepto', { texto: 'Cant.', clase: 'der' }, { texto: 'P. unitario', clase: 'der' }, { texto: 'Subtotal', clase: 'der' }], cobro.cargos.map((c) => h('tr', null,
      h('td', { class: 'ajustar', text: c.concepto }), h('td', { class: 'der', text: c.cantidad }),
      h('td', { class: 'der', text: fMoneda(c.precio_unitario) }), h('td', { class: 'der', text: fMoneda(c.monto) }))))
    : h('p', { class: 'muted', text: 'Sin cargos todavía.' });
  const pagos = cobro.pagos.length
    ? tabla(['Fecha', 'Método', 'Referencia', { texto: 'Monto', clase: 'der' }], cobro.pagos.map((p) => h('tr', null,
      h('td', { class: 'num', text: fFechaHora(p.fecha_hora) }), h('td', { text: METODOS_PAGO[p.metodo] || p.metodo }),
      h('td', { class: 'ajustar', text: p.referencia || '—' }), h('td', { class: 'der', text: fMoneda(p.monto) }))))
    : h('p', { class: 'muted', text: 'Sin pagos.' });

  const acciones = [];
  if (registra && abierta) {
    if (Number(cobro.pagado) === 0) {
      acciones.push(h('button', {
        class: 'btn peligro', type: 'button', text: 'Anular',
        onclick: () => confirmar({
          titulo: 'Anular factura',
          peligro: true,
          accion: 'Anular factura',
          cuerpo: [h('p', { text: `La factura ${cobro.id_cobro} queda anulada: no se borra y ya no admite cargos ni pagos. La consulta se podrá facturar de nuevo.` })],
          alConfirmar: async () => {
            const nuevo = await api(`${rutaFactura(cobro)}/anular`, { metodo: 'POST' });
            aviso_flotante('Factura anulada', 'ban');
            refrescar(nuevo);
          },
        }),
      }));
    }
    acciones.push(h('button', { class: 'btn sec', type: 'button', onclick: () => abrirCargo(cobro, refrescar) }, ic('plus', 16), 'Agregar cargo'));
    if (Number(cobro.saldo) > 0) acciones.push(h('button', { class: 'btn', type: 'button', onclick: () => abrirPago(cobro, refrescar) }, ic('banknote', 16), 'Registrar pago'));
  }

  const panel = lateral(`Factura ${cobro.id_cobro}`, [
    h('div', { class: 'fila' }, chipFactura(cobro.estado)),
    !registra && aviso('info', 'eye', 'Solo lectura: tu cuenta puede ver las facturas, no registrar cobros.'),
    h('dl', { class: 'lista-datos' },
      h('dt', { text: 'Paciente' }), h('dd', null, h('a', { class: 'enlace', href: enlace(`pacientes/${encodeURIComponent(cobro.id_paciente)}/facturas`), text: cobro.nombre_paciente, onclick: () => panel.cerrar() })),
      h('dt', { text: 'Facturada a' }), h('dd', { text: cobro.facturado_a ? `${cobro.facturado_a.nombre} (tutor)` : 'Sin tutor asignado' }),
      h('dt', { text: 'Emitida' }), h('dd', { text: fFechaHora(cobro.abierto_en) }),
      cobro.cerrado_en && [h('dt', { text: 'Anulada' }), h('dd', { text: fFechaHora(cobro.cerrado_en) })],
      h('dt', { text: 'Consulta' }), h('dd', { class: 'num', text: cobro.id_atencion }),
      cobro.descripcion && [h('dt', { text: 'Descripción' }), h('dd', { text: cobro.descripcion })]),
    h('section', { class: 'pila-s' }, h('h3', { text: 'Cargos' }), cargos),
    h('dl', { class: 'totales' },
      h('dt', { text: 'Total' }), h('dd', { text: fMoneda(cobro.total) }),
      h('dt', { text: 'Pagado' }), h('dd', { text: fMoneda(cobro.pagado) }),
      h('dt', { class: 'saldo', text: 'Saldo' }), h('dd', { class: 'saldo', text: fMoneda(cobro.saldo) })),
    h('section', { class: 'pila-s' }, h('h3', { text: 'Pagos' }), pagos),
  ], acciones.length ? acciones : null);
}

function abrirCargo(cobro, alGuardar) {
  const concepto = entrada('cargo-concepto', { maxlength: 200, placeholder: 'Consulta de control del niño sano' });
  const cantidad = entrada('cargo-cantidad', { type: 'number', min: 0.01, step: '0.01', value: '1', inputmode: 'decimal' });
  const precio = entrada('cargo-precio', { type: 'number', min: 0, step: '0.01', inputmode: 'decimal' });
  const campos = {
    concepto: campo('Concepto', concepto), cantidad: campo('Cantidad', cantidad), precio_unitario: campo('Precio unitario (Q)', precio),
  };
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'button', text: 'Agregar cargo' });
  const ventana = modal('Agregar cargo', h('div', { class: 'pila-s' }, campos.concepto, h('div', { class: 'dos' }, campos.cantidad, campos.precio_unitario), zona),
    [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => ventana.cerrar() }), boton]);
  boton.addEventListener('click', () => {
    const conceptoOk = Boolean(concepto.value.trim());
    const cantidadOk = DINERO.test(cantidad.value) && Number(cantidad.value) > 0;
    const precioOk = DINERO.test(precio.value);
    campos.concepto.marcar(conceptoOk ? null : 'Escribe el concepto.');
    campos.cantidad.marcar(cantidadOk ? null : 'Escribe una cantidad mayor que cero, con hasta dos decimales.');
    campos.precio_unitario.marcar(precioOk ? null : 'Escribe el precio, con hasta dos decimales.');
    if (!conceptoOk || !cantidadOk || !precioOk) return;
    enviar(boton, zona, campos, async () => {
      const nuevo = await api(`${rutaFactura(cobro)}/cargos`, {
        metodo: 'POST',
        cuerpo: { concepto: concepto.value.trim(), cantidad: cantidad.value, precio_unitario: precio.value },
      });
      ventana.cerrar();
      aviso_flotante('Cargo agregado');
      alGuardar(nuevo);
    });
  });
}

function abrirPago(cobro, alGuardar) {
  const metodo = seleccion('pago-metodo', METODOS.map((valor) => ({ valor, texto: METODOS_PAGO[valor] })));
  const monto = entrada('pago-monto', { type: 'number', min: 0.01, step: '0.01', value: cobro.saldo, inputmode: 'decimal' });
  const referencia = entrada('pago-referencia', { maxlength: 150 });
  const campos = {
    metodo: campo('Método', metodo),
    monto: campo('Monto (Q)', monto, { ayuda: `Saldo pendiente: ${fMoneda(cobro.saldo)}` }),
    referencia: campo('Referencia', referencia, { opcional: true, ayuda: 'Número de comprobante. Nunca escribas datos de la tarjeta.' }),
  };
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'button', text: 'Registrar pago' });
  const ventana = modal('Registrar pago', h('div', { class: 'pila-s' }, h('p', { class: 'muted', text: `Factura ${cobro.id_cobro} · ${cobro.nombre_paciente}` }), campos.metodo, campos.monto, campos.referencia, zona),
    [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => ventana.cerrar() }), boton]);
  boton.addEventListener('click', () => {
    let problema = null;
    if (!DINERO.test(monto.value) || Number(monto.value) <= 0) problema = 'Escribe un monto mayor que cero, con hasta dos decimales.';
    else if (Number(monto.value) > Number(cobro.saldo)) problema = 'El pago no puede exceder el saldo pendiente.';
    campos.monto.marcar(problema);
    if (problema) return;
    enviar(boton, zona, campos, async () => {
      const nuevo = await api(`${rutaFactura(cobro)}/pagos`, {
        metodo: 'POST',
        cuerpo: { metodo: metodo.value, monto: monto.value, referencia: referencia.value.trim() || null },
      });
      ventana.cerrar();
      aviso_flotante(nuevo.estado === 'pagado' ? 'Pago registrado. La factura quedó pagada.' : 'Pago registrado');
      alGuardar(nuevo);
    });
  });
}

/* ---------- Emitir ---------- */
export function abrirEmision({ paciente, consulta, alCambiar }) {
  let elegido = paciente || null;
  const consultas = seleccion('factura-consulta', [{ valor: '', texto: 'Primero elige el paciente' }], { disabled: true });
  const tutor = seleccion('factura-tutor', [{ valor: '', texto: 'Primero elige el paciente' }], { disabled: true });
  const descripcion = entrada('factura-descripcion', { maxlength: 300 });
  const campos = {
    id_atencion: campo('Consulta que se factura', consultas),
    id_tutor: campo('Facturar a', tutor, { ayuda: 'Por defecto, el tutor principal.' }),
    descripcion: campo('Descripción', descripcion, { opcional: true }),
  };
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'button', text: 'Emitir factura', disabled: true });

  async function cargarDatos(p) {
    elegido = p;
    boton.disabled = true;
    zona.replaceChildren();
    const base = `/pacientes/${encodeURIComponent(p.id_paciente)}`;
    try {
      const [historial, tutores] = await Promise.all([
        consulta ? null : api(`${base}/historial`, { params: { limite: 50 } }),
        api(`${base}/tutores`),
      ]);
      if (!consulta) {
        consultas.replaceChildren(...(historial.consultas.length
          ? [h('option', { value: '', text: 'Elige la consulta' }), ...historial.consultas.map((c) => h('option', { value: c.id_consulta, text: `${fFechaHora(c.fecha_hora)} · ${c.motivo}` }))]
          : [h('option', { value: '', text: 'Este paciente no tiene consultas' })]));
        consultas.disabled = !historial.consultas.length;
      }
      /* Sin tutor la factura se puede emitir (queda sin titular), como permite la API. */
      const principal = tutores.find((v) => v.es_principal);
      tutor.replaceChildren(...(tutores.length
        ? tutores.map((v) => h('option', { value: v.tutor.id_tutor, text: `${nombreDe(v.tutor)} · ${v.parentesco}${v.es_principal ? ' (principal)' : ''}` }))
        : [h('option', { value: '', text: 'Sin tutores vinculados' })]));
      if (principal) tutor.value = principal.tutor.id_tutor;
      tutor.disabled = !tutores.length;
      if (!principal && tutores.length) tutor.value = tutores[0].tutor.id_tutor;
      if (!tutores.length) zona.replaceChildren(aviso('aviso', 'triangle-alert', 'Este paciente no tiene tutores: la factura quedará sin titular. Vincula uno en su ficha si corresponde.'));
      boton.disabled = !consulta && !historial.consultas.length;
    } catch (error) {
      zona.replaceChildren(estadoDeError(error, () => cargarDatos(p)));
    }
  }

  const selector = paciente ? null : selectorDePaciente({ incluirArchivados: true, alElegir: cargarDatos });
  const panel = lateral('Emitir factura', [
    paciente ? aviso('info', 'user-round', h('b', { text: nombreDe(paciente) })) : selector.nodo,
    !paciente && h('p', { class: 'hint', text: 'Un historial archivado también se puede facturar.' }),
    consulta ? h('p', { class: 'muted', text: `Consulta: ${fFechaHora(consulta.fecha_hora)} · ${consulta.motivo}` }) : campos.id_atencion,
    campos.id_tutor, campos.descripcion, zona,
  ], [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => panel.cerrar() }), boton]);

  boton.addEventListener('click', () => {
    const atencion = consulta ? consulta.id_consulta : consultas.value;
    campos.id_atencion.marcar(atencion ? null : 'Elige la consulta.');
    if (!atencion) return;
    enviar(boton, zona, campos, async () => {
      const cuerpo = { id_atencion: atencion, descripcion: descripcion.value.trim() || null };
      if (tutor.value) cuerpo.id_tutor = tutor.value;
      const nueva = await api(`/pacientes/${encodeURIComponent(elegido.id_paciente)}/cobros`, { metodo: 'POST', cuerpo });
      panel.cerrar();
      aviso_flotante('Factura emitida. Agrega sus cargos.');
      abrirFactura(nueva, alCambiar);
      alCambiar?.();
    });
  });
  if (paciente) cargarDatos(paciente);
}

/* ---------- Listas ---------- */
function tablaFacturas(cobros, alCambiar, { conPaciente }) {
  return tabla(['Factura', conPaciente && 'Paciente', 'Facturada a', 'Emitida', 'Estado', { texto: 'Total', clase: 'der' }, { texto: 'Saldo', clase: 'der' }],
    cobros.map((c) => {
      const abrir = () => abrirFactura(c, alCambiar);
      return h('tr', { class: 'clic', onclick: abrir },
        h('td', null, h('button', { class: 'enlace num', type: 'button', text: c.id_cobro, onclick: (e) => { e.stopPropagation(); abrir(); } })),
        conPaciente && h('td', { class: 'ajustar', text: c.nombre_paciente }),
        h('td', { class: 'ajustar', text: c.facturado_a?.nombre || 'Sin tutor' }),
        h('td', { class: 'num', text: fFechaHora(c.abierto_en) }),
        h('td', null, chipFactura(c.estado)),
        h('td', { class: `der ${c.estado === 'anulado' ? 'tachado' : ''}`, text: fMoneda(c.total) }),
        h('td', { class: 'der', text: c.estado === 'anulado' ? '—' : fMoneda(c.saldo) }));
    }));
}

export function pestanaFacturas(p, ctx) {
  const { valor, error } = ctx.datos.facturas;
  if (error) return estadoDeError(error, ctx.repintar);
  if (!valor.length) {
    return vacio('receipt', 'Sin facturas', sesion.tiene('pagos:registrar') ? 'Emítela desde la consulta, en la pestaña Historial.' : 'Las facturas de este paciente aparecerán aquí.');
  }
  return tablaFacturas(valor, ctx.repintar, { conPaciente: false });
}

export async function vistaFacturacion({ contenedor, params, repintar }) {
  const LIMITE = 100;
  let filtro = ESTADOS[params.estado] ? params.estado : '';
  const puedeEmitir = sesion.tiene('pagos:registrar') && sesion.tiene('historiales:leer');
  const encabezado = cabeza('Facturación', 'Facturas a nombre del tutor de cada paciente.',
    puedeEmitir && h('button', { class: 'btn', type: 'button', onclick: () => abrirEmision({ alCambiar: repintar }) }, ic('file-plus', 16), 'Emitir factura'));
  const zona = h('div', { class: 'pila', 'aria-live': 'polite' }, cargando(6));
  contenedor.append(encabezado, zona);

  const lista = h('div', { class: 'pila-s' });
  async function cargarLista() {
    lista.replaceChildren(cargando(4));
    try {
      const cobros = await api('/cobros', { params: { estado: filtro, limite: LIMITE } });
      lista.replaceChildren(...(cobros.length
        ? [tablaFacturas(cobros, repintar, { conPaciente: true }),
          cobros.length === LIMITE && h('p', { class: 'hint', text: `Se muestran las ${LIMITE} más recientes.` })].filter(Boolean)
        : [vacio('receipt', 'Sin facturas', filtro ? 'No hay facturas en este estado.' : 'Las facturas emitidas aparecerán aquí.')]));
    } catch (error) {
      lista.replaceChildren(estadoDeError(error, cargarLista));
    }
  }

  try {
    const resumen = await api('/cobros/resumen');
    const n = (estado) => resumen.cobros_por_estado[estado] || 0;
    const metodos = Object.entries(resumen.cobrado_hoy_por_metodo).filter(([, v]) => Number(v) > 0).map(([k, v]) => `${METODOS_PAGO[k] || k}: ${fMoneda(v)}`).join(', ');
    const barra = h('div');
    const pintarBarra = () => barra.replaceChildren(segmento('Filtrar facturas', [
      { valor: '', texto: `Todas ${fEntero(n('abierto') + n('pagado') + n('anulado'))}` },
      ...Object.entries(ESTADOS).map(([k, e]) => ({ valor: k, texto: `${e.filtro} ${fEntero(n(k))}` })),
    ], filtro, (v) => {
      filtro = v;
      reflejar('facturacion', { estado: v });
      pintarBarra();
      cargarLista();
    }));
    pintarBarra();
    zona.replaceChildren(
      cifras([
        { etiqueta: 'Por cobrar', valor: fMoneda(resumen.saldo_pendiente), nota: n('abierto') === 1 ? '1 factura' : `${fEntero(n('abierto'))} facturas` },
        { etiqueta: 'Cobrado hoy', valor: fMoneda(resumen.cobrado_hoy), nota: metodos || 'Sin pagos hoy' },
        { etiqueta: 'Pagadas', valor: fEntero(n('pagado')) },
        { etiqueta: 'Anuladas', valor: fEntero(n('anulado')) },
      ]),
      barra, lista);
    await cargarLista();
  } catch (error) {
    zona.replaceChildren(estadoDeError(error, repintar));
  }
}
