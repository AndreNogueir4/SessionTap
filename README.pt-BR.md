<p align="center">
  <img src="extension/static/icons/icon128.png" width="88" alt="SessionTap" />
</p>

<h1 align="center">SessionTap</h1>

<p align="center">
  <b>Entregue a sessão que você já tem no navegador para os seus próprios scripts.</b><br/>
  Localmente, só quando você escolhe, criptografado.
</p>

<p align="center">
  <img alt="Versão" src="https://img.shields.io/badge/vers%C3%A3o-1.0.0-0f766e" />
  <img alt="Licença" src="https://img.shields.io/badge/licen%C3%A7a-Apache--2.0-blue" />
  <img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-3776ab" />
  <img alt="Navegadores" src="https://img.shields.io/badge/navegadores-Chrome%20%C2%B7%20Brave%20%C2%B7%20Edge%20%C2%B7%20Firefox-555" />
  <img alt="Sistemas" src="https://img.shields.io/badge/os-Linux%20%C2%B7%20macOS%20%C2%B7%20Windows-555" />
</p>

<p align="center">
  <a href="README.md">English</a> · <b>Português (Brasil)</b>
</p>

<p align="center">
  <a href="#-instalação">Instalação</a> ·
  <a href="#-uso">Uso</a> ·
  <a href="#-exportações-para-agentes-de-ia">Exportações para IA</a> ·
  <a href="#%EF%B8%8F-configuração">Configuração</a> ·
  <a href="#-como-funciona">Como funciona</a> ·
  <a href="#%EF%B8%8F-segurança">Segurança</a>
</p>

---

Ferramentas de automação gastam a maior parte do esforço *imitando* um humano logado:
login por script, CAPTCHAs, tokens que expiram, headers adivinhados. **O SessionTap pula
tudo isso.** Você faz login normalmente enquanto o SessionTap grava aquela aba, e seus
scripts em Python, Node.js ou shell reaproveitam os seus cookies, tokens e user agent
reais. Ele também mostra todas as chamadas de API que o site faz, gera código para elas e
exporta tudo o que um agente de IA precisa para montar a automação para você.

```python
import sessiontap

client = sessiontap.httpx_client("example.com")   # sua sessão real, carregada na hora de rodar
print(client.get("https://example.com/api/me").json())
```

## ✨ Recursos

| | |
|---|---|
| 🔒 **Seguro por padrão** | API só em loopback e com token, proteção contra DNS rebinding e CSRF, vault criptografado (AES-256-GCM, chave no chaveiro do sistema) e segredos mascarados em todo lugar, a não ser que você peça para ver. |
| ✋ **Opt-in por aba** | Nada é gravado até você clicar em **Gravar esta aba**. A gravação segue logins e redirects entre domínios até você parar. |
| 🚫 **Sua lista de bloqueio** | Sites que nunca podem ser capturados, editáveis pelo dashboard e com trava para uma empresa inteira. |
| 🧩 **Extensão** | Chrome, Brave, Edge e Firefox. Sem telemetria, sem código remoto, sem modificar páginas. |
| 🐍 **SDKs Python e JS** | Helpers para `httpx`, `requests`, `curl_cffi`, Playwright e Puppeteer. |
| 🧪 **Gerador de código** | curl, Python e JavaScript para qualquer requisição capturada. O código carrega os segredos na hora de rodar, então pode ser compartilhado. |
| 🩺 **Saúde da sessão** | Expiração de cookies e JWTs, antes do seu script falhar. |
| 📜 **Exportação OpenAPI** | Inferida do tráfego real, com exemplos reais (mascarados). |
| 📦 **Pacote para IA** | Um .zip com todas as requisições, respostas e páginas HTML completas em ordem, para um agente automatizar sites complexos. |
| 🤖 **Servidor MCP** | Agentes de IA estudam a API e escrevem o script sem nunca ver um segredo. |
| 🔐 **Exportação/importação criptografada** | Leve uma sessão para outra máquina com uma senha. |
| 🌐 **Inglês e português** | Na extensão e no dashboard. |

## 🚀 Instalação

O SessionTap roda direto deste repositório. Nada é publicado no PyPI nem no npm.

**Requisitos:** Git, [Node.js](https://nodejs.org) 20+ e [uv](https://docs.astral.sh/uv/)
(o uv instala o Python 3.11+ para você se precisar).

**1. Clone e compile**

```bash
git clone https://github.com/AndreNogueir4/SessionTap.git
cd SessionTap
npm ci && npm run build            # extensão, dashboard e SDK JS
uv tool install "./core[server]"   # coloca `sessiontap` e `sessiontap-host` no PATH
```

Se o terminal não encontrar o `sessiontap`, rode `uv tool update-shell` e abra um terminal novo.

**2. Inicie o daemon**

```bash
sessiontap install-host      # deixa a extensão falar com o SessionTap (Chrome, Chromium, Brave, Edge, Firefox)
sessiontap start --detach    # http://127.0.0.1:8711, só loopback
```

Use `sessiontap install-host --browser brave` para registrar um navegador só.

**3. Carregue a extensão**

- **Chrome / Brave / Edge:** `chrome://extensions` → *Modo do desenvolvedor* →
  **Carregar sem compactação** → `extension/dist/chromium`
- **Firefox:** `about:debugging` → *Este Firefox* → **Carregar extensão temporária** →
  `extension/dist/firefox/manifest.json`

O popup deve mostrar **Conectado**. A extensão segue o idioma do navegador.

**4. Bloqueie os sites que você nunca quer capturar**

> [!WARNING]
> A lista de bloqueio vem só com um exemplo (`example.block.com`). O SessionTap **não**
> bloqueia sozinho e-mail, bancos, provedores de identidade ou gerenciadores de senha: se
> uma aba gravada passar por um deles (um redirect de "Entrar com Google", por exemplo),
> ele é capturado. Adicione esses sites antes da primeira gravação:
>
> ```bash
> sessiontap blocklist add mail.google.com
> sessiontap blocklist add accounts.google.com
> sessiontap blocklist add login.microsoftonline.com
> ```
>
> Ou use dashboard → **Configurações** → **Lista de bloqueio**, onde você também pode colar
> uma URL. Adicione também o seu banco, os meios de pagamento e as ferramentas internas da
> sua empresa.

## 🧭 Uso

### Grave uma aba

Abra o site, clique no ícone do SessionTap → **Gravar esta aba**, depois faça login e
navegue normalmente. O ícone mostra **REC** e o popup mostra as contagens ao vivo:
requisições, cookies, tokens, valores do storage e todos os sites que a gravação adicionou.

A gravação acompanha a aba: subdomínios, um login em outro domínio (SSO, redirects de
OAuth) e chamadas de API com header `Authorization` são adicionados automaticamente, então
o fluxo inteiro vai para o vault. Anúncios e trackers em iframes não entram. Clique em
**Parar gravação** em qualquer página daquela aba, ou feche a aba, para parar.

### Use a sessão

**Python**: instale o SDK no projeto onde ficam os seus scripts, apontando para o seu clone:

```bash
uv add /caminho/para/SessionTap/core   # ou: pip install /caminho/para/SessionTap/core
```

```python
import sessiontap

client = sessiontap.httpx_client("example.com")                  # cookies + user agent
session = sessiontap.requests_session("example.com")             # precisa de `requests`
session = sessiontap.curl_cffi_session("example.com", "chrome")  # também imita o TLS do navegador

s = sessiontap.session("example.com")
s.cookies, s.user_agent, s.local_storage(), s.cookie_header()
token = sessiontap.secret("example.com", "authorization")        # último valor capturado do header

context.add_cookies(sessiontap.playwright_cookies("example.com"))  # Playwright
```

**Node.js**: depois do `npm run build` no clone, instale o SDK no seu projeto:

```bash
npm install /caminho/para/SessionTap/sdk/js
```

```js
import { SessionTap } from "sessiontap";

const tap = new SessionTap();   // lê o token local, sem configuração
const res = await fetch("https://example.com/api/me", { headers: await tap.headers("example.com") });

await context.addCookies(await tap.playwrightCookies("example.com"));   // Playwright
await page.setCookie(...(await tap.puppeteerCookies("example.com")));   // Puppeteer
const auth = await tap.secret("example.com", "authorization");
```

**Shell**

```bash
curl -H "Cookie: $(sessiontap cookie-header example.com)" https://example.com/api/me
curl -H "Authorization: $(sessiontap secret example.com authorization)" https://api.example.com/me
```

Os dois SDKs leem o token do diretório do SessionTap e se recusam a falar com qualquer
endereço que não seja `127.0.0.1`.

### Dashboard

```bash
sessiontap open
```

Ele abre já autenticado e mostra os sites capturados, cada requisição com headers e
corpos, a sessão (cookies, tokens, storage) com revelar e copiar, um feed ao vivo, a
saúde da sessão, a visão da API com as exportações e as configurações. Cada requisição tem
um painel **Código** que gera curl, Python ou JavaScript para ela. Por padrão o código não
tem segredos e carrega tudo pelo SDK na hora de rodar.

<details>
<summary><b>Todos os comandos da CLI</b></summary>

| Comando | O que faz |
|---|---|
| `sessiontap start [--detach]` · `stop` · `status` | Inicia, para e mostra o estado do daemon |
| `sessiontap open` | Abre o dashboard já autenticado |
| `sessiontap token` | Mostra o caminho do token, o token, ou gera um novo |
| `sessiontap install-host` · `uninstall-host` | Registra ou remove o native host dos navegadores |
| `sessiontap capture list\|allow\|deny` | Lista os sites capturados, ou liga/desliga a captura de um |
| `sessiontap blocklist list\|add\|remove\|reset` | Gerencia os sites que nunca podem ser capturados |
| `sessiontap cookie-header <domínio>` | Mostra o header `Cookie` de um site |
| `sessiontap secret <domínio> <header>` | Mostra o último valor capturado de um header de credencial |
| `sessiontap openapi <domínio>` | Grava a descrição OpenAPI inferida |
| `sessiontap bundle <domínio>` | Grava o pacote para IA (.zip) |
| `sessiontap export` · `import` | Arquivo de sessão criptografado com senha |
| `sessiontap purge --domain <d>` · `--all` | Apaga os dados de um site, ou o vault inteiro e a chave |
| `sessiontap mcp` | Roda o servidor MCP (stdio) para agentes de IA |

</details>

## 🤖 Exportações para agentes de IA

Duas exportações foram feitas para escrever automações, normalmente com um agente de IA.
As duas mascaram as credenciais: o código que o agente escreve carrega tudo pelo SDK na
hora de rodar.

| | OpenAPI | Pacote para IA (.zip) |
|---|---|---|
| **Melhor para** | Sites simples com API JSON | Sites complexos, HTML renderizado no servidor, fluxos com várias etapas |
| **Contém** | Endpoints, parâmetros, schemas e um exemplo real por resposta | Tudo do OpenAPI, mais todas as requisições e respostas em ordem e o HTML completo de cada página |
| **Dashboard** | Site → **API** → **Baixar OpenAPI** | Site → **API** → **Baixar pacote para IA (.zip)** |
| **CLI** | `sessiontap openapi example.com` | `sessiontap bundle example.com` |

**OpenAPI 3.1**: as URLs viram templates (`/users/123/orders` → `/users/{userId}/orders`),
os schemas juntam todas as chamadas observadas e os exemplos vêm de respostas reais
(listas cortadas em 3 itens, textos longos em 300 caracteres, credenciais trocadas por
`****`). Abre no Swagger UI, Redoc, Postman, Insomnia e Bruno.

**Pacote para IA**

```
example.com-sessiontap.zip
├── README.md        instruções para o agente: arquivos, como autenticar, regras
├── openapi.json     o OpenAPI acima
├── timeline.json    todas as requisições em ordem, com links para os arquivos
├── session.json     nomes de cookies, tipos de token, chaves do storage, perfil do navegador (sem valores)
└── endpoints/
    └── GET_api.example.com_users_{userId}_orders/
        ├── 0007.json              URL, headers (mascarados), status, tempos
        ├── 0007.request.json      corpo da requisição, se houver
        └── 0007.response.json     corpo completo da resposta (.html para páginas)
```

`0007` é a posição no `timeline.json`, então o agente consegue seguir um fluxo: qual
resposta definiu um cookie ou devolveu um token CSRF, e qual requisição depois usou ele.

**Páginas HTML completas**: no Chromium, o SessionTap guarda o HTML completo de cada página
principal que uma aba gravada carrega, com um teto de segurança de 100 MiB por página.
Iframes (anúncios, widgets) ficam de fora. Desligue em **Configurações** → **Captura**.

> [!CAUTION]
> As credenciais são mascaradas, mas corpos de resposta e principalmente páginas HTML podem
> conter dados pessoais e tokens embutidos (um token CSRF numa tag `<meta>`, por exemplo).
> Revise o pacote antes de compartilhar.

**Exemplo de prompt**

> Leia o pacote do SessionTap em anexo. Escreva um script Python que liste meus pedidos em
> aberto (id, data, total) em CSV. Use `sessiontap.httpx_client("example.com")` para a
> sessão e nunca coloque cookies ou tokens no código. Siga o `timeline.json` para ver como
> o site carrega a página de pedidos.

### Servidor MCP

Deixe um agente explorar o que você capturou pelo
[Model Context Protocol](https://modelcontextprotocol.io):

```bash
uv tool install --reinstall "./core[server,mcp]"   # na pasta do seu clone
```

```json
{
  "mcpServers": {
    "sessiontap": { "command": "sessiontap", "args": ["mcp"] }
  }
}
```

Ferramentas: `list_domains`, `session_health`, `list_requests`, `get_request`,
`generate_code` e `openapi_spec`. O servidor é **somente leitura** e **nunca retorna
cookies ou tokens em claro**. O agente consegue escrever código que funciona, mas as
credenciais só existem quando *você* roda esse código.

## ⚙️ Configuração

Tudo fica no diretório do SessionTap (mude com `SESSIONTAP_HOME`):

| Sistema | Padrão |
|---|---|
| Linux | `~/.local/share/sessiontap` |
| macOS | `~/Library/Application Support/sessiontap` |
| Windows | `%LOCALAPPDATA%\sessiontap` |

`config.toml` opcional nesse diretório:

```toml
[server]
port = 8711              # o daemon sempre escuta em 127.0.0.1

[vault]
key_backend = "auto"     # auto | keyring | file

[capture]
max_body_kb = 512        # maior corpo de requisição/resposta de API salvo (0–4096)
html = true              # guardar o HTML completo das páginas (até 100 MiB cada)
blocklist = ["mail.google.com", "accounts.google.com", "paypal.com"]   # lista de bloqueio inicial
locked = false           # true: as opções de [capture] não podem ser mudadas em uso
```

Variáveis de ambiente: `SESSIONTAP_PORT`, `SESSIONTAP_KEY_BACKEND`, `SESSIONTAP_HOME`.

O dashboard (**Configurações**), a CLI e a API mudam a retenção, a captura de HTML, o
maior corpo salvo e a lista de bloqueio sem reiniciar. Adicionar um site à lista de
bloqueio para a captura dele na hora. Os dados capturados antes continuam salvos; apague em
**Configurações** → **Sites**.

**Máquinas gerenciadas por empresas**: com `locked = true`, o `config.toml` é a única fonte
de verdade. O dashboard, a CLI e a API se recusam a editar a lista de bloqueio e as opções
de captura (403). Proteja o próprio arquivo com as ferramentas de sempre (permissões de
arquivo, MDM).

## 🧩 Como funciona

```
 Navegador                                  Sua máquina (seu usuário)
┌──────────────────────────────┐          ┌───────────────────────────────────────────────┐
│ Extensão SessionTap (MV3)    │  stdio   │ sessiontap-host          daemon sessiontap    │
│  • popup: opt-in por aba     │◄────────►│  (iniciado pelo    HTTP   (FastAPI, 127.0.0.1) │
│  • captura CDP / webRequest  │  native  │   navegador)      ──────►  • portão de segurança│
│  • cookies, storage, perfil  │ messaging│                   token    • ingestão + vault  │
└──────────────────────────────┘          │                            • API, feed, UI     │
                                          │                                  │             │
     Seus scripts ── SDK (token) ────────►│                                  ▼             │
     Agentes de IA ── MCP (token) ───────►│                         vault.db (SQLite,      │
     Dashboard ───── navegador (token) ──►│                         AES-GCM por campo)     │
                                          └───────────────────────────────────────────────┘
```

1. Você clica em **Gravar esta aba**. A extensão ativa aquele site no daemon e se conecta
   à aba (Chromium: protocolo do DevTools, para headers, corpos e HTML; Firefox:
   `webRequest`, para headers).
2. Quando a aba navega para outro site, ou chama um com header `Authorization`, esse site
   entra na gravação. Parar (ou fechar a aba) desativa todos os sites que ela adicionou.
3. As requisições terminadas vão em lotes a cada segundo, por native messaging, para o
   `sessiontap-host`, que valida e repassa ao daemon com o token.
4. O daemon confere cada evento contra os sites ativados e a lista de bloqueio, corta
   corpos grandes demais, criptografa os campos secretos, extrai tokens e atualiza o feed
   ao vivo.
5. Seu script chama `sessiontap.httpx_client("example.com")`. O SDK lê o arquivo do token
   e pede a sessão para o daemon.

## 🛡️ Segurança

O SessionTap guarda a coisa mais valiosa que o seu navegador tem: sessões logadas. O
projeto original respondia `fetch("http://localhost:8080/api/v1/session/all")` de qualquer
página. O SessionTap foi construído para isso não acontecer.

| Quem poderia atacar | Defesa |
|---|---|
| **Um site que você visita** | Nenhum header CORS. Toda rota exige um token de 256 bits que as páginas não têm como saber. Escritas precisam ser JSON, e um `Origin` estranho ou `Sec-Fetch-Site: cross-site` é recusado (CSRF). O `Host` precisa ser loopback (DNS rebinding). Falhas de autenticação são limitadas. O dashboard não pode ser colocado em iframe e tem CSP estrita. |
| **Um dispositivo na sua rede** | O daemon só escuta em `127.0.0.1`, e isso não é configurável. |
| **Outra extensão** | Só o ID fixo da extensão do SessionTap pode iniciar o native host; mensagens de páginas e de outras extensões são ignoradas. |
| **Uma página que você está capturando** | Limites de tamanho por mensagem, validação estrita de cada evento, corpos cortados em `max_body_kb`, e o código gerado escapa cada valor. |
| **Captura acidental** | Nada é capturado até você gravar uma aba, o daemon confere cada evento, e a lista de bloqueio sempre vence. O Chromium mostra a barra "começou a depurar este navegador" e o ícone mostra **REC**. |
| **Recursos de conveniência** | Credenciais mascaradas a não ser que você revele, código gerado sem segredos, servidor MCP somente leitura, só resumos no feed ao vivo, código de login de uso único válido por 60 segundos no `sessiontap open`, sem log de acesso. |
| **Outro usuário no computador** | Diretório `0700`; token, chave e vault `0600`. |
| **Cadeia de suprimentos** | Lockfiles, Dependabot, CodeQL, gitleaks no pre-commit e no CI, GitHub Actions fixadas por SHA de commit, e uma extensão sem minificação que você pode ler. |

<details>
<summary><b>O que é guardado, e o que não é protegido</b></summary>

**Guardado:** cookies, headers de autenticação, tokens, valores do Web Storage, URLs,
headers e corpos são criptografados por campo no `vault.db`. A chave do vault fica no
chaveiro do sistema (alternativa `vault.key`, `0600`). Domínios, caminhos de URL, status e
*nomes* de cookies ficam em claro para poderem ser listados e pesquisados.

**Fora do escopo:**

- **Malware rodando com o seu usuário.** Ele consegue ler o próprio banco de cookies do
  navegador com a mesma facilidade. Com a **chave em arquivo** (sem chaveiro, por exemplo
  Linux sem interface), ele consegue descriptografar o vault direto; o `sessiontap status`
  e o dashboard avisam sobre isso.
- **O que você faz com uma sessão.** APIs não documentadas, limites de requisição e termos
  de uso são responsabilidade sua.
- **Bugs do navegador** no native messaging, no `chrome.debugger` ou nos pedidos de
  permissão.

</details>

<details>
<summary><b>Permissões da extensão</b></summary>

| Permissão | Por quê |
|---|---|
| `nativeMessaging` | Falar com o `sessiontap-host`, o único caminho pelo qual dados saem da extensão. |
| `activeTab` | Ler o endereço da aba atual quando você abre o popup. |
| `debugger` (Chromium) | Ler headers, corpos de API e o HTML completo pelo DevTools, só em abas gravadas. |
| `webRequest` (Firefox) | Ler headers de requisição e resposta em sites ativados. |
| `cookies` | Tirar um snapshot e acompanhar mudanças nos cookies dos sites ativados. |
| `scripting` | Ler localStorage/sessionStorage e o perfil do navegador em sites ativados. |
| `storage` | Lembrar quais abas estão sendo gravadas (apagado quando o navegador fecha). |
| Acesso a sites (todos) | Concedido uma vez na instalação, para a gravação seguir um fluxo entre domínios sem pedir permissão a cada site. Nada é lido de um site até você gravá-lo. |

A extensão não faz nenhuma requisição de rede (sem analytics, sem telemetria, sem código
remoto) e nunca modifica as páginas.

</details>

## 🔄 Atualizar e desinstalar

```bash
# atualizar
git pull
npm ci && npm run build
uv tool install --reinstall "./core[server]"
sessiontap stop && sessiontap start --detach   # depois recarregue a extensão

# desinstalar
sessiontap stop
sessiontap purge --all          # apaga o vault e a chave dele
sessiontap uninstall-host
uv tool uninstall sessiontap
```

## 🩹 Problemas comuns

| Mensagem | Solução |
|---|---|
| Popup: "Rode `sessiontap install-host`" | `sessiontap install-host` e depois recarregue a extensão |
| Popup: "Daemon desligado" | `sessiontap start --detach` |
| Popup: botão de gravar desativado em um site | O site está na sua lista de bloqueio. Remova em **Configurações** → **Lista de bloqueio** se realmente precisar. |
| Dashboard: "A chave do vault está em um arquivo" | Nenhum chaveiro do sistema encontrado. Instale GNOME Keyring ou KWallet e rode `sessiontap purge --all`. |

## 📁 Repositório

| Caminho | O quê |
|---|---|
| [`core/`](core) | Pacote Python: daemon, CLI, native host, SDK, servidor MCP |
| [`extension/`](extension) | Extensão do navegador (TypeScript, Manifest V3) |
| [`dashboard/`](dashboard) | Interface web (React + Vite), compilada para dentro do pacote Python |
| [`sdk/js/`](sdk/js) | SDK JavaScript |
| [`CHANGELOG.md`](CHANGELOG.md) | O que mudou em cada versão (em inglês) |

## ⚖️ Uso responsável

O SessionTap é para **as suas próprias contas e dados**. Respeite os termos de uso e os
limites de requisição dos sites. Não use para acessar contas de outras pessoas nem para
contornar controles de acesso. APIs não documentadas mudam sem aviso.

## 🤝 Contribuindo e segurança

Contribuições são bem-vindas, inclusive traduções. Comece pelo
[CONTRIBUTING.md](CONTRIBUTING.md). Por favor, **não abra uma issue pública para problemas de
segurança**: reporte de forma privada na aba **Security** do repositório → **Report a
vulnerability**.

## 📄 Créditos e licença

O SessionTap é uma reescrita do zero inspirada no
[SCRAPY / SCRAPPER](https://github.com/BunElysiaReact/SCRAPY) de Ernest Pease.

Licenciado sob a [Apache License 2.0](LICENSE).
