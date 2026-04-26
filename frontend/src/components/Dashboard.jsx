import { useState, useEffect } from "react";
import { getDashboard, exportarLote } from "../api";
import toast from "react-hot-toast";
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";

const STATUS_COLOR = {
  concluido:   "bg-green-100 text-green-700",
  processando: "bg-blue-100 text-blue-700",
  pendente:    "bg-yellow-100 text-yellow-700",
  erro:        "bg-red-100 text-red-700",
};

function StatCard({ label, value, sub, color }) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-5">
      <p className="text-sm text-slate-500 font-medium">{label}</p>
      <p className={`text-3xl font-bold mt-1 ${color || "text-slate-800"}`}>{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-1">{sub}</p>}
    </div>
  );
}

export default function Dashboard({ onIrParaLotes }) {
  const [stats, setStats]     = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getDashboard()
      .then(setStats)
      .catch(() => toast.error("Erro ao carregar dashboard."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-white rounded-2xl border border-slate-200 p-5 animate-pulse">
              <div className="h-3 bg-slate-200 rounded w-1/2 mb-3" />
              <div className="h-8 bg-slate-200 rounded w-1/3" />
            </div>
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {[1, 2].map((i) => (
            <div key={i} className="bg-white rounded-2xl border border-slate-200 p-5 h-56 animate-pulse">
              <div className="h-4 bg-slate-200 rounded w-1/3 mb-4" />
              <div className="h-36 bg-slate-100 rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!stats) return null;

  const consultasDia  = stats.consultas_por_dia  || [];
  const margensBanco  = stats.margens_por_banco  || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Início</h1>
        <p className="text-slate-500 text-sm mt-1">Visão geral da sua operação</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total de Lotes"
          value={stats.total_lotes.toLocaleString("pt-BR")}
          sub="consultas realizadas"
        />
        <StatCard
          label="CPFs Processados"
          value={stats.total_cpfs.toLocaleString("pt-BR")}
          sub="em todos os lotes"
          color="text-blue-600"
        />
        <StatCard
          label="Sucessos"
          value={stats.total_sucessos.toLocaleString("pt-BR")}
          sub="com margem encontrada"
          color="text-green-600"
        />
        <StatCard
          label="Taxa de Sucesso"
          value={`${stats.taxa_sucesso_pct}%`}
          sub={`${stats.total_erros.toLocaleString("pt-BR")} erros/sem margem`}
          color={stats.taxa_sucesso_pct >= 70 ? "text-green-600" : "text-orange-500"}
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Consultas por dia */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5">
          <h3 className="font-semibold text-slate-800 mb-4">Consultas por Dia</h3>
          {consultasDia.length === 0 ? (
            <div className="h-36 flex items-center justify-center text-slate-400 text-sm">
              Sem dados nos últimos 14 dias
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={consultasDia} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis
                  dataKey="dia"
                  tick={{ fontSize: 11, fill: "#94a3b8" }}
                  tickFormatter={(v) => v.slice(5)}
                />
                <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 }}
                  labelFormatter={(v) => `Dia: ${v}`}
                />
                <Line
                  type="monotone"
                  dataKey="total"
                  stroke="#2563eb"
                  strokeWidth={2}
                  dot={{ r: 3, fill: "#2563eb" }}
                  name="CPFs"
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Margem por banco */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5">
          <h3 className="font-semibold text-slate-800 mb-4">CPFs por Portal</h3>
          {margensBanco.length === 0 ? (
            <div className="h-36 flex items-center justify-center text-slate-400 text-sm">
              Nenhum lote processado ainda
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={margensBanco} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="banco" tick={{ fontSize: 11, fill: "#94a3b8" }} />
                <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 }}
                />
                <Bar dataKey="cpfs" name="Total CPFs" fill="#bfdbfe" radius={[4, 4, 0, 0]} />
                <Bar dataKey="sucessos" name="Sucessos" fill="#2563eb" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Lotes recentes */}
      <div className="bg-white rounded-2xl border border-slate-200">
        <div className="flex items-center justify-between p-5 border-b border-slate-100">
          <h3 className="font-semibold text-slate-800">Lotes Recentes</h3>
          <button
            onClick={onIrParaLotes}
            className="text-sm text-blue-600 hover:text-blue-700 font-medium"
          >
            Ver todos →
          </button>
        </div>

        {stats.lotes_recentes.length === 0 ? (
          <div className="p-10 text-center text-slate-400">
            <p className="text-sm">Nenhum lote processado ainda.</p>
            <button
              onClick={onIrParaLotes}
              className="mt-3 bg-blue-600 text-white px-4 py-2 rounded-xl text-sm font-semibold hover:bg-blue-700"
            >
              Fazer primeiro upload
            </button>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {stats.lotes_recentes.map((lote) => (
              <div key={lote.id} className="p-4 flex items-center justify-between hover:bg-slate-50">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="shrink-0">
                    <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${STATUS_COLOR[lote.status] || STATUS_COLOR.pendente}`}>
                      {lote.status}
                    </span>
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">
                      {lote.arquivo_original || "—"}
                    </p>
                    <p className="text-xs text-slate-500">
                      {lote.banco_portal?.toUpperCase()} · {lote.total_cpfs} CPFs ·{" "}
                      {new Date(lote.criado_em).toLocaleDateString("pt-BR")}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <div className="hidden md:flex flex-col items-end">
                    <div className="w-28 bg-slate-100 rounded-full h-1.5">
                      <div
                        className="bg-blue-500 h-1.5 rounded-full"
                        style={{ width: `${lote.progresso_pct}%` }}
                      />
                    </div>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {lote.sucessos}/{lote.total_cpfs} ok
                    </p>
                  </div>

                  {lote.status === "concluido" && (
                    <div className="flex gap-1">
                      <button
                        onClick={() => exportarLote(lote.id, "csv").catch(() => toast.error("Erro ao exportar"))}
                        className="text-xs text-slate-500 hover:text-blue-600 border border-slate-200 px-2 py-1 rounded-lg hover:border-blue-200 transition-colors"
                        title="Exportar CSV"
                      >
                        CSV
                      </button>
                      <button
                        onClick={() => exportarLote(lote.id, "xlsx").catch(() => toast.error("Erro ao exportar"))}
                        className="text-xs text-slate-500 hover:text-green-600 border border-slate-200 px-2 py-1 rounded-lg hover:border-green-200 transition-colors"
                        title="Exportar Excel"
                      >
                        XLS
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
