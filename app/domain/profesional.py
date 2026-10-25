from dataclasses import dataclass

# Roles administrativos: pueden agendar, pero no tienen agenda propia de pacientes.
ROLES_SIN_ATENCION = frozenset({"secretaria", "administrativo"})


@dataclass(frozen=True, slots=True)
class ProfesionalLocal:
    """Perfil del profesional dentro de la base clinica de su institucion.

    El identificador es el UUID de la identidad central (PostgreSQL). La base
    clinica nunca guarda correo ni contrasena.
    """

    id_profesional: str
    nombres: str
    apellidos: str
    rol: str
    activo: bool = True

    @property
    def atiende_pacientes(self) -> bool:
        return self.activo and self.rol not in ROLES_SIN_ATENCION
