/* Pacientes: buscador a la izquierda y ficha a la derecha, con la ruta #/pacientes/<id>/<pestana>. */
import { api } from '../../api.js';
import { enlace, reflejar } from '../../enrutador.js';
import { fEdad } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import { cabeza, cargando, chip, entrada, estadoDeError, vacio } from '../../ui/componentes.js';
import { pintarFicha } from './ficha.js';

const ESPERA_MS = 250;

export function vistaPacientes({ contenedor, args, params, repintar }) {
  const idPaciente = args[0] ? decodeURIComponent(args[0]) : null;
  const pestana = args[1] || 'resumen';
  const resultados = h('div', { class: 'pila-s', 'aria-live': 'polite' });
  const ficha = h('div', { class: 'pila' });
  let turno = 0;
  let temporizador = null;

  const rutaFicha = (id, q) => enlace(`pacientes/${encodeURIComponent(id)}`, { q });
  const filaPaciente = (p, q) => h('a', {
    class: 'item-paciente', href: rutaFicha(p.id_paciente, q), 'aria-current': p.id_paciente === idPaciente ? 'true' : null,
  },
  h('b', { text: `${p.apellidos}, ${p.nombres}` }),
  h('span', { class: 'fila-datos' },
    p.fecha_nacimiento && h('span', { text: fEdad(p.fecha_nacimiento) }),
    p.archivado && chip('', 'archive', 'Archivado')));

  async function buscar(q) {
    const mio = ++turno;
    if (q.length < 2) {
      resultados.replaceChildren(h('p', { class: 'hint', text: 'Escribe al menos 2 letras. La búsqueda ignora mayúsculas y acentos y encuentra por comienzo de palabra.' }));
      return;
    }
    resultados.replaceChildren(cargando(2));
    try {
      const lista = await api('/pacientes', { params: { nombre: q, limite: 20 } });
      if (mio !== turno) return;
      resultados.replaceChildren(...(lista.length
        ? [h('p', { class: 'hint', text: lista.length === 1 ? '1 resultado' : `${lista.length} resultados` }), ...lista.map((p) => filaPaciente(p, q))]
        : [vacio('search', 'Sin resultados', `No hay pacientes de tu institución que empiecen con «${q}».`)]));
    } catch (error) {
      if (mio === turno) resultados.replaceChildren(estadoDeError(error, () => buscar(q)));
    }
  }

  const caja = entrada('buscar-paciente', {
    type: 'search', value: params.q || '', placeholder: 'Nombre o apellido',
    oninput: () => {
      const q = caja.value.trim();
      clearTimeout(temporizador);
      if (!idPaciente) reflejar('pacientes', { q });
      temporizador = setTimeout(() => buscar(q), ESPERA_MS);
    },
  });

  contenedor.append(
    cabeza('Pacientes', 'Busca un paciente de tu institución.'),
    h('div', { class: 'dividido' },
      h('section', { class: 'pila-s', 'aria-label': 'Buscador' },
        h('div', { class: 'campo' }, h('label', { for: 'buscar-paciente', text: 'Buscar paciente' }),
          h('div', { class: 'buscador' }, ic('search', 18), caja)),
        resultados),
      ficha));

  buscar((params.q || '').trim());
  if (idPaciente) {
    pintarFicha(ficha, { idPaciente, pestana, q: params.q, origen: params.origen, repintar });
  } else {
    ficha.append(vacio('users', 'Elige un paciente', 'Busca por nombre o apellido y selecciona un resultado para ver su ficha.'));
  }
}
