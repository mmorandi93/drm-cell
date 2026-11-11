# Relatório de segurança — DRM Cell (site + Área do dono)

Data: 10/11/2026. Escopo: este repositório (`index.html`, `calculadora/`, `api/`, `auth.py`, `calculo.py`).
Referência: OWASP Top 10 e ASVS (nível básico). **Este relatório não declara o projeto "seguro":** ele lista o que foi
corrigido, como foi testado e o que ainda depende de você.

## 1. Auditoria inicial (antes de alterar)

| # | Achado | Gravidade |
|---|--------|-----------|
| A1 | Login sem limite de tentativas (força bruta) | Alta |
| A2 | Sem 2FA: só e-mail + senha protegiam o histórico de preços | Alta (**decisão do dono: 2FA não será usado**) |
| A3 | Sem cabeçalhos de segurança nem CSP; JS e CSS embutidos na página | Média |
| A4 | Entradas sem validação no servidor: aceitava negativos, `NaN`, `Infinity`, textos de qualquer tamanho; corpo sem limite | Média |
| A5 | Mensagens de erro do login revelavam configuração ("Faltam variáveis…", código do Supabase) | Média |
| A6 | Exportação CSV vulnerável a injeção de fórmulas (`=`, `+`, `-`, `@` no campo Modelo) | Média |
| A7 | Sem log de eventos de segurança nem como detectar ataques | Média |
| A8 | Sem backup nem teste de restauração | Média |
| A9 | `esc()` do front não escapava `>` e aspas | Baixa |
| A10 | Logout só apagava o token do navegador; o token seguia válido no servidor | Baixa |
| A11 | Rota de histórico dava erro 500 com banco novo (tabela inexistente) | Baixa (bug) |
| A12 | Qualquer pessoa autenticada tinha todos os poderes (sem perfis) | Baixa |

Pontos que já estavam corretos: consultas SQL parametrizadas, token validado no servidor a cada requisição,
nenhum segredo no código ou no histórico do git (verificado com busca), RLS ligado nas tabelas, `.env*` ignorado.

## 2. Correções feitas

| Requisito | O que foi feito | Onde |
|-----------|-----------------|------|
| 1. Rotas privadas | Toda rota `/api/calcular` e `/api/historico` exige token válido, verificado no servidor | `seguranca.py` (`exigir`), `auth.py` |
| 2. Autenticação | E-mail + senha via Supabase; token validado no servidor a cada requisição. **2FA removido a pedido do dono** (era a única barreira extra contra senha vazada) | `auth.py`, `api/login.py` |
| 3. Hash de senha | Senhas ficam no Supabase Auth (bcrypt). O projeto não guarda nem registra senhas | — |
| 4. Perfis | `dono` (calcula e vê histórico) e `leitura` (só histórico, via `VIEWER_EMAILS`) | `auth.py` (`PERMISSOES`) |
| 5. Banco | RLS ligado em `calculos` e `eventos_seguranca` (a chave pública do Supabase não lê as tabelas); logs apagados após 90 dias | `calculo.py`, `seguranca.py` |
| 6–7. Validação / injeções | Números: tipo, finitos, faixa 0–100.000; texto sem `<`/`>`/controle, limite de tamanho; qualidade só da lista; corpo máx. 4 KB; só `application/json`. SQL parametrizado. Front escapa `& < > " '`. CSP bloqueia scripts injetados. CSRF: token no cabeçalho (não em cookie) + rejeição de `Origin` de outro site | `seguranca.py`, `calculo.py`, `app.js` |
| 8. Segredos | Nada de chave no front (varredura automática). Variáveis só na Vercel | testes |
| 9. Rate limit | Login: 5 falhas/15 min por IP (HTTP 429). Código 2FA: 5 falhas/15 min. API: 60 req/min por IP | `seguranca.py` |
| 10. Logs | Eventos `login_falha`, `login_bloqueado`, `mfa_falha`, `acesso_negado`, `permissao_negada`, `rate_limit_api`, `erro_interno`… em stdout (logs da Vercel) e na tabela `eventos_seguranca`. IP guardado só como hash; nunca senha/token/e-mail | `seguranca.py` |
| 11. Backup | `backup.py` (SQLite e Postgres) + rotina diária no GitHub Actions com **criptografia** e restauração de teste | `backup.py`, `docs/backup.yml.exemplo` (mover para `.github/workflows/backup.yml` após `gh auth refresh -s workflow`) |
| 12. Dependências | `psycopg2-binary 2.9.10`: **0 vulnerabilidades conhecidas** (consulta OSV). Única dependência | — |
| 13. Cabeçalhos | HSTS, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, COOP, CSP (na calculadora sem `unsafe-inline`), `no-store` nas rotas privadas | `vercel.json` |
| 14. Erros | Respostas genéricas; detalhes só no log do servidor; 405 em JSON; sem stack trace | `seguranca.py` |
| 15. LGPD | Ver seção 4 | — |

Funcionalidades existentes mantidas: calculadora, lista de valores, ordenar/filtrar/exportar CSV, site institucional.
(O fluxo de login agora tem a etapa do 2FA; o e-mail/senha continuam os mesmos.)

## 3. Evidências dos testes

`python -m unittest discover -s tests` → **22 testes, todos passando** (Supabase simulado + SQLite temporário). Cobrem:

- Sem token / token inválido / token forjado com aal2 falso → **401**.
- 5 senhas erradas → 6ª tentativa **429**, mesmo com a senha certa; outro IP não é afetado.
- Mensagem idêntica para e-mail inexistente e senha errada; sem a palavra "Supabase" na resposta.
- Perfil `leitura` vê histórico (200) e é barrado em calcular (**403**).
- Logout revoga o token no servidor (depois, 401).
- 63 requisições seguidas → aparece **429**.
- Entradas inválidas (negativo, texto, booleano, 1e12, `NaN`, `Infinity`, qualidade inválida, JSON malformado, array, corpo de 10 KB, `text/plain`) → **400**.
- `Origin` de site externo → **403**; origem própria → 200.
- SQL injection (`'); DROP TABLE…`) e `<script>`: a tabela continua existindo e `<`/`>` são removidos.
- Erro interno forçado com "senha" na mensagem: resposta **500 genérica** sem vazar nada.
- Logs gravados sem senha, sem e-mail e sem IP puro.
- `vercel.json`: cabeçalhos presentes; CSP da calculadora sem `unsafe-inline`/`unsafe-eval`; hash do script do site confere; front sem handlers inline e sem segredos; `.gitignore` protege `.env`, `*.db`, `backups/`.

Testes no navegador (servidor local aplicando o `vercel.json`):
- `/calculadora/` carrega com CSP ativa e sem erros; tentativas de `<script>` inline, `onerror=` e script externo foram **bloqueadas** (violações `script-src-elem`/`script-src-attr`).
- Site público carrega com CSP, imagens do Unsplash aparecem, script inline por hash funciona, injeção bloqueada.

Backup: `python backup.py testar` → original `{calculos: 3}`, restaurado `{calculos: 3}`, integridade OK.

## 4. LGPD

- A calculadora guarda apenas modelo do aparelho, tipo de tela e valores. **Não há dados pessoais de clientes** no banco.
- Os logs usam IP em hash (com sal `LOG_SALT`) e são apagados após 90 dias.
- O site público não coleta dados (sem formulário, cookies ou analytics). WhatsApp e Instagram são serviços de terceiros.
- Se um dia o sistema passar a registrar nome/telefone de clientes, será preciso: base legal, aviso de privacidade,
  campo para exclusão e criptografia do backup (o workflow já criptografa).

## 5. Riscos que continuam e o que fazer

1. **Sem 2FA**: quem descobrir a senha entra. Use senha longa e única e mantenha o limite de tentativas (5/15 min). Dá para reativar o 2FA pelo histórico do git (commit anterior).
2. **Variáveis na Vercel** (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `OWNER_EMAIL`, `DATABASE_URL`, e recomendado `LOG_SALT`) ainda precisam estar configuradas.
3. **No Supabase**: desative "Allow new users to sign up" (senão qualquer pessoa cria conta; o código só libera os e-mails permitidos, mas é melhor fechar a porta) e 
4. **Rate limit de API é por instância** (memória). Em picos de ataque distribuído ele é parcial. O limite de login/2FA usa o banco e é consistente.
5. **Vercel Authentication** do projeto `drm-cell` está ligada: o site hoje exige login da Vercel. Desligue para o site ficar público.
6. **GitHub Pages não aplica `vercel.json`**: no endereço `github.io` os cabeçalhos e a API não existem. Use a Vercel como endereço oficial e, se quiser, desative o Pages.
7. **Backup automático não foi executado** (precisa dos secrets `DATABASE_URL` e `BACKUP_PASSPHRASE` no GitHub). O teste de restauração foi feito só com SQLite. Se usar o plano gratuito do Supabase, não há backup nativo.
8. **Alertas**: os logs existem, mas ninguém é avisado. Configure um Log Drain ou alerta na Vercel para `login_bloqueado` / `mfa_bloqueado`.
9. **HSTS sem `preload`** e sem teste em produção: confira os cabeçalhos com `curl -I` depois do deploy.
10. Repositório **público** expõe a lógica de cálculo (taxa 13,92%). Considere torná-lo privado se isso for sensível.
11. `psycopg2-binary` tem versão mais nova (2.9.13); sem vulnerabilidade conhecida na atual, atualize quando puder testar no deploy.
12. A pasta antiga `Calculadora de taxas/` (raiz, com `app.py`) é uma cópia anterior sem estas proteções; não publique dela.
