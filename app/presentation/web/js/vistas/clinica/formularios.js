/* Formularios de la ficha: consulta, adenda, alergias, datos del paciente y archivo. */
import { api } from '../../api.js';
import { fFecha, hoyLocal, nombreDe } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import { aviso, aviso_flotante, campo, entrada, lateral, modal, seleccion } from '../../ui/componentes.js';
import { areaTexto, enviar, nuevoId, repetible } from './comun.js';

const ruta = (p) => `/pacientes/${encodeURIComponent(p.id_paciente)}`;
const limpio = (control) => control.value.trim() || null;
const obligatorio = (nodo, control, mensaje) => {
  const ok = Boolean(control.value.trim());
  nodo.marcar(ok ? null : mensaje);
  return ok;
};

const pie = (cancelar, texto) => {
  const boton = h('button', { class: 'btn', type: 'button', text: texto });
  return { boton, nodos: [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: cancelar }), boton] };
};

/* ---------- Filas repetibles ---------- */
export function filaDiagnostico() {
  const descripcion = entrada(nuevoId('dx'), { maxlength: 500, placeholder: 'Descripción' });
  const codigo = entrada(nuevoId('dx-c'), { maxlength: 20, placeholder: 'p. ej. K02.1' });
  const sistema = entrada(nuevoId('dx-s'), { maxlength: 20, placeholder: 'CIE-10' });
  const cDesc = campo('Diagnóstico', descripcion);
  return {
    nodo: h('div', { class: 'pila-s' }, cDesc, h('div', { class: 'dos' }, campo('Código', codigo, { opcional: true }), campo('Sistema de codificación', sistema, { opcional: true }))),
    leer: () => (limpio(descripcion) ? { descripcion: limpio(descripcion), codigo: limpio(codigo), sistema_codigo: limpio(sistema) } : null),
    validar: () => !(limpio(codigo) || limpio(sistema)) || obligatorio(cDesc, descripcion, 'Escribe la descripción.'),
  };
}

function filaTratamiento() {
  const descripcion = areaTexto(nuevoId('tx'), { maxlength: 1000, rows: 2 });
  return {
    nodo: campo('Tratamiento', descripcion),
    leer: () => (limpio(descripcion) ? { descripcion: limpio(descripcion) } : null),
  };
}

export function filaReceta() {
  const medicamento = entrada(nuevoId('rx-m'), { maxlength: 200 });
  const dosis = entrada(nuevoId('rx-d'), { maxlength: 200 });
  const frecuencia = entrada(nuevoId('rx-f'), { maxlength: 200 });
  const via = entrada(nuevoId('rx-v'), { maxlength: 100 });
  const dias = entrada(nuevoId('rx-n'), { type: 'number', min: 1, max: 3650, inputmode: 'numeric' });
  const instrucciones = areaTexto(nuevoId('rx-i'), { maxlength: 1000, rows: 2 });
  const requeridos = [
    [campo('Medicamento', medicamento), medicamento, 'Escribe el medicamento.'],
    [campo('Dosis', dosis), dosis, 'Escribe la dosis.'],
    [campo('Frecuencia', frecuencia), frecuencia, 'Escribe la frecuencia.'],
  ];
  const opcionales = [via, dias, instrucciones];
  const hayAlgo = () => [medicamento, dosis, frecuencia, ...opcionales].some((c) => c.value.trim());
  return {
    nodo: h('div', { class: 'pila-s' }, requeridos[0][0],
      h('div', { class: 'dos' }, requeridos[1][0], requeridos[2][0]),
      h('div', { class: 'dos' }, campo('Vía', via, { opcional: true }), campo('Duración (días)', dias, { opcional: true })),
      campo('Instrucciones', instrucciones, { opcional: true })),
    leer: () => (hayAlgo() ? {
      medicamento: limpio(medicamento), dosis: limpio(dosis), frecuencia: limpio(frecuencia),
      via_administracion: limpio(via), duracion_dias: dias.value ? Number(dias.value) : null, instrucciones: limpio(instrucciones),
    } : null),
    validar: () => !hayAlgo() || requeridos.map(([nodo, control, mensaje]) => obligatorio(nodo, control, mensaje)).every(Boolean),
  };
}

export function filaAlergia() {
  const sustancia = entrada(nuevoId('al-s'), { maxlength: 120 });
  const reaccion = entrada(nuevoId('al-r'), { maxlength: 300 });
  const severidad = entrada(nuevoId('al-v'), { maxlength: 50, placeholder: 'Leve, moderada, grave…' });
  const cSustancia = campo('Sustancia', sustancia);
  return {
    nodo: h('div', { class: 'pila-s' }, cSustancia, h('div', { class: 'dos' }, campo('Reacción', reaccion, { opcional: true }), campo('Severidad', severidad, { opcional: true }))),
    leer: () => (limpio(sustancia) ? { sustancia: limpio(sustancia), reaccion: limpio(reaccion), severidad: limpio(severidad) } : null),
    validar: () => !(limpio(reaccion) || limpio(severidad)) || obligatorio(cSustancia, sustancia, 'Escribe la sustancia.'),
  };
}

function bloquesClinicos() {
  const dx = repetible('Agregar diagnóstico', filaDiagnostico);
  const tx = repetible('Agregar tratamiento', filaTratamiento);
  const rx = repetible('Agregar receta', filaReceta);
  return {
    nodos: [
      h('div', null, h('div', { class: 'subtitulo', text: 'Diagnósticos' }), dx.nodo),
      h('div', null, h('div', { class: 'subtitulo', text: 'Tratamientos' }), tx.nodo),
      h('div', null, h('div', { class: 'subtitulo', text: 'Recetas' }), rx.nodo),
    ],
    validar: () => [dx.validar(), tx.validar(), rx.validar()].every(Boolean),
    leer: () => ({ diagnosticos: dx.leer(), tratamientos: tx.leer(), recetas: rx.leer() }),
  };
}

function contador(control, maximo) {
  const nodo = h('span', { class: 'hint', text: `0 de ${maximo}` });
  control.addEventListener('input', () => { nodo.textContent = `${control.value.length} de ${maximo}`; });
  return nodo;
}

/* ---------- Consulta y adenda ---------- */
export function abrirConsulta(p, alGuardar) {
  const motivo = entrada('consulta-motivo', { maxlength: 500, placeholder: '¿Por qué consulta?' });
  const notas = areaTexto('consulta-notas', { maxlength: 5000, rows: 4, placeholder: 'Notas clínicas' });
  const campos = { motivo: campo('Motivo de consulta', motivo), notas: campo('Notas', notas, { opcional: true }) };
  const bloques = bloquesClinicos();
  const zona = h('div');
  const acciones = pie(() => panel.cerrar(), 'Guardar consulta');
  const panel = lateral('Nueva consulta', [
    h('p', { class: 'muted', text: `Paciente: ${nombreDe(p)}. Consulta, diagnósticos, tratamientos y recetas se guardan juntos.` }),
    campos.motivo, campos.notas, contador(notas, 5000), ...bloques.nodos, zona,
  ], acciones.nodos);
  acciones.boton.addEventListener('click', () => {
    if (!obligatorio(campos.motivo, motivo, 'El motivo es obligatorio.')) { motivo.focus(); return; }
    if (!bloques.validar()) return;
    enviar(acciones.boton, zona, campos, async () => {
      await api(`${ruta(p)}/consultas`, { metodo: 'POST', cuerpo: { motivo: motivo.value.trim(), notas: limpio(notas), ...bloques.leer() } });
      panel.cerrar();
      aviso_flotante('Consulta guardada');
      alGuardar();
    });
  });
}

export function abrirAdenda(c, p, alGuardar) {
  const nota = areaTexto('adenda-nota', { maxlength: 2000, rows: 4, placeholder: 'Nota de la adenda' });
  const campos = { nota: campo('Nota', nota, { opcional: true }) };
  const bloques = bloquesClinicos();
  const zona = h('div');
  const acciones = pie(() => panel.cerrar(), 'Guardar adenda');
  const panel = lateral('Agregar adenda', [
    h('p', { class: 'muted', text: `A la consulta «${c.motivo}» del ${fFecha(c.fecha_hora)}. La consulta original no se modifica; la adenda queda firmada con tu usuario.` }),
    campos.nota, contador(nota, 2000), ...bloques.nodos, zona,
  ], acciones.nodos);
  acciones.boton.addEventListener('click', () => {
    if (!bloques.validar()) return;
    const elementos = bloques.leer();
    if (!limpio(nota) && !elementos.diagnosticos.length && !elementos.tratamientos.length && !elementos.recetas.length) {
      zona.replaceChildren(aviso('crit', 'circle-alert', h('b', { text: 'Escribe una nota o agrega al menos un elemento.' })));
      return;
    }
    enviar(acciones.boton, zona, campos, async () => {
      await api(`${ruta(p)}/consultas/${encodeURIComponent(c.id_consulta)}/adenda`, { metodo: 'POST', cuerpo: { nota: limpio(nota), ...elementos } });
      panel.cerrar();
      aviso_flotante('Adenda guardada');
      alGuardar();
    });
  });
}

/* ---------- Alergias ---------- */
export function abrirAlergias(p, alGuardar) {
  const lista = repetible('Agregar otra alergia', filaAlergia, { minimo: 1 });
  const zona = h('div');
  const acciones = pie(() => panel.cerrar(), 'Guardar alergias');
  const panel = lateral('Agregar alergias', [
    h('p', { class: 'muted', text: 'Se suman a las ya registradas. No se borra ni se edita ninguna.' }), lista.nodo, zona,
  ], acciones.nodos);
  acciones.boton.addEventListener('click', () => {
    if (!lista.validar()) return;
    const alergias = lista.leer();
    if (!alergias.length) {
      zona.replaceChildren(aviso('crit', 'circle-alert', h('b', { text: 'Escribe al menos una sustancia.' })));
      return;
    }
    enviar(acciones.boton, zona, {}, async () => {
      await api(`${ruta(p)}/alergias`, { metodo: 'POST', cuerpo: { alergias } });
      panel.cerrar();
      aviso_flotante('Alergias guardadas');
      alGuardar();
    });
  });
}

/* ---------- Datos del paciente ---------- */
export function abrirEditar(p, alGuardar) {
  const c = p.contacto || {};
  const hoy = hoyLocal();
  const nombres = entrada('editar-nombres', { maxlength: 120, value: p.nombres });
  const apellidos = entrada('editar-apellidos', { maxlength: 120, value: p.apellidos });
  const nacimiento = entrada('editar-nacimiento', { type: 'date', value: p.fecha_nacimiento || '', max: hoy });
  const telefono = entrada('editar-telefono', { maxlength: 30, value: c.telefono || '' });
  const correo = entrada('editar-correo', { type: 'email', maxlength: 254, value: c.correo || '' });
  const direccion = entrada('editar-direccion', { maxlength: 300, value: c.direccion || '' });
  const campos = {
    nombres: campo('Nombres', nombres), apellidos: campo('Apellidos', apellidos),
    fecha_nacimiento: campo('Fecha de nacimiento', nacimiento, { opcional: true }),
    telefono: campo('Teléfono', telefono, { opcional: true }),
    correo: campo('Correo', correo, { opcional: true }), direccion: campo('Dirección', direccion, { opcional: true }),
  };
  const zona = h('div');
  const acciones = pie(() => panel.cerrar(), 'Guardar cambios');
  const panel = lateral('Editar datos del paciente', [
    aviso('info', 'info', 'Los campos de contacto reemplazan el contacto completo al guardar.'),
    h('div', { class: 'dos' }, campos.nombres, campos.apellidos), campos.fecha_nacimiento, campos.telefono, campos.correo, campos.direccion, zona,
  ], acciones.nodos);
  acciones.boton.addEventListener('click', () => {
    const ok = [obligatorio(campos.nombres, nombres, 'Escribe los nombres.'), obligatorio(campos.apellidos, apellidos, 'Escribe los apellidos.')].every(Boolean);
    if (!ok) return;
    const cuerpo = {
      nombres: nombres.value.trim(),
      apellidos: apellidos.value.trim(),
      contacto: { telefono: limpio(telefono), correo: limpio(correo), direccion: limpio(direccion) },
    };
    if (nacimiento.value) cuerpo.fecha_nacimiento = nacimiento.value;
    enviar(acciones.boton, zona, campos, async () => {
      await api(ruta(p), { metodo: 'PATCH', cuerpo });
      panel.cerrar();
      aviso_flotante('Datos actualizados');
      alGuardar();
    });
  });
}

/* ---------- Archivo ---------- */
export function abrirArchivar(p, alGuardar) {
  const motivo = seleccion('archivo-motivo', [
    { valor: 'traslado', texto: 'Traslado a otra institución' },
    { valor: 'fallecimiento', texto: 'Fallecimiento' },
    { valor: 'administrativo', texto: 'Causa administrativa' },
  ]);
  const detalle = areaTexto('archivo-detalle', { maxlength: 500 });
  const campos = { motivo: campo('Motivo', motivo), detalle: campo('Detalle', detalle, { opcional: true }) };
  const zona = h('div');
  const boton = h('button', { class: 'btn peligro solido', type: 'button' }, ic('archive', 16), 'Archivar historial');
  const ventana = modal('Archivar historial', h('div', { class: 'pila-s' },
    aviso('aviso', 'triangle-alert', 'No se borra información clínica. El historial deja de admitir consultas y citas nuevas.'),
    campos.motivo, campos.detalle, zona), [
    h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => ventana.cerrar() }), boton,
  ]);
  boton.addEventListener('click', () => enviar(boton, zona, campos, async () => {
    await api(`${ruta(p)}/archivo`, { metodo: 'POST', cuerpo: { motivo: motivo.value, detalle: limpio(detalle) } });
    ventana.cerrar();
    aviso_flotante('Historial archivado', 'archive');
    alGuardar();
  }));
}
