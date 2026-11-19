# Controle de Caixa

Sistema web de controle financeiro empresarial (MVP), voltado a pequenos
comerciantes (bares, mercearias, padarias, lanchonetes). Construído com
Django, Django Templates, Bootstrap 5, JavaScript puro e PostgreSQL.

## Tecnologias

- Python 3.11+ e Django 5.2
- Django Templates + Bootstrap 5 (via CDN)
- JavaScript puro (sem frameworks)
- Apache ECharts 6.1.0 para gráficos, distribuído localmente
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

### Alternativa SQLite (somente desenvolvimento)

Em uma máquina ou servidor de **desenvolvimento isolado**, é possível usar
SQLite sem instalar/configurar um servidor PostgreSQL, trocando apenas a
variável `DATABASE_URL` no `.env`:

```
DATABASE_URL=sqlite:///db.sqlite3
```

Nenhuma outra alteração é necessária — `python manage.py migrate` e
`python manage.py runserver` funcionam normalmente com esse banco. **Não use
essa opção em produção nem em ambientes com múltiplos usuários simultâneos**:
o SQLite trava o banco inteiro durante escritas concorrentes e não possui as
constraints de integridade reforçadas no banco (ex.: chaves estrangeiras por
trigger) usadas pelo PostgreSQL — por isso alguns testes específicos de
integridade entre empresas (`apps/core/test_tenant_foreign_keys.py`) são
pulados automaticamente quando o banco não é PostgreSQL. O PostgreSQL
continua sendo o banco padrão e obrigatório para produção.

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
  automaticamente; divergências não exigem justificativa.
- Abertura obrigatória do caixa (com valor inicial em dinheiro) antes de
  qualquer lançamento financeiro, com regra de caixa único (apenas um
  caixa aberto por vez).
- Fechamento e reabertura de caixa, com bloqueio de lançamentos em dias
  fechados e exigência de conferência completa antes do fechamento.
- Planejamento por dia da semana respeitando o calendário real, com
  os indicadores Faturamento (dinheiro conferido no fechamento menos
  o valor de abertura, somado ao conferido nas demais formas de
  pagamento) e Gastos (despesas pagas).
- Geração do prompt de análise de IA sem chamada a serviços externos, e
  tratamento de falhas da chamada automática à API do Gemini (mantida no
  código para uso futuro) sem interromper o sistema.

## Contas a pagar recorrentes (Fixa, Semanal e Parcelada)

Na tela de Contas a pagar, ao criar uma nova conta é possível escolher
entre **Única** (comportamento padrão, igual a antes) ou um dos três
tipos de recorrência:

- **Fixa mensal**: repete todo mês em um dia fixo (ex.: aluguel, todo
  dia 10). As próximas ocorrências são geradas automaticamente sempre
  que a tela de Contas a pagar é acessada (geração "sob demanda", sem
  jobs em segundo plano), mantendo uma janela de 2 meses à frente.
- **Semanal**: repete todo(a) um dia da semana (ex.: fornecedor de pão
  às quartas), com a mesma lógica de geração sob demanda, mantendo uma
  janela de 8 semanas à frente.
- **Parcelada**: finita por natureza — todas as parcelas são geradas de
  uma vez no momento da criação, com o valor total dividido em partes
  iguais (ajuste de centavos na última parcela, nunca usando `float`).

Cada ocorrência gerada é uma conta a pagar comum e independente (com
seu próprio saldo, pagamentos e histórico); a série é apenas o "molde"
usado para gerar e, opcionalmente, editar várias ocorrências de uma vez.

### Editar apenas 1 ocorrência vs. editar toda a série

- **Editar uma ocorrência** (tela normal de edição de conta): se o
  valor ou a data forem alterados de forma diferente do padrão da
  série, essa ocorrência é marcada como **"Alterada manualmente"** e
  nunca mais será sobrescrita por uma edição em massa da série.
- **Editar a série** (tela "Ver série completa", acessível pelo ícone
  de recorrência ao lado da descrição na listagem): aplica a mudança de
  descrição/fornecedor/valor a todas as ocorrências **futuras**, ainda
  **pendentes** e que **não** tenham sido alteradas manualmente.
  Ocorrências já pagas, canceladas ou já personalizadas nunca são
  tocadas — o histórico financeiro é sempre preservado.
- Séries parceladas não podem ter o valor/descrição editados em massa
  (mudaria o total já combinado); é possível apenas cancelar as
  parcelas restantes não pagas.
- "Cancelar ocorrências futuras" cancela apenas o que ainda não foi
  pago e pausa a geração de novas ocorrências daquela série.

## Assistente IA (geração de prompt para cópia manual)

O Assistente IA (menu "Assistente IA") não envia nenhum dado automaticamente
a serviços externos. Para cada análise pré-programada, o backend Django
calcula os indicadores financeiros relevantes e monta um texto (prompt)
já pronto para ser copiado e colado pelo usuário em qualquer IA de sua
preferência (ChatGPT, Gemini, Copilot etc.), usando o botão "Copiar texto"
da tela de resultado.

Essa abordagem foi adotada porque algumas hospedagens (ex.: planos
gratuitos do PythonAnywhere) restringem chamadas de saída a uma lista
fixa de domínios, o que impediria o backend de chamar diretamente a API
de um provedor de IA. Como o backend nunca envia o prompt para nenhum
serviço externo, nenhuma chave de API é necessária para essa
funcionalidade, e nenhum dado financeiro deixa o navegador do usuário
sem que ele decida colar o texto em outro serviço por conta própria.

O código de chamada automática à API do Google Gemini (`apps/ai_assistant/services.py`,
funções `ask`/`run_analysis`/`_call_gemini`) permanece no projeto para uso
futuro em ambientes sem essa restrição de rede (ex.: Render), mas não é
utilizado pelas views padrão atualmente. Caso seja reativado, siga as
variáveis `GEMINI_ENABLED`, `GEMINI_API_KEY`, `GEMINI_MODEL` e
`GEMINI_TIMEOUT_SECONDS` do `.env.example`.

## Backup e restauração do PostgreSQL

Use `pg_dump` com credencial de administração e armazene o backup
criptografado fora do diretório da aplicação. Teste a restauração com
`pg_restore` em um banco isolado; não restaure sobre o banco de uso sem
planejamento e autorização. Para o Neon, consulte também os recursos de
backup e recuperação disponíveis no plano contratado. Configure uma rotina
de backups e teste a restauração periodicamente.

## PWA (aplicativo instalável)

O sistema pode ser instalado como PWA em navegadores compatíveis e exige
HTTPS (ou localhost para desenvolvimento).

- No Android, abra o sistema no Chrome e use o menu **Instalar aplicativo**
  ou **Adicionar à tela inicial**, conforme a opção disponível no navegador.
- No iPhone, abra o sistema no Safari, toque em **Compartilhar** e depois
  em **Adicionar à Tela de Início**.

O Service Worker é servido em `/service-worker.js` e armazena em cache apenas
uma página pública de aviso de indisponibilidade; páginas autenticadas e dados
financeiros não são armazenados por ele. Se a conexão falhar após o envio de
uma operação, confira o histórico antes de tentar novamente, pois ela pode
ter sido registrada no servidor mesmo sem confirmação na tela. Não há
sincronização offline de transações.

## Gráficos e visualização de dados

O Apache ECharts é o padrão para gráficos do projeto. O arquivo compilado
6.1.0 e seus avisos de licença estão em `static/js/vendor/echarts/`; não
são necessários Node.js, npm ou CDN para usá-lo. A visão anual carrega a
biblioteca apenas quando necessária. O comparativo de faturamento e gastos
usa barras verticais agrupadas; os gráficos de planejado versus realizado
usam barras horizontais agrupadas.

Os cálculos financeiros permanecem no Django. Meses pendentes não são
tratados como zero; meses parciais são identificados. As tabelas de valores
exatos ficam ocultas visualmente e disponíveis para leitores de tela; se a
biblioteca não carregar, o gráfico SVG original continua disponível. Ao adicionar gráficos, escolha
a visualização adequada aos dados, preserve as definições dos indicadores,
a acessibilidade e o isolamento entre empresas.

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

- Em Planejamento, cartões permitem alternar entre as visões diária,
  semanal e anual. As semanas vão de segunda a domingo e incluem somente
  os dias do mês selecionado. A visão anual apresenta gráficos dos 12 meses
  do ano do mês selecionado: comparativo de faturamento e gastos realizados
  e comparações entre planejado e realizado para cada indicador. Tabelas
  acessíveis a leitores de tela apresentam valores exatos e a situação de cada mês.
  O faturamento considera os valores conferidos em caixas fechados e pode
  ser parcial quando há dias sem fechamento. Os gastos são agrupados pela
  data prevista da conta, inclusive para pagamentos já registrados com
  data prevista futura; esse critério é diferente do fluxo de caixa efetivo.
  A receita exibida é a diferença entre faturamento e gastos, não uma
  demonstração contábil de lucro.
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
- A instalação do PWA depende do navegador e deve ser validada em dispositivos
  Android e iOS; as opções e a experiência podem variar.
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
  aquela data são bloqueados no backend. A reabertura é restrita a usuários
  autorizados, registra responsável e horário, e é bloqueada se já houver
  outro caixa aberto no momento. Não é solicitado motivo.
- Na "Conferência de caixa", o operador informa os valores contados e os
  salva em conjunto. O sistema calcula a sobra ou falta sem exigir
  justificativa. Cada conferência preserva o histórico; uma correção gera
  um novo registro. Os motivos de reabertura registrados anteriormente
  permanecem no histórico.
