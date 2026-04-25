import { useState } from "react";
import { login, registrar } from "../api";

export default function Login({ onLogin }) {
  const [modo, setModo] = useState("login"); // "login" | "registrar"
  const [form, setForm] = useState({ nome: "", email: "", senha: "" });
  const [erro, setErro] = useState(null);
  const [carregando, setCarregando] = useState(false);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErro(null);
    setCarregando(true);
    try {
      if (modo === "login") {
        const resp = await login(form.email, form.senha);
        localStorage.setItem("token", resp.access_token);
        onLogin(resp.access_token);
      } else {
        await registrar(form.nome, form.email, form.senha);
        // Após registro faz login automático
        const resp = await login(form.email, form.senha);
        localStorage.setItem("token", resp.access_token);
        onLogin(resp.access_token);
      }
    } catch (err) {
      setErro(err.response?.data?.detail || "Erro de autenticação.");
    } finally {
      setCarregando(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-blue-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-600 rounded-2xl shadow-lg mb-4">
            <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-white">ConsultaMargem</h1>
          <p className="text-slate-400 text-sm mt-1">Sistema de Consulta em Lote</p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-xl p-8">
          {/* Tabs */}
          <div className="flex mb-6 bg-slate-100 rounded-xl p-1">
            <button
              onClick={() => { setModo("login"); setErro(null); }}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all ${
                modo === "login"
                  ? "bg-white shadow text-slate-800"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              Entrar
            </button>
            <button
              onClick={() => { setModo("registrar"); setErro(null); }}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all ${
                modo === "registrar"
                  ? "bg-white shadow text-slate-800"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              Criar Conta
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {modo === "registrar" && (
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Nome</label>
                <input
                  type="text"
                  value={form.nome}
                  onChange={set("nome")}
                  required
                  placeholder="Seu nome completo"
                  className="w-full border border-slate-300 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">E-mail</label>
              <input
                type="email"
                value={form.email}
                onChange={set("email")}
                required
                placeholder="seu@email.com"
                className="w-full border border-slate-300 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Senha</label>
              <input
                type="password"
                value={form.senha}
                onChange={set("senha")}
                required
                placeholder="••••••••"
                className="w-full border border-slate-300 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {erro && (
              <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">
                {erro}
              </div>
            )}

            <button
              type="submit"
              disabled={carregando}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white font-semibold py-2.5 rounded-xl transition-colors text-sm"
            >
              {carregando
                ? "Aguarde..."
                : modo === "login" ? "Entrar" : "Criar Conta"}
            </button>
          </form>
        </div>

        <p className="text-center text-slate-500 text-xs mt-6">
          AkiCapital · GridSoftware / Roraima
        </p>
      </div>
    </div>
  );
}
