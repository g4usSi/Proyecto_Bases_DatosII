/* Pacientes del Hospital General: buscador compartido con la ficha del hospital. */
import { crearVistaPacientes } from '../compartido/pacientes.js';
import { pintarFicha } from './ficha.js';

export const vistaPacientes = crearVistaPacientes(pintarFicha);
