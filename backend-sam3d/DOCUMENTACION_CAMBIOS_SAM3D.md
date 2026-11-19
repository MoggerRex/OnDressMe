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

## Ajuste de prendas basado en huesos

- `services/body_skeleton.py`: asigna cada vértice del cuerpo al hueso MHR más cercano (distancia normalizada por el radio del hueso). Los vértices de brazos y manos se excluyen de las secciones de cadera/cintura y de la superficie de colisión de Blender cuando la prenda es un pantalón, así una mano junto a la cadera ya no se mide ni se usa como superficie de la prenda. Sin los huesos de codo/muñeca se conserva el comportamiento anterior.
- `services/garment_rig.py`: si el GLB de la prenda trae `skin` (huesos y pesos), sus huesos de cadera, muslo, rodilla y pie se mapean sobre los keypoints del cuerpo (`left/right-hip`, `knee`, `ankle`) mediante los pesos de cada vértice. Los nombres de hueso se reconocen en formato Mixamo/Blender; el lado izquierdo/derecho se decide por posición X. Sin skin se usa el ajuste geométrico anterior.
- Métricas nuevas en `pipeline_info`: `fit_body_arm_vertices_excluded`, `fit_garment_rig`, `fit_garment_rig_joints`.
- La huella del cuerpo cambió a `v2-skeleton`, por lo que las prendas guardadas antes se vuelven a procesar.
- Pruebas: `python -m unittest tests.test_skeleton_fit tests.test_garment_pipeline tests.test_garment_library tests.test_blender_simulation` (desde `backend-sam3d`, entorno `sam3d`).

## Zapatos y cintura trasera

- Cintura trasera del pantalón: la elevación del borde posterior bajó de 5.5 % a 2 % de la altura del cuerpo (antes quedaba ~9.5 cm sobre el frente y se abría hacia atrás).
- Tipo `shoes` (`services/shoe_fit.py`): ajuste rígido, sin Blender, sobre los huesos del pie (`heel`, `big-toe-tip`, `ankle`). Acepta un par (separado en X o Z), un solo zapato (se refleja para el otro pie) o un GLB con huesos (el hueso del dedo da la dirección). Sin hueso, la punta es el extremo más bajo de la suela. La suela se apoya en el punto más bajo del pie del cuerpo. Se escala a 1.12 × la distancia talón–punta.

### Zapatos: puntos inicial y final del pie

Cada pie se mide en la malla del cuerpo: su huella (vértices más bajos) da el eje real del pie, y de él salen un punto inicial (talón) y uno final (punta). Así un pie girado hacia dentro o fuera se sigue exactamente, aunque los keypoints MHR digan otra cosa o no existan. Los keypoints `heel`/`big-toe-tip`, si están, solo eligen qué extremo es la punta; sin ellos, la punta es el extremo más plano. El zapato se escala por largo (×1.18 sobre la huella) y por ancho (×1.12), y se gira para que su eje talón-punta coincida con el del pie. No se aplica inclinación (pitch): la suela queda plana sobre el piso.

## Axilas y nuevos tipos de prenda

- **Axila / brazos pegados** (`services/body_volume.py`): tras la simulación de una prenda superior, el cuerpo se voxeliza y se "cierra" a través de huecos estrechos (≈ 4 cm, como la axila con el brazo pegado). Todo vértice de la prenda que quede dentro de ese volumen (incluida la manga hundida en el brazo) sale por el camino más corto, con el desplazamiento suavizado sobre la malla. Con la camisa y el avatar de prueba, de ~4000–6000 vértices dentro del cuerpo se pasó a 0. Las métricas del log incluyen `BODY_OVERLAP_RESOLVED`.
- **Tipos nuevos**: `tank` (sin mangas), `longsleeve` (manga larga) y `shorts`.
  - `shorts`: igual que el pantalón pero el borde inferior queda un 12 % de la distancia rodilla–cadera sobre la rodilla (keypoints MHR, o ~0.285 de la altura sin ellos).
  - `longsleeve` (`services/sleeve_fit.py`): se escala por el ancho del torso (dobladillo) y cada manga se dobla sobre la cadena hombro→codo→muñeca del avatar, con el radio ajustado al brazo. Requiere los huesos del brazo y que la camisa tenga los brazos extendidos fuera del torso (T/A); si no detecta ambas mangas, lo avisa en `warnings`.
  - `tank`: mismo ajuste de torso que la camiseta.

## Correcciones de sin mangas, short y holgura

- **Opción de ajuste** (`fit`: `tight` / `regular` / `loose`, por defecto `regular`): en `/generate-garment` y en el selector "Ajuste" del frontend. Multiplica la holgura de cada prenda (camiseta/manga larga +20 %, sin mangas +6 %, cadera +12 %, bocamanga del pantalón +6 %, del short +14 %) por 0.4 / 1 / 2. La misma malla con otro ajuste se guarda aparte en la biblioteca.
- **Short y pantalón** (`services/leg_fit.py`): cada pierna se escala por niveles al grosor del muslo del avatar × holgura, se mantiene un hueco entre ambas piernas, y la entrepierna de la prenda se sube a la del cuerpo (antes colgaba ~7 cm más abajo y dejaba un panel entre las piernas). En Blender también se fija la costura de la entrepierna.
- **Camiseta sin mangas**: el ancho sale del torso a la altura de la axila (hombro − 6 % de la altura), el hueco de la prenda se alinea con la axila del avatar y `keep_off_arms` mantiene el borde de la sisa fuera del tubo del brazo sin arrastrarlo hacia el costado (eso creaba "aletas"). En el solapado posterior el empuje se limita a ~3 cm.
- **Manga larga**: el radio de la manga sigue la holgura elegida.
