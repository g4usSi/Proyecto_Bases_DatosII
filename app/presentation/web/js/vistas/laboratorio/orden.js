/* Orden de laboratorio: muestras, resultados por prueba, validacion y cancelacion.
   Una orden validada o cancelada ya no se modifica; el servidor lo vuelve a comprobar. */
import { api } from '../../api.js';
import { accionesFicha, bloqueDatos } from '../compartido/ficha.js';
import { sesion } from '../../sesion.js';
import { enlace } from '../../enrutador.js';
import { fFechaHora } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import { aviso, aviso_flotante, campo, cargando, chip, confirmar, entrada, estadoDeError, lateral, modal, seleccion, tabla, vacio } from '../../ui/componentes.js';
import { areaTexto, enviar } from '../clinica/comun.js';
import { chipLectura, chipOrden, estaAbierta, rutaOrden, textoReferencia, textoValor } from './comun.js';

const limpio = (texto) => texto.trim() || null;
const pieDe = (cerrar, texto) => {
  const boton = h('button', { class: 'btn', type: 'button', text: texto });
  return { boton, nodos: [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: cerrar }), boton] };
};

function abrirMuestra(orden, alGuardar) {
  const tipo = entrada('muestra-tipo', { maxlength: 100, placeholder: 'Sangre, orina, heces…' });
  const condicion = entrada('muestra-condicion', { maxlength: 300, placeholder: 'Ayuno de 8 horas' });
  const observaciones = areaTexto('muestra-obs', { maxlength: 500 });
  const campos = {
    tipo: campo('Tipo de muestra', tipo),
    condicion: campo('Condición', condicion, { opcional: true }),
    observaciones: campo('Observaciones', observaciones, { opcional: true }),
  };
  const zona = h('div');
  const pie = pieDe(() => ventana.cerrar(), 'Registrar muestra');
  const ventana = modal(`Muestra para ${orden.numero_orden}`, h('div', { class: 'pila-s' }, Object.values(campos), h('p', { class: 'hint', text: 'Se registra con la hora actual.' }), zona), pie.nodos);
  pie.boton.addEventListener('click', () => enviar(pie.boton, zona, campos, async () => {
    if (!tipo.value.trim()) {
      throw Object.assign(new Error('Revisa el formulario.'), { campos: { tipo: 'Indica el tipo de muestra.' } });
    }
    const actualizada = await api(`${rutaOrden(orden.id_paciente, orden.id_orden)}/muestras`, {
      metodo: 'POST',
      cuerpo: { tipo: tipo.value.trim(), condicion: limpio(condicion.value), observaciones: limpio(observaciones.value) },
    });
    ventana.cerrar();
    aviso_flotante('Muestra registrada');
    alGuardar(actualizada);
  }));
}

/* Un control por parametro segun su tipo; los vacios no se envian. */
function controlDe(param, previo) {
  const id = `res-${param.codigo}`;
  if (param.tipo_valor === 'booleano') {
    return seleccion(id, [{ valor: '', texto: 'Sin resultado' }, { valor: 'true', texto: 'Positivo' }, { valor: 'false', texto: 'Negativo' }],
      { value: previo == null ? '' : String(previo.valor) });
  }
  return entrada(id, param.tipo_valor === 'numerico'
    ? { type: 'number', step: 'any', inputmode: 'decimal', value: previo?.valor ?? '' }
    : { maxlength: 500, value: previo?.valor ?? '' });
}

function leerValor(param, control) {
  const v = control.value.trim();
  if (!v) return undefined;
  if (param.tipo_valor === 'booleano') return v === 'true';
  if (param.tipo_valor === 'numerico') {
    const n = Number(v);
    return Number.isFinite(n) ? n : NaN;
  }
  return v;
}

function abrirResultados(orden, prueba, alGuardar) {
  const previos = new Map(prueba.resultados.map((r) => [r.codigo, r]));
  const controles = prueba.parametros.map((param) => ({ param, control: controlDe(param, previos.get(param.codigo)) }));
  const campos = Object.fromEntries(controles.map(({ param, control }) => [param.codigo,
    campo(`${param.nombre}${param.unidad ? ` (${param.unidad})` : ''}`, control, { ayuda: `Referencia: ${textoReferencia(param.referencia, param.unidad)}`, opcional: true })]));
  const observaciones = areaTexto('res-obs', { maxlength: 1000, value: prueba.observaciones || '' });
  campos.observaciones = campo('Observaciones', observaciones, { opcional: true });
  const zona = h('div');
  const pie = pieDe(() => ventana.cerrar(), 'Guardar resultados');
  const ventana = modal(prueba.nombre, h('div', { class: 'pila-s' },
    h('p', { class: 'hint', text: `${orden.numero_orden} · versión ${prueba.version} de la prueba. Puedes corregirlos mientras la orden siga abierta.` }),
    Object.values(campos), zona), pie.nodos);
  pie.boton.addEventListener('click', () => enviar(pie.boton, zona, campos, async () => {
    const valores = [];
    const errores = {};
    for (const { param, control } of controles) {
      const valor = leerValor(param, control);
      if (Number.isNaN(valor)) errores[param.codigo] = 'Escribe un número.';
      else if (valor !== undefined) valores.push({ codigo_parametro: param.codigo, valor });
    }
    if (Object.keys(errores).length) throw Object.assign(new Error('Revisa los valores marcados.'), { campos: errores });
    if (!valores.length) throw new Error('Registra al menos un resultado.');
    const actualizada = await api(`${rutaOrden(orden.id_paciente, orden.id_orden)}/pruebas/${encodeURIComponent(prueba.codigo)}/resultados`, {
      metodo: 'PUT', cuerpo: { valores, observaciones: limpio(observaciones.value) },
    });
    ventana.cerrar();
    aviso_flotante('Resultados guardados');
    alGuardar(actualizada);
  }));
}

function abrirCancelacion(orden, alGuardar) {
  const motivo = areaTexto('orden-cancelar', { maxlength: 300, placeholder: 'Por qué se cancela' });
  const campos = { motivo: campo('Motivo', motivo) };
  const zona = h('div');
  const boton = h('button', { class: 'btn peligro solido', type: 'button', text: 'Cancelar orden' });
  const ventana = modal(`Cancelar ${orden.numero_orden}`, h('div', { class: 'pila-s' },
    h('p', { text: 'La orden queda cancelada con su motivo y ya no admite muestras ni resultados.' }), campos.motivo, zona),
  [h('button', { class: 'btn sec', type: 'button', text: 'Volver', onclick: () => ventana.cerrar() }), boton]);
  boton.addEventListener('click', () => enviar(boton, zona, campos, async () => {
    if (!motivo.value.trim()) {
      throw Object.assign(new Error('Revisa el formulario.'), { campos: { motivo: 'Indica el motivo.' } });
    }
    const actualizada = await api(`${rutaOrden(orden.id_paciente, orden.id_orden)}/cancelar`, { metodo: 'POST', cuerpo: { motivo: motivo.value.trim() } });
    ventana.cerrar();
    aviso_flotante('Orden cancelada');
    alGuardar(actualizada);
  }));
}

function nodoPrueba(orden, prueba, alGuardar) {
  const editable = estaAbierta(orden) && sesion.tiene('laboratorio:resultados');
  const con = prueba.resultados.length > 0;
  return h('article', { class: 'prueba-orden' },
    h('header', { class: 'fila' },
      h('b', { text: prueba.nombre }), h('span', { class: 'hint codigo', text: `${prueba.codigo} · v${prueba.version}` }),
      con ? chip('ok', 'circle-check', 'Con resultados')
        : (estaAbierta(orden) ? chip('aviso', 'hourglass', 'Pendiente') : chip('', 'ban', 'Sin resultados'))),
    con
      ? tabla(['Parámetro', 'Resultado', 'Lectura', 'Referencia'], prueba.resultados.map((r) => h('tr', { class: r.interpretacion && r.interpretacion !== 'normal' ? `fuera-${r.interpretacion}` : '' },
        h('td', { class: 'ajustar', text: r.nombre }),
        h('td', { class: 'num' }, h('b', { text: textoValor(r) })),
        h('td', null, chipLectura(r.interpretacion)),
        h('td', { class: 'hint ajustar', text: textoReferencia(r.referencia, r.unidad) }))))
      : h('ul', { class: 'lista-simple' }, prueba.parametros.map((param) => h('li', null, param.nombre,
        h('span', { class: 'hint', text: ` · ref. ${textoReferencia(param.referencia, param.unidad)}` })))),
    prueba.observaciones && h('p', { class: 'con-saltos hint', text: prueba.observaciones }),
    prueba.registrado_en && h('small', { class: 'hint', text: `Registrado el ${fFechaHora(prueba.registrado_en)}` }),
    editable && accionesFicha([h('button', { class: 'btn sec sm', type: 'button', onclick: () => abrirResultados(orden, prueba, alGuardar) },
      ic('pencil', 14), con ? 'Corregir resultados' : 'Registrar resultados')]));
}

function contenidoOrden(orden, { nombrePaciente, alGuardar, panel }) {
  const abierta = estaAbierta(orden);
  const completas = orden.pruebas.length > 0 && orden.pruebas.every((p) => p.resultados.length > 0);
  const acciones = [];
  if (abierta && sesion.tiene('laboratorio:resultados')) {
    acciones.push(h('button', { class: 'btn sec', type: 'button', onclick: () => abrirMuestra(orden, alGuardar) }, ic('test-tubes', 16), 'Registrar muestra'));
  }
  if (abierta && sesion.tiene('laboratorio:validar')) {
    acciones.push(h('button', {
      class: 'btn', type: 'button', disabled: !completas, title: completas ? null : 'Cada prueba necesita al menos un resultado',
      onclick: () => confirmar({
        titulo: `Validar ${orden.numero_orden}`,
        accion: 'Validar orden',
        cuerpo: [h('p', { text: 'Después de validarla los resultados ya no se pueden corregir.' })],
        alConfirmar: async () => {
          const validada = await api(`${rutaOrden(orden.id_paciente, orden.id_orden)}/validar`, { metodo: 'POST' });
          aviso_flotante('Orden validada');
          alGuardar(validada);
        },
      }),
    }, ic('badge-check', 16), 'Validar'));
  }
  if (abierta && sesion.tiene('consultas:registrar')) {
    acciones.push(h('button', { class: 'btn peligro', type: 'button', onclick: () => abrirCancelacion(orden, alGuardar) }, ic('ban', 16), 'Cancelar orden'));
  }

  return [
    bloqueDatos('Datos de la orden',
      h('div', { class: 'fila' }, chipOrden(orden.estado), h('b', { class: 'num', text: orden.numero_orden })),
      h('dl', { class: 'lista-datos' },
        nombrePaciente && [h('dt', { text: 'Paciente' }), h('dd', null, h('a', {
          class: 'enlace', href: enlace(`pacientes/${encodeURIComponent(orden.id_paciente)}`, { origen: 'ordenes' }), text: nombrePaciente, onclick: () => panel.cerrar(),
        }))],
        h('dt', { text: 'Solicitada' }), h('dd', { text: fFechaHora(orden.solicitada_en) }),
        orden.validada_en && [h('dt', { text: 'Validada' }), h('dd', { text: fFechaHora(orden.validada_en) })])),
    orden.motivo_cancelacion && aviso('', 'ban', h('b', { text: 'Cancelada: ' }), orden.motivo_cancelacion),
    abierta && !completas && sesion.tiene('laboratorio:validar') && h('p', { class: 'hint', text: 'Podrás validarla cuando cada prueba tenga resultados.' }),
    accionesFicha(acciones),
    h('section', { class: 'pila-s' }, h('h3', { text: `Muestras (${orden.muestras.length})` }),
      orden.muestras.length
        ? h('ul', { class: 'lista-simple' }, orden.muestras.map((m) => h('li', null,
          h('b', { text: m.tipo }), h('span', { class: 'hint', text: ` · ${m.codigo} · ${fFechaHora(m.tomada_en)}` }),
          m.condicion && h('span', { class: 'bloque hint', text: m.condicion }),
          m.observaciones && h('span', { class: 'bloque hint', text: m.observaciones }))))
        : h('p', { class: 'muted', text: 'Aún no se registran muestras.' })),
    h('section', { class: 'pila-s' }, h('h3', { text: `Pruebas (${orden.pruebas.length})` }),
      orden.pruebas.map((p) => nodoPrueba(orden, p, alGuardar))),
  ];
}

/* Abre la orden en un panel; cada cambio repinta el panel con la orden que devuelve el servidor. */
export async function abrirOrden(idPaciente, idOrden, { nombrePaciente, alCambiar } = {}) {
  const panel = lateral('Orden de laboratorio', [cargando(6)]);
  const cuerpo = panel.nodo.querySelector('.cuerpo');
  const pintar = (orden) => cuerpo.replaceChildren(...contenidoOrden(orden, {
    nombrePaciente, panel,
    alGuardar: (actualizada) => {
      pintar(actualizada);
      alCambiar?.();
    },
  }).flat().filter(Boolean));
  try {
    pintar(await api(rutaOrden(idPaciente, idOrden)));
  } catch (error) {
    cuerpo.replaceChildren(error.estado === 404
      ? vacio('inbox', 'Orden no encontrada', 'La orden ya no está en el historial del paciente.')
      : estadoDeError(error));
  }
}

/* Solicitud desde la ficha: la orden cuelga de una consulta del paciente. */
export async function abrirNuevaOrden(p, { consultas, alGuardar }) {
  const zona = h('div');
  const pie = pieDe(() => panel.cerrar(), 'Solicitar orden');
  const panel = lateral('Nueva orden de laboratorio', [cargando(5)], pie.nodos);
  const cuerpo = panel.nodo.querySelector('.cuerpo');
  pie.boton.disabled = true;
  let catalogo;
  try {
    catalogo = await api('/laboratorio/pruebas');
  } catch (error) {
    pie.boton.hidden = true;
    cuerpo.replaceChildren(estadoDeError(error));
    return;
  }
  if (!consultas.length) {
    pie.boton.hidden = true;
    cuerpo.replaceChildren(vacio('notebook-text', 'Primero registra una consulta', 'Cada orden se solicita desde una consulta del paciente.'));
    return;
  }
  const consulta = seleccion('orden-consulta', consultas.map((c) => ({ valor: c.id_consulta, texto: `${fFechaHora(c.fecha_hora)} · ${c.motivo}` })));
  const marcas = catalogo.map((prueba) => ({
    prueba,
    caja: h('input', { type: 'checkbox', id: `orden-p-${prueba.codigo}`, value: prueba.codigo }),
  }));
  const grupo = h('fieldset', { class: 'pila-s lista-pruebas', id: 'orden-pruebas' },
    h('legend', { text: 'Pruebas' }),
    marcas.map(({ prueba, caja }) => h('label', { class: 'opcion-prueba', for: caja.id }, caja,
      h('span', null, h('b', { text: prueba.nombre }),
        h('small', { class: 'hint bloque', text: [prueba.tipo_muestra, prueba.parametros.length === 1 ? '1 parámetro' : `${prueba.parametros.length} parámetros`, prueba.indicaciones].filter(Boolean).join(' · ') })))));
  const campos = { id_consulta: campo('Consulta', consulta, { ayuda: 'La consulta en la que se piden los exámenes.' }), pruebas: campo('Pruebas', grupo, { id: 'orden-pruebas' }) };
  cuerpo.replaceChildren(h('p', { class: 'muted', text: `${p.nombres} ${p.apellidos}` }), campos.id_consulta, grupo, zona);
  pie.boton.disabled = false;
  pie.boton.addEventListener('click', () => enviar(pie.boton, zona, campos, async () => {
    const pruebas = marcas.filter((m) => m.caja.checked).map((m) => m.prueba.codigo);
    if (!pruebas.length) throw new Error('Elige al menos una prueba.');
    const orden = await api(rutaOrden(p.id_paciente), { metodo: 'POST', cuerpo: { id_consulta: consulta.value, pruebas } });
    panel.cerrar();
    aviso_flotante(`Orden ${orden.numero_orden} solicitada`);
    alGuardar?.(orden);
  }));
}
