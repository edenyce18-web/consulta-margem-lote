import { useState, useEffect, useCallback } from "react";
import { getStatusLote } from "../api";

const STATUS_CONFIG = {
  pendente:    { label: "Pendente",    cor: "text-yellow-600 bg-yellow-50 border-yellow-200" },
  processando: { label: "Processando", cor: "text-blue-600 bg-blue-50 border-blue-200" },
  concluido:   { label: "Concluído",   cor: "text-green-600 bg-green-50 border-green-200" },
  erro:        { label: "Erro",        cor: "text-red-600 bg-red-50 border-red-200" },
};

const CONSULTA_STATUS = {
  aguardando:   { label: "Aguardando",   bg: "bg-slate-100 text-slate-600" },
  processando:  { label: "Processando",  bg: "bg-blue-100 text-blue-700" },
  sucesso:      { label: "Sucesso",      bg: "bg-green-100 text-green-700" },
  erro:         { label: "Erro",         bg: "bg-red-100 text-red-700" },
  cpf_invalido: { label: "CPF Inválido", bg: "bg-orange-100 text-orange-700" },
  sem_margem:   { label: "Sem Margem",   bg: "bg-purple-100 text-purple-700" },
};

function moeda(val) {
  if (val == null) return "—";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(val);
}

function formatarCPF(cpf) {
  if (!cpf) return "";
  const d = cpf.replace(/\D/g, "");
  if (d.length !== 11) return cpf;
  return `${d.slice(0,3)}.${d.slice(3,6)}.${d.slice(6,9)}-${d.slice(9)}`;
}

function BadgeAutorizacao({ situacao }) {
  if (!situacao) return <span className="text-slate-300 text-xs">—</span>;
  const autorizado = situacao === "Autorizado";
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${
      autorizado ? "bg-green-100 text-green-700" : "bg-red-100 text-red-600"
    }`}>
      {autorizado ? "✓ Autorizado" : "✗ Não Autori."}
    </span>
  );
}

export default function StatusLote({ loteId }) {
  const [dados, setDados] = useState(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [filtro, setFiltro] = useState("todos");

  const carregar = useCallback(async () => {
    if (!loteId) return;
    setCarregando(true);
    try {
      const resp = await getStatusLote(loteId, 0, 500);
      setDados(resp);
      setErro(null);
      if (resp.status === "concluido" || resp.status === "erro") {
        setAutoRefresh(false);
      }
    } catch (e) {
      setErro(e.response?.data?.detail || "Erro ao buscar status.");
    } finally {
      setCarregando(false);
    }
  }, [loteId]);

  useEffect(() => { carregar(); }, [carregar]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(carregar, 3000);
    return () => clearInterval(interval);
  }, [autoRefresh, carregar]);

  if (!loteId) return null;

  const cfg = dados ? (STATUS_CONFIG[dados.status] || STATUS_CONFIG.pendente) : null;

  // Detecta se é portal Aki (usa campos de autorização) ou Grid (usa margens em R$)
  const isAki = dados?.banco_portal === "aki" || dados?.consultas?.some(
    (c) => c.emprestimo_situacao != null || c.cartao_credito_situacao != null
  );

  const consultasFiltradas = (dados?.consultas ?? []).filter((c) =>
    filtro === "todos" ? true : c.status_consulta === filtro
  );

  const exportarCSV = () => {
    if (!dados?.consultas?.length) return;
    const cols = isAki
      ? ["CPF","Nome","Órgão","Tipo Vínculo","Matrícula","Empréstimo","Cartão Crédito","Cartão Benefício","Margem Benefício","Status","Erro"]
      : ["CPF","Nome","Órgão","Margem Empréstimo","Margem Cartão","Status","Erro"];

    const rows = dados.consultas
      .filter((c) => c.status_consulta !== "aguardando")
      .map((c) => isAki
        ? [
            formatarCPF(c.cpf), c.nome_titular || "", c.orgao || "",
            c.tipo_vinculo || "", c.matricula || "",
            c.emprestimo_situacao || "", c.cartao_credito_situacao || "",
            c.cartao_beneficio_situacao || "",
            c.margem_beneficio != null ? Number(c.margem_beneficio).toFixed(2).replace(".", ",") : "",
            c.status_consulta, c.mensagem_erro || "",
          ]
        : [
            formatarCPF(c.cpf), c.nome_titular || "", c.orgao || "",
            c.margem_disponivel != null ? Number(c.margem_disponivel).toFixed(2).replace(".", ",") : "",
            c.margem_cartao != null ? Number(c.margem_cartao).toFixed(2).replace(".", ",") : "",
            c.status_consulta, c.mensagem_erro || "",
          ]
      );

    const csv = [cols.join(";"), ...rows.map((r) => r.join(";"))].join("\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `resultados_${dados.banco_portal || "lote"}_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 space-y-5">
      {/* Cabeçalho */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-700 flex items-center gap-2">
          <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
          </svg>
          Resultados do Lote
          {dados?.banco_portal && (
            <span className="text-xs font-normal bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full ml-1">
              {dados.banco_portal === "aki" ? "AkiCapital" : "GridSoftware / Roraima"}
            </span>
          )}
        </h2>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setAutoRefresh((v) => !v)}
            className={`text-xs px-2 py-1 rounded-full border transition-colors ${
              autoRefresh
                ? "bg-blue-50 border-blue-200 text-blue-700"
                : "bg-slate-50 border-slate-200 text-slate-500"
            }`}
          >
            {autoRefresh ? "Auto ativo" : "Pausado"}
          </button>
          <button
            onClick={carregar}
            disabled={carregando}
            title="Atualizar"
            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 transition-colors"
          >
            <svg className={`w-4 h-4 ${carregando ? "animate-spin" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>

      {/* ID */}
      <div className="text-xs text-slate-400 font-mono break-all">ID: {loteId}</div>

      {erro && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">
          {erro}
        </div>
      )}

      {dados && (
        <>
          {/* Status badge */}
          <div className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-sm font-medium ${cfg.cor}`}>
            {dados.status === "processando" && (
              <svg className="w-3.5 h-3.5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            )}
            {cfg.label}
          </div>

          {/* Métricas */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "Total",       val: dados.total_cpfs,  cor: "text-slate-800" },
              { label: "Processados", val: dados.processados, cor: "text-blue-600" },
              { label: "Sucesso",     val: dados.sucessos,    cor: "text-green-600" },
              { label: "Erros",       val: dados.erros,       cor: "text-red-600" },
            ].map(({ label, val, cor }) => (
              <div key={label} className="bg-slate-50 rounded-xl p-3 text-center border border-slate-100">
                <div className={`text-2xl font-bold ${cor}`}>{val ?? 0}</div>
                <div className="text-xs text-slate-500 mt-0.5">{label}</div>
              </div>
            ))}
          </div>

          {/* Barra de progresso */}
          <div>
            <div className="flex justify-between text-xs text-slate-500 mb-1">
              <span>Progresso</span>
              <span>{dados.progresso_pct}%</span>
            </div>
            <div className="w-full bg-slate-100 rounded-full h-3">
              <div
                className={`h-3 rounded-full transition-all duration-700 ${
                  dados.status === "concluido" ? "bg-green-500" : "bg-blue-500"
                }`}
                style={{ width: `${dados.progresso_pct}%` }}
              />
            </div>
          </div>

          {/* Filtros */}
          {dados.consultas?.length > 0 && (
            <>
              <div className="flex flex-wrap gap-2 text-xs">
                {["todos", "sucesso", "sem_margem", "erro", "cpf_invalido", "aguardando"].map((f) => (
                  <button
                    key={f}
                    onClick={() => setFiltro(f)}
                    className={`px-3 py-1 rounded-full border transition-colors ${
                      filtro === f
                        ? "bg-blue-600 border-blue-600 text-white"
                        : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {f === "todos" ? "Todos" : CONSULTA_STATUS[f]?.label ?? f}
                    {f !== "todos" && (
                      <span className="ml-1 opacity-70">
                        ({dados.consultas.filter((c) => c.status_consulta === f).length})
                      </span>
                    )}
                  </button>
                ))}
              </div>

              {/* Tabela */}
              <div className="overflow-x-auto rounded-xl border border-slate-200">
                {isAki ? (
                  // ── Tabela AkiCapital ──────────────────────────────────────
                  <table className="w-full text-sm min-w-[820px]">
                    <thead className="bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                      <tr>
                        <th className="px-4 py-3 text-left">CPF</th>
                        <th className="px-4 py-3 text-left">Nome / Órgão</th>
                        <th className="px-4 py-3 text-center">Empréstimo</th>
                        <th className="px-4 py-3 text-center">Cartão Crédito</th>
                        <th className="px-4 py-3 text-center">Cartão Benefício</th>
                        <th className="px-4 py-3 text-right">Marg. Benefício</th>
                        <th className="px-4 py-3 text-left">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {consultasFiltradas.length === 0 ? (
                        <tr>
                          <td colSpan={7} className="text-center py-10 text-slate-400 text-sm">
                            Nenhum resultado para o filtro selecionado.
                          </td>
                        </tr>
                      ) : consultasFiltradas.map((c) => {
                        const sc = CONSULTA_STATUS[c.status_consulta] ?? { label: c.status_consulta, bg: "bg-slate-100" };
                        return (
                          <tr key={c.id} className="hover:bg-slate-50 transition-colors">
                            <td className="px-4 py-3 font-mono text-xs text-slate-700">
                              {formatarCPF(c.cpf)}
                            </td>
                            <td className="px-4 py-3">
                              <div className="text-sm font-medium text-slate-800">
                                {c.nome_titular || "—"}
                              </div>
                              {c.orgao && (
                                <div className="text-xs text-slate-400 mt-0.5">{c.orgao}</div>
                              )}
                              {c.tipo_vinculo && (
                                <div className="text-xs text-slate-400">{c.tipo_vinculo}</div>
                              )}
                            </td>
                            <td className="px-4 py-3 text-center">
                              <BadgeAutorizacao situacao={c.emprestimo_situacao} />
                            </td>
                            <td className="px-4 py-3 text-center">
                              <BadgeAutorizacao situacao={c.cartao_credito_situacao} />
                            </td>
                            <td className="px-4 py-3 text-center">
                              <BadgeAutorizacao situacao={c.cartao_beneficio_situacao} />
                            </td>
                            <td className={`px-4 py-3 text-right font-semibold ${
                              c.margem_beneficio ? "text-green-700" : "text-slate-300"
                            }`}>
                              {moeda(c.margem_beneficio)}
                            </td>
                            <td className="px-4 py-3">
                              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${sc.bg}`}>
                                {sc.label}
                              </span>
                              {c.mensagem_erro && (
                                <p className="text-xs text-red-500 mt-0.5 max-w-xs truncate" title={c.mensagem_erro}>
                                  {c.mensagem_erro}
                                </p>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                ) : (
                  // ── Tabela GridSoftware (margens em R$) ───────────────────
                  <table className="w-full text-sm min-w-[700px]">
                    <thead className="bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                      <tr>
                        <th className="px-4 py-3 text-left">CPF</th>
                        <th className="px-4 py-3 text-left">Nome / Órgão</th>
                        <th className="px-4 py-3 text-right">Marg. Empréstimo</th>
                        <th className="px-4 py-3 text-right">Marg. Cartão</th>
                        <th className="px-4 py-3 text-left">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {consultasFiltradas.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="text-center py-10 text-slate-400 text-sm">
                            Nenhum resultado para o filtro selecionado.
                          </td>
                        </tr>
                      ) : consultasFiltradas.map((c) => {
                        const sc = CONSULTA_STATUS[c.status_consulta] ?? { label: c.status_consulta, bg: "bg-slate-100" };
                        return (
                          <tr key={c.id} className="hover:bg-slate-50 transition-colors">
                            <td className="px-4 py-3 font-mono text-xs text-slate-700">
                              {formatarCPF(c.cpf)}
                            </td>
                            <td className="px-4 py-3">
                              <div className="text-sm font-medium text-slate-800">
                                {c.nome_titular || "—"}
                              </div>
                              {c.orgao && (
                                <div className="text-xs text-slate-400 mt-0.5">{c.orgao}</div>
                              )}
                            </td>
                            <td className={`px-4 py-3 text-right font-semibold ${
                              c.margem_disponivel ? "text-green-700" : "text-slate-300"
                            }`}>
                              {moeda(c.margem_disponivel)}
                            </td>
                            <td className={`px-4 py-3 text-right ${
                              c.margem_cartao ? "text-blue-700" : "text-slate-300"
                            }`}>
                              {moeda(c.margem_cartao)}
                            </td>
                            <td className="px-4 py-3">
                              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${sc.bg}`}>
                                {sc.label}
                              </span>
                              {c.mensagem_erro && (
                                <p className="text-xs text-red-500 mt-0.5 max-w-xs truncate" title={c.mensagem_erro}>
                                  {c.mensagem_erro}
                                </p>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>

              {/* Exportar */}
              <div className="flex justify-end">
                <button
                  onClick={exportarCSV}
                  className="flex items-center gap-2 text-sm text-slate-600 border border-slate-200 hover:border-blue-300 hover:text-blue-700 hover:bg-blue-50 px-4 py-2 rounded-xl transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Exportar CSV
                </button>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
