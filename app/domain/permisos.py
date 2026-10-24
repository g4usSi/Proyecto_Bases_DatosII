"""Codigos de permiso (tabla identidad.permiso en PostgreSQL)."""

PACIENTES_LEER = "pacientes:leer"
PACIENTES_REGISTRAR = "pacientes:registrar"
HISTORIALES_LEER = "historiales:leer"  # diagnosticos, consultas, alergias, odontograma
CONSULTAS_REGISTRAR = "consultas:registrar"
HISTORIALES_ARCHIVAR = "historiales:archivar"
CITAS_LEER = "citas:leer"
CITAS_GESTIONAR = "citas:gestionar"

# Igual que identidad.permisos_clinicos() en 006_rol_secretaria_citas.sql.
PERMISOS_CLINICOS = frozenset({HISTORIALES_LEER, CONSULTAS_REGISTRAR})

# La secretaria tampoco puede dar de baja (archivar) un historial.
# Igual que identidad.permisos_vedados_secretaria() en 007_secretaria_restricciones.sql.
PERMISOS_VEDADOS_SECRETARIA = PERMISOS_CLINICOS | {HISTORIALES_ARCHIVAR}

# La secretaria existe solo en la clinica odontologica (CHECK en la misma migracion 007).
INSTITUCION_DE_SECRETARIA = "clinica_odontologica"

PERMISOS_POR_ROL = {
    "secretaria": frozenset({PACIENTES_LEER, PACIENTES_REGISTRAR, CITAS_LEER, CITAS_GESTIONAR}),
}
PERMISOS_POR_DEFECTO = frozenset({PACIENTES_LEER})
