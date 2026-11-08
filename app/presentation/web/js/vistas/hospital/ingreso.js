/* Ingreso hospitalario: detalle con diagnosticos, ordenes medicas y alta; y el alta de un ingreso nuevo. */
import { api } from '../../api.js';
import { accionesFicha, bloqueDatos } from '../compartido/ficha.js';
import { sesion } from '../../sesion.js';
import { enlace } from '../../enrutador.js';
import { fFechaHora, nombreDe } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import { aviso, aviso_flotante, campo, cargando, chip, entrada, estadoDeError, lateral, modal, seleccion, tabla } from '../../ui/componentes.js';
import { areaTexto, cargarProfesionales, enviar, nombreProfesional, repetible } from '../clinica/comun.js';
import { filaDiagnostico, filaReceta } from '../clinica/formularios.js';
import { selectorDePaciente } from '../clinica/agendar.js';
import { chipDe, duracion, rutaPaciente, TIPOS_INGRESO, TIPOS_ORDEN_MEDICA } from './comun.js';

const rutaIngreso = (ing) => `${rutaPaciente(ing.id_paciente)}/ingresos/${encodeURIComponent(ing.id_ingreso)}`;
const limpio = (control) => control.value.trim() || null;

const listaDiagnosticos = (dx) => (dx.length
  ? h('div', { class: 'etiquetas' }, dx.map((d) => h('span', { class: 'chip info' }, d.descripcion, d.codigo && h('span', { class: 'codigo', text: ` ${d.codigo}` }))))
  : h('p', { class: 'muted', text: 'Sin diagnósticos registrados.' }));

function nodoOrden(o, profesionales) {
  return h('article', { class: 'orden-medica' },
    h('header', null, chip('info', null, TIPOS_ORDEN_MEDICA[o.tipo] || o.tipo),
      h('span', { class: 'hint', text: `${fFechaHora(o.fecha_hora)} · ${nombreProfesional(profesionales, o.id_profesional)}` })),
    o.descripcion && h('p', { class: 'con-saltos', text: o.descripcion }),
    o.recetas.length > 0 && tabla(['Medicamento', 'Dosis', 'Frecuencia', 'Vía'], o.recetas.map((r) => h('tr', null,
      h('td', { class: 'ajustar' }, h('b', { text: r.medicamento }), r.instrucciones && h('div', { class: 'hint', text: r.instrucciones })),
      h('td', { text: r.dosis }), h('td', { text: r.frecuencia }), h('td', { text: r.via_administracion || '—' })))));
}

/* ---------- Detalle ---------- */
export async function abrirIngreso(ingreso, { alCambiar } = {}) {
  const profesionales = await cargarProfesionales();
  const registra = sesion.tiene('consultas:registrar');
  let panel;
  const refrescar = (nuevo) => {
    panel.cerrar();
    abrirIngreso(nuevo, { alCambiar });
    alCambiar?.();
  };
  const abierto = ingreso.abierto;
  const acciones = [];
  if (registra && abierto) {
    acciones.push(
      h('button', { class: 'btn sec', type: 'button', onclick: () => abrirDiagnostico(ingreso, refrescar) }, ic('plus', 16), 'Diagnóstico'),
      h('button', { class: 'btn sec', type: 'button', onclick: () => abrirOrdenMedica(ingreso, refrescar) }, ic('list-checks', 16), 'Orden médica'),
      h('button', { class: 'btn', type: 'button', onclick: () => abrirAlta(ingreso, refrescar) }, ic('door-open', 16), 'Dar de alta'));
  }
  panel = lateral(`Ingreso de ${ingreso.nombre_paciente}`, [
    bloqueDatos('Datos del ingreso',
      h('div', { class: 'fila' }, chipDe(TIPOS_INGRESO, ingreso.tipo),
        abierto ? chip('aviso', 'clock', `Lleva ${duracion(ingreso.ingreso_en)}`) : chip('ok', 'door-open', 'Dado de alta')),
      h('dl', { class: 'lista-datos' },
        h('dt', { text: 'Paciente' }), h('dd', null, h('a', { class: 'enlace', href: enlace(`pacientes/${encodeURIComponent(ingreso.id_paciente)}`), text: ingreso.nombre_paciente, onclick: () => panel.cerrar() })),
        h('dt', { text: 'Cama' }), h('dd', { text: `${ingreso.cama} · ${ingreso.departamento}` }),
        h('dt', { text: 'Ingreso' }), h('dd', { text: fFechaHora(ingreso.ingreso_en) }),
        h('dt', { text: 'Ingresó' }), h('dd', { text: nombreProfesional(profesionales, ingreso.id_profesional) }),
        h('dt', { text: 'Motivo' }), h('dd', { class: 'con-saltos', text: ingreso.motivo }),
        !abierto && [h('dt', { text: 'Alta' }), h('dd', { text: fFechaHora(ingreso.alta_en) }),
          h('dt', { text: 'Motivo del alta' }), h('dd', { class: 'con-saltos', text: ingreso.motivo_alta || '—' })])),
    h('section', { class: 'pila-s' }, h('h3', { text: 'Diagnósticos' }), listaDiagnosticos(ingreso.diagnosticos)),
    h('section', { class: 'pila-s' }, h('h3', { text: 'Órdenes médicas' }),
      ingreso.ordenes.length
        ? h('div', { class: 'pila-s' }, [...ingreso.ordenes].sort((a, b) => b.fecha_hora.localeCompare(a.fecha_hora)).map((o) => nodoOrden(o, profesionales)))
        : h('p', { class: 'muted', text: 'Sin órdenes médicas.' })),
    !abierto && aviso('info', 'lock', 'Un ingreso con alta ya no admite diagnósticos ni órdenes nuevas.'),
  ], accionesFicha(acciones));
  return panel;
}

/* Abre el detalle a partir del id (desde camas, atenciones o la ficha). */
export async function abrirIngresoPorId(idPaciente, idIngreso, opciones) {
  const espera = lateral('Ingreso', [cargando(5)]);
  try {
    const ingreso = await api(`${rutaPaciente(idPaciente)}/ingresos/${encodeURIComponent(idIngreso)}`);
    espera.cerrar();
    return abrirIngreso(ingreso, opciones);
  } catch (error) {
    espera.nodo.querySelector('.cuerpo').replaceChildren(estadoDeError(error));
    return espera;
  }
}

function abrirDiagnostico(ingreso, alGuardar) {
  const fila = filaDiagnostico();
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'button', text: 'Agregar diagnóstico' });
  const ventana = modal('Agregar diagnóstico', h('div', { class: 'pila-s' }, fila.nodo, zona),
    [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => ventana.cerrar() }), boton]);
  boton.addEventListener('click', () => {
    if (!fila.validar()) return;
    const dx = fila.leer();
    if (!dx) {
      zona.replaceChildren(aviso('crit', 'circle-alert', h('b', { text: 'Escribe la descripción del diagnóstico.' })));
      return;
    }
    enviar(boton, zona, {}, async () => {
      const nuevo = await api(`${rutaIngreso(ingreso)}/diagnosticos`, { metodo: 'POST', cuerpo: dx });
      ventana.cerrar();
      aviso_flotante('Diagnóstico agregado');
      alGuardar(nuevo);
    });
  });
}

function abrirOrdenMedica(ingreso, alGuardar) {
  const tipo = seleccion('orden-tipo', Object.entries(TIPOS_ORDEN_MEDICA).map(([valor, texto]) => ({ valor, texto })));
  const descripcion = areaTexto('orden-descripcion', { maxlength: 1000, rows: 3 });
  const recetas = repetible('Agregar medicamento', filaReceta);
  const campos = { tipo: campo('Tipo de orden', tipo), descripcion: campo('Indicación', descripcion, { opcional: true }) };
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'button', text: 'Guardar orden' });
  const panel = lateral('Nueva orden médica', [
    h('p', { class: 'muted', text: `${ingreso.nombre_paciente} · cama ${ingreso.cama}. La orden queda firmada con tu usuario.` }),
    campos.tipo, campos.descripcion,
    h('div', null, h('div', { class: 'subtitulo', text: 'Medicamentos' }), recetas.nodo), zona,
  ], [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => panel.cerrar() }), boton]);
  boton.addEventListener('click', () => {
    if (!recetas.validar()) return;
    const lista = recetas.leer();
    if (!limpio(descripcion) && !lista.length) {
      zona.replaceChildren(aviso('crit', 'circle-alert', h('b', { text: 'Escribe la indicación o agrega al menos un medicamento.' })));
      return;
    }
    if (tipo.value === 'medicamento' && !lista.length) {
      zona.replaceChildren(aviso('crit', 'circle-alert', h('b', { text: 'Una orden de medicamento necesita al menos un medicamento.' })));
      return;
    }
    enviar(boton, zona, campos, async () => {
      const nuevo = await api(`${rutaIngreso(ingreso)}/ordenes`, { metodo: 'POST', cuerpo: { tipo: tipo.value, descripcion: limpio(descripcion), recetas: lista } });
      panel.cerrar();
      aviso_flotante('Orden médica guardada');
      alGuardar(nuevo);
    });
  });
}

function abrirAlta(ingreso, alGuardar) {
  const motivo = areaTexto('alta-motivo', { maxlength: 500, rows: 3, placeholder: 'Mejoría, traslado, alta voluntaria…' });
  const campos = { motivo: campo('Motivo del alta', motivo) };
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'button' }, ic('door-open', 16), 'Dar de alta');
  const ventana = modal('Dar de alta', h('div', { class: 'pila-s' },
    h('p', { class: 'muted', text: `${ingreso.nombre_paciente} · cama ${ingreso.cama} · lleva ${duracion(ingreso.ingreso_en)}.` }),
    aviso('info', 'info', 'La cama queda en limpieza; el personal de camas la marca disponible cuando esté lista.'),
    campos.motivo, zona), [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => ventana.cerrar() }), boton]);
  boton.addEventListener('click', () => {
    const ok = Boolean(motivo.value.trim());
    campos.motivo.marcar(ok ? null : 'Escribe el motivo del alta.');
    if (!ok) return;
    enviar(boton, zona, campos, async () => {
      const nuevo = await api(`${rutaIngreso(ingreso)}/alta`, { metodo: 'POST', cuerpo: { motivo: motivo.value.trim() } });
      ventana.cerrar();
      aviso_flotante('Alta registrada', 'door-open');
      alGuardar(nuevo);
    });
  });
}

/* ---------- Ingreso nuevo ---------- */
export async function abrirNuevoIngreso({ paciente, cama, tipo = 'emergencia', alGuardar } = {}) {
  const selector = paciente ? null : selectorDePaciente();
  const camas = seleccion('ingreso-cama', [{ valor: '', texto: 'Cargando camas disponibles…' }], { disabled: true });
  const tipoSel = seleccion('ingreso-tipo', Object.entries(TIPOS_INGRESO).map(([valor, e]) => ({ valor, texto: e.texto })), { value: tipo });
  const motivo = areaTexto('ingreso-motivo', { maxlength: 500, rows: 3 });
  const diagnosticos = repetible('Agregar diagnóstico', filaDiagnostico);
  const campos = { id_cama: campo('Cama', camas), tipo: campo('Tipo de ingreso', tipoSel), motivo: campo('Motivo del ingreso', motivo) };
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'button', disabled: true }, ic('bed-double', 16), 'Ingresar');
  const panel = lateral('Nuevo ingreso', [
    paciente ? h('p', { class: 'muted', text: `Paciente: ${nombreDe(paciente)}.` }) : selector.nodo,
    cama ? h('p', { class: 'muted', text: `Cama ${cama.codigo} · ${cama.departamento}.` }) : campos.id_cama,
    campos.tipo, campos.motivo,
    h('div', null, h('div', { class: 'subtitulo', text: 'Diagnósticos de ingreso' }), diagnosticos.nodo), zona,
  ], [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => panel.cerrar() }), boton]);

  if (cama) {
    boton.disabled = false;
  } else {
    try {
      const libres = await api('/camas', { params: { estado: 'disponible' } });
      camas.replaceChildren(...(libres.length
        ? [h('option', { value: '', text: 'Elige una cama' }), ...libres.map((c) => h('option', { value: String(c.id_cama), text: `${c.codigo} · ${c.departamento} (hab. ${c.habitacion})` }))]
        : [h('option', { value: '', text: 'No hay camas disponibles' })]));
      camas.disabled = !libres.length;
      boton.disabled = !libres.length;
      if (!libres.length) zona.replaceChildren(aviso('aviso', 'triangle-alert', 'No hay camas disponibles. Libera una en Camas antes de ingresar.'));
    } catch (error) {
      zona.replaceChildren(estadoDeError(error));
    }
  }

  boton.addEventListener('click', () => {
    const elegido = paciente || selector.valor();
    const idCama = cama ? cama.id_cama : Number(camas.value);
    let ok = true;
    if (!elegido) { selector.campo.marcar('Busca y elige al paciente.'); ok = false; }
    if (!idCama) { campos.id_cama.marcar('Elige una cama.'); ok = false; }
    const motivoOk = Boolean(motivo.value.trim());
    campos.motivo.marcar(motivoOk ? null : 'Escribe el motivo del ingreso.');
    if (!ok || !motivoOk || !diagnosticos.validar()) return;
    enviar(boton, zona, campos, async () => {
      const ingreso = await api(`${rutaPaciente(elegido.id_paciente)}/ingresos`, {
        metodo: 'POST',
        cuerpo: { id_cama: idCama, tipo: tipoSel.value, motivo: motivo.value.trim(), diagnosticos: diagnosticos.leer() },
      });
      panel.cerrar();
      aviso_flotante('Paciente ingresado', 'bed-double');
      alGuardar?.(ingreso);
    });
  });
}
