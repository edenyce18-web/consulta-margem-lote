import { useState, useEffect } from "react";
import { Toaster } from "react-hot-toast";
import Login from "./components/Login";
import UploadLote from "./components/UploadLote";
import StatusLote from "./components/StatusLote";
import HistoricoLotes from "./components/HistoricoLotes";
import Credenciais from "./components/Credenciais";
import Dashboard from "./components/Dashboard";
import { logout, getMe } from "./api";

const TABS = [
  { id: "dashboard", label: "Dashboard", icon: "M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" },
  { id: "lotes",     label: "Consultas",  icon: "M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" },
  { id: "credenciais", label: "Credenciais", icon: "M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" },
];

export default function App() {
  const [token, setToken]           = useState(() => localStorage.getItem("token"));
  const [loteAtivo, setLoteAtivo]   = useState(null);
  const [usuario, setUsuario]       = useState(null);
  const [abaAtiva, setAbaAtiva]     = useState("dashboard");

  useEffect(() => {
    if (!token) return;
    getMe()
      .then(setUsuario)
      .catch(() => handleLogout());
  }, [token]);

  async function handleLogout() {
    await logout();
    setToken(null);
    setUsuario(null);
    setLoteAtivo(null);
  }

  if (!token) {
    return (
      <>
        <Toaster position="top-right" />
        <Login onLogin={(t) => setToken(t)} />
      </>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <Toaster position="top-right" />

      {/* Header */}
      <header className="bg-white border-b border-slate-200 shadow-sm sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-blue-600 p-2 rounded-xl">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-bold text-slate-800 leading-none">ConsultaMargem</h1>
              <p className="text-xs text-slate-400">Multi-usuário · AkiCapital · GridSoftware</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {usuario && (
              <span className="text-sm text-slate-500 hidden md:block">{usuario.nome}</span>
            )}
            <button
              onClick={handleLogout}
              className="text-xs text-slate-500 hover:text-red-600 border border-slate-200 hover:border-red-200 px-3 py-1.5 rounded-lg transition-colors"
            >
              Sair
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="max-w-7xl mx-auto px-4">
          <nav className="flex gap-1">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setAbaAtiva(tab.id)}
                className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                  abaAtiva === tab.id
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={tab.icon} />
                </svg>
                {tab.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-7xl mx-auto px-4 py-6">

        {/* Dashboard */}
        {abaAtiva === "dashboard" && (
          <Dashboard onIrParaLotes={() => setAbaAtiva("lotes")} />
        )}

        {/* Consultas / Lotes */}
        {abaAtiva === "lotes" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="space-y-5">
              <UploadLote onLoteIniciado={(id) => { setLoteAtivo(id); }} />
              <HistoricoLotes onSelecionar={setLoteAtivo} loteAtivo={loteAtivo} />
            </div>
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
        )}

        {/* Credenciais */}
        {abaAtiva === "credenciais" && <Credenciais />}

      </main>
    </div>
  );
}
