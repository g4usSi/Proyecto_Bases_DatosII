# Secretos locales

Esta carpeta guarda archivos que **no se suben a Git** (todo excepto este README está en
`.gitignore` y `.dockerignore`).

## Clave de Firebase (Clínica Odontológica)

La Clínica Odontológica usa Cloud Firestore. La API necesita la clave JSON de una cuenta de
servicio de Firebase, que se entrega por separado (no está en el repositorio).

1. Guardar el archivo recibido exactamente como:

   ```text
   .secrets/firebase-adminsdk.json
   ```

2. Comprobarla (opcional):

   ```powershell
   .\.venv\Scripts\python.exe -m scripts.probar_firestore
   ```

   Debe terminar con `OK: escritura, lectura y borrado funcionan`.

3. Si la API ya estaba levantada, reiniciarla:

   ```powershell
   docker compose --profile api restart api
   ```

   <http://127.0.0.1:8000/health/ready> debe mostrar `"clinica_odontologica": "ok"`.

- **Docker** monta esta carpeta en la API como solo lectura
  (`/run/secrets/historiales/firebase-adminsdk.json`); la clave nunca entra en la imagen.
- **En consola** la API la lee desde la ruta de `HISTORIALES_FIRESTORE_CREDENTIALS` en `.env`
  (por defecto `.secrets/firebase-adminsdk.json`).
- Sin la clave, la API arranca igual: los otros tres motores y la administración funcionan,
  y solo las operaciones de odontología responden 503.

No compartir ni subir la clave a Git: da acceso de escritura a la base de Firestore.
