import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_URL || "";

const api = axios.create({ baseURL: BASE_URL });

// ── Interceptor: adiciona token e trata expiração ─────────────────────────────
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      const refreshToken = localStorage.getItem("refresh_token");
      if (refreshToken) {
        try {
          const { data } = await axios.post(`${BASE_URL}/auth/refresh`, {
            refresh_token: refreshToken,
          });
          localStorage.setItem("token", data.access_token);
          if (data.refresh_token) {
            localStorage.setItem("refresh_token", data.refresh_token);
          }
          original.headers.Authorization = `Bearer ${data.access_token}`;
          return api(original);
        } catch {
          // refresh falhou — força logout
          localStorage.removeItem("token");
          localStorage.removeItem("refresh_token");
          if (window.location.pathname !== "/login") {
            window.location.href = "/login";
          }
        }
      }
    }
    return Promise.reject(error);
  }
);

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function login(email, senha) {
  const { data } = await api.post("/auth/login", { email, senha });
  localStorage.setItem("token", data.access_token);
  localStorage.setItem("refresh_token", data.refresh_token);
  return data;
}

export async function registrar(nome, email, senha) {
  const { data } = await api.post("/auth/registrar", { nome, email, senha });
  return data;
}

export async function logout() {
  const refreshToken = localStorage.getItem("refresh_token");
  try {
    if (refreshToken) {
      await api.post("/auth/logout", { refresh_token: refreshToken });
    }
  } finally {
    localStorage.removeItem("token");
    localStorage.removeItem("refresh_token");
  }
}

export async function getMe() {
  const { data } = await api.get("/auth/me");
  return data;
}

// ── Credenciais ───────────────────────────────────────────────────────────────

export async function getCredenciais() {
  const { data } = await api.get("/credenciais/");
  return data;
}

export async function criarCredencial(payload) {
  const { data } = await api.post("/credenciais/", payload);
  return data;
}

export async function atualizarCredencial(id, payload) {
  const { data } = await api.put(`/credenciais/${id}`, payload);
  return data;
}

export async function deletarCredencial(id) {
  await api.delete(`/credenciais/${id}`);
}

// ── Lotes ─────────────────────────────────────────────────────────────────────

export async function uploadLote(arquivo, banco, credencialId = null) {
  const form = new FormData();
  form.append("arquivo", arquivo);
  let url = `/upload-lote/?banco=${banco}`;
  if (credencialId) url += `&credencial_id=${credencialId}`;
  const { data } = await api.post(url, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function getStatusLote(loteId, skip = 0, limit = 200) {
  const { data } = await api.get(`/status-lote/${loteId}?skip=${skip}&limit=${limit}`);
  return data;
}

export async function getLotes(skip = 0, limit = 20) {
  const { data } = await api.get(`/lotes/?skip=${skip}&limit=${limit}`);
  return data;
}

export async function exportarLote(loteId, formato = "csv") {
  const response = await api.get(`/lotes/${loteId}/exportar?formato=${formato}`, {
    responseType: "blob",
  });
  const ext = formato === "xlsx" ? "xlsx" : "csv";
  const url = URL.createObjectURL(response.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = `lote_${loteId}_resultados.${ext}`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export async function getDashboard() {
  const { data } = await api.get("/dashboard/");
  return data;
}

// ── Catálogo ──────────────────────────────────────────────────────────────────

export async function getCatalogo() {
  const { data } = await api.get("/catalogo/bancos");
  return data;
}

// ── Adaptadores ───────────────────────────────────────────────────────────────

export async function getAdaptadores() {
  const { data } = await api.get("/adaptadores/");
  return data.adaptadores;
}

export default api;
