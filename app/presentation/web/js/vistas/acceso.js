/* Inicio de sesion y cambio de contrasena. */
import { api, ErrorApi } from '../api.js';
import { sesion } from '../sesion.js';
import { ENTIDADES } from '../catalogos.js';
import { h, ic, marca } from '../ui/dom.js';
import { aviso, aviso_flotante, campo, claveConOjo, entrada, lateral, medidorDeClave, problemaDeClave } from '../ui/componentes.js';

const logo = () => h('div', { class: 'acceso-logo' }, marca(), 'Historiales');

export function vistaLogin({ motivo, alEntrar }) {
  const zona = h('div');
  if (motivo === 'vencida') {
    zona.append(aviso('info', 'clock', h('b', { text: 'Tu sesión venció. ' }), 'Inicia sesión de nuevo y volverás a la pantalla en la que estabas.'));
  }
  const correo = entrada('lg-correo', { type: 'email', autocomplete: 'username', placeholder: 'nombre@institucion.org', required: true, maxlength: 254 });
  const clave = claveConOjo('lg-clave', { autocomplete: 'current-password', required: true, maxlength: 1024 });
  const boton = h('button', { class: 'btn', type: 'submit' }, ic('log-in', 18), 'Iniciar sesión');
  const form = h('form', {
    novalidate: true,
    onsubmit: async (e) => {
      e.preventDefault();
      zona.replaceChildren();
      const control = clave.querySelector('input');
      if (!correo.value.trim() || !control.value) {
        zona.append(aviso('crit', 'circle-alert', h('b', { text: 'Escribe tu correo y tu contraseña.' })));
        return;
      }
      boton.disabled = true;
      try {
        const respuesta = await api('/auth/login', {
          metodo: 'POST', anonimo: true,
          cuerpo: { correo: correo.value.trim(), password: control.value },
        });
        sesion.iniciar(respuesta);
        alEntrar();
      } catch (error) {
        boton.disabled = false;
        control.value = '';
        zona.append(errorDeLogin(error));
      }
    },
  },
  campo('Correo profesional', correo),
  campo('Contraseña', clave),
  boton);

  return h('div', { class: 'acceso' },
    h('section', { class: 'acceso-panel' },
      logo(),
      h('div', null,
        h('h1', { text: 'Iniciar sesión', tabindex: '-1' }),
        h('p', { class: 'muted', text: 'Entra con tu correo profesional. Tu institución se asigna automáticamente.' })),
      zona, form,
      h('p', { class: 'hint', text: 'Las cuentas las crea la administración de cada institución.' })),
    h('div', { class: 'cuatro', 'aria-hidden': 'true' },
      ENTIDADES.map((e) => h('div', null, ic(e.emblema, 30), h('b', { text: e.nombre })))));
}

function errorDeLogin(error) {
  if (error.estado === 401 || error.estado === 422) {
    return aviso('crit', 'circle-alert', h('b', { text: 'Correo o contraseña inválidos. ' }), 'Revísalos e inténtalo otra vez.');
  }
  if (error.estado === 503) {
    return aviso('aviso', 'server-off', h('b', { text: 'El inicio de sesión no está disponible. ' }), 'Intenta de nuevo en unos minutos.');
  }
  return aviso('crit', 'server-off', h('b', { text: error instanceof ErrorApi ? error.message : 'No se pudo iniciar sesión.' }));
}

function formularioClave({ alTerminar, textoBoton, correo }) {
  const zona = h('div');
  const actual = claveConOjo('cc-actual', { autocomplete: 'current-password', maxlength: 1024 });
  const nueva = claveConOjo('cc-nueva', { autocomplete: 'new-password', maxlength: 128 });
  const repetir = claveConOjo('cc-repetir', { autocomplete: 'new-password', maxlength: 128 });
  const cActual = campo('Contraseña actual', actual);
  const cNueva = campo('Contraseña nueva', nueva, { ayuda: 'Entre 12 y 128 caracteres, con letras y números o símbolos.' });
  const cRepetir = campo('Repite la contraseña nueva', repetir);
  const boton = h('button', { class: 'btn', type: 'submit', text: textoBoton });
  const valor = (nodo) => nodo.querySelector('input').value;
  return h('form', {
    class: 'pila',
    novalidate: true,
    onsubmit: async (e) => {
      e.preventDefault();
      zona.replaceChildren();
      [cActual, cNueva, cRepetir].forEach((c) => c.marcar(null));
      let bien = true;
      if (!valor(actual)) { cActual.marcar('Escribe tu contraseña actual.'); bien = false; }
      const problema = problemaDeClave(valor(nueva), correo);
      if (problema) { cNueva.marcar(problema); bien = false; }
      if (valor(nueva) !== valor(repetir)) { cRepetir.marcar('Las contraseñas no coinciden.'); bien = false; }
      if (!bien) return;
      boton.disabled = true;
      try {
        const respuesta = await api('/auth/cambiar-contrasena', {
          metodo: 'POST',
          cuerpo: { contrasena_actual: valor(actual), contrasena_nueva: valor(nueva) },
        });
        sesion.iniciar(respuesta);
        alTerminar();
      } catch (error) {
        boton.disabled = false;
        if (error.estado !== 401) zona.append(aviso('crit', 'circle-alert', h('b', { text: error.message })));
      }
    },
  }, zona, cActual, cNueva, medidorDeClave(nueva.querySelector('input')), cRepetir, boton);
}

/* Tras un alta o un restablecimiento: hay que elegir contrasena antes de entrar. */
export function vistaCambioObligatorio({ alTerminar, alSalir }) {
  return h('div', { class: 'pantalla-sola' },
    h('section', { class: 'acceso-panel' },
      logo(),
      h('div', null,
        h('h1', { text: 'Elige tu contraseña', tabindex: '-1' }),
        h('p', { class: 'muted', text: 'La que tienes te la entregó la administración. Cámbiala por una que solo tú conozcas para continuar.' })),
      formularioClave({ alTerminar, textoBoton: 'Guardar y continuar' }),
      h('button', { class: 'btn tenue', type: 'button', onclick: alSalir, text: 'Cerrar sesión' })));
}

export function abrirCambioDeClave() {
  const panel = lateral('Cambiar mi contraseña', [
    aviso('info', 'info', 'Tus otras sesiones se cerrarán. Esta seguirá abierta.'),
    formularioClave({
      textoBoton: 'Guardar contraseña',
      alTerminar: () => {
        panel.cerrar();
        aviso_flotante('Contraseña actualizada');
      },
    }),
  ]);
}
