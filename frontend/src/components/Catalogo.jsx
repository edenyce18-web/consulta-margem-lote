import { useEffect, useState } from "react";
import { Building2, Plus, CheckCircle, AlertCircle } from "lucide-react";
import { getCatalogo } from "../api";
import toast from "react-hot-toast";

export default function Catalogo({ onAdicionarCredencial }) {
  const [bancos, setBancos] = useState([]);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    getCatalogo()
      .then(setBancos)
      .catch(() => toast.error("Erro ao carregar catálogo"))
      .finally(() => setCarregando(false));
  }, []);

  if (carregando) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-2xl border border-slate-200 p-5 animate-pulse">
            <div className="h-4 bg-slate-200 rounded w-1/2 mb-3" />
            <div className="h-3 bg-slate-200 rounded w-3/4 mb-6" />
            <div className="h-10 bg-slate-100 rounded mb-3" />
            <div className="h-8 bg-slate-100 rounded" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Catálogo</h1>
        <p className="text-slate-500 text-sm mt-1">Bancos e consignatárias disponíveis para consulta</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {bancos.map((banco) => (
          <div
            key={banco.id}
            className="bg-white rounded-2xl border border-slate-200 p-5 hover:shadow-md transition-shadow"
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="bg-blue-50 rounded-xl p-2.5">
                  <Building2 size={20} className="text-blue-600" />
                </div>
                <div>
                  <h3 className="font-semibold text-slate-800">{banco.nome}</h3>
                  <p className="text-xs text-slate-400">{banco.id}</p>
                </div>
              </div>
              <span
                className={`flex items-center gap-1 text-xs px-2 py-1 rounded-full font-medium ${
                  banco.status === "ativo"
                    ? "bg-green-50 text-green-700"
                    : "bg-slate-100 text-slate-500"
                }`}
              >
                {banco.status === "ativo" ? (
                  <CheckCircle size={11} />
                ) : (
                  <AlertCircle size={11} />
                )}
                {banco.status}
              </span>
            </div>

            <p className="text-sm text-slate-500 mb-4">{banco.descricao}</p>

            {/* Detalhes */}
            <div className="bg-slate-50 rounded-xl p-3 mb-4 grid grid-cols-2 gap-2">
              <div>
                <p className="text-xs text-slate-400">Margem máx.</p>
                <p className="text-sm font-semibold text-slate-700">{banco.margem_maxima}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400">Taxa média</p>
                <p className="text-sm font-semibold text-blue-600">{banco.taxa_media}</p>
              </div>
            </div>

            <button
              onClick={() => onAdicionarCredencial && onAdicionarCredencial(banco.id)}
              className="w-full flex items-center justify-center gap-2 border border-slate-200 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 text-slate-600 text-sm py-2 rounded-xl transition-colors"
            >
              <Plus size={15} />
              Adicionar Credencial
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
