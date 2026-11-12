"""Convierte Fashion-MNIST IDX comprimido a carpetas de imagenes etiquetadas."""

from __future__ import annotations

import argparse
import gzip
import struct
from pathlib import Path

import numpy as np
from PIL import Image


CLASS_NAMES = {
    0: "camisetas",
    1: "pantalones",
    2: "sueteres",
    3: "vestidos",
    4: "abrigos",
    6: "camisas",
}


def read_images(images_path: Path) -> np.ndarray:
    with gzip.open(images_path, "rb") as file:
        magic, count, rows, columns = struct.unpack(">IIII", file.read(16))
        if magic != 2051:
            raise ValueError(f"El archivo de imagenes no es IDX3 valido: {images_path}")
        data = np.frombuffer(file.read(), dtype=np.uint8)

    expected_size = count * rows * columns
    if data.size != expected_size:
        raise ValueError(
            f"El archivo contiene {data.size} pixeles; se esperaban {expected_size}."
        )
    return data.reshape(count, rows, columns)


def read_labels(labels_path: Path) -> np.ndarray:
    with gzip.open(labels_path, "rb") as file:
        magic, count = struct.unpack(">II", file.read(8))
        if magic != 2049:
            raise ValueError(f"El archivo de etiquetas no es IDX1 valido: {labels_path}")
        labels = np.frombuffer(file.read(), dtype=np.uint8)

    if labels.size != count:
        raise ValueError(f"Hay {labels.size} etiquetas; se esperaban {count}.")
    return labels


def prepare_dataset(
    images_path: Path,
    labels_path: Path,
    output_dir: Path,
    max_per_class: int | None,
) -> None:
    images = read_images(images_path)
    labels = read_labels(labels_path)
    if len(images) != len(labels):
        raise ValueError("La cantidad de imagenes y etiquetas no coincide.")

    counts = {class_id: 0 for class_id in CLASS_NAMES}
    for index, raw_label in enumerate(labels):
        class_id = int(raw_label)
        if class_id not in CLASS_NAMES:
            continue
        if max_per_class is not None and counts[class_id] >= max_per_class:
            continue

        class_dir = output_dir / CLASS_NAMES[class_id]
        class_dir.mkdir(parents=True, exist_ok=True)
        filename = f"fashion_{class_id}_{counts[class_id]:05d}.png"
        Image.fromarray(images[index]).save(class_dir / filename)
        counts[class_id] += 1

    print(f"Dataset creado en: {output_dir}")
    for class_id, class_name in CLASS_NAMES.items():
        print(f"{class_name}: {counts[class_id]} imagenes")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Descomprime y organiza Fashion-MNIST para el clasificador."
    )
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dataset_fashion_mnist"),
    )
    parser.add_argument(
        "--max-per-class",
        type=int,
        default=500,
        help="Imagenes por clase; usa 0 para convertir todas.",
    )
    args = parser.parse_args()
    max_per_class = None if args.max_per_class == 0 else args.max_per_class
    prepare_dataset(args.images, args.labels, args.output, max_per_class)


if __name__ == "__main__":
    main()
