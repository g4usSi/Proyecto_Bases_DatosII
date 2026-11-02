/* Centro Pediatrico: personal clinico. La administracion la atiende su propio modulo,
   que se registra antes y por eso se queda con las cuentas de administrador. */
import { registrarModulo } from './registro.js';
import { vistaPacientes } from '../vistas/pediatrico/pacientes.js';
import { vistaRegistrar } from '../vistas/pediatrico/registrar.js';

registrarModulo({
  aplica: (usuario) => usuario.institucion === 'centro_pediatrico',
  nav: (usuario) => {
    const tiene = (permiso) => usuario.permisos.includes(permiso);
    const items = [];
    if (tiene('pacientes:leer')) items.push({ ruta: 'pacientes', icono: 'users', texto: 'Pacientes' });
    if (tiene('pacientes:registrar')) items.push({ ruta: 'registrar', icono: 'user-plus', texto: 'Registrar paciente' });
    return [{ items }];
  },
  vistas: {
    pacientes: vistaPacientes,
    registrar: vistaRegistrar,
  },
});
