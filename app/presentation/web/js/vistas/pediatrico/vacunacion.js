/* Esquema de vacunacion del paciente y catalogo. Decision del equipo: sin lotes ni existencias. */
import { api } from '../../api.js';
import { sesion } from '../../sesion.js';
import { fFechaCivil, fFechaHora, hoyLocal, nombreDe } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import {
  aviso, aviso_flotante, cabeza, campo, cargando, chip, confirmar, entrada, estadoDeError, lateral, seleccion, tabla, vacio,
} from '../../ui/componentes.js';
import { areaTexto, enviar, nombreProfesional } from './comun.js';

const ruta = (p) => `/pacientes/${encodeURIComponent(p.id_paciente)}/vacunacion`;

export function edadRecomendada(meses) {
  if (meses == null) return '—';
  if (meses === 0) return 'Al nacer';
  if (meses < 24 || meses % 12) return meses === 1 ? '1 mes' : `${meses} meses`;
  return `${meses / 12} años`;
}

const estaAtrasada = (d, hoy) => d.estado === 'pendiente' && d.fecha_programada && d.fecha_programada < hoy;

function chipDosis(d, hoy) {
  if (d.estado === 'aplicada') return chip('ok', 'check', 'Aplicada');
  if (d.estado === 'cancelada') return chip('', 'ban', 'Cancelada');
  return estaAtrasada(d, hoy) ? chip('aviso', 'hourglass', 'Atrasada') : chip('info', 'clock', 'Pendiente');
}

export function pestanaVacunacion(p, ctx) {
  const { valor: dosis, error } = ctx.datos.vacunacion;
  if (error) return estadoDeError(error, ctx.repintar);
  const hoy = hoyLocal();
  const escribe = sesion.tiene('consultas:registrar') && !p.archivado;
  const vacunas = ctx.datos.vacunas?.valor;

  const generar = h('button', {
    class: 'btn sec', type: 'button',
    onclick: async () => {
      generar.disabled = true;
      try {
        const nuevas = await api(`${ruta(p)}/esquema-recomendado`, { metodo: 'POST' });
        aviso_flotante(nuevas.length === 0 ? 'El esquema ya estaba completo'
          : nuevas.length === 1 ? 'Se programó 1 dosis' : `Se programaron ${nuevas.length} dosis`);
        ctx.repintar();
      } catch (e) {
        generar.disabled = false;
        aviso_flotante(e.message, 'circle-alert');
      }
    },
  }, ic('list-checks', 16), 'Generar esquema recomendado');
  /* Sin catalogo no hay que programar: "generar" responderia una lista vacia, como si estuviera completo. */
  const sinCatalogo = vacunas?.length === 0;
  const acciones = escribe && !sinCatalogo ? h('div', { class: 'fila' }, generar,
    vacunas && h('button', { class: 'btn', type: 'button', onclick: () => abrirDosis(p, vacunas, ctx.repintar) }, ic('plus', 16), 'Programar dosis')) : null;

  if (!dosis.length) {
    return sinCatalogo
      ? vacio('syringe', 'El catálogo de vacunas está vacío', 'Para programar dosis, primero hay que cargar los tipos de vacuna en la base del centro.')
      : vacio('syringe', 'Sin dosis programadas', 'Genera el esquema recomendado según la edad o programa una dosis.', acciones);
  }

  const cuenta = (filtro) => dosis.filter(filtro).length;
  const atrasadas = cuenta((d) => estaAtrasada(d, hoy));
  const mosaico = (clase, icono, texto, valor) => h('div', { class: `mosaico ${clase}` }, ic(icono, 20), h('div', null, h('small', { text: texto }), h('b', { text: String(valor) })));

  return h('div', { class: 'pila' },
    h('div', { class: 'papel-cab sin-margen' }, h('h2', { text: 'Esquema de vacunación' }), acciones),
    h('div', { class: 'mosaicos' },
      mosaico('ok', 'circle-check', 'Aplicadas', cuenta((d) => d.estado === 'aplicada')),
      mosaico('', 'clock', 'Pendientes', cuenta((d) => d.estado === 'pendiente') - atrasadas),
      atrasadas > 0 && mosaico('aviso', 'hourglass', 'Atrasadas', atrasadas)),
    tabla(['Vacuna', 'Dosis', 'Programada', 'Estado', 'Aplicación', ''], dosis.map((d) => h('tr', null,
      h('td', null, h('b', { text: d.nombre_vacuna })),
      h('td', { class: 'num', text: d.numero_dosis ?? '—' }),
      h('td', { class: 'num', text: d.fecha_programada ? fFechaCivil(d.fecha_programada) : '—' }),
      h('td', null, chipDosis(d, hoy)),
      h('td', { class: 'ajustar' }, d.fecha_aplicacion
        ? h('div', null, fFechaHora(d.fecha_aplicacion),
          h('div', { class: 'hint', text: nombreProfesional(ctx.profesionales, d.id_aplicador) }),
          d.observaciones_reaccion && h('div', { class: 'hint', text: `Reacción: ${d.observaciones_reaccion}` }))
        : '—'),
      h('td', null, escribe && d.estado === 'pendiente' && h('div', { class: 'fila' },
        h('button', { class: 'btn sm', type: 'button', text: 'Aplicar', onclick: () => abrirAplicar(p, d, ctx.repintar) }),
        h('button', {
          class: 'btn tenue sm', type: 'button', text: 'Cancelar',
          onclick: () => confirmar({
            titulo: 'Cancelar dosis',
            peligro: true,
            accion: 'Cancelar dosis',
            cuerpo: h('p', { text: `Se cancelará la dosis${d.numero_dosis ? ` ${d.numero_dosis}` : ''} de ${d.nombre_vacuna}. Queda en el esquema como cancelada.` }),
            alConfirmar: async () => {
              await api(`${ruta(p)}/${encodeURIComponent(d.id_dosis)}/cancelar`, { metodo: 'POST' });
              aviso_flotante('Dosis cancelada');
              ctx.repintar();
            },
          }),
        })))))));
}

function abrirDosis(p, vacunas, alGuardar) {
  const vacuna = seleccion('dosis-vacuna', [
    { valor: '', texto: 'Elige la vacuna' },
    ...vacunas.map((v) => ({ valor: v.id_vacuna, texto: `${v.nombre} · ${edadRecomendada(v.edad_recomendada_meses)}` })),
  ]);
  const numero = entrada('dosis-numero', { type: 'number', min: 1, max: 20, inputmode: 'numeric' });
  const fecha = entrada('dosis-fecha', { type: 'date', min: p.fecha_nacimiento || null });
  const campos = {
    id_vacuna: campo('Vacuna', vacuna),
    numero_dosis: campo('Número de dosis', numero, { opcional: true }),
    fecha_programada: campo('Fecha programada', fecha, { opcional: true }),
  };
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'button', text: 'Programar' });
  const panel = lateral('Programar dosis', [campos.id_vacuna, h('div', { class: 'dos' }, campos.numero_dosis, campos.fecha_programada), zona],
    [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => panel.cerrar() }), boton]);
  boton.addEventListener('click', () => {
    campos.id_vacuna.marcar(vacuna.value ? null : 'Elige la vacuna.');
    const numeroValido = numero.validity.valid;
    campos.numero_dosis.marcar(numeroValido ? null : 'Escribe un número entre 1 y 20.');
    const fechaValida = fecha.validity.valid;
    campos.fecha_programada.marcar(fechaValida ? null : 'No puede ser anterior al nacimiento.');
    if (!vacuna.value || !numeroValido || !fechaValida) return;
    enviar(boton, zona, campos, async () => {
      await api(ruta(p), {
        metodo: 'POST',
        cuerpo: { id_vacuna: vacuna.value, numero_dosis: numero.value ? Number(numero.value) : null, fecha_programada: fecha.value || null },
      });
      panel.cerrar();
      aviso_flotante('Dosis programada');
      alGuardar();
    });
  });
}

function abrirAplicar(p, d, alGuardar) {
  const reaccion = areaTexto('aplicar-reaccion', { maxlength: 1000, placeholder: 'Fiebre leve, enrojecimiento en el sitio…' });
  const campos = { observaciones_reaccion: campo('Reacción observada', reaccion, { opcional: true }) };
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'button' }, ic('syringe', 16), 'Marcar como aplicada');
  const panel = lateral('Aplicar dosis', [
    h('p', { class: 'muted', text: `${d.nombre_vacuna}${d.numero_dosis ? ` · dosis ${d.numero_dosis}` : ''} · ${nombreDe(p)}` }),
    aviso('info', 'info', 'Quedas registrado como quien aplica, con la fecha y la hora de ahora.'),
    campos.observaciones_reaccion, zona,
  ], [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => panel.cerrar() }), boton]);
  boton.addEventListener('click', () => enviar(boton, zona, campos, async () => {
    await api(`${ruta(p)}/${encodeURIComponent(d.id_dosis)}/aplicar`, {
      metodo: 'POST',
      cuerpo: { observaciones_reaccion: reaccion.value.trim() || null },
    });
    panel.cerrar();
    aviso_flotante('Dosis aplicada');
    alGuardar();
  }));
}

/* ---------- Catalogo ---------- */
export async function vistaCatalogoVacunas({ contenedor, repintar }) {
  const zona = h('div', { class: 'pila', 'aria-live': 'polite' }, cargando(6));
  contenedor.append(cabeza('Catálogo de vacunas', 'Tipos de vacuna del centro, en solo lectura.'), zona);
  try {
    const vacunas = await api('/vacunas');
    zona.replaceChildren(vacunas.length
      ? tabla(['Vacuna', 'Previene', 'Edad recomendada', 'Dosis sugerida'], vacunas.map((v) => h('tr', null,
        h('td', null, h('b', { text: v.nombre })),
        h('td', { class: 'ajustar', text: v.enfermedades_que_previene || '—' }),
        h('td', { text: edadRecomendada(v.edad_recomendada_meses) }),
        h('td', { text: v.dosis_sugerida || '—' }))))
      : vacio('syringe', 'El catálogo está vacío', 'Los tipos de vacuna se cargan con las migraciones de la base.'));
  } catch (error) {
    zona.replaceChildren(estadoDeError(error, repintar));
  }
}
