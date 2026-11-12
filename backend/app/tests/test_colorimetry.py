import io
from unittest.mock import patch
import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def create_dummy_image_bytes() -> bytes:
  """Genera una imagen sintética en memoria codificada como JPEG para las pruebas."""
  img = np.ones((200, 200, 3), dtype=np.uint8) * 210  # Imagen gris clara
  _, encoded = cv2.imencode(".jpg", img)
  return encoded.tobytes()


@patch("app.services.colorimetry.analyzer.mp_face_detection.FaceDetection")
def test_analyze_colorimetry_success(mock_face_detection):
  # 1. Configuramos el mock de MediaPipe para simular que SÍ encontró un rostro
  mock_instance = mock_face_detection.return_value.__enter__.return_value
  mock_detection_obj = type(
      "Detection",
      (object,),
      {
          "location_data": type(
              "LocData",
              (object,),
              {
                  "relative_bounding_box": type(
                      "BBox",
                      (object,),
                      {"xmin": 0.2, "ymin": 0.2, "width": 0.6, "height": 0.6},
                  )()
              },
          )()
      },
  )()
  mock_instance.process.return_value.detections = [mock_detection_obj]

  # 2. Preparamos el archivo simulado
  img_bytes = create_dummy_image_bytes()

  # 3. Ejecutamos la petición POST al endpoint
  response = client.post(
      "/api/colorimetry?profile_id=user_abc123",
      files={"image": ("face.jpg", io.BytesIO(img_bytes), "image/jpeg")},
  )

  # 4. Verificamos las assertions
  assert response.status_code == 200
  data = response.json()
  assert data["profile_id"] == "user_abc123"
  assert data["status"] == "completed"
  assert "season" in data["result"]
  assert "undertone" in data["result"]
  assert "contrast" in data["result"]
  assert "metrics" in data["result"]


@patch("app.services.colorimetry.analyzer.mp_face_detection.FaceDetection")
def test_analyze_colorimetry_no_face(mock_face_detection):
  # Simulamos que MediaPipe NO detecta ningún rostro en la imagen
  mock_instance = mock_face_detection.return_value.__enter__.return_value
  mock_instance.process.return_value.detections = None

  img_bytes = create_dummy_image_bytes()

  response = client.post(
      "/api/colorimetry?profile_id=user_abc123",
      files={"image": ("object.jpg", io.BytesIO(img_bytes), "image/jpeg")},
  )

  # Debe retornar un error 422 indicando que no se detectó un rostro
  assert response.status_code == 422
  assert "No se detectó un rostro claro" in response.json()["detail"]