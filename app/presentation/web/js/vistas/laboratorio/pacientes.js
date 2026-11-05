/* Pacientes del Laboratorio Clinico: buscador compartido con la ficha del laboratorio. */
import { crearVistaPacientes } from '../compartido/pacientes.js';
import { pintarFicha } from './ficha.js';

export const vistaPacientes = crearVistaPacientes(pintarFicha);
