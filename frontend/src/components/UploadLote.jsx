import { useState, useRef } from "react";
import { uploadLote } from "../api";

const BANCOS = [
  { value: "aki",  label: "AkiCapital (SIAPE / Federal)" },
  { value: "grid", label: "GridSoftware / Roraima (GOV RR)" },
];

export default function UploadLote({ onLoteIniciado }) {
  const [arquivo, setArquivo] = useState(null);
  const [banco, setBanco] = useState("aki");
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState(null);
  const [sucesso, setSucesso] = useState(null);
  const inputRef = useRef(null);

  const handleDrop = (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f?.name.toLowerCase().endsWith(".csv")) {
      setArquivo(f);
      setErro(null);
    } else {
      setErro("Apenas arquivos .csv são aceitos.");
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!arquivo) return setErro("Selecione um arquivo CSV com os CPFs.");
    setCarregando(true);
    setErro(null);
    setSucesso(null);
    try {
      const resp = await uploadLote(arquivo, banco);
      setSucesso(resp);
      onLoteIniciado(resp.lote_id);
    } catch (err) {
      setErro(err.response?.data?.detail || "Erro ao enviar o arquivo.");
    } finally {
      setCarregando(false);
    }
  };

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
              setErro(null);
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

        {/* Seletor de portal */}
        <div>
          <label className="block text-sm font-medium text-slate-600 mb-1">
            Portal de Consulta
          </label>
          <select
            value={banco}
            onChange={(e) => setBanco(e.target.value)}
            className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
          >
            {BANCOS.map((b) => (
              <option key={b.value} value={b.value}>{b.label}</option>
            ))}
          </select>
        </div>

        {/* Informação do portal selecionado */}
        {banco === "aki" && (
          <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-xs text-blue-700">
            <strong>AkiCapital:</strong> Captura Empréstimo, Cartão de Crédito e Cartão Benefício
            (Autorizado/Não Autorizado) + Margem Consignável do Benefício.
          </div>
        )}
        {banco === "grid" && (
          <div className="bg-indigo-50 border border-indigo-100 rounded-lg p-3 text-xs text-indigo-700">
            <strong>GridSoftware / Roraima:</strong> Captura Margem de Empréstimo e Margem de
            Cartão de Crédito em R$.
          </div>
        )}

        {/* Feedback */}
        {erro && (
          <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">
            <svg className="w-4 h-4 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            {erro}
          </div>
        )}
        {sucesso && (
          <div className="flex items-start gap-2 bg-green-50 border border-green-200 text-green-700 rounded-lg p-3 text-sm">
            <svg className="w-4 h-4 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              <strong>Lote criado!</strong>{" "}
              {sucesso.total_cpfs} CPFs em processamento.
            </div>
          </div>
        )}

        <button
          type="submit"
          disabled={carregando || !arquivo}
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
