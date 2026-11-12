"""Clasificacion de prendas con embeddings de DINOv2.

El modulo puede ejecutarse de forma independiente para entrenar y predecir:

    python classifier.py demo
    python classifier.py train --dataset dataset_ropa
    python classifier.py predict --image dataset_ropa/camisas/ejemplo.jpg
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import joblib
import torch
from PIL import Image, ImageDraw
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder
from torchvision import transforms


MODEL_NAME = "dinov2_vits14"
IMAGE_SIZE = 224
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_ARTIFACT = Path("outfit_classifier.joblib")


def load_dino(device: torch.device) -> torch.nn.Module:
    """Carga DINOv2 desde PyTorch Hub y lo deja listo para inferencia."""
    model = torch.hub.load("facebookresearch/dinov2", MODEL_NAME)
    model.to(device)
    model.eval()
    return model


def image_transform() -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=(0.485, 0.456, 0.406),
                std=(0.229, 0.224, 0.225),
            ),
        ]
    )


def extract_embedding(
    image_path: Path,
    model: torch.nn.Module,
    transform: transforms.Compose,
    device: torch.device,
) -> Any:
    """Extrae un embedding 1D de una imagen usando la misma transformacion del entrenamiento."""
    try:
        with Image.open(image_path) as image:
            tensor = transform(image.convert("RGB")).unsqueeze(0).to(device)
    except (OSError, ValueError) as exc:
        raise ValueError(f"No se pudo abrir la imagen '{image_path}': {exc}") from exc

    with torch.inference_mode():
        embedding = model(tensor)
    return embedding.detach().cpu().numpy()[0]


def dataset_images(dataset_dir: Path) -> list[tuple[Path, str]]:
    """Devuelve imagenes y etiquetas a partir de subcarpetas de la raiz del dataset."""
    if not dataset_dir.is_dir():
        raise FileNotFoundError(f"No existe la carpeta del dataset: {dataset_dir}")

    samples = [
        (image_path, label_dir.name)
        for label_dir in sorted(path for path in dataset_dir.iterdir() if path.is_dir())
        for image_path in sorted(label_dir.iterdir())
        if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS
    ]
    if not samples:
        raise ValueError(
            f"No se encontraron imagenes en subcarpetas de '{dataset_dir}'. "
            "Ejemplo esperado: dataset_ropa/camisas/foto.jpg"
        )
    if len({label for _, label in samples}) < 2:
        raise ValueError("El entrenamiento requiere al menos dos subcarpetas/clases.")
    return samples


def train_classifier(
    dataset_dir: Path = Path("dataset_ropa"),
    artifact_path: Path = DEFAULT_ARTIFACT,
    device_name: str | None = None,
) -> dict[str, Any]:
    """Entrena LogisticRegression sobre embeddings y guarda el artefacto completo."""
    device = torch.device(device_name or ("cuda" if torch.cuda.is_available() else "cpu"))
    samples = dataset_images(dataset_dir)
    model = load_dino(device)
    transform = image_transform()

    embeddings = []
    labels = []
    for image_path, label in samples:
        embeddings.append(extract_embedding(image_path, model, transform, device))
        labels.append(label)

    label_encoder = LabelEncoder()
    encoded_labels = label_encoder.fit_transform(labels)
    classifier = LogisticRegression(max_iter=1000, random_state=42)
    classifier.fit(embeddings, encoded_labels)

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "classifier": classifier,
            "label_encoder": label_encoder,
            "model_name": MODEL_NAME,
            "image_size": IMAGE_SIZE,
        },
        artifact_path,
    )
    summary = {
        "artifact": str(artifact_path),
        "images": len(samples),
        "classes": list(label_encoder.classes_),
        "device": str(device),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def predict_garment(
    image_path: Path,
    artifact_path: Path = DEFAULT_ARTIFACT,
    device_name: str | None = None,
) -> dict[str, Any]:
    """Predice una prenda y devuelve su nombre junto con confianza porcentual."""
    if not artifact_path.is_file():
        raise FileNotFoundError(
            f"No existe el clasificador '{artifact_path}'. Ejecuta primero el entrenamiento."
        )
    artifact = joblib.load(artifact_path)
    if artifact.get("model_name") != MODEL_NAME:
        raise ValueError("El artefacto no fue creado con el modelo DINOv2 esperado.")

    device = torch.device(device_name or ("cuda" if torch.cuda.is_available() else "cpu"))
    model = load_dino(device)
    embedding = extract_embedding(image_path, model, image_transform(), device)
    classifier = artifact["classifier"]
    encoded_prediction = classifier.predict([embedding])[0]
    label_encoder: LabelEncoder = artifact["label_encoder"]
    probabilities = classifier.predict_proba([embedding])[0]
    confidence = float(probabilities.max() * 100)
    result = {
        "prenda": str(label_encoder.inverse_transform([encoded_prediction])[0]),
        "confianza": round(confidence, 2),
        "confianza_texto": f"{confidence:.2f}%",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def predecir_prenda(path_imagen: str | Path) -> str:
    """Interfaz solicitada para inferencia desde codigo Python."""
    result = predict_garment(Path(path_imagen), Path(os.getenv("OUTFIT_MODEL_PATH", DEFAULT_ARTIFACT)))
    return f"{result['prenda']} ({result['confianza_texto']})"


def create_demo_dataset(dataset_dir: Path) -> Path:
    """Crea imagenes locales simples para probar el flujo sin datos de la computadora A."""
    colors = {"camisas": (55, 125, 220), "pantalones": (45, 50, 65), "chaquetas": (190, 75, 55)}
    for label, color in colors.items():
        label_dir = dataset_dir / label
        label_dir.mkdir(parents=True, exist_ok=True)
        for index in range(3):
            image = Image.new("RGB", (IMAGE_SIZE, IMAGE_SIZE), color)
            draw = ImageDraw.Draw(image)
            draw.rectangle((20 + index * 3, 20, 204, 204), outline="white", width=4)
            image.save(label_dir / f"demo_{index}.png")
    return dataset_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clasificador de prendas DINOv2.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    train_parser = subparsers.add_parser("train", help="Entrena con dataset_ropa/<clase>/*.jpg")
    train_parser.add_argument("--dataset", type=Path, default=Path("dataset_ropa"))
    train_parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    train_parser.add_argument("--device", default=None, help="cpu, cuda o vacio para autodetectar")

    predict_parser = subparsers.add_parser("predict", help="Predice una imagen")
    predict_parser.add_argument("--image", type=Path, required=True)
    predict_parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    predict_parser.add_argument("--device", default=None)

    demo_parser = subparsers.add_parser("demo", help="Crea dataset local, entrena y predice")
    demo_parser.add_argument("--workdir", type=Path, default=Path("demo_outfits"))
    demo_parser.add_argument("--device", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "train":
        train_classifier(args.dataset, args.artifact, args.device)
    elif args.command == "predict":
        predict_garment(args.image, args.artifact, args.device)
    else:
        dataset_dir = create_demo_dataset(args.workdir / "dataset_ropa")
        artifact = args.workdir / "outfit_classifier.joblib"
        train_classifier(dataset_dir, artifact, args.device)
        predict_garment(dataset_dir / "camisas" / "demo_0.png", artifact, args.device)


if __name__ == "__main__":
    main()
