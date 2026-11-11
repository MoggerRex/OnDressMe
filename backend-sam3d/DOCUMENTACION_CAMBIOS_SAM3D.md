# Generación de maniquí con SAM 3D Body

El backend utiliza SAM 3D Body para recuperar una malla humana a partir de una foto corporal y devolverla como GLB. La aplicación no incluye flujos para cargar, ajustar o simular prendas.

## Modelo

- Repositorio: `backend-sam3d/sam-3d-body` (`facebookresearch/sam-3d-body`).
- Pesos: `facebook/sam-3d-body-vith`, cargados desde Hugging Face.
- El servidor requiere CUDA y carga el modelo al iniciar.

## Endpoint

`POST /generate-3d` recibe `image` como archivo multipart y devuelve `avatar_output.glb` con tipo `model/gltf-binary`.

El endpoint procesa la foto con `SAM3DBodyEstimator`, orienta y centra los vértices para que el cuerpo aparezca de pie, estima un tono de piel uniforme y exporta la malla con Trimesh. Si SAM 3D Body no encuentra una persona, devuelve HTTP 422.

## Ejecución local

```powershell
conda activate sam3d
cd "C:\ruta\al\proyecto\backend-sam3d"
uvicorn server:app --port 8000
```

Inicia el frontend desde la raíz con `npm run dev`. Para validar la integración visual, ejecuta `npm run lint` y `npm run build`.
