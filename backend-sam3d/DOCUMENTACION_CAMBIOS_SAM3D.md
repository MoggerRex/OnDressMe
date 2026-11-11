# Documentación de cambios: SAM 3D Body → GLB con color de piel

Este documento explica **qué se cambió, qué se instaló, qué se descargó y cómo quedó funcionando** el backend `backend-sam3d` para que:

1. El modelo SAM 3D Body cargara correctamente en la GPU.
2. El endpoint `/generate-3d` dejara de devolver errores y exportara un `.glb` real.
3. El `.glb` saliera con un **color uniforme de piel**, estimado de la zona del rostro de la foto, en lugar de copiar píxeles de ropa y fondo.

---

## 1. Resumen ejecutivo

- Se clonó el repositorio oficial **`facebookresearch/sam-3d-body`** dentro de `backend-sam3d/sam-3d-body`.
- Se creó un entorno Conda llamado **`sam3d`** con Python 3.10.
- Se instalaron **PyTorch 2.5.1 + CUDA 12.1**, `torchvision`, `pytorch-lightning`, `opencv-python`, `trimesh`, `fastapi`, `uvicorn`, `huggingface_hub`, entre otras dependencias.
- Se descargaron los pesos oficiales desde Hugging Face:
  - `facebook/sam-3d-body-vith` (el que usa actualmente el servidor).
  - `facebook/sam-3d-body-dinov3` (usado en intentos anteriores).
- Se corrigió la carga del modelo usando `load_sam_3d_body_hf(...)` en lugar de descargar manualmente archivos con nombres incorrectos.
- Se cambió la exportación de `.obj` a **`.glb`**, asignando **colores por vértice** (`COLOR_0`) para que el modelo se vea con color en visores y en Three.js.
- Se reemplazó el mapeo de textura píxel-por-píxel por una **estimación de un solo tono de piel** a partir de una región superior centrada de la foto (zona del rostro).
- Si no se encuentran píxeles de piel, se usa un tono neutro de respaldo: **RGB `(180, 130, 110)`**.

> Importante: **no es detección facial real**. Es una heurística que asume que el rostro está en la parte superior y centrada de la foto. Por eso el resultado es una figura de **un solo color**, sin textura de ropa, sin ojos, sin boca y sin detalles faciales.

---

## 2. Problema inicial

El servidor intentaba cargar el modelo así:

- Repositorio de Hugging Face: `facebook/sam-3d-body`
- Archivo: `sam3d_body.pth`
- Configuración: buscaba cualquier `.yaml` dentro del repo clonado.
- Si fallaba, dejaba `model = None` y el endpoint respondía:
  ```json
  {"detail": "El modelo no pudo inicializarse."}
  ```

Ese mensaje se guardó varias veces como si fuera un `.glb` (por ejemplo `avatar_con_ropa.glb`, `Leo_Texturas.glb`, `Leo_Textura2s.glb`). Esos archivos pesan **45 bytes** y **no son GLB**: son el JSON de error que `curl` guardó con extensión `.glb`.

Además, la versión anterior exportaba **`.obj`**, que no lleva colores por vértice de la misma forma y no era lo que se quería mostrar.

---

## 3. Evolución de los cambios

### 3.1. Primer intento: repositorio y archivo incorrectos

Se intentaba usar:

```python
from huggingface_hub import hf_hub_download
checkpoint_file = hf_hub_download(
    repo_id="facebook/sam-3d-body",
    filename="sam3d_body.pth",
)
```

Ese no es el paquete correcto de pesos para este modelo. El resultado era que el modelo no se inicializaba y el endpoint devolvía el JSON de error.

### 3.2. Corrección de la carga del modelo

Se pasó a usar el repositorio oficial y la función de carga incluida en el propio repo:

```python
from sam_3d_body import SAM3DBodyEstimator, load_sam_3d_body

model_dir = snapshot_download(repo_id="facebook/sam-3d-body-dinov3")
checkpoint_path = os.path.join(model_dir, "model.ckpt")
mhr_path = os.path.join(model_dir, "assets", "mhr_model.pt")

sam3d_model, model_config = load_sam_3d_body(
    checkpoint_path=checkpoint_path,
    device="cuda",
    mhr_path=mhr_path,
)
estimator = SAM3DBodyEstimator(
    sam_3d_body_model=sam3d_model,
    model_cfg=model_config,
)
```

Después se simplificó aún más usando la función que descarga y carga directo desde Hugging Face:

```python
from sam_3d_body import SAM3DBodyEstimator, load_sam_3d_body_hf

network, model_cfg = load_sam_3d_body_hf(
    "facebook/sam-3d-body-vith",
    device="cuda",
)
estimator = SAM3DBodyEstimator(
    sam_3d_body_model=network,
    model_cfg=model_cfg,
)
```

`load_sam_3d_body_hf` internamente hace `snapshot_download`, localiza `model.ckpt`, `assets/mhr_model.pt` y `model_config.yaml`, y llama a `load_sam_3d_body`.

También se agregó:

- Validación explícita de CUDA:
  ```python
  if not torch.cuda.is_available():
      raise RuntimeError("SAM 3D Body requiere una GPU CUDA disponible.")
  ```
- `try/except` con `logger.exception(...)` para ver el error real si el modelo no carga.
- `with torch.inference_mode():` al procesar la imagen, para no gastar memoria en gradientes.

### 3.3. Cambio de `.obj` a `.glb` con colores por vértice

La malla se sigue obteniendo de:

```python
vertices = outputs[0]["pred_vertices"]
faces = estimator.faces
```

Pero ahora se crea una matriz RGBA por vértice:

```python
vertex_colors = np.empty((len(vertices), 4), dtype=np.uint8)
vertex_colors[:, :3] = skin_color
vertex_colors[:, 3] = 255

mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
mesh.visual.vertex_colors = vertex_colors
mesh.export(output_path)
```

Puntos clave:

- `process=False` evita que Trimesh elimine o reordene vértices, para que el arreglo de colores coincida exactamente con la cantidad de vértices.
- `vertex_colors` es `uint8` con forma `(N, 4)`: RGB + alpha 255.
- Trimesh exporta esos colores como el atributo **`COLOR_0`** del GLB.
- El GLB resultante no necesita una imagen de textura ni un material complejo: el color va “horneado” en los vértices.

Salida final:

```python
output_path = os.path.join(os.path.dirname(__file__), "avatar_output.glb")
mesh.export(output_path)

return FileResponse(
    output_path,
    media_type="model/gltf-binary",
    filename="avatar.glb",
)
```

### 3.4. Primer mapeo de color: proyección píxel por píxel (descartado)

En una primera versión del cambio se proyectaban los vértices de la malla sobre la foto:

1. Se normalizaban las coordenadas X/Y de los vértices.
2. Se convertían a coordenadas de píxel.
3. Se tomaba el color del píxel correspondiente de la foto.
4. Se asignaba ese color a cada vértice.

Esto “funcionaba” técnicamente, pero **tomaba colores de la ropa, el fondo y accesorios**, no solo de la piel. Por eso el modelo salía con manchas y colores incorrectos.

### 3.5. Cambio final: un solo color de piel estimado de la cara

Se eliminó la proyección píxel por píxel y se agregó la función `estimate_skin_color`.

```python
def estimate_skin_color(image: np.ndarray) -> np.ndarray:
    height, width, _ = image.shape
    face_region = image[
        int(height * 0.18):int(height * 0.30),
        int(width * 0.40):int(width * 0.60),
    ]

    hsv = cv2.cvtColor(face_region, cv2.COLOR_RGB2HSV)
    ycrcb = cv2.cvtColor(face_region, cv2.COLOR_RGB2YCrCb)
    hue, saturation, value = cv2.split(hsv)
    _, cr, cb = cv2.split(ycrcb)

    skin_mask = (
        ((hue <= 25) | (hue >= 170))
        & (saturation >= 30)
        & (value >= 40)
        & (cr >= 133)
        & (cr <= 173)
        & (cb >= 77)
        & (cb <= 127)
    )
    skin_pixels = face_region[skin_mask]

    if len(skin_pixels) == 0:
        logger.warning("No se pudo estimar el tono de piel; se usará un tono neutro.")
        return np.array([180, 130, 110], dtype=np.uint8)

    return np.median(skin_pixels, axis=0).astype(np.uint8)
```

Luego, en el endpoint:

```python
img_array = np.array(img)
skin_color = estimate_skin_color(img_array)

vertex_colors = np.empty((len(vertices), 4), dtype=np.uint8)
vertex_colors[:, :3] = skin_color
vertex_colors[:, 3] = 255
```

Resultado: **todos los vértices de la malla tienen exactamente el mismo color**.

---

## 4. Cómo funciona la estimación del color de piel

### 4.1. Región que se muestrea

```python
face_region = image[
    int(height * 0.18):int(height * 0.30),
    int(width * 0.40):int(width * 0.60),
]
```

- Vertical: del **18% al 30%** de la altura de la imagen.
- Horizontal: del **40% al 60%** del ancho.

Es decir, un rectángulo centrado en la parte superior de la foto. La suposición es que ahí está el rostro en una foto de cuerpo completo o medio cuerpo.

**No se usa un detector de rostros.** Si la persona no está centrada, si la cara está en otra posición o si hay otra persona/objeto en esa zona, el color puede salir mal.

### 4.2. Filtro de piel

Se combinan dos espacios de color:

- **HSV**:
  - Tono: `H <= 25` o `H >= 170`.
  - Saturación: `S >= 30`.
  - Brillo: `V >= 40`.
- **YCrCb**:
  - `Cr` entre `133` y `173`.
  - `Cb` entre `77` y `127`.

Un píxel se considera piel si cumple **todas** las condiciones. Así se descartan sombras, fondo, ropa y zonas con poca saturación.

### 4.3. Color representativo

```python
np.median(skin_pixels, axis=0)
```

Se usa la **mediana** de los píxeles de piel, no el promedio. La mediana es más resistente a valores atípicos (brillos, sombras, bordes).

### 4.4. Respaldo

Si no hay ningún píxel que cumpla el filtro:

```python
return np.array([180, 130, 110], dtype=np.uint8)
```

Ese es el tono neutro de respaldo.

### 4.5. Limitaciones

- No distingue piel de madera, paredes color piel o ropa color piel.
- No detecta la cara de verdad; solo muestrea una zona fija.
- No separa brazos, manos, cuello ni piernas: todo el cuerpo recibe el mismo color.
- No genera textura, ropa, ojos, boca ni detalles.
- Si la foto tiene fondo muy similar al tono de piel, la estimación puede desviarse.
- La iluminación de la foto afecta directamente el tono estimado.

---

## 5. Qué se descargó y qué se instaló

### 5.1. Repositorio clonado

Ruta:

```text
backend-sam3d/sam-3d-body
```

Origen:

```powershell
git clone https://github.com/facebookresearch/sam-3d-body.git
```

Datos del clon que quedó:

- Remoto: `https://github.com/facebookresearch/sam-3d-body.git`
- Commit: `b5c765a0d89d789985e186d396315e7590887b94`
- Fecha del commit: `2026-02-19`
- Mensaje: `add arXiv`

El servidor no instala el repo como paquete; lo agrega al `sys.path`:

```python
repo_path = os.path.join(os.path.dirname(__file__), "sam-3d-body")
sys.path.append(repo_path)
```

### 5.2. Entorno Conda

Entorno creado:

```powershell
conda create -n sam3d python=3.10 -y
conda activate sam3d
```

Datos reales del entorno:

- Nombre: `sam3d`
- Ruta: `C:\Users\polo0\miniconda3\envs\sam3d`
- Python: `3.10.22`

> La guía oficial de SAM 3D Body sugiere Python 3.11, pero el entorno que quedó funcionando usa Python 3.10.

### 5.3. Paquetes principales instalados

Versiones que quedaron en el entorno `sam3d`:

| Paquete | Versión |
|---|---|
| `torch` | `2.5.1+cu121` |
| `torchvision` | `0.20.1+cu121` |
| `pytorch-lightning` | `2.6.6` |
| `torchmetrics` | `1.9.0` |
| `timm` | `1.0.31` |
| `einops` | `0.8.2` |
| `omegaconf` | `2.4.0` |
| `yacs` | `0.1.8` |
| `scipy` | `1.15.3` |
| `roma` | `1.8.0` |
| `opencv-python` | `5.0.0.93` |
| `numpy` | `2.2.6` |
| `pillow` | `12.3.0` |
| `trimesh` | `5.2.0` |
| `fastapi` | `0.162.0` |
| `uvicorn` | `0.54.0` |
| `python-multipart` | `0.0.32` |
| `huggingface_hub` | `2.4.0` |
| `safetensors` | `0.8.0` |
| `hf-xet` | `1.8.0` |

Comandos equivalentes para reproducir el entorno:

```powershell
conda create -n sam3d python=3.10 -y
conda activate sam3d

python -m pip install --upgrade pip

# PyTorch con CUDA 12.1
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121

# Dependencias del modelo
pip install pytorch-lightning==2.6.6 torchmetrics==1.9.0 timm==1.0.31 einops==0.8.2 omegaconf==2.4.0 yacs==0.1.8 scipy==1.15.3 roma==1.8.0

# Procesamiento de imagen, malla y API
pip install opencv-python==5.0.0.93 numpy==2.2.6 pillow==12.3.0 trimesh==5.2.0
pip install fastapi==0.162.0 uvicorn==0.54.0 python-multipart==0.0.32 huggingface_hub==2.4.0
```

> Nota: fijar las versiones sirve para reproducir el entorno actual. Si en el futuro una versión falla, se pueden quitar los `==` y dejar que pip resuelva, revisando que `torch.cuda.is_available()` siga dando `True`.

### 5.4. Lo que **no** se instaló

`detectron2` **no** está instalado en el entorno `sam3d`.

Esto no impide que el servidor funcione, porque `SAM3DBodyEstimator` se construye **sin detector humano**:

```python
estimator = SAM3DBodyEstimator(
    sam_3d_body_model=network,
    model_cfg=model_cfg,
)
```

Cuando no hay detector, `process_one_image` usa **toda la imagen como caja delimitadora**:

```python
boxes = np.array([0, 0, width, height]).reshape(1, 4)
```

Consecuencia: si la foto tiene varias personas o mucho fondo, el modelo puede reconstruir mal la persona. No hay un paso de “detectar persona” separado.

Tampoco se instalaron `pyrender`, `detectron2`, `MoGe` ni `SAM3`, que son opcionales en la guía oficial.

### 5.5. Modelos descargados desde Hugging Face

Caché local:

```text
C:\Users\polo0\.cache\huggingface\hub
```

Modelos:

| Repositorio | Tamaño aproximado en caché | Uso |
|---|---:|---|
| `facebook/sam-3d-body-vith` | ~2.28 GB | **Modelo actual** del servidor |
| `facebook/sam-3d-body-dinov3` | ~2.68 GB | Modelo de intentos anteriores |

Cada snapshot incluye, entre otros:

- `model.ckpt`
- `assets/mhr_model.pt`
- `model_config.yaml`

La descarga ocurre la primera vez que se ejecuta el servidor, mediante `load_sam_3d_body_hf` → `snapshot_download`. En arranques posteriores se reutiliza la caché.

Requisitos de acceso:

- Solicitar acceso al repositorio en Hugging Face:
  - `https://huggingface.co/facebook/sam-3d-body-vith`
  - `https://huggingface.co/facebook/sam-3d-body-dinov3`
- Autenticarse con una cuenta que tenga acceso:

```powershell
hf auth login
# o, en versiones anteriores:
huggingface-cli login
```

Sin token válido o sin acceso aprobado, la descarga y la carga fallan al iniciar el servidor.

### 5.6. Requisitos de hardware

- GPU: `NVIDIA GeForce RTX 4050 Laptop GPU`
- VRAM: ~6 GB
- Driver NVIDIA: `617.14`
- PyTorch compilado para CUDA 12.1

El servidor aborta al iniciar si `torch.cuda.is_available()` es `False`.

---

## 6. Qué se importa en Python

En `backend-sam3d/server.py`:

```python
import io
import logging
import os
import sys
import torch
import trimesh
import numpy as np
import cv2
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
```

Y el modelo:

```python
from sam_3d_body import SAM3DBodyEstimator, load_sam_3d_body_hf
```

Origen de cada import:

| Import | Paquete / origen |
|---|---|
| `torch` | `torch` |
| `trimesh` | `trimesh` |
| `numpy` | `numpy` |
| `cv2` | `opencv-python` |
| `FastAPI`, `UploadFile`, `File`, `HTTPException`, `FileResponse` | `fastapi` |
| `CORSMiddleware` | `fastapi` |
| `Image` | `pillow` |
| `SAM3DBodyEstimator`, `load_sam_3d_body_hf` | repo clonado `sam-3d-body` |

---

## 7. Cómo levantar el servidor y probarlo

### 7.1. Levantar

```powershell
cd "C:\Users\polo0\Documents\Leo Olivares\Softtek\OnDressMe\backend-sam3d"
conda activate sam3d
uvicorn server:app --port 8000
```

Esperar mensajes como:

```text
Cargando el modelo SAM 3D Body desde Hugging Face...
¡Modelo SAM 3D Body cargado exitosamente en VRAM!
Application startup complete.
```

La primera vez puede tardar varios minutos si debe descargar el checkpoint.

### 7.2. Probar con una imagen

```powershell
curl.exe -X POST "http://127.0.0.1:8000/generate-3d" `
  -F "image=@C:\ruta\a\foto.jpg" `
  -o avatar_output_test.glb `
  -w "`nHTTP %{http_code}`n"
```

Respuesta esperada:

- `HTTP 200`
- Archivo `.glb` de cientos de KB (no 45 bytes).
- Cabecera del archivo: `glTF`.

Verificación rápida en PowerShell:

```powershell
Get-Item .\avatar_output_test.glb | Select-Object Name, Length
Get-Content .\avatar_output_test.glb -AsByteStream -TotalCount 4
```

Los primeros bytes deben ser `0x67 0x6C 0x54 0x46` (`glTF`).

### 7.3. Probar dentro de Python

```python
import trimesh
import numpy as np

mesh = trimesh.load("avatar_output.glb", force="mesh")
colors = np.asarray(mesh.visual.vertex_colors)

print("Vértices:", len(mesh.vertices))
print("Caras:", len(mesh.faces))
print("Colores únicos:", np.unique(colors[:, :3], axis=0))
print("Alpha:", np.unique(colors[:, 3]))
```

---

## 8. Evidencia de validación

### 8.1. Foto de prueba `LeoJordan.jpeg`

Con la misma lógica de la función `estimate_skin_color`, esa foto produjo:

```text
skin candidate pixels: ~cientos
estimated RGB: (170, 119, 99)
```

### 8.2. GLB que quedó en disco

El archivo `backend-sam3d/avatar_output.glb` generado con otra foto de prueba tiene:

- Tamaño: **738,492 bytes** (~721 KB).
- Vértices: **18,439**.
- Caras: **36,874**.
- Color único de vértices: **RGB `(233, 191, 168)`**.
- Alpha: **255**.
- Atributos del primitivo GLB: `POSITION` y `COLOR_0`.
- Sin material ni textura embebida.

Esto confirma que el GLB contiene un color uniforme por vértice y que no está usando una textura.

### 8.3. Los archivos de 45 bytes

Archivos como:

- `avatar_con_ropa.glb`
- `Leo_Texturas.glb`
- `Leo_Textura2s.glb`

pesan 45 bytes porque contienen:

```json
{"detail":"El modelo no pudo inicializarse."}
```

No son modelos 3D. Eran respuestas de error guardadas por `curl` con extensión `.glb`, de cuando el servidor aún no cargaba SAM 3D Body.

---

## 9. Estado del frontend

El frontend **todavía no consume** el GLB generado. En `src/features/mannequin/MannequinScene.jsx` sigue renderizándose un maniquí procedural con primitivas de Three.js, y la línea de `useGLTF` está comentada:

```jsx
// const { scene } = useGLTF('/src/assets/mannequin.glb');
```

Por lo tanto:

- El backend ya produce un `.glb` válido con color de piel.
- La integración para mostrarlo en React/Three.js queda pendiente.
- Cuando se integre, el GLB puede cargarse con `useGLTF` y renderizarse con `<primitive object={scene} />`; Three.js respeta `COLOR_0` automáticamente.

También existe CORS configurado para el frontend de Vite:

```python
allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"]
```

---

## 10. Resumen técnica en una frase

Se reemplazó la carga manual e incorrecta del checkpoint por `load_sam_3d_body_hf("facebook/sam-3d-body-vith")`, se exporta la malla como GLB con colores RGBA por vértice y se asigna a todos los vértices la **mediana del color de piel** detectada con HSV + YCrCb en una región superior centrada de la foto, con respaldo `(180, 130, 110)` si no se encuentra piel.

---

## 11. Prompt corto para pasarle a Gemini

> Tengo un backend FastAPI en `backend-sam3d/server.py` que usa SAM 3D Body (`facebook/sam-3d-body-vith`) cargado desde Hugging Face con `load_sam_3d_body_hf`. El modelo corre en un entorno Conda `sam3d` con Python 3.10, PyTorch 2.5.1+cu121, OpenCV, Trimesh, FastAPI y Uvicorn. El endpoint `/generate-3d` recibe una imagen, obtiene `pred_vertices` y `estimator.faces`, estima un color de piel con una máscara HSV + YCrCb sobre la región `[18%–30% de alto, 40%–60% de ancho]` de la foto, toma la mediana de los píxeles de piel y asigna ese mismo RGBA a todos los vértices. Luego exporta `avatar_output.glb` con `trimesh` usando `process=False`, lo que genera el atributo `COLOR_0`, y lo devuelve con `media_type="model/gltf-binary"`. No hay detector de personas ni de rostros: si no hay detector, SAM usa la imagen completa como bbox. No hay textura ni ropa; es un color sólido. El frontend aún no carga el GLB. Necesito que me ayudes a [explicar / mejorar / integrar / depurar] este flujo.

---

## 12. Ajuste de prenda sobre un cuerpo seleccionado

`POST /generate-cloth` ya no usa SAM 3D Objects ni un servicio remoto. Recibe obligatoriamente los dos archivos multipart:

- `garment_image`: imagen PNG o JPG de la prenda.
- `body_glb`: GLB del cuerpo que se seleccionó previamente.

`POST /generate-3d` invierte los ejes Y/Z de la salida de SAM 3D Body para que el avatar aparezca de pie en Blender y apoya los pies en el plano Y=0, centrando el modelo horizontalmente. Es necesario volver a generar los avatares creados antes de este cambio.

`POST /generate-cloth` utiliza el canal alfa o GrabCut para segmentar y clasificar camiseta/pantalón. Para la camiseta carga `templates/base_shirt.glb` con Trimesh (`force="mesh"`), elimina componentes de superficie duplicados con orientación opuesta, conserva las UV restantes y asigna la foto recortada como textura RGBA con transparencia. Escala y traslada la caja completa de la plantilla para que coincida con la caja del torso del avatar: la banda vertical es `50–85%` de su altura y los límites lateral/profundidad son los percentiles `5–95%` de sus vértices en esa banda. Para pantalones conserva la plantilla local `jeans.glb` (o sus nombres alternativos). La geometría viene de las plantillas, no se reconstruye en 3D a partir de la foto. No se crea una malla del torso/hombros del avatar como capa de cobertura. El endpoint exporta `prenda_fit.glb` como `model/gltf-binary`. Si falta un archivo multipart, FastAPI responde con `422`; los errores de plantilla se registran y se devuelven como error del servidor.

El pantalón se ajusta a la banda vertical `3–55%` de la altura corporal; sus límites lateral/profundidad también se calculan con percentiles `5–95%`. La clasificación es heurística y está pensada para una sola prenda aislada. El ajuste a una caja no garantiza que la plantilla respete cada medida anatómica ni que no intersecte el cuerpo. No se generan paneles/patrones ni se reconstruye la espalda a partir de una sola foto.

Las respuestas de `/generate-3d` se generan en un archivo temporal único, que se elimina después de enviarse. Esto evita que `curl -o avatar_output.glb` sobrescriba el archivo del cuerpo mientras FastAPI aún lo está transmitiendo.

Ejemplo de llamada:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/generate-cloth" `
  -F "garment_image=@C:\ruta\a\prenda.png" `
  -F "body_glb=@C:\ruta\a\avatar.glb" `
  -o prenda_fit.glb
```

El frontend permite generar un avatar o seleccionar un GLB, requiere ese cuerpo antes de enviar la prenda, consume ambos endpoints, muestra los dos modelos en el mismo visor Three.js y permite descargar sus GLB. También permite solicitar la simulación y muestra el error explícito cuando Blender no está instalado.

## 13. Simulación local con Blender

`POST /simulate-cloth` recibe `body_glb` y `garment_glb`. El servicio `services/blender_service.py` invoca el ejecutable oficial como proceso separado, serializa solicitudes para evitar varias instancias simultáneas, aplica un timeout y valida el GLB exportado. Antes de añadir Cloth, `simulation/scripts/simulate_garment.py` reduce el cuerpo de colisión a un máximo de 16.000 caras y cada malla de prenda a 6.000 caras. Cloth se aplica a las mallas de la prenda, que ya no incluyen una capa derivada del cuerpo. Luego avanza 24 frames y exporta la prenda.

El servicio busca Blender en `PATH` y también detecta automáticamente la instalación de Steam de este equipo. Para especificar otra instalación, configura la variable antes de iniciar FastAPI:

```powershell
$env:BLENDER_EXECUTABLE = 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe'
$env:BLENDER_TIMEOUT_SECONDS = '300'
```

Si no se encuentra Blender, el endpoint devuelve `503`; si excede el timeout, devuelve `504`. Los valores físicos incluidos son parámetros iniciales del prototipo y no propiedades textiles calibradas. Las validaciones anteriores de simulación correspondían a una plantilla y geometría distintas; se requiere volver a probar Cloth con la plantilla `base_shirt.glb` ajustada por este flujo.
