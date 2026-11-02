/* Resumen: cuatro entidades para el superusuario; lo pendiente de su personal para el administrador. */
import { api } from '../../api.js';
import { sesion } from '../../sesion.js';
import { ACCIONES_BITACORA, ENTIDADES, entidad, textoRol } from '../../catalogos.js';
import { enlace } from '../../enrutador.js';
import { fEntero, fFechaHora, fMoneda, nombreDe, plural } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import { aviso, cabeza, cargando, chip, cifras, estadoDeError } from '../../ui/componentes.js';
import { describirDetalle } from './bitacora.js';
import { abrirUsuario } from './usuarios.js';

export function vistaResumen(contexto) {
  return sesion.tiene('plataforma:administrar') ? resumenPlataforma(contexto) : resumenEntidad(contexto);
}

function filasDe(id, datos) {
  const propias = {
    hospital_general: [
      ['Camas ocupadas', fEntero(datos.camas_ocupadas)],
      ['Emergencias abiertas', fEntero(datos.emergencias_abiertas)],
      ['Cobros abiertos', fEntero(datos.cobros_abiertos)],
      ['Saldo pendiente', fMoneda(datos.saldo_pendiente)],
    ],
    centro_pediatrico: [
      ['Cobros abiertos', fEntero(datos.cobros_abiertos)],
      ['Saldo pendiente', fMoneda(datos.saldo_pendiente)],
    ],
    laboratorio_clinico: [['Órdenes abiertas', fEntero(datos.ordenes_abiertas)]],
    clinica_odontologica: [],
  };
  const sinAcceso = datos.personal_sin_acceso;
  return [
    ['Administración', datos.administrador_activo || 'Sin administrador'],
    ['Personal activo', fEntero(datos.personal_activo)],
    ['Personal sin acceso', fEntero(sinAcceso)],
    ['Pacientes registrados', fEntero(datos.pacientes_registrados)],
    ['Citas de hoy', fEntero(datos.citas_hoy)],
    ...propias[id],
  ];
}

function panelEntidad(e, datos) {
  const cab = h('div', { class: 'entidad-cab' },
    h('span', { class: 'emblema' }, ic(e.emblema, 20)),
    h('div', null, h('h2', { text: e.nombre }), h('small', { text: `Base de datos: ${e.motor}` })));
  const usuarios = h('a', { class: 'btn sec sm', href: enlace('usuarios', { entidad: e.id }) }, ic('user-cog', 15), 'Ver usuarios');
  if (!datos) {
    return h('section', { class: 'entidad sin-datos', 'aria-label': e.nombre }, cab,
      chip('aviso', 'server-off', 'Sin conexión'),
      h('p', { text: 'Su base de datos no respondió o no está configurada. Las otras entidades no se ven afectadas.' }),
      h('div', { class: 'fila' }, usuarios));
  }
  const cobros = { hospital_general: ['Ver pagos', 'banknote'], centro_pediatrico: ['Ver facturación', 'receipt'] }[e.id];
  return h('section', { class: 'entidad', 'aria-label': e.nombre }, cab,
    h('dl', { class: 'entidad-datos' }, filasDe(e.id, datos).flatMap(([t, v]) => [h('dt', { text: t }), h('dd', { text: v })])),
    h('div', { class: 'fila' }, usuarios,
      cobros && h('a', { class: 'btn tenue sm', href: enlace(`cobros/${e.id}`) }, ic(cobros[1], 15), cobros[0])));
}

async function resumenPlataforma({ contenedor, repintar }) {
  const encabezado = cabeza('Resumen', 'Las cuatro entidades de un vistazo. Solo conteos: ningún dato clínico ni de pacientes.');
  contenedor.replaceChildren(encabezado, cargando(6));
  contenedor.querySelector('h1').focus({ preventScroll: true });
  try {
    const datos = await api('/plataforma/resumen');
    const presentes = ENTIDADES.filter((e) => datos[e.id]);
    const faltan = ENTIDADES.filter((e) => !datos[e.id]);
    const suma = (campo) => presentes.reduce((total, e) => total + (datos[e.id][campo] || 0), 0);
    contenedor.replaceChildren(encabezado,
      cifras([
        { etiqueta: 'Personal activo', valor: fEntero(suma('personal_activo')) },
        { etiqueta: 'Cuentas sin acceso', valor: fEntero(suma('personal_sin_acceso')), clase: suma('personal_sin_acceso') ? 'crit' : '', nota: 'Bloqueadas o deshabilitadas' },
        { etiqueta: 'Pacientes registrados', valor: fEntero(suma('pacientes_registrados')) },
        { etiqueta: 'Citas de hoy', valor: fEntero(suma('citas_hoy')) },
      ]),
      ...(faltan.length ? [aviso('aviso', 'triangle-alert', h('b', { text: 'Totales parciales. ' }), `No incluyen: ${faltan.map((e) => e.nombre).join(', ')}.`)] : []),
      h('div', { class: 'entidades' }, ENTIDADES.map((e) => panelEntidad(e, datos[e.id]))));
  } catch (error) {
    contenedor.replaceChildren(encabezado, estadoDeError(error, repintar));
  }
}

async function resumenEntidad({ contenedor, repintar }) {
  const inst = entidad(sesion.usuario.institucion);
  const encabezado = cabeza('Resumen', `Personal de ${inst.nombre} y lo que necesita tu atención.`);
  contenedor.replaceChildren(encabezado, cargando(6));
  contenedor.querySelector('h1').focus({ preventScroll: true });
  try {
    const [resumen, personal] = await Promise.all([api('/profesionales/resumen'), api('/profesionales', { params: { limite: 500 } })]);
    const porEstado = resumen.por_estado;
    const atender = personal.filter((p) => p.estado === 'bloqueada' || (p.estado === 'activa' && p.debe_cambiar_contrasena));
    const fila = (p) => {
      const bloqueada = p.estado === 'bloqueada';
      return h('div', { class: 'movimiento corto' },
        bloqueada ? chip('crit', 'ban', 'Bloqueada') : chip('aviso', 'key-round', 'Contraseña'),
        h('div', null, h('b', { text: nombreDe(p) }), h('small', { text: `${textoRol(p.rol)}. ${bloqueada ? 'No puede entrar hasta que la desbloquees.' : 'Todavía no elige su propia contraseña.'}` })),
        h('button', { class: 'btn sec sm', type: 'button', onclick: () => abrirUsuario(p, { personal, alCambiar: repintar }), text: 'Abrir' }));
    };
    const conteos = (mapa, texto) => h('div', { class: 'conteos' }, Object.entries(mapa).map(([k, v]) => h('div', null, h('span', { text: texto(k) }), h('b', { text: fEntero(v) }))));
    contenedor.replaceChildren(encabezado,
      cifras([
        { etiqueta: 'Personal activo', valor: fEntero(porEstado.activa || 0) },
        { etiqueta: 'Bloqueadas', valor: fEntero(porEstado.bloqueada || 0), clase: porEstado.bloqueada ? 'crit' : '', nota: `${fEntero(resumen.bloqueadas_por_intentos)} por intentos fallidos` },
        { etiqueta: 'Deshabilitadas', valor: fEntero(porEstado.inactiva || 0) },
        { etiqueta: 'Deben cambiar su contraseña', valor: fEntero(resumen.pendientes_cambio_contrasena), clase: resumen.pendientes_cambio_contrasena ? 'aviso' : '' },
      ]),
      h('div', { class: 'dos-col' },
        h('section', { class: 'papel' },
          h('div', { class: 'papel-cab' }, h('h2', { text: 'Requieren atención' }), h('small', { class: 'muted', text: plural(atender.length, 'cuenta', 'cuentas') })),
          atender.length ? h('div', { class: 'movimientos' }, atender.map(fila)) : h('p', { class: 'muted', text: 'Nada pendiente.' })),
        h('section', { class: 'papel' },
          h('div', { class: 'papel-cab' }, h('h2', { text: 'Personal activo' }), h('small', { class: 'muted', text: resumen.activos_por_departamento ? 'Por rol y por área' : 'Por rol' })),
          Object.keys(resumen.activos_por_rol).length ? conteos(resumen.activos_por_rol, textoRol) : h('p', { class: 'muted', text: 'Aún no hay personal activo.' }),
          resumen.activos_por_departamento && Object.keys(resumen.activos_por_departamento).length > 0
            && [h('h3', { class: 'titulo-sub', text: 'Por área' }), conteos(resumen.activos_por_departamento, (k) => k)])),
      h('section', { class: 'papel' },
        h('div', { class: 'papel-cab' }, h('h2', { text: 'Últimos movimientos' }),
          h('a', { class: 'btn tenue sm', href: enlace('bitacora') }, ic('history', 15), 'Ver bitácora')),
        resumen.ultimos_movimientos.length
          ? h('div', { class: 'movimientos' }, resumen.ultimos_movimientos.map((m) => {
            const a = ACCIONES_BITACORA[m.accion] || { clase: '', texto: m.accion };
            return h('div', { class: 'movimiento' }, chip(a.clase, a.icono, a.texto),
              h('div', null, h('b', { text: m.cuenta }), h('small', { text: [describirDetalle(m.detalle), `Por ${m.actor}`].filter(Boolean).join('. ') })),
              h('small', { text: fFechaHora(m.ocurrido_en) }));
          }))
          : h('p', { class: 'muted', text: 'Sin movimientos todavía.' })));
  } catch (error) {
    contenedor.replaceChildren(encabezado, estadoDeError(error, repintar));
  }
}
