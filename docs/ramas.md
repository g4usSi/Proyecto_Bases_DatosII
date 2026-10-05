# Trabajo por ramas

La base común incluye FastAPI, identidad central, scripts de tres motores y sus
adaptadores iniciales de lectura. Las ramas siguientes completarán escrituras e
historiales conservando los contratos compartidos. Todavía no se han creado ramas.

## Flujo sugerido

Una vez revisada y guardada la base en `main`, crear ramas como:

| Rama sugerida | Adaptador | Institución |
| --- | --- | --- |
| `feature/postgresql` | PostgreSQL | Hospital general |
| `feature/mysql` | MySQL | Centro pediátrico |
| `feature/mongodb` | MongoDB | Laboratorio clínico |
| `feature/firestore` | Cloud Firestore | Clínica odontológica |

Ejemplo para empezar PostgreSQL:

```powershell
git switch main
git switch -c feature/postgresql
```

Las ramas deben partir de la misma base guardada. Antes de integrar una rama,
incorporar los cambios recientes de `main` y resolver los contratos compartidos.
Los nombres son sugerencias; esta preparación no crea ramas ni commits.

## Alcance de una rama de motor

- Implementar repositorios y unidad de trabajo dentro de su carpeta de infraestructura.
- Ampliar los drivers en `requirements.txt` al necesitar capacidades adicionales.
- Mantener scripts y migraciones en `database/<motor>/`; MongoDB conserva el script
  inicial en la raíz según lo solicitado, sin duplicar dos versiones del modelo.
- Agregar configuración local a `.env.example`, sin credenciales reales.
- Registrar su fábrica de unidad de trabajo en la composición de la aplicación.
- Extender Compose o documentar el emulador correspondiente.
- Probar persistencia, integridad y aislamiento contra el motor real.
- Documentar modelado, transacciones y seguridad para el informe comparativo.

`database/` y los drivers de PostgreSQL, MySQL y MongoDB ya forman parte de esta base.
La identidad central es compartida: ninguna rama debe crear otro login ni guardar
contrasenas en su base clínica. Firestore agregará su SDK/configuración al implementarse.

## Integración final

Trabajar por ramas organiza el desarrollo. Para la entrega, los cuatro adaptadores
deben estar fusionados en una aplicación: dos usuarios de instituciones diferentes
deben poder operar al mismo tiempo, cada uno sobre su motor.

Cambiar de rama para demostrar un motor no cumple el enrutamiento por usuario del
enunciado. Tampoco debe existir una variable global que cambie el motor activo de
todas las solicitudes cuando inicia sesión un usuario.

Las pruebas comunes verificarán el comportamiento equivalente. Cada rama agregará
pruebas de integración específicas para las garantías de su motor.
