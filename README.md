# ConsultaMargem — Sistema de Consulta em Lote de Margem Consignada

Sistema full-stack para consulta em lote de margem consignada via portais bancários reais.
Upload de CSV com CPFs → processamento assíncrono (Celery) → resultados em tempo real (React).

---

## Arquitetura do Sistema

```
┌─────────────┐     POST /upload-lote/      ┌─────────────────┐
│  React UI   │ ──────────────────────────► │   FastAPI API   │
│  (Nginx)    │                             │   (backend)     │
│             │ ◄────── polling 3s ──────── │                 │
└─────────────┘   GET /status-lote/{id}     └────────┬────────┘
                                                     │ Celery task
                                            ┌────────▼────────┐
                                            │  Celery Worker  │
                                            │                 │
                                            │ AdapterManager  │
                                            │  ┌──────────┐   │
                                            │  │   aki    │   │  AkiCapital
                                            │  │   grid   │   │  GridSoftware
                                            │  │ exemplo  │   │  Simulador
                                            │  └──────────┘   │
                                            └────────┬────────┘
                                                     │
                                            ┌────────▼────────┐
                                            │   PostgreSQL    │
                                            └─────────────────┘
```

## Estrutura de Pastas

```
consulta-margem-lote/
├── backend/
│   ├── app/
│   │   ├── scraper/                  ← Pacote modular de adaptadores
│   │   │   ├── __init__.py           ← Auto-registro + API pública
│   │   │   ├── base_adapter.py       ← BaseScraperAdapter (Playwright + sessão)
│   │   │   ├── manager.py            ← AdapterManager (registry + fábrica)
│   │   │   ├── captcha.py            ← TwoCaptchaSolver (reCAPTCHA v2)
│   │   │   ├── utils.py              ← Utilitários compartilhados
│   │   │   ├── akicapital_adapter.py ← Portal AkiCapital (REAL)
│   │   │   ├── gridsoftware_adapter.py ← GridSoftware/Roraima (REAL)
│   │   │   └── exemplo_adapter.py    ← Simulador para testes
│   │   ├── main.py                   ← FastAPI — rotas e endpoints
│   │   ├── models.py                 ← SQLAlchemy — Lote, Consulta, Usuario
│   │   ├── schemas.py                ← Pydantic — validação e serialização
│   │   ├── crud.py                   ← Operações no banco de dados
│   │   ├── database.py               ← Conexão PostgreSQL
│   │   ├── auth.py                   ← JWT — autenticação
│   │   ├── celery_app.py             ← Configuração do Celery
│   │   ├── tasks.py                  ← Tarefa processar_lote
│   │   └── config.py                 ← Configurações via variáveis de ambiente
│   ├── .env                          ← Credenciais reais (não commitar!)
│   ├── .env.example                  ← Template
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── api.js
│   │   └── components/
│   │       ├── UploadLote.jsx
│   │       ├── StatusLote.jsx
│   │       └── HistoricoLotes.jsx
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
└── cpfs_exemplo.csv
```

---

## Portais Disponíveis

| Chave      | Portal                      | reCAPTCHA | Status    |
|------------|-----------------------------|-----------|-----------| 
| `exemplo`  | Simulador (sem portal real) | Não       | Ativo     |
| `aki`      | AkiCapital                  | Não       | Ativo     |
| `grid`     | GridSoftware / Roraima      | Sim       | Ativo     |
| `bv`       | RF1Consig / Boa Vista       | Imagem    | Ativo     |

---

## Instalação e Execução

### Pré-requisitos
- Docker Desktop 24+
- Docker Compose v2

### 1. Subir todos os serviços

```bash
cd consulta-margem-lote
docker compose up --build
```

### 2. Acessar

| URL                           | Descrição                |
|-------------------------------|--------------------------|
| http://localhost              | Interface web (React)    |
| http://localhost:8000/docs    | Swagger UI da API        |
| http://localhost:5555         | Flower (monitor Celery)  |

---

## Uso — API

### Listar adaptadores disponíveis

```bash
curl http://localhost:8000/adaptadores/
# {"adaptadores": ["aki", "bv", "exemplo", "grid"]}
```

### Upload de lote

```bash
# Portal simulado (para testes)
curl -X POST "http://localhost:8000/upload-lote/?banco=exemplo" \
  -F "arquivo=@cpfs_exemplo.csv"

# AkiCapital
curl -X POST "http://localhost:8000/upload-lote/?banco=aki" \
  -F "arquivo=@cpfs.csv"

# GridSoftware / Roraima
curl -X POST "http://localhost:8000/upload-lote/?banco=grid" \
  -F "arquivo=@cpfs.csv"

# RF1Consig / Prefeitura de Boa Vista
curl -X POST "http://localhost:8000/upload-lote/?banco=bv" \
  -F "arquivo=@cpfs.csv"
```

Resposta:
```json
{
  "lote_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "mensagem": "Lote aceito. 100 CPFs em processamento.",
  "total_cpfs": 100
}
```

### Verificar status (polling)

```bash
curl "http://localhost:8000/status-lote/3fa85f64-5717-4562-b3fc-2c963f66afa6"
```

Resposta:
```json
{
  "id": "3fa85f64...",
  "status": "processando",
  "total_cpfs": 100,
  "processados": 42,
  "sucessos": 38,
  "erros": 4,
  "progresso_pct": 42.0,
  "consultas": [
    {
      "cpf": "12345678901",
      "nome_titular": "FULANO DA SILVA",
      "margem_disponivel": 1250.00,
      "margem_cartao": 375.00,
      "banco": "AkiCapital",
      "status_consulta": "sucesso"
    }
  ]
}
```

---

## Formato do CSV

```csv
cpf
12345678909
98765432100
11144477735
```

- Apenas coluna `cpf` é obrigatória
- CPF com ou sem formatação (123.456.789-09 ou 12345678909)
- Limite: 5.000 CPFs por lote

---

## Robô local Boa Vista (Excel no computador)

Para rodar sem abrir a interface web, use o script `backend/robo_boa_vista_excel.py`. Ele abre o Chromium pelo Playwright em modo automático, faz login no RF1Consig, resolve o código de segurança via 2Captcha, consulta cada CPF ou matrícula e grava as colunas de resultado na planilha de saída.

### Preparar o ambiente local

```bash
cd consulta-margem-lote
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
pip install -r backend/requirements.txt
python -m playwright install chromium
```

O RF1Consig de Boa Vista usa código de segurança/CAPTCHA no login. Para o robô trabalhar sozinho, configure obrigatoriamente uma chave 2Captcha em `TWOCAPTCHA_API_KEY` no `backend/.env`/ambiente ou informe a chave pelo parâmetro `--twocaptcha-api-key`. Sem essa chave, o script interrompe antes de iniciar porque não há etapa manual.

### Formato da planilha

A planilha pode ser `.xlsx`, `.xlsm`, `.xls` ou `.csv` e precisa conter uma destas colunas:

- `cpf`
- `matricula` / `matrícula`
- `identificador`

### Executar

```bash
python backend/robo_boa_vista_excel.py \
  --arquivo servidores.xlsx \
  --login 00000000000 \
  --senha SUA_SENHA \
  --twocaptcha-api-key SUA_CHAVE_2CAPTCHA
```

Por padrão, o robô usa a página de consulta/listagem da Prefeitura de Boa Vista:

```text
https://boavista.rf1consig.com.br/SGConsignataria/GESTOR/CADPessoaListar.aspx
```

O arquivo de saída será criado ao lado do original com o sufixo `_resultado`, por exemplo `servidores_resultado.xlsx`. Para escolher outro local:

```bash
python backend/robo_boa_vista_excel.py \
  --arquivo servidores.xlsx \
  --saida resultado_boa_vista.xlsx \
  --login 00000000000 \
  --senha SUA_SENHA \
  --twocaptcha-api-key SUA_CHAVE_2CAPTCHA
```

Colunas gravadas no resultado:

- `margem_emprestimo`
- `margem_cartao_consignado`
- `margem_cartao_beneficio`
- `nome_titular`, `orgao`, `matricula_resultado`, `tipo_vinculo`
- `status_consulta` e `mensagem_erro`

---

## Como Adicionar um Novo Adaptador

### 1. Criar o arquivo do adaptador

```python
# backend/app/scraper/meu_banco_adapter.py

from app.scraper.base_adapter import BaseScraperAdapter
from app.scraper.manager import AdapterManager
from app.scraper.utils import formatar_cpf, pausa_humana, digitar_lento, parse_moeda
from app.config import settings


@AdapterManager.registrar("meubanco")   # ← chave usada no ?banco=
class MeuBancoAdapter(BaseScraperAdapter):
    NOME_BANCO   = "Meu Banco"
    CHAVE_SESSAO = "meu_banco"          # nome do arquivo de sessão em disco
    URL_LOGIN    = "https://portal.meubanco.com.br/login"

    def _esta_logado(self, page) -> bool:
        """Retorna True se a sessão está ativa."""
        return "login" not in page.url.lower()

    def _fazer_login(self, page) -> None:
        """Autentica no portal. Chamado apenas quando a sessão expirar."""
        page.goto(self.URL_LOGIN, wait_until="networkidle")
        pausa_humana()
        digitar_lento(page, "#usuario", settings.AKICAPITAL_LOGIN)
        digitar_lento(page, "#senha",   settings.AKICAPITAL_SENHA)
        page.click("#entrar")
        page.wait_for_url("**/home**")

    def _extrair_margem(self, page, cpf: str) -> dict:
        """Navega à consulta, insere CPF e extrai os valores."""
        # Navegação
        page.goto("https://portal.meubanco.com.br/margem")
        page.wait_for_load_state("networkidle")
        pausa_humana()

        # Inserção do CPF
        digitar_lento(page, "#cpf", formatar_cpf(cpf))
        page.click("#consultar")
        page.wait_for_selector("#resultado", timeout=30_000)

        return {
            "cpf":               cpf,
            "status_consulta":   "sucesso",
            "mensagem_erro":     None,
            "nome_titular":      page.text_content("#nome"),
            "margem_disponivel": parse_moeda(page.text_content("#margem")),
            "margem_cartao":     parse_moeda(page.text_content("#cartao")),
            "margem_beneficio":  None,
            "banco":             self.NOME_BANCO,
            "orgao":             page.text_content("#orgao"),
            "dados_brutos":      None,
        }
```

### 2. Registrar no `__init__.py`

```python
# backend/app/scraper/__init__.py — adicionar linha:
from app.scraper.meu_banco_adapter import MeuBancoAdapter  # noqa: F401
```

### 3. Adicionar variáveis de ambiente (se necessário)

```bash
# backend/.env
MEU_BANCO_LOGIN=usuario
MEU_BANCO_SENHA=senha
```

```python
# backend/app/config.py — adicionar ao Settings:
MEU_BANCO_LOGIN: str = ""
MEU_BANCO_SENHA: str = ""
```

### 4. Para portais com reCAPTCHA

```python
from app.scraper.captcha import TwoCaptchaSolver

def _fazer_login(self, page) -> None:
    # ... preenche credenciais ...
    
    # Resolve reCAPTCHA automaticamente
    solver = TwoCaptchaSolver()
    sitekey = solver.extrair_sitekey(page)
    if sitekey:
        token = solver.resolver(sitekey=sitekey, page_url=page.url)
        solver.injetar_token(page, token)
    
    page.click("#submit")
```

---

## Variáveis de Ambiente

| Variável                      | Descrição                                          |
|-------------------------------|----------------------------------------------------|
| `DATABASE_URL`                | Connection string PostgreSQL                       |
| `REDIS_URL`                   | URL do Redis (broker Celery)                       |
| `SECRET_KEY`                  | Chave JWT (trocar em produção!)                    |
| `AKICAPITAL_URL`              | URL de login AkiCapital (com FISession)            |
| `AKICAPITAL_LOGIN`            | Usuário AkiCapital                                 |
| `AKICAPITAL_SENHA`            | Senha AkiCapital                                   |
| `GRID_URL`                    | URL de login GridSoftware                          |
| `GRID_LOGIN`                  | CPF do operador GridSoftware                       |
| `GRID_SENHA`                  | Senha GridSoftware                                 |
| `TWOCAPTCHA_API_KEY`          | Chave da API 2captcha.com                          |
| `TWOCAPTCHA_TIMEOUT_S`        | Timeout de resolução de CAPTCHA (padrão: 120s)     |
| `SESSION_DIR`                 | Diretório de sessões Playwright no container       |

---

## Endpoints da API

| Método | Rota                        | Descrição                            |
|--------|-----------------------------|--------------------------------------|
| GET    | `/adaptadores/`             | Lista adaptadores disponíveis        |
| POST   | `/upload-lote/?banco=`      | Upload CSV → cria lote e inicia fila |
| GET    | `/status-lote/{lote_id}`    | Status + resultados (paginado)       |
| GET    | `/lotes/`                   | Histórico de lotes                   |
| POST   | `/auth/registrar`           | Criar usuário                        |
| POST   | `/auth/login`               | Obter token JWT                      |
| GET    | `/auth/me`                  | Dados do usuário logado              |
| GET    | `/health`                   | Healthcheck                          |

---

## Sessões Persistentes

O sistema reutiliza sessões de browser entre CPFs do mesmo worker para
evitar login repetido a cada consulta. As sessões ficam em `/tmp/pw_sessions/`
(volume compartilhado entre backend e worker):

```
/tmp/pw_sessions/
├── akicapital.json      ← Sessão AkiCapital
├── grid_roraima.json    ← Sessão GridSoftware
└── erro_aki_1234.png    ← Screenshots de erros (diagnóstico)
```

Se o portal rejeitar a sessão (expirada ou bloqueada), o sistema
invalida o arquivo e faz novo login automaticamente na próxima consulta.

---

## Modo Desenvolvimento

```bash
# Frontend com hot-reload na porta 5173
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

---

## Considerações de Produção

1. **Credenciais**: mova as senhas para variáveis de ambiente injetadas pelo
   orquestrador (Docker Swarm secrets, Kubernetes secrets, etc.) — nunca commite `.env`.
2. **Rate limiting**: adicione delays entre consultas para cada portal específico.
3. **Proxy rotativo**: para scraping em alta escala, use proxies residenciais.
4. **HTTPS**: configure certificado SSL no Nginx antes de expor ao público.
5. **Backup**: habilite replicação do PostgreSQL e snapshots regulares.
6. **LGPD**: dados de CPF e margem são sensíveis — implemente política de
   retenção e exclusão conforme exigido pela lei.
