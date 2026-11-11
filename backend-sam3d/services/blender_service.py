import logging
import os
import shutil
import subprocess
import threading


logger = logging.getLogger(__name__)
STEAM_BLENDER_PATH = (
    r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"
)


class BlenderUnavailableError(RuntimeError):
    pass


class BlenderBusyError(RuntimeError):
    pass


_simulation_lock = threading.Lock()


def _resolve_blender_executable() -> str:
    configured_path = os.environ.get("BLENDER_EXECUTABLE")
    if configured_path:
        if not os.path.isfile(configured_path):
            raise BlenderUnavailableError(
                "BLENDER_EXECUTABLE apunta a un archivo inexistente."
            )
        return configured_path

    executable = shutil.which("blender")
    if executable is not None:
        return executable

    if os.path.isfile(STEAM_BLENDER_PATH):
        return STEAM_BLENDER_PATH

    raise BlenderUnavailableError(
        "Blender no está instalado o no está en PATH. Configura "
        "BLENDER_EXECUTABLE con la ruta completa a blender.exe."
    )


def run_blender_simulation(
    body_path: str,
    garment_path: str,
    output_path: str,
) -> None:
    executable = _resolve_blender_executable()
    try:
        timeout_seconds = int(os.environ.get("BLENDER_TIMEOUT_SECONDS", "300"))
    except ValueError as error:
        raise RuntimeError("BLENDER_TIMEOUT_SECONDS debe ser un entero.") from error
    if timeout_seconds <= 0:
        raise RuntimeError("BLENDER_TIMEOUT_SECONDS debe ser mayor que cero.")

    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "simulation",
        "scripts",
        "simulate_garment.py",
    )
    command = [
        executable,
        "--background",
        "--python",
        script_path,
        "--",
        body_path,
        garment_path,
        output_path,
    ]

    if not _simulation_lock.acquire(blocking=False):
        raise BlenderBusyError(
            "Ya hay una simulación ejecutándose. Espera a que termine antes de iniciar otra."
        )

    try:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            logger.error("Blender excedió el timeout de %s segundos.", timeout_seconds)
            raise TimeoutError(
                f"La simulación de Blender excedió {timeout_seconds} segundos."
            ) from error

        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip()
            logger.error(
                "Blender terminó con código %s: %s",
                result.returncode,
                details,
            )
            if result.returncode in {-1073741819, 3221225477}:
                raise RuntimeError(
                    "Blender se cerró con una violación de acceso. La escena se "
                    "simplificó para Cloth; reinicia el backend si quedaron procesos "
                    "de Blender activos y evita iniciar varias simulaciones a la vez."
                )
            raise RuntimeError(
                f"Blender no pudo completar la simulación. "
                f"Consulta el log del servidor. {details[-2000:]}"
            )

        if not os.path.isfile(output_path):
            raise RuntimeError("Blender finalizó sin exportar el GLB simulado.")
        with open(output_path, "rb") as output_file:
            if output_file.read(4) != b"glTF":
                raise RuntimeError("Blender generó una salida que no es un GLB válido.")
    finally:
        _simulation_lock.release()
