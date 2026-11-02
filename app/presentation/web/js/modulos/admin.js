/* Administracion: superusuario de plataforma y administrador de cada entidad. */
import { registrarModulo } from './registro.js';
import { vistaResumen } from '../vistas/admin/resumen.js';
import { vistaUsuarios } from '../vistas/admin/usuarios.js';
import { vistaBitacora } from '../vistas/admin/bitacora.js';
import { vistaCobros } from '../vistas/admin/cobros.js';

const tiene = (usuario, permiso) => usuario.permisos.includes(permiso);

registrarModulo({
  aplica: (usuario) => tiene(usuario, 'plataforma:administrar') || tiene(usuario, 'profesionales:administrar'),
  nav: (usuario) => {
    const grupos = [{
      items: [
        { ruta: 'resumen', icono: 'house', texto: 'Resumen' },
        { ruta: 'usuarios', icono: 'user-cog', texto: 'Usuarios y accesos' },
        { ruta: 'bitacora', icono: 'history', texto: 'Bitácora' },
      ],
    }];
    if (usuario.institucion === null && tiene(usuario, 'pagos:ver')) {
      grupos.push(
        { titulo: 'Hospital General', items: [{ ruta: 'cobros/hospital_general', vista: 'cobros', icono: 'banknote', texto: 'Pagos' }] },
        { titulo: 'Centro Pediátrico', items: [{ ruta: 'cobros/centro_pediatrico', vista: 'cobros', icono: 'receipt', texto: 'Facturación' }] },
      );
    }
    return grupos;
  },
  vistas: {
    resumen: vistaResumen,
    usuarios: vistaUsuarios,
    bitacora: vistaBitacora,
    cobros: vistaCobros,
  },
});
