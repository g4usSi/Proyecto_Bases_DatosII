/* Agenda semanal: los resumenes se calculan en el cliente a partir de GET /citas. */
import { api } from '../../api.js';
import { sesion } from '../../sesion.js';
import { enlace, irA } from '../../enrutador.js';
import { diaDe, fDia, fFechaCivil, fHora, finDeDia, hoyLocal, inicioDeDia, lunesDe, sumarDias } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import { cabeza, cargando, chip, cifras, estadoDeError, vacio } from '../../ui/componentes.js';
import { cargarProfesionales, chipCita, claseCita, estaPorAtender, nombreProfesional } from './comun.js';
import { abrirCita, botonEstado } from './agendar.js';

const conMayuscula = (texto) => texto.charAt(0).toUpperCase() + texto.slice(1);
const horas = (cita) => (new Date(cita.fin) - new Date(cita.inicio)) / 3600000;

function resumen(citas, profesionales, hoy) {
  const porProfesional = new Map();
  for (const c of citas) {
    const p = porProfesional.get(c.id_profesional) || { id: c.id_profesional, n: 0, horas: 0 };
    p.n += 1;
    p.horas += horas(c);
    porProfesional.set(c.id_profesional, p);
  }
  const filas = [...porProfesional.values()].sort((a, b) => b.horas - a.horas);
  const mayor = Math.max(...filas.map((f) => f.horas), 0.01);
  return [
    cifras([
      { etiqueta: 'Citas en la semana', valor: citas.length },
      { etiqueta: 'Hoy', valor: citas.filter((c) => diaDe(c.inicio) === hoy).length },
      { etiqueta: 'Por atender', valor: citas.filter(estaPorAtender).length, nota: 'Programadas o confirmadas' },
      { etiqueta: 'Canceladas o inasistencias', valor: citas.filter((c) => c.estado === 'cancelada' || c.estado === 'no_asistio').length },
    ]),
    h('section', { class: 'papel' },
      h('div', { class: 'papel-cab' }, h('h3', { text: 'Carga por profesional' }), h('span', { class: 'hint', text: 'Horas agendadas en la semana' })),
      h('div', { class: 'cargas' }, filas.map((f) => h('div', { class: 'carga' },
        h('span', { text: nombreProfesional(profesionales, f.id) }),
        h('div', { class: 'medida', role: 'img', 'aria-label': `${f.horas.toFixed(1)} horas` }, h('i', { estilo: { width: `${(f.horas / mayor) * 100}%` } })),
        h('span', { class: 'hint cifra-tabular', text: `${f.n} ${f.n === 1 ? 'cita' : 'citas'} · ${f.horas.toFixed(1)} h` }))))),
  ];
}

function filaCita(c, profesionales, repintar) {
  const pestana = sesion.tiene('citas:leer') ? '/citas' : '';
  return h('div', { class: `fila-cita con-accion ${claseCita(c.estado)}` },
    h('time', null, fHora(c.inicio), h('small', { text: `a ${fHora(c.fin)}` })),
    h('div', { class: 'cita-datos' },
      h('a', { class: 'enlace', href: enlace(`pacientes/${encodeURIComponent(c.id_paciente)}${pestana}`, { origen: 'agenda' }), text: c.nombre_paciente }),
      h('small', { text: c.motivo }),
      c.motivo_cambio && h('small', { text: `Motivo del cambio: ${c.motivo_cambio}` })),
    h('div', { class: 'fila' }, h('span', { class: 'hint', text: nombreProfesional(profesionales, c.id_profesional) }), chipCita(c.estado)),
    botonEstado(c, repintar));
}

export async function vistaAgenda({ contenedor, params, repintar }) {
  const semana = Number.parseInt(params.semana, 10) || 0;
  const solo = params.solo === '1';
  const hoy = hoyLocal();
  const lunes = sumarDias(lunesDe(hoy), semana * 7);
  const domingo = sumarDias(lunes, 6);
  const ir = (cambios) => irA('agenda', { semana: semana || null, solo: solo ? '1' : null, ...cambios });
  const zona = h('div', { class: 'pila', 'aria-live': 'polite' }, cargando(5));
  const acciones = h('div', { class: 'fila' });

  contenedor.append(
    cabeza('Agenda de citas', `${fFechaCivil(lunes)} a ${fFechaCivil(domingo)}`, acciones),
    zona);

  acciones.append(
    h('button', { class: 'ibtn', type: 'button', 'aria-label': 'Semana anterior', onclick: () => ir({ semana: semana - 1 || null }) }, ic('chevron-left', 18)),
    h('button', { class: 'btn sec sm', type: 'button', disabled: semana === 0, text: 'Esta semana', onclick: () => ir({ semana: null }) }),
    h('button', { class: 'ibtn', type: 'button', 'aria-label': 'Semana siguiente', onclick: () => ir({ semana: semana + 1 || null }) }, ic('chevron-right', 18)));

  let citas;
  let profesionales;
  try {
    [citas, profesionales] = await Promise.all([
      api('/citas', { params: { desde: inicioDeDia(lunes), hasta: finDeDia(domingo), id_profesional: solo ? sesion.usuario.id_usuario : null } }),
      cargarProfesionales(),
    ]);
  } catch (error) {
    zona.replaceChildren(estadoDeError(error, repintar));
    return;
  }

  if (sesion.tiene('citas:gestionar')) {
    acciones.append(h('button', {
      class: 'btn', type: 'button',
      onclick: () => abrirCita({ profesionales, alGuardar: repintar }),
    }, ic('calendar-plus', 16), 'Agendar cita'));
  }
  const atiende = profesionales.some((p) => p.id_profesional === sesion.usuario.id_usuario);
  const filtro = atiende && h('label', { class: 'casilla' },
    h('input', { type: 'checkbox', checked: solo, onchange: (e) => ir({ solo: e.target.checked ? '1' : null }) }),
    h('span', { text: 'Solo mis citas' }));

  if (!citas.length) {
    zona.replaceChildren(...[filtro, vacio('calendar-days', 'No hay citas en estas fechas',
      solo ? 'No tienes citas esta semana. Desactiva «Solo mis citas» para ver las de todos.' : 'Cuando se agenden citas aparecerán aquí.')].filter(Boolean));
    return;
  }
  const ordenadas = [...citas].sort((a, b) => a.inicio.localeCompare(b.inicio));
  const dias = [...new Set(ordenadas.map((c) => diaDe(c.inicio)))];
  zona.replaceChildren(...[filtro, ...resumen(ordenadas, profesionales, hoy),
    ...dias.map((dia) => {
      const delDia = ordenadas.filter((c) => diaDe(c.inicio) === dia);
      return h('section', { class: 'pila-s' },
        h('h3', { class: 'titulo-dia' }, conMayuscula(fDia(delDia[0].inicio)), dia === hoy && chip('info', null, 'Hoy'),
          h('small', { text: delDia.length === 1 ? '1 cita' : `${delDia.length} citas` })),
        delDia.map((c) => filaCita(c, profesionales, repintar)));
    })].filter(Boolean));
}
