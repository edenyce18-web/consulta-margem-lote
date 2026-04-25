import { useState, useEffect } from "react";
import Login from "./components/Login";
import UploadLote from "./components/UploadLote";
import StatusLote from "./components/StatusLote";
import HistoricoLotes from "./components/HistoricoLotes";
import { logout } from "./api";

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem("token"));
  const [loteAtivo, setLoteAtivo] = useState(null);
  const [usuario, setUsuario] = useState(null);

  // Busca dados do usuário após login
  useEffect(() => {
    if (!token) return;
    fetch("/auth/me", { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => {
        if (!r.ok) { handleLogout(); return null; }
        return r.json();
      })
      .then((u) => u && setUsuario(u))
      .catch(handleLogout);
  }, [token]);

  function handleLogin(t) {
    setToken(t);
  }

  function handleLogout() {
    logout();
    setToken(null);
    setUsuario(null);
    setLoteAtivo(null);
  }

  if (!token) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-100 to-blue-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 shadow-sm sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-blue-600 p-2 rounded-xl">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-bold text-slate-800">ConsultaMargem</h1>
              <p className="text-xs text-slate-500">Consulta em lote · AkiCapital e GridSoftware</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {usuario && (
              <span className="text-sm text-slate-600 hidden md:block">
                {usuario.nome}
              </span>
            )}
            <button
              onClick={handleLogout}
              className="text-xs text-slate-500 hover:text-red-600 border border-slate-200 hover:border-red-200 px-3 py-1.5 rounded-lg transition-colors"
            >
              Sair
            </button>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Coluna esquerda */}
          <div className="space-y-5">
            <UploadLote onLoteIniciado={setLoteAtivo} />
            <HistoricoLotes onSelecionar={setLoteAtivo} loteAtivo={loteAtivo} />
          </div>

          {/* Coluna direita */}
          <div className="lg:col-span-2">
            {loteAtivo ? (
              <StatusLote loteId={loteAtivo} />
            ) : (
              <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-12 flex flex-col items-center justify-center text-center text-slate-400 min-h-80">
                <svg className="w-16 h-16 mb-4 text-slate-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                </svg>
                <p className="font-medium">Nenhum lote selecionado</p>
                <p className="text-sm mt-1">Faça upload de um CSV para iniciar</p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
