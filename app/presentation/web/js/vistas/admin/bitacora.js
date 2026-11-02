/* Bitacora de administracion: solo se agrega y nunca contiene contrasenas. */
import { api } from '../../api.js';
import { sesion } from '../../sesion.js';
import { ACCIONES_BITACORA, ENTIDADES, entidad, textoRol } from '../../catalogos.js';
import { reflejar } from '../../enrutador.js';
import { fFechaHora, finDeDia, inicioDeDia } from '../../formato.js';
import { h } from '../../ui/dom.js';
import { cabeza, campo, cargando, chip, entrada, estadoDeError, segmento, tabla, vacio } from '../../ui/componentes.js';

const POR_PAGINA = 50;

const textoEstado = { activa: 'activa', bloqueada: 'bloqueada', inactiva: 'deshabilitada', eliminada: 'eliminada' };

/* El detalle es JSON libre: lo conocido se redacta y lo demas se muestra como dato. */
export function describirDetalle(detalle) {
  if (!detalle || !Object.keys(detalle).length) return '';
  const partes = [];
  for (const [clave, valor] of Object.entries(detalle)) {
    if (valor == null) continue;
    if (clave === 'id_departamento' && typeof valor !== 'object') partes.push('Área asignada');
    else if (clave === 'nombres' || clave === 'apellidos') partes.push(`${clave === 'nombres' ? 'Nombres' : 'Apellidos'} corregidos`);
    else if (clave === 'permisos' && valor && typeof valor === 'object' && !Array.isArray(valor)) {
      const mas = (valor.agregados || []).map((p) => `+ ${p}`);
      const menos = (valor.retirados || []).map((p) => `− ${p}`);
      partes.push(`Permisos: ${[...mas, ...menos].join(', ')}`);
    } else if (clave === 'permisos' && Array.isArray(valor)) partes.push(valor.length === 1 ? '1 permiso' : `${valor.length} permisos`);
    else if (clave === 'estado' && valor && typeof valor === 'object') partes.push(`Estado: ${textoEstado[valor.antes] || valor.antes || '—'} a ${textoEstado[valor.despues] || valor.despues || '—'}`);
    else if (clave === 'id_departamento' && valor && typeof valor === 'object') partes.push(`Área: ${valor.antes ?? 'sin área'} a ${valor.despues ?? 'sin área'}`);
    else if (clave === 'rol') partes.push(textoRol(String(valor)));
    else if (typeof valor === 'object') partes.push(`${clave}: ${JSON.stringify(valor)}`);
    else partes.push(`${clave}: ${valor}`);
  }
  return partes.join(', ');
}

export async function vistaBitacora({ contenedor, params }) {
  const esSuper = sesion.tiene('plataforma:administrar');
  const inst = sesion.usuario.institucion && entidad(sesion.usuario.institucion);
  const filtros = {
    entidad: esSuper ? (params.entidad || '') : '',
    accion: params.accion || '',
    desde: params.desde || '',
    hasta: params.hasta || '',
  };
  const zona = h('div', { class: 'pila', 'aria-live': 'polite' });

  async function cargar(anteriores = []) {
    reflejar('bitacora', filtros);
    if (!anteriores.length) zona.replaceChildren(cargando(6));
    try {
      const eventos = await api('/profesionales/bitacora', {
        params: {
          establecimiento: filtros.entidad,
          accion: filtros.accion,
          desde: inicioDeDia(filtros.desde),
          hasta: finDeDia(filtros.hasta),
          limite: POR_PAGINA,
          antes_de: anteriores.at(-1)?.id_evento,
        },
      });
      pintar([...anteriores, ...eventos], eventos.length === POR_PAGINA);
    } catch (error) {
      zona.replaceChildren(estadoDeError(error, () => cargar(anteriores)));
    }
  }

  function pintar(eventos, hayMas) {
    if (!eventos.length) {
      zona.replaceChildren(vacio('history', 'Sin movimientos', 'No hay movimientos con estos filtros.'));
      return;
    }
    zona.replaceChildren(
      tabla(['Fecha', 'Quién', 'Acción', 'Cuenta', esSuper && 'Entidad', 'Detalle'], eventos.map((ev) => {
        const accion = ACCIONES_BITACORA[ev.accion] || { clase: '', texto: ev.accion };
        const inst_ev = ev.institucion && entidad(ev.institucion);
        return h('tr', null,
          h('td', { class: 'num', text: fFechaHora(ev.ocurrido_en) }),
          h('td', null, h('div', { text: ev.actor }), h('small', { class: 'muted', text: textoRol(ev.rol_actor) })),
          h('td', null, chip(accion.clase, accion.icono, accion.texto)),
          h('td', { text: ev.cuenta }),
          esSuper && h('td', { text: inst_ev ? inst_ev.nombre : 'Plataforma' }),
          h('td', { class: 'ajustar', text: describirDetalle(ev.detalle) || '—' }));
      })),
      ...(hayMas ? [h('div', { class: 'mas' }, h('button', { class: 'btn sec', type: 'button', onclick: () => cargar(eventos), text: 'Cargar anteriores' }))] : []),
      h('p', { class: 'hint', text: 'Solo se agrega: nadie la edita ni la borra. Nunca guarda contraseñas ni sus hashes.' }));
  }

  function pintarFiltros() {
    const desde = entrada('bt-desde', { type: 'date', value: filtros.desde, onchange: (e) => { filtros.desde = e.target.value; cargar(); } });
    const hasta = entrada('bt-hasta', { type: 'date', value: filtros.hasta, onchange: (e) => { filtros.hasta = e.target.value; cargar(); } });
    return h('div', { class: 'filtros' },
      esSuper && segmento('Filtrar por entidad', [{ valor: '', texto: 'Todas' }, ...ENTIDADES.map((e) => ({ valor: e.id, texto: e.corto }))], filtros.entidad, (v) => { filtros.entidad = v; refrescar(); }),
      segmento('Filtrar por acción', [{ valor: '', texto: 'Todas' }, ...Object.entries(ACCIONES_BITACORA).map(([k, a]) => ({ valor: k, texto: a.filtro }))], filtros.accion, (v) => { filtros.accion = v; refrescar(); }),
      campo('Desde', desde, { opcional: true }),
      campo('Hasta', hasta, { opcional: true }));
  }

  const barra = h('div');
  function refrescar() {
    barra.replaceChildren(pintarFiltros());
    cargar();
  }

  contenedor.replaceChildren(
    cabeza('Bitácora', esSuper ? 'Quién hizo qué en la administración de las cuatro entidades.' : `Quién hizo qué en la administración de ${inst.nombre}.`),
    barra, zona);
  contenedor.querySelector('h1').focus({ preventScroll: true });
  refrescar();
}
