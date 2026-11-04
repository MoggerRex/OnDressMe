const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export async function getJob(jobId) {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${encodeURIComponent(jobId)}`);
  if (!response.ok) {
    throw new Error(`Unable to retrieve job ${jobId}: ${response.status}`);
  }
  return response.json();
}

export { API_BASE_URL };
