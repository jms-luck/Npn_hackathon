const API_URL = import.meta.env.VITE_API_URL || "/api";

async function request(path, options = {}) {
  const token = localStorage.getItem("access_token");
  const isForm = options.body instanceof FormData;
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed (${response.status})`);
  }
  return response;
}

export async function api(path, options = {}) {
  const response = await request(path, options);
  return response.status === 204 ? null : response.json();
}

export async function apiBlob(path, options = {}) {
  return (await request(path, options)).blob();
}

export async function apiResponse(path, options = {}) {
  return request(path, options);
}