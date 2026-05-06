import { useState } from "react";
import {
  LayoutDashboard, Zap, Phone, MessageSquare, BookOpen,
  Key, ChevronLeft, ChevronRight, LogOut, Shield, User,
} from "lucide-react";

const MENU_BASE = [
  { id: "dashboard",   label: "Início",       icon: LayoutDashboard },
  { id: "consultas",   label: "Higienização", icon: Zap },
  { id: "credenciais", label: "Credenciais",  icon: Key },
  { id: "catalogo",    label: "Catálogo",     icon: BookOpen },
  { id: "perfil",      label: "Perfil",       icon: User },
  { id: "ura",         label: "URA",          icon: Phone },
  { id: "chat",        label: "Chat",         icon: MessageSquare },
];

const MENU_ADMIN = { id: "admin", label: "Admin", icon: Shield };

function CotaBar({ usuario, collapsed }) {
  if (!usuario) return null;

  const plano = usuario.plano || "basico";
  const ilimitado = usuario.cpfs_mes_limite === -1 || plano === "enterprise" || plano === "admin";
  const usado = usuario.cpfs_mes_usado || 0;
  const limite = usuario.cpfs_mes_limite || 500;
  const pct = ilimitado ? 0 : Math.min(100, Math.round((usado / limite) * 100));
  const cor = pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-yellow-400" : "bg-blue-400";

  if (collapsed) return null;

  return (
    <div className="px-3 py-2 border-t border-slate-700">
      <p className="text-xs text-slate-400 mb-1 font-medium">CPFs este mês</p>
      {ilimitado ? (
        <p className="text-xs text-green-400 font-semibold">Ilimitado</p>
      ) : (
        <>
          <div className="flex justify-between text-xs text-slate-400 mb-1">
            <span>{usado.toLocaleString()}/{limite.toLocaleString()}</span>
            <span>{pct}%</span>
          </div>
          <div className="w-full bg-slate-700 rounded-full h-1.5">
            <div
              className={`${cor} h-1.5 rounded-full transition-all duration-300`}
              style={{ width: `${pct}%` }}
            />
          </div>
        </>
      )}
    </div>
  );
}

export default function Sidebar({ abaAtiva, onChangeAba, usuario, onLogout }) {
  const [collapsed, setCollapsed] = useState(false);

  const isAdmin = usuario?.plano === "admin";
  const menu = isAdmin ? [...MENU_BASE, MENU_ADMIN] : MENU_BASE;

  return (
    <aside
      className={`${
        collapsed ? "w-16" : "w-60"
      } bg-slate-900 text-white flex flex-col shrink-0 transition-all duration-200 relative`}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-slate-700">
        <div className="bg-blue-600 rounded-xl p-2 shrink-0">
          <LayoutDashboard size={18} className="text-white" />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <p className="font-bold text-sm leading-none">ConsultaMargem</p>
            <p className="text-xs text-slate-400 mt-0.5 truncate">AkiCapital · Grid</p>
          </div>
        )}
      </div>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed((v) => !v)}
        className="absolute -right-3 top-6 bg-slate-700 hover:bg-slate-600 rounded-full p-1 z-10 transition-colors"
      >
        {collapsed ? (
          <ChevronRight size={14} className="text-white" />
        ) : (
          <ChevronLeft size={14} className="text-white" />
        )}
      </button>

      {/* Nav items */}
      <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
        {menu.map(({ id, label, icon: Icon }) => {
          const ativo = abaAtiva === id;
          const desabilitado = id === "ura" || id === "chat";
          return (
            <button
              key={id}
              onClick={() => !desabilitado && onChangeAba(id)}
              disabled={desabilitado}
              title={collapsed ? label : undefined}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors
                ${ativo
                  ? id === "admin"
                    ? "bg-red-700 text-white"
                    : "bg-blue-600 text-white"
                  : desabilitado
                  ? "text-slate-600 cursor-not-allowed"
                  : "text-slate-300 hover:bg-slate-800 hover:text-white"}
              `}
            >
              <Icon size={18} className="shrink-0" />
              {!collapsed && (
                <span className="truncate">
                  {label}
                  {desabilitado && (
                    <span className="ml-1 text-[10px] bg-slate-700 text-slate-400 px-1 py-0.5 rounded">
                      em breve
                    </span>
                  )}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Cota bar */}
      <CotaBar usuario={usuario} collapsed={collapsed} />

      {/* User area */}
      <div className="border-t border-slate-700 p-3 space-y-2">
        {!collapsed && usuario && (
          <div className="px-2 py-1">
            <p className="text-sm font-semibold truncate">{usuario.nome}</p>
            <p className="text-xs text-slate-400 truncate">{usuario.email}</p>
          </div>
        )}
        <button
          onClick={onLogout}
          title="Sair"
          className="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm text-slate-400 hover:bg-slate-800 hover:text-red-400 transition-colors"
        >
          <LogOut size={16} className="shrink-0" />
          {!collapsed && <span>Sair</span>}
        </button>
      </div>
    </aside>
  );
}
