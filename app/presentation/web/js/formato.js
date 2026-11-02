/* Fechas siempre en la zona de la red (HISTORIALES_ZONA_HORARIA), no la del navegador. */
const ZONA = 'America/Guatemala';
const DESFASE = '-06:00';

const fechaHora = new Intl.DateTimeFormat('es-GT', { timeZone: ZONA, dateStyle: 'medium', timeStyle: 'short' });
const fecha = new Intl.DateTimeFormat('es-GT', { timeZone: ZONA, dateStyle: 'medium' });
const quetzales = new Intl.NumberFormat('es-GT', { style: 'currency', currency: 'GTQ' });
const entero = new Intl.NumberFormat('es-GT');
const hora = new Intl.DateTimeFormat('es-GT', { timeZone: ZONA, hour: '2-digit', minute: '2-digit', hour12: false });
const corta = new Intl.DateTimeFormat('es-GT', { timeZone: ZONA, day: 'numeric', month: 'short' });
const larga = new Intl.DateTimeFormat('es-GT', { timeZone: ZONA, weekday: 'long', day: 'numeric', month: 'long' });
const civil = new Intl.DateTimeFormat('es-GT', { timeZone: 'UTC', dateStyle: 'medium' });
const diaIso = new Intl.DateTimeFormat('en-CA', { timeZone: ZONA });

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

export const fHora = (iso) => (iso ? hora.format(new Date(iso)) : '—');
export const fFechaCorta = (iso) => (iso ? corta.format(new Date(iso)) : '—');
export const fDia = (iso) => (iso ? larga.format(new Date(iso)) : '—');
/* Fechas sin hora (AAAA-MM-DD), como el nacimiento: no se convierten de zona o cambiarian de dia. */
export const fFechaCivil = (dia) => (dia ? civil.format(new Date(`${dia}T12:00:00Z`)) : '—');

export const diaDe = (iso) => diaIso.format(new Date(iso));
export const hoyLocal = () => diaIso.format(new Date());
export function sumarDias(dia, n) {
  const fecha = new Date(`${dia}T12:00:00Z`);
  fecha.setUTCDate(fecha.getUTCDate() + n);
  return fecha.toISOString().slice(0, 10);
}
export function lunesDe(dia) {
  const semana = new Date(`${dia}T12:00:00Z`).getUTCDay();
  return sumarDias(dia, -((semana + 6) % 7));
}
/* Valor de <input type=datetime-local> con la zona que exige la API. */
export const conZona = (local) => `${local}:00${DESFASE}`;

export function fEdad(nacimiento) {
  if (!nacimiento) return '—';
  const [ay, am, ad] = hoyLocal().split('-').map(Number);
  const [ny, nm, nd] = nacimiento.split('-').map(Number);
  const meses = (ay - ny) * 12 + (am - nm) - (ad < nd ? 1 : 0);
  if (meses < 24) return meses === 1 ? '1 mes' : `${Math.max(meses, 0)} meses`;
  const anos = Math.floor(meses / 12);
  return `${anos} años`;
}
