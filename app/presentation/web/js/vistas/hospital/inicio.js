/* Inicio del Hospital General: ocupacion, emergencias, citas de hoy y, con pagos:ver, los cobros.
   Cada bloque falla por separado: un servicio caido no oculta los demas. */
import { api } from '../../api.js';
import { sesion } from '../../sesion.js';
import { enlace } from '../../enrutador.js';
import { fEntero, fMoneda } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import { cabeza, cargando, chip, cifras, estadoDeError } from '../../ui/componentes.js';
import { ESTADOS_CITA } from '../clinica/comun.js';
import { lectura } from '../clinica/ficha.js';
import { duracion, ESTADOS_CAMA, horasDesde } from './comun.js';
import { abrirIngreso } from './ingreso.js';

const papel = (titulo, enlaceTexto, ruta, ...contenido) => h('section', { class: 'papel pila-s' },
  h('div', { class: 'papel-cab' }, h('h3', { text: titulo }), ruta && h('a', { class: 'enlace', href: enlace(ruta), text: enlaceTexto })),
  ...contenido);

function barraCamas(porEstado, total) {
  return h('div', { class: 'pila-s' },
    h('div', { class: 'barra-estados', role: 'img', 'aria-label': Object.entries(ESTADOS_CAMA).map(([k, e]) => `${e.texto}: ${porEstado[k] || 0}`).join(', ') },
      Object.keys(ESTADOS_CAMA).filter((k) => porEstado[k]).map((k) => h('i', { class: k, estilo: { width: `${(porEstado[k] / Math.max(total, 1)) * 100}%` } }))),
    h('div', { class: 'leyenda-estados' }, Object.entries(ESTADOS_CAMA).map(([k, e]) => h('span', null, h('i', { class: k }), `${e.texto}: ${fEntero(porEstado[k] || 0)}`))));
}

export async function vistaInicio({ contenedor, repintar }) {
  const clinico = sesion.tiene('historiales:leer');
  const zona = h('div', { class: 'pila', 'aria-live': 'polite' }, cargando(6));
  contenedor.append(cabeza('Inicio', 'Así está el hospital ahora.'), zona);

  const [resumen, emergencias, departamentos, cobros] = await Promise.all([
    lectura(api('/hospital/resumen')),
    clinico ? lectura(api('/ingresos', { params: { tipo: 'emergencia', abiertos: true, limite: 100 } })) : null,
    lectura(api('/departamentos')),
    sesion.tiene('pagos:ver') ? lectura(api('/cobros/resumen')) : null,
  ]);
  if (resumen.error) {
    zona.replaceChildren(estadoDeError(resumen.error, repintar));
    return;
  }
  const r = resumen.valor;
  const libres = r.camas_por_estado.disponible || 0;
  const citas = Object.values(r.citas_hoy_por_estado).reduce((s, n) => s + n, 0);

  const bloques = [
    cifras([
      { etiqueta: 'Ocupación', valor: `${Math.round(r.ocupacion)} %`, nota: `${fEntero(libres)} ${libres === 1 ? 'cama libre' : 'camas libres'} de ${fEntero(r.camas_total)}`, clase: r.ocupacion >= 90 ? 'aviso' : '' },
      { etiqueta: 'Emergencias activas', valor: fEntero(r.emergencias_abiertas), clase: r.emergencias_abiertas ? 'crit' : '' },
      { etiqueta: 'Ingresos hoy', valor: fEntero(r.ingresos_hoy), nota: `${fEntero(r.ingresos_abiertos)} ${r.ingresos_abiertos === 1 ? 'internado' : 'internados'}` },
      { etiqueta: 'Altas hoy', valor: fEntero(r.altas_hoy) },
    ]),
  ];

  const izquierda = [];
  if (emergencias) {
    izquierda.push(papel('Emergencias activas', 'Ver todas', 'emergencias',
      emergencias.error ? estadoDeError(emergencias.error) : (emergencias.valor.length
        ? h('div', { class: 'pila-s' }, [...emergencias.valor].sort((a, b) => a.ingreso_en.localeCompare(b.ingreso_en)).slice(0, 5).map((ing) => h('button', {
          class: 'fila-emergencia', type: 'button', onclick: () => abrirIngreso(ing, { alCambiar: repintar }),
        }, h('b', { class: 'emergencia-cama-chica', text: ing.cama }),
        h('span', { class: 'ajustar' }, h('b', { text: ing.nombre_paciente }), h('small', { class: 'hint bloque', text: ing.motivo })),
        h('span', { class: horasDesde(ing.ingreso_en) >= 4 ? 'texto-aviso' : 'hint', text: duracion(ing.ingreso_en) }))))
        : h('p', { class: 'muted', text: 'No hay emergencias activas.' }))));
  }
  izquierda.push(papel('Citas de hoy', 'Ver agenda', sesion.tiene('citas:leer') && 'agenda',
    citas
      ? h('div', { class: 'etiquetas' }, Object.entries(r.citas_hoy_por_estado).filter(([, n]) => n).map(([k, n]) => {
        const e = ESTADOS_CITA[k] || { clase: '', texto: k };
        return chip(e.clase, e.icono, `${e.texto}: ${fEntero(n)}`);
      }))
      : h('p', { class: 'muted', text: 'No hay citas para hoy.' })));

  const derecha = [papel('Camas', 'Ver camas', 'camas', barraCamas(r.camas_por_estado, r.camas_total))];
  if (!departamentos.error && departamentos.valor.length) {
    derecha.push(papel('Disponibilidad por área', null, null, h('div', { class: 'cargas' }, departamentos.valor.map((d) => h('div', { class: 'carga' },
      h('span', { text: d.nombre }),
      h('div', { class: 'medida', role: 'img', 'aria-label': `${d.camas_disponibles ?? 0} de ${d.camas ?? 0} camas libres` },
        h('i', { estilo: { width: `${((d.camas_disponibles ?? 0) / Math.max(d.camas ?? 0, 1)) * 100}%` } })),
      h('span', { class: 'hint cifra-tabular', text: `${d.camas_disponibles ?? 0} de ${d.camas ?? 0} libres` }))))));
  }
  if (cobros) {
    derecha.push(papel('Cobros', 'Ver pagos', 'pagos', cobros.error ? estadoDeError(cobros.error) : h('dl', { class: 'lista-datos' },
      h('dt', { text: 'Saldo pendiente' }), h('dd', { class: 'num', text: fMoneda(cobros.valor.saldo_pendiente) }),
      h('dt', { text: 'Cobrado hoy' }), h('dd', { class: 'num', text: fMoneda(cobros.valor.cobrado_hoy) }),
      h('dt', { text: 'Cobros abiertos' }), h('dd', { class: 'num', text: fEntero(cobros.valor.cobros_por_estado.abierto || 0) }))));
  }

  bloques.push(h('div', { class: 'dos-col' }, h('div', { class: 'pila' }, izquierda), h('div', { class: 'pila' }, derecha)));
  zona.replaceChildren(...bloques);
  if (!emergencias && !clinico) zona.append(h('p', { class: 'hint' }, ic('lock', 14), ' Las emergencias y los ingresos se muestran al personal con acceso a historiales.'));
}
