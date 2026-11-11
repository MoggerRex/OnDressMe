# OnDressMe

Prototipo local de probador 3D con React/Three.js y FastAPI.

## Requisitos

- Node.js y npm para el frontend.
- Entorno Conda `sam3d` con SAM 3D Body, PyTorch con CUDA, FastAPI, OpenCV, Pillow y Trimesh.
- Una GPU CUDA compatible para generar avatares.

## Iniciar el backend

En una terminal de Anaconda:

```powershell
conda activate sam3d
cd "C:\ruta\al\proyecto\backend-sam3d"
uvicorn server:app --port 8000
```

SAM 3D Body se carga al iniciar el servidor y requiere CUDA. No uses `--reload`: el observador recorre también los repositorios grandes del backend y puede consumir memoria o detenerse al resolver sus rutas. Reinicia FastAPI manualmente al cambiar código.

## Iniciar el frontend

En otra terminal, desde la raíz del proyecto:

```powershell
npm install
npm run dev
```

Abre la URL local que muestre Vite. El frontend consume por defecto `http://127.0.0.1:8000`; se puede cambiar con `VITE_API_URL`.

## Flujo disponible

1. Genera un avatar con una foto corporal o selecciona un avatar GLB existente.
2. Selecciona una foto de camiseta o pantalón. Se requiere un cuerpo seleccionado antes de ajustar la prenda.
3. El backend segmenta la imagen y clasifica la prenda. Para camisetas usa `backend-sam3d/templates/base_shirt.glb`; ajusta la plantilla a la caja del torso del cuerpo seleccionado con una transformación afín y aplica la foto recortada como textura usando las UV existentes. No añade una malla del cuerpo debajo de la prenda. La geometría no se reconstruye desde la foto: se usa una plantilla existente.
4. El visor muestra el avatar y la prenda juntos; ambos GLB se pueden descargar.

Endpoints actuales:

- `POST /generate-3d`: recibe `image` y devuelve `avatar_output.glb`.
- `POST /generate-cloth`: recibe `garment_image` y `body_glb`, y devuelve `prenda_fit.glb`.
- `POST /simulate-cloth`: recibe `body_glb` y `garment_glb`, ejecuta Blender y devuelve `prenda_simulada.glb`.

## Alcance actual

El ajuste por dimensiones es aproximado: la prenda usa una plantilla y no reconstruye un patrón textil ni garantiza una adaptación anatómica perfecta. La textura reutiliza las UV de la plantilla; la foto de frente no contiene información para reconstruir exactamente la espalda. Antes de Cloth, Blender reduce la malla de colisión del cuerpo a un máximo de 16.000 caras y la prenda a 6.000 para limitar el uso de memoria. La simulación usa parámetros iniciales que aún requieren calibración. El backend detecta automáticamente esta instalación de Steam en `C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe`; para usar otra instalación, establece `BLENDER_EXECUTABLE` en la misma terminal desde la que arrancas FastAPI. `BLENDER_TIMEOUT_SECONDS` es opcional (por defecto 300). Si Blender no está disponible, el endpoint devuelve HTTP 503 en lugar de simular un resultado. No hay generación de patrones/costuras ni trabajos en segundo plano.

Las pruebas geométricas del backend se ejecutan desde `backend-sam3d` con:

```powershell
python -m unittest discover -s tests -v
```
