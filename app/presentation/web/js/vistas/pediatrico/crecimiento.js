/* Crecimiento: graficas sin bibliotecas (SVG local) y controles que no se editan despues. */
import { api } from '../../api.js';
import { sesion } from '../../sesion.js';
import { fFecha, nombreDe } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import { aviso, aviso_flotante, campo, chip, entrada, estadoDeError, lateral, tabla, vacio } from '../../ui/componentes.js';
import { areaTexto, enviar } from './comun.js';

const SVG = 'http://www.w3.org/2000/svg';

function sv(etiqueta, atributos = {}, ...hijos) {
  const el = document.createElementNS(SVG, etiqueta);
  for (const [clave, valor] of Object.entries(atributos)) {
    if (clave === 'text') el.textContent = valor;
    else el.setAttribute(clave, valor);
  }
  el.append(...hijos);
  return el;
}

const titulo = (texto) => sv('title', { text: texto });

function ejeDeEdad(svg, X, maximo, base, centro, alto) {
  const paso = maximo > 48 ? 12 : 6;
  for (let v = 0; v <= maximo; v += paso) {
    svg.append(sv('text', { x: X(v), y: base + 18, 'text-anchor': 'middle', class: 'graf-texto', text: v }));
  }
  svg.append(sv('text', { x: centro, y: alto - 4, 'text-anchor': 'middle', class: 'graf-eje', text: 'Edad (meses)' }));
}

function graficaDeLinea(puntos, unidad, serie) {
  /* Ancho pensado para media columna: el texto debe seguir siendo legible al escalar. */
  const W = 440; const H = 230; const L = 40; const R = 14; const T = 18; const B = 38;
  const svg = sv('svg', {
    viewBox: `0 0 ${W} ${H}`, class: 'grafica', role: 'img',
    'aria-label': `${unidad} según la edad en meses: ${puntos.map((d) => `${d.y} a los ${d.x} meses`).join('; ')}`,
  });
  const xs = puntos.map((d) => d.x);
  const ys = puntos.map((d) => d.y);
  const x1 = Math.max(...xs) * 1.05 || 1;
  const menor = Math.min(...ys);
  const mayor = Math.max(...ys);
  const margen = (mayor - menor || mayor * 0.2) * 0.25;
  const y0 = Math.max(0, menor - margen);
  const y1 = mayor + margen;
  const X = (v) => L + (v / x1) * (W - L - R);
  const Y = (v) => H - B - ((v - y0) / (y1 - y0)) * (H - T - B);
  for (let i = 0; i <= 4; i += 1) {
    const v = y0 + ((y1 - y0) * i) / 4;
    svg.append(
      sv('line', { x1: L, x2: W - R, y1: Y(v), y2: Y(v), class: 'graf-rejilla' }),
      sv('text', { x: L - 8, y: Y(v) + 4, 'text-anchor': 'end', class: 'graf-texto', text: v.toFixed(v < 30 ? 1 : 0) }),
    );
  }
  ejeDeEdad(svg, X, x1, H - B, (L + W - R) / 2, H);
  svg.append(sv('text', { x: L - 8, y: 9, 'text-anchor': 'end', class: 'graf-eje', text: unidad }));
  svg.append(sv('polyline', { points: puntos.map((d) => `${X(d.x)},${Y(d.y)}`).join(' '), class: `graf-linea ${serie}` }));
  puntos.forEach((d) => svg.append(
    sv('circle', { cx: X(d.x), cy: Y(d.y), r: 4.5, class: `graf-punto ${serie}` }, titulo(`${d.y} ${unidad} a los ${d.x} meses`)),
    sv('text', { x: X(d.x), y: Y(d.y) - 10, 'text-anchor': 'middle', class: 'graf-valor', text: d.y }),
  ));
  return svg;
}

/* El API entrega el percentil de cada control; P3 a P97 son referencias fijas, no curvas. */
function graficaDePercentiles(controles) {
  const W = 700; const H = 250; const L = 46; const R = 44; const T = 16; const B = 40;
  const series = [['percentil_peso', 'Peso', 'peso'], ['percentil_talla', 'Talla', 'talla']];
  const svg = sv('svg', { viewBox: `0 0 ${W} ${H}`, class: 'grafica', role: 'img', 'aria-label': 'Percentiles de peso y talla según la edad en meses' });
  const x1 = Math.max(...controles.map((c) => c.edad_meses), 12) * 1.05;
  const X = (v) => L + (v / x1) * (W - L - R);
  const Y = (v) => H - B - (v / 100) * (H - T - B);
  svg.append(
    sv('rect', { x: L, y: Y(97), width: W - L - R, height: Y(3) - Y(97), class: 'graf-banda' }),
    sv('rect', { x: L, y: Y(85), width: W - L - R, height: Y(15) - Y(85), class: 'graf-banda media' }),
  );
  [3, 15, 50, 85, 97].forEach((v) => svg.append(
    sv('line', { x1: L, x2: W - R, y1: Y(v), y2: Y(v), class: `graf-ref ${v === 50 ? 'central' : ''}` }),
    sv('text', { x: W - R + 6, y: Y(v) + 4, class: 'graf-texto', text: `P${v}` }),
  ));
  ejeDeEdad(svg, X, x1, H - B, (L + W - R) / 2, H);
  series.forEach(([clave, nombre, serie]) => {
    const puntos = controles.filter((c) => c[clave] != null);
    if (!puntos.length) return;
    svg.append(sv('polyline', { points: puntos.map((c) => `${X(c.edad_meses)},${Y(c[clave])}`).join(' '), class: `graf-linea ${serie}` }));
    puntos.forEach((c) => svg.append(sv('circle', { cx: X(c.edad_meses), cy: Y(c[clave]), r: 4.5, class: `graf-punto ${serie}` }, titulo(`${nombre}: P${c[clave]} a los ${c.edad_meses} meses`))));
  });
  return svg;
}

const medida = (valor, unidad) => (valor == null ? '—' : `${valor} ${unidad}`);
const percentil = (valor) => (valor == null ? h('span', { class: 'muted', text: '—' }) : chip('info', null, `P${valor}`));

export function pestanaCrecimiento(p, ctx) {
  const { valor, error } = ctx.datos.crecimiento;
  if (error) return estadoDeError(error, ctx.repintar);
  const nuevo = sesion.tiene('consultas:registrar') && !p.archivado
    ? h('button', { class: 'btn', type: 'button', onclick: () => abrirControl(p, ctx.repintar) }, ic('plus', 16), 'Nuevo control')
    : null;
  if (!valor.length) return vacio('ruler', 'Sin controles de crecimiento', 'Registra peso, talla y perímetro cefálico en cada control para ver la evolución.', nuevo);

  /* La API los entrega del mas reciente al mas antiguo; las graficas van en orden de edad. */
  const recientes = [...valor].sort((a, b) => b.fecha_registro.localeCompare(a.fecha_registro));
  const conEdad = recientes.filter((c) => c.edad_meses != null).reverse();
  const puntos = (clave) => conEdad.filter((c) => c[clave] != null).map((c) => ({ x: c.edad_meses, y: c[clave] }));
  const peso = puntos('peso_kg');
  const talla = puntos('talla_cm');
  const hayPercentiles = conEdad.some((c) => c.percentil_peso != null || c.percentil_talla != null);

  return h('div', { class: 'pila' },
    h('div', { class: 'papel-cab sin-margen' }, h('h2', { text: 'Controles de crecimiento' }), nuevo),
    (peso.length > 0 || talla.length > 0) && h('div', { class: 'dos-col' },
      peso.length > 0 && h('section', { class: 'papel' }, h('h3', { class: 'titulo-papel', text: 'Peso' }), graficaDeLinea(peso, 'kg', 'peso')),
      talla.length > 0 && h('section', { class: 'papel' }, h('h3', { class: 'titulo-papel', text: 'Talla' }), graficaDeLinea(talla, 'cm', 'talla'))),
    hayPercentiles && h('section', { class: 'papel' },
      h('div', { class: 'papel-cab' }, h('h3', { text: 'Percentiles a lo largo del tiempo' }), h('span', { class: 'hint', text: 'Banda clara: P3 a P97. Banda oscura: P15 a P85.' })),
      graficaDePercentiles(conEdad),
      h('div', { class: 'leyenda-graf' }, h('span', null, h('i', { class: 'peso' }), 'Peso'), h('span', null, h('i', { class: 'talla' }), 'Talla'))),
    h('p', { class: 'hint', text: 'Se grafican solo los controles registrados. Un control no se edita después de guardarlo.' }),
    tabla(['Fecha', 'Edad', 'Peso', 'Talla', 'Perímetro cefálico', 'Percentil peso', 'Percentil talla', 'Referencia', 'Observaciones'],
      recientes.map((c) => h('tr', null,
        h('td', { class: 'num', text: fFecha(c.fecha_registro) }),
        h('td', { class: 'num', text: c.edad_meses == null ? '—' : `${c.edad_meses} m` }),
        h('td', { class: 'num', text: medida(c.peso_kg, 'kg') }),
        h('td', { class: 'num', text: medida(c.talla_cm, 'cm') }),
        h('td', { class: 'num', text: medida(c.perimetro_cefalico, 'cm') }),
        h('td', null, percentil(c.percentil_peso)),
        h('td', null, percentil(c.percentil_talla)),
        h('td', { text: c.referencia_percentiles || '—' }),
        h('td', { class: 'ajustar', text: c.observaciones || '—' })))));
}

function abrirControl(p, alGuardar) {
  const numero = (id, atributos) => entrada(id, { type: 'number', inputmode: 'decimal', ...atributos });
  const peso = numero('control-peso', { step: '0.01', min: 0, max: 300 });
  const talla = numero('control-talla', { step: '0.1', min: 0, max: 250 });
  const cefalico = numero('control-cefalico', { step: '0.1', min: 0, max: 100 });
  const percentilPeso = numero('control-pp', { step: '0.1', min: 0, max: 100 });
  const percentilTalla = numero('control-pt', { step: '0.1', min: 0, max: 100 });
  const referencia = entrada('control-referencia', { maxlength: 150, placeholder: 'OMS 2006' });
  const observaciones = areaTexto('control-observaciones', { maxlength: 2000 });
  const campos = {
    peso_kg: campo('Peso (kg)', peso, { opcional: true }),
    talla_cm: campo('Talla (cm)', talla, { opcional: true }),
    perimetro_cefalico: campo('Perímetro cefálico (cm)', cefalico, { opcional: true }),
    percentil_peso: campo('Percentil de peso', percentilPeso, { opcional: true, ayuda: 'De 0 a 100.' }),
    percentil_talla: campo('Percentil de talla', percentilTalla, { opcional: true, ayuda: 'De 0 a 100.' }),
    referencia_percentiles: campo('Referencia de percentiles', referencia, { opcional: true }),
    observaciones: campo('Observaciones', observaciones, { opcional: true }),
  };
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'button', text: 'Guardar control' });
  const panel = lateral('Nuevo control de crecimiento', [
    h('p', { class: 'muted', text: `Paciente: ${nombreDe(p)}. La edad en meses la calcula el servidor con la fecha de nacimiento.` }),
    h('div', { class: 'dos' }, campos.peso_kg, campos.talla_cm), campos.perimetro_cefalico,
    h('div', { class: 'dos' }, campos.percentil_peso, campos.percentil_talla), campos.referencia_percentiles, campos.observaciones, zona,
  ], [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => panel.cerrar() }), boton]);

  const leer = (control) => (control.value === '' ? null : Number(control.value));
  const enRango = (control, nodo, excluirCero) => {
    const v = leer(control);
    const ok = control.validity.valid && (v === null || !excluirCero || v > 0);
    nodo.marcar(ok ? null : `Escribe un valor válido, hasta ${control.max}.`);
    return ok;
  };

  boton.addEventListener('click', () => {
    const validos = [
      enRango(peso, campos.peso_kg, true), enRango(talla, campos.talla_cm, true), enRango(cefalico, campos.perimetro_cefalico, true),
      enRango(percentilPeso, campos.percentil_peso, false), enRango(percentilTalla, campos.percentil_talla, false),
    ].every(Boolean);
    if (!validos) return;
    const texto = observaciones.value.trim() || null;
    if (leer(peso) === null && leer(talla) === null && leer(cefalico) === null && !texto) {
      zona.replaceChildren(aviso('crit', 'circle-alert', h('b', { text: 'Registra al menos peso, talla, perímetro cefálico u observaciones.' })));
      return;
    }
    enviar(boton, zona, campos, async () => {
      await api(`/pacientes/${encodeURIComponent(p.id_paciente)}/crecimiento`, {
        metodo: 'POST',
        cuerpo: {
          peso_kg: leer(peso),
          talla_cm: leer(talla),
          perimetro_cefalico: leer(cefalico),
          percentil_peso: leer(percentilPeso),
          percentil_talla: leer(percentilTalla),
          referencia_percentiles: referencia.value.trim() || null,
          observaciones: texto,
        },
      });
      panel.cerrar();
      aviso_flotante('Control registrado');
      alGuardar();
    });
  });
}
