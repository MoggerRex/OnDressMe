import io
import logging
import os
import shutil
import sys
import tempfile
import torch
import trimesh
import numpy as np
import cv2
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
from gradio_client import Client, handle_file
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

# Agregar el repositorio clonado al PATH de Python
repo_path = os.path.join(os.path.dirname(__file__), "sam-3d-body")
sys.path.append(repo_path)

from sam_3d_body import SAM3DBodyEstimator, load_sam_3d_body_hf

app = FastAPI(title="OnDressMe 3D Generation Server")
logger = logging.getLogger(__name__)
OBJECTS_SPACE_ID = os.getenv(
    "SAM3D_OBJECTS_SPACE",
    "stabilityai/stable-fast-3d",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if not torch.cuda.is_available():
    raise RuntimeError("SAM 3D Body requiere una GPU CUDA disponible.")

print("Cargando el modelo SAM 3D Body desde Hugging Face...")
try:
    network, model_cfg = load_sam_3d_body_hf(
        "facebook/sam-3d-body-vith",
        device="cuda",
    )
    estimator = SAM3DBodyEstimator(
        sam_3d_body_model=network,
        model_cfg=model_cfg,
    )
    print("¡Modelo SAM 3D Body cargado exitosamente en VRAM!")
except Exception as e:
    logger.exception("Error al cargar el modelo SAM 3D Body.")
    raise RuntimeError("No se pudo inicializar SAM 3D Body.") from e


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


def discover_objects_endpoints(api_info: dict) -> tuple[str, str]:
    if not isinstance(api_info, dict):
        raise RuntimeError("El Space no publicó un esquema de API válido.")

    named_endpoints = api_info.get("named_endpoints", {})
    if not isinstance(named_endpoints, dict):
        raise RuntimeError("El Space no publicó endpoints nombrados.")

    generation_candidates = []
    preprocessing_candidates = []

    for endpoint_name, endpoint_info in named_endpoints.items():
        parameters = endpoint_info.get("parameters", [])
        parameter_names = {
            parameter.get("parameter_name", "").lower()
            for parameter in parameters
        }
        output_labels = {
            output.get("label", "").lower()
            for output in endpoint_info.get("returns", [])
        }

        if (
            "3d model" in output_labels
            and "input_image" in parameter_names
            and "texture_size" in parameter_names
        ):
            generation_candidates.append(endpoint_name)

        if (
            "preview background removal" in output_labels
            and "image" in parameter_names
            and ("fr" in parameter_names or "foreground_ratio" in parameter_names)
        ):
            preprocessing_candidates.append(endpoint_name)

    if len(generation_candidates) != 1 or len(preprocessing_candidates) != 1:
        raise RuntimeError(
            "No se pudo identificar de forma inequívoca la API de generación "
            "y eliminación de fondo del Space."
        )

    return preprocessing_candidates[0], generation_candidates[0]


def build_endpoint_arguments(
    endpoint_info: dict,
    image_parameter: str,
    image_file: object,
    overrides: dict[str, object],
) -> dict[str, object]:
    arguments = {}
    for parameter in endpoint_info.get("parameters", []):
        name = parameter.get("parameter_name")
        if name == image_parameter:
            arguments[name] = image_file
        elif name in overrides:
            arguments[name] = overrides[name]
        elif parameter.get("parameter_has_default"):
            arguments[name] = parameter.get("parameter_default")
        else:
            raise RuntimeError(
                f"El endpoint remoto requiere un parámetro desconocido: {name}."
            )
    return arguments


def build_full_endpoint_arguments(
    client: Client,
    endpoint_name: str,
    overrides: dict[str, object],
) -> list[object]:
    endpoint = next(
        endpoint
        for endpoint in client.endpoints.values()
        if endpoint.api_name == endpoint_name
    )
    components = {
        component["id"]: component
        for component in client.config.get("components", [])
    }
    parameters = client.view_api(print_info=False, return_format="dict")[
        "named_endpoints"
    ][endpoint_name]["parameters"]
    parameter_index = 0
    arguments = []

    for component_id, component_type in zip(
        endpoint.dependency["inputs"],
        endpoint.input_component_types,
    ):
        component = components[component_id]
        props = component.get("props", {})

        if component_type.is_state:
            arguments.append(None)
        elif component_type.skip:
            if component.get("type") != "button":
                raise RuntimeError(
                    f"El Space tiene un componente omitido no compatible: "
                    f"{component.get('type')}."
                )
            arguments.append(overrides["run_btn"])
        else:
            parameter = parameters[parameter_index]
            parameter_index += 1
            name = parameter.get("parameter_name")
            if name in overrides:
                arguments.append(overrides[name])
            elif parameter.get("parameter_has_default"):
                arguments.append(parameter.get("parameter_default"))
            else:
                raise RuntimeError(
                    f"El endpoint remoto requiere un parámetro desconocido: {name}."
                )

    if parameter_index != len(parameters):
        raise RuntimeError("No se pudieron asociar los parámetros de la API remota.")
    return arguments


def find_glb_path(value: object) -> str | None:
    if isinstance(value, (str, os.PathLike)):
        path = os.fspath(value)
        if path.lower().endswith(".glb") and os.path.isfile(path):
            return path
    elif isinstance(value, dict):
        path = value.get("path")
        if isinstance(path, str) and path.lower().endswith(".glb") and os.path.isfile(path):
            return path
        for item in value.values():
            result = find_glb_path(item)
            if result:
                return result
    elif isinstance(value, (list, tuple)):
        for item in value:
            result = find_glb_path(item)
            if result:
                return result
    return None


def generate_cloth_with_space(image_path: str) -> str:
    token = os.getenv("HF_TOKEN")
    client = Client(
        OBJECTS_SPACE_ID,
        token=token,
        verbose=False,
        _skip_components=False,
    )
    api_info = client.view_api(print_info=False, return_format="dict")
    preprocessing_endpoint, generation_endpoint = discover_objects_endpoints(api_info)
    named_endpoints = api_info["named_endpoints"]

    image_file = handle_file(image_path)
    preprocessing_info = named_endpoints[preprocessing_endpoint]
    preprocessing_arguments = build_endpoint_arguments(
        preprocessing_info,
        image_parameter="image",
        image_file=image_file,
        overrides={"fr": 0.85, "foreground_ratio": 0.85},
    )
    preprocessing_result = client.predict(
        api_name=preprocessing_endpoint,
        **preprocessing_arguments,
    )

    button_state = (
        preprocessing_result[0].get("value")
        if isinstance(preprocessing_result, (list, tuple))
        and preprocessing_result
        and isinstance(preprocessing_result[0], dict)
        else None
    )
    if button_state not in {"Run", "Remove Background"}:
        raise RuntimeError(
            "El Space no devolvió un estado de botón reconocido tras procesar la imagen."
        )

    generation_overrides = {
        "run_btn": button_state,
        "input_image": image_file,
        "foreground_ratio": 0.85,
        "remesh_option": "None",
        "vertex_count": -1,
        "texture_size": 1024,
    }
    generation_arguments = build_full_endpoint_arguments(
        client,
        generation_endpoint,
        generation_overrides,
    )
    result = client.predict(
        *generation_arguments,
        api_name=generation_endpoint,
    )

    if button_state == "Remove Background":
        generation_overrides["run_btn"] = "Run"
        generation_arguments = build_full_endpoint_arguments(
            client,
            generation_endpoint,
            generation_overrides,
        )
        result = client.predict(
            *generation_arguments,
            api_name=generation_endpoint,
        )

    glb_path = find_glb_path(result)
    if glb_path is None:
        raise RuntimeError("El Space no devolvió un archivo .glb descargable.")

    with open(glb_path, "rb") as glb_file:
        if glb_file.read(4) != b"glTF":
            raise RuntimeError("El archivo recibido no tiene un encabezado GLB válido.")

    return glb_path


@app.post("/generate-3d")
async def generate_3d(image: UploadFile = File(...)):
    try:
        img_bytes = await image.read()
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")

        with torch.inference_mode():
            outputs = estimator.process_one_image(np.asarray(img))

        if not outputs:
            raise HTTPException(
                status_code=422,
                detail="SAM 3D Body no encontró una persona en la imagen.",
            )

        vertices = outputs[0]["pred_vertices"]
        faces = estimator.faces

        img_array = np.array(img)
        skin_color = estimate_skin_color(img_array)
        vertex_colors = np.empty((len(vertices), 4), dtype=np.uint8)
        vertex_colors[:, :3] = skin_color
        vertex_colors[:, 3] = 255

        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        mesh.visual.vertex_colors = vertex_colors

        output_path = os.path.join(os.path.dirname(__file__), "avatar_output.glb")
        mesh.export(output_path)

        return FileResponse(output_path, media_type="model/gltf-binary", filename="avatar.glb")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error procesando la imagen.")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate-cloth")
async def generate_cloth(image: UploadFile = File(...)):
    output_path = None
    try:
        image_bytes = await image.read()
        try:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        except (OSError, ValueError) as e:
            raise HTTPException(status_code=422, detail="El archivo no es una imagen válida.") from e

        with tempfile.TemporaryDirectory(prefix="sam3d-cloth-") as temp_dir:
            input_path = os.path.join(temp_dir, "input.png")
            img.save(input_path, format="PNG")

            remote_glb_path = await run_in_threadpool(
                generate_cloth_with_space,
                input_path,
            )

            output_fd, output_path = tempfile.mkstemp(prefix="prenda-", suffix=".glb")
            os.close(output_fd)
            shutil.copyfile(remote_glb_path, output_path)

        return FileResponse(
            output_path,
            media_type="model/gltf-binary",
            filename="prenda.glb",
            background=BackgroundTask(os.remove, output_path),
        )
    except HTTPException:
        raise
    except Exception as e:
        if output_path and os.path.exists(output_path):
            os.remove(output_path)
        logger.exception("Error generando el modelo de la prenda con el Space remoto.")
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo generar la prenda con el Space remoto: {e}",
        ) from e