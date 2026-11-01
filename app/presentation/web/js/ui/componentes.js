/* Componentes compartidos por todas las instituciones. */
import { h, ic } from './dom.js';
import { ErrorApi } from '../api.js';

export const chip = (clase, icono, texto) =>
  h('span', { class: `chip ${clase}` }, icono && ic(icono, 14), texto);

export const aviso = (clase, icono, ...contenido) =>
  h('div', { class: `aviso-caja ${clase}`, role: clase === 'crit' ? 'alert' : 'status' }, ic(icono, 18), h('div', null, contenido));

export const vacio = (icono, titulo, texto, accion) =>
  h('div', { class: 'vacio' }, h('span', { class: 'ico' }, ic(icono, 22)), h('h3', { text: titulo }), texto && h('p', { text: texto }), accion);

export const cargando = (filas = 4) =>
  h('div', { class: 'cargando', 'aria-busy': 'true', 'aria-label': 'Cargando' }, h('i', { class: 'alto' }),
    Array.from({ length: filas }, (_, i) => h('i', { estilo: { width: `${92 - i * 12}%` } })));

export const cabeza = (titulo, texto, accion) =>
  h('div', { class: 'cabeza' },
    h('div', null, h('h1', { text: titulo, tabindex: '-1' }), texto && h('p', { text: texto })),
    accion && h('div', { class: 'fila' }, accion));

export const cifras = (lista) =>
  h('div', { class: 'cifras' }, lista.filter(Boolean).map(({ etiqueta, valor, nota, clase }) =>
    h('div', { class: `cifra ${clase || ''}` }, h('b', { text: String(valor) }), h('span', { text: etiqueta }), nota && h('small', { text: nota }))));

export function segmento(etiqueta, opciones, actual, alElegir) {
  return h('div', { class: 'seg', role: 'group', 'aria-label': etiqueta },
    opciones.map(({ valor, texto }) => h('button', {
      type: 'button',
      'aria-pressed': valor === actual ? 'true' : 'false',
      onclick: () => alElegir(valor),
      text: texto,
    })));
}

export const tabla = (columnas, filas) =>
  h('div', { class: 'tabla', tabindex: '0', role: 'region', 'aria-label': 'Tabla con desplazamiento' },
    h('table', null,
      h('thead', null, h('tr', null, columnas.filter(Boolean).map((c) => (typeof c === 'string'
        ? h('th', { scope: 'col', text: c })
        : h('th', { scope: 'col', class: c.clase, text: c.texto }))))),
      h('tbody', null, filas)));

/* ---------- Campos ---------- */
export function campo(etiqueta, control, { ayuda, opcional, id } = {}) {
  const idControl = id || control.id || control.querySelector?.('input,select,textarea')?.id;
  const error = h('div', { class: 'error-campo', role: 'alert', hidden: true });
  const nodo = h('div', { class: 'campo' },
    h('label', { for: idControl }, etiqueta, opcional && h('small', { text: ' (opcional)' })),
    control,
    ayuda && h('span', { class: 'hint', text: ayuda }),
    error);
  const entrada = control.matches?.('input,select,textarea') ? control : control.querySelector?.('input,select,textarea');
  nodo.marcar = (mensaje) => {
    error.replaceChildren(...(mensaje ? [ic('circle-alert', 15), h('span', { text: mensaje })] : []));
    error.hidden = !mensaje;
    entrada?.classList.toggle('mal', Boolean(mensaje));
    if (entrada) entrada.setAttribute('aria-invalid', mensaje ? 'true' : 'false');
  };
  return nodo;
}

export const entrada = (id, opciones = {}) => h('input', {
  class: 'in', id, type: 'text', autocomplete: 'off', ...opciones,
});

export const seleccion = (id, opciones, atributos = {}) => {
  const el = h('select', { class: 'in', id, ...atributos },
    opciones.map(({ valor, texto, apagada }) => h('option', { value: valor, disabled: apagada, text: texto })));
  if (atributos.value != null) el.value = atributos.value;
  return el;
};

export function claveConOjo(id, atributos = {}) {
  const control = h('input', { class: 'in', id, type: 'password', ...atributos });
  const ojo = h('button', {
    class: 'ibtn', type: 'button', 'aria-label': 'Mostrar contraseña', 'aria-pressed': 'false',
    onclick: () => {
      const mostrar = control.type === 'password';
      control.type = mostrar ? 'text' : 'password';
      ojo.setAttribute('aria-pressed', mostrar ? 'true' : 'false');
      ojo.setAttribute('aria-label', mostrar ? 'Ocultar contraseña' : 'Mostrar contraseña');
      ojo.replaceChildren(ic(mostrar ? 'eye-off' : 'eye', 18));
    },
  }, ic('eye', 18));
  return h('div', { class: 'clave' }, control, ojo);
}

/* Misma politica que app/domain/administracion.py; el servidor sigue siendo quien decide. */
export function problemaDeClave(clave, correo) {
  if (clave.length < 12 || clave.length > 128) return 'Usa entre 12 y 128 caracteres.';
  if (clave.trim() !== clave) return 'No puede empezar ni terminar con espacios.';
  if (!/\p{L}/u.test(clave) || /^\p{L}+$/u.test(clave)) return 'Combina letras con números o símbolos.';
  if (new Set(clave).size < 5) return 'Es demasiado repetitiva.';
  const usuario = (correo || '').split('@')[0].toLowerCase();
  if (usuario.length >= 4 && clave.toLowerCase().includes(usuario)) return 'No puede contener tu correo.';
  return null;
}

export function medidorDeClave(control) {
  const barra = h('div', { class: 'medidor', 'aria-hidden': 'true', 'data-n': '0' }, h('i'), h('i'), h('i'), h('i'));
  const actualizar = () => {
    const t = control.value;
    let n = 0;
    if (t.length >= 12) n += 1;
    if (t.length >= 16) n += 1;
    if (/[a-z]/.test(t) && /[A-Z]/.test(t)) n += 1;
    if (/\d/.test(t) && /[^A-Za-z0-9]/.test(t)) n += 1;
    if (t.length < 12) n = Math.min(n, 1);
    barra.dataset.n = String(t ? Math.max(n, 1) : 0);
  };
  control.addEventListener('input', actualizar);
  return barra;
}

/* ---------- Errores ---------- */
/* Muestra el error junto a su campo si la API lo identifico; si no, en el aviso general. */
export function mostrarErrorDeFormulario(error, campos, zonaAviso) {
  zonaAviso.replaceChildren();
  let ubicados = 0;
  for (const [nombre, mensaje] of Object.entries(error.campos || {})) {
    if (campos[nombre]) { campos[nombre].marcar(mensaje); ubicados += 1; }
  }
  if (!ubicados) zonaAviso.append(aviso('crit', 'circle-alert', h('b', { text: error.message })));
}

export function estadoDeError(error, reintentar) {
  const e = error instanceof ErrorApi ? error : new ErrorApi(0, 'No se pudo completar la operación.');
  const iconos = { 403: 'lock', 404: 'inbox', 501: 'info', 503: 'server-off', 0: 'server-off' };
  const clase = e.estado === 403 || e.estado === 404 || e.estado === 501 ? 'info' : 'crit';
  return aviso(clase, iconos[e.estado] || 'circle-alert',
    h('b', { text: e.message }),
    reintentar && [' ', h('button', { class: 'enlace', type: 'button', onclick: reintentar, text: 'Intentar de nuevo' })]);
}

/* ---------- Dialogos sobre <dialog>: foco atrapado, Esc y fondo inerte los da el navegador ---------- */
function cerrarConSalida(dialogo) {
  if (!dialogo.open || dialogo.classList.contains('sale')) return;
  dialogo.classList.add('sale');
  const fin = () => { dialogo.close(); dialogo.remove(); };
  const reducido = matchMedia('(prefers-reduced-motion: reduce)').matches;
  setTimeout(fin, reducido ? 0 : 200);
}

function abrir(dialogo, { fijo, enfocar } = {}) {
  dialogo.addEventListener('cancel', (e) => {
    e.preventDefault();
    if (!fijo) cerrarConSalida(dialogo);
  });
  dialogo.addEventListener('click', (e) => {
    if (e.target === dialogo && !fijo) cerrarConSalida(dialogo);
  });
  document.body.append(dialogo);
  dialogo.showModal();
  (enfocar || dialogo.querySelector('input:not([disabled]),select:not([disabled]),textarea'))?.focus();
  return { cerrar: () => cerrarConSalida(dialogo), nodo: dialogo };
}

export function lateral(titulo, cuerpo, pie) {
  const dialogo = h('dialog', { class: 'lateral', 'aria-label': titulo },
    h('div', { class: 'lateral-int' },
      h('header', null, h('h2', { text: titulo }), h('button', { class: 'ibtn', type: 'button', 'aria-label': 'Cerrar', onclick: () => cerrarConSalida(dialogo) }, ic('x', 20))),
      h('div', { class: 'cuerpo' }, cuerpo),
      pie && h('footer', null, pie)));
  return abrir(dialogo);
}

export function modal(titulo, cuerpo, pie, { fijo } = {}) {
  const dialogo = h('dialog', { class: 'modal', 'aria-label': titulo },
    h('div', { class: 'modal-int' }, h('h2', { text: titulo }), cuerpo, h('footer', null, pie)));
  /* El foco inicial nunca cae en la accion destructiva. */
  return abrir(dialogo, { fijo, enfocar: dialogo.querySelector('footer button') });
}

export function confirmar({ titulo, cuerpo, accion, peligro, alConfirmar }) {
  const zona = h('div');
  const boton = h('button', { class: `btn ${peligro ? 'peligro solido' : ''}`, type: 'button', text: accion });
  const m = modal(titulo, h('div', { class: 'pila-s' }, cuerpo, zona), [
    h('button', { class: 'btn sec', type: 'button', text: 'Volver', onclick: () => m.cerrar() }),
    boton,
  ]);
  boton.addEventListener('click', async () => {
    boton.disabled = true;
    try {
      await alConfirmar();
      m.cerrar();
    } catch (error) {
      boton.disabled = false;
      zona.replaceChildren(aviso('crit', 'circle-alert', h('b', { text: error.message })));
    }
  });
  return m;
}

export function aviso_flotante(mensaje, icono = 'circle-check') {
  const nodo = h('div', { class: 'toast', role: 'status', popover: 'manual' }, ic(icono, 18), h('span', { text: mensaje }));
  document.body.append(nodo);
  nodo.showPopover?.();
  setTimeout(() => {
    nodo.classList.add('sale');
    setTimeout(() => nodo.remove(), 200);
  }, 3200);
}

export function copiar(texto, mensaje) {
  const fallo = () => aviso_flotante('No se pudo copiar. Selecciónalo y cópialo a mano.', 'circle-alert');
  try {
    navigator.clipboard.writeText(texto).then(() => aviso_flotante(mensaje, 'copy'), fallo);
  } catch {
    fallo();
  }
}
