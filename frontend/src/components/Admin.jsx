import { useState, useEffect, useCallback } from "react";
import toast from "react-hot-toast";
import { getAdmin, toggleUser, getAdminStats } from "../api";
import { Users, Activity, Database, TrendingUp, RefreshCw } from "lucide-react";

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

  const carregar = useCallback(async () => {
    setLoading(true);
    try {
      const [us, st] = await Promise.all([getAdmin(), getAdminStats()]);
      setUsuarios(us);
      setStats(st);
    } catch {
      toast.error("Erro ao carregar dados de admin.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  async function handleToggle(u) {
    try {
      await toggleUser(u.id);
      toast.success(`Usuário ${u.ativo ? "desativado" : "ativado"}.`);
      carregar();
    } catch {
      toast.error("Erro ao alterar status.");
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[1,2,3,4].map(i => (
            <div key={i} className="bg-white rounded-2xl border border-slate-200 p-5 animate-pulse h-24" />
          ))}
        </div>
        <div className="bg-white rounded-2xl border border-slate-200 p-8 animate-pulse h-64" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Painel Admin</h1>
          <p className="text-slate-500 text-sm mt-1">Gestão de usuários do sistema</p>
        </div>
        <button
          onClick={carregar}
          className="flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 rounded-xl text-sm font-medium text-slate-700 transition-colors"
        >
          <RefreshCw size={15} />
          Atualizar
        </button>
      </div>

      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Total usuários"   value={stats.total_usuarios}         icon={Users}      color="bg-blue-500" />
          <StatCard label="Usuários ativos"  value={stats.usuarios_ativos}        icon={Activity}   color="bg-green-500" />
          <StatCard label="Total de lotes"   value={stats.total_lotes}            icon={Database}   color="bg-purple-500" />
          <StatCard label="CPFs processados" value={stats.total_cpfs_processados} icon={TrendingUp} color="bg-orange-500" />
        </div>
      )}

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100">
          <h2 className="font-semibold text-slate-800">Usuários ({usuarios.length})</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
                <th className="px-6 py-3 text-left">Nome / Email</th>
                <th className="px-4 py-3 text-left">Cadastro</th>
                <th className="px-4 py-3 text-center">Lotes</th>
                <th className="px-4 py-3 text-center">CPFs</th>
                <th className="px-4 py-3 text-center">Perfil</th>
                <th className="px-4 py-3 text-center">Status</th>
                <th className="px-4 py-3 text-center">Ação</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {usuarios.map(u => (
                <tr key={u.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-6 py-3">
                    <p className="font-medium text-slate-800">{u.nome}</p>
                    <p className="text-xs text-slate-400">{u.email}</p>
                  </td>
                  <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
                    {new Date(u.criado_em).toLocaleDateString("pt-BR")}
                  </td>
                  <td className="px-4 py-3 text-center font-medium text-slate-700">
                    {u.total_lotes.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-center font-medium text-slate-700">
                    {u.total_cpfs.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${
                      u.is_admin ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-500"
                    }`}>
                      {u.is_admin ? "Admin" : "Usuário"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${
                      u.ativo ? "bg-green-100 text-green-700" : "bg-red-100 text-red-600"
                    }`}>
                      {u.ativo ? "Ativo" : "Inativo"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => handleToggle(u)}
                      className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                        u.ativo
                          ? "bg-red-50 text-red-600 hover:bg-red-100"
                          : "bg-green-50 text-green-600 hover:bg-green-100"
                      }`}
                    >
                      {u.ativo ? "Desativar" : "Ativar"}
                    </button>
                  </td>
                </tr>
              ))}
              {usuarios.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-6 py-10 text-center text-slate-400 text-sm">
                    Nenhum usuário encontrado.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
