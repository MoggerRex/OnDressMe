const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

async function requestGlb(endpoint, formData) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: 'POST',
      body: formData,
    });
  } catch {
    throw new Error(
      'No se pudo conectar con FastAPI. Verifica que el backend esté ejecutándose en el puerto 8000.',
    );
  }

  if (!response.ok) {
    let detail = `La solicitud falló (HTTP ${response.status}).`;
    try {
      const payload = await response.json();
      if (typeof payload.detail === 'string') detail = payload.detail;
    } catch {
      // Keep the HTTP status when the server does not return JSON.
    }
    throw new Error(detail);
  }

  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('model/gltf-binary')) {
    throw new Error('El backend no devolvió un archivo GLB.');
  }

  const blob = await response.blob();
  const magic = new TextDecoder().decode(await blob.slice(0, 4).arrayBuffer());
  if (magic !== 'glTF') {
    throw new Error('La respuesta no contiene un GLB válido.');
  }
  return blob;
}

export async function generateAvatar(imageFile) {
  const formData = new FormData();
  formData.append('image', imageFile);
  return requestGlb('/generate-3d', formData);
}
