/* Cliente HTTP: agrega el token y traduce los errores de la API a mensajes para la persona. */
import { sesion } from './sesion.js';

const BASE = '/api/v1';

const POR_ESTADO = {
  403: 'No tienes permiso para esta acción.',
  404: 'No se encontró lo que buscas. Es posible que ya no exista.',
  409: 'La operación entra en conflicto con el estado actual.',
  422: 'Revisa los datos marcados.',
  501: 'Esta función todavía no está disponible para tu institución.',
  503: 'El servicio de datos no está disponible. Intenta más tarde.',
};

const CAMPO_INVALIDO = {
  missing: 'Este campo es obligatorio.',
  string_too_short: 'Es demasiado corto.',
  string_too_long: 'Es demasiado largo.',
  greater_than_equal: 'El valor es demasiado bajo.',
  less_than_equal: 'El valor es demasiado alto.',
  enum: 'Elige una opción válida.',
  literal_error: 'Elige una opción válida.',
  extra_forbidden: 'Este dato no se admite aquí.',
};

/* Los mensajes de dominio se escriben sin tildes en el backend. */
const TILDES = [
  [/contrasena/gi, (m) => (m[0] === 'C' ? 'Contraseña' : 'contraseña')],
  [/institucion/gi, (m) => (m[0] === 'I' ? 'Institución' : 'institución')],
  [/\bsesion\b/gi, (m) => (m[0] === 'S' ? 'Sesión' : 'sesión')],
  [/\bnumeros\b/g, 'números'], [/\bsimbolos\b/g, 'símbolos'], [/\bClinica\b/g, 'Clínica'],
  [/\bclinicos\b/g, 'clínicos'], [/\bvalido\b/g, 'válido'], [/\binvalido\b/g, 'inválido'],
  [/\bInvalido\b/g, 'Inválido'], [/\barea\b/g, 'área'], [/\bareas\b/g, 'áreas'],
  [/\boperacion\b/g, 'operación'], [/\badministracion\b/g, 'administración'],
];
const conTildes = (texto) => TILDES.reduce((t, [patron, sustituto]) => t.replace(patron, sustituto), texto);

export class ErrorApi extends Error {
  constructor(estado, mensaje, campos = null) {
    super(mensaje);
    this.estado = estado;
    this.campos = campos;
  }
}

function aErrorApi(estado, cuerpo) {
  const detalle = cuerpo?.detail;
  if (Array.isArray(detalle)) {
    const campos = {};
    for (const item of detalle) {
      const nombre = [...(item.loc || [])].reverse().find((p) => typeof p === 'string' && p !== 'body' && p !== 'query');
      if (nombre) campos[nombre] = CAMPO_INVALIDO[item.type] || 'Revisa este campo.';
    }
    return new ErrorApi(estado, POR_ESTADO[422], campos);
  }
  const propio = typeof detalle === 'string' && estado !== 503 && estado !== 501 ? conTildes(detalle) : null;
  return new ErrorApi(estado, propio || POR_ESTADO[estado] || 'No se pudo completar la operación.');
}

let alVencer = () => {};
export const alVencerSesion = (fn) => { alVencer = fn; };

export async function api(ruta, { metodo = 'GET', cuerpo, params, anonimo = false } = {}) {
  const url = new URL(BASE + ruta, location.origin);
  for (const [clave, valor] of Object.entries(params || {})) {
    if (valor == null || valor === '') continue;
    for (const v of Array.isArray(valor) ? valor : [valor]) url.searchParams.append(clave, v);
  }
  const cabeceras = {};
  if (cuerpo !== undefined) cabeceras['Content-Type'] = 'application/json';
  if (!anonimo && sesion.token) cabeceras.Authorization = `Bearer ${sesion.token}`;

  let respuesta;
  try {
    respuesta = await fetch(url, {
      method: metodo,
      headers: cabeceras,
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
      cache: 'no-store',
    });
  } catch {
    throw new ErrorApi(0, 'No se pudo conectar con el servidor. Revisa tu conexión e intenta de nuevo.');
  }
  if (respuesta.status === 204) return null;
  const datos = await respuesta.json().catch(() => null);
  if (respuesta.ok) return datos;
  if (respuesta.status === 401 && !anonimo) {
    alVencer();
    throw new ErrorApi(401, 'Tu sesión venció. Inicia sesión de nuevo.');
  }
  throw aErrorApi(respuesta.status, datos);
}
