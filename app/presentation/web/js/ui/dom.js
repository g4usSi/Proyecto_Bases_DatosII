/* Construccion del DOM sin HTML en texto: todo dato de la API llega como textContent o nodo. */

const SVG = 'http://www.w3.org/2000/svg';

export function h(etiqueta, atributos, ...hijos) {
  const el = document.createElement(etiqueta);
  aplicar(el, atributos);
  anexar(el, hijos);
  return el;
}

function aplicar(el, atributos) {
  if (!atributos) return;
  for (const [clave, valor] of Object.entries(atributos)) {
    if (valor == null || valor === false) continue;
    if (clave === 'class') el.className = valor;
    else if (clave === 'text') el.textContent = valor;
    else if (clave === 'estilo') for (const [p, v] of Object.entries(valor)) el.style.setProperty(p, v);
    else if (clave === 'value') el.value = valor;
    else if (clave === 'checked' || clave === 'disabled' || clave === 'selected') el[clave] = Boolean(valor);
    else if (clave.startsWith('on')) el.addEventListener(clave.slice(2), valor);
    else el.setAttribute(clave, valor === true ? '' : valor);
  }
}

function anexar(el, hijos) {
  for (const hijo of hijos.flat(Infinity)) {
    if (hijo == null || hijo === false) continue;
    el.append(hijo.nodeType ? hijo : document.createTextNode(String(hijo)));
  }
}

export function ic(nombre, tam = 18) {
  const svg = document.createElementNS(SVG, 'svg');
  svg.setAttribute('class', 'ic');
  svg.setAttribute('width', tam);
  svg.setAttribute('height', tam);
  svg.setAttribute('aria-hidden', 'true');
  const uso = document.createElementNS(SVG, 'use');
  uso.setAttribute('href', `assets/icons/sprite.svg#${nombre}`);
  svg.append(uso);
  return svg;
}

export const marca = () => h('span', { class: 'marca', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'), h('i'));
