import { useState, useEffect } from "react";
import { Toaster } from "react-hot-toast";
import Login from "./components/Login";
import Sidebar from "./components/Sidebar";
import Dashboard from "./components/Dashboard";
import UploadLote from "./components/UploadLote";
import StatusLote from "./components/StatusLote";
import HistoricoLotes from "./components/HistoricoLotes";
import Credenciais from "./components/Credenciais";
import Catalogo from "./components/Catalogo";
import Admin from "./components/Admin";
import Perfil from "./components/Perfil";
import { logout, getMe } from "./api";

export default function App() {
  const [token, setToken]         = useState(() => localStorage.getItem("token"));
  const [loteAtivo, setLoteAtivo] = useState(null);
  const [usuario, setUsuario]     = useState(null);
  const [abaAtiva, setAbaAtiva]   = useState("dashboard");

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
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      <Toaster position="top-right" />

      <Sidebar
        abaAtiva={abaAtiva}
        onChangeAba={setAbaAtiva}
        usuario={usuario}
        onLogout={handleLogout}
      />

      <main className="flex-1 overflow-y-auto p-6">
        {abaAtiva === "dashboard" && (
          <Dashboard onIrParaLotes={() => setAbaAtiva("consultas")} />
        )}

        {abaAtiva === "consultas" && (
          <div className="space-y-4">
            <div>
              <h1 className="text-2xl font-bold text-slate-800">Higienização</h1>
              <p className="text-slate-500 text-sm mt-1">Upload e acompanhamento de lotes em processamento</p>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="space-y-5">
                <UploadLote onLoteIniciado={(id) => setLoteAtivo(id)} />
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
          </div>
        )}

        {abaAtiva === "credenciais" && <Credenciais />}

        {abaAtiva === "catalogo" && (
          <Catalogo onAdicionarCredencial={() => setAbaAtiva("credenciais")} />
        )}

        {abaAtiva === "perfil" && <Perfil />}

        {abaAtiva === "admin" && usuario?.is_admin === true && <Admin />}
      </main>
    </div>
  );
}
