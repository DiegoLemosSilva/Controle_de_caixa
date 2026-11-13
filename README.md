# Controle de Caixa

Sistema web de controle financeiro empresarial (MVP), voltado a pequenos
comerciantes (bares, mercearias, padarias, lanchonetes). Construído com
Django, Django Templates, Bootstrap 5, JavaScript puro e PostgreSQL.

## Tecnologias

- Python 3.11+ e Django 5.2
- Django Templates + Bootstrap 5 (via CDN)
- JavaScript puro (sem frameworks)
- PostgreSQL
- PWA (Web App Manifest + Service Worker)
- API do Google Gemini (opcional, desativável)

## Instalação

```bash
# 1. Criar e ativar um ambiente virtual (recomendado)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate    # Linux/Mac

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Copiar o arquivo de variáveis de ambiente
copy .env.example .env         # Windows
# cp .env.example .env          # Linux/Mac
```

Edite o arquivo `.env` com os valores adequados ao seu ambiente. Nunca
versione o arquivo `.env` com segredos reais.

## Banco de dados e migrações

```bash
python manage.py migrate
```

### Conexão ao PostgreSQL

Instale as dependências de `requirements.txt` e configure `DATABASE_URL`
no `.env` com a URL PostgreSQL fornecida pelo serviço, incluindo os
parâmetros TLS exigidos. Não compartilhe ou versione credenciais.
Para manutenção explícita, `DATABASE_ADMIN_URL` pode ser mantida no mesmo
`.env`; a aplicação não a utiliza automaticamente. Proteja o arquivo:
quem puder lê-lo terá acesso a todas as credenciais nele armazenadas.

Antes do corte, faça e teste um backup consistente, ensaie a migração e
reconcilie os dados. Não execute `migrate` ou testes contra um banco de
produção sem avaliar o destino e as permissões. Use um banco ou branch
descartável para testes. O RLS experimental foi descontinuado: o isolamento
entre empresas depende das validações e filtros do código. Uma credencial
proprietária não deve ser usada como papel normal da aplicação.

O procedimento de auditoria, ensaio, corte e reversão está em
[`docs/migracao-postgresql.md`](docs/migracao-postgresql.md).

## Criar o usuário administrador (vinculado a uma empresa)

O sistema exige que cada usuário esteja vinculado a exatamente uma empresa
(`Business`). Use o comando de gerenciamento abaixo para criar o primeiro
usuário já vinculado:

```bash
python manage.py create_business_user --username admin --password "SENHA_FORTE" --business "Nome do Estabelecimento" --superuser
```

- Omita `--superuser` se não precisar de acesso ao `/admin/`.
- Repita o comando com um novo `--business` para cada novo estabelecimento.

### Restringir um usuário apenas às funcionalidades do Caixa (grupo "Operador")

Para que um usuário (ex: um funcionário) só possa acessar o Caixa, registrar
vendas/comandas e fazer a conferência de caixa — sem ver Vendas (histórico),
Clientes, Contas a pagar, Planejamento ou o Assistente IA:

1. Acesse `/admin/auth/group/` e crie (ou confirme que já existe) um grupo
   chamado exatamente **Operador**.
2. Em `/admin/auth/user/`, edite o usuário desejado e adicione-o ao grupo
   **Operador**, na seção "Grupos".
3. O usuário deve continuar vinculado à empresa normalmente (`BusinessOwner`).

A partir disso, qualquer tentativa de acessar views fora do Caixa (Vendas,
Clientes, Contas a pagar, Planejamento, Assistente IA) retorna erro 403, e
esses links desaparecem do menu de navegação para esse usuário. Superusuários
nunca são afetados por essa restrição, mesmo que estejam no grupo.

Além disso, usuários do grupo Operador **nunca podem reabrir um caixa
fechado** — essa é considerada uma decisão gerencial, não uma operação do
dia a dia do caixa. O botão "Reabrir caixa" nem aparece para esse grupo na
tela de Conferência de Caixa, e a tentativa de reabertura é bloqueada (403)
também no backend, de forma fixa (não configurável por permissão do Admin).

## Executar o sistema

```bash
python manage.py runserver
```

Acesse `http://127.0.0.1:8000/` e faça login com o usuário criado.

### Implantação de teste no Render

Crie um Web Service Python vinculado ao repositório. Utilize um PostgreSQL
separado para testes e confirme seu destino antes de executar migrações.

- Build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
- Start command: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`

Configure no Render, sem adicionar segredos ao Git:

- `DJANGO_DEBUG=False`
- `DJANGO_SECRET_KEY`: chave aleatória forte e exclusiva do ambiente.
- `DJANGO_ALLOWED_HOSTS`: domínio do serviço, sem `https://`.
- `DJANGO_CSRF_TRUSTED_ORIGINS`: origem completa, por exemplo `https://seu-servico.onrender.com`.
- `DATABASE_URL`: URL PostgreSQL com credencial restrita e TLS.
- `DJANGO_SECURE_COOKIES=True`, `DJANGO_TRUST_PROXY_HTTPS=True` e
  `DJANGO_SECURE_SSL_REDIRECT=True`.
- `GEMINI_ENABLED=False` inicialmente. Para testar a IA, configure também
  `GEMINI_API_KEY` e `GEMINI_MODEL` nas variáveis privadas do serviço.

Execute `python manage.py migrate` separadamente com credencial de migração,
apontando para o banco de teste confirmado; não use a credencial proprietária
como credencial normal da aplicação. O build não aplica migrações.
Crie um usuário com empresa vinculada usando `create_business_user`; evite
passar senhas reais por comandos que possam ser registrados em histórico.

Teste login, arquivos estáticos, operações com dados fictícios e isolamento
entre empresas. Revogue e substitua credenciais previamente expostas antes de
publicar. O serviço não foi validado para produção: o Admin padrão pode
permitir alterações financeiras diretas e o isolamento depende do código.

### PostgreSQL e isolamento empresarial

Neste ambiente, o `.env` seleciona o PostgreSQL sem RLS e contém a
`DATABASE_URL` do papel restrito da aplicação. O comando normal
`python manage.py runserver` usa essa configuração, salvo se variáveis
de ambiente a sobrescreverem. A URL administrativa, quando necessária,
pode ser armazenada como `DATABASE_ADMIN_URL` no mesmo arquivo.

Gravações são feitas no PostgreSQL configurado. O Admin padrão depende das
permissões Django e pode permitir acesso e alterações financeiras diretas.
Restrinja seu acesso a pessoas autorizadas e use as telas próprias para
operações financeiras. O isolamento por empresa, o Admin e os demais fluxos
precisam de revisão antes de uso em produção. Veja
[`docs/migracao-postgresql.md`](docs/migracao-postgresql.md).

## Executar os testes automatizados

Não execute testes contra o banco PostgreSQL de uso da aplicação. Configure
uma URL e credenciais administrativas para um banco ou branch descartável,
defina essa URL como `DATABASE_URL` somente na sessão de testes e execute
`python manage.py test`.
Não substitua a URL da aplicação permanentemente pela administrativa.
O usuário de teste precisa ter permissão de criar o banco de testes do Django.

**Nota de performance**: a suíte usa `MD5PasswordHasher` em vez do
`PBKDF2PasswordHasher` padrão do Django **apenas durante os testes**
(ativado automaticamente em `config/settings.py` quando o comando é
`manage.py test`, nunca em produção). PBKDF2 é intencionalmente lento
(resistência a força bruta) e, como a suíte cria dezenas de usuários via
`User.objects.create_user(...)`, isso reduziu o tempo total de execução
de ~5 minutos para ~5 segundos, sem qualquer impacto na segurança real
do sistema (o hasher de produção nunca é alterado).

Os testes cobrem, entre outros pontos exigidos pelo `AGENTS.md`:

- Isolamento de dados entre empresas e bloqueio de acesso cruzado.
- Autenticação e vínculo obrigatório usuário-empresa.
- Venda dividida entre Pix, dinheiro e fiado (sem divergência).
- Rejeição de venda com soma de valores incorreta ou fiado sem cliente.
- Cancelamento de venda (preserva histórico, não pode ser repetido).
- Comandas: finalização gera uma única venda, sem duplicidade.
- Pagamentos parciais e totais de recebíveis e contas a pagar.
- Rejeição de pagamento superior ao saldo devido.
- Cálculo de indicadores financeiros sem dupla contagem.
- Conferência de caixa físico (sobra/falta) com valor esperado calculado
  automaticamente e justificativa obrigatória.
- Abertura obrigatória do caixa (com valor inicial em dinheiro) antes de
  qualquer lançamento financeiro, com regra de caixa único (apenas um
  caixa aberto por vez).
- Fechamento e reabertura de caixa, com bloqueio de lançamentos em dias
  fechados e exigência de conferência completa antes do fechamento.
- Planejamento por dia da semana respeitando o calendário real, com
  os indicadores Faturamento (dinheiro conferido no fechamento menos
  o valor de abertura, somado ao conferido nas demais formas de
  pagamento) e Gastos (despesas pagas).
- Tratamento de falhas da API do Gemini sem interromper o sistema.

## Configuração da API Gemini (opcional)

A integração com IA é opcional. Para habilitá-la:

1. Obtenha uma chave de API do Google Gemini.
2. No arquivo `.env`, defina:
   ```
   GEMINI_ENABLED=True
   GEMINI_API_KEY=sua-chave-aqui
   GEMINI_MODEL=gemini-2.5-flash
   GEMINI_TIMEOUT_SECONDS=15
   ```
3. A chave nunca é exposta ao navegador: todas as chamadas são feitas pelo
   backend Django, que envia apenas dados financeiros agregados (nunca
   dados pessoais de clientes) e trata timeouts e falhas de forma segura.

Se a API estiver indisponível ou desativada, as telas de "Assistente IA" e
"Análise automática" exibem uma mensagem informativa, sem afetar o restante
do sistema.

## Backup e restauração do PostgreSQL

Use `pg_dump` com credencial de administração e armazene o backup
criptografado fora do diretório da aplicação. Teste a restauração com
`pg_restore` em um banco isolado; não restaure sobre o banco de uso sem
planejamento e autorização. Para o Neon, consulte também os recursos de
backup e recuperação disponíveis no plano contratado. Configure uma rotina
de backups e teste a restauração periodicamente.

## PWA (aplicativo instalável)

O sistema é instalável como PWA. O Service Worker (`static/pwa/service-worker.js`)
armazena em cache **apenas arquivos estáticos públicos** — nunca páginas
autenticadas ou dados financeiros — para evitar exposição de informações
após logout ou expiração de sessão.

## Estrutura do projeto

```
config/            Configurações do projeto Django (settings, urls)
apps/
    core/           Modelos e constantes compartilhadas
    businesses/     Empresas (Business) e isolamento por usuário
    customers/      Clientes
    products/       Cadastro simples de produtos (nome + preço)
    sales/          Vendas, pagamentos divididos e comandas
    receivables/    Recebíveis (fiado) e pagamentos
    payables/       Contas a pagar e pagamentos
    cash/           Indicadores financeiros (dashboard de caixa)
    planning/       Planejamento financeiro mensal
    ai_assistant/   Integração com a API do Google Gemini
templates/          Templates HTML (Bootstrap 5)
static/             CSS, JS e arquivos do PWA
```

## Limitações conhecidas do MVP

- O limite de fiado no cadastro de clientes é opcional e informativo:
  ultrapassá-lo gera um aviso, mas não bloqueia vendas nem comandas.
  O aviso considera o saldo em aberto e o fiado registrado em comandas
  abertas; a prévia usa os dados carregados na tela e pode ficar
  desatualizada. O total de fiados da lista considera apenas recebíveis
  em aberto, incluindo clientes inativos, independentemente da pesquisa.
  Ocultar valores é apenas uma opção visual, não uma proteção de acesso.
- O cadastro de produtos (menu Produtos) é intencionalmente simples:
  apenas nome e preço de venda, sem controle de estoque, variações ou
  categorias. Serve só para pré-preencher a descrição e o valor ao
  lançar um item em Vendas ou Comandas, e para permitir uma análise
  futura de produtos mais vendidos. Usar um produto é sempre opcional:
  a descrição livre continua funcionando normalmente em qualquer venda
  ou item de comanda.
- Comandas aceitam pagamento dividido entre várias pessoas da mesma mesa:
  cada pessoa pode registrar sua parte com sua própria forma de pagamento
  (inclusive fiado, com cliente próprio), à medida que o saldo é abatido.
  A comanda só pode ser finalizada quando o saldo restante for exatamente
  zero. Enquanto estiver aberta, esses pagamentos não entram em nenhum
  indicador financeiro — só passam a contar quando a comanda é finalizada.
- Não há sincronização offline: todas as operações financeiras exigem conexão.
- O MVP trabalha com um usuário por empresa (estrutura preparada para evoluir
  para múltiplos usuários por empresa no futuro).
- Os ícones do PWA (`static/icons/icon-192.png`, `icon-512.png`) precisam ser
  adicionados manualmente antes da instalação completa como aplicativo (o
  sistema funciona normalmente sem eles, apenas sem ícone customizado).
- A integração com Gemini depende de uma chave de API externa e está sujeita
  aos termos de uso e disponibilidade do serviço do Google.
- Por padrão, o caixa de qualquer data está **fechado**: é necessário
  abri-lo explicitamente (menu Caixa), informando o valor inicial em
  dinheiro presente na gaveta. Esse valor de abertura é exibido
  separadamente de Vendas e Recebimentos nos indicadores, e é somado ao
  valor esperado em "Dinheiro" na Conferência de caixa.
- Só pode existir **um caixa aberto por vez** por empresa: tentar abrir
  um novo caixa com outro já aberto é bloqueado no backend, orientando a
  fechar o caixa atual primeiro.
- A aba "Caixa" é organizada por dia, com navegação para o dia anterior e
  o próximo. O fechamento do caixa de um dia (Caixa > Conferência de caixa)
  exige que todas as formas de pagamento tenham sido conferidas fisicamente
  e que não existam comandas abertas. Após o fechamento, novos lançamentos
  financeiros (vendas, recebimentos de fiado, pagamentos de contas) para
  aquela data são bloqueados no backend. A reabertura exige justificativa
  e é bloqueada se já houver outro caixa aberto no momento.
- A diferença entre o caixa físico e o valor esperado pelo sistema é
  resolvida pela "Conferência de caixa": o operador informa o valor
  contado por forma de pagamento e o sistema calcula a sobra/falta
  automaticamente. Cada conferência é um registro histórico e auditável
  (nunca editado ou apagado); uma correção gera uma nova conferência,
  preservando a anterior.
