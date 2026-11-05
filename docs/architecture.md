# Arquitectura distribuida

La arquitectura sigue el documento tecnico de On Dress Me:

La computadora central A ahora es `desktop-vs5lm9k` (Windows), con IP Tailscale
`100.82.214.123`. Todas las URLs de los demas equipos deben apuntar a esa IP;
no uses la direccion anterior `100.120.77.108`.

| Equipo | Responsabilidad | Puerto sugerido |
|---|---|---:|
| A | FastAPI, OpenCV/NumPy, Redis, almacenamiento y coordinacion | 8000 |
| B | React, Three.js, React Three Fiber y experiencia web | 5173 |
| C | Worker futuro de avatar corporal 3D | 8101 |
| D | Worker futuro de generacion de outfits | 8102 |

El frontend solo conoce `VITE_API_BASE_URL`. El backend es el unico modulo que conoce Redis y los workers. Los archivos se guardan en el almacenamiento persistente de A y los mensajes contienen referencias relativas, nunca rutas locales que otro equipo no pueda resolver.

## Flujo de trabajos

1. B envia una solicitud HTTP a A.
2. A crea un `job_id`, guarda el archivo (si aplica) y publica un mensaje JSON en `avatar_jobs` u `outfit_jobs`.
3. C o D consume el mensaje y actualiza el estado en Redis.
4. El worker envia el resultado o error a A mediante el endpoint interno.
5. B consulta `GET /api/jobs/{job_id}` y muestra el estado o el recurso persistente.

Estados permitidos: `queued`, `running`, `completed`, `failed`.

## Endpoints preparados

- `GET /health`
- `POST /api/avatar/jobs`
- `POST /api/outfits/jobs`
- `GET /api/jobs/{job_id}`
- `POST /api/internal/jobs/{job_id}/result`

Colorimetria, perfiles y armario tienen los espacios de API preparados, pero no se inventan resultados en esta etapa.
