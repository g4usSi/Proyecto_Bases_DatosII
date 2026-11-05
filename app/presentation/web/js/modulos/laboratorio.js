/* Laboratorio Clinico: laboratoristas y medicos. La administracion la atiende su propio modulo,
   que se registra antes y por eso se queda con las cuentas de administrador. */
import { registrarModulo } from './registro.js';
import { vistaOrdenes } from '../vistas/laboratorio/tablero.js';
import { vistaPacientes } from '../vistas/laboratorio/pacientes.js';
import { vistaCatalogo } from '../vistas/laboratorio/catalogo.js';
import { vistaRegistrar } from '../vistas/clinica/registrar.js';
import { vistaAgenda } from '../vistas/clinica/agenda.js';

registrarModulo({
  aplica: (usuario) => usuario.institucion === 'laboratorio_clinico',
  nav: (usuario) => {
    const tiene = (permiso) => usuario.permisos.includes(permiso);
    const lab = tiene('historiales:leer') || tiene('laboratorio:resultados');
    const items = [];
    if (lab) items.push({ ruta: 'ordenes', icono: 'flask-conical', texto: 'Órdenes' });
    if (tiene('pacientes:leer')) items.push({ ruta: 'pacientes', icono: 'users', texto: 'Pacientes' });
    if (lab) items.push({ ruta: 'catalogo', icono: 'test-tubes', texto: 'Catálogo de pruebas' });
    if (tiene('pacientes:registrar')) items.push({ ruta: 'registrar', icono: 'user-plus', texto: 'Registrar paciente' });
    if (tiene('citas:leer')) items.push({ ruta: 'agenda', icono: 'calendar-days', texto: 'Agenda de citas' });
    return [{ items }];
  },
  vistas: {
    ordenes: vistaOrdenes,
    pacientes: vistaPacientes,
    catalogo: vistaCatalogo,
    registrar: vistaRegistrar,
    agenda: vistaAgenda,
  },
});
