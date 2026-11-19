from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import trimesh

from services.body_skeleton import body_without_arms
from services.body_volume import BodyVolume, resolve_overlaps
from services.garment_pipeline import LOWER_GARMENT_TYPES, UPPER_GARMENT_TYPES

logger = logging.getLogger(__name__)


class GarmentSimulationError(RuntimeError):
    """Raised when Blender cannot produce a validated static garment mesh."""


BLENDER_CANDIDATES = (
    r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
)

SIMULATION_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "simulation"
    / "scripts"
    / "simulate_garment.py"
)


def _find_blender() -> str:
    configured = os.environ.get("ONDRESSME_BLENDER_PATH")
    if configured:
        if not Path(configured).is_file():
            raise GarmentSimulationError(
                "ONDRESSME_BLENDER_PATH no apunta a un ejecutable de Blender válido."
            )
        return configured

    installed = shutil.which("blender")
    if installed:
        return installed

    for candidate in BLENDER_CANDIDATES:
        if Path(candidate).is_file():
            return candidate

    raise GarmentSimulationError(
        "No se encontró Blender. Instálalo o configura ONDRESSME_BLENDER_PATH."
    )


def _resolve_arm_overlaps(
    glb: bytes, scene: trimesh.Scene, body_mesh, max_push: float | None = None
) -> tuple[bytes, int]:
    """Push shirt vertices out of the arms and of the (closed) armpit gap.

    With the arms against the torso the cloth collision cannot satisfy both
    surfaces, so the sleeve ends up inside the arm. The body is closed across
    narrow gaps and every vertex still inside it is moved to the outside.
    """
    height = float(np.ptp(body_mesh.vertices[:, 1]))
    volume = BodyVolume(body_mesh.vertices, body_mesh.faces)
    resolved = resolve_overlaps(
        scene,
        volume,
        margin=max(0.004, height * 0.0025),
        min_y=float(body_mesh.vertices[:, 1].min()) + 0.5 * height,
        max_push=max_push,
    )
    if not resolved:
        return glb, 0
    fixed = bytes(scene.export(file_type="glb"))
    if len(fixed) < 12 or fixed[:4] != b"glTF":
        raise GarmentSimulationError("No se pudo exportar la prenda corregida.")
    return fixed, resolved


def simulate_static_garment(
    body_mesh: trimesh.Trimesh,
    garment_scene: trimesh.Scene,
    garment_type: str = "tshirt",
    timeout_seconds: int | None = None,
    body_landmarks: dict[str, np.ndarray] | None = None,
) -> tuple[bytes, str, int]:
    blender = _find_blender()
    if not SIMULATION_SCRIPT.is_file():
        raise GarmentSimulationError("No se encontró el script de simulación de Blender.")

    with tempfile.TemporaryDirectory(prefix="ondressme-cloth-") as work_dir:
        work_path = Path(work_dir)
        body_path = work_path / "body.glb"
        garment_path = work_path / "garment.glb"
        result_path = work_path / "garment_fitted.glb"

        collision_body = body_mesh
        if garment_type in LOWER_GARMENT_TYPES:
            # Con los huesos del avatar se quitan brazos y manos de la superficie
            # de proyección/colisión: un pantalón nunca debe pegarse a una mano
            # que descansa junto a la cadera.
            collision_body, removed = body_without_arms(body_mesh, body_landmarks)
            if removed:
                logger.info("Pantalón: %s vértices de brazos fuera de la colisión.", removed)
        collision_body.export(body_path, file_type="glb")
        garment_scene.export(garment_path, file_type="glb")
        command = [
            blender,
            "--background",
            "--factory-startup",
            "--python",
            str(SIMULATION_SCRIPT),
            "--",
            "--body",
            str(body_path),
            "--garment",
            str(garment_path),
            "--output",
            str(result_path),
            "--type",
            garment_type,
        ]
        logger.info(
            "Iniciando Blender para simular la prenda; timeout=%s.",
            timeout_seconds if timeout_seconds is not None else "sin límite",
        )
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise GarmentSimulationError(
                f"Blender excedió el límite de {timeout_seconds} segundos."
            ) from error
        except OSError as error:
            raise GarmentSimulationError("No se pudo ejecutar Blender.") from error

        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout).strip()
            raise GarmentSimulationError(
                "Blender no pudo completar la simulación."
                + (f" Detalle: {details[-2500:]}" if details else "")
            )
        penetration_match = re.search(
            r"PENETRATION_TRIANGLE_PAIRS=(\d+)", completed.stdout
        )
        if penetration_match is None:
            raise GarmentSimulationError(
                "Blender no devolvió el resultado de la comprobación de intersecciones."
            )
        if not result_path.is_file():
            details = (completed.stderr or completed.stdout).strip()
            raise GarmentSimulationError(
                "Blender terminó sin exportar la malla de prenda."
                + (f" Detalle: {details[-2500:]}" if details else "")
            )

        result = result_path.read_bytes()
        if len(result) < 12 or result[:4] != b"glTF":
            raise GarmentSimulationError("Blender exportó un archivo GLB inválido.")

        try:
            loaded = trimesh.load(result_path, file_type="glb", force="scene")
        except Exception as error:
            raise GarmentSimulationError(
                "No se pudo validar el GLB exportado por Blender."
            ) from error
        if not isinstance(loaded, trimesh.Scene) or not loaded.geometry:
            raise GarmentSimulationError(
                "El GLB exportado no contiene geometría de prenda."
            )
        for geometry in loaded.geometry.values():
            if (
                not isinstance(geometry, trimesh.Trimesh)
                or not np.isfinite(geometry.vertices).all()
            ):
                raise GarmentSimulationError(
                    "La simulación produjo geometría inválida."
                )

        log = completed.stdout
        if garment_type in UPPER_GARMENT_TYPES:
            height = float(np.ptp(body_mesh.vertices[:, 1]))
            result, resolved = _resolve_arm_overlaps(
                result, loaded, body_mesh, 0.018 * height if garment_type == "tank" else None
            )
            log += f"\nBODY_OVERLAP_RESOLVED={resolved}"
        return result, log, int(penetration_match.group(1))
