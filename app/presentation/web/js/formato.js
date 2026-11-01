/* Fechas siempre en la zona de la red (HISTORIALES_ZONA_HORARIA), no la del navegador. */
const ZONA = 'America/Guatemala';
const DESFASE = '-06:00';

const fechaHora = new Intl.DateTimeFormat('es-GT', { timeZone: ZONA, dateStyle: 'medium', timeStyle: 'short' });
const fecha = new Intl.DateTimeFormat('es-GT', { timeZone: ZONA, dateStyle: 'medium' });
const quetzales = new Intl.NumberFormat('es-GT', { style: 'currency', currency: 'GTQ' });
const entero = new Intl.NumberFormat('es-GT');

export const fFechaHora = (iso) => (iso ? fechaHora.format(new Date(iso)) : '—');
export const fFecha = (iso) => (iso ? fecha.format(new Date(iso)) : '—');
export const fMoneda = (texto) => (texto == null ? '—' : quetzales.format(Number(texto)));
export const fEntero = (n) => (n == null ? '—' : entero.format(n));

/* Convierte el valor de <input type=date> al limite del dia local, con zona como exige la API. */
export const inicioDeDia = (dia) => (dia ? `${dia}T00:00:00${DESFASE}` : null);
export function finDeDia(dia) {
  if (!dia) return null;
  const siguiente = new Date(`${dia}T12:00:00Z`);
  siguiente.setUTCDate(siguiente.getUTCDate() + 1);
  return `${siguiente.toISOString().slice(0, 10)}T00:00:00${DESFASE}`;
}

export const plural = (n, uno, varios) => `${entero.format(n)} ${n === 1 ? uno : varios}`;
export const nombreDe = (p) => `${p.nombres} ${p.apellidos}`.trim();
