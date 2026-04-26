import { useState, useRef, useEffect } from "react";
import toast from "react-hot-toast";
import { uploadLote, getCredenciais } from "../api";

export default function UploadLote({ onLoteIniciado }) {
  const [arquivo, setArquivo]         = useState(null);
  const [credenciais, setCredenciais] = useState([]);
  const [credencialId, setCredencialId] = useState("");
  const [banco, setBanco]             = useState("aki");
  const [carregando, setCarregando]   = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    getCredenciais().then(setCredenciais).catch(() => {});
  }, []);

  // Quando seleciona credencial, sincroniza o banco
  const handleCredencial = (id) => {
    setCredencialId(id);
    if (id) {
      const cred = credenciais.find((c) => c.id === id);
      if (cred) setBanco(cred.tipo_instituicao);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f?.name.toLowerCase().endsWith(".csv")) {
      setArquivo(f);
    } else {
      toast.error("Apenas arquivos .csv são aceitos.");
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!arquivo) return toast.error("Selecione um arquivo CSV com os CPFs.");
    if (!credencialId) return toast.error("Selecione uma credencial antes de iniciar.");

    setCarregando(true);
    try {
      const resp = await uploadLote(arquivo, banco, credencialId);
      toast.success(`Lote criado! ${resp.total_cpfs} CPFs em processamento.`);
      onLoteIniciado(resp.lote_id);
      setArquivo(null);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao enviar o arquivo.");
    } finally {
      setCarregando(false);
    }
  };

  const credSelecionada = credenciais.find((c) => c.id === credencialId);

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
      <h2 className="text-lg font-semibold text-slate-700 mb-4 flex items-center gap-2">
        <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
        </svg>
        Novo Lote de Consulta
      </h2>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Seleção de credencial */}
        <div>
          <label className="block text-sm font-medium text-slate-600 mb-1">
            Credencial de Acesso *
          </label>
          {credenciais.length === 0 ? (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-700">
              Nenhuma credencial cadastrada. Vá em <strong>Credenciais</strong> e adicione seu acesso ao portal.
            </div>
          ) : (
            <select
              value={credencialId}
              onChange={(e) => handleCredencial(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
            >
              <option value="">— Selecione uma credencial —</option>
              {credenciais.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome} ({c.tipo_instituicao.toUpperCase()})
                </option>
              ))}
            </select>
          )}
          {credSelecionada && (
            <p className="text-xs text-slate-500 mt-1">
              Portal: {credSelecionada.tipo_instituicao} · Status: {credSelecionada.status}
            </p>
          )}
        </div>

        {/* Drop zone */}
        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => inputRef.current?.click()}
          className="border-2 border-dashed border-slate-300 rounded-xl p-8 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-colors"
        >
          <input
            ref={inputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => {
              setArquivo(e.target.files[0]);
              e.target.value = "";
            }}
          />
          {arquivo ? (
            <div className="flex items-center justify-center gap-2 text-blue-700 font-medium text-sm">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              {arquivo.name}
              <span className="text-slate-400 text-xs font-normal">
                ({(arquivo.size / 1024).toFixed(1)} KB)
              </span>
            </div>
          ) : (
            <div className="text-slate-400">
              <svg className="w-10 h-10 mx-auto mb-2 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
              <p className="text-sm">Arraste o CSV aqui ou clique para selecionar</p>
              <p className="text-xs mt-1">
                Coluna obrigatória: <code className="bg-slate-100 px-1 rounded">cpf</code>
              </p>
            </div>
          )}
        </div>

        <button
          type="submit"
          disabled={carregando || !arquivo || !credencialId}
          className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white font-semibold py-2.5 rounded-xl transition-colors text-sm"
        >
          {carregando ? "Enviando..." : "Iniciar Consulta em Lote"}
        </button>
      </form>

      <div className="mt-4 p-3 bg-slate-50 rounded-lg text-xs text-slate-500">
        <strong>Formato CSV:</strong>
        <pre className="mt-1 font-mono">cpf{"\n"}02622395230{"\n"}12345678901</pre>
      </div>
    </div>
  );
}
