# Climate Admin Dashboard

Panel administrativo para consultar y validar la configuración del pipeline de boletines agroclimáticos. La programación (período de envío), MongoDB y sensores son siempre de solo lectura; la política de correo y los destinatarios tienen edición controlada.

Lee `pipeline.yaml` y `email.yaml` desde `CLIMATE_CONFIG_DIR`. Solo modifica los campos editables mediante un `POST` validado. Cada campo puede activar o desactivar el envío y los destinatarios primarios se separan con `;`; el CC se configura una sola vez para todos. No conecta a MongoDB, no envía correo y no reinicia contenedores. Las contraseñas, archivos de credenciales y secretos no se muestran en la respuesta.

## Prueba local

```bash
cp .env.example .env.local
docker compose --env-file .env.local -f compose.yaml -f compose.local.yaml up --build -d
open http://127.0.0.1:8070/
docker compose --env-file .env.local -f compose.yaml -f compose.local.yaml logs -f climate-admin-dashboard
curl -s http://127.0.0.1:8070/api/health | python3 -m json.tool
curl -s http://127.0.0.1:8070/api/config | python3 -m json.tool
```

Para leer la configuración real local del repositorio de reporting, ajustar `CLIMATE_CONFIG_HOST` en `.env.local` a la ruta absoluta de `cerezas_web_data/config`.

## Integración con el sitio

El sitio principal mantiene la autenticación y expone el dashboard en `/admin/config/`. El enlace solo aparece en el menú de administración y la ruta exige `session.role == 0`. En producción el servicio debe estar en `FIC-app-network` con el nombre `climate-admin-dashboard`; el sitio lo consulta mediante `http://climate-admin-dashboard:8070`.

Para una prueba local, `compose.local.yaml` conecta el dashboard a la red
`fic-local-network` (configurable con `ADMIN_DASHBOARD_NETWORK`). El contenedor
del sitio debe iniciarse en esa misma red y usar
`ADMIN_CONFIG_UPSTREAM_URL=http://climate-admin-dashboard:8070`.

```bash
docker compose --env-file .env.local -f compose.yaml -f compose.production.yaml up --build -d
```

El inicio del período, la temporada, MongoDB, rutas, modelos y filtros quedan fuera de la edición. La fecha final sí se puede modificar, pero debe ser el día 2 del mes; el formulario usa el año actual solo para mostrar la fecha completa. En producción, solo `pipeline.yaml` y `email.yaml` tienen montajes de escritura; el resto del directorio continúa protegido.

