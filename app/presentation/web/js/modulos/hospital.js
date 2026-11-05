/* Hospital General: medicos y enfermeria. La administracion la atiende su propio modulo,
   que se registra antes y por eso se queda con las cuentas de administrador. */
import { registrarModulo } from './registro.js';
import { vistaInicio } from '../vistas/hospital/inicio.js';
import { vistaPacientes } from '../vistas/hospital/pacientes.js';
import { vistaEmergencias } from '../vistas/hospital/emergencias.js';
import { vistaCamas } from '../vistas/hospital/camas.js';
import { vistaAtenciones } from '../vistas/hospital/atenciones.js';
import { vistaPagos } from '../vistas/hospital/pagos.js';
import { vistaRegistrar } from '../vistas/clinica/registrar.js';
import { vistaAgenda } from '../vistas/clinica/agenda.js';

registrarModulo({
  aplica: (usuario) => usuario.institucion === 'hospital_general',
  nav: (usuario) => {
    const tiene = (permiso) => usuario.permisos.includes(permiso);
    const inicio = [];
    if (tiene('pacientes:leer')) inicio.push({ ruta: 'inicio', icono: 'house', texto: 'Inicio' });
    const atencion = [];
    if (tiene('pacientes:leer')) atencion.push({ ruta: 'pacientes', icono: 'users', texto: 'Pacientes' });
    if (tiene('pacientes:registrar')) atencion.push({ ruta: 'registrar', icono: 'user-plus', texto: 'Registrar paciente' });
    if (tiene('historiales:leer')) atencion.push({ ruta: 'emergencias', icono: 'siren', texto: 'Emergencias' });
    if (tiene('pacientes:leer')) atencion.push({ ruta: 'camas', icono: 'bed-double', texto: 'Camas' });
    if (tiene('citas:leer')) atencion.push({ ruta: 'agenda', icono: 'calendar-days', texto: 'Agenda de citas' });
    if (tiene('historiales:leer')) atencion.push({ ruta: 'atenciones', icono: 'activity', texto: 'Atenciones' });
    const cobros = [];
    if (tiene('pagos:ver')) cobros.push({ ruta: 'pagos', icono: 'banknote', texto: 'Pagos' });
    return [
      { items: inicio },
      { titulo: 'Atención', items: atencion },
      { titulo: 'Cobros', items: cobros },
    ].filter((g) => g.items.length);
  },
  vistas: {
    inicio: vistaInicio,
    pacientes: vistaPacientes,
    registrar: vistaRegistrar,
    emergencias: vistaEmergencias,
    camas: vistaCamas,
    agenda: vistaAgenda,
    atenciones: vistaAtenciones,
    pagos: vistaPagos,
  },
});
