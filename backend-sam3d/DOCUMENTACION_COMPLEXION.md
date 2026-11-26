# Complexión del avatar según la foto

## Problema
SAM 3D Body predice el cuerpo con un modelo estadístico: un físico poco común
(muy musculoso, busto grande) sale cercano al promedio.

## Solución (`services/body_shape.py`)
1. **Silueta:** se recorta a la persona con `u2net_human_seg.onnx`
   (`~/.rembg/models/u2net_human_seg/`, o la ruta de `ONDRESSME_SEGMENTATION_MODEL`).
2. **Medición:** para brazos, piernas, cadera, cintura y pecho se compara el ancho
   de la silueta con el de la malla predicha. El busto se estima solo en fotos
   giradas (de 20° a 80°), donde dibuja parte del contorno.
3. **Ropa:** donde no se ve piel (color de la cara) solo se cree parte del ancho extra.
4. **Esculpido:** cada parte se ensancha alrededor de su hueso; el busto avanza hacia
   delante. Las articulaciones no se mueven, así que la ropa se sigue ajustando.
5. **Corrección manual:** panel «Complexión» y `POST /adjust-avatar`
   (`avatar_id`, `shape` = `{"bust": 1.3, "arms": 1.2}`).

Se descartó optimizar los parámetros de forma del modelo contra la silueta:
coincidía mejor, pero rellenaba con grasa (el fisicoculturista salía obeso).

## Resultados (coincidencia entre silueta de la foto y del avatar)

| Foto | Antes | Después | Factores medidos |
|---|---|---|---|
| `hombre_mamado.jpg` | 84 % | 90 % | pecho 1.24, cintura 0.95, brazos 1.50, piernas 1.28 |
| `Prueba_foto_mujer.jpg` | 76 % | 83 % | busto 1.60, pecho 1.27, cintura 1.28, cadera 1.29 |
| `hombre_guapo.jpeg` | 83 % | 86 % | brazos 1.22, piernas 1.09 |

## Límites
- Da volumen, no definición muscular: no aparecen abdominales ni estrías.
- La ropa holgada se confunde en parte con el cuerpo (cintura de la mujer, brazos
  de `hombre_guapo` con manga larga). Conviene corregir con los controles.
- Con una sola foto la profundidad (busto, abdomen, glúteos) es una estimación.
- El avatar conserva la pose de la foto; con brazos en alto o piernas cruzadas la
  ropa se ajusta mal. Para probar prendas conviene una foto de frente, de pie.
- Sin el modelo de silueta se genera el cuerpo predicho y se ajusta a mano.
- El backend recuerda los últimos 12 cuerpos base para poder re-esculpirlos.
