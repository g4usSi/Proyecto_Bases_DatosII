/* Ficha del paciente: cabecera con la edad e indicadores, y pestanas segun los permisos. */
import { api } from '../../api.js';
import { sesion } from '../../sesion.js';
import { enlace, irA } from '../../enrutador.js';
import { fFechaCivil, fFechaCorta, fFechaHora, fHora, mesesCumplidos, nombreDe } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import { aviso, cargando, chip, estadoDeError, vacio } from '../../ui/componentes.js';
import { cargarProfesionales, chipCita, claseCita, estaPorAtender, nombreProfesional } from './comun.js';
import { abrirAdenda, abrirAlergias, abrirArchivar, abrirConsulta, abrirEditar } from './formularios.js';
import { abrirCita } from './agendar.js';
import { pestanaCrecimiento } from './crecimiento.js';
import { pestanaVacunacion } from './vacunacion.js';

const POR_PAGINA = 10;

const iniciales = (p) => `${p.nombres[0] || ''}${p.apellidos[0] || ''}`.toUpperCase();

/* Cada lectura falla por separado: un servicio caido no debe ocultar la ficha. */
const lectura = (promesa) => promesa.then((valor) => ({ valor }), (error) => ({ error }));

function proximaCita(citas) {
  const ahora = Date.now();
  return citas.filter((c) => estaPorAtender(c) && new Date(c.inicio).getTime() > ahora)
    .sort((a, b) => a.inicio.localeCompare(b.inicio))[0] || null;
}

/* La edad en burbujas es el rasgo del Centro Pediatrico: decorativa, el texto la repite. */
function burbujasDeEdad(nacimiento) {
  const meses = mesesCumplidos(nacimiento);
  const burbuja = (n, unidad, clase) => h('span', { class: `burbuja ${clase}` }, h('b', { text: String(n) }), h('small', { text: unidad }));
  if (meses < 24) return h('span', { class: 'burbujas', 'aria-hidden': 'true' }, burbuja(meses, meses === 1 ? 'mes' : 'meses', 'b1'));
  const anos = Math.floor(meses / 12);
  const resto = meses % 12;
  return h('span', { class: 'burbujas', 'aria-hidden': 'true' }, burbuja(anos, 'años', 'b1'), burbuja(resto, resto === 1 ? 'mes' : 'meses', 'b2'));
}

function textoDeEdad(nacimiento) {
  const meses = mesesCumplidos(nacimiento);
  const conMeses = (n) => (n === 1 ? '1 mes' : `${n} meses`);
  if (meses < 24) return conMeses(meses);
  const resto = meses % 12;
  return `${Math.floor(meses / 12)} años${resto ? ` y ${conMeses(resto)}` : ''}`;
}

function indicadores(p, datos) {
  const clinico = sesion.tiene('historiales:leer');
  const lista = [p.archivado ? ['', 'archive', 'Estado', 'Archivado'] : ['ok', 'circle-check', 'Estado', 'Activo']];
  if (clinico && datos.historial?.valor) {
    const ultima = datos.historial.valor.consultas[0];
    lista.push(['', 'history', 'Última consulta', ultima ? fFechaCorta(ultima.fecha_hora) : 'Sin consultas']);
  }
  if (datos.citas?.valor) {
    const proxima = proximaCita(datos.citas.valor);
    lista.push(['', 'calendar-days', 'Próxima cita', proxima ? `${fFechaCorta(proxima.inicio)}, ${fHora(proxima.inicio)}` : 'Sin cita programada']);
  }
  if (clinico && p.alergias?.length) {
    lista.push(['aviso', 'triangle-alert', 'Alergias', p.alergias.length === 1 ? '1 registrada' : `${p.alergias.length} registradas`]);
  }
  const ultimoControl = datos.crecimiento?.valor?.[0];
  if (ultimoControl) {
    const medida = (valor, unidad) => (valor == null ? '—' : `${valor} ${unidad}`);
    lista.push(['', 'scale', 'Último control', `${medida(ultimoControl.peso_kg, 'kg')} · ${medida(ultimoControl.talla_cm, 'cm')}`]);
  }
  return lista.map(([clase, icono, titulo, valor]) => h('div', { class: `mosaico ${clase}` }, ic(icono, 20), h('div', null, h('small', { text: titulo }), h('b', { text: valor }))));
}

function pestanaResumen(p, ctx) {
  const clinico = sesion.tiene('historiales:leer');
  const c = p.contacto;
  let alergias;
  if (!clinico) {
    alergias = h('div', { class: 'reservado' }, ic('lock', 16), h('span', { text: 'Información clínica reservada para el personal con acceso a historiales.' }));
  } else if (p.alergias === null) {
    alergias = h('div', { class: 'pila-s' }, chip('', 'circle-help', 'No registradas'),
      h('p', { class: 'hint', text: 'Todavía no se han evaluado. No es lo mismo que «sin alergias».' }));
  } else if (!p.alergias.length) {
    alergias = chip('ok', 'circle-check', 'Sin alergias conocidas');
  } else {
    alergias = h('div', { class: 'pila-s' }, p.alergias.map((a) => aviso('aviso', 'triangle-alert',
      h('b', { text: a.sustancia }), a.reaccion && h('div', { text: a.reaccion }),
      a.severidad && h('div', { class: 'hint', text: `Severidad: ${a.severidad}` }))));
  }
  return h('div', { class: 'dos-col' },
    h('section', { class: 'papel' }, h('h3', { class: 'titulo-papel', text: 'Contacto' }),
      c && (c.telefono || c.correo || c.direccion)
        ? h('dl', { class: 'lista-datos' },
          h('dt', { text: 'Teléfono' }), h('dd', { text: c.telefono || 'No registrado' }),
          h('dt', { text: 'Correo' }), h('dd', { text: c.correo || 'No registrado' }),
          h('dt', { text: 'Dirección' }), h('dd', { text: c.direccion || 'No registrada' }))
        : h('p', { class: 'muted', text: 'Sin datos de contacto.' })),
    h('section', { class: 'papel' },
      h('div', { class: 'papel-cab' }, h('h3', { text: 'Alergias' }),
        clinico && sesion.tiene('pacientes:registrar') && !p.archivado
        && h('button', { class: 'btn sec sm', type: 'button', onclick: () => abrirAlergias(p, ctx.repintar) }, ic('plus', 14), 'Agregar')),
      alergias));
}

function nodoConsulta(c, p, ctx) {
  return h('article', { class: 'consulta' },
    h('header', null, h('h3', { text: c.motivo }),
      h('span', { class: 'hint', text: `${fFechaHora(c.fecha_hora)} · ${nombreProfesional(ctx.profesionales, c.id_profesional)}` })),
    c.notas && h('p', { class: 'con-saltos', text: c.notas }),
    c.diagnosticos.length > 0 && h('div', null, h('div', { class: 'subtitulo', text: 'Diagnósticos' }),
      h('div', { class: 'etiquetas' }, c.diagnosticos.map((d) => h('span', { class: 'chip info' }, d.descripcion, d.codigo && h('span', { class: 'codigo', text: ` ${d.codigo}` }))))),
    c.tratamientos.length > 0 && h('div', null, h('div', { class: 'subtitulo', text: 'Tratamientos' }),
      h('ul', { class: 'lista-simple' }, c.tratamientos.map((t) => h('li', { text: t.descripcion })))),
    c.recetas.length > 0 && h('div', null, h('div', { class: 'subtitulo', text: 'Recetas' }),
      h('div', { class: 'tabla', tabindex: '0', role: 'region', 'aria-label': 'Recetas' }, h('table', null,
        h('thead', null, h('tr', null, ['Medicamento', 'Dosis', 'Frecuencia', 'Vía', 'Días'].map((t) => h('th', { scope: 'col', text: t })))),
        h('tbody', null, c.recetas.map((r) => h('tr', null,
          h('td', { class: 'ajustar' }, h('b', { text: r.medicamento }), r.instrucciones && h('div', { class: 'hint', text: r.instrucciones })),
          h('td', { text: r.dosis }), h('td', { text: r.frecuencia }),
          h('td', { text: r.via_administracion || '—' }), h('td', { text: r.duracion_dias ?? '—' }))))))),
    h('div', { class: 'fila' },
      sesion.tiene('consultas:registrar') && !p.archivado
      && h('button', { class: 'btn tenue sm', type: 'button', onclick: () => abrirAdenda(c, p, ctx.repintar) }, ic('file-plus', 14), 'Agregar adenda')));
}

function pestanaHistorial(p, ctx) {
  const { valor, error } = ctx.datos.historial;
  if (error) return estadoDeError(error, ctx.repintar);
  if (!valor.consultas.length) {
    return vacio('notebook-text', 'Aún no hay consultas', 'Cuando se registre una consulta aparecerá aquí, de la más reciente a la más antigua.',
      sesion.tiene('consultas:registrar') && !p.archivado
        ? h('button', { class: 'btn', type: 'button', onclick: () => abrirConsulta(p, ctx.repintar) }, ic('file-plus', 16), 'Registrar la primera consulta')
        : null);
  }
  const lista = h('div', { class: 'pila' }, valor.consultas.map((c) => nodoConsulta(c, p, ctx)));
  const zonaMas = h('div', { class: 'mas' });

  function pintarMas(cursor) {
    zonaMas.replaceChildren();
    if (!cursor) return;
    const boton = h('button', {
      class: 'btn sec', type: 'button',
      onclick: async () => {
        boton.disabled = true;
        try {
          const pagina = await api(`/pacientes/${encodeURIComponent(p.id_paciente)}/historial`, { params: { limite: POR_PAGINA, antes_de: cursor } });
          lista.append(...pagina.consultas.map((c) => nodoConsulta(c, p, ctx)));
          pintarMas(pagina.siguiente_antes_de);
        } catch (e) {
          zonaMas.replaceChildren(estadoDeError(e, () => pintarMas(cursor)));
        }
      },
    }, ic('chevron-down', 16), 'Cargar consultas anteriores');
    zonaMas.append(boton);
  }
  pintarMas(valor.siguiente_antes_de);
  return h('div', { class: 'pila' }, lista, zonaMas);
}

function pestanaCitas(p, ctx) {
  const { valor, error } = ctx.datos.citas;
  if (error) return estadoDeError(error, ctx.repintar);
  if (!valor.length) {
    return vacio('calendar-days', 'Sin citas', 'Este paciente no tiene citas registradas.',
      sesion.tiene('citas:gestionar') && !p.archivado
        ? h('button', { class: 'btn', type: 'button', onclick: () => abrirCita({ paciente: p, profesionales: ctx.profesionales, alGuardar: ctx.repintar }) }, ic('calendar-plus', 16), 'Agendar cita')
        : null);
  }
  const ordenadas = [...valor].sort((a, b) => b.inicio.localeCompare(a.inicio));
  return h('div', { class: 'pila-s' }, ordenadas.map((c) => h('div', { class: `fila-cita ${claseCita(c.estado)}` },
    h('time', null, fFechaCorta(c.inicio), h('small', { text: `${fHora(c.inicio)} a ${fHora(c.fin)}` })),
    h('div', { class: 'cita-datos' }, h('b', { text: c.motivo }), c.motivo_cambio && h('small', { text: `Motivo del cambio: ${c.motivo_cambio}` })),
    h('span', { class: 'hint', text: nombreProfesional(ctx.profesionales, c.id_profesional) }),
    chipCita(c.estado))));
}

function pestanasDe() {
  const lista = [['resumen', 'user-round', 'Resumen']];
  if (sesion.tiene('historiales:leer')) lista.push(['historial', 'notebook-text', 'Historial']);
  if (sesion.tiene('citas:leer')) lista.push(['citas', 'calendar-days', 'Citas']);
  if (sesion.tiene('historiales:leer')) lista.push(['crecimiento', 'ruler', 'Crecimiento']);
  if (sesion.tiene('historiales:leer')) lista.push(['vacunacion', 'syringe', 'Vacunación']);
  return lista;
}

function acciones(p, ctx) {
  const lista = [];
  if (!p.archivado) {
    if (sesion.tiene('consultas:registrar')) lista.push(h('button', { class: 'btn', type: 'button', onclick: () => abrirConsulta(p, ctx.alGuardarConsulta) }, ic('file-plus', 16), 'Nueva consulta'));
    if (sesion.tiene('citas:gestionar')) lista.push(h('button', { class: 'btn sec', type: 'button', onclick: () => abrirCita({ paciente: p, profesionales: ctx.profesionales, alGuardar: ctx.repintar }) }, ic('calendar-plus', 16), 'Agendar cita'));
    if (sesion.tiene('pacientes:registrar')) lista.push(h('button', { class: 'btn sec', type: 'button', onclick: () => abrirEditar(p, ctx.repintar) }, ic('pencil', 16), 'Editar datos'));
    if (sesion.tiene('historiales:archivar')) lista.push(h('button', { class: 'btn peligro', type: 'button', onclick: () => abrirArchivar(p, ctx.repintar) }, ic('archive', 16), 'Archivar historial'));
  }
  return lista;
}

export async function pintarFicha(zona, { idPaciente, pestana, q, origen, repintar }) {
  zona.replaceChildren(cargando(6));
  const base = `/pacientes/${encodeURIComponent(idPaciente)}`;
  const pestanas = pestanasDe();
  const actual = pestanas.some(([k]) => k === pestana) ? pestana : 'resumen';
  const clinico = sesion.tiene('historiales:leer');
  /* Lo que alimenta los indicadores se lee siempre; el resto, solo en su pestana. */
  const soloEn = (clave, permitido, leer) => (actual === clave && permitido ? lectura(leer()) : null);

  let paciente;
  let datos;
  let profesionales;
  try {
    [paciente, datos, profesionales] = await Promise.all([
      api(base),
      (async () => {
        const [historial, citas, crecimiento, vacunacion, vacunas, tutores, facturas] = await Promise.all([
          clinico ? lectura(api(`${base}/historial`, { params: { limite: actual === 'historial' ? POR_PAGINA : 1 } })) : null,
          sesion.tiene('citas:leer') ? lectura(api(`${base}/citas`)) : null,
          clinico ? lectura(api(`${base}/crecimiento`, { params: { limite: 200 } })) : null,
          soloEn('vacunacion', clinico, () => api(`${base}/vacunacion`)),
          soloEn('vacunacion', clinico, () => api('/vacunas')),
          soloEn('tutores', true, () => api(`${base}/tutores`)),
          soloEn('facturas', sesion.tiene('pagos:ver'), () => api(`${base}/cobros`)),
        ]);
        return { historial, citas, crecimiento, vacunacion, vacunas, tutores, facturas };
      })(),
      cargarProfesionales(),
    ]);
  } catch (error) {
    if (error.estado === 404) {
      zona.replaceChildren(vacio('inbox', 'Paciente no encontrado', 'No existe en tu institución o ya no está disponible.'));
    } else {
      zona.replaceChildren(estadoDeError(error, repintar));
    }
    return;
  }

  const ruta = (k) => `pacientes/${encodeURIComponent(idPaciente)}${k === 'resumen' ? '' : `/${k}`}`;
  const ctx = {
    datos,
    profesionales,
    repintar,
    alGuardarConsulta: () => {
      if (actual === 'historial') repintar();
      else irA(ruta('historial'), { q });
    },
  };
  const contenido = {
    resumen: pestanaResumen,
    historial: pestanaHistorial,
    citas: pestanaCitas,
    crecimiento: pestanaCrecimiento,
    vacunacion: pestanaVacunacion,
  }[actual];

  zona.replaceChildren(...[
    paciente.archivado && aviso('', 'archive', h('b', { text: 'Este historial está archivado. ' }), 'No admite consultas, citas ni cambios nuevos. La información clínica sigue disponible para consulta.'),
    h('section', { class: 'papel ficha-cab', 'aria-label': 'Paciente' },
      origen === 'agenda' && h('a', { class: 'enlace', href: enlace('agenda'), text: '← Volver a la agenda' }),
      h('div', { class: 'ficha-titulo' },
        h('div', { class: 'ficha-nombre' },
          paciente.fecha_nacimiento ? burbujasDeEdad(paciente.fecha_nacimiento) : h('span', { class: 'avatar', 'aria-hidden': 'true', text: iniciales(paciente) }),
          h('div', null, h('h2', { text: nombreDe(paciente) }),
            h('p', { class: 'hint', text: paciente.fecha_nacimiento ? `${textoDeEdad(paciente.fecha_nacimiento)}. Nació el ${fFechaCivil(paciente.fecha_nacimiento)}` : 'Sin fecha de nacimiento' }))),
        h('div', { class: 'fila' }, acciones(paciente, ctx))),
      h('div', { class: 'mosaicos' }, indicadores(paciente, datos))),
    h('div', { class: 'pestanas', role: 'tablist', 'aria-label': 'Secciones de la ficha' }, pestanas.map(([k, icono, texto]) => h('button', {
      type: 'button', role: 'tab', 'aria-selected': k === actual ? 'true' : 'false', onclick: () => irA(ruta(k), { q, origen }),
    }, ic(icono, 16), texto))),
    h('div', { role: 'tabpanel' }, contenido(paciente, ctx)),
  ].filter(Boolean));
}
