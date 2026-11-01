/* Sesion en sessionStorage: muere con la pestana y nunca va a localStorage (docs/frontend.md). */

const CLAVE = 'historiales.sesion';

function leer() {
  try {
    return JSON.parse(sessionStorage.getItem(CLAVE));
  } catch {
    return null;
  }
}

export const sesion = {
  token: null,
  vence: 0,
  usuario: null,

  cargar() {
    const guardada = leer();
    if (guardada && guardada.vence > Date.now()) Object.assign(this, guardada);
    else this.limpiar();
    return Boolean(this.token);
  },

  /* Recibe la respuesta de login o de cambiar-contrasena (LoginResponse). */
  iniciar({ access_token: token, expires_in: duracion, usuario }) {
    this.token = token;
    this.vence = Date.now() + duracion * 1000;
    this.usuario = usuario;
    this.guardar();
  },

  actualizarUsuario(usuario) {
    this.usuario = usuario;
    this.guardar();
  },

  guardar() {
    try {
      sessionStorage.setItem(CLAVE, JSON.stringify({ token: this.token, vence: this.vence, usuario: this.usuario }));
    } catch {
      /* Sin almacenamiento la sesion dura hasta recargar. */
    }
  },

  limpiar() {
    this.token = null;
    this.vence = 0;
    this.usuario = null;
    try {
      sessionStorage.removeItem(CLAVE);
    } catch {
      /* Nada que limpiar. */
    }
  },

  minutosRestantes() {
    return Math.max(0, Math.ceil((this.vence - Date.now()) / 60000));
  },

  tiene(permiso) {
    return Boolean(this.usuario?.permisos?.includes(permiso));
  },
};
