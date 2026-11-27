# OnDressMe — Especificación funcional y técnica (uso interno)

> **Fecha de auditoría:** 2026-11-26
> **Ramas auditadas (remoto `origin`, tras `git fetch`):**
>
> | Rama | Commit | Último mensaje |
> |---|---|---|
> | `frontend` | `6c0129b` | `transicion` |
> | `backend` | `9df7dac` (local: `9a9c9c5`, 1 commit adelante, sin subir) | `cambios_movil` / `cambio_temas` |
> | `NoMas_3D_Object` | `cca65e1` | `Aplicacion_prendas_mejorada` |
> | `NoMas_3D_ObjectLeo` | `4865d5c` | `Mejorado blurreo detalle de prenda` |
>
> **Convenciones:** ✅ existe y funciona · 🟡 existe parcial / desconectado · ⬜ planeado (no hay código) · `[POR DEFINIR / VERIFICAR]` = no verificable en el código.

---

## 0. Hallazgos clave (resumen ejecutivo)

1. **Hay dos proyectos distintos en el repositorio, no uno.**
   - **Monorepo distribuido** (`frontend` y `backend`): carpetas `frontend/`, `backend/`, `workers/`, `infra/`, `shared/`, `docs/`. API central FastAPI con cola Redis.
   - **Prototipo 3D monolítico** (`NoMas_3D_Object` y `NoMas_3D_ObjectLeo`): frontend Vite en la **raíz** (`src/`) y un servidor FastAPI independiente en `backend-sam3d/server.py`, que carga SAM 3D Body en la GPU local y llama a Blender.
   - Los dos **no comparten** estructura de carpetas, cliente HTTP, puertos (ambos usan `:8000`), contratos ni variables de entorno (`VITE_API_BASE_URL` frente a `VITE_API_URL`). Ninguna rama integra a otra.
2. **La colorimetría SÍ está implementada** (lo contrario de lo que dice el contexto). Existe en `backend` (`backend/app/services/colorimetry/analyzer.py`, `POST /api/colorimetry`) y el onboarding de `frontend` la consume. Es una heurística básica (MediaPipe + LAB) sin persistencia.
3. **La "generación 3D de prendas a partir de fotos" no ocurre dentro de OnDressMe.** El servidor 3D rechaza las fotos con HTTP 422 (`backend-sam3d/server.py`, `/generate-garment`). La malla GLB/OBJ se genera **fuera** del proyecto (Garment3DGen + InstantMesh, según el `README.md` de la rama). Dentro de OnDressMe sí están el **ajuste al cuerpo y la simulación de tela en Blender**, que son la parte lenta.
4. **El avatar 3D funciona**, e incluye un módulo específico de complexión para cuerpos voluminosos o poco comunes: `services/body_shape.py` y `POST /adjust-avatar`. Ese módulo **solo existe en `NoMas_3D_Object`**; `NoMas_3D_ObjectLeo` no lo tiene.
5. **El clóset virtual 3D de Leo** (`src/features/closet/room/`) es puramente de frontend. Carga GLB/OBJ locales en memoria, las cuelga de barras con un "drapeado" procedural por corte (playera manga corta / manga larga) y **no llama a ningún backend** (el propio código lo dice en `ClosetPage.jsx`).
6. **No hay base de datos.** Todo el estado vive en memoria del proceso (avatares: 3 en caché + 12 bases), en el sistema de archivos (`backend-sam3d/storage/wardrobe/`), en Redis (jobs) o en el navegador (`localStorage` / `useState`).
7. **Los workers del monorepo son stubs** que marcan todos los jobs como `failed` a propósito (`workers/avatar/worker.py`, `workers/outfits/worker.py`). El código real del avatar vive en el servidor 3D y no está conectado a la cola.

---

## 1. Estado actual por rama

### 1.1 `frontend` — UI web (React 19 + Vite + Tailwind + R3F)

| Aspecto | Detalle |
|---|---|
| Entrada | `frontend/src/main.jsx` → `App.jsx` → `page/Main.jsx` (≈750 líneas, monolito de UI) |
| Vistas | `DressMe`, `Avatar`, `Closet`, `Profile` (estado `activeView`, sin router) |
| Onboarding | `features/onboarding/OnboardingModal.jsx` + `ClosetWorldScene.jsx` (escena 3D con scroll de 5 capítulos) |
| Maniquí | `features/mannequin/MannequinScene.jsx`: maniquí **procedural** (primitivas Three.js) coloreado por prenda y deformado por `bodyMetrics`. **No carga GLB.** |
| Llamadas a backend | Solo `POST /api/colorimetry` (onboarding). `services/api.js` define `getJob()`, pero **ninguna vista lo usa**. |
| Persistencia | `localStorage`: `ondressme-theme`, `ondressme-profile`, `ondressme-profile-created`. Looks guardados y medidas **solo en memoria** (se pierden al recargar, aunque la UI dice "Your measurements are saved on this device"). |
| Datos | Armario **hardcodeado** (12 prendas en `wardrobe` dentro de `Main.jsx`), con 2 looks por defecto. |
| Archivos vacíos (0 líneas) | `context/AppContext.jsx`, `features/closet/ClosetDrawer.jsx`, `ClosetItem.jsx`, `features/mannequin/EmoteController.jsx`, `MannequinCanvas.jsx`, `features/profile/ProfileCard.jsx`, `ProfileSettings.jsx` |
| Madurez | UI/UX avanzada (12 temas, responsive, accesibilidad ARIA); lógica de negocio maqueta. |

**Desconexiones:** las fotos de cuerpo y de prenda del onboarding solo se previsualizan y no se envían. El botón "Add item" no tiene handler. La subida de foto en Perfil solo guarda el nombre del archivo. El selector de subtono (Warm/Cool/Neutral) es manual y no usa el resultado de colorimetría.

### 1.2 `backend` — API central (FastAPI + Redis)

| Aspecto | Detalle |
|---|---|
| App | `backend/app/main.py`: CORS, monta `/storage` como estáticos, routers `jobs` y `platform` |
| Config | `backend/app/core/config.py`: `API_HOST`, `API_PORT`, `REDIS_URL`, `STORAGE_PATH`, `MAX_UPLOAD_MB=10`, `INTERNAL_WORKER_TOKEN`, `AVATAR_WORKER_URL`, `OUTFIT_WORKER_URL` (estas dos últimas **no se usan**), `CORS_ORIGINS` |
| Jobs | `services/job_manager.py`: hash `job:{id}` + lista `{kind}_jobs` en Redis |
| Storage | `services/storage/files.py::save_upload` → `storage/uploads/{job_id}{ext}` con límite de tamaño |
| Colorimetría | `services/colorimetry/analyzer.py` (OpenCV + MediaPipe) ✅ |
| Workers | `workers/avatar/worker.py`, `workers/outfits/worker.py`: consumen la cola con `BLPOP` y **siempre responden `failed`** |
| Infra | `infra/docker-compose.yml`: Redis 7 con AOF |
| Contrato | `shared/contracts/job.schema.json` (el `kind` no incluye `garment_3d`, aunque `schemas/jobs.py` sí lo declara) |
| Tests | `backend/app/tests/test_colorimetry.py` `[POR DEFINIR / VERIFICAR]` cobertura |
| `database/`, `jobs/` | Paquetes vacíos (solo `__init__.py`) |

**Endpoints reales:**

| Método | Ruta | Estado |
|---|---|---|
| GET | `/health` | ✅ |
| POST | `/api/colorimetry?profile_id=` (multipart `image`) | ✅ síncrono, sin persistir |
| POST | `/api/avatar/jobs?profile_id=` (multipart `image`) | 🟡 encola; el worker falla siempre |
| POST | `/api/outfits/jobs` (JSON `OutfitJobRequest`) | 🟡 encola; el worker falla siempre |
| GET | `/api/jobs/{job_id}` | ✅ |
| POST | `/api/internal/jobs/{job_id}/result` (header `X-Worker-Token`) | ✅ (el token es opcional si está vacío) |
| GET | `/api/profile/{id}`, `/api/wardrobe?profile_id=` | ⬜ responden 501 |

**Observaciones:**
- `JobManager()` se instancia al importar el módulo. Si Redis no está disponible, falla en la primera petición, no al arrancar.
- Los workers escriben `status=running` **directamente en Redis**, lo que rompe la regla de `docs/architecture.md` de que "solo el backend conoce Redis".
- Hay una variable muerta en el analizador: `is_high_contrast = contrast_divider = ...`.
- Si un worker muere, el job queda en `running` para siempre: no hay *visibility timeout* ni reintentos.
- Diferencia con `frontend`: `origin/frontend` lleva 1 commit más (`6c0129b transicion`, cambios en `App.css` y `Main.jsx`). El `backend` local tiene `cambio_temas` sin subir.

### 1.3 `NoMas_3D_Object` — generación del avatar 3D y ajuste/simulación de prendas

Estructura **distinta** al monorepo: `src/` (frontend) y `backend-sam3d/` en la raíz. El repositorio de SAM 3D Body (`backend-sam3d/sam-3d-body`) **no está versionado**, se clona aparte.

| Módulo | Archivo | Función |
|---|---|---|
| Servidor | `backend-sam3d/server.py` | Carga `facebook/sam-3d-body-vith` en CUDA al arrancar (falla si no hay GPU) |
| Complexión | `services/body_shape.py` | Silueta con `u2net_human_seg.onnx` → factores `chest, waist, hips, arms, legs, bust` → esculpido por hueso |
| Esqueleto | `services/body_skeleton.py` | Asigna vértices a huesos MHR; excluye brazos en prendas inferiores |
| Ajuste | `services/garment_pipeline.py` (≈1 700 líneas), `torso_fit.py`, `sleeve_fit.py`, `leg_fit.py`, `shoe_fit.py`, `garment_rig.py`, `body_volume.py` | Escalado por secciones, mangas sobre la cadena hombro→codo→muñeca, piernas, zapatos rígidos, *rig* si el GLB trae skin, resolución de penetraciones por voxelizado |
| Patrones | `services/patterns/` (`analyzer`, `segmenter`, `flatten`, `editor`, `fitting`, `sewing`, `validation`, `service`) | Segmentación de camisas en piezas, aplanado LSCM+ARAP, edición de ancho/largo, costura en Blender |
| Simulación | `services/blender_simulator.py` + `simulation/scripts/simulate_garment.py`, `sew_garment.py` | `subprocess.run` de Blender 4.2 en modo background, **sin timeout por defecto** |
| Biblioteca | `services/garment_library.py` | Caché en disco `storage/wardrobe/{body_fingerprint}/`, deduplicada por huella de malla + cuerpo + tipo + ajuste |
| Frontend | `src/App.jsx`, `src/services/ondressmeApi.js`, `features/body/BodyShapePanel.jsx`, `features/patterns/PatternPanel.jsx`, `features/mannequin/MannequinScene.jsx` | Flujo de 3 pasos: maniquí → prenda → piezas/patrones; visor con caché LRU de 32 MB |
| Tests | `backend-sam3d/tests/` (9 archivos; la documentación reporta 65 pruebas) | `unittest` |
| Docs | `DOCUMENTACION_CAMBIOS_SAM3D.md`, `DOCUMENTACION_COMPLEXION.md`, `DOCUMENTACION_PATRONES.md` | Muy detalladas, con métricas |

**Endpoints reales (puerto 8000):**

| Método | Ruta | Entrada | Salida |
|---|---|---|---|
| POST | `/generate-3d` | multipart `image` | GLB + headers `X-Avatar-Id`, `X-Body-Shape`, `X-Body-Shape-Source` |
| POST | `/adjust-avatar` | form `avatar_id`, `shape` (JSON de factores) | GLB nuevo con nuevo `X-Avatar-Id` |
| POST | `/generate-garment` | `garment_mesh` (GLB/OBJ ≤ 64 MB), `avatar_id`, `garment_type` ∈ {`tshirt`,`tank`,`longsleeve`,`pants`,`shorts`,`shoes`}, `fit` ∈ {`tight`,`regular`,`loose`}, `edits` | GLB + `X-Pipeline-Info`, `X-Garment-Id`, `X-Garment-Cached`. Si recibe `image`, responde 422. |
| POST | `/garment-patterns` | `garment_mesh`, `garment_type`, `fit`, `avatar_id?` | JSON de piezas, patrones y medidas |
| GET | `/wardrobe/{avatar_id}` | — | `{items: [...]}` |
| GET | `/wardrobe/{avatar_id}/{item_id}/model` | — | GLB |

**Madurez:** es el módulo técnicamente más avanzado. Sus limitaciones (según el código y su propia documentación):
- Los avatares viven **en memoria** (máximo 3 en `_avatar_cache` y 12 en `_avatar_bases`). Si se reinicia el servidor, se pierde el `avatar_id` y su biblioteca queda inaccesible por API, aunque los archivos sigan en disco.
- Todo es síncrono dentro de la petición HTTP (`run_in_threadpool`). Una simulación tarda de 1 a 7 minutos (hasta 95 min sin la copia ligera), lo que expone a timeouts del navegador o de proxies.
- Es un solo proceso, que combina la GPU (SAM 3D) y la CPU (Blender) en la misma máquina.
- La malla de la prenda tiene que venir de fuera (Garment3DGen/InstantMesh no están integrados).
- Se versionaron `__pycache__/*.pyc`, `blender.crash.txt` y `graphify-out/`.
- CORS fijo a `localhost:5173`.

### 1.4 `NoMas_3D_ObjectLeo` — clóset virtual 3D

Es una **bifurcación anterior** de `NoMas_3D_Object` con trabajo propio en el frontend del clóset.

| Aspecto | Detalle |
|---|---|
| Backend | El mismo `backend-sam3d/server.py`, **sin** `/adjust-avatar` ni `/garment-patterns`. Le faltan `body_shape.py`, `torso_fit.py` y `services/patterns/`. `garment_pipeline.py`, `sleeve_fit.py`, `body_volume.py`, `blender_simulator.py` y `garment_library.py` difieren, porque son versiones anteriores. |
| Ruteo | `src/main.jsx`: si el hash es `#closet` muestra `ClosetPage`; si no, muestra `App` (el flujo de maniquí) |
| Clóset | `src/features/closet/room/`: `ClosetPage.jsx` (UI, búsqueda, subida `.glb,.obj`, nombre y corte), `ClosetRoom.jsx` (cuarto con 3 barras), `HangingGarment.jsx` (`useGLTF` / `OBJLoader`), `cloth.js` (pose colgada, gancho y normales suaves), `cuts/tshirt.js`, `cuts/longSleeve.js`, `layout.js` (3 barras × 14 ganchos, separación 0.4 m) |
| Navegación | Vista general ↔ barra ↔ detalle (con teclado, scroll y clic); el detalle desenfoca el fondo |
| Persistencia | **Ninguna.** Las prendas son `URL.createObjectURL` en memoria y el código marca pendiente persistir en "IndexedDB/backend". |
| Madurez | Buena para camisas (manga corta y manga larga). No hay cortes para pantalón, short ni zapatos. No conecta con `/wardrobe`. |

### 1.5 Otras ramas remotas (fuera del alcance, solo como referencia)

- `Worker-outfits` (`974727a DINO_V2`): `workers/outfits/classifier.py` y `prepare_fashion_mnist.py`, más un CSV de 5 750 filas de resultados. Es un clasificador de prendas que podría servir para el etiquetado automático. `[POR DEFINIR / VERIFICAR]` si sigue vigente.
- `LeoMogger_Dev`, `Blender_Python`: puntos de control antiguos del trabajo 3D.
- `Proyecto_base`: base del monorepo.

---

## 2. Flujo funcional end-to-end: existente frente a objetivo

| # | Paso del flujo objetivo | Estado | Dónde está hoy | Brecha |
|---|---|---|---|---|
| 1 | Registro / inicio de sesión | ⬜ | — | Sin BD ni autenticación. El onboarding pide nombre + email (validación por regex) y los guarda en `localStorage`. |
| 2 | Perfil | 🟡 | `frontend` (`Main.jsx` vista Profile) | `GET /api/profile` devuelve 501 |
| 3 | Foto de rostro → colorimetría | ✅/🟡 | `backend` `POST /api/colorimetry` ← `frontend` `OnboardingModal.jsx` | El resultado no se persiste ni se usa para el subtono, la paleta o las recomendaciones. El `profile_id` es `user_${Date.now()}`. |
| 4 | Foto de cuerpo completo → avatar 3D | ✅ en `NoMas_3D_Object` / 🟡 en el monorepo | `backend-sam3d` `/generate-3d` (+ `/adjust-avatar`) | El monorepo tiene el job `avatar` con worker stub. El frontend principal usa un maniquí procedural. |
| 5 | Fotos de prendas → modelo 3D | 🟡 | Externo (Garment3DGen/InstantMesh) → `/generate-garment` ajusta y simula | No hay foto→malla dentro del sistema |
| 6 | Cuestionario de gustos | ⬜ | — | — |
| 7 | Gestión del clóset | 🟡 en tres sitios | `frontend` (lista fija), `NoMas_3D_Object` (`/wardrobe` por cuerpo), `NoMas_3D_ObjectLeo` (cuarto 3D en memoria) | Tres modelos de "prenda" incompatibles |
| 8 | Prueba en visor 3D (vestir maniquí) | ✅ en `NoMas_3D_Object` / 🟡 en `frontend` | `MannequinScene.jsx` en ambas ramas (versiones distintas) | El `frontend` solo cambia colores de primitivas |
| 9 | Outfits favoritos | 🟡 | `frontend` `savedLooks` (máximo 6, en memoria) | Sin persistencia; los looks referencian prendas hardcodeadas |
| 10 | Paleta del outfit (PNG) | ✅ | `frontend` `downloadOutfitPalette()` | — |
| 11 | Amigos | ⬜ | — | — |
| 12 | Lobby compartido | ⬜ | — | Requiere tiempo real (WebSocket) |
| 13 | Publicar ropa en desuso | ⬜ | — | — |
| 14 | Favoritos de ropa de terceros o tienda | ⬜ | — | — |
| 15 | Tienda / marketplace | ⬜ | — | — |
| 16 | Recomendaciones (nodo de lenguaje) | ⬜ | `POST /api/outfits/jobs` + worker stub (Ollama/Llama, según el README) | Sin modelo ni lógica |

**Flujo objetivo propuesto (diseño):**

```text
Registro → Onboarding [rostro → colorimetría] [cuerpo → job avatar] [prendas → job garment_3d] [cuestionario]
        → Clóset (lista + cuarto 3D) → Probador 3D (avatar GLB + prendas ajustadas) → Guardar outfit
        → Social (amigos, lobby) → Marketplace (publicar, favoritos, tienda) → Recomendaciones (LLM + colorimetría + gustos)
```

---

## 3. Especificación funcional por módulo

Cada módulo indica **[Implementado]** o **[Pendiente]** por regla.

### 3.1 Cuenta, perfil y onboarding
- **[Implementado – frontend]** El onboarding es un modal de pantalla completa con 5 capítulos (`onboarding-start`, `-mirror`, `-fitting`, `-rail`, `-profile`). Se puede omitir ("Skip and explore") o cerrar con Esc. Solo aparece si no existe `ondressme-profile-created`.
- **[Implementado]** Validaciones: nombre obligatorio (máximo 48 caracteres) y email con formato válido (`/^[^\s@]+@[^\s@]+\.[^\s@]+$/`). El botón "Enter your closet" queda deshabilitado mientras no se cumplan.
- **[Pendiente]** Crear la cuenta en el servidor, verificar el email, gestionar la sesión (JWT o cookie `[POR DEFINIR]`) y un `profile_id` real en lugar de `user_${Date.now()}`.
- **Estados propuestos del onboarding:** `not_started → in_progress → completed | skipped`, por paso (`face`, `body`, `garment`, `questionnaire`).

### 3.2 Colorimetría
- **Entrada:** imagen (multipart) + `profile_id`.
- **[Implementado]** Reglas en `analyzer.py`:
  1. Detección de rostro con MediaPipe (`model_selection=1`, confianza ≥ 0.6). Si no hay rostro → 422.
  2. Si el recorte del rostro es menor de 20 px → 422 ("La foto está muy alejada").
  3. Subtono: media del canal b* (LAB) en la zona de mejillas. Si b* > 128.5 → Cálido; si no → Frío.
  4. Contraste: |brillo de mejillas − brillo de la zona ojos/cejas| > 30 → Alto.
  5. Estación: Cálido + (contraste alto o rasgos < 85) → **Otoño**; Cálido → **Primavera**; Frío + contraste alto → **Invierno**; Frío → **Verano**.
- **Salida:** `{season, undertone, contrast, description, metrics: {skin_warmth_index, contrast_index}}`.
- **[Implementado – frontend]** Traduce estación y errores al inglés y muestra "YOUR COLOR READING".
- **Limitaciones:** no corrige el balance de blancos ni la iluminación, no tiene subtono neutro (el frontend sí lo ofrece) ni sub-estaciones (12 o 16), no tiene paleta de colores asociada y no persiste nada. La lógica de errores mezcla `HTTPException(422)` interno con un `except Exception → 400`, por lo que **los 422 llegan como 400**.
- **[Pendiente]** Persistir el resultado en el perfil; añadir paleta recomendada (HEX); ofrecer la opción de usar el subtono detectado en el probador; decidir si la colorimetría se queda en el nodo central (CPU) o pasa al nodo GPU de visión `[POR DEFINIR]`.

### 3.3 Avatar 3D
- **[Implementado – `NoMas_3D_Object`]**
  - `/generate-3d`: SAM 3D Body → orienta (Y arriba, pies en y = 0) → keypoints MHR → tono de piel (mediana HSV/YCrCb en la zona de la cara; si no se detecta, usa un neutro `[180,130,110]`) → complexión desde la silueta → esculpido → GLB.
  - Si no se detecta una persona → 422.
  - Factores de complexión con rangos: `chest 0.85–1.4`, `waist 0.8–1.35`, `hips 0.85–1.4`, `arms 0.8–1.7`, `legs 0.8–1.5`, `bust 0.7–1.8`. Origen: `foto`, `sin-segmentacion`, `error` o `manual`.
  - `/adjust-avatar`: valida las claves contra `NEUTRAL` y crea **un avatar nuevo** (nuevo `avatar_id`).
- **Cuerpos voluminosos (en ajuste):** la documentación reporta una mejora en la coincidencia de silueta del 76–84 % al 83–90 %. Límites conocidos: la ropa holgada se confunde con el cuerpo, la profundidad sale de una sola foto, la pose de la foto se conserva y no hay definición muscular.
- **[Pendiente]**
  - Persistir el avatar (GLB + landmarks + factores + base) por usuario.
  - Que el `avatar_id` sobreviva a reinicios.
  - Llevar el proceso al job `avatar` del monorepo.
  - Normalizar la pose (A/T) `[POR DEFINIR]`.
  - Que el frontend principal cargue el GLB en lugar del maniquí procedural.
  - Decidir el destino de los sliders de `metricFields` del `frontend` (altura, peso, etc.), que hoy deforman primitivas y no tienen equivalente en `/adjust-avatar`.

### 3.4 Prendas 3D (ajuste + simulación)
- **Entrada:** malla GLB/OBJ (≤ 64 MB, ≤ 500 000 vértices), `garment_type`, `fit`, `edits` opcionales y `avatar_id`.
- **[Implementado]** Reglas:
  - Tipos superiores (`tshirt`, `tank`, `longsleeve`): se cosen por piezas (`patterns/sewing.py`); si falla, se usa el ajuste directo y se avisa.
  - Inferiores (`pants`, `shorts`): ajuste directo por piernas.
  - `shoes`: ajuste rígido sin Blender.
  - Multiplicadores de holgura: `tight 0.2`, `regular 1.0`, `loose 2.0` sobre `TORSO_EASE`, `SECTION_EASE`, `HIP_EASE` y `LEG_EASE`.
  - Más de 9 000 vértices → se simula una copia ligera y se transfiere a la malla completa.
  - Deduplicación: la misma malla con el mismo cuerpo, tipo y ajuste reutiliza el GLB (`X-Garment-Cached: true`). Un lock por clave evita simular dos veces en paralelo.
  - Ediciones de patrón: factores entre 70 % y 140 % por pieza (`{"front": {"width": 1.1}}`).
- **Salida:** GLB + `pipeline_info` (métricas y avisos) en un header HTTP.
- **[Pendiente]**
  - Foto → malla (InstantMesh/Garment3DGen o una alternativa) como job en el nodo GPU de visión.
  - Ejecución asíncrona.
  - Selección de material de tela.
  - Patrones para pantalón.
  - Exportar patrones (SVG/DXF).
  - Mover `pipeline_info` del header al cuerpo de la respuesta, porque los headers tienen límite de tamaño.

### 3.5 Clóset virtual
- **[Implementado – `frontend`]** 5 categorías (`Tops`, `Bottoms`, `Accessories`, `Shoes`, `Hats`), cuadrícula por categoría, carrusel, selección de una prenda por slot (`shirt`, `pants`, `accessory`, `shoes`, `hat`).
- **[Implementado – `NoMas_3D_ObjectLeo`]** Cuarto 3D con 3 barras × 14 ganchos; subida de `.glb`/`.obj`; nombre editable; corte `tshirt` o `longSleeve` (detectado por el nombre del archivo `/larga|long/i`); búsqueda; borrado; vista de detalle con rotación.
- **[Implementado – `NoMas_3D_Object`]** Biblioteca por cuerpo (`GET /wardrobe/{avatar_id}`) y "vestir" arrastrando la prenda al visor.
- **[Pendiente]** Un modelo único de prenda (sección 4.4) que una las tres versiones, persistencia y categorías alineadas con `garment_type`.

### 3.6 Probador / visor 3D
- **[Implementado – `frontend`]** Maniquí procedural, control de órbita, subtono del escenario (Warm/Cool/Neutral cambia el degradado de fondo), slots del outfit y descarga de paleta PNG (1000×340).
- **[Implementado – `NoMas_3D_Object`]** Avatar GLB real + varias prendas a la vez (camiseta + pantalón), caché LRU de 32 MB y liberación de recursos de GPU al quitar una prenda.
- **[Pendiente]** Unificar en el `frontend` con el visor de `NoMas_3D_Object`.

### 3.7 Outfits favoritos
- **[Implementado – frontend, en memoria]** Firma del outfit = ids de prendas unidos por `|`. Guardar o quitar alterna. Máximo 6 (`.slice(0, 6)`). Nombre automático `Look N`. Permite aplicar y eliminar.
- **[Pendiente]** Persistir, nombre editable, referencia a prendas reales y miniatura del render.

### 3.8 Cuestionario de preferencias ⬜
Propuesta: preguntas versionadas (`questionnaire_version`), respuestas por usuario, que alimentan el job `outfit` (`preferences`). Las preguntas concretas están `[POR DEFINIR]` con producto.

### 3.9 Social: amigos y lobby ⬜
- **Amigos:** estados `pending → accepted | rejected | blocked`.
- **Lobby:** sala con anfitrión, invitados (amigos) y outfits propuestos sincronizados en tiempo real (WebSocket desde el nodo central). `[POR DEFINIR]` si cada participante ve el avatar de los demás (implica privacidad de datos corporales).

### 3.10 Marketplace, favoritos de terceros y tienda ⬜
- **Publicación:** prenda propia → anuncio (`draft → published → reserved → sold | withdrawn`).
- **Favoritos:** de prendas de otros usuarios o de productos de tienda.
- `[POR DEFINIR]`: pagos, envíos, moderación, y si una prenda ajena se puede "probar" en mi avatar (requiere re-simular su malla sobre mi cuerpo, con coste de GPU/CPU).

### 3.11 Recomendaciones ⬜
- **Entrada propuesta:** colorimetría + cuestionario + clóset (+ ocasión o clima `[POR DEFINIR]`).
- **Salida:** lista de outfits con justificación. La API ya define `OutfitJobRequest {profile_id, wardrobe_item_ids, preferences}`.
- `Worker-outfits` contiene un clasificador DINOv2 / Fashion-MNIST que podría servir para auto-etiquetar prendas.

---

## 4. Especificación técnica

### 4.1 Nodos: arquitectura de referencia frente al código actual

| Nodo | Responsabilidad objetivo | Código actual | Brecha |
|---|---|---|---|
| **Central / API Gateway** | API, cola, estáticos, MySQL | `backend/` (FastAPI + Redis + `/storage`) | Le faltan BD, autenticación, y servir los GLB del clóset. Hoy los GLB viven en `backend-sam3d/storage/wardrobe/` de otra máquina. |
| **Cliente** | Web + render 3D | `frontend/` (y otros dos frontends en las ramas 3D) | Tres frontends que hay que fusionar |
| **GPU visión** | Segmentación, avatar, prendas, colorimetría | `backend-sam3d/server.py` como **servidor HTTP propio**, no como worker | Hay que convertirlo en worker de la cola `avatar_jobs` / `garment_3d_jobs`. Blender (CPU) va en el mismo proceso. |
| **GPU lenguaje** | Estilo y combinaciones | `workers/outfits/worker.py` stub | Sin modelo |

**Decisión recomendada:** mantener el patrón del monorepo (worker + Redis + resultado vía `/api/internal/...`) y **reempaquetar** `backend-sam3d` como `workers/avatar` + `workers/garments`, conservando sus servicios. El worker **no** debería exponer HTTP público. Además:
- Los archivos viajan como rutas relativas al storage central, tal como pide `docs/architecture.md`.
- `[POR DEFINIR]`: almacenamiento compartido entre nodos. Las opciones son subir/descargar por HTTP al nodo central (recomendado al principio) o un recurso compartido SMB/NFS sobre Tailscale.

### 4.2 Pipelines 3D y oportunidades de optimización

**Pipeline del avatar (actual):**
```text
foto → SAM 3D Body (GPU) → orientar + keypoints → tono de piel → u2net silueta → factores → sculpt → GLB
```

**Pipeline de la prenda (actual):**
```text
[externo: foto → InstantMesh → Garment3DGen → malla]
→ read_garment_scene → densify → ajuste por tipo (torso/mangas/piernas/zapatos/rig)
→ (camisas) segmentar → aplanar → coser en Blender → fallback ajuste directo
→ Blender simulate (18–24 frames, quality 4–5 / coser quality 10) → resolver penetraciones (voxel) → GLB → biblioteca
```

**Cuellos de botella observados en el código:**
1. **Ejecución síncrona dentro de la petición HTTP.** `/generate-garment` espera a Blender (1–7 min, sin timeout: `timeout_seconds=None`). → Pasarlo a un job asíncrono con estados y progreso.
2. **Arranque de Blender por cada prenda** (`subprocess.run`), con su coste de inicio e importación. → Un pool de Blender persistente o `bpy` como módulo `[POR DEFINIR / VERIFICAR viabilidad con Blender 4.2]`.
3. **"Coser primero y, si falla, ajuste directo"** duplica el tiempo en prendas que no se dejan coser (`camisa_manga_corta_2`: 7 min). → Usar las señales de `patterns/validation.py` / `analyzer` para predecir si la costura va a fallar y saltarla.
4. **Mallas densas.** Ya existe la copia ligera a partir de 9 000 vértices (de 95 min a 1 min). → Decimar al ingresar la prenda y guardar una *proxy* de simulación reutilizable para cualquier cuerpo.
5. **Re-simular por cuerpo.** La caché depende de `body_fingerprint`, así que cada avatar nuevo vuelve a simular toda su ropa. → Separar un "pre-procesado independiente del cuerpo" (segmentación, patrones, proxy), que se cachea una vez por prenda, del "ajuste al cuerpo".
6. **Estado en memoria** (`_avatar_cache` de 3 avatares): impide escalar o reiniciar. → Persistir el cuerpo base y los landmarks (`.npz` en storage + fila en BD).
7. **Foto → malla inexistente.** Es el mayor hueco funcional. Hay que evaluar el coste de InstantMesh + Garment3DGen en el nodo GPU `[POR DEFINIR / VERIFICAR tiempos y VRAM]`.
8. **Cuerpos voluminosos:** `FACTOR_RANGES` limita (p. ej. `waist ≤ 1.35`), lo que puede quedarse corto con cuerpos grandes. → Revisar los rangos con fotos de prueba y añadir pruebas de regresión con siluetas grandes. Las holguras (`TORSO_EASE` y similares) son relativas, así que conviene validar la proporción en tallas grandes.

### 4.3 Propuesta de API unificada (nodo central, prefijo `/api/v1`)

Extiende la API actual de `backend/app/api/`. ✅ = ya existe (con otro prefijo).

```text
# Autenticación / cuenta
POST   /auth/register            POST /auth/login           POST /auth/logout      GET /me

# Perfil y colorimetría
GET    /profiles/me              PATCH /profiles/me
POST   /profiles/me/colorimetry  (multipart image)  → síncrono, persiste   ✅ (hoy /api/colorimetry)
GET    /profiles/me/colorimetry

# Avatar
POST   /avatars                  (multipart image) → 202 {job_id}          🟡 (hoy /api/avatar/jobs)
GET    /avatars/me               → {avatar_id, glb_url, shape, status}
PATCH  /avatars/{id}/shape       {factors} → 202 {job_id}                  (hoy /adjust-avatar)

# Prendas / clóset
POST   /garments                 (multipart image[] | mesh, metadata) → 202 {job_id}
GET    /garments?category=&q=    PATCH /garments/{id}    DELETE /garments/{id}
POST   /garments/{id}/fits       {avatar_id, fit, edits} → 202 {job_id}    (hoy /generate-garment)
GET    /garments/{id}/fits/{fit_id}  → {glb_url, pipeline_info}
GET    /garments/{id}/patterns                                               (hoy /garment-patterns)

# Outfits
POST   /outfits   GET /outfits   PATCH /outfits/{id}   DELETE /outfits/{id}

# Cuestionario
GET    /questionnaire            PUT /questionnaire/answers

# Recomendaciones
POST   /recommendations          → 202 {job_id}                             🟡 (hoy /api/outfits/jobs)

# Jobs (común)
GET    /jobs/{job_id}   ✅      GET /jobs/{job_id}/events (SSE, progreso)
POST   /internal/jobs/{job_id}/result  ✅   POST /internal/jobs/{job_id}/progress
POST   /internal/assets          (worker sube GLB/NPZ al storage central)

# Social / marketplace (fases posteriores)
/friends, /lobbies (+ WS /lobbies/{id}/ws), /listings, /favorites, /store/products
```

**Reglas transversales:**
- Toda operación con GPU o Blender es **asíncrona** (202 + `job_id`).
- Los assets se sirven desde `/storage/...` del nodo central con URL relativa.
- Errores con forma `{detail, code}`.
- Los workers solo hablan con la API interna (no escriben en Redis directamente) y usan un token obligatorio.

### 4.4 Estructuras JSON propuestas

**Job (extiende `shared/contracts/job.schema.json`):**
```json
{
  "job_id": "uuid",
  "kind": "avatar | garment_3d | garment_fit | outfit",
  "status": "queued | running | completed | failed",
  "progress": { "stage": "simulating", "percent": 40 },
  "input":  { "profile_id": "…", "asset_refs": ["uploads/<job_id>.jpg"] },
  "result": { "asset_refs": ["avatars/<id>/avatar.glb"], "metrics": {} },
  "error":  null,
  "created_at": "ISO-8601", "updated_at": "ISO-8601"
}
```

**Prenda (une las tres versiones actuales):**
```json
{
  "id": "uuid", "owner_id": "uuid", "name": "Camisa azul",
  "category": "Tops", "garment_type": "tshirt", "cut": "tshirt",
  "color_hex": "#36546d", "shade": "Ink blue",
  "source": { "photos": ["garments/<id>/photo_0.jpg"], "mesh": "garments/<id>/source.glb", "mesh_sha256": "…" },
  "fits": [{ "avatar_id": "…", "fit": "regular", "glb": "fits/<body>/<id>.glb", "cached": true }],
  "status": "processing | ready | failed"
}
```

**Avatar:**
```json
{ "id": "…", "glb": "avatars/<id>/avatar.glb", "base": "avatars/<id>/base.npz",
  "shape": { "chest": 1.0, "waist": 1.0, "hips": 1.0, "arms": 1.0, "legs": 1.0, "bust": 1.0 },
  "shape_source": "foto | manual | sin-segmentacion | error", "fingerprint": "v2-skeleton:…" }
```

**Organización del storage central:**
```text
storage/
  uploads/          originales (fotos)
  avatars/<id>/     avatar.glb, base.npz (vértices, caras, landmarks, tono)
  garments/<id>/    fotos, source.glb, proxy.glb, patterns.json
  fits/<body_fp>/   <garment_id>_<fit>.glb, pipeline_info.json
```

### 4.5 Base de datos MySQL: enfoque iterativo

> Aquí **no** va el esquema completo. Es un punto de partida para construir la base de datos juntos.

**Entidades candidatas detectadas** (a partir del código y del flujo):
`user`, `profile`, `colorimetry_result`, `avatar`, `garment`, `garment_asset`, `garment_fit`, `outfit`, `outfit_item`, `job`, `questionnaire` / `questionnaire_answer`, `friendship`, `lobby` / `lobby_member`, `listing`, `favorite`, `store_product`.

**Núcleo mínimo propuesto (iteración 1):** solo lo necesario para dejar de perder datos al recargar o reiniciar.

| Entidad | Campos clave (orientativos) | Motivo |
|---|---|---|
| `user` | id, email (único), password_hash, created_at | Sustituye a `localStorage` |
| `profile` | user_id (1:1), display_name, theme, colorimetría actual (season, undertone, contrast, métricas) | Se puede separar en `colorimetry_result` en la iteración 2 si se quiere historial |
| `avatar` | id, user_id, glb_path, base_path, shape (JSON), fingerprint, status | Resuelve la pérdida del `avatar_id` al reiniciar |
| `garment` | id, user_id, name, category, garment_type, color_hex, source_mesh_path, mesh_sha256, status | Une las tres versiones del clóset |

`job` puede seguir en Redis durante la iteración 1 (el estado es efímero) y pasar a una tabla después si se necesita auditoría.

**Preguntas para revisar contigo antes de escribir el DDL:**
1. ¿Un usuario puede tener **varios avatares** (historial o distintas fotos) o solo uno activo?
2. ¿`garment_fit` (prenda × avatar × ajuste) va en tabla propia o basta con la caché en disco por huella?
3. ¿Los JSON (`shape`, `pipeline_info`, `preferences`) van en columnas `JSON` de MySQL o se normalizan?
4. ¿Las prendas del marketplace o de la tienda comparten la tabla `garment` (con `owner_type`) o van en una tabla separada?
5. ¿Borrado lógico (`deleted_at`) o físico? Afecta a los outfits que referencian prendas borradas.
6. ¿IDs `CHAR(36)` UUID, `BINARY(16)` o autoincrementales + UUID público?
7. ¿Las fotos de cuerpo y rostro se conservan tras procesarlas? Son datos biométricos sensibles: hay que definir retención y consentimiento.
8. ¿Qué ORM o herramienta de migraciones usamos (SQLAlchemy + Alembic, recomendado con FastAPI)? `[POR DEFINIR]`

---

## 5. Brechas, riesgos y roadmap de integración

### 5.1 Brechas que faltan conectar
1. Hay dos estructuras de repositorio (monorepo frente a raíz plana) y tres frontends.
2. `backend-sam3d` es un servidor HTTP con estado en memoria; la arquitectura espera un worker de cola.
3. No hay storage compartido entre el nodo central y los nodos GPU (los GLB del clóset viven en el nodo GPU).
4. El frontend principal no usa avatares GLB, prendas reales, jobs (`getJob` sin usar) ni el clóset 3D.
5. No hay foto → malla de prenda.
6. No hay BD, autenticación ni persistencia de colorimetría, looks o medidas.
7. El contrato `job.schema.json` está desalineado con `schemas/jobs.py` (`garment_3d`).

### 5.2 Riesgos técnicos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Simulaciones de varios minutos dentro de HTTP | Timeouts y UI bloqueada | Jobs asíncronos + SSE de progreso |
| GPU (SAM 3D, ~VRAM `[POR VERIFICAR]`) y Blender en la misma máquina | Contención | Separar worker de avatar (GPU) y de simulación (CPU) |
| Estado en memoria (3 avatares) | Pérdida de datos y no escala | Persistir base + landmarks |
| Divergencia entre `NoMas_3D_Object` y `NoMas_3D_ObjectLeo` en `garment_pipeline.py` y otros | Conflictos de merge | Tomar `NoMas_3D_Object` como fuente del backend 3D y traer **solo** `src/features/closet/room/` de Leo |
| Datos biométricos (rostro y cuerpo) | Legal y privacidad | Consentimiento, retención, cifrado en reposo `[POR DEFINIR]` |
| Dependencias no versionadas (`sam-3d-body`, `u2net_human_seg.onnx`, Blender 4.2, pesos de Hugging Face) | Entorno irreproducible | Documentar versiones y añadir script de instalación |
| Artefactos versionados (`__pycache__`, `blender.crash.txt`, `graphify-out/`) | Ruido en el repositorio | `.gitignore` |
| Rutas y comandos de Windows/PowerShell en las ramas 3D, frente a un entorno mixto | Despliegue | Configuración solo por variables de entorno |
| Los 422 de colorimetría llegan al cliente como 400 | Mensajes de error incorrectos | Relanzar `HTTPException` antes del `except Exception` |

### 5.3 Roadmap recomendado (orden de implementación)

1. **Higiene y fuente única** (bajo riesgo):
   - Subir el commit local de `backend`.
   - Hacer merge de `frontend` (`6c0129b`) en `backend` o viceversa.
   - Limpiar los artefactos versionados de las ramas 3D.
   - Alinear `job.schema.json`.
2. **Integrar el backend 3D en el monorepo:**
   - Mover `backend-sam3d/services/` de `NoMas_3D_Object` a `workers/avatar/` (y `workers/garments/`).
   - Envolverlos en el bucle de cola existente (`worker.py`), sustituyendo el stub.
   - El worker sube resultados al storage central y notifica vía `/api/internal/...`.
3. **Endpoints asíncronos en el nodo central:**
   - `/avatars`, `/garments/{id}/fits` y `/jobs/{id}/events`, con progreso.
   - Timeout en Blender y *visibility timeout* en Redis.
4. **BD MySQL, iteración 1** (núcleo de la sección 4.5) + autenticación básica, iterando sobre las preguntas pendientes.
5. **Unificar el frontend:**
   - Portar el visor GLB de `NoMas_3D_Object` y el cuarto 3D de `NoMas_3D_ObjectLeo` a `frontend/src/features/`.
   - Conectar el onboarding (cuerpo y prenda) a los jobs.
   - Persistir looks y colorimetría.
6. **Optimizar el pipeline de prendas:**
   - Pre-procesado de la prenda independiente del cuerpo (proxy + patrones), cacheado una vez.
   - Predicción de "costura viable" para evitar el fallback doble.
   - Pool de Blender.
   - Tallas grandes: revisar `FACTOR_RANGES` y las holguras.
7. **Foto → malla de prenda** en el nodo GPU de visión (InstantMesh/Garment3DGen u otra opción, tras evaluar tiempo y VRAM).
8. **Cuestionario + recomendaciones** (nodo de lenguaje; reutilizar el clasificador de `Worker-outfits` para etiquetar).
9. **Social** (amigos → lobby con WebSocket).
10. **Marketplace / favoritos / tienda.**

---

### Anexo: comandos usados en la auditoría (reproducibles)

```bash
git fetch origin
git log --oneline -12 origin/<rama>
git ls-tree -r --name-only origin/<rama>
git show origin/<rama>:<ruta>
git archive origin/<rama> | tar -x -C <dir_temporal>
```
