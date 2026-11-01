/* Marco de la aplicacion: tema por institucion, navegacion por permisos y datos de la sesion. */
import { sesion } from '../sesion.js';
import { entidad, textoRol } from '../catalogos.js';
import { enlace } from '../enrutador.js';
import { h, ic, marca } from '../ui/dom.js';
import { chip } from '../ui/componentes.js';
import { abrirCambioDeClave } from './acceso.js';

const PLATAFORMA = { tema: 'plataforma', nombre: 'Administración general', emblema: 'shield-check' };

export const temaDe = (usuario) => (usuario.institucion ? entidad(usuario.institucion) : PLATAFORMA);

function menu(grupos, vistaActual) {
  return h('nav', { class: 'nav', 'aria-label': 'Principal' }, grupos.flatMap((grupo, i) => [
    grupo.titulo && h('div', { class: 'nav-grupo', id: `nav-g${i}`, text: grupo.titulo }),
    h('ul', { 'aria-labelledby': grupo.titulo ? `nav-g${i}` : null }, grupo.items.map((item) => h('li', null,
      h('a', {
        href: enlace(item.ruta),
        'aria-current': item.ruta === vistaActual ? 'page' : null,
      }, ic(item.icono, 18), h('span', { text: item.texto }))))),
  ]));
}

export function chipDeSesion() {
  const minutos = sesion.minutosRestantes();
  return minutos <= 5
    ? chip('aviso', 'timer', `Vence en ${minutos} min`)
    : chip('', 'clock', `Sesión: ${minutos} min`);
}

export function marco({ grupos, vistaActual, titulo, contenido, alSalir, relojSesion }) {
  const usuario = sesion.usuario;
  const tema = temaDe(usuario);
  const nombre = [usuario.nombres, usuario.apellidos].filter(Boolean).join(' ') || tema.nombre;
  const quien = h('div', { class: 'quien' },
    relojSesion,
    h('div', { class: 'quien-datos' }, h('b', { text: nombre }), h('small', { text: textoRol(usuario.rol) })),
    h('button', { class: 'ibtn', type: 'button', title: 'Cambiar mi contraseña', 'aria-label': 'Cambiar mi contraseña', onclick: abrirCambioDeClave }, ic('key-round', 18)),
    h('button', { class: 'btn sec sm', type: 'button', onclick: alSalir }, ic('log-out', 15), 'Cerrar sesión'));
  const saltar = h('a', {
    class: 'saltar', href: '#contenido',
    onclick: (e) => { e.preventDefault(); document.querySelector('main h1')?.focus(); },
    text: 'Saltar al contenido',
  });
  const suelo = h('div', { class: 'suelo', 'aria-hidden': 'true' });

  if (tema.tema === 'laboratorio') {
    return h('div', { class: 'app superior', 'data-tema': tema.tema }, suelo, saltar,
      h('div', { class: 'principal' },
        h('header', { class: 'barra-lab' },
          h('div', { class: 'barra-lab-marca' }, h('span', { class: 'emblema' }, ic(tema.emblema, 20)),
            h('div', null, h('b', { text: tema.nombre }), h('small', { text: 'Historiales' }))),
          menu(grupos, vistaActual), quien),
        contenido));
  }
  return h('div', { class: 'app', 'data-tema': tema.tema }, suelo, saltar,
    h('aside', { class: 'lado' },
      h('div', { class: 'lado-logo' }, marca(), 'Historiales'),
      h('div', { class: 'lado-inst' }, h('span', { class: 'emblema' }, ic(tema.emblema, 20)),
        h('div', null, h('b', { text: tema.nombre }), h('small', { text: usuario.institucion ? 'Tu institución' : 'Las cuatro entidades' }))),
      menu(grupos, vistaActual)),
    h('div', { class: 'principal' },
      h('header', { class: 'arriba' }, h('span', { class: 'ruta muted', text: titulo }), quien),
      contenido));
}
