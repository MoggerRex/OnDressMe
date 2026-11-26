# Segmentación y patronaje de camisas

## 1. Análisis del proyecto

| Parte | Dónde está |
|---|---|
| Subida de la prenda | `src/App.jsx` → `src/services/ondressmeApi.js` → `POST /generate-garment` (`server.py`) |
| Carga de mallas (GLB/OBJ, `trimesh`) | `services/garment_pipeline.py::read_garment_scene` |
| Colocación sobre el avatar | `load_garment_mesh` (escala por secciones, mangas, torso) → `services/blender_simulator.py` (tela en Blender 4.2) |
| Caché de prendas | `services/garment_library.py` |
| Visor | `src/features/mannequin/MannequinScene.jsx` (`three`, `@react-three/fiber`) |
| Bibliotecas de geometría | `numpy`, `scipy`, `trimesh`; no se añadió ninguna |

Las camisas (`tshirt`, `tank`, `longsleeve`) se montan ahora cosiendo sus piezas
(sección 4). El ajuste directo anterior queda como respaldo y sigue siendo el
único método para pantalones, shorts y zapatos. El archivo subido nunca se altera.

## 2. Hallazgo sobre las prendas de prueba

Las UV de `camisa_manga_corta_1.obj` ya son su patronaje: delantero, espalda, dos
mangas y cuello. `camisa_manga_corta_2`, `Camisa_manga_larga` y `Camisa_sin_mangas`
también traen islas UV que corresponden a piezas. Por eso hay dos métodos de corte
y se elige solo.

## 3. Módulos (`services/patterns/`)

| Módulo | Qué hace | Algoritmo | Límite |
|---|---|---|---|
| `analyzer` (GarmentAnalyzer) | Vértices, caras, dimensiones, islas UV, aberturas | Soldado por posición, componentes conexas, bordes | Supone prenda erguida (eje Y) |
| `segmenter` (GarmentSegmenter) | Una etiqueta de pieza por triángulo | `uv`: islas UV nombradas por posición. `geometry`: plano en la axila (mangas), media profundidad por altura (hombros y costados), banda alrededor del escote (cuello) | `geometry` sigue los bordes de los triángulos (contorno dentado) y falla en mallas de muy pocos polígonos (`camisa_manga_corta_2` sin sus UV) |
| `flatten` (PatternGenerator) | Patrón 2D de cada pieza y costuras | Apertura del tubo por la costura bajo el brazo; LSCM + ARAP | No añade pinzas; una superficie con doble curvatura no se aplana sin distorsión |
| `editor` (PatternEditor + reconstrucción) | Ancho y largo por pieza | Deformación en el marco de cada pieza; costuras compartidas y corrección armónica en la vecina | Estira triángulos, no añade tela; factores de 70 % a 140 % |
| `fitting` (BodyFitting) | Holgura en pecho, cintura, cadera y brazos; sugerencia | Perímetros aproximados (elipse y círculo) | Orientativo, no es una toma de medidas |
| `validation` (ClothValidation) | Huecos en costuras, caras invertidas, cambio de área, vértices dentro del cuerpo | Comparación antes/después | No detecta autointersecciones |

No se usa el despliegue UV como patrón: en la camisa de prueba su distorsión de
longitudes es del 3–15 %, frente a 0.1–0.4 % de LSCM + ARAP.

## 4. Costura y física (`sewing.py` + `simulation/scripts/sew_garment.py`)

1. **Cortar:** delantero, espalda, cada manga en delantera y trasera, y cuello.
2. **Forma de reposo:** las piezas diseñadas, a la talla del avatar (contorno +
   holgura del ajuste) y con tus cambios de ancho/largo. De ahí salen las
   longitudes de la tela en la simulación.
3. **Colocar:** las piezas rodean el cuerpo casi sin deformar, con los brazos abiertos.
4. **Coser:** los resortes de costura de Blender juntan cada par de bordes; después
   los brazos bajan y la prenda cae por gravedad. No hay puntos fijos en los hombros.
5. **Acabado:** se cierran las costuras, se suaviza el ruido del solver y se saca
   lo que quede dentro del cuerpo. Se conserva la malla, las UV y los materiales.

Más de 9 000 vértices: se simula una copia ligera y el movimiento se traslada a la
malla completa. Si la prenda se resbala de los hombros se reintenta una vez; si
aun así falla, o quedan costuras abiertas, se usa el ajuste directo y se avisa.

## 5. Resultados con el avatar de `hombre_guapo.jpeg`

| Prenda | Método | Tiempo aproximado |
|---|---|---|
| `camisa_manga_corta_1` (ajustado, normal, holgado) | cosida | 1–3 min |
| `Camisa_manga_larga` | cosida | 1 min |
| `Camisa_sin_mangas` (82 000 caras) | cosida (copia ligera) | 1 min (sin la copia: 95 min) |
| `camisa_manga_corta_2` | ajuste directo (su cuello no se deja coser) | 7 min |

- Corte `geometry` sin UV: coincide en el 93 % de los triángulos con el de las UV.
- Distorsión media de los patrones: 0.1–0.4 %.
- Costuras: antes de cerrarlas, el 95 % de las puntadas queda a menos de 2 cm.

## 6. Uso

1. Reiniciar el backend (`server.py`).
2. Generar el maniquí y elegir el archivo de la camisa.
3. «Simular» cose la prenda tal cual. «3. Piezas y patrones» permite ver las
   piezas, cambiar ancho/largo y «Coser las piezas y probar».

Sin cambios de ancho o largo, ambos botones dan la misma prenda.

API: `POST /garment-patterns` (`garment_mesh`, `garment_type`, `fit`, `avatar_id`
opcional) y el campo `edits` de `POST /generate-garment`, por ejemplo
`{"front": {"width": 1.1, "length": 1.0}}`.

## 7. Límites y pendientes

- La tela es genérica (punto de algodón); no hay selección de material.
- Blender puede dejar algunos pares de triángulos cruzando el cuerpo (decenas).
- Prendas con partes sueltas (cuellos con solapa) caen al ajuste directo, y tardan
  más porque primero se intenta coser.
- Puños, exportar patrones (SVG/DXF), márgenes de costura y editar el contorno
  punto a punto.
- Pantalones y shorts.
