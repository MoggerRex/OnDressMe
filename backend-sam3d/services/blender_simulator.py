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


def simulate_static_garment(
    body_mesh: trimesh.Trimesh,
    garment_scene: trimesh.Scene,
    garment_type: str = "tshirt",
    timeout_seconds: int | None = None,
) -> tuple[bytes, str, int]:
    blender = _find_blender()
    if not SIMULATION_SCRIPT.is_file():
        raise GarmentSimulationError("No se encontró el script de simulación de Blender.")

    with tempfile.TemporaryDirectory(prefix="ondressme-cloth-") as work_dir:
        work_path = Path(work_dir)
        body_path = work_path / "body.glb"
        garment_path = work_path / "garment.glb"
        result_path = work_path / "garment_fitted.glb"

        body_mesh.export(body_path, file_type="glb")
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

        return result, completed.stdout, int(penetration_match.group(1))
