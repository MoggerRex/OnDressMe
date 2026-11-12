import cv2
import mediapipe as mp
import numpy as np
from fastapi import HTTPException, UploadFile

# Inicializar utilidades de MediaPipe Face Detection / Mesh
mp_face_detection = mp.solutions.face_detection


async def analyze_face_colorimetry(upload_file: UploadFile) -> dict:
    contents = await upload_file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        raise HTTPException(
            status_code=400, detail="No se pudo decodificar la imagen."
        )

    h, w, _ = img.shape

    # 1. Validación de Rostro usando MediaPipe
    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    with mp_face_detection.FaceDetection(
        model_selection=1, min_detection_confidence=0.6
    ) as detector:
        results = detector.process(rgb_img)

        if not results.detections:
            raise HTTPException(
                status_code=422,
                detail=(
                    "No se detectó un rostro claro en la imagen. Por favor, asegúrate"
                    " de subir un primer plano de tu cara con buena iluminación y sin"
                    " obstrucciones."
                ),
            )

        # Tomamos la primera detección y sus coordenadas relativas
        detection = results.detections[0]
        bboxC = detection.location_data.relative_bounding_box
        xmin = int(bboxC.xmin * w)
        ymin = int(bboxC.ymin * h)
        box_width = int(bboxC.width * w)
        box_height = int(bboxC.height * h)

        # Asegurar límites dentro de la imagen
        xmin, ymin = max(0, xmin), max(0, ymin)
        xmax, ymax = min(w, xmin + box_width), min(h, ymin + box_height)

    # 2. Análisis de Piel (Región de las mejillas dentro del rostro detectado)
    face_crop = img[ymin:ymax, xmin:xmax]
    fh, fw, _ = face_crop.shape

    if fh < 20 or fw < 20:
        raise HTTPException(
            status_code=422,
            detail="La foto está muy alejada. Acércate más a la cámara.",
        )

    # Recortar zona de mejillas (área central-inferior del rostro)
    cheeks_roi = face_crop[
        int(fh * 0.4) : int(fh * 0.7), int(fw * 0.25) : int(fw * 0.75)
    ]

    # Convertir a LAB para evaluar temperatura de piel
    lab_cheeks = cv2.cvtColor(cheeks_roi, cv2.COLOR_BGR2LAB)
    _, _, mean_b = cv2.mean(lab_cheeks)[:3]

    # Umbral de temperatura (canal b* en LAB: > 128.5 es cálido)
    is_warm = mean_b > 128.5

    # 3. Análisis de Contraste (Piel vs Ojos/Cejas superiores del rostro)
    upper_face_roi = face_crop[
        int(fh * 0.15) : int(fh * 0.4), int(fw * 0.2) : int(fw * 0.8)
    ]
    gray_face = cv2.cvtColor(cheeks_roi, cv2.COLOR_BGR2GRAY)
    gray_features = cv2.cvtColor(upper_face_roi, cv2.COLOR_BGR2GRAY)

    mean_skin_brightness = np.mean(gray_face)
    mean_feature_brightness = np.mean(
        gray_features
    )  # Refleja oscuridad de cejas/ojos

    contrast_diff = abs(
        float(mean_skin_brightness) - float(mean_feature_brightness)
    )
    is_high_contrast = contrast_divider = contrast_diff > 30.0

    # 4. Motor de Reglas de Colorimetría (4 Estaciones)
    if is_warm:
        if is_high_contrast or mean_feature_brightness < 85:
            season = "Otoño"
            description = (
                "Tonos cálidos con profundidad. Te favorecen los colores tierra,"
                " terracota, verde oliva, mostaza y marrones cálidos."
            )
        else:
            season = "Primavera"
            description = (
                "Tonos cálidos y luminosos. Te favorecen los colores vibrantes y"
                " claros como durazno, coral, verde manzana e marfil."
            )
    else:
        if is_high_contrast:
            season = "Invierno"
            description = (
                "Tonos fríos con alto contraste. Te favorecen los colores puros e"
                " intensos como negro, blanco puro, rojo cereza y azul rey."
            )
        else:
            season = "Verano"
            description = (
                "Tonos fríos y suaves. Te favorecen los colores pastel apagados,"
                " azul suave, rosa polvoriento y gris perla."
            )

    return {
        "season": season,
        "undertone": "Cálido" if is_warm else "Frío",
        "contrast": "Alto" if is_high_contrast else "Suave / Bajo",
        "description": description,
        "metrics": {
            "skin_warmth_index": float(mean_b),
            "contrast_index": float(contrast_diff),
        },
    }