# OnDressMe

Aplicación local para generar y visualizar un maniquí 3D a partir de una foto corporal con SAM 3D Body.

## Requisitos

- Node.js y npm para el frontend.
- Entorno Conda `sam3d` con SAM 3D Body, PyTorch con CUDA, FastAPI, OpenCV, Pillow y Trimesh.
- Una GPU CUDA compatible para generar maniquís.

## Iniciar el backend

En una terminal de Anaconda:

```powershell
conda activate sam3d
cd "C:\ruta\al\proyecto\backend-sam3d"
uvicorn server:app --port 8000
```

SAM 3D Body se carga al iniciar el servidor y requiere CUDA. No uses `--reload`: el observador recorre también el repositorio grande del backend y puede consumir memoria o detenerse al resolver sus rutas. Reinicia FastAPI manualmente al cambiar código.

## Iniciar el frontend

En otra terminal, desde la raíz del proyecto:

```powershell
npm install
npm run dev
```

Abre la URL local que muestre Vite. El frontend consume por defecto `http://127.0.0.1:8000`; se puede cambiar con `VITE_API_URL`.

## Flujo disponible

1. Selecciona una foto corporal.
2. Genera el maniquí con SAM 3D Body.
3. Rota y acerca el modelo en el visor, o descarga el resultado como GLB.

El backend expone únicamente `POST /generate-3d`, que recibe el archivo multipart `image` y devuelve `avatar_output.glb` (`model/gltf-binary`). El modelo asigna un color de piel uniforme estimado de la foto; no genera ropa ni texturas faciales.
