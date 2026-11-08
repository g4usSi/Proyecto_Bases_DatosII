/* Ficha del paciente en el Laboratorio Clinico: datos, historial, citas y ordenes con resultados.
   El laboratorista ve ordenes y resultados aunque no tenga acceso al historial clinico. */
import { api } from '../../api.js';
import { sesion } from '../../sesion.js';
import { enlace, irA } from '../../enrutador.js';
import { fEdad, fFechaCivil, fFechaCorta, fFechaHora, fHora, nombreDe } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import { aviso, cargando, estadoDeError, vacio } from '../../ui/componentes.js';
import { cargarProfesionales, nombreProfesional } from '../clinica/comun.js';
import { abrirArchivar, abrirConsulta, abrirEditar } from '../clinica/formularios.js';
import { abrirCita } from '../clinica/agendar.js';
import { lectura, pestanaCitas, pestanaHistorial, pestanaResumen, proximaCita } from '../clinica/ficha.js';
import { ORIGENES } from '../compartido/pacientes.js';
import { accionesFicha, indicadorFicha, resumenFicha } from '../compartido/ficha.js';
import { chipLectura, chipOrden, estaAbierta, textoValor } from './comun.js';
import { abrirNuevaOrden, abrirOrden } from './orden.js';

const POR_PAGINA = 10;
const iniciales = (p) => `${p.nombres[0] || ''}${p.apellidos[0] || ''}`.toUpperCase();
const veOrdenes = () => sesion.tiene('historiales:leer') || sesion.tiene('laboratorio:resultados');
const fuera = (orden) => orden.pruebas.flatMap((p) => p.resultados).filter((r) => r.interpretacion && r.interpretacion !== 'normal');

function indicadores(p, datos) {
  const mosaico = indicadorFicha;
  const lista = [mosaico(p.archivado ? '' : 'ok', p.archivado ? 'archive' : 'circle-check', 'Estado', p.archivado ? 'Archivado' : 'Activo')];
  if (p.fecha_nacimiento) lista.push(mosaico('', 'cake', 'Edad', fEdad(p.fecha_nacimiento)));
  if (datos.ordenes?.valor) {
    const abiertas = datos.ordenes.valor.filter(estaAbierta).length;
    lista.push(mosaico(abiertas ? 'aviso' : '', 'flask-conical', 'Órdenes abiertas', abiertas ? String(abiertas) : 'Ninguna'));
    const ultima = datos.ordenes.valor.find((o) => o.estado === 'validada');
    if (ultima) {
      const n = fuera(ultima).length;
      lista.push(mosaico(n ? 'crit' : 'ok', n ? 'triangle-alert' : 'badge-check', 'Último resultado',
        `${fFechaCorta(ultima.validada_en)} · ${n ? `${n} fuera de rango` : 'en rango'}`));
    }
  }
  if (datos.citas?.valor) {
    const proxima = proximaCita(datos.citas.valor);
    lista.push(mosaico('', 'calendar-days', 'Próxima cita', proxima ? `${fFechaCorta(proxima.inicio)}, ${fHora(proxima.inicio)}` : 'Sin cita programada'));
  }
  if (sesion.tiene('historiales:leer') && p.alergias?.length) {
    lista.push(mosaico('aviso', 'triangle-alert', 'Alergias', p.alergias.length === 1 ? '1 registrada' : `${p.alergias.length} registradas`));
  }
  return lista;
}

function tarjetaOrden(o, p, ctx) {
  const abrir = () => abrirOrden(o.id_paciente, o.id_orden, { alCambiar: ctx.repintar });
  const conResultados = o.pruebas.filter((x) => x.resultados.length).length;
  const destacados = fuera(o);
  return h('article', { class: 'consulta' },
    h('header', null,
      h('div', { class: 'fila' }, chipOrden(o.estado), h('b', { class: 'num', text: o.numero_orden })),
      h('span', { class: 'hint', text: `${fFechaHora(o.solicitada_en)} · ${nombreProfesional(ctx.profesionales, o.id_profesional)}` })),
    h('div', { class: 'etiquetas' }, o.pruebas.map((x) => h('span', { class: `chip ${x.resultados.length ? 'ok' : ''}`, text: x.nombre }))),
    destacados.length > 0 && h('ul', { class: 'lista-simple' }, destacados.slice(0, 4).map((r) => h('li', null,
      chipLectura(r.interpretacion), ' ', h('b', { text: r.nombre }), h('span', { class: 'hint', text: ` ${textoValor(r)}` })))),
    o.motivo_cancelacion && h('p', { class: 'hint', text: `Cancelada: ${o.motivo_cancelacion}` }),
    h('div', { class: 'fila' },
      h('span', { class: 'hint', text: `${conResultados} de ${o.pruebas.length} pruebas con resultados · ${o.muestras.length === 1 ? '1 muestra' : `${o.muestras.length} muestras`}` }),
      h('button', { class: 'btn sec sm', type: 'button', onclick: abrir }, ic('flask-conical', 14), 'Ver orden')));
}

function pestanaOrdenes(p, ctx) {
  const { valor, error } = ctx.datos.ordenes;
  if (error) return estadoDeError(error, ctx.repintar);
  const nueva = sesion.tiene('consultas:registrar') && !p.archivado && ctx.nuevaOrden;
  if (!valor.length) {
    return vacio('flask-conical', 'Sin órdenes', 'Las órdenes de laboratorio del paciente aparecerán aquí.',
      nueva && h('button', { class: 'btn', type: 'button', onclick: ctx.nuevaOrden }, ic('plus', 16), 'Solicitar la primera orden'));
  }
  return h('div', { class: 'pila-s' }, valor.map((o) => tarjetaOrden(o, p, ctx)));
}

function pestanasDe() {
  const lista = [['resumen', 'user-round', 'Resumen']];
  if (veOrdenes()) lista.push(['ordenes', 'flask-conical', 'Órdenes']);
  if (sesion.tiene('historiales:leer')) lista.push(['historial', 'notebook-text', 'Historial']);
  if (sesion.tiene('citas:leer')) lista.push(['citas', 'calendar-days', 'Citas']);
  return lista;
}

function acciones(p, ctx) {
  if (p.archivado) return [];
  const lista = [];
  if (sesion.tiene('consultas:registrar')) {
    lista.push(h('button', { class: 'btn', type: 'button', onclick: ctx.nuevaOrden }, ic('flask-conical', 16), 'Nueva orden'));
    lista.push(h('button', { class: 'btn sec', type: 'button', onclick: () => abrirConsulta(p, ctx.alGuardarConsulta) }, ic('file-plus', 16), 'Nueva consulta'));
  }
  if (sesion.tiene('citas:gestionar')) lista.push(h('button', { class: 'btn sec', type: 'button', onclick: () => abrirCita({ paciente: p, profesionales: ctx.profesionales, alGuardar: ctx.repintar }) }, ic('calendar-plus', 16), 'Agendar cita'));
  if (sesion.tiene('pacientes:registrar')) lista.push(h('button', { class: 'btn sec', type: 'button', onclick: () => abrirEditar(p, ctx.repintar) }, ic('pencil', 16), 'Editar datos'));
  if (sesion.tiene('historiales:archivar')) lista.push(h('button', { class: 'btn peligro', type: 'button', onclick: () => abrirArchivar(p, ctx.repintar) }, ic('archive', 16), 'Archivar historial'));
  return lista;
}

export async function pintarFicha(zona, { idPaciente, pestana, q, origen, repintar }) {
  zona.replaceChildren(cargando(6));
  const base = `/pacientes/${encodeURIComponent(idPaciente)}`;
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
        const [historial, citas, ordenes] = await Promise.all([
          clinico ? lectura(api(`${base}/historial`, { params: { limite: actual === 'historial' ? POR_PAGINA : 20 } })) : null,
          sesion.tiene('citas:leer') ? lectura(api(`${base}/citas`)) : null,
          veOrdenes() ? lectura(api(`${base}/ordenes`, { params: { limite: 50 } })) : null,
        ]);
        return { historial, citas, ordenes };
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
    /* La orden se pide sobre una consulta: se ofrecen las mas recientes del historial. */
    nuevaOrden: () => abrirNuevaOrden(paciente, {
      consultas: datos.historial?.valor?.consultas || [],
      alGuardar: () => (actual === 'ordenes' ? repintar() : irA(ruta('ordenes'), { q })),
    }),
  };
  const contenido = { resumen: pestanaResumen, historial: pestanaHistorial, citas: pestanaCitas, ordenes: pestanaOrdenes }[actual];

  zona.replaceChildren(...[
    paciente.archivado && aviso('', 'archive', h('b', { text: 'Este historial está archivado. ' }), 'No admite consultas, órdenes ni cambios nuevos. Sus resultados siguen disponibles.'),
    h('section', { class: 'papel ficha-cab', 'aria-label': 'Paciente' },
      ORIGENES[origen] && h('a', { class: 'enlace', href: enlace(origen), text: `← Volver a ${ORIGENES[origen]}` }),
      h('div', { class: 'ficha-titulo' },
        h('div', { class: 'ficha-nombre' }, h('span', { class: 'avatar', 'aria-hidden': 'true', text: iniciales(paciente) }),
          h('div', null, h('h2', { text: nombreDe(paciente) }),
            h('p', { class: 'hint' }, paciente.fecha_nacimiento ? `Nació el ${fFechaCivil(paciente.fecha_nacimiento)} · ` : '', 'ID ', h('span', { class: 'num', text: paciente.id_paciente }))))),
      resumenFicha(indicadores(paciente, datos)), accionesFicha(acciones(paciente, ctx))),
    !clinico && h('p', { class: 'hint' }, ic('lock', 14), ' Ves órdenes y resultados; el historial clínico es del personal médico.'),
    h('div', { class: 'pestanas', role: 'tablist', 'aria-label': 'Secciones de la ficha' }, pestanas.map(([k, icono, texto]) => h('button', {
      type: 'button', role: 'tab', 'aria-selected': k === actual ? 'true' : 'false', onclick: () => irA(ruta(k), { q, origen }),
    }, ic(icono, 16), texto))),
    h('div', { role: 'tabpanel' }, contenido(paciente, ctx)),
  ].filter(Boolean));
}
