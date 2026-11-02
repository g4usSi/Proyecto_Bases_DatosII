/* Centro Pediatrico: personal clinico. La administracion la atiende su propio modulo,
   que se registra antes y por eso se queda con las cuentas de administrador. */
import { registrarModulo } from './registro.js';
import { vistaPacientes } from '../vistas/pediatrico/pacientes.js';
import { vistaRegistrar } from '../vistas/pediatrico/registrar.js';
import { vistaAgenda } from '../vistas/pediatrico/agenda.js';
import { vistaCatalogoVacunas } from '../vistas/pediatrico/vacunacion.js';

registrarModulo({
  aplica: (usuario) => usuario.institucion === 'centro_pediatrico',
  nav: (usuario) => {
    const tiene = (permiso) => usuario.permisos.includes(permiso);
    const items = [];
    if (tiene('pacientes:leer')) items.push({ ruta: 'pacientes', icono: 'users', texto: 'Pacientes' });
    if (tiene('pacientes:registrar')) items.push({ ruta: 'registrar', icono: 'user-plus', texto: 'Registrar paciente' });
    if (tiene('citas:leer')) items.push({ ruta: 'agenda', icono: 'calendar-days', texto: 'Agenda de citas' });
    if (tiene('historiales:leer')) items.push({ ruta: 'vacunas', icono: 'syringe', texto: 'Catálogo de vacunas' });
    return [{ items }];
  },
  vistas: {
    pacientes: vistaPacientes,
    registrar: vistaRegistrar,
    agenda: vistaAgenda,
    vacunas: vistaCatalogoVacunas,
  },
});
