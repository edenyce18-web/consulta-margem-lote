import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_URL || "";

const api = axios.create({ baseURL: BASE_URL });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export async function uploadLote(arquivo, banco = "exemplo") {
  const form = new FormData();
  form.append("arquivo", arquivo);
  const { data } = await api.post(`/upload-lote/?banco=${banco}`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function getStatusLote(loteId, skip = 0, limit = 200) {
  const { data } = await api.get(
    `/status-lote/${loteId}?skip=${skip}&limit=${limit}`
  );
  return data;
}

export async function getLotes(skip = 0, limit = 20) {
  const { data } = await api.get(`/lotes/?skip=${skip}&limit=${limit}`);
  return data;
}

export async function login(email, senha) {
  const { data } = await api.post("/auth/login", { email, senha });
  localStorage.setItem("token", data.access_token);
  return data;
}

export async function registrar(nome, email, senha) {
  const { data } = await api.post("/auth/registrar", { nome, email, senha });
  return data;
}

export function logout() {
  localStorage.removeItem("token");
}

export default api;
