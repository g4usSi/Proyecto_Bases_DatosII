/* Ficha del paciente en el Hospital General: pulsera con grupo sanguineo, ingreso en curso y atenciones. */
import { api } from '../../api.js';
import { sesion } from '../../sesion.js';
import { enlace, irA } from '../../enrutador.js';
import { fEdad, fFechaCivil, fFechaCorta, fFechaHora, fHora, nombreDe } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import { aviso, aviso_flotante, campo, cargando, chip, estadoDeError, modal, seleccion, vacio } from '../../ui/componentes.js';
import { cargarProfesionales, enviar } from '../clinica/comun.js';
import { abrirArchivar, abrirConsulta, abrirEditar } from '../clinica/formularios.js';
import { abrirCita } from '../clinica/agendar.js';
import { lectura, pestanaCitas, pestanaHistorial, pestanaResumen, proximaCita } from '../clinica/ficha.js';
import { ORIGENES } from '../compartido/pacientes.js';
import { accionesFicha, indicadorFicha, resumenFicha } from '../compartido/ficha.js';
import { chipDe, duracion, GRUPOS_SANGUINEOS, pulsera, rutaPaciente, TIPOS_INGRESO } from './comun.js';
import { abrirIngreso, abrirNuevoIngreso } from './ingreso.js';
import { abrirAtencion, chipAtencion } from './atenciones.js';

const POR_PAGINA = 10;
const iniciales = (p) => `${p.nombres[0] || ''}${p.apellidos[0] || ''}`.toUpperCase();

function abrirGrupo(p, alGuardar) {
  const grupo = seleccion('grupo-sanguineo', [{ valor: '', texto: 'Sin dato' }, ...GRUPOS_SANGUINEOS.map((g) => ({ valor: g, texto: g }))], { value: p.grupo_sanguineo || '' });
  const campos = { grupo_sanguineo: campo('Grupo sanguíneo', grupo, { ayuda: 'Confírmalo con un examen antes de registrarlo.' }) };
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'button', text: 'Guardar' });
  const ventana = modal('Grupo sanguíneo', h('div', { class: 'pila-s' }, h('p', { class: 'muted', text: nombreDe(p) }), campos.grupo_sanguineo, zona),
    [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => ventana.cerrar() }), boton]);
  boton.addEventListener('click', () => enviar(boton, zona, campos, async () => {
    await api(`${rutaPaciente(p.id_paciente)}/grupo-sanguineo`, { metodo: 'PUT', cuerpo: { grupo_sanguineo: grupo.value || null } });
    ventana.cerrar();
    aviso_flotante('Grupo sanguíneo guardado');
    alGuardar();
  }));
}

function indicadores(p, datos, ingreso) {
  const clinico = sesion.tiene('historiales:leer');
  const mosaico = indicadorFicha;
  const lista = [mosaico(p.archivado ? '' : 'ok', p.archivado ? 'archive' : 'circle-check', 'Estado', p.archivado ? 'Archivado' : 'Activo')];
  if (p.fecha_nacimiento) lista.push(mosaico('', 'cake', 'Edad', fEdad(p.fecha_nacimiento)));
  if (clinico && datos.historial?.valor) {
    const ultima = datos.historial.valor.consultas[0];
    lista.push(mosaico('', 'history', 'Última consulta', ultima ? fFechaCorta(ultima.fecha_hora) : 'Sin consultas'));
  }
  if (datos.citas?.valor) {
    const proxima = proximaCita(datos.citas.valor);
    lista.push(mosaico('', 'calendar-days', 'Próxima cita', proxima ? `${fFechaCorta(proxima.inicio)}, ${fHora(proxima.inicio)}` : 'Sin cita programada'));
  }
  if (clinico && p.alergias?.length) {
    lista.push(mosaico('aviso', 'triangle-alert', 'Alergias', p.alergias.length === 1 ? '1 registrada' : `${p.alergias.length} registradas`));
  }
  if (ingreso) {
    const emergencia = ingreso.tipo === 'emergencia';
    lista.push(mosaico(emergencia ? 'crit' : 'info', emergencia ? 'siren' : 'bed-double',
      emergencia ? 'En emergencia' : 'Hospitalizado', `Cama ${ingreso.cama} · ${duracion(ingreso.ingreso_en)}`));
  }
  return lista;
}

function pestanaAtenciones(p, ctx) {
  const { valor, error } = ctx.datos.atenciones;
  if (error) return estadoDeError(error, ctx.repintar);
  if (!valor.length) return vacio('activity', 'Sin atenciones', 'Este paciente no tiene consultas ni ingresos registrados en el hospital.');
  return h('div', { class: 'pila-s' }, valor.map((a) => h('article', { class: 'consulta' },
    h('header', null, h('div', { class: 'fila' }, chipAtencion(a.tipo), a.tipo_ingreso && chipDe(TIPOS_INGRESO, a.tipo_ingreso), h('b', { class: 'num', text: `#${a.id_atencion}` })),
      h('span', { class: 'hint', text: `${fFechaHora(a.fecha_hora)} · ${a.nombre_profesional}` })),
    h('p', { text: a.motivo }),
    h('div', { class: 'fila' },
      a.cama && chip('', 'bed-double', `Cama ${a.cama}`),
      a.tipo === 'INGRESO' && (a.alta_en ? chip('ok', 'door-open', `Alta ${fFechaCorta(a.alta_en)}`) : chip('aviso', 'clock', 'Internado')),
      h('button', { class: 'btn sec sm', type: 'button', onclick: () => abrirAtencion(a.id_paciente, a.id_atencion, { alCambiar: ctx.repintar }) }, ic('activity', 14), 'Ver recorrido')))));
}

function pestanasDe() {
  const lista = [['resumen', 'user-round', 'Resumen']];
  if (sesion.tiene('historiales:leer')) lista.push(['historial', 'notebook-text', 'Historial']);
  if (sesion.tiene('citas:leer')) lista.push(['citas', 'calendar-days', 'Citas']);
  if (sesion.tiene('historiales:leer')) lista.push(['atenciones', 'activity', 'Atenciones']);
  return lista;
}

function acciones(p, ingreso, ctx) {
  const lista = [];
  const registraConsultas = sesion.tiene('consultas:registrar');
  if (!p.archivado && registraConsultas) lista.push(h('button', { class: 'btn', type: 'button', onclick: () => abrirConsulta(p, ctx.alGuardarConsulta) }, ic('file-plus', 16), 'Nueva consulta'));
  if (ingreso) lista.push(h('button', { class: 'btn sec', type: 'button', onclick: () => abrirIngreso(ingreso, { alCambiar: ctx.repintar }) }, ic('bed-double', 16), 'Ver ingreso'));
  if (p.archivado) return lista;
  if (registraConsultas) {
    if (!ingreso) {
      lista.push(h('button', { class: 'btn sec', type: 'button', onclick: () => abrirNuevoIngreso({ paciente: p, tipo: 'programado', alGuardar: ctx.repintar }) }, ic('bed-double', 16), 'Ingresar'));
    }
    if (sesion.tiene('historiales:leer')) lista.push(h('button', { class: 'btn sec', type: 'button', onclick: () => abrirGrupo(p, ctx.repintar) }, ic('droplet', 16), 'Editar grupo sanguíneo'));
  }
  if (sesion.tiene('citas:gestionar')) lista.push(h('button', { class: 'btn sec', type: 'button', onclick: () => abrirCita({ paciente: p, profesionales: ctx.profesionales, alGuardar: ctx.repintar }) }, ic('calendar-plus', 16), 'Agendar cita'));
  if (sesion.tiene('pacientes:registrar')) lista.push(h('button', { class: 'btn sec', type: 'button', onclick: () => abrirEditar(p, ctx.repintar) }, ic('pencil', 16), 'Editar datos'));
  if (sesion.tiene('historiales:archivar')) lista.push(h('button', { class: 'btn peligro', type: 'button', onclick: () => abrirArchivar(p, ctx.repintar) }, ic('archive', 16), 'Archivar historial'));
  return lista;
}

export async function pintarFicha(zona, { idPaciente, pestana, q, origen, repintar }) {
  zona.replaceChildren(cargando(6));
  const base = rutaPaciente(idPaciente);
  const pestanas = pestanasDe();
  const actual = pestanas.some(([k]) => k === pestana) ? pestana : 'resumen';
  const clinico = sesion.tiene('historiales:leer');

  let paciente;
  let datos;
  let profesionales;
  try {
    [paciente, datos, profesionales] = await Promise.all([
      api(base),
      (async () => {
        const [historial, citas, ingresos, atenciones] = await Promise.all([
          clinico ? lectura(api(`${base}/historial`, { params: { limite: actual === 'historial' ? POR_PAGINA : 1 } })) : null,
          sesion.tiene('citas:leer') ? lectura(api(`${base}/citas`)) : null,
          clinico ? lectura(api(`${base}/ingresos`, { params: { limite: 10 } })) : null,
          clinico && actual === 'atenciones' ? lectura(api(`${base}/atenciones`, { params: { limite: 50 } })) : null,
        ]);
        return { historial, citas, ingresos, atenciones };
      })(),
      cargarProfesionales(),
    ]);
  } catch (error) {
    zona.replaceChildren(error.estado === 404
      ? vacio('inbox', 'Paciente no encontrado', 'No existe en tu institución o ya no está disponible.')
      : estadoDeError(error, repintar));
    return;
  }

  const ruta = (k) => `pacientes/${encodeURIComponent(idPaciente)}${k === 'resumen' ? '' : `/${k}`}`;
  const ctx = {
    datos,
    profesionales,
    repintar,
    alGuardarConsulta: () => (actual === 'historial' ? repintar() : irA(ruta('historial'), { q })),
  };
  const contenido = { resumen: pestanaResumen, historial: pestanaHistorial, citas: pestanaCitas, atenciones: pestanaAtenciones }[actual];
  const ingreso = datos.ingresos?.valor?.find((i) => i.abierto);

  zona.replaceChildren(...[
    paciente.archivado && aviso('', 'archive', h('b', { text: 'Este historial está archivado. ' }), 'No admite consultas, citas ni cambios nuevos. La información clínica sigue disponible para consulta.'),
    h('section', { class: 'papel ficha-cab pulsera-hospital', 'aria-label': 'Paciente' },
      ORIGENES[origen] && h('a', { class: 'enlace', href: enlace(origen), text: `← Volver a ${ORIGENES[origen]}` }),
      h('div', { class: 'ficha-titulo' },
        h('div', { class: 'ficha-nombre' }, h('span', { class: 'avatar', 'aria-hidden': 'true', text: iniciales(paciente) }),
          h('div', null, h('h2', { text: nombreDe(paciente) }),
            h('p', { class: 'hint' }, paciente.fecha_nacimiento ? `Nació el ${fFechaCivil(paciente.fecha_nacimiento)} · ` : '', 'ID ', h('span', { class: 'num', text: paciente.id_paciente })))),
        clinico && pulsera(paciente.grupo_sanguineo)),
      resumenFicha(indicadores(paciente, datos, ingreso)), accionesFicha(acciones(paciente, ingreso, ctx))),
    h('div', { class: 'pestanas', role: 'tablist', 'aria-label': 'Secciones de la ficha' }, pestanas.map(([k, icono, texto]) => h('button', {
      type: 'button', role: 'tab', 'aria-selected': k === actual ? 'true' : 'false', onclick: () => irA(ruta(k), { q, origen }),
    }, ic(icono, 16), texto))),
    h('div', { role: 'tabpanel' }, contenido(paciente, ctx)),
  ].filter(Boolean));
}
