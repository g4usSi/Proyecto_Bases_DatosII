/* Rutas con hash: StaticFiles no tiene respaldo a index.html y asi no hace falta un catch-all. */

export function rutaActual() {
  const crudo = location.hash.replace(/^#\/?/, '');
  const [camino, consulta] = crudo.split('?');
  const partes = camino.split('/').filter(Boolean);
  return { vista: partes[0] || '', args: partes.slice(1), params: Object.fromEntries(new URLSearchParams(consulta || '')) };
}

export function enlace(vista, params) {
  const limpios = Object.entries(params || {}).filter(([, v]) => v != null && v !== '');
  const consulta = new URLSearchParams(limpios).toString();
  return `#/${vista}${consulta ? `?${consulta}` : ''}`;
}

export const irA = (vista, params) => { location.hash = enlace(vista, params); };

/* Filtros en la URL sin registrar otra entrada de historial ni redibujar. */
export function reflejar(vista, params) {
  history.replaceState(null, '', enlace(vista, params));
}
