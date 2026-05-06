import { useState, useEffect } from "react";
import toast from "react-hot-toast";
import { getPerfil } from "../api";
import { User, TrendingUp, Star, MessageCircle } from "lucide-react";

const PLANO_CONFIG = {
  basico:     { label: "Básico",     badge: "bg-slate-200 text-slate-700",  desc: "Até 500 CPFs por mês" },
  pro:        { label: "Pro",        badge: "bg-blue-100 text-blue-700",    desc: "Até 2.000 CPFs por mês" },
  enterprise: { label: "Enterprise", badge: "bg-purple-100 text-purple-700", desc: "CPFs ilimitados" },
  admin:      { label: "Admin",      badge: "bg-red-100 text-red-700",      desc: "Acesso total ao sistema" },
};

export default function Perfil() {
  const [perfil, setPerfil] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPerfil()
      .then(setPerfil)
      .catch(() => toast.error("Erro ao carregar perfil."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">
        Carregando perfil...
      </div>
    );
  }

  if (!perfil) return null;

  const plano = perfil.plano || "basico";
  const config = PLANO_CONFIG[plano] || PLANO_CONFIG.basico;
  const ilimitado = perfil.cpfs_mes_limite === -1 || plano === "enterprise" || plano === "admin";
  const usado = perfil.cpfs_mes_usado || 0;
  const limite = perfil.cpfs_mes_limite || 500;
  const pct = ilimitado ? 0 : Math.min(100, Math.round((usado / limite) * 100));
  const cor = pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-yellow-400" : "bg-blue-500";

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Meu Perfil</h1>
        <p className="text-slate-500 text-sm mt-1">Informações da sua conta e plano</p>
      </div>

      {/* Info Card */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 space-y-4">
        <div className="flex items-center gap-4">
          <div className="bg-blue-100 rounded-full p-3">
            <User size={24} className="text-blue-600" />
          </div>
          <div>
            <p className="font-semibold text-slate-800 text-lg">{perfil.nome}</p>
            <p className="text-slate-500 text-sm">{perfil.email}</p>
          </div>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <span className="text-sm text-slate-600 font-medium">Plano atual:</span>
          <span className={`inline-block px-3 py-1 rounded-full text-sm font-semibold ${config.badge}`}>
            {config.label}
          </span>
        </div>
        <p className="text-slate-500 text-sm">{config.desc}</p>
      </div>

      {/* Cota Card */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 space-y-4">
        <div className="flex items-center gap-2">
          <TrendingUp size={18} className="text-slate-600" />
          <h2 className="font-semibold text-slate-800">Uso este mês</h2>
        </div>

        {ilimitado ? (
          <div className="flex items-center gap-2">
            <Star size={16} className="text-purple-500" />
            <p className="text-green-600 font-semibold">Consultas ilimitadas</p>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-slate-600">
                {usado.toLocaleString()} CPFs consultados
              </span>
              <span className="text-slate-500">
                de {limite.toLocaleString()} disponíveis
              </span>
            </div>
            <div className="w-full bg-slate-100 rounded-full h-3">
              <div
                className={`${cor} h-3 rounded-full transition-all duration-500`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-slate-400">
              <span>{pct}% utilizado</span>
              <span>{Math.max(0, limite - usado).toLocaleString()} restantes</span>
            </div>
          </div>
        )}
      </div>

      {/* Upgrade Card */}
      {plano !== "enterprise" && plano !== "admin" && (
        <div className="bg-gradient-to-r from-blue-50 to-purple-50 rounded-2xl border border-blue-100 p-6 space-y-3">
          <div className="flex items-center gap-2">
            <Star size={18} className="text-purple-500" />
            <h2 className="font-semibold text-slate-800">Aumentar seu plano</h2>
          </div>
          <p className="text-slate-600 text-sm">
            Precisa de mais CPFs por mês? Entre em contato para conhecer os planos Pro e Enterprise.
          </p>
          <button
            onClick={() => toast.success("Entre em contato via WhatsApp para solicitar o upgrade do seu plano.")}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            <MessageCircle size={16} />
            Solicitar upgrade
          </button>
        </div>
      )}
    </div>
  );
}
