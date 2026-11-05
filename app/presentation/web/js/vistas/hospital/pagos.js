/* Pagos del Hospital General: un cobro por atencion, cargos del catalogo de servicios, pagos,
   anulacion de pagos y cierre. Ver montos exige pagos:ver; registrar, pagos:registrar. */
import { api } from '../../api.js';
import { ESTADOS_COBRO, METODOS_PAGO } from '../../catalogos.js';
import { sesion } from '../../sesion.js';
import { enlace, reflejar } from '../../enrutador.js';
import { fEntero, fFechaHora, fMoneda } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import {
  aviso, aviso_flotante, cabeza, campo, cargando, chip, cifras, confirmar, entrada, estadoDeError, lateral, modal, segmento, seleccion, tabla, vacio,
} from '../../ui/componentes.js';
import { enviar } from '../clinica/comun.js';
import { chipDe, rutaPaciente } from './comun.js';

const rutaCobro = (c) => `${rutaPaciente(c.id_paciente)}/cobros/${encodeURIComponent(c.id_cobro)}`;
const DINERO = /^\d{1,10}(\.\d{1,2})?$/;
const LIMITE = 100;
export const chipCobro = (estado) => chipDe(ESTADOS_COBRO, estado);

/* ---------- Detalle ---------- */
export function abrirCobro(cobro, alCambiar) {
  const registra = sesion.tiene('pagos:registrar');
  const abierto = cobro.estado === 'abierto';
  let panel;
  const refrescar = (nuevo) => {
    panel.cerrar();
    abrirCobro(nuevo, alCambiar);
    alCambiar?.();
  };
  const cargos = cobro.cargos.length
    ? tabla(['Concepto', { texto: 'Cant.', clase: 'der' }, { texto: 'P. unitario', clase: 'der' }, { texto: 'Subtotal', clase: 'der' }], cobro.cargos.map((c) => h('tr', null,
      h('td', { class: 'ajustar', text: c.concepto }), h('td', { class: 'der', text: c.cantidad }),
      h('td', { class: 'der', text: fMoneda(c.precio_unitario) }), h('td', { class: 'der', text: fMoneda(c.monto) }))))
    : h('p', { class: 'muted', text: 'Sin cargos todavía.' });
  const pagos = cobro.pagos.length
    ? tabla(['Fecha', 'Método', 'Referencia', { texto: 'Monto', clase: 'der' }, ''], cobro.pagos.map((p) => h('tr', null,
      h('td', { class: 'num', text: fFechaHora(p.fecha_hora) }), h('td', { text: METODOS_PAGO[p.metodo] || p.metodo }),
      h('td', { class: 'ajustar', text: p.referencia || '—' }),
      h('td', { class: `der ${p.anulado ? 'tachado' : ''}`, text: fMoneda(p.monto) }),
      h('td', null, p.anulado ? chip('', 'ban', 'Anulado') : (registra && ['abierto', 'cerrado'].includes(cobro.estado) && h('button', {
        class: 'btn tenue sm', type: 'button', text: 'Anular',
        onclick: () => confirmar({
          titulo: 'Anular pago',
          peligro: true,
          accion: 'Anular pago',
          cuerpo: [h('p', { text: `El pago de ${fMoneda(p.monto)} (${METODOS_PAGO[p.metodo] || p.metodo}) queda anulado: no se borra y el saldo vuelve a subir.` })],
          alConfirmar: async () => {
            const nuevo = await api(`${rutaCobro(cobro)}/pagos/${encodeURIComponent(p.id_pago)}/anular`, { metodo: 'POST' });
            aviso_flotante('Pago anulado', 'ban');
            refrescar(nuevo);
          },
        }),
      }))))))
    : h('p', { class: 'muted', text: 'Sin pagos.' });

  const acciones = [];
  const sinPagos = !cobro.pagos.some((p) => !p.anulado);
  const anular = () => h('button', {
    class: 'btn peligro', type: 'button', text: 'Anular cobro',
    onclick: () => confirmar({
      titulo: 'Anular cobro',
      peligro: true,
      accion: 'Anular cobro',
      cuerpo: [h('p', { text: `El cobro ${cobro.id_cobro} queda anulado: no se borra y ya no admite cargos ni pagos. La atención se podrá cobrar de nuevo.` })],
      alConfirmar: async () => {
        refrescar(await api(`${rutaCobro(cobro)}/anular`, { metodo: 'POST' }));
        aviso_flotante('Cobro anulado', 'ban');
      },
    }),
  });
  if (registra && abierto) {
    if (sinPagos) {
      acciones.push(anular());
    }
    acciones.push(h('button', { class: 'btn sec', type: 'button', onclick: () => abrirCargo(cobro, refrescar) }, ic('plus', 16), 'Agregar cargo'));
    if (Number(cobro.saldo) > 0) acciones.push(h('button', { class: 'btn', type: 'button', onclick: () => abrirPago(cobro, refrescar) }, ic('banknote', 16), 'Registrar pago'));
    if (cobro.cargos.length) {
      acciones.push(h('button', {
        class: 'btn sec', type: 'button',
        onclick: () => confirmar({
          titulo: 'Cerrar cobro',
          accion: 'Cerrar cobro',
          cuerpo: [h('p', { text: `Al cerrarlo ya no admite cargos nuevos. ${Number(cobro.saldo) > 0 ? `El saldo de ${fMoneda(cobro.saldo)} se puede seguir pagando.` : ''}` })],
          alConfirmar: async () => {
            refrescar(await api(`${rutaCobro(cobro)}/cerrar`, { metodo: 'POST' }));
            aviso_flotante('Cobro cerrado', 'lock');
          },
        }),
      }, ic('lock', 16), 'Cerrar cobro'));
    }
  } else if (registra && cobro.estado === 'cerrado') {
    /* Cerrado: ya no admite cargos, pero si pagos hasta saldarse. */
    if (sinPagos) acciones.push(anular());
    if (Number(cobro.saldo) > 0) acciones.push(h('button', { class: 'btn', type: 'button', onclick: () => abrirPago(cobro, refrescar) }, ic('banknote', 16), 'Registrar pago'));
  }

  panel = lateral(`Cobro ${cobro.id_cobro}`, [
    h('div', { class: 'fila' }, chipCobro(cobro.estado)),
    !registra && aviso('info', 'eye', 'Solo lectura: tu cuenta puede ver los cobros, no registrar movimientos.'),
    h('dl', { class: 'lista-datos' },
      h('dt', { text: 'Paciente' }), h('dd', null, h('a', { class: 'enlace', href: enlace(`pacientes/${encodeURIComponent(cobro.id_paciente)}`, { origen: 'pagos' }), text: cobro.nombre_paciente, onclick: () => panel.cerrar() })),
      h('dt', { text: 'Atención' }), h('dd', { class: 'num', text: cobro.id_atencion }),
      h('dt', { text: 'Abierto el' }), h('dd', { text: fFechaHora(cobro.abierto_en) }),
      cobro.cerrado_en && [h('dt', { text: cobro.estado === 'anulado' ? 'Anulado el' : 'Cerrado el' }), h('dd', { text: fFechaHora(cobro.cerrado_en) })],
      cobro.descripcion && [h('dt', { text: 'Descripción' }), h('dd', { text: cobro.descripcion })]),
    h('section', { class: 'pila-s' }, h('h3', { text: 'Cargos' }), cargos),
    h('dl', { class: 'totales' },
      h('dt', { text: 'Total' }), h('dd', { text: fMoneda(cobro.total) }),
      h('dt', { text: 'Pagado' }), h('dd', { text: fMoneda(cobro.pagado) }),
      h('dt', { class: 'saldo', text: 'Saldo' }), h('dd', { class: 'saldo', text: fMoneda(cobro.saldo) })),
    h('section', { class: 'pila-s' }, h('h3', { text: 'Pagos' }), pagos),
  ], acciones.length ? acciones : null);
  return panel;
}

async function abrirCargo(cobro, alGuardar) {
  const servicio = seleccion('cargo-servicio', [{ valor: '', texto: 'Cargando servicios…' }], { disabled: true });
  const concepto = entrada('cargo-concepto', { maxlength: 200, placeholder: 'Solo si no está en el catálogo' });
  const cantidad = entrada('cargo-cantidad', { type: 'number', min: 0.01, step: '0.01', value: '1', inputmode: 'decimal' });
  const precio = entrada('cargo-precio', { type: 'number', min: 0, step: '0.01', inputmode: 'decimal' });
  const campos = {
    id_servicio: campo('Servicio', servicio, { ayuda: 'Toma el nombre y la tarifa del catálogo del hospital.' }),
    concepto: campo('Concepto libre', concepto, { opcional: true }),
    cantidad: campo('Cantidad', cantidad),
    precio_unitario: campo('Precio unitario (Q)', precio, { ayuda: 'Con un servicio del catálogo, vacío usa su tarifa.' }),
  };
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'button', text: 'Agregar cargo' });
  const ventana = modal('Agregar cargo', h('div', { class: 'pila-s' }, campos.id_servicio, campos.concepto, h('div', { class: 'dos' }, campos.cantidad, campos.precio_unitario), zona),
    [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => ventana.cerrar() }), boton]);
  try {
    const lista = await api('/servicios');
    servicio.replaceChildren(h('option', { value: '', text: 'Concepto libre (sin catálogo)' }),
      ...lista.map((s) => h('option', { value: String(s.id_servicio), text: `${s.nombre}${s.tarifa_general ? ` · ${fMoneda(s.tarifa_general)}` : ''}` })));
    servicio.disabled = false;
  } catch {
    servicio.replaceChildren(h('option', { value: '', text: 'Catálogo no disponible: usa concepto libre' }));
  }
  boton.addEventListener('click', () => {
    const conServicio = Boolean(servicio.value);
    const conceptoOk = conServicio || Boolean(concepto.value.trim());
    const cantidadOk = DINERO.test(cantidad.value) && Number(cantidad.value) > 0;
    const precioOk = precio.value === '' ? conServicio : DINERO.test(precio.value);
    campos.concepto.marcar(conceptoOk ? null : 'Elige un servicio o escribe el concepto.');
    campos.cantidad.marcar(cantidadOk ? null : 'Escribe una cantidad mayor que cero, con hasta dos decimales.');
    campos.precio_unitario.marcar(precioOk ? null : 'Escribe el precio, con hasta dos decimales.');
    if (!conceptoOk || !cantidadOk || !precioOk) return;
    const cuerpo = { cantidad: cantidad.value };
    if (conServicio) cuerpo.id_servicio = Number(servicio.value);
    if (concepto.value.trim()) cuerpo.concepto = concepto.value.trim();
    if (precio.value !== '') cuerpo.precio_unitario = precio.value;
    enviar(boton, zona, campos, async () => {
      const nuevo = await api(`${rutaCobro(cobro)}/cargos`, { metodo: 'POST', cuerpo });
      ventana.cerrar();
      aviso_flotante('Cargo agregado');
      alGuardar(nuevo);
    });
  });
}

function abrirPago(cobro, alGuardar) {
  const metodo = seleccion('pago-metodo', Object.entries(METODOS_PAGO).map(([valor, texto]) => ({ valor, texto })));
  const monto = entrada('pago-monto', { type: 'number', min: 0.01, step: '0.01', value: cobro.saldo, inputmode: 'decimal' });
  const referencia = entrada('pago-referencia', { maxlength: 150 });
  const campos = {
    metodo: campo('Método', metodo),
    monto: campo('Monto (Q)', monto, { ayuda: `Saldo pendiente: ${fMoneda(cobro.saldo)}` }),
    referencia: campo('Referencia', referencia, { opcional: true, ayuda: 'Número de comprobante o de cheque. Nunca escribas datos de la tarjeta.' }),
  };
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'button', text: 'Registrar pago' });
  const ventana = modal('Registrar pago', h('div', { class: 'pila-s' }, h('p', { class: 'muted', text: `Cobro ${cobro.id_cobro} · ${cobro.nombre_paciente}` }), campos.metodo, campos.monto, campos.referencia, zona),
    [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => ventana.cerrar() }), boton]);
  boton.addEventListener('click', () => {
    let problema = null;
    if (!DINERO.test(monto.value) || Number(monto.value) <= 0) problema = 'Escribe un monto mayor que cero, con hasta dos decimales.';
    else if (Number(monto.value) > Number(cobro.saldo)) problema = 'El pago no puede exceder el saldo pendiente.';
    campos.monto.marcar(problema);
    if (problema) return;
    enviar(boton, zona, campos, async () => {
      const nuevo = await api(`${rutaCobro(cobro)}/pagos`, {
        metodo: 'POST',
        cuerpo: { metodo: metodo.value, monto: monto.value, referencia: referencia.value.trim() || null },
      });
      ventana.cerrar();
      aviso_flotante(nuevo.estado === 'pagado' ? 'Pago registrado. El cobro quedó pagado.' : 'Pago registrado');
      alGuardar(nuevo);
    });
  });
}

/* Abre el cobro de una atencion (uno vigente por atencion; la API responde 409 si ya existe). */
export async function abrirCobroDeAtencion(atencion, alCambiar) {
  const cobro = await api(`${rutaPaciente(atencion.id_paciente)}/cobros`, { metodo: 'POST', cuerpo: { id_atencion: atencion.id_atencion } });
  aviso_flotante('Cobro abierto. Agrega sus cargos.');
  alCambiar?.();
  return abrirCobro(cobro, alCambiar);
}

export async function abrirCobroPorId(idPaciente, idCobro, alCambiar) {
  return abrirCobro(await api(`${rutaPaciente(idPaciente)}/cobros/${encodeURIComponent(idCobro)}`), alCambiar);
}

/* ---------- Tablero ---------- */
export async function vistaPagos({ contenedor, params, repintar }) {
  let filtro = ESTADOS_COBRO[params.estado] ? params.estado : '';
  const encabezado = cabeza('Pagos', 'Cobros por atención y los pagos que los cubren.',
    sesion.tiene('pagos:registrar') && h('span', { class: 'hint', text: 'Los cobros se abren desde la atención, en Atenciones.' }));
  const zona = h('div', { class: 'pila', 'aria-live': 'polite' }, cargando(6));
  contenedor.append(encabezado, zona);

  const lista = h('div', { class: 'pila-s' });
  async function cargarLista() {
    lista.replaceChildren(cargando(4));
    try {
      const cobros = await api('/cobros', { params: { estado: filtro, limite: LIMITE } });
      lista.replaceChildren(...(cobros.length
        ? [tabla(['Cobro', 'Paciente', 'Abierto', 'Estado', { texto: 'Total', clase: 'der' }, { texto: 'Pagado', clase: 'der' }, { texto: 'Saldo', clase: 'der' }],
          cobros.map((c) => {
            const abrir = () => abrirCobro(c, repintar);
            return h('tr', { class: 'clic', onclick: abrir },
              h('td', null, h('button', { class: 'enlace num', type: 'button', text: c.id_cobro, onclick: (e) => { e.stopPropagation(); abrir(); } })),
              h('td', { class: 'ajustar', text: c.nombre_paciente }), h('td', { class: 'num', text: fFechaHora(c.abierto_en) }), h('td', null, chipCobro(c.estado)),
              h('td', { class: `der ${c.estado === 'anulado' ? 'tachado' : ''}`, text: fMoneda(c.total) }),
              h('td', { class: 'der', text: fMoneda(c.pagado) }),
              h('td', { class: 'der', text: c.estado === 'anulado' ? '—' : fMoneda(c.saldo) }));
          })),
        cobros.length === LIMITE && h('p', { class: 'hint', text: `Se muestran los ${LIMITE} más recientes.` })].filter(Boolean)
        : [vacio('banknote', 'Sin cobros', filtro ? 'No hay cobros en este estado.' : 'Los cobros aparecen aquí cuando se abren desde una atención.')]));
    } catch (error) {
      lista.replaceChildren(estadoDeError(error, cargarLista));
    }
  }

  try {
    const resumen = await api('/cobros/resumen');
    const n = (estado) => resumen.cobros_por_estado[estado] || 0;
    const metodos = Object.entries(resumen.cobrado_hoy_por_metodo).filter(([, v]) => Number(v) > 0).map(([k, v]) => `${METODOS_PAGO[k] || k}: ${fMoneda(v)}`).join(', ');
    const barra = h('div');
    const pintarBarra = () => barra.replaceChildren(segmento('Filtrar cobros', [
      { valor: '', texto: `Todos ${fEntero(Object.values(resumen.cobros_por_estado).reduce((s, v) => s + v, 0))}` },
      ...Object.entries(ESTADOS_COBRO).map(([k, e]) => ({ valor: k, texto: `${e.texto} ${fEntero(n(k))}` })),
    ], filtro, (v) => {
      filtro = v;
      reflejar('pagos', { estado: v });
      pintarBarra();
      cargarLista();
    }));
    pintarBarra();
    zona.replaceChildren(
      cifras([
        { etiqueta: 'Saldo pendiente', valor: fMoneda(resumen.saldo_pendiente), clase: Number(resumen.saldo_pendiente) > 0 ? 'aviso' : '' },
        { etiqueta: 'Cobrado hoy', valor: fMoneda(resumen.cobrado_hoy), nota: metodos || 'Sin pagos hoy' },
        { etiqueta: 'Cobros abiertos', valor: fEntero(n('abierto')) },
        { etiqueta: 'Pagos anulados', valor: fEntero(resumen.pagos_anulados) },
      ]),
      barra, lista);
    await cargarLista();
  } catch (error) {
    zona.replaceChildren(estadoDeError(error, repintar));
  }
}
