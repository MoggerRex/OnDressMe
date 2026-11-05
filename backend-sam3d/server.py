import io
import os
import sys

import numpy as np
import torch
import trimesh
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
from huggingface_hub import snapshot_download

# Agregar el repositorio clonado al PATH de Python
repo_path = os.path.join(os.path.dirname(__file__), "sam-3d-body")
sys.path.append(repo_path)

from sam_3d_body import SAM3DBodyEstimator, load_sam_3d_body

app = FastAPI(title="OnDressMe SAM 3D Body Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if not torch.cuda.is_available():
    raise RuntimeError(
        "SAM 3D Body requiere una GPU CUDA para esta configuración; no se detectó CUDA."
    )

print("Descargando configuración y archivos oficiales de SAM 3D Body...")
model_dir = snapshot_download(repo_id="facebook/sam-3d-body-dinov3")
checkpoint_path = os.path.join(model_dir, "model.ckpt")
mhr_path = os.path.join(model_dir, "assets", "mhr_model.pt")

required_files = (
    checkpoint_path,
    mhr_path,
    os.path.join(model_dir, "model_config.yaml"),
)
for required_file in required_files:
    if not os.path.isfile(required_file):
        raise FileNotFoundError(f"No se encontró un archivo requerido del modelo: {required_file}")

print("Cargando el modelo SAM 3D Body en la GPU...")
sam3d_model, model_config = load_sam_3d_body(
    checkpoint_path=checkpoint_path,
    device="cuda",
    mhr_path=mhr_path,
)
estimator = SAM3DBodyEstimator(
    sam_3d_body_model=sam3d_model,
    model_cfg=model_config,
)
print("¡Modelo SAM 3D Body cargado exitosamente en la GPU!")

@app.post("/generate-3d")
async def generate_3d(image: UploadFile = File(...)):
    try:
        img_bytes = await image.read()
        img = np.asarray(Image.open(io.BytesIO(img_bytes)).convert("RGB"))
        outputs = estimator.process_one_image(img)
        if not outputs:
            raise HTTPException(
                status_code=422,
                detail="No se pudo reconstruir una persona en la imagen.",
            )

        mesh = trimesh.Trimesh(
            vertices=outputs[0]["pred_vertices"],
            faces=estimator.faces,
        )
        output_path = os.path.join(os.path.dirname(__file__), "avatar_output.obj")
        mesh.export(output_path)
        
        return FileResponse(output_path, media_type="application/octet-stream", filename="avatar.obj")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))