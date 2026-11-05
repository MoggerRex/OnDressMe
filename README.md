# On Dress Me

On Dress Me es una plataforma web para colorimetria facial, armario digital, avatar corporal 3D y recomendaciones de outfits. El repositorio conserva el frontend React existente y prepara la separacion en cuatro computadoras descrita en `docs/architecture.md`.

## Arquitectura

```text
Computadora B (frontend) --HTTP--> Computadora A (backend central)
                                      |
                                      +--Redis: avatar_jobs--> Computadora C (worker avatar)
                                      +--Redis: outfit_jobs--> Computadora D (worker outfits)
                                      |
                                      +--backend/storage: archivos persistentes
```

Tailscale se usa para la red privada entre equipos. La computadora central A es
`desktop-vs5lm9k` (Windows), actualmente en `100.82.214.123`; las direcciones
operativas se configuran mediante variables de entorno. Redis coordina trabajos
y estados, pero no almacena fotografias ni archivos 3D.

## Estructura

- `backend/`: API FastAPI, contratos, coordinacion de trabajos y almacenamiento central.
- `frontend/`: aplicacion React/Vite, Three.js y React Three Fiber existente.
- `workers/avatar/`: punto de entrada preparado para SAM 3D Body; no incluye el modelo.
- `workers/outfits/`: punto de entrada preparado para Ollama/Llama; no incluye el modelo.
- `shared/contracts/`: contratos JSON compartidos entre servicios.
- `infra/`: Redis local para desarrollo; no se publica a Internet.
- `docs/`: instrucciones por computadora y decisiones de arquitectura.

## Requisitos

- Python 3.11 o posterior para backend y workers.
- Node.js 20 o posterior para el frontend.
- Redis accesible solo por la red privada de Tailscale.
- Los modelos de IA, CUDA, PyTorch, SAM 3D Body y Llama se instalaran en una fase posterior.

## Ejecucion rapida

1. Levanta Redis en la computadora A: `docker compose -f infra/docker-compose.yml up -d redis`.
2. Configura y ejecuta el backend siguiendo [docs/computer-a-backend.md](docs/computer-a-backend.md).
3. Configura la URL del backend en `frontend/.env` y ejecuta [docs/computer-b-frontend.md](docs/computer-b-frontend.md).
4. Prepara los workers con [docs/computer-c-avatar.md](docs/computer-c-avatar.md) y [docs/computer-d-outfits.md](docs/computer-d-outfits.md).

Los workers fallan explicitamente los trabajos hasta que se integre el procesamiento real. No generan resultados simulados.
