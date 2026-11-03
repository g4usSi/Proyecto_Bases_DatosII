/* Arranque: decide entre login, cambio obligatorio de contrasena y el modulo de la cuenta. */
import { api, alVencerSesion } from './api.js';
import { sesion } from './sesion.js';
import { rutaActual, irA } from './enrutador.js';
import { h } from './ui/dom.js';
import { aviso_flotante, cabeza, vacio } from './ui/componentes.js';
import { moduloDe } from './modulos/registro.js';
import './modulos/admin.js';
import './modulos/clinica.js';
import { vistaCambioObligatorio, vistaLogin } from './vistas/acceso.js';
import { chipDeSesion, marco, temaDe } from './vistas/marco.js';

const raiz = document.getElementById('raiz');
let vistaPintada = null;
let avisoDado = false;

function mostrar(nodo) {
  raiz.replaceChildren(nodo);
  nodo.querySelector('h1')?.focus({ preventScroll: true });
}

function aLogin(motivo) {
  sesion.limpiar();
  vistaPintada = null;
  document.querySelectorAll('dialog').forEach((d) => d.remove());
  document.documentElement.removeAttribute('data-tema');
  document.title = 'Historiales';
  mostrar(h('div', null, h('div', { class: 'suelo', 'aria-hidden': 'true' }), vistaLogin({ motivo, alEntrar: pintar })));
}

async function salir() {
  try {
    await api('/auth/logout', { metodo: 'POST' });
  } catch {
    /* Se cierra localmente aunque el servidor no responda. */
  }
  location.hash = '';
  aLogin();
}

function vistaSinModulo() {
  return h('main', { class: 'contenido', id: 'contenido' },
    cabeza('Te damos la bienvenida'),
    vacio('layers', 'Tu área todavía no está en esta versión', 'Tu cuenta funciona y tus permisos están activos. Las pantallas de tu institución se agregan en su propia versión de la aplicación.'));
}

function pintar() {
  if (!sesion.token) return aLogin();
  const usuario = sesion.usuario;
  if (usuario.debe_cambiar_contrasena) {
    document.documentElement.dataset.tema = temaDe(usuario).tema;
    return mostrar(h('div', null, h('div', { class: 'suelo', 'aria-hidden': 'true' }),
      vistaCambioObligatorio({ alTerminar: pintar, alSalir: salir })));
  }

  const modulo = moduloDe(usuario);
  const grupos = modulo ? modulo.nav(usuario) : [];
  const primera = grupos[0]?.items[0]?.ruta;
  const { vista, args, params } = rutaActual();
  const permitida = grupos.flatMap((g) => g.items).find((i) => i.ruta === [vista, ...args].join('/'))
    || grupos.flatMap((g) => g.items).find((i) => i.ruta === vista);
  if (modulo && !permitida && primera) {
    irA(primera);
    return undefined;
  }

  const tema = temaDe(usuario);
  document.documentElement.dataset.tema = tema.tema;
  const clave = permitida?.ruta;
  const contenedor = h('main', { class: 'contenido', id: 'contenido' });
  const cambioDePantalla = vistaPintada !== clave;
  if (cambioDePantalla) contenedor.classList.add('entra');
  vistaPintada = clave;
  const titulo = permitida?.texto || 'Inicio';
  document.title = `${titulo}: Historiales`;
  mostrar(marco({
    grupos,
    vistaActual: clave,
    titulo: `${tema.nombre}: ${titulo}`,
    contenido: permitida ? contenedor : vistaSinModulo(),
    alSalir: salir,
    relojSesion: h('span', { id: 'reloj-sesion' }, chipDeSesion()),
  }));
  if (permitida) modulo.vistas[permitida.vista || permitida.ruta]({ contenedor, args, params, repintar: pintar });
  return undefined;
}

/* Reloj: avisa antes de que venza el token, que dura 30 minutos y no se renueva. */
setInterval(() => {
  if (!sesion.token) return;
  if (Date.now() >= sesion.vence) {
    aLogin('vencida');
    return;
  }
  document.getElementById('reloj-sesion')?.replaceChildren(chipDeSesion());
  if (sesion.minutosRestantes() <= 5 && !avisoDado) {
    avisoDado = true;
    aviso_flotante('Tu sesión vence en menos de 5 minutos. Termina lo que estás haciendo.', 'timer');
  }
}, 20000);

alVencerSesion(() => aLogin('vencida'));
window.addEventListener('hashchange', () => {
  if (sesion.token) pintar();
});

sesion.cargar();
if (!sesion.token) {
  aLogin();
} else {
  /* El token se vuelve a validar: la cuenta pudo deshabilitarse desde la ultima visita. */
  api('/auth/me').then((usuario) => {
    sesion.actualizarUsuario(usuario);
    pintar();
  }).catch((error) => {
    if (error.estado !== 401) pintar();
  });
}
