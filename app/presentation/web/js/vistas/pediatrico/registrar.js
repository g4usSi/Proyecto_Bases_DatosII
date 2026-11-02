/* Registrar paciente. Las alergias tienen tres significados y el formulario los separa. */
import { api } from '../../api.js';
import { irA } from '../../enrutador.js';
import { hoyLocal } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import { aviso_flotante, cabeza, campo, entrada } from '../../ui/componentes.js';
import { enviar, repetible } from './comun.js';
import { filaAlergia } from './formularios.js';

const OPCIONES_ALERGIAS = [
  ['omitir', 'Aún no evaluadas', 'La ficha mostrará «No registradas».'],
  ['ninguna', 'Evaluadas: sin alergias conocidas', 'Queda constancia de que se preguntó.'],
  ['lista', 'Registrar alergias', 'Una o más sustancias.'],
];

export function vistaRegistrar({ contenedor }) {
  const hoy = hoyLocal();
  const nombres = entrada('registro-nombres', { maxlength: 120, autocomplete: 'off' });
  const apellidos = entrada('registro-apellidos', { maxlength: 120 });
  const nacimiento = entrada('registro-nacimiento', { type: 'date', max: hoy });
  const telefono = entrada('registro-telefono', { maxlength: 30 });
  const correo = entrada('registro-correo', { type: 'email', maxlength: 254 });
  const direccion = entrada('registro-direccion', { maxlength: 300 });
  const campos = {
    nombres: campo('Nombres *', nombres), apellidos: campo('Apellidos *', apellidos),
    fecha_nacimiento: campo('Fecha de nacimiento *', nacimiento, { ayuda: 'Obligatoria: con ella se calculan la edad, el crecimiento y el esquema de vacunación.' }),
    telefono: campo('Teléfono', telefono, { opcional: true }), correo: campo('Correo', correo, { opcional: true }),
    direccion: campo('Dirección', direccion, { opcional: true }),
  };
  const alergias = repetible('Agregar otra alergia', filaAlergia, { minimo: 1 });
  alergias.nodo.hidden = true;
  let modo = 'omitir';
  const zona = h('div');
  const boton = h('button', { class: 'btn', type: 'submit' }, ic('user-plus', 16), 'Registrar paciente');

  function validar() {
    const faltan = [[campos.nombres, nombres, 'Escribe los nombres.'], [campos.apellidos, apellidos, 'Escribe los apellidos.'], [campos.fecha_nacimiento, nacimiento, 'Escribe la fecha de nacimiento.']]
      .map(([nodo, control, mensaje]) => {
        const ok = Boolean(control.value.trim());
        nodo.marcar(ok ? null : mensaje);
        return ok;
      });
    return faltan.every(Boolean) && (modo !== 'lista' || alergias.validar());
  }

  async function guardar(evento) {
    evento.preventDefault();
    if (!validar()) return;
    const cuerpo = { nombres: nombres.value.trim(), apellidos: apellidos.value.trim(), fecha_nacimiento: nacimiento.value };
    const contacto = { telefono: telefono.value.trim() || null, correo: correo.value.trim() || null, direccion: direccion.value.trim() || null };
    if (Object.values(contacto).some(Boolean)) cuerpo.contacto = contacto;
    /* Sin enviar el campo significa «no se pregunto», distinto de una lista vacia. */
    if (modo === 'ninguna') cuerpo.alergias = [];
    if (modo === 'lista') cuerpo.alergias = alergias.leer();
    await enviar(boton, zona, campos, async () => {
      const paciente = await api('/pacientes', { metodo: 'POST', cuerpo });
      aviso_flotante('Paciente registrado. Ahora agrega a su tutor.');
      irA(`pacientes/${encodeURIComponent(paciente.id_paciente)}/tutores`);
    });
  }

  contenedor.append(
    cabeza('Registrar paciente', 'Los campos con asterisco son obligatorios.'),
    h('form', { class: 'papel pila formulario-angosto', novalidate: true, onsubmit: guardar },
      h('div', { class: 'dos' }, campos.nombres, campos.apellidos),
      campos.fecha_nacimiento,
      h('fieldset', { class: 'pila-s' }, h('legend', { class: 'leyenda', text: 'Contacto' }),
        h('div', { class: 'dos' }, campos.telefono, campos.correo), campos.direccion),
      h('fieldset', { class: 'pila-s' }, h('legend', { class: 'leyenda', text: 'Alergias' }),
        OPCIONES_ALERGIAS.map(([valor, titulo, ayuda]) => h('label', { class: 'casilla' },
          h('input', {
            type: 'radio', name: 'registro-alergias', value: valor, checked: valor === modo,
            onchange: () => {
              modo = valor;
              alergias.nodo.hidden = valor !== 'lista';
            },
          }),
          h('span', null, h('b', { text: titulo }), h('span', { class: 'hint bloque', text: ayuda })))),
        alergias.nodo),
      zona,
      h('div', { class: 'fila fin' },
        h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => irA('pacientes') }), boton)));
}
