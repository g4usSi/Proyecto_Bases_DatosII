"""Codigos de permiso (tabla identidad.permiso en PostgreSQL)."""

PACIENTES_LEER = "pacientes:leer"
PACIENTES_REGISTRAR = "pacientes:registrar"
HISTORIALES_LEER = "historiales:leer"  # diagnosticos, consultas, alergias, odontograma
CONSULTAS_REGISTRAR = "consultas:registrar"
HISTORIALES_ARCHIVAR = "historiales:archivar"
CITAS_LEER = "citas:leer"
CITAS_GESTIONAR = "citas:gestionar"
LABORATORIO_RESULTADOS = "laboratorio:resultados"  # tomar muestras y registrar resultados
LABORATORIO_VALIDAR = "laboratorio:validar"  # validar una orden (despues no se modifica)
# Solo el rol administrador (uno por institucion): altas, permisos, estado y contrasenas del
# personal de SU institucion. Nunca se combina con permisos clinicos (012_administracion).
PROFESIONALES_ADMINISTRAR = "profesionales:administrar"
# Hospital General: marcar camas en limpieza/mantenimiento/disponibles (013_camas_ingresos).
CAMAS_GESTIONAR = "camas:gestionar"
# Cobros y pagos (Hospital General y Centro Pediatrico): ver montos / registrar movimientos.
PAGOS_VER = "pagos:ver"
PAGOS_REGISTRAR = "pagos:registrar"
PLATAFORMA_ADMINISTRAR = "plataforma:administrar"

# Igual que identidad.permisos_clinicos() en 006_rol_secretaria_citas.sql.
PERMISOS_CLINICOS = frozenset({HISTORIALES_LEER, CONSULTAS_REGISTRAR})

# La secretaria tampoco puede dar de baja (archivar) un historial ni tocar el laboratorio.
# Igual que identidad.permisos_vedados_secretaria() en 007 y 011.
PERMISOS_VEDADOS_SECRETARIA = PERMISOS_CLINICOS | {
    HISTORIALES_ARCHIVAR,
    LABORATORIO_RESULTADOS,
    LABORATORIO_VALIDAR,
}

# La secretaria existe solo en la clinica odontologica (CHECK en la misma migracion 007).
INSTITUCION_DE_SECRETARIA = "clinica_odontologica"

PERMISOS_POR_ROL = {
    "laboratorista": frozenset({PACIENTES_LEER, LABORATORIO_RESULTADOS, LABORATORIO_VALIDAR}),
    "secretaria": frozenset({PACIENTES_LEER, PACIENTES_REGISTRAR, CITAS_LEER, CITAS_GESTIONAR}),
    "administrador": frozenset({PROFESIONALES_ADMINISTRAR}),
    "superusuario": frozenset({PLATAFORMA_ADMINISTRAR, PAGOS_VER}),
}
PERMISOS_POR_DEFECTO = frozenset({PACIENTES_LEER})
