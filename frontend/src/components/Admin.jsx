import { useState, useEffect, useCallback } from "react";
import toast from "react-hot-toast";
import { getAdmin, updateUserPlan, toggleUser, getAdminStats } from "../api";
import { Users, Activity, Database, TrendingUp, RefreshCw } from "lucide-react";

const PLANOS = ["basico", "pro", "enterprise", "admin"];

const BADGE = {
  basico:     "bg-slate-200 text-slate-700",
  pro:        "bg-blue-100 text-blue-700",
  enterprise: "bg-purple-100 text-purple-700",
  admin:      "bg-red-100 text-red-700",
};

function StatCard({ label, value, icon: Icon, color }) {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-5 flex items-center gap-4">
      <div className={`${color} p-3 rounded-xl`}>
        <Icon size={22} className="text-white" />
      </div>
      <div>
        <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">{label}</p>
        <p className="text-2xl font-bold text-slate-800">{value?.toLocaleString() ?? "—"}</p>
      </div>
    </div>
  );
}

export default function Admin() {
  const [usuarios, setUsuarios] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  // edit state per user row
  const [editando, setEditando] = useState({}); // { [id]: { plano, cpfs_mes_limite } }

  const carregar = useCallback(async () => {
    setLoading(true);
    try {
      const [us, st] = await Promise.all([getAdmin(), getAdminStats()]);
      setUsuarios(us);
      setStats(st);
    } catch (e) {
      toast.error("Erro ao carregar dados de admin.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  function iniciarEdicao(u) {
    setEditando(prev => ({
      ...prev,
      [u.id]: { plano: u.plano, cpfs_mes_limite: u.cpfs_mes_limite },
    }));
  }

  function cancelarEdicao(id) {
    setEditando(prev => { const n = { ...prev }; delete n[id]; return n; });
  }

  async function salvarPlano(u) {
    const dados = editando[u.id];
    if (!dados) return;
    try {
      await updateUserPlan(u.id, {
        plano: dados.plano,
        cpfs_mes_limite: parseInt(dados.cpfs_mes_limite, 10),
      });
      toast.success("Plano atualizado.");
      cancelarEdicao(u.id);
      carregar();
    } catch {
      toast.error("Erro ao atualizar plano.");
    }
  }

  async function handleToggle(u) {
    try {
      await toggleUser(u.id);
      toast.success(u.ativo ? "Usuário desativado." : "Usuário ativado.");
      carregar();
    } catch {
      toast.error("Erro ao alterar status.");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Painel Admin</h1>
          <p className="text-slate-500 text-sm mt-1">Gestão de usuários e planos</p>
        </div>
        <button
          onClick={carregar}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-medium transition-colors"
        >
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          Atualizar
        </button>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Usuários"     value={stats?.total_usuarios}          icon={Users}      color="bg-blue-500" />
        <StatCard label="Usuários Ativos"    value={stats?.usuarios_ativos}         icon={Activity}   color="bg-green-500" />
        <StatCard label="CPFs Processados"   value={stats?.total_cpfs_processados}  icon={Database}   color="bg-purple-500" />
        <StatCard label="CPFs Este Mês"      value={stats?.cpfs_este_mes}           icon={TrendingUp} color="bg-orange-500" />
      </div>

      {/* Users table */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100">
          <h2 className="font-semibold text-slate-800">Usuários ({usuarios.length})</h2>
        </div>

        {loading ? (
          <div className="p-10 text-center text-slate-400">Carregando...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                <tr>
                  <th className="px-4 py-3 text-left">Usuário</th>
                  <th className="px-4 py-3 text-left">Plano</th>
                  <th className="px-4 py-3 text-left">Cota/Mês</th>
                  <th className="px-4 py-3 text-left">Usado</th>
                  <th className="px-4 py-3 text-left">Lotes</th>
                  <th className="px-4 py-3 text-left">CPFs Total</th>
                  <th className="px-4 py-3 text-left">Status</th>
                  <th className="px-4 py-3 text-left">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {usuarios.map((u) => {
                  const emEdicao = !!editando[u.id];
                  const ed = editando[u.id] || {};
                  return (
                    <tr key={u.id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3">
                        <p className="font-medium text-slate-800">{u.nome}</p>
                        <p className="text-xs text-slate-400">{u.email}</p>
                      </td>

                      <td className="px-4 py-3">
                        {emEdicao ? (
                          <select
                            value={ed.plano}
                            onChange={e => setEditando(prev => ({
                              ...prev, [u.id]: { ...prev[u.id], plano: e.target.value }
                            }))}
                            className="border border-slate-300 rounded-lg px-2 py-1 text-xs"
                          >
                            {PLANOS.map(p => (
                              <option key={p} value={p}>{p}</option>
                            ))}
                          </select>
                        ) : (
                          <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${BADGE[u.plano] || BADGE.basico}`}>
                            {u.plano}
                          </span>
                        )}
                      </td>

                      <td className="px-4 py-3">
                        {emEdicao ? (
                          <input
                            type="number"
                            value={ed.cpfs_mes_limite}
                            onChange={e => setEditando(prev => ({
                              ...prev, [u.id]: { ...prev[u.id], cpfs_mes_limite: e.target.value }
                            }))}
                            className="border border-slate-300 rounded-lg px-2 py-1 text-xs w-24"
                            min={-1}
                          />
                        ) : (
                          <span className="text-slate-700">
                            {u.cpfs_mes_limite === -1 ? "Ilimitado" : u.cpfs_mes_limite?.toLocaleString()}
                          </span>
                        )}
                      </td>

                      <td className="px-4 py-3 text-slate-600">{u.cpfs_mes_usado?.toLocaleString()}</td>
                      <td className="px-4 py-3 text-slate-600">{u.total_lotes}</td>
                      <td className="px-4 py-3 text-slate-600">{u.total_cpfs?.toLocaleString()}</td>

                      <td className="px-4 py-3">
                        <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${u.ativo ? "bg-green-100 text-green-700" : "bg-red-100 text-red-600"}`}>
                          {u.ativo ? "Ativo" : "Inativo"}
                        </span>
                      </td>

                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2 flex-wrap">
                          {emEdicao ? (
                            <>
                              <button
                                onClick={() => salvarPlano(u)}
                                className="px-2 py-1 rounded-lg bg-blue-600 text-white text-xs hover:bg-blue-700 transition-colors"
                              >
                                Salvar
                              </button>
                              <button
                                onClick={() => cancelarEdicao(u.id)}
                                className="px-2 py-1 rounded-lg bg-slate-200 text-slate-700 text-xs hover:bg-slate-300 transition-colors"
                              >
                                Cancelar
                              </button>
                            </>
                          ) : (
                            <button
                              onClick={() => iniciarEdicao(u)}
                              className="px-2 py-1 rounded-lg bg-slate-100 text-slate-700 text-xs hover:bg-slate-200 transition-colors"
                            >
                              Editar
                            </button>
                          )}
                          <button
                            onClick={() => handleToggle(u)}
                            className={`px-2 py-1 rounded-lg text-xs transition-colors ${
                              u.ativo
                                ? "bg-red-50 text-red-600 hover:bg-red-100"
                                : "bg-green-50 text-green-700 hover:bg-green-100"
                            }`}
                          >
                            {u.ativo ? "Desativar" : "Ativar"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
