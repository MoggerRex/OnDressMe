# Graph Report - OnDressMe  (2026-11-18)

## Corpus Check
- Corpus is ~20,802 words - fits in a single context window. You may not need a graph.

## Summary
- 341 nodes · 918 edges · 13 communities (8 shown, 5 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 14 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Ajuste de prendas (pipeline)
- Config y dependencias frontend
- Servidor SAM 3D
- Biblioteca de prendas
- Esqueleto del cuerpo
- App React
- Pruebas de zapatos
- Simulación Blender

## God Nodes (most connected - your core abstractions)
1. `load_garment_mesh()` - 43 edges
2. `GarmentPipelineError` - 22 edges
3. `_body_pants_profile()` - 20 edges
4. `simulate_static_garment()` - 19 edges
5. `process_or_reuse_garment()` - 18 edges
6. `GarmentLibraryError` - 17 edges
7. `read_garment_rig()` - 16 edges
8. `GarmentPipelineTests` - 16 edges
9. `fit_shoes()` - 15 edges
10. `body_fingerprint()` - 14 edges

## Surprising Connections (you probably didn't know these)
- `generate_garment()` --uses--> `GarmentLibraryError`  [INFERRED]
  backend-sam3d/server.py → backend-sam3d/services/garment_library.py
- `generate_garment()` --indirect_call--> `process_or_reuse_garment()`  [INFERRED]
  backend-sam3d/server.py → backend-sam3d/services/garment_library.py
- `generate_garment()` --uses--> `GarmentPipelineError`  [INFERRED]
  backend-sam3d/server.py → backend-sam3d/services/garment_pipeline.py
- `vertices_on_hands()` --calls--> `simulate_static_garment()`  [EXTRACTED]
  backend-sam3d/tests/test_skeleton_fit.py → backend-sam3d/services/blender_simulator.py
- `ShoeFitTests` --uses--> `GarmentPipelineError`  [INFERRED]
  backend-sam3d/tests/test_shoe_fit.py → backend-sam3d/services/garment_pipeline.py

## Import Cycles
- None detected.

## Communities (13 total, 5 thin omitted)

### Community 0 - "Ajuste de prendas (pipeline)"
Cohesion: 0.08
Nodes (39): _apply_anterior_waist_clamp(), _apply_posterior_waist_anchor(), _apply_waist_contour_clamp(), _bilateral_section_centers(), _body_pants_profile(), _body_radial_profile(), _body_section_centers(), _body_section_dimensions() (+31 more)

### Community 1 - "Config y dependencias frontend"
Cohesion: 0.06
Nodes (49): dependencies, framer-motion@^14.9.0, lucide-react@^1.66.0, react@^19.3.1, react-dom@^19.3.1, @react-three/drei@^10.7.9, @react-three/fiber@^9.8.2, three@^0.187.0 (+41 more)

### Community 2 - "Servidor SAM 3D"
Cohesion: 0.08
Nodes (11): estimate_skin_color(), generate_3d(), generate_garment(), orient_body_keypoints(), orient_body_vertices(), _remember_avatar(), _find_blender(), GarmentSimulationError (+3 more)

### Community 3 - "Biblioteca de prendas"
Cohesion: 0.14
Nodes (20): _cached_avatar(), get_wardrobe(), get_wardrobe_model(), _artifact_path(), _body_directory(), body_fingerprint(), find_cached_garment(), GarmentLibraryError (+12 more)

### Community 4 - "Esqueleto del cuerpo"
Cohesion: 0.11
Nodes (17): arm_vertex_mask(), body_without_arms(), has_arm_bones(), label_body_vertices(), _landmark_point(), _segment_distances(), without_arms(), arm_landmarks() (+9 more)

### Community 5 - "App React"
Cohesion: 0.11
Nodes (29): lucide-react, react, App(), handleDropGarment(), handleGenerateAvatar(), handleGenerateGarment(), handleToggleWear(), handleWearGarment() (+21 more)

### Community 6 - "Pruebas de zapatos"
Cohesion: 0.29
Nodes (8): fit(), landmarks(), make_body_with_feet(), make_shoe(), shoe_vertices(), ShoeFitTests, to_glb(), skinned_glb()

### Community 7 - "Simulación Blender"
Cohesion: 0.20
Nodes (11): add_collision(), add_top_edge_pins(), clear_garment_penetrations(), count_surface_intersections(), fit_body_surface_clearance(), fit_pants_surface_regions(), import_meshes(), main() (+3 more)

## Knowledge Gaps
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `load_garment_mesh()` connect `Ajuste de prendas (pipeline)` to `Servidor SAM 3D`, `Biblioteca de prendas`, `Esqueleto del cuerpo`, `Pruebas de zapatos`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `GarmentPipelineError` (e.g. with `generate_garment()` and `GarmentPipelineTests`) actually correct?**
  _`GarmentPipelineError` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Should `Ajuste de prendas (pipeline)` be split into smaller, more focused modules?**
  _Cohesion score 0.08037974683544304 - nodes in this community are weakly interconnected._
- **Why does `GarmentPipelineError` connect `Ajuste de prendas (pipeline)` to `Servidor SAM 3D`, `Pruebas de zapatos`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Should `Config y dependencias frontend` be split into smaller, more focused modules?**
  _Cohesion score 0.05656108597285068 - nodes in this community are weakly interconnected._
- **Why does `simulate_static_garment()` connect `Servidor SAM 3D` to `Ajuste de prendas (pipeline)`, `Biblioteca de prendas`, `Esqueleto del cuerpo`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Should `Servidor SAM 3D` be split into smaller, more focused modules?**
  _Cohesion score 0.07585568917668825 - nodes in this community are weakly interconnected._