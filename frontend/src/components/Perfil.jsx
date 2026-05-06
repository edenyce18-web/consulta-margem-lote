import { useState, useEffect } from "react";
import { getPerfil } from "../api";
import { User } from "lucide-react";

export default function Perfil() {
  const [perfil, setPerfil] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPerfil()
      .then(setPerfil)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="max-w-lg mx-auto space-y-4">
        <div className="bg-white rounded-2xl border border-slate-200 p-6 animate-pulse h-40" />
      </div>
    );
  }

  if (!perfil) return null;

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Meu Perfil</h1>
        <p className="text-slate-500 text-sm mt-1">Informações da sua conta</p>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
        <div className="flex items-center gap-4 mb-6">
          <div className="bg-blue-600 rounded-full p-3">
            <User size={28} className="text-white" />
          </div>
          <div>
            <p className="text-lg font-bold text-slate-800">{perfil.nome}</p>
            <p className="text-slate-500 text-sm">{perfil.email}</p>
          </div>
        </div>

        <div className="space-y-3 text-sm">
          <div className="flex justify-between py-2 border-b border-slate-100">
            <span className="text-slate-500">Membro desde</span>
            <span className="font-medium text-slate-700">
              {new Date(perfil.criado_em).toLocaleDateString("pt-BR", {
                day: "2-digit", month: "long", year: "numeric"
              })}
            </span>
          </div>
          <div className="flex justify-between py-2 border-b border-slate-100">
            <span className="text-slate-500">Status</span>
            <span className={`font-semibold ${perfil.ativo ? "text-green-600" : "text-red-500"}`}>
              {perfil.ativo ? "Ativa" : "Inativa"}
            </span>
          </div>
          {perfil.is_admin && (
            <div className="flex justify-between py-2">
              <span className="text-slate-500">Perfil</span>
              <span className="inline-block px-2 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-700">
                Administrador
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
