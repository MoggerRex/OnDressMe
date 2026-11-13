const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

async function responseError(response) {
  let detail = `La solicitud falló (HTTP ${response.status}).`;
  try {
    const payload = await response.json();
    if (typeof payload.detail === 'string') detail = payload.detail;
  } catch {
    // Keep the HTTP status when the server does not return JSON.
  }
  return new Error(detail);
}

async function requestGlb(endpoint, options) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, options);
  } catch {
    throw new Error(
      'No se pudo conectar con FastAPI. Verifica que el backend esté ejecutándose en el puerto 8000.',
    );
  }

  if (!response.ok) {
    throw await responseError(response);
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
  return { blob, response };
}

export async function generateAvatar(imageFile) {
  const formData = new FormData();
  formData.append('image', imageFile);
  const { blob, response } = await requestGlb('/generate-3d', {
    method: 'POST',
    body: formData,
  });
  return {
    blob,
    avatarId: response.headers.get('x-avatar-id'),
  };
}

export async function generateGarment(meshFile, avatarId, garmentType = 'tshirt') {
  if (!avatarId) {
    throw new Error('Genera de nuevo el maniquí para vincular la prenda.');
  }

  const formData = new FormData();
  formData.append('garment_mesh', meshFile);
  formData.append('avatar_id', avatarId);
  formData.append('garment_type', garmentType);
  const { blob, response } = await requestGlb('/generate-garment', {
    method: 'POST',
    body: formData,
  });
  const garmentId = response.headers.get('x-garment-id');
  if (!garmentId) {
    throw new Error('El backend no devolvió el identificador de la prenda guardada.');
  }
  return {
    blob,
    pipelineInfo: response.headers.get('x-pipeline-info'),
    garmentId,
    cached: response.headers.get('x-garment-cached') === 'true',
  };
}

export async function listWardrobe(avatarId) {
  let response;
  try {
    response = await fetch(
      `${API_BASE_URL}/wardrobe/${encodeURIComponent(avatarId)}`,
    );
  } catch {
    throw new Error(
      'No se pudo conectar con FastAPI para cargar la biblioteca de prendas.',
    );
  }
  if (!response.ok) throw await responseError(response);

  const payload = await response.json();
  if (!Array.isArray(payload.items)) {
    throw new Error('El backend devolvió una biblioteca de prendas inválida.');
  }
  return payload.items;
}

export async function getGarmentModel(avatarId, garmentId) {
  const endpoint = getGarmentModelUrl(avatarId, garmentId);
  try {
    const { blob } = await requestGlb(endpoint, { method: 'GET' });
    return blob;
  } catch (error) {
    if (error.message.startsWith('No se pudo conectar con FastAPI')) {
      throw new Error(
        'El GLB sigue guardado localmente, pero FastAPI debe estar activo para cargarlo en el navegador por primera vez.',
        { cause: error },
      );
    }
    throw error;
  }
}

export function getGarmentModelUrl(avatarId, garmentId) {
  return `${API_BASE_URL}/wardrobe/${encodeURIComponent(avatarId)}/${encodeURIComponent(garmentId)}/model`;
}
