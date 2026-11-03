/* Clinica Odontologica: odontologos y secretaria. La administracion la atiende su propio modulo,
   que se registra antes y por eso se queda con las cuentas de administrador. */
import { registrarModulo } from './registro.js';
import { vistaPacientes } from '../vistas/clinica/pacientes.js';
import { vistaRegistrar } from '../vistas/clinica/registrar.js';
import { vistaAgenda } from '../vistas/clinica/agenda.js';

registrarModulo({
  aplica: (usuario) => usuario.institucion === 'clinica_odontologica',
  nav: (usuario) => {
    const tiene = (permiso) => usuario.permisos.includes(permiso);
    const items = [];
    if (tiene('pacientes:leer')) items.push({ ruta: 'pacientes', icono: 'users', texto: 'Pacientes' });
    if (tiene('pacientes:registrar')) items.push({ ruta: 'registrar', icono: 'user-plus', texto: 'Registrar paciente' });
    if (tiene('citas:leer')) items.push({ ruta: 'agenda', icono: 'calendar-days', texto: 'Agenda de citas' });
    return [{ items }];
  },
  vistas: {
    pacientes: vistaPacientes,
    registrar: vistaRegistrar,
    agenda: vistaAgenda,
  },
});
