/* Cada institucion agrega su modulo sin tocar el marco de la aplicacion.
   Un modulo declara: aplica(usuario), nav(usuario) -> grupos y vistas { ruta: fn(contexto) }. */

const modulos = [];

export const registrarModulo = (modulo) => modulos.push(modulo);

export const moduloDe = (usuario) => modulos.find((m) => m.aplica(usuario)) || null;
