/* Usuarios y accesos. Alcance: el superusuario todas las entidades; el administrador, la suya. */
import { api } from '../../api.js';
import { sesion } from '../../sesion.js';
import {
  ENTIDADES, ESTADOS_CUENTA, PERMISOS, PERMISOS_ASIGNABLES, PERMISOS_SUGERIDOS, ROLES_POR_ENTIDAD,
  VEDADOS_SECRETARIA, entidad, textoRol,
} from '../../catalogos.js';
import { reflejar } from '../../enrutador.js';
import { fEntero, fFecha, nombreDe } from '../../formato.js';
import { h, ic } from '../../ui/dom.js';
import {
  aviso, aviso_flotante, cabeza, campo, cargando, chip, cifras, claveConOjo, confirmar, copiar, entrada,
  estadoDeError, lateral, medidorDeClave, modal, mostrarErrorDeFormulario, problemaDeClave, segmento,
  seleccion, tabla, vacio,
} from '../../ui/componentes.js';

const esSuper = () => sesion.tiene('plataforma:administrar');
const sinAcceso = (p) => p.estado !== 'activa';
const chipEstado = (estado) => {
  const e = ESTADOS_CUENTA[estado] || { clase: '', texto: estado };
  return chip(e.clase, e.icono, e.texto);
};
const adminActivo = (lista, id) => lista.find((p) => p.institucion === id && p.rol === 'administrador' && p.estado === 'activa');

/* Las areas solo existen en el Hospital General. */
async function cargarAreas() {
  const params = esSuper() ? { establecimiento: 'hospital_general' } : {};
  return api('/departamentos', { params });
}

function casillasDePermisos(inst, rol, marcados) {
  if (rol === 'administrador') {
    return [h('p', { class: 'hint', text: 'Una cuenta de administración tiene un único permiso y ningún acceso clínico.' })];
  }
  return PERMISOS_ASIGNABLES[inst].map((clave) => {
    const { texto, ayuda } = PERMISOS[clave];
    const vedado = rol === 'secretaria' && VEDADOS_SECRETARIA.includes(clave);
    const base = clave === 'pacientes:leer';
    const nota = vedado ? 'No aplica a secretaría.' : ayuda;
    return h('label', { class: `casilla ${vedado ? 'apagada' : ''}` },
      h('input', { type: 'checkbox', value: clave, checked: base || (!vedado && marcados.includes(clave)), disabled: base || vedado }),
      h('span', null, h('b', { text: texto }), nota && h('div', { class: 'hint', text: nota })));
  });
}
const permisosMarcados = (nodo) => [...nodo.querySelectorAll('input[type=checkbox]:checked')].map((i) => i.value);

/* ---------- Credenciales: se muestran una sola vez ---------- */
function mostrarCredenciales({ persona, clave, titulo, alCerrar }) {
  const linea = (etiqueta, valor, mono) => h('div', { class: 'credencial' }, h('small', { text: etiqueta }),
    h('div', null, h('b', { class: mono ? 'mono' : null, text: valor }),
      h('button', { class: 'btn sec sm', type: 'button', onclick: () => copiar(valor, `${etiqueta} copiado`) }, ic('copy', 14), 'Copiar')));
  const m = modal(titulo, h('div', { class: 'pila-s' },
    h('p', { text: `${nombreDe(persona)}, ${textoRol(persona.rol)}, ${entidad(persona.institucion).nombre}` }),
    linea('Correo', persona.correo),
    clave ? linea('Contraseña', clave, true) : aviso('info', 'info', 'Entrega la contraseña que escribiste.'),
    aviso('aviso', 'triangle-alert', h('b', { text: 'No se volverá a mostrar. ' }), 'Entrégala por un medio seguro. Si se pierde, hay que restablecerla.'),
    h('p', { class: 'hint', text: 'Al entrar por primera vez, la persona debe elegir su propia contraseña.' })),
  [h('button', { class: 'btn', type: 'button', text: 'Listo, ya la entregué', onclick: () => { m.cerrar(); alCerrar?.(); } })], { fijo: true });
}

/* ---------- Crear ---------- */
function abrirCreacion({ personal, alCambiar }) {
  const sup = esSuper();
  const fija = sup ? null : sesion.usuario.institucion;
  const zona = h('div');
  const nombres = entrada('us-n', { maxlength: 120, autocomplete: 'off' });
  const apellidos = entrada('us-a', { maxlength: 120, autocomplete: 'off' });
  const correo = entrada('us-c', { type: 'email', maxlength: 254, placeholder: 'nombre.apellido@entidad.gt' });
  const selEntidad = seleccion('us-e', [{ valor: '', texto: 'Elige la entidad' }, ...ENTIDADES.map((e) => ({ valor: e.id, texto: e.nombre }))]);
  const selRol = seleccion('us-r', [{ valor: '', texto: 'Primero elige la entidad' }]);
  const selArea = seleccion('us-ar', [{ valor: '', texto: 'Cargando áreas' }], { disabled: true });
  const clave = claveConOjo('us-p', { autocomplete: 'new-password', maxlength: 128 });
  const control = clave.querySelector('input');
  const permisos = h('div', { class: 'pila-s' });

  const cN = campo('Nombres', nombres);
  const cA = campo('Apellidos', apellidos);
  const cC = campo('Correo de ingreso', correo, { ayuda: 'Será su usuario. No se puede repetir en todo el sistema.' });
  const cE = campo('Entidad', selEntidad);
  const cR = campo('Rol', selRol, { ayuda: sup ? 'Los roles dependen de la entidad.' : null });
  const cAr = campo('Área asignada', selArea);
  const cP = campo('Contraseña inicial', clave, { opcional: true, ayuda: 'Déjala vacía para que el sistema genere una segura.' });
  cAr.hidden = true;
  let areasListas = false;

  const inst = () => fija || selEntidad.value;
  const pintarPermisos = () => {
    const i = inst();
    cAr.hidden = i !== 'hospital_general' || selRol.value === 'administrador';
    if (!cAr.hidden && !areasListas) prepararAreas();
    if (i && selRol.value) permisos.replaceChildren(...casillasDePermisos(i, selRol.value, PERMISOS_SUGERIDOS[selRol.value] || []));
    else permisos.replaceChildren(h('p', { class: 'hint', text: 'Elige la entidad y el rol para ver los permisos que aplican.' }));
  };
  const pintarRoles = () => {
    const i = inst();
    const opciones = !i ? [{ valor: '', texto: 'Primero elige la entidad' }] : [
      { valor: '', texto: 'Elige el rol' },
      ...ROLES_POR_ENTIDAD[i].map((r) => ({ valor: r, texto: textoRol(r) })),
      ...(sup ? [{ valor: 'administrador', texto: adminActivo(personal, i) ? 'Administrador/a (ya tiene uno activo)' : 'Administrador/a de la entidad', apagada: Boolean(adminActivo(personal, i)) }] : []),
    ];
    selRol.replaceChildren(...opciones.map(({ valor, texto, apagada }) => h('option', { value: valor, disabled: apagada, text: texto })));
    pintarPermisos();
  };
  async function prepararAreas() {
    try {
      const areas = await cargarAreas();
      selArea.replaceChildren(h('option', { value: '', text: 'Elige un área' }), ...areas.map((a) => h('option', { value: a.id_departamento, text: a.nombre })));
      selArea.disabled = false;
      areasListas = true;
    } catch (error) {
      selArea.replaceChildren(h('option', { value: '', text: 'No disponibles' }));
      cAr.marcar(`${error.message} La cuenta se puede crear sin área.`);
      areasListas = 'sin-datos';
    }
  }
  selEntidad.addEventListener('change', pintarRoles);
  selRol.addEventListener('change', pintarPermisos);

  const campos = { nombres: cN, apellidos: cA, correo: cC, establecimiento: cE, rol: cR, id_departamento: cAr, contrasena_inicial: cP };
  const boton = h('button', { class: 'btn', type: 'button' }, ic('user-plus', 16), 'Crear cuenta');
  boton.addEventListener('click', async () => {
    zona.replaceChildren();
    Object.values(campos).forEach((c) => c.marcar(null));
    let bien = true;
    const falla = (c, m) => { c.marcar(m); bien = false; };
    const correoLimpio = correo.value.trim().toLowerCase();
    if (!nombres.value.trim()) falla(cN, 'Escribe los nombres.');
    if (!apellidos.value.trim()) falla(cA, 'Escribe los apellidos.');
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(correoLimpio)) falla(cC, 'Escribe un correo válido.');
    if (!inst()) falla(cE, 'Elige la entidad a la que tendrá acceso.');
    if (!selRol.value) falla(cR, 'Elige el rol.');
    if (!cAr.hidden && areasListas === true && !selArea.value) falla(cAr, 'Asigna el área donde trabajará.');
    if (control.value) {
      const problema = problemaDeClave(control.value, correoLimpio);
      if (problema) falla(cP, problema);
    }
    if (!bien) return;

    const cuerpo = {
      correo: correoLimpio,
      nombres: nombres.value.trim(),
      apellidos: apellidos.value.trim(),
      rol: selRol.value,
      permisos: selRol.value === 'administrador' ? ['profesionales:administrar'] : permisosMarcados(permisos),
    };
    if (sup) cuerpo.establecimiento = inst();
    if (!cAr.hidden && selArea.value) cuerpo.id_departamento = Number(selArea.value);
    if (control.value) cuerpo.contrasena_inicial = control.value;

    boton.disabled = true;
    try {
      const creado = await api('/profesionales', { metodo: 'POST', cuerpo });
      const clavePropia = control.value;
      panel.cerrar();
      mostrarCredenciales({
        persona: creado.profesional,
        clave: creado.contrasena_temporal || clavePropia,
        titulo: 'Cuenta creada',
        alCerrar: alCambiar,
      });
      if (!creado.vinculado) {
        aviso_flotante(`El perfil local en ${entidad(creado.profesional.institucion).nombre} quedó pendiente: hay que ejecutar la sincronización de profesionales.`, 'triangle-alert');
      }
    } catch (error) {
      boton.disabled = false;
      mostrarErrorDeFormulario(error, campos, zona);
    }
  });

  const panel = lateral('Crear usuario', [
    sup
      ? aviso('info', 'shield-check', h('b', { text: 'Tú eliges la entidad. ' }), 'La cuenta solo podrá entrar a esa entidad; para trabajar en otra hace falta una cuenta distinta.')
      : aviso('info', 'building-2', h('b', { text: `Se crea en ${entidad(fija).nombre}. ` }), 'Para crear una cuenta en otra entidad, pídelo a la administración general.'),
    zona,
    h('div', { class: 'dos' }, cN, cA),
    cC,
    sup ? h('div', { class: 'dos' }, cE, cR) : cR,
    cAr,
    cP,
    medidorDeClave(control),
    h('fieldset', null, h('legend', { class: 'leyenda', text: 'Permisos' }), permisos),
  ], [
    h('button', { class: 'btn sec', type: 'button', text: 'Cancelar', onclick: () => panel.cerrar() }),
    boton,
  ]);
  if (fija) pintarRoles();
  else pintarPermisos();
}

/* ---------- Detalle y cambios ---------- */
export function abrirUsuario(persona, { personal, alCambiar }) {
  const sup = esSuper();
  const inst = entidad(persona.institucion);
  const esAdmin = persona.rol === 'administrador';
  const zona = h('div');
  const nombres = entrada('ud-n', { value: persona.nombres, maxlength: 120 });
  const apellidos = entrada('ud-a', { value: persona.apellidos, maxlength: 120 });
  const cN = campo('Nombres', nombres);
  const cA = campo('Apellidos', apellidos);
  const permisos = h('div', { class: 'pila-s' }, casillasDePermisos(persona.institucion, persona.rol, persona.permisos));
  const conArea = persona.institucion === 'hospital_general' && !esAdmin;
  const selArea = seleccion('ud-ar', [{ valor: '', texto: persona.departamento || 'Cargando áreas' }], { disabled: true });
  const cAr = campo('Área asignada', selArea);
  const campos = { nombres: cN, apellidos: cA, id_departamento: cAr };

  if (conArea) {
    cargarAreas().then((areas) => {
      selArea.replaceChildren(h('option', { value: '', text: 'Sin área' }), ...areas.map((a) => h('option', { value: a.id_departamento, text: a.nombre })));
      selArea.value = persona.id_departamento ?? '';
      selArea.disabled = false;
    }).catch((error) => cAr.marcar(error.message));
  }

  const terminar = (mensaje) => {
    panel.cerrar();
    aviso_flotante(mensaje);
    alCambiar?.();
  };
  const cambiarEstado = (estado, mensaje) => api(`/profesionales/${persona.id_profesional}`, { metodo: 'PATCH', cuerpo: { estado } }).then(() => terminar(mensaje));

  const guardar = h('button', { class: 'btn', type: 'button', text: 'Guardar cambios' });
  guardar.addEventListener('click', async () => {
    zona.replaceChildren();
    Object.values(campos).forEach((c) => c.marcar(null));
    if (!nombres.value.trim()) return cN.marcar('Escribe los nombres.');
    if (!apellidos.value.trim()) return cA.marcar('Escribe los apellidos.');
    const cuerpo = {};
    if (nombres.value.trim() !== persona.nombres) cuerpo.nombres = nombres.value.trim();
    if (apellidos.value.trim() !== persona.apellidos) cuerpo.apellidos = apellidos.value.trim();
    if (!esAdmin) {
      const nuevos = permisosMarcados(permisos).sort();
      if (nuevos.join() !== [...persona.permisos].sort().join()) cuerpo.permisos = nuevos;
    }
    if (conArea && !selArea.disabled) {
      const area = selArea.value ? Number(selArea.value) : null;
      if (area !== (persona.id_departamento ?? null)) cuerpo.id_departamento = area;
    }
    if (!Object.keys(cuerpo).length) return zona.replaceChildren(aviso('info', 'info', 'No hay cambios por guardar.'));
    guardar.disabled = true;
    try {
      const r = await api(`/profesionales/${persona.id_profesional}`, { metodo: 'PATCH', cuerpo });
      terminar(r.vinculado === false ? 'Cambios guardados. El perfil local quedó pendiente de sincronizar.' : 'Cambios guardados');
    } catch (error) {
      guardar.disabled = false;
      mostrarErrorDeFormulario(error, campos, zona);
    }
    return undefined;
  });

  const acciones = [];
  if (sup) {
    acciones.push(h('button', {
      class: 'btn peligro', type: 'button',
      onclick: () => confirmar({
        titulo: 'Eliminar cuenta',
        peligro: true,
        accion: 'Eliminar cuenta',
        cuerpo: [
          h('p', { text: `${nombreDe(persona)} dejará de existir para ${inst.nombre}: no podrá iniciar sesión ni volver a habilitarse.` }),
          aviso('info', 'shield-check', 'Sus consultas, citas y la bitácora se conservan con su nombre. El correo queda reservado.'),
        ],
        alConfirmar: () => api(`/profesionales/${persona.id_profesional}`, { metodo: 'DELETE' }).then(() => terminar('Cuenta eliminada')),
      }),
    }, ic('trash-2', 16), 'Eliminar'));
  }
  if (persona.estado === 'activa') {
    acciones.push(h('button', {
      class: 'btn peligro', type: 'button',
      onclick: () => confirmar({
        titulo: 'Deshabilitar cuenta',
        peligro: true,
        accion: 'Deshabilitar',
        cuerpo: [
          h('p', { text: `${nombreDe(persona)} no podrá iniciar sesión hasta que alguien vuelva a habilitar la cuenta.` }),
          aviso('info', 'shield-check', 'El acceso se corta de inmediato, sin esperar a que venza su sesión. Nada se borra.'),
        ],
        alConfirmar: () => cambiarEstado('inactiva', 'Cuenta deshabilitada'),
      }),
    }, ic('ban', 16), 'Deshabilitar'));
  } else {
    const desbloquear = persona.estado === 'bloqueada';
    acciones.push(h('button', {
      class: 'btn sec', type: 'button',
      onclick: async (e) => {
        e.currentTarget.disabled = true;
        const boton = e.currentTarget;
        try {
          await cambiarEstado('activa', desbloquear ? 'Cuenta desbloqueada' : 'Cuenta habilitada');
        } catch (error) {
          boton.disabled = false;
          zona.replaceChildren(aviso('crit', 'circle-alert', h('b', { text: error.message })));
        }
      },
    }, ic('circle-check', 16), desbloquear ? 'Desbloquear' : 'Habilitar'));
  }
  acciones.push(guardar);

  const restablecer = h('button', {
    class: 'btn sec', type: 'button',
    onclick: () => confirmar({
      titulo: 'Restablecer contraseña',
      accion: 'Restablecer',
      cuerpo: [h('p', { text: `Se generará una contraseña nueva para ${nombreDe(persona)} y se cerrarán sus sesiones abiertas.` })],
      alConfirmar: async () => {
        const r = await api(`/profesionales/${persona.id_profesional}/restablecer-contrasena`, { metodo: 'POST' });
        panel.cerrar();
        mostrarCredenciales({ persona, clave: r.contrasena_temporal, titulo: 'Contraseña restablecida', alCerrar: alCambiar });
      },
    }),
  }, ic('key-round', 16), 'Restablecer contraseña');

  const panel = lateral(nombreDe(persona), [
    h('div', { class: 'fila' }, chipEstado(persona.estado), persona.debe_cambiar_contrasena && persona.estado === 'activa' && chip('aviso', 'key-round', 'Debe cambiar su contraseña')),
    zona,
    h('dl', { class: 'lista-datos' },
      h('dt', { text: 'Correo' }), h('dd', { text: persona.correo }),
      h('dt', { text: 'Entidad' }), h('dd', { text: inst.nombre }),
      h('dt', { text: 'Rol' }), h('dd', { text: textoRol(persona.rol) }),
      h('dt', { text: 'Alta' }), h('dd', { text: fFecha(persona.creado_en) })),
    h('div', { class: 'dos' }, cN, cA),
    conArea && cAr,
    h('fieldset', null, h('legend', { class: 'leyenda', text: 'Permisos' }), permisos),
    h('section', { class: 'pila-s' }, h('h3', { text: 'Contraseña' }), h('div', null, restablecer), h('p', { class: 'hint', text: 'Genera una nueva y la muestra una sola vez.' })),
    h('p', { class: 'hint', text: 'La entidad no se cambia: para que alguien trabaje en otra, se crea una cuenta nueva en esa entidad.' }),
  ], acciones);
  return panel;
}

/* ---------- Lista ---------- */
export async function vistaUsuarios({ contenedor, params, repintar }) {
  const sup = esSuper();
  const inst = sesion.usuario.institucion && entidad(sesion.usuario.institucion);
  const encabezadoTexto = sup
    ? 'Quién entra a cada entidad, con qué rol y con qué permisos. Cada cuenta pertenece a una sola entidad.'
    : `Personal de ${inst.nombre}: altas, roles, permisos y acceso. Eliminar una cuenta o crearla en otra entidad lo hace la administración general.`;
  const filtros = { entidad: sup ? (params.entidad || '') : '', estado: params.estado || '' };
  let personal = [];
  const crear = h('button', { class: 'btn', type: 'button', onclick: () => abrirCreacion({ personal, alCambiar: repintar }) }, ic('user-plus', 16), 'Crear usuario');
  const encabezado = cabeza('Usuarios y accesos', encabezadoTexto, crear);
  const zona = h('div', { class: 'pila', 'aria-live': 'polite' });
  contenedor.replaceChildren(encabezado, zona);
  zona.append(cargando(6));
  contenedor.querySelector('h1').focus({ preventScroll: true });

  function pintar() {
    reflejar('usuarios', filtros);
    const deEntidad = personal.filter((p) => !filtros.entidad || p.institucion === filtros.entidad);
    const visibles = deEntidad
      .filter((p) => !filtros.estado || (filtros.estado === 'activa' ? !sinAcceso(p) : sinAcceso(p)))
      .sort((a, b) => ENTIDADES.findIndex((e) => e.id === a.institucion) - ENTIDADES.findIndex((e) => e.id === b.institucion)
        || (a.rol === 'administrador' ? -1 : b.rol === 'administrador' ? 1 : 0)
        || `${a.apellidos} ${a.nombres}`.localeCompare(`${b.apellidos} ${b.nombres}`, 'es'));
    const conPagos = personal.filter((p) => !sinAcceso(p) && p.permisos.includes('pagos:ver')).length;
    const pagosAplican = sup || ['hospital_general', 'centro_pediatrico'].includes(sesion.usuario.institucion);
    const activas = personal.filter((p) => !sinAcceso(p)).length;
    const sin = personal.length - activas;
    const conteo = (t, n) => `${t} ${fEntero(n)}`;

    zona.replaceChildren(
      cifras([
        { etiqueta: 'Cuentas activas', valor: fEntero(activas) },
        { etiqueta: 'Sin acceso', valor: fEntero(sin), clase: sin ? 'crit' : '', nota: 'Bloqueadas o deshabilitadas' },
        pagosAplican && { etiqueta: 'Con acceso a pagos', valor: fEntero(conPagos), nota: sup ? 'Hospital y Pediátrico' : null },
      ]),
      h('div', { class: 'filtros' },
        sup && segmento('Filtrar por entidad', [
          { valor: '', texto: conteo('Todas', personal.length) },
          ...ENTIDADES.map((e) => ({ valor: e.id, texto: conteo(e.corto, personal.filter((p) => p.institucion === e.id).length) })),
        ], filtros.entidad, (v) => { filtros.entidad = v; pintar(); }),
        segmento('Filtrar por estado', [
          { valor: '', texto: conteo('Todos', deEntidad.length) },
          { valor: 'activa', texto: conteo('Activas', deEntidad.filter((p) => !sinAcceso(p)).length) },
          { valor: 'sin', texto: conteo('Sin acceso', deEntidad.filter(sinAcceso).length) },
        ], filtros.estado, (v) => { filtros.estado = v; pintar(); })),
      !visibles.length
        ? vacio('users', personal.length ? 'Sin usuarios' : 'Aún no hay cuentas', personal.length ? 'No hay cuentas con estos filtros.' : 'Crea la primera cuenta con el botón de arriba.')
        : tabla(['Usuario', 'Correo', sup && 'Entidad', 'Rol', 'Área', 'Estado', 'Alta'], visibles.map((p) => {
          const abrir = () => abrirUsuario(p, { personal, alCambiar: repintar });
          return h('tr', { class: 'clic', onclick: abrir },
            h('td', null, h('button', { class: 'enlace', type: 'button', text: nombreDe(p), onclick: (e) => { e.stopPropagation(); abrir(); } })),
            h('td', { class: 'correo', text: p.correo }),
            sup && h('td', { text: entidad(p.institucion).corto }),
            h('td', null, p.rol === 'administrador' ? chip('info', 'shield-check', textoRol(p.rol)) : textoRol(p.rol)),
            h('td', { text: p.departamento || '—' }),
            h('td', null, chipEstado(p.estado)),
            h('td', { class: 'num', text: fFecha(p.creado_en) }));
        })),
      h('p', { class: 'hint', text: sup ? 'La cuenta de superusuario no aparece aquí: no pertenece a ninguna entidad y no tiene permisos clínicos.' : 'Las cuentas de administración solo las gestiona la administración general.' }));
  }

  try {
    personal = await api('/profesionales', { params: { limite: 500 } });
    pintar();
  } catch (error) {
    zona.replaceChildren(estadoDeError(error, repintar));
  }
}
