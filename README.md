# OnDressMe

Aplicación local para generar y visualizar un maniquí 3D a partir de una foto corporal con SAM 3D Body.

## Requisitos

- Node.js y npm para el frontend.
- Entorno Conda `sam3d` con SAM 3D Body, PyTorch con CUDA, FastAPI, OpenCV, Pillow y Trimesh.
- Una GPU CUDA compatible para generar maniquís.
- Blender 4.2 instalado para simular y exportar prendas. Si no está en el PATH o en la ruta predeterminada, define `ONDRESSME_BLENDER_PATH` con la ruta a `blender.exe`.

## Iniciar el backend

En una terminal de Anaconda:

```powershell
conda activate sam3d
cd "C:\ruta\al\proyecto\backend-sam3d"
uvicorn server:app --port 8000
```

SAM 3D Body se carga al iniciar el servidor y requiere CUDA. No uses `--reload`: el observador recorre también el repositorio grande del backend y puede consumir memoria o detenerse al resolver sus rutas. Reinicia FastAPI manualmente al cambiar código.

La simulación de prendas se ejecuta en Blender en segundo plano y no tiene un límite de tiempo automático; las mallas densas pueden tardar mucho. Mantén abiertos FastAPI y el navegador hasta que termine. Por ejemplo, si Blender está instalado en una ruta distinta:

```powershell
$env:ONDRESSME_BLENDER_PATH = "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"
```

## Iniciar el frontend

En otra terminal, desde la raíz del proyecto:

```powershell
npm install
npm run dev
```

Abre la URL local que muestre Vite. El frontend consume por defecto `http://127.0.0.1:8000`; se puede cambiar con `VITE_API_URL`.

## Flujo disponible

1. Selecciona una foto corporal y genera el maniquí con SAM 3D Body.
2. Genera la geometría 3D de la prenda con Garment3DGen y su etapa de malla objetivo de InstantMesh, fuera de OnDressMe por el momento.
3. Sube el archivo de la prenda (GLB, o el OBJ de salida de Garment3DGen) para ajustarlo inicialmente al torso y ejecutar una simulación estática en Blender.
4. El GLB simulado se muestra junto al cuerpo en el visor y puede descargarse.

El backend expone:

- `POST /generate-3d`: recibe el archivo multipart `image`, devuelve `avatar_output.glb` (`model/gltf-binary`) y un identificador `X-Avatar-Id`.
- `POST /generate-garment`: recibe `garment_mesh` (GLB u OBJ), `avatar_id` y `garment_type=tshirt`; devuelve `garment_fitted.glb` y las métricas/advertencias en `X-Pipeline-Info`. Si se envía solo una imagen, responde HTTP 422 en lugar de fabricar una geometría aproximada.

Los cuerpos se conservan temporalmente en memoria (máximo tres) y sus identificadores dejan de ser válidos al reiniciar FastAPI; genera de nuevo el maniquí si eso ocurre.

### Garment3DGen y reconstrucción

Garment3DGen no es solamente un aplicador de texturas: su método deforma una malla base para acercarla a una geometría objetivo y el artículo describe además generación de texturas. Sin embargo, el [README oficial](https://github.com/nsarafianos/Garment3DGen#data) y su `example_config.yml` requieren una malla `mesh` de origen y una `target_mesh`; el README recomienda obtener esta última de una imagen con InstantMesh. El runner publicado optimiza esas mallas, así que **no convierte por sí solo el archivo de foto en una malla**.

Esta aplicación todavía no ejecuta InstantMesh ni Garment3DGen. Para simular, carga una malla de prenda ya generada (por ejemplo, el `mesh_final/mesh.obj` de Garment3DGen). Se recomienda GLB si se quieren conservar texturas/materiales embebidos; un OBJ sin sus archivos MTL/textura conservará la geometría, pero no esos recursos externos.

### Limitaciones de esta etapa

- Solo se admite camiseta de manga corta y una persona aproximadamente erguida.
- OnDressMe no reconstruye actualmente la prenda desde la foto. La malla recibida se escala y centra con las dimensiones de secciones del torso; antes de la simulación Blender proyecta hacia fuera del cuerpo los vértices que empiezan penetrados.
- La simulación y exportación con Blender están integradas. La comprobación de intersecciones compara superficies triangulares y advierte si encuentra cruces; no demuestra ausencia de toda penetración volumétrica.
- Se probó el ajuste y la simulación local con una malla corporal SAM 3D real generada desde `persona.png` y `camisa_star.glb`. El resultado se revisó desde frente y perfil; la calidad puede variar con la postura y las mallas de entrada.

Las pruebas geométricas y de exportación se pueden ejecutar en el entorno `sam3d`:

```powershell
cd "C:\ruta\al\proyecto\backend-sam3d"
python -m unittest discover -s tests -v
```
