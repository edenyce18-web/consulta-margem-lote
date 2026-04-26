import { useState, useEffect } from "react";
import toast from "react-hot-toast";
import { getCredenciais, criarCredencial, deletarCredencial } from "../api";

const TIPOS = [
  { value: "aki",     label: "AkiCapital (SIAPE / Federal)" },
  { value: "grid",    label: "GridSoftware / Roraima (GOV RR)" },
  { value: "exemplo", label: "Portal Exemplo (Testes)" },
];

const STATUS_BADGE = {
  ativa:   "bg-green-100 text-green-700",
  inativa: "bg-slate-100 text-slate-600",
  erro:    "bg-red-100 text-red-700",
};

function ModalNova({ onClose, onSalvar }) {
  const [form, setForm] = useState({ nome: "", tipo_instituicao: "aki", login: "", senha: "", url: "" });
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.nome || !form.login || !form.senha) {
      return toast.error("Preencha todos os campos obrigatórios.");
    }
    setLoading(true);
    try {
      const payload = { ...form };
      if (!payload.url) delete payload.url;
      await criarCredencial(payload);
      toast.success("Credencial salva com sucesso!");
      onSalvar();
      onClose();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao salvar credencial.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md">
        <div className="p-6 border-b border-slate-100">
          <h3 className="text-lg font-semibold text-slate-800">Nova Credencial</h3>
          <p className="text-sm text-slate-500 mt-1">Login e senha são criptografados com AES-256.</p>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Nome da credencial *</label>
            <input
              type="text"
              placeholder="Ex: NyCred - Consultor 1"
              value={form.nome}
              onChange={(e) => setForm({ ...form, nome: e.target.value })}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Portal / Instituição *</label>
            <select
              value={form.tipo_instituicao}
              onChange={(e) => setForm({ ...form, tipo_instituicao: e.target.value })}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
            >
              {TIPOS.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Login *</label>
            <input
              type="text"
              placeholder="CPF ou usuário do portal"
              value={form.login}
              onChange={(e) => setForm({ ...form, login: e.target.value })}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              autoComplete="off"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Senha *</label>
            <div className="relative">
              <input
                type={mostrarSenha ? "text" : "password"}
                placeholder="Senha do portal"
                value={form.senha}
                onChange={(e) => setForm({ ...form, senha: e.target.value })}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                autoComplete="new-password"
              />
              <button
                type="button"
                onClick={() => setMostrarSenha(!mostrarSenha)}
                className="absolute right-2 top-2 text-slate-400 hover:text-slate-600"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {mostrarSenha
                    ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                    : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  }
                </svg>
              </button>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">URL personalizada <span className="text-slate-400">(opcional)</span></label>
            <input
              type="url"
              placeholder="Deixe em branco para usar URL padrão"
              value={form.url}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 border border-slate-300 text-slate-600 py-2 rounded-xl text-sm font-medium hover:bg-slate-50 transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 bg-blue-600 text-white py-2 rounded-xl text-sm font-semibold hover:bg-blue-700 disabled:bg-slate-300 transition-colors"
            >
              {loading ? "Salvando..." : "Salvar Credencial"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ModalConfirmar({ titulo, mensagem, onConfirmar, onCancelar }) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-2">{titulo}</h3>
        <p className="text-sm text-slate-500 mb-6">{mensagem}</p>
        <div className="flex gap-3">
          <button
            onClick={onCancelar}
            className="flex-1 border border-slate-300 text-slate-600 py-2 rounded-xl text-sm font-medium hover:bg-slate-50 transition-colors"
          >
            Cancelar
          </button>
          <button
            onClick={onConfirmar}
            className="flex-1 bg-red-600 text-white py-2 rounded-xl text-sm font-semibold hover:bg-red-700 transition-colors"
          >
            Confirmar
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Credenciais() {
  const [credenciais, setCredenciais] = useState([]);
  const [loading, setLoading]         = useState(true);
  const [showModal, setShowModal]     = useState(false);
  const [deletando, setDeletando]     = useState(null);

  const carregar = async () => {
    try {
      const data = await getCredenciais();
      setCredenciais(data);
    } catch {
      toast.error("Erro ao carregar credenciais.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { carregar(); }, []);

  const handleDeletar = async () => {
    try {
      await deletarCredencial(deletando.id);
      toast.success("Credencial removida.");
      setDeletando(null);
      carregar();
    } catch {
      toast.error("Erro ao remover credencial.");
    }
  };

  const tipoLabel = (tipo) => TIPOS.find((t) => t.value === tipo)?.label || tipo;

  return (
    <div className="max-w-3xl mx-auto">
      {showModal && (
        <ModalNova onClose={() => setShowModal(false)} onSalvar={carregar} />
      )}
      {deletando && (
        <ModalConfirmar
          titulo="Remover credencial"
          mensagem={`Deseja remover a credencial "${deletando.nome}"? Esta ação não pode ser desfeita.`}
          onConfirmar={handleDeletar}
          onCancelar={() => setDeletando(null)}
        />
      )}

      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Credenciais de Acesso</h2>
          <p className="text-sm text-slate-500 mt-1">
            Seus logins são criptografados com AES-256 e nunca ficam visíveis.
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-xl text-sm font-semibold hover:bg-blue-700 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Nova Credencial
        </button>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="bg-white rounded-2xl border border-slate-200 p-5 animate-pulse">
              <div className="h-4 bg-slate-200 rounded w-1/3 mb-2" />
              <div className="h-3 bg-slate-100 rounded w-1/2" />
            </div>
          ))}
        </div>
      ) : credenciais.length === 0 ? (
        <div className="bg-white rounded-2xl border border-dashed border-slate-300 p-12 text-center">
          <svg className="w-12 h-12 mx-auto mb-3 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
          </svg>
          <p className="font-medium text-slate-600">Nenhuma credencial cadastrada</p>
          <p className="text-sm text-slate-400 mt-1">Adicione seu login e senha dos portais bancários</p>
          <button
            onClick={() => setShowModal(true)}
            className="mt-4 bg-blue-600 text-white px-4 py-2 rounded-xl text-sm font-semibold hover:bg-blue-700"
          >
            Adicionar Credencial
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {credenciais.map((cred) => (
            <div key={cred.id} className="bg-white rounded-2xl border border-slate-200 p-5 flex items-center justify-between hover:shadow-sm transition-shadow">
              <div className="flex items-center gap-4">
                <div className="bg-blue-50 p-2.5 rounded-xl">
                  <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                  </svg>
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <p className="font-semibold text-slate-800">{cred.nome}</p>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[cred.status] || STATUS_BADGE.inativa}`}>
                      {cred.status}
                    </span>
                  </div>
                  <p className="text-sm text-slate-500 mt-0.5">{tipoLabel(cred.tipo_instituicao)}</p>
                  {cred.testada_em && (
                    <p className="text-xs text-slate-400 mt-0.5">
                      Testada: {new Date(cred.testada_em).toLocaleString("pt-BR")}
                    </p>
                  )}
                  {cred.mensagem_erro && (
                    <p className="text-xs text-red-500 mt-0.5">{cred.mensagem_erro}</p>
                  )}
                </div>
              </div>

              <button
                onClick={() => setDeletando(cred)}
                className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                title="Remover credencial"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="mt-6 bg-blue-50 border border-blue-100 rounded-xl p-4 text-sm text-blue-700">
        <strong>Segurança:</strong> Suas credenciais são criptografadas com AES-256-GCM antes de
        serem armazenadas. Nem o administrador do sistema consegue ver seus logins e senhas.
      </div>
    </div>
  );
}
