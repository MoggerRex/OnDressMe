from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

import numpy as np
import trimesh

from services.blender_simulator import simulate_static_garment
from services.garment_pipeline import load_garment_mesh


_ITEM_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_BODY_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ITEM_FIELDS = (
    "id",
    "name",
    "source_filename",
    "download_filename",
    "garment_type",
    "source_sha256",
    "created_at",
    "pipeline_info",
)
_store_lock = threading.RLock()
_processing_locks: dict[str, threading.Lock] = {}


class GarmentLibraryError(RuntimeError):
    """Raised when the local garment library cannot be read or updated."""


@dataclass(frozen=True)
class GarmentLibraryResult:
    item: dict[str, str]
    file_path: Path
    pipeline_info: str
    cached: bool


def _library_root() -> Path:
    configured = os.environ.get("ONDRESSME_WARDROBE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "storage" / "wardrobe"


def _body_directory(body_fingerprint: str) -> Path:
    if not _BODY_ID_PATTERN.fullmatch(body_fingerprint):
        raise GarmentLibraryError("La huella del cuerpo no es válida.")
    return _library_root() / body_fingerprint


def body_fingerprint(
    body_mesh: trimesh.Trimesh,
    landmarks: dict[str, np.ndarray],
) -> str:
    digest = hashlib.sha256()
    digest.update(b"ondressme-body-v1\0")
    for array in (body_mesh.vertices, body_mesh.faces):
        normalized = np.ascontiguousarray(array)
        if normalized.dtype.kind == "f":
            normalized = np.ascontiguousarray(
                np.round(normalized.astype(np.float64), decimals=5),
                dtype="<f8",
            )
        else:
            normalized = np.ascontiguousarray(normalized, dtype="<i8")
        digest.update(str(normalized.shape).encode("ascii"))
        digest.update(normalized.tobytes())

    for name in sorted(landmarks):
        points = np.ascontiguousarray(
            np.round(np.asarray(landmarks[name], dtype=np.float64), decimals=5),
            dtype="<f8",
        )
        if points.shape != (3,) or not np.isfinite(points).all():
            raise GarmentLibraryError(
                f"El ancla corporal '{name}' no contiene coordenadas válidas."
            )
        digest.update(name.encode("utf-8"))
        digest.update(points.tobytes())
    return digest.hexdigest()


def source_fingerprint(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _read_items(body_id: str) -> list[dict[str, str]]:
    manifest_path = _body_directory(body_id) / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GarmentLibraryError(
            "No se pudo leer el índice local de prendas."
        ) from error
    items = manifest.get("items") if isinstance(manifest, dict) else None
    if not isinstance(items, list) or not all(
        isinstance(item, dict)
        and all(isinstance(item.get(field), str) for field in _ITEM_FIELDS)
        and _ITEM_ID_PATTERN.fullmatch(item["id"])
        and _BODY_ID_PATTERN.fullmatch(item["source_sha256"])
        for item in items
    ):
        raise GarmentLibraryError("El índice local de prendas está dañado.")
    return items


def _artifact_path(body_id: str, item_id: str) -> Path:
    if not _ITEM_ID_PATTERN.fullmatch(item_id):
        raise GarmentLibraryError("El identificador de prenda no es válido.")
    return _body_directory(body_id) / f"{item_id}.glb"


def list_garments(body_id: str) -> list[dict[str, str]]:
    with _store_lock:
        items = _read_items(body_id)
        for item in items:
            if not _artifact_path(body_id, item["id"]).is_file():
                raise GarmentLibraryError(
                    "Falta un archivo GLB registrado en la biblioteca local."
                )
        return sorted(
            items,
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )


def get_garment(
    body_id: str,
    item_id: str,
) -> tuple[dict[str, str], Path] | None:
    with _store_lock:
        item = next(
            (entry for entry in _read_items(body_id) if entry["id"] == item_id),
            None,
        )
        if item is None:
            return None
        file_path = _artifact_path(body_id, item_id)
        if not file_path.is_file():
            raise GarmentLibraryError(
                "Falta el archivo GLB solicitado en la biblioteca local."
            )
        return item, file_path


def find_cached_garment(
    body_id: str,
    source_id: str,
    garment_type: str,
) -> tuple[dict[str, str], Path] | None:
    with _store_lock:
        item = next(
            (
                entry
                for entry in _read_items(body_id)
                if entry.get("source_sha256") == source_id
                and entry.get("garment_type") == garment_type
            ),
            None,
        )
        if item is None:
            return None
        file_path = _artifact_path(body_id, item["id"])
        if not file_path.is_file():
            raise GarmentLibraryError(
                "La prenda existe en el índice, pero falta su archivo GLB."
            )
        return item, file_path


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def save_garment(
    body_id: str,
    source_id: str,
    source_filename: str,
    garment_type: str,
    glb: bytes,
    pipeline_info: str,
) -> tuple[dict[str, str], Path]:
    if len(glb) < 12 or glb[:4] != b"glTF":
        raise GarmentLibraryError("No se guardó una malla GLB válida.")

    source_name = PureWindowsPath(source_filename).name
    source_stem = re.sub(
        r"[\x00-\x1f\x7f/\\]",
        "_",
        Path(source_name).stem,
    ).strip(" .")[:120] or "Prenda"
    item_id = uuid.uuid4().hex
    directory = _body_directory(body_id)
    directory.mkdir(parents=True, exist_ok=True)
    file_path = _artifact_path(body_id, item_id)
    temporary_path = file_path.with_name(f".{item_id}.tmp")
    try:
        temporary_path.write_bytes(glb)
        os.replace(temporary_path, file_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    item = {
        "id": item_id,
        "name": source_stem,
        "source_filename": source_name,
        "download_filename": f"{source_stem}_adaptada.glb",
        "garment_type": garment_type,
        "source_sha256": source_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_info": pipeline_info,
    }

    with _store_lock:
        items = _read_items(body_id)
        _write_json_atomic(
            directory / "manifest.json",
            {"version": 1, "items": [*items, item]},
        )
    return item, file_path


def _processing_lock(key: str) -> threading.Lock:
    with _store_lock:
        return _processing_locks.setdefault(key, threading.Lock())


def process_or_reuse_garment(
    body_mesh: trimesh.Trimesh,
    body_landmarks: dict[str, np.ndarray],
    mesh_contents: bytes,
    filename: str,
    garment_type: str,
) -> GarmentLibraryResult:
    body_id = body_fingerprint(body_mesh, body_landmarks)
    source_id = source_fingerprint(mesh_contents)
    lock_key = f"{body_id}:{garment_type}:{source_id}"

    with _processing_lock(lock_key):
        cached = find_cached_garment(body_id, source_id, garment_type)
        if cached is not None:
            item, file_path = cached
            return GarmentLibraryResult(
                item=item,
                file_path=file_path,
                pipeline_info=item["pipeline_info"],
                cached=True,
            )

        build = load_garment_mesh(
            mesh_contents,
            filename,
            body_mesh,
            garment_type,
            body_landmarks=body_landmarks,
        )
        glb, _, penetration_pairs = simulate_static_garment(
            body_mesh,
            build.scene,
            garment_type,
        )
        build.metrics["simulation"] = "blender_completed"
        build.metrics["penetration_check"] = "triangle_surface_intersections"
        build.metrics["penetration_triangle_pairs"] = penetration_pairs
        warnings = build.warnings
        if penetration_pairs:
            warnings += (
                "La comprobación BVH encontró "
                f"{penetration_pairs} pares de triángulos intersectados; revisa el resultado.",
            )
        pipeline_info = json.dumps(
            {"metrics": build.metrics, "warnings": warnings},
            ensure_ascii=True,
            separators=(",", ":"),
        )
        item, file_path = save_garment(
            body_id,
            source_id,
            filename,
            garment_type,
            glb,
            pipeline_info,
        )
        return GarmentLibraryResult(
            item=item,
            file_path=file_path,
            pipeline_info=pipeline_info,
            cached=False,
        )
