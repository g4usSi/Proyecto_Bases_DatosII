/* Odontograma interactivo con numeracion FDI, portado del mockup aprobado.
   Dibujo en SVG con atributos: la CSP prohibe estilos en linea en el marcado. */
import { api } from '../../api.js';
import { sesion } from '../../sesion.js';
import { fFechaHora } from '../../formato.js';
import { h } from '../../ui/dom.js';
import { aviso_flotante, segmento, vacio } from '../../ui/componentes.js';
import { areaTexto, nombreProfesional } from './comun.js';

const NS = 'http://www.w3.org/2000/svg';

function sv(etiqueta, atributos, ...hijos) {
  const el = document.createElementNS(NS, etiqueta);
  for (const [clave, valor] of Object.entries(atributos || {})) {
    if (valor == null || valor === false) continue;
    if (clave === 'text') el.textContent = valor;
    else el.setAttribute(clave, valor === true ? '' : valor);
  }
  for (const hijo of hijos.flat()) if (hijo) el.append(hijo);
  return el;
}

export const REQUIEREN_ATENCION = ['caries', 'fractura', 'extraccion_indicada'];
export const piezasPorNumero = (respuesta) => Object.fromEntries(respuesta.piezas.map((p) => [p.pieza, p]));

const ESTADOS = [
  ['sana', 'Sana', '', '#3E9B5F', '#FFFFFF'], ['caries', 'Caries', 'C', '#D93025', '#FFFFFF'], ['obturada', 'Obturada', 'O', '#2F6FDE', '#FFFFFF'],
  ['corona', 'Corona', 'Co', '#C9971A', '#1F272D'], ['endodoncia', 'Endodoncia', 'E', '#7B3FBF', '#FFFFFF'], ['sellante', 'Sellante', 'S', '#5CC4EC', '#0E2F3B'],
  ['fractura', 'Fractura', 'F', '#F08A24', '#2A1500'], ['protesis', 'Prótesis', 'P', '#5A6F85', '#FFFFFF'], ['implante', 'Implante', 'I', '#4A4F57', '#FFFFFF'],
  ['extraccion_indicada', 'Extracción indicada', 'X', '#D93025', '#FFFFFF'], ['ausente', 'Ausente', '—', '#D5DADF', '#3A444D'], ['en_erupcion', 'En erupción', '↑', '#F2D13A', '#2B2400'],
];
const MAPA = Object.fromEntries(ESTADOS.map(([k, l, m, c, i]) => [k, { k, l, m, c, i }]));
const SUPERFICIES = ['oclusal', 'incisal', 'mesial', 'distal', 'vestibular', 'lingual', 'palatino'];
const CORTO = { sana: 'Sana', caries: 'Caries', obturada: 'Obtur.', corona: 'Corona', endodoncia: 'Endod.', sellante: 'Sellante', fractura: 'Fractura', protesis: 'Prótesis', implante: 'Implante', extraccion_indicada: 'Extrac.', ausente: 'Ausente', en_erupcion: 'Erupción' };
const SIGLA = { oclusal: 'O', incisal: 'I', mesial: 'M', distal: 'D', vestibular: 'V', lingual: 'L', palatino: 'P' };
const ADULTO_SUP = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28];
const ADULTO_INF = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38];
const TEMPORAL_SUP = [55, 54, 53, 52, 51, 61, 62, 63, 64, 65];
const TEMPORAL_INF = [85, 84, 83, 82, 81, 71, 72, 73, 74, 75];

/* Formas anatomicas simplificadas, vistas de frente (raiz arriba, corona abajo). */
const tipoDiente = (n) => {
  const q = Math.floor(n / 10);
  const u = n % 10;
  if (u <= 2) return 'inc';
  if (u === 3) return 'can';
  if (q >= 5) return 'mol';
  return u <= 5 ? 'pre' : 'mol';
};
const FORMA = {
  inc: { yb: 58, crown: 'M8 26C6 36 5 48 7 55Q8 58 12 58L28 58Q32 58 33 55C35 48 34 36 32 26Z', roots: ['M12 26C13 16 17 6 20 3C23 6 27 16 28 26Z'], canal: ['M20 26V9'] },
  can: { yb: 63, crown: 'M8 26C6 38 7 48 10 54L20 63L30 54C33 48 34 38 32 26Z', roots: ['M12 26C13 14 17 4 20 1C23 4 27 14 28 26Z'], canal: ['M20 26V7'] },
  pre: { yb: 58, crown: 'M7 26C5 38 5 50 8 55Q10 58 14 57L20 54L26 57Q30 58 32 55C35 50 35 38 33 26Z', roots: ['M12 26C12 16 16 9 20 4C24 9 28 16 28 26Z'], canal: ['M20 26V8'] },
  mol: { yb: 58, crown: 'M4 26C1 36 1 50 4 56Q6 59 11 58L15 55L20 58L25 55L29 58Q34 59 36 56C39 50 39 36 36 26Z' },
};
const RAIZ3 = { roots: ['M6 26C6 18 8 9 11 4C13 10 14 18 15 26Z', 'M16 26C17 16 19 9 20 5C21 9 23 16 24 26Z', 'M25 26C26 18 27 10 29 4C32 8 34 18 34 26Z'], canal: ['M10.5 26V10', 'M20 26V10', 'M29.5 26V10'] };
const RAIZ2 = { roots: ['M5 26C5 16 8 9 11 4C15 10 17 18 18 26Z', 'M22 26C23 18 25 10 29 4C32 8 35 16 35 26Z'], canal: ['M11.5 26V10', 'M28.5 26V10'] };
const ALTO_DIENTE = 68;

function diente(num, d, prefijo, volteado) {
  const q = Math.floor(num / 10);
  const superior = [1, 2, 5, 6].includes(q);
  const mesialDerecha = [1, 4, 5, 8].includes(q);
  const tipo = tipoDiente(num);
  const F = tipo === 'mol' ? { ...FORMA[tipo], ...(superior ? RAIZ3 : RAIZ2) } : FORMA[tipo];
  const e = d && MAPA[d.estado];
  const k = e?.k;
  const sups = d?.superficies || [];
  const todo = e && !sups.length;
  const cid = `${prefijo}-${num}`;
  const yb = F.yb;
  const yb2 = yb - 13;
  const G = sv('g');
  const trazo = !e ? '#A9B3BC' : '#5E6B77';
  const rayado = (!e || k === 'ausente') ? '3 2' : null;
  G.append(sv('defs', null, sv('clipPath', { id: cid }, sv('path', { d: F.crown })),
    sv('pattern', { id: `h-${cid}`, width: 4, height: 4, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' },
      sv('line', { x1: 0, y1: 0, x2: 0, y2: 4, stroke: '#5E6B77', 'stroke-width': 1, opacity: 0.55 }))));
  if (k === 'implante') {
    G.append(sv('rect', { x: 16.5, y: 3, width: 7, height: 23, rx: 1.5, fill: '#4A4F57', stroke: '#2B2F35', 'stroke-width': 1 }));
    for (let y = 7; y < 25; y += 4) G.append(sv('line', { x1: 16.5, y1: y, x2: 23.5, y2: y + 2, stroke: '#E3E6EA', 'stroke-width': 1.1 }));
  } else {
    let relleno = '#F1EBDD';
    if (k === 'endodoncia') relleno = '#7B3FBF';
    else if (!e || k === 'ausente') relleno = '#FFFFFF';
    F.roots.forEach((r) => G.append(sv('path', { d: r, fill: relleno, stroke: trazo, 'stroke-width': 1.2, 'stroke-dasharray': (k === 'en_erupcion' || rayado) ? '3 2' : null, 'stroke-linejoin': 'round' })));
    if (k === 'endodoncia') F.canal.forEach((c) => G.append(sv('path', { d: c, stroke: '#fff', 'stroke-width': 1.4, 'stroke-linecap': 'round', fill: 'none' })));
  }
  G.append(sv('path', { d: F.crown, fill: k === 'ausente' ? '#F3F5F7' : '#FFFFFF' }));
  if (e && k !== 'ausente') {
    const corona = sv('g', { 'clip-path': `url(#${cid})` });
    const color = k === 'endodoncia' && todo ? '#E9DDF7' : e.c;
    if (todo) {
      corona.append(sv('rect', { x: 0, y: 0, width: 40, height: 70, fill: color }));
    } else {
      const zonas = [];
      if (sups.includes('oclusal') || sups.includes('incisal')) zonas.push([0, yb2, 40, 20]);
      if (sups.includes('vestibular')) zonas.push([11, 33, 18, yb2 - 33]);
      if (sups.includes('mesial')) zonas.push([mesialDerecha ? 29 : 0, 33, 11, yb2 - 33]);
      if (sups.includes('distal')) zonas.push([mesialDerecha ? 0 : 29, 33, 11, yb2 - 33]);
      if (sups.includes('lingual') || sups.includes('palatino')) zonas.push([0, 26, 40, 7]);
      zonas.forEach(([x, y, w, alto]) => corona.append(sv('rect', { x, y, width: w, height: alto, fill: e.c })));
    }
    const internaTocada = sups.some((s) => s === 'lingual' || s === 'palatino');
    corona.append(sv('rect', { x: 0, y: 26, width: 40, height: 7, fill: `url(#h-${cid})`, opacity: internaTocada ? 0.5 : null }));
    const linea = todo ? '#FFFFFF' : '#5E6B77';
    const opacidad = todo ? 0.5 : 0.55;
    ['M0 33H40', `M0 ${yb2}H40`, `M11 33V${yb2}`, `M29 33V${yb2}`].forEach((l) => corona.append(sv('path', { d: l, stroke: linea, 'stroke-width': 0.8, opacity: opacidad, fill: 'none' })));
    if (k === 'corona') corona.append(sv('rect', { x: 0, y: 26, width: 40, height: 6, fill: '#8A6A0E' }), sv('path', { d: `M0 ${yb - 2}H40`, stroke: '#8A6A0E', 'stroke-width': 1.2 }));
    if (k === 'fractura') {
      const rotura = 'M5 40L13 47L20 38L27 48L35 41';
      corona.append(sv('path', { d: rotura, fill: 'none', stroke: '#fff', 'stroke-width': 3.4, 'stroke-linejoin': 'round' }), sv('path', { d: rotura, fill: 'none', stroke: '#3A1D00', 'stroke-width': 1.5, 'stroke-linejoin': 'round' }));
    }
    if (k === 'extraccion_indicada') {
      [`M5 28L35 ${yb - 2}`, `M35 28L5 ${yb - 2}`].forEach((l) => corona.append(sv('path', { d: l, stroke: '#fff', 'stroke-width': 3.6, fill: 'none' }), sv('path', { d: l, stroke: '#6E140E', 'stroke-width': 1.6, fill: 'none' })));
    }
    G.append(corona);
  }
  G.append(sv('path', { d: F.crown, fill: 'none', stroke: trazo, 'stroke-width': 1.3, 'stroke-dasharray': rayado, 'stroke-linejoin': 'round' }));
  /* Letra de estado, siempre al derecho aunque la arcada este volteada. */
  if (e?.m && k !== 'fractura' && k !== 'extraccion_indicada') {
    const ym = (26 + yb) / 2 - 1;
    const sobreColor = todo && k !== 'endodoncia';
    G.append(sv('g', { transform: `translate(20 ${ym}) ${volteado ? 'scale(1 -1)' : ''}` },
      sv('text', { x: 0, y: 3.5, 'text-anchor': 'middle', 'font-size': e.m.length > 1 ? 9 : 11, 'font-weight': 700, fill: sobreColor ? e.i : '#1F272D', 'paint-order': 'stroke', stroke: sobreColor ? 'none' : '#fff', 'stroke-width': todo ? 0 : 2.5, text: e.m })));
  }
  return G;
}

function geometria(num) {
  const q = Math.floor(num / 10);
  const superior = [1, 2, 5, 6].includes(q);
  const derecha = [1, 4, 5, 8].includes(q);
  return {
    top: superior ? 'vestibular' : 'lingual', bottom: superior ? 'palatino' : 'vestibular',
    left: derecha ? 'distal' : 'mesial', right: derecha ? 'mesial' : 'distal', center: num % 10 <= 3 ? 'incisal' : 'oclusal',
  };
}

function cubo(num, d) {
  const g = geometria(num);
  const e = d && MAPA[d.estado];
  const sups = d?.superficies || [];
  const todo = e && !sups.length;
  const G = sv('g');
  const zonas = { top: 'M0 0L36 0L25 11L11 11Z', bottom: 'M0 36L36 36L25 25L11 25Z', left: 'M0 0L11 11L11 25L0 36Z', right: 'M36 0L25 11L25 25L36 36Z' };
  const trazo = !e ? '#A9B3BC' : '#5E6B77';
  const rayado = !e || e.k === 'ausente' ? '3 2' : null;
  G.append(sv('rect', { x: 0, y: 0, width: 36, height: 36, rx: 5, fill: e && todo ? e.c : '#FFFFFF', stroke: trazo, 'stroke-width': 1.4, 'stroke-dasharray': rayado }));
  const centro = sups.includes('oclusal') || sups.includes('incisal');
  if (e && !todo) {
    Object.entries(zonas).forEach(([zona, trazado]) => { if (sups.includes(g[zona])) G.append(sv('path', { d: trazado, fill: e.c })); });
    if (centro) G.append(sv('rect', { x: 11, y: 11, width: 14, height: 14, fill: e.c }));
  }
  Object.values(zonas).forEach((trazado) => G.append(sv('path', { d: trazado, fill: 'none', stroke: trazo, 'stroke-width': 1 })));
  G.append(sv('rect', { x: 11, y: 11, width: 14, height: 14, fill: 'none', stroke: trazo, 'stroke-width': 1 }));
  if (e?.m) G.append(sv('text', { x: 18, y: 21.6, 'text-anchor': 'middle', 'font-size': e.m.length > 1 ? 8.5 : 10, 'font-weight': 700, fill: todo || centro ? e.i : '#1F272D', text: e.m }));
  if (e?.k === 'extraccion_indicada') G.append(sv('line', { x1: 2, y1: 34, x2: 34, y2: 2, stroke: '#FFFFFF', 'stroke-width': 2.4 }), sv('line', { x1: 2, y1: 34, x2: 34, y2: 2, stroke: '#6E140E', 'stroke-width': 1.2 }));
  return G;
}

const textoSuperficies = (d) => (d?.superficies?.length ? d.superficies.map((s) => SIGLA[s]).join('·') : 'Toda');
const muestra = (e) => h('span', { class: 'muestra', estilo: { background: e.c, color: e.i }, text: e.m || ' ' });

function descripcion(num, d) {
  const e = d && MAPA[d.estado];
  if (!e) return `Pieza ${num}, sin registrar`;
  return `Pieza ${num}, ${e.l.toLowerCase()}${d.superficies?.length ? `, superficies ${d.superficies.join(' y ')}` : ', toda la pieza'}`;
}

export function nodoOdontograma({ paciente, piezas, profesionales, alCambiar }) {
  const soloLectura = paciente.archivado || !sesion.tiene('consultas:registrar');
  const estado = { pieza: null, vista: 'diente', temporal: Object.keys(piezas).some((k) => Number(k) >= 51), sanas: false };
  const carta = h('section', { class: 'od-carta', 'aria-label': 'Odontograma' });
  const panel = h('aside', { class: 'od-panel', 'aria-label': 'Pieza seleccionada' });

  const enfocar = (selector) => setTimeout(() => carta.querySelector(selector)?.focus(), 0);
  function elegir(num) {
    estado.pieza = String(num);
    dibujar();
    pintarPanel();
    enfocar(`[data-pieza="${num}"]`);
  }

  function grupoPieza(num, d, transformacion) {
    const seleccionada = estado.pieza === String(num);
    const texto = descripcion(num, d);
    const grupo = sv('g', { class: 'pieza', role: 'button', tabindex: '0', 'data-pieza': num, 'aria-pressed': seleccionada ? 'true' : 'false', 'aria-label': texto, transform: transformacion }, sv('title', { text: texto }));
    grupo.addEventListener('click', () => elegir(num));
    grupo.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        elegir(num);
      }
    });
    return { grupo, seleccionada };
  }

  function divisorTemporal(svg, y, ancho, margen) {
    svg.append(sv('line', { x1: margen, x2: ancho - margen, y1: y, y2: y, stroke: '#D8DEE3' }),
      sv('rect', { x: ancho / 2 - 70, y: y - 9, width: 140, height: 18, fill: '#fff' }),
      sv('text', { x: ancho / 2, y: y + 4, 'text-anchor': 'middle', 'font-size': 11, fill: '#515D67', text: 'Dentición temporal' }));
  }
  function lados(svg, alto, ancho, margen) {
    svg.append(sv('text', { x: margen, y: alto - 4, 'font-size': 11, fill: '#515D67', text: 'Derecha del paciente' }),
      sv('text', { x: ancho - margen, y: alto - 4, 'font-size': 11, fill: '#515D67', 'text-anchor': 'end', text: 'Izquierda del paciente' }));
  }

  function vistaDiente() {
    const paso = 46; const x0 = 8; const medio = 20; const ancho = x0 * 2 + 16 * paso + medio; const escalaT = 0.82;
    const bloques = [{ s: ADULTO_SUP, i: ADULTO_INF, off: 0, esc: 1 }];
    if (estado.temporal) bloques.push({ s: TEMPORAL_SUP, i: TEMPORAL_INF, off: 3, esc: escalaT });
    let y = 24;
    let divisor = null;
    const filas = [];
    bloques.forEach((b, indice) => {
      if (indice === 1) { divisor = y + 18; y += 48; }
      const alto = ALTO_DIENTE * b.esc;
      filas.push({ nums: b.s, off: b.off, esc: b.esc, y, inferior: false, alto });
      y += alto + (b.esc === 1 ? 22 : 14);
      filas.push({ nums: b.i, off: b.off, esc: b.esc, y, inferior: true, alto });
      y += alto + (indice === 0 && bloques.length === 1 ? 4 : 24);
    });
    const altoTotal = y + 34;
    const svg = sv('svg', { viewBox: `0 0 ${ancho} ${altoTotal}`, role: 'group', 'aria-label': 'Piezas dentales en vista de diente, numeración FDI' });
    const xMedio = x0 + 8 * paso + medio / 2 - (paso - 40) / 2;
    svg.append(sv('line', { x1: xMedio, x2: xMedio, y1: 8, y2: altoTotal - 24, stroke: '#C4CBD2', 'stroke-dasharray': '3 4' }));
    if (divisor != null) divisorTemporal(svg, divisor, ancho, x0);
    lados(svg, altoTotal, ancho, x0);
    filas.forEach((f) => f.nums.forEach((num, j) => {
      const idx = f.off + j;
      const x = x0 + idx * paso + (idx >= 8 ? medio : 0) + (40 - 40 * f.esc) / 2;
      const d = piezas[String(num)];
      const { grupo, seleccionada } = grupoPieza(num, d, `translate(${x} ${f.y})`);
      grupo.append(sv('rect', { x: -3, y: -3, width: 46, height: f.alto / f.esc + 6, fill: 'transparent' }));
      grupo.append(sv('g', { transform: f.inferior ? `translate(0 ${ALTO_DIENTE * f.esc}) scale(${f.esc} ${-f.esc})` : `scale(${f.esc})` }, diente(num, d, 'dt', f.inferior)));
      grupo.append(sv('rect', { class: 'aro', x: -4, y: -4, width: 48, height: f.alto + 8, rx: 9 }));
      grupo.append(sv('text', { x: 20, y: f.inferior ? f.alto + 14 : -6, 'text-anchor': 'middle', 'font-size': 11.5, 'font-weight': seleccionada ? 700 : 500, fill: '#1F272D', text: num }));
      svg.append(grupo);
    }));
    return svg;
  }

  function vistaCubo() {
    const lado = 40; const escala = lado / 36; const paso = 46; const x0 = 8; const medio = 20; const ancho = x0 * 2 + 16 * paso + medio;
    const filas = [{ nums: ADULTO_SUP, off: 0 }, { nums: ADULTO_INF, off: 0 }];
    if (estado.temporal) filas.push({ nums: TEMPORAL_SUP, off: 3 }, { nums: TEMPORAL_INF, off: 3 });
    const altoFila = 94;
    const ys = [];
    let y = 22;
    filas.forEach((_, i) => {
      if (i === 2) y += 42;
      ys.push(y);
      y += altoFila;
    });
    const altoTotal = y + 8;
    const svg = sv('svg', { viewBox: `0 0 ${ancho} ${altoTotal}`, role: 'group', 'aria-label': 'Piezas dentales en vista de cubo, con estado y superficies' });
    const xMedio = x0 + 8 * paso + medio / 2 - (paso - lado) / 2;
    svg.append(sv('line', { x1: xMedio, x2: xMedio, y1: 8, y2: altoTotal - 24, stroke: '#C4CBD2', 'stroke-dasharray': '3 4' }));
    if (estado.temporal) divisorTemporal(svg, ys[2] - 36, ancho, x0);
    lados(svg, altoTotal, ancho, x0);
    filas.forEach((f, ri) => f.nums.forEach((num, j) => {
      const idx = f.off + j;
      const x = x0 + idx * paso + (idx >= 8 ? medio : 0);
      const d = piezas[String(num)];
      const e = d && MAPA[d.estado];
      const { grupo, seleccionada } = grupoPieza(num, d, `translate(${x} ${ys[ri]})`);
      grupo.append(sv('rect', { x: -4, y: -18, width: lado + 8, height: lado + 52, fill: 'transparent' }));
      grupo.append(sv('g', { transform: `scale(${escala})` }, cubo(num, d)));
      grupo.append(sv('rect', { class: 'aro', x: -5, y: -19, width: lado + 10, height: lado + 50, rx: 9 }));
      grupo.append(sv('text', { x: lado / 2, y: -6, 'text-anchor': 'middle', 'font-size': 11.5, 'font-weight': seleccionada ? 700 : 500, fill: '#1F272D', text: num }));
      grupo.append(sv('text', { x: lado / 2, y: lado + 13, 'text-anchor': 'middle', 'font-size': 9.5, 'font-weight': e ? 700 : 400, fill: e ? '#1F272D' : '#6B7680', text: e ? CORTO[e.k] : '—' }));
      if (e && e.k !== 'ausente') grupo.append(sv('text', { x: lado / 2, y: lado + 26, 'text-anchor': 'middle', 'font-size': 9.5, fill: '#515D67', text: textoSuperficies(d) }));
      svg.append(grupo);
    }));
    return svg;
  }

  function tablaDetalle() {
    const claves = Object.keys(piezas).filter((k) => estado.sanas || piezas[k].estado !== 'sana').sort((a, b) => Number(a) - Number(b));
    if (!claves.length) return vacio('layout-grid', 'Sin piezas registradas', 'Elige una pieza del odontograma para registrar su estado.');
    return h('div', { class: 'tabla', tabindex: '0', role: 'region', 'aria-label': 'Detalle de las piezas registradas' }, h('table', null,
      h('thead', null, h('tr', null, ['Pieza', 'Estado', 'Superficies', 'Nota', 'Actualizado'].map((t) => h('th', { scope: 'col', text: t })))),
      h('tbody', null, claves.map((k) => {
        const d = piezas[k];
        const e = MAPA[d.estado];
        return h('tr', { class: estado.pieza === k ? 'elegida' : null },
          h('td', null, h('button', { class: 'enlace', type: 'button', text: k, onclick: () => elegir(k) })),
          h('td', null, h('span', { class: 'fila-datos' }, muestra(e), e.l)),
          h('td', { text: d.superficies.length ? d.superficies.join(', ') : 'Toda la pieza' }),
          h('td', { class: 'ajustar', text: d.nota || '—' }),
          h('td', { text: `${nombreProfesional(profesionales, d.actualizado_por)}, ${fFechaHora(d.actualizado_en)}` }));
      }))));
  }

  function dibujar() {
    const claves = Object.keys(piezas);
    const conteo = {};
    claves.forEach((k) => { conteo[piezas[k].estado] = (conteo[piezas[k].estado] || 0) + 1; });
    const sanas = conteo.sana || 0;
    carta.replaceChildren(...[
      h('div', { class: 'od-arriba' },
        h('div', { class: 'fila' }, h('strong', { text: 'Estado de las piezas' }),
          segmento('Vista del odontograma', [{ valor: 'diente', texto: 'Diente' }, { valor: 'cubo', texto: 'Cubo' }], estado.vista, (v) => { estado.vista = v; dibujar(); })),
        h('label', { class: 'casilla' }, h('input', {
          type: 'checkbox', checked: estado.temporal,
          onchange: (e) => { estado.temporal = e.target.checked; dibujar(); },
        }), h('span', { text: 'Mostrar dentición temporal' }))),
      h('div', { class: 'od-dibujo' }, estado.vista === 'diente' ? vistaDiente() : vistaCubo()),
      h('p', {
        class: 'hint',
        text: estado.vista === 'diente'
          ? 'Vista de frente. La franja rayada junto a la encía es la cara lingual o palatina, que no se ve de frente: si está afectada se pinta con el color del estado.'
          : 'Cada cubo muestra las cinco superficies; debajo de cada pieza se lee su estado y las superficies afectadas (O oclusal, I incisal, M mesial, D distal, V vestibular, L lingual, P palatino).',
      }),
      h('div', { class: 'od-leyenda', role: 'group', 'aria-label': 'Leyenda de estados' },
        ESTADOS.map(([k, l]) => h('span', { class: 'od-ley' }, muestra(MAPA[k]), l, conteo[k] && h('b', { text: ` ${conteo[k]}` }))),
        h('span', { class: 'od-ley' }, h('span', { class: 'muestra sin-registrar', text: ' ' }), 'Sin registrar')),
      estado.vista === 'cubo' && h('section', { class: 'pila-s' },
        h('div', { class: 'od-arriba' }, h('h3', { text: 'Detalle de las piezas' }),
          sanas > 0 && h('label', { class: 'casilla' }, h('input', {
            type: 'checkbox', checked: estado.sanas,
            onchange: (e) => { estado.sanas = e.target.checked; dibujar(); },
          }), h('span', { text: `Incluir ${sanas === 1 ? '1 pieza sana' : `${sanas} piezas sanas`}` }))),
        tablaDetalle()),
    ].filter(Boolean));
  }

  function pintarPanel() {
    if (!estado.pieza) {
      panel.replaceChildren(h('h3', { text: 'Elige una pieza' }),
        h('p', { class: 'hint', text: soloLectura ? 'Toca o selecciona una pieza para ver su detalle.' : 'Toca, o selecciona con el teclado, una pieza para cambiar su estado, marcar superficies y escribir una nota.' }));
      return;
    }
    const numero = estado.pieza;
    const d = piezas[numero] || {};
    let elegido = d.estado || null;
    const marcadas = new Set(d.superficies || []);
    const inferior = ![1, 2, 5, 6].includes(Math.floor(Number(numero) / 10));
    const previo = d.estado ? d : null;
    const vistaPrevia = sv('svg', { viewBox: '0 0 128 76', width: 150, height: 89, 'aria-hidden': 'true' },
      sv('g', { transform: inferior ? 'translate(8 72) scale(1 -1)' : 'translate(8 4)' }, diente(Number(numero), previo, 'pv', inferior)),
      sv('g', { transform: 'translate(70 20) scale(1.35)' }, cubo(Number(numero), previo)));
    const grupoEstados = h('div', { class: 'od-estados', role: 'radiogroup', 'aria-label': 'Estado de la pieza' });
    const pintarEstados = () => grupoEstados.replaceChildren(...ESTADOS.map(([k, l]) => h('button', {
      class: 'od-estado', type: 'button', role: 'radio', 'aria-checked': elegido === k ? 'true' : 'false', disabled: soloLectura,
      onclick: () => { elegido = k; pintarEstados(); },
    }, muestra(MAPA[k]), l)));
    pintarEstados();
    const nota = areaTexto('pieza-nota', { maxlength: 500, disabled: soloLectura, value: d.nota || '' });
    const contador = h('span', { class: 'hint', text: `${(d.nota || '').length} de 500` });
    nota.addEventListener('input', () => { contador.textContent = `${nota.value.length} de 500`; });
    const error = h('div', { class: 'error-campo', role: 'alert', hidden: true });
    const avisar = (mensaje) => {
      error.textContent = mensaje;
      error.hidden = false;
    };
    const guardar = h('button', {
      class: 'btn', type: 'button', text: 'Guardar pieza',
      onclick: async () => {
        if (!elegido) { avisar('Elige un estado para la pieza.'); return; }
        guardar.disabled = true;
        error.hidden = true;
        try {
          piezas[numero] = await api(`/pacientes/${encodeURIComponent(paciente.id_paciente)}/odontograma/piezas/${numero}`, {
            metodo: 'PUT',
            cuerpo: { estado: elegido, superficies: SUPERFICIES.filter((s) => marcadas.has(s)), nota: nota.value.trim() || null },
          });
          aviso_flotante(`Pieza ${numero} guardada`);
          dibujar();
          pintarPanel();
          alCambiar();
          enfocar(`[data-pieza="${numero}"]`);
        } catch (e) {
          avisar(e.message);
          guardar.disabled = false;
        }
      },
    });
    panel.replaceChildren(...[
      h('h3', { text: `Pieza ${numero}` }),
      h('div', { class: 'od-previa' }, vistaPrevia, h('div', { class: 'pila-s' },
        h('p', { class: 'hint', text: d.estado ? `Estado actual: ${MAPA[d.estado].l.toLowerCase()}` : 'Esta pieza aún no tiene estado registrado.' }),
        d.actualizado_por && h('p', { class: 'hint', text: `Actualizado por ${nombreProfesional(profesionales, d.actualizado_por)}, ${fFechaHora(d.actualizado_en)}` }))),
      h('div', { class: 'campo' }, h('span', { class: 'leyenda', text: 'Estado' }), grupoEstados),
      h('fieldset', { class: 'campo' }, h('legend', { class: 'leyenda', text: 'Superficies afectadas' }),
        h('div', { class: 'od-superficies' }, SUPERFICIES.map((s) => h('label', { class: 'casilla' }, h('input', {
          type: 'checkbox', checked: marcadas.has(s), disabled: soloLectura,
          onchange: (e) => { if (e.target.checked) marcadas.add(s); else marcadas.delete(s); },
        }), h('span', { class: 'capital', text: s })))),
        h('span', { class: 'hint', text: 'Sin superficies marcadas, el estado se aplica a toda la pieza.' })),
      h('div', { class: 'campo' }, h('label', { for: 'pieza-nota', text: 'Nota' }), nota, contador),
      error,
      soloLectura
        ? h('p', { class: 'hint', text: paciente.archivado ? 'Este historial está archivado y no admite cambios.' : 'Tu cuenta puede ver el odontograma, pero no modificarlo.' })
        : h('div', { class: 'fila' }, guardar, h('button', {
          class: 'btn sec', type: 'button', text: 'Cerrar',
          onclick: () => { estado.pieza = null; dibujar(); pintarPanel(); },
        })),
    ].filter(Boolean));
  }

  dibujar();
  pintarPanel();
  return h('div', { class: 'od' }, carta, panel);
}
