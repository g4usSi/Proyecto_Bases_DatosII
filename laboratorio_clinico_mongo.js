// Ejecutar con mongosh, no con Node ni en el navegador.
// Inicializacion idempotente: conserva documentos, valida nuevas escrituras y crea indices.
// Uso: mongosh <URI autenticada> --file laboratorio_clinico_mongo.js
// MongoDB 8+. Documento de decisiones: docs/modelo_laboratorio.md.
(() => {
  const laboratorio = db.getSiblingDB("laboratorio_clinico");
  const texto = { bsonType: "string", minLength: 1, pattern: "\\S" };
  const uuid = { bsonType: "string", pattern: "^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$" };
  const fecha = { bsonType: "date" };
  const numero = { bsonType: ["int", "long", "double", "decimal"] };
  const objetoId = { bsonType: "objectId" };

  function asegurarColeccion(nombre, esquema, reglas = []) {
    const validator = { $and: [{ $jsonSchema: esquema }, ...reglas] };
    const opciones = { validator, validationLevel: "strict", validationAction: "error" };
    if (laboratorio.getCollectionInfos({ name: nombre }).length === 0) {
      laboratorio.createCollection(nombre, opciones);
    } else {
      const respuesta = laboratorio.runCommand({ collMod: nombre, ...opciones });
      if (respuesta.ok !== 1) {
        throw new Error(`No se pudo actualizar el validador de ${nombre}: ${respuesta.errmsg}`);
      }
    }
  }

  asegurarColeccion("pacientes", {
    bsonType: "object",
    required: ["_id", "numero_expediente", "nombres", "apellidos", "estado", "creado_en", "actualizado_en"],
    properties: {
      _id: objetoId, numero_expediente: texto, nombres: texto, apellidos: texto,
      fecha_nacimiento: fecha,
      contacto: { bsonType: "object", properties: {
        telefono: texto, correo: texto, direccion: texto
      } },
      alergias_evaluadas: { bsonType: "bool" },
      alergias: { bsonType: "array", items: { bsonType: "object",
        required: ["sustancia"], properties: {
          sustancia: texto, reaccion: texto, severidad: texto
        }
      } },
      estado: { enum: ["Activo", "Archivado"] },
      fecha_baja: fecha, motivo_baja: texto,
      creado_en: fecha, actualizado_en: fecha
    }
  }, [{ $or: [
    { estado: "Activo", fecha_baja: { $exists: false }, motivo_baja: { $exists: false } },
    { estado: "Archivado", fecha_baja: { $type: "date" }, motivo_baja: { $type: "string", $regex: "\\S" } }
  ] }]);
  laboratorio.pacientes.createIndex({ numero_expediente: 1 }, { unique: true, name: "uq_expediente" });
  laboratorio.pacientes.createIndex({ apellidos: 1, nombres: 1 }, { name: "ix_nombre" });
  laboratorio.pacientes.createIndex({ estado: 1, _id: 1 }, { name: "ix_estado" });

  asegurarColeccion("profesionales", {
    bsonType: "object", required: ["_id", "id_profesional_central", "nombres", "apellidos", "activo"],
    properties: {
      _id: objetoId, id_profesional_central: uuid, nombres: texto, apellidos: texto,
      especialidad: texto, registro_profesional: texto, activo: { bsonType: "bool" }
    }
  });
  laboratorio.profesionales.createIndex({ id_profesional_central: 1 }, { unique: true, name: "uq_identidad" });

  asegurarColeccion("catalogo_pruebas", {
    bsonType: "object", required: ["_id", "codigo", "nombre", "version", "activo", "parametros"],
    properties: {
      _id: objetoId, codigo: texto, nombre: texto,
      version: { bsonType: "int", minimum: 1 }, activo: { bsonType: "bool" },
      tipo_muestra: texto, indicaciones: texto,
      parametros: { bsonType: "array", minItems: 1, items: {
        bsonType: "object", required: ["codigo", "nombre", "tipo_valor"],
        properties: {
          codigo: texto, nombre: texto, unidad: texto,
          tipo_valor: { enum: ["numerico", "texto", "booleano"] },
          referencia: { bsonType: "object", properties: {
            minimo: numero, maximo: numero, descripcion: texto, poblacion: texto
          } }
        }
      } }
    }
  });
  laboratorio.catalogo_pruebas.createIndex({ codigo: 1, version: 1 }, { unique: true, name: "uq_prueba_version" });
  laboratorio.catalogo_pruebas.createIndex({ activo: 1, nombre: 1 }, { name: "ix_catalogo_activo" });

  // Una consulta con sus diagnosticos/tratamientos/recetas = una escritura atomica.
  // Cada consulta es un documento independiente; nunca un array ilimitado en paciente.
  asegurarColeccion("consultas", {
    bsonType: "object",
    required: ["_id", "id_paciente", "id_profesional_central", "fecha_hora", "motivo", "diagnosticos", "tratamientos", "recetas"],
    properties: {
      _id: objetoId, id_paciente: objetoId, id_profesional_central: uuid,
      fecha_hora: fecha, motivo: texto, notas: texto,
      diagnosticos: { bsonType: "array", maxItems: 100, items: {
        bsonType: "object", required: ["descripcion"],
        properties: { descripcion: texto, codigo: texto, sistema_codigo: texto }
      } },
      tratamientos: { bsonType: "array", maxItems: 100, items: {
        bsonType: "object", required: ["descripcion"], properties: { descripcion: texto }
      } },
      recetas: { bsonType: "array", maxItems: 100, items: {
        bsonType: "object", required: ["medicamento", "dosis", "frecuencia"],
        properties: {
          medicamento: texto, dosis: texto, frecuencia: texto, via_administracion: texto,
          duracion_dias: { bsonType: "int", minimum: 1 }, instrucciones: texto
        }
      } }
    }
  });
  laboratorio.consultas.createIndex({ id_paciente: 1, fecha_hora: -1, _id: -1 }, { name: "ix_historial" });
  laboratorio.consultas.createIndex({ id_profesional_central: 1, fecha_hora: -1 }, { name: "ix_profesional" });

  // La orden conserva una copia de la prueba/version y del rango usado en ese examen.
  // Cambiar el catalogo no debe reinterpretar un resultado historico.
  const valorResultado = {
    bsonType: "object", required: ["codigo", "nombre", "tipo_valor", "valor"],
    properties: {
      codigo: texto, nombre: texto, unidad: texto,
      tipo_valor: { enum: ["numerico", "texto", "booleano"] },
      valor: { bsonType: ["int", "long", "double", "decimal", "string", "bool"] },
      referencia: { bsonType: "object", properties: {
        minimo: numero, maximo: numero, descripcion: texto, poblacion: texto
      } },
      interpretacion: texto
    },
    oneOf: [
      { properties: { tipo_valor: { enum: ["numerico"] }, valor: numero } },
      { properties: { tipo_valor: { enum: ["texto"] }, valor: texto } },
      { properties: { tipo_valor: { enum: ["booleano"] }, valor: { bsonType: "bool" } } }
    ]
  };
  asegurarColeccion("ordenes_laboratorio", {
    bsonType: "object",
    required: ["_id", "numero_orden", "id_paciente", "id_consulta", "id_profesional_central", "estado", "solicitada_en", "pruebas"],
    properties: {
      _id: objetoId, numero_orden: texto, id_paciente: objetoId, id_consulta: objetoId,
      id_profesional_central: uuid, solicitada_en: fecha,
      estado: { enum: ["Solicitada", "En proceso", "Validada", "Cancelada"] },
      validada_en: fecha, validada_por: uuid, motivo_cancelacion: texto,
      muestras: { bsonType: "array", maxItems: 100, items: {
        bsonType: "object", required: ["codigo", "tipo", "tomada_en"], properties: {
          codigo: texto, tipo: texto, tomada_en: fecha, recibida_en: fecha,
          condicion: texto, observaciones: texto
        }
      } },
      pruebas: { bsonType: "array", minItems: 1, maxItems: 100, items: {
        bsonType: "object", required: ["codigo", "nombre", "version", "resultados"],
        properties: {
          codigo: texto, nombre: texto, version: { bsonType: "int", minimum: 1 },
          resultados: { bsonType: "array", maxItems: 300, items: valorResultado },
          observaciones: texto
        }
      } }
    }
  }, [{ $or: [
    { estado: "Validada", validada_en: { $type: "date" }, validada_por: { $type: "string" },
      $expr: { $allElementsTrue: [{ $map: { input: "$pruebas", as: "p",
        in: { $gt: [{ $size: "$$p.resultados" }, 0] }
      } }] } },
    { estado: { $in: ["Solicitada", "En proceso", "Cancelada"] },
      validada_en: { $exists: false }, validada_por: { $exists: false } }
  ] }, { $or: [
    { estado: "Cancelada", motivo_cancelacion: { $regex: "\\S" } },
    { estado: { $ne: "Cancelada" }, motivo_cancelacion: { $exists: false } }
  ] }]);
  laboratorio.ordenes_laboratorio.createIndex({ numero_orden: 1 }, { unique: true, name: "uq_orden" });
  laboratorio.ordenes_laboratorio.createIndex({ id_paciente: 1, solicitada_en: -1, _id: -1 }, { name: "ix_orden_historial" });
  laboratorio.ordenes_laboratorio.createIndex({ id_consulta: 1 }, { name: "ix_orden_consulta" });
  laboratorio.ordenes_laboratorio.createIndex({ estado: 1, solicitada_en: 1 }, { name: "ix_cola_trabajo" });

  // Solo el contenedor de desarrollo provee esta variable. No incrustar contrasenas.
  if (process.env.MONGO_APP_PASSWORD && !laboratorio.getUser("historiales_app")) {
    laboratorio.createUser({ user: "historiales_app", pwd: process.env.MONGO_APP_PASSWORD,
      roles: [{ role: "readWrite", db: "laboratorio_clinico" }] });
  }
  print("Laboratorio Clinico: 5 colecciones, validadores e indices listos. Sin pacientes de ejemplo.");
})();
