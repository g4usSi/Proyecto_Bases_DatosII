/* Tutores del paciente: el contacto es del tutor y lo comparten sus hermanos; el parentesco,
   ser principal y poder recoger al paciente son del vinculo con este paciente. */
import { api } from '../../api.js';
import { accionesFicha, bloqueDatos } from '../compartido/ficha.js';
import { sesion } from '../../sesion.js';
import { nombreDe } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import { aviso, aviso_flotante, campo, chip, entrada, estadoDeError, lateral, vacio } from '../../ui/componentes.js';
import { enviar } from './comun.js';

const ruta = (p) => `/pacientes/${encodeURIComponent(p.id_paciente)}/tutores`;
const limpio = (control) => control.value.trim() || null;
const iniciales = (t) => `${t.nombres[0] || ''}${t.apellidos[0] || ''}`.toUpperCase();

function selectorParentesco(id, valor) {
  const opciones = h('datalist', { id: `${id}-opciones` }, ['Madre', 'Padre', 'Abuela', 'Abuelo', 'Tía', 'Tío', 'Tutor legal'].map((v) => h('option', { value: v })));
  const control = entrada(id, { maxlength: 80, list: `${id}-opciones`, value: valor || '' });
  return { control, opciones };
}

/* Un tutor principal siempre puede recoger al paciente (regla de la base). */
function casillasDeVinculo({ principal, autorizado }) {
  const esPrincipal = h('input', { type: 'checkbox', checked: principal });
  const puedeRecoger = h('input', { type: 'checkbox', checked: autorizado || principal, disabled: principal });
  esPrincipal.addEventListener('change', () => {
    if (esPrincipal.checked) puedeRecoger.checked = true;
    puedeRecoger.disabled = esPrincipal.checked;
  });
  return {
    nodo: h('div', { class: 'pila-s' },
      h('label', { class: 'casilla' }, esPrincipal, h('span', null, h('b', { text: 'Tutor principal' }), h('span', { class: 'hint bloque', text: 'Las facturas salen a su nombre si no se elige otro. Reemplaza al principal actual.' }))),
      h('label', { class: 'casilla' }, puedeRecoger, h('span', null, h('b', { text: 'Autorizado para recoger' }), h('span', { class: 'hint bloque', text: 'El tutor principal siempre lo está.' })))),
    esPrincipal,
    puedeRecoger,
  };
}

export function pestanaTutores(p, ctx) {
  const { valor: tutores, error } = ctx.datos.tutores;
  if (error) return estadoDeError(error, ctx.repintar);
  const escribe = sesion.tiene('pacientes:registrar') && !p.archivado;
  const vincular = escribe
    ? h('button', { class: 'btn', type: 'button', onclick: () => abrirVincular(p, tutores, ctx.repintar) }, ic('user-plus', 16), 'Vincular tutor')
    : null;
  if (!tutores.length) return vacio('users', 'Sin tutores registrados', 'Cada paciente debería tener al menos un tutor responsable.', vincular);
  return h('div', { class: 'pila' },
    h('div', { class: 'papel-cab sin-margen' }, h('h2', { text: 'Tutores' }), vincular),
    h('div', { class: 'tarjetas' }, tutores.map((v) => h('section', { class: 'papel tarjeta-tutor' },
      h('div', { class: 'ficha-nombre' }, h('span', { class: 'avatar', 'aria-hidden': 'true', text: iniciales(v.tutor) }),
        h('div', null, h('h3', { text: nombreDe(v.tutor) }), h('p', { class: 'hint', text: v.parentesco }))),
      h('div', { class: 'fila' },
        v.es_principal && chip('info', 'badge-check', 'Tutor principal'),
        v.autorizado ? chip('ok', 'check', 'Autorizado para recoger') : chip('', 'ban', 'No autorizado para recoger')),
      bloqueDatos('Datos del tutor', h('dl', { class: 'lista-datos' },
        h('dt', { text: 'Documento' }), h('dd', { text: v.tutor.documento || 'No registrado' }),
        h('dt', { text: 'Teléfono' }), h('dd', { text: v.tutor.telefono || 'No registrado' }),
        h('dt', { text: 'Correo' }), h('dd', { text: v.tutor.correo || 'No registrado' }),
        h('dt', { text: 'Dirección' }), h('dd', { text: v.tutor.direccion || 'No registrada' }))),
      escribe && accionesFicha([h('button', { class: 'btn sec sm', type: 'button', onclick: () => abrirCambios(p, v, ctx.repintar) }, ic('pencil', 14), 'Editar tutor')])))));
}

function abrirVincular(p, tutores, alGuardar) {
  let existente = null;
  const documento = entrada('tutor-documento', { maxlength: 30, placeholder: 'DPI o pasaporte' });
  const nombres = entrada('tutor-nombres', { maxlength: 100 });
  const apellidos = entrada('tutor-apellidos', { maxlength: 100 });
  const telefono = entrada('tutor-telefono', { maxlength: 30 });
  const correo = entrada('tutor-correo', { type: 'email', maxlength: 254 });
  const direccion = entrada('tutor-direccion', { maxlength: 300 });
  const parentesco = selectorParentesco('tutor-parentesco');
  const campos = {
    documento: campo('Documento', documento, { opcional: true, ayuda: 'Si es tutor de un hermano, búscalo para no registrarlo dos veces.' }),
    nombres: campo('Nombres', nombres), apellidos: campo('Apellidos', apellidos),
    telefono: campo('Teléfono', telefono, { opcional: true }), correo: campo('Correo', correo, { opcional: true }),
    direccion: campo('Dirección', direccion, { opcional: true }),
    parentesco: campo('Parentesco', parentesco.control),
  };
  const vinculo = casillasDeVinculo({ principal: !tutores.some((v) => v.es_principal), autorizado: true });
  const resultado = h('div');
  const datosNuevos = h('div', { class: 'pila-s' },
    h('div', { class: 'dos' }, campos.nombres, campos.apellidos),
    h('div', { class: 'dos' }, campos.telefono, campos.correo), campos.direccion);
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'button', text: 'Vincular tutor' });

  const elegir = (tutor) => {
    existente = tutor;
    datosNuevos.hidden = Boolean(tutor);
    resultado.replaceChildren(...(tutor ? [aviso('info', 'user-round', h('b', { text: nombreDe(tutor) }), ' ya está registrado. Se vinculará este tutor.')] : []));
  };
  const buscar = h('button', {
    class: 'btn sec sm', type: 'button', text: 'Buscar por documento',
    onclick: async () => {
      if (!limpio(documento)) {
        campos.documento.marcar('Escribe el documento para buscar.');
        return;
      }
      campos.documento.marcar(null);
      buscar.disabled = true;
      try {
        elegir(await api('/tutores', { params: { documento: limpio(documento) } }));
      } catch (e) {
        elegir(null);
        resultado.replaceChildren(e.estado === 404
          ? aviso('', 'info', 'No hay un tutor con ese documento: completa sus datos para registrarlo.')
          : aviso('crit', 'circle-alert', h('b', { text: e.message })));
      } finally {
        buscar.disabled = false;
      }
    },
  });
  documento.addEventListener('input', () => { if (existente) elegir(null); });

  const panel = lateral('Vincular tutor', [
    h('p', { class: 'muted', text: `Paciente: ${nombreDe(p)}.` }),
    campos.documento, h('div', null, buscar), resultado, datosNuevos,
    campos.parentesco, parentesco.opciones, vinculo.nodo, zona,
  ], [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => panel.cerrar() }), boton]);

  boton.addEventListener('click', () => {
    campos.parentesco.marcar(limpio(parentesco.control) ? null : 'Escribe el parentesco.');
    let ok = Boolean(limpio(parentesco.control));
    if (!existente) {
      campos.nombres.marcar(limpio(nombres) ? null : 'Escribe los nombres.');
      campos.apellidos.marcar(limpio(apellidos) ? null : 'Escribe los apellidos.');
      ok = ok && Boolean(limpio(nombres)) && Boolean(limpio(apellidos));
    }
    if (!ok) return;
    const cuerpo = {
      parentesco: limpio(parentesco.control),
      es_principal: vinculo.esPrincipal.checked,
      autorizado: vinculo.puedeRecoger.checked,
    };
    if (existente) {
      cuerpo.id_tutor = existente.id_tutor;
    } else {
      cuerpo.tutor = {
        nombres: limpio(nombres), apellidos: limpio(apellidos), documento: limpio(documento),
        telefono: limpio(telefono), correo: limpio(correo), direccion: limpio(direccion),
      };
    }
    enviar(boton, zona, campos, async () => {
      await api(ruta(p), { metodo: 'POST', cuerpo });
      panel.cerrar();
      aviso_flotante('Tutor vinculado');
      alGuardar();
    });
  });
}

function abrirCambios(p, v, alGuardar) {
  const parentesco = selectorParentesco('cambio-parentesco', v.parentesco);
  const telefono = entrada('cambio-telefono', { maxlength: 30, value: v.tutor.telefono || '' });
  const correo = entrada('cambio-correo', { type: 'email', maxlength: 254, value: v.tutor.correo || '' });
  const direccion = entrada('cambio-direccion', { maxlength: 300, value: v.tutor.direccion || '' });
  const campos = {
    parentesco: campo('Parentesco', parentesco.control),
    telefono: campo('Teléfono', telefono, { opcional: true }), correo: campo('Correo', correo, { opcional: true }),
    direccion: campo('Dirección', direccion, { opcional: true }),
  };
  const vinculo = casillasDeVinculo({ principal: v.es_principal, autorizado: v.autorizado });
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'button', text: 'Guardar cambios' });
  const panel = lateral(nombreDe(v.tutor), [
    campos.parentesco, parentesco.opciones, vinculo.nodo,
    h('fieldset', { class: 'pila-s' }, h('legend', { class: 'leyenda', text: 'Contacto' }),
      aviso('info', 'info', 'El contacto es del tutor: el cambio también se ve en la ficha de sus otros pacientes.'),
      h('div', { class: 'dos' }, campos.telefono, campos.correo), campos.direccion),
    zona,
  ], [h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => panel.cerrar() }), boton]);

  boton.addEventListener('click', () => {
    if (!limpio(parentesco.control)) {
      campos.parentesco.marcar('Escribe el parentesco.');
      return;
    }
    /* Solo lo que cambio; un contacto en blanco lo borra (la API trata null como «sin cambio»). */
    const cuerpo = {};
    if (limpio(parentesco.control) !== v.parentesco) cuerpo.parentesco = limpio(parentesco.control);
    if (vinculo.esPrincipal.checked !== v.es_principal) cuerpo.es_principal = vinculo.esPrincipal.checked;
    if (vinculo.puedeRecoger.checked !== v.autorizado) cuerpo.autorizado = vinculo.puedeRecoger.checked;
    if (telefono.value.trim() !== (v.tutor.telefono || '')) cuerpo.telefono = telefono.value.trim();
    if (correo.value.trim() !== (v.tutor.correo || '')) cuerpo.correo = correo.value.trim();
    if (direccion.value.trim() !== (v.tutor.direccion || '')) cuerpo.direccion = direccion.value.trim();
    if (!Object.keys(cuerpo).length) {
      zona.replaceChildren(aviso('info', 'info', 'No hay cambios por guardar.'));
      return;
    }
    enviar(boton, zona, campos, async () => {
      await api(`${ruta(p)}/${encodeURIComponent(v.tutor.id_tutor)}`, { metodo: 'PATCH', cuerpo });
      panel.cerrar();
      aviso_flotante('Cambios guardados');
      alGuardar();
    });
  });
}
