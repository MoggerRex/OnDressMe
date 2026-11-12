# Worker de outfits

Este worker clasifica una prenda con `dinov2_vits14` y `LogisticRegression`.
El modelo DINOv2 se descarga la primera vez desde PyTorch Hub y queda en la
cache local de Torch.

## Instalacion

Desde esta carpeta:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Prueba local sin la computadora central

El comando `demo` crea un dataset pequeño de imagenes sinteticas, entrena el
clasificador, guarda el artefacto y predice una imagen local:

```powershell
python classifier.py demo --workdir demo_outfits
```

La primera ejecucion requiere internet para descargar DINOv2. Las siguientes
usan la cache. Para usar imagenes reales:

```powershell
python classifier.py train --dataset dataset_ropa --artifact outfit_classifier.joblib
python classifier.py predict --image dataset_ropa\camisas\ejemplo.jpg --artifact outfit_classifier.joblib
```

La estructura esperada es `dataset_ropa\<clase>\<imagen>`, por ejemplo
`dataset_ropa\chaquetas\foto_01.jpg`. El resultado incluye `prenda` y
`confianza`.

## Preparar Fashion-MNIST

Coloca estos archivos en la misma carpeta:

```text
demo_outfits\dataset_ropa\dataset\
├── train-images-idx3-ubyte.gz
└── train-labels-idx1-ubyte.gz
```

Desde `workers\outfits`, convierte inicialmente 500 imágenes por clase:

```powershell
python prepare_fashion_mnist.py `
  --images demo_outfits\dataset_ropa\dataset\train-images-idx3-ubyte.gz `
  --labels demo_outfits\dataset_ropa\dataset\train-labels-idx1-ubyte.gz `
  --output dataset_fashion_mnist `
  --max-per-class 500
```

El conversor crea las carpetas `camisetas`, `pantalones`, `sueteres`,
`vestidos`, `abrigos` y `camisas`. Para convertir todas las imágenes usa
`--max-per-class 0`. Fashion-MNIST es útil para probar el pipeline, pero sus
imágenes son pequeñas y en escala de grises; después conviene mezclarlo con
fotografías reales.

## Ejecucion como worker Redis

Configura `REDIS_URL`, `BACKEND_URL`, `WORKER_TOKEN` y
`OUTFIT_MODEL_PATH` en `.env`, entrena antes el artefacto y ejecuta:

```powershell
python worker.py
```

Los trabajos deben incluir `image_path` con una ruta accesible en la
computadora D. Si solo contienen `wardrobe_item_ids`, el worker los marca como
fallidos explícitamente porque todavía no existe una ruta de imagen resoluble.
