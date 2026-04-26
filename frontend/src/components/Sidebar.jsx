import { useState } from "react";
import {
  LayoutDashboard, Zap, Phone, MessageSquare, BookOpen,
  Key, ChevronLeft, ChevronRight, LogOut,
} from "lucide-react";

const MENU = [
  { id: "dashboard",   label: "Início",       icon: LayoutDashboard },
  { id: "consultas",   label: "Higienização", icon: Zap },
  { id: "credenciais", label: "Credenciais",  icon: Key },
  { id: "catalogo",    label: "Catálogo",     icon: BookOpen },
  { id: "ura",         label: "URA",          icon: Phone },
  { id: "chat",        label: "Chat",         icon: MessageSquare },
];

export default function Sidebar({ abaAtiva, onChangeAba, usuario, onLogout }) {
  const [collapsed, setCollapsed] = useState(false);

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
        {MENU.map(({ id, label, icon: Icon }) => {
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
                  ? "bg-blue-600 text-white"
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
