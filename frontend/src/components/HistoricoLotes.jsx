import { useState, useEffect } from "react";
import { getLotes } from "../api";

const STATUS_COR = {
  pendente:    "bg-yellow-100 text-yellow-700",
  processando: "bg-blue-100 text-blue-700",
  concluido:   "bg-green-100 text-green-700",
  erro:        "bg-red-100 text-red-700",
};

const PORTAL_LABEL = {
  aki:  "AkiCapital",
  grid: "Grid / RR",
};

export default function HistoricoLotes({ onSelecionar, loteAtivo }) {
  const [lotes, setLotes] = useState([]);

  useEffect(() => {
    const fetch = () => getLotes().then(setLotes).catch(() => {});
    fetch();
    const t = setInterval(fetch, 8000);
    return () => clearInterval(t);
  }, []);

  if (!lotes.length) return null;

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
      <h2 className="text-lg font-semibold text-slate-700 mb-4 flex items-center gap-2">
        <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        Histórico de Lotes
      </h2>
      <div className="space-y-2">
        {lotes.map((lote) => (
          <button
            key={lote.id}
            onClick={() => onSelecionar(lote.id)}
            className={`w-full flex items-center justify-between p-3 rounded-xl border transition-colors text-left ${
              loteAtivo === lote.id
                ? "border-blue-400 bg-blue-50"
                : "border-slate-100 hover:border-blue-200 hover:bg-blue-50"
            }`}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5 mb-0.5">
                {lote.banco_portal && (
                  <span className="text-xs bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded font-medium">
                    {PORTAL_LABEL[lote.banco_portal] || lote.banco_portal}
                  </span>
                )}
                <span className="text-xs font-mono text-slate-400 truncate">
                  {lote.id?.slice(0, 12)}...
                </span>
              </div>
              <div className="text-sm text-slate-700 font-medium truncate">
                {lote.arquivo_original}
              </div>
              <div className="text-xs text-slate-400 mt-0.5">
                {lote.total_cpfs} CPFs ·{" "}
                {new Date(lote.criado_em).toLocaleString("pt-BR")} ·{" "}
                <span className="text-green-600">{lote.sucessos} ok</span>
                {" / "}
                <span className="text-red-500">{lote.erros} erros</span>
              </div>
            </div>
            <div className="flex items-center gap-2 ml-3 shrink-0">
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COR[lote.status] ?? ""}`}>
                {lote.status}
              </span>
              <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
