/* Agendar una cita y cambiar su estado: se usan desde la agenda y desde la ficha. */
import { api } from '../../api.js';
import { indicadorFicha, resumenFicha } from '../compartido/ficha.js';
import { sesion } from '../../sesion.js';
import { conZona, fFechaHora, nombreDe } from '../../formato.js';
import { h } from '../../ui/dom.js';
import { aviso, aviso_flotante, campo, entrada, lateral, modal, seleccion } from '../../ui/componentes.js';
import { areaTexto, enviar, estaPorAtender } from './comun.js';

/* Manana a las 09:00 hora de Guatemala: nunca cae en el pasado, que la API rechaza. */
function inicioSugerido() {
  const manana = new Date(Date.now() + 86400000);
  const dia = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Guatemala' }).format(manana);
  return `${dia}T09:00`;
}

export function selectorDePaciente({ incluirArchivados = false, alElegir } = {}) {
  let elegido = null;
  let turno = 0;
  const resultados = h('div', { class: 'pila-s' });
  const caja = entrada('cita-buscar', {
    type: 'search', placeholder: 'Nombre o apellido',
    oninput: async () => {
      const q = caja.value.trim();
      const mio = ++turno;
      elegido = null;
      if (q.length < 2) { resultados.replaceChildren(); return; }
      try {
        const lista = await api('/pacientes', { params: { nombre: q, limite: 5 } });
        if (mio !== turno) return;
        const activos = incluirArchivados ? lista : lista.filter((p) => !p.archivado);
        resultados.replaceChildren(...(activos.length
          ? activos.map((p) => h('button', {
            class: 'item-paciente', type: 'button',
            onclick: () => {
              elegido = p;
              resultados.replaceChildren(aviso('info', 'user-round', h('b', { text: nombreDe(p) })));
              alElegir?.(p);
            },
          }, h('b', { text: nombreDe(p) })))
          : [h('p', { class: 'hint', text: incluirArchivados ? 'Sin pacientes con ese nombre.' : 'Sin pacientes activos con ese nombre.' })]));
      } catch (error) {
        if (mio === turno) resultados.replaceChildren(aviso('crit', 'circle-alert', h('b', { text: error.message })));
      }
    },
  });
  const nodoCampo = campo('Paciente', caja);
  return { nodo: h('div', { class: 'pila-s' }, nodoCampo, resultados), campo: nodoCampo, valor: () => elegido };
}

export function abrirCita({ paciente, profesionales, alGuardar }) {
  const yo = sesion.usuario.id_usuario;
  const selector = paciente ? null : selectorDePaciente();
  const profesional = seleccion('cita-profesional', profesionales.map((p) => ({
    valor: p.id_profesional, texto: `${p.nombres} ${p.apellidos}`.trim() + (p.id_profesional === yo ? ' (tú)' : ''),
  })), { value: profesionales.some((p) => p.id_profesional === yo) ? yo : null });
  const inicio = entrada('cita-inicio', { type: 'datetime-local', value: inicioSugerido() });
  const duracion = entrada('cita-duracion', { type: 'number', min: 5, max: 480, step: 5, value: '30' });
  const motivo = entrada('cita-motivo', { maxlength: 300, placeholder: 'Motivo de la cita' });
  const campos = {
    id_profesional: campo('Profesional', profesional),
    inicio: campo('Inicio', inicio, { ayuda: 'Hora de Guatemala (UTC−06:00)' }),
    duracion_minutos: campo('Duración (minutos)', duracion, { ayuda: 'Entre 5 y 480.' }),
    motivo: campo('Motivo', motivo),
  };
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'button', text: 'Agendar cita', disabled: !profesionales.length });
  const panel = lateral('Agendar cita', [
    paciente ? aviso('info', 'user-round', h('b', { text: nombreDe(paciente) })) : selector.nodo,
    !profesionales.length && aviso('aviso', 'triangle-alert', 'No hay profesionales activos que atiendan pacientes.'),
    campos.id_profesional,
    h('div', { class: 'dos' }, campos.inicio, campos.duracion_minutos),
    campos.motivo, zona,
  ], [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => panel.cerrar() }), boton]);

  boton.addEventListener('click', () => {
    const elegido = paciente || selector.valor();
    selector?.campo.marcar(elegido ? null : 'Elige un paciente de la lista.');
    campos.motivo.marcar(motivo.value.trim() ? null : 'Escribe el motivo de la cita.');
    campos.inicio.marcar(inicio.value ? null : 'Elige la fecha y la hora.');
    if (!elegido || !motivo.value.trim() || !inicio.value) return;
    enviar(boton, zona, campos, async () => {
      await api('/citas', {
        metodo: 'POST',
        cuerpo: {
          id_paciente: elegido.id_paciente,
          id_profesional: profesional.value,
          inicio: conZona(inicio.value),
          duracion_minutos: Number(duracion.value),
          motivo: motivo.value.trim(),
        },
      });
      panel.cerrar();
      aviso_flotante('Cita agendada');
      alGuardar();
    });
  });
}

export function abrirEstadoCita(cita, alGuardar) {
  const opciones = [
    cita.estado === 'programada' && ['confirmada', 'Confirmada'],
    ['atendida', 'Atendida'],
    ['no_asistio', 'No asistió'],
    ['cancelada', 'Cancelada'],
  ].filter(Boolean);
  let elegido = opciones[0][0];
  const motivo = areaTexto('estado-motivo', { maxlength: 300, rows: 2 });
  const cMotivo = campo('Motivo de la cancelación', motivo);
  cMotivo.hidden = true;
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'button', text: 'Guardar' });
  const ventana = modal('Actualizar estado de la cita', h('div', { class: 'pila-s' },
    resumenFicha([
      indicadorFicha('', 'user-round', 'Paciente', cita.nombre_paciente),
      indicadorFicha('', 'calendar-days', 'Inicio', fFechaHora(cita.inicio)),
    ], 'Datos de la cita'),
    h('fieldset', { class: 'pila-s' }, h('legend', { class: 'ficha-etiqueta', text: 'Nuevo estado' }),
      opciones.map(([valor, texto]) => h('label', { class: 'casilla' },
        h('input', {
          type: 'radio', name: 'estado-cita', value: valor, checked: valor === elegido,
          onchange: () => {
            elegido = valor;
            cMotivo.hidden = valor !== 'cancelada';
          },
        }),
        h('span', { text: texto })))),
    cMotivo,
    aviso('', 'info', 'Los estados finales ya no cambian.'), zona), [
    h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => ventana.cerrar() }), boton,
  ]);
  boton.addEventListener('click', () => {
    if (elegido === 'cancelada' && !motivo.value.trim()) {
      cMotivo.marcar('Escribe el motivo de la cancelación.');
      return;
    }
    enviar(boton, zona, { motivo: cMotivo }, async () => {
      await api(`/citas/${encodeURIComponent(cita.id_cita)}/estado`, {
        metodo: 'POST',
        cuerpo: { estado: elegido, motivo: elegido === 'cancelada' ? motivo.value.trim() : null },
      });
      ventana.cerrar();
      aviso_flotante('Estado actualizado');
      alGuardar();
    });
  });
}

export const botonEstado = (cita, alGuardar) => (sesion.tiene('citas:gestionar') && estaPorAtender(cita)
  ? h('button', { class: 'btn sec sm', type: 'button', text: 'Actualizar estado', onclick: () => abrirEstadoCita(cita, alGuardar) })
  : h('span'));
