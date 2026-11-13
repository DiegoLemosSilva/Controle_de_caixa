# AGENTS.md — Sistema de Controle Financeiro Empresarial

## 1. Objetivo do projeto

Desenvolver um sistema web de controle financeiro empresarial por assinatura, destinado principalmente a pequenos comerciantes, como bares, mercearias, padarias, lanchonetes e pequenos estabelecimentos.

O sistema deve ser simples de operar, confiável nos cálculos financeiros, responsivo para celulares e computadores e preparado para funcionar como PWA instalável.

A prioridade é entregar um MVP funcional, seguro e de fácil manutenção, sem complexidade arquitetural desnecessária.

## 2. Tecnologias obrigatórias

- **Backend:** Python + Django.
- **Interface:** Django Templates, HTML5 e CSS3.
- **Estilização:** Bootstrap 5.
- **Interatividade:** JavaScript puro, sem frameworks.
- **Banco de dados:** PostgreSQL.
- **Aplicativo instalável:** PWA com Web App Manifest e Service Worker.
- **Inteligência artificial:** API do Google Gemini.
- **Autenticação:** sistema nativo de autenticação do Django.
- **Testes:** testes automatizados do Django.

### Restrições tecnológicas

Não introduzir sem autorização:

- Spring Boot ou Java como backend.
- React, Next.js, Angular ou Vue.js.
- Django REST Framework ou API REST separada.
- MySQL ou MongoDB.
- Redis, Celery ou infraestrutura adicional desnecessária.
- Bibliotecas pagas ou serviços obrigatórios com custo recorrente.

Não criar uma arquitetura de microsserviços. Manter o sistema como uma aplicação Django modular.

Dependências adicionais só devem ser incluídas quando houver necessidade real e justificativa.

## 3. Princípios de desenvolvimento

1. Priorizar simplicidade, legibilidade e manutenção.
2. Implementar regras de negócio no backend, nunca apenas na interface.
3. Utilizar componentes e templates reutilizáveis.
4. Evitar duplicação de código e cálculos financeiros.
5. Não criar funcionalidades que não tenham relação com os requisitos.
6. Não deixar botões, formulários ou links sem funcionamento.
7. Não utilizar dados fictícios como se fossem dados reais em produção.
8. Não substituir funcionalidades existentes sem verificar seus impactos.
9. Executar testes e verificações após cada etapa relevante.
10. Documentar decisões técnicas importantes.

Antes de modificar o projeto, verificar a estrutura, as dependências, os arquivos existentes e o estado atual da implementação.

## 4. Arquitetura sugerida

Organizar o projeto em aplicativos Django por domínio, evitando a concentração de todas as regras em um único arquivo.

Estrutura de referência:

    config/
        settings.py
        urls.py
        wsgi.py
        asgi.py

    apps/
        core/
        businesses/
        customers/
        sales/
        receivables/
        payables/
        cash/
        planning/
        ai_assistant/

    templates/
        base.html
        components/
        registration/

    static/
        css/
        js/
        icons/
        pwa/

    manage.py
    requirements.txt
    .env.example
    .gitignore
    README.md

A estrutura pode ser ajustada à medida que o projeto evoluir, desde que permaneça modular e coerente.

Não criar aplicativos vazios apenas para seguir o exemplo. Criar cada módulo quando ele for necessário.

## 5. Usuários e isolamento empresarial

O MVP deve trabalhar com uma conta de usuário por empresa.

Criar um modelo Business para representar cada estabelecimento e relacionar o usuário autenticado à sua empresa por meio de um relacionamento explícito e obrigatório.

Regras:

- Todo registro financeiro deve pertencer a uma empresa.
- Toda consulta e alteração deve respeitar a empresa do usuário autenticado.
- Nunca confiar em um business_id enviado pelo navegador para definir o acesso.
- Obter a empresa autorizada a partir do usuário autenticado.
- Validar a propriedade dos objetos em todas as operações.
- Impedir acesso cruzado entre empresas, inclusive por alteração de IDs na URL.
- Não permitir que um usuário sem empresa vinculada acesse dados financeiros.

O sistema deve permitir evolução futura para múltiplos usuários por empresa, mas isso não é requisito do MVP.

## 6. Regras monetárias e datas

- Utilizar DecimalField para valores monetários, nunca float.
- Padrão de precisão monetária: max_digits=12 e decimal_places=2, ajustável somente com justificativa.
- Utilizar transações atômicas nas operações financeiras compostas.
- Armazenar datas e horários de forma consistente, utilizando os recursos de fuso horário do Django.
- Apresentar datas no formato brasileiro e valores em reais.
- Validar valores negativos, nulos e limites de precisão.
- Definir regras claras para arredondamento e evitar divergências entre cálculos.

## 7. Vendas e formas de pagamento

Permitir registrar vendas com descrição livre, valor total, data e hora, forma de pagamento e, quando necessário, cliente.

**Atualização de decisão:** foi implementado um cadastro simples de
produtos (nome + preço de venda), sem controle de estoque, com o único
propósito de agilizar o lançamento de itens em vendas e comandas
(pré-preenchendo descrição e valor) e permitir uma análise futura dos
produtos mais vendidos. O uso do produto é sempre opcional: vendas e
itens de comanda continuam aceitando descrição livre normalmente, e o
produto nunca é obrigatório para nenhuma operação financeira. Essa
decisão substitui a restrição original de não implementar catálogo de
produtos, mantendo o escopo deliberadamente mínimo (sem estoque, sem
variações, sem categorias).

Uma venda pode ser dividida entre diferentes formas de pagamento e ter uma parte recebida posteriormente como fiado.

Exemplo: venda de R$ 100,00:

- Pix: R$ 40,00.
- Dinheiro: R$ 20,00.
- Fiado: R$ 40,00.

O modelo financeiro deve registrar:

- Uma única venda de R$ 100,00.
- Um recebimento de R$ 40,00 via Pix.
- Um recebimento de R$ 20,00 em dinheiro.
- Um recebível de R$ 40,00 vinculado à venda e ao cliente.

A soma dos recebimentos imediatos com o saldo lançado no fiado deve ser igual ao total da venda no momento da finalização.

Regras obrigatórias:

- Não permitir finalizar a venda com divergência de valores.
- Não permitir pagamentos superiores ao saldo devido.
- Não permitir fiado sem cliente identificado.
- Não permitir finalizar a mesma venda mais de uma vez.
- Criar venda, recebimentos e recebível na mesma transação atômica.
- Não contabilizar a mesma receita duas vezes.
- Diferenciar venda realizada de dinheiro efetivamente recebido.
- Cancelamentos devem preservar histórico e gerar os ajustes necessários.

## 8. Comandas

Uma comanda representa uma venda em andamento.

Deve permitir:

- Abrir comanda.
- Adicionar itens com descrição livre.
- Informar quantidade e valor.
- Consultar o total acumulado.
- Registrar pagamentos parciais.
- Finalizar com divisão entre formas de pagamento e fiado.

Uma comanda aberta não deve ser contabilizada como venda finalizada.

Na finalização, criar uma única venda definitiva e seus respectivos recebimentos e recebíveis.

Não gerar uma segunda venda ao receber posteriormente o saldo fiado.

## 9. Clientes e fiado

Cadastrar clientes com:

- Nome obrigatório.
- Telefone opcional.
- Observações opcionais.
- Situação ativa ou inativa.

Permitir consultar:

- Saldo em aberto.
- Histórico de dívidas.
- Origem de cada dívida.
- Pagamentos parciais e totais.
- Saldo restante após cada pagamento.

Cada recebimento posterior de fiado deve estar vinculado ao recebível correspondente.

O recebimento de uma dívida antiga não constitui uma nova venda.

Não permitir receber valor superior ao saldo devedor.

## 10. Contas a pagar

Permitir cadastrar contas a pagar com:

- Descrição.
- Fornecedor opcional.
- Valor original.
- Data de vencimento.
- Situação.
- Histórico de pagamentos.

Permitir pagamento parcial ou integral.

A criação de uma conta a pagar não representa saída de caixa. A saída ocorre quando um pagamento é efetivamente registrado.

O sistema deve distinguir contas pendentes, vencidas e pagas.

Pagamentos devem preservar histórico, forma de pagamento, data e usuário responsável.

## 11. Caixa e indicadores financeiros

Apresentar indicadores de:

- Vendas realizadas.
- Recebimentos efetivos.
- Despesas efetivamente pagas.
- Valores pendentes de clientes.
- Contas a pagar em aberto.
- Resumo diário, semanal e mensal.

Definir claramente cada indicador:

- **Vendas:** valor das vendas finalizadas no período.
- **Recebimentos:** valores efetivamente recebidos no período, inclusive pagamentos de dívidas anteriores.
- **Despesas pagas:** pagamentos de despesas efetivamente realizados no período.
- **Fiado:** valores a receber, não dinheiro disponível.
- **Contas a pagar:** compromissos financeiros, não necessariamente despesas já pagas.

Não somar a mesma movimentação por tabelas diferentes.

Utilizar os registros financeiros de origem para calcular os indicadores. Não criar movimentações de caixa duplicadas para vendas, recebimentos ou pagamentos já representados em seus respectivos modelos.

O modelo CashMovement deve ser utilizado apenas para movimentações avulsas que não tenham sido geradas por outros fluxos financeiros.

Se houver cancelamentos ou estornos, considerar seus efeitos nos indicadores sem apagar o histórico original.

## 12. Planejamento financeiro

Permitir selecionar ano e mês e planejar três indicadores separadamente:

- Vendas.
- Recebimentos.
- Despesas pagas.

O usuário poderá informar um valor-base para cada dia da semana.

O sistema deverá aplicar esse valor a todas as ocorrências daquele dia da semana no mês selecionado, respeitando o calendário real.

Exemplo: todas as segundas-feiras do mês recebem inicialmente a mesma meta de vendas.

Permitir:

- Alterar a previsão de uma data sem modificar as demais.
- Copiar o planejamento do mês anterior.
- Editar o novo mês independentemente do anterior.
- Comparar planejado e realizado.
- Exibir diferença absoluta e percentual quando o cálculo for válido.
- Marcar dias ainda não encerrados como pendentes, evitando apresentar zero como resultado definitivo.

Os valores realizados devem ser calculados a partir das movimentações financeiras reais. Não duplicar transações para preencher o planejamento.

Criar restrições para evitar duplicidade de planejamento por empresa, ano, mês, data e indicador, conforme o modelo adotado.

## 13. Fechamento diário

Permitir fechar o movimento financeiro de uma data.

Após o fechamento, bloquear novos lançamentos para aquela data, incluindo alterações que afetem seus resultados financeiros.

A reabertura deve exigir autorização e justificativa.

Registrar:

- Data do movimento.
- Data e horário do fechamento.
- Usuário responsável.
- Data e horário da reabertura.
- Usuário responsável pela reabertura.
- Motivo da reabertura.
- Histórico dos eventos.

Verificar o fechamento no backend em todas as operações financeiras relevantes. Desabilitar botões na interface não é suficiente.

Operações concorrentes devem ser tratadas de forma consistente, reduzindo o risco de lançamentos após o fechamento.

## 14. Inteligência artificial com Gemini

Implementar duas funcionalidades:

1. Análise financeira automática.
2. Chat para perguntas sobre as finanças da empresa.

A aplicação Django deve calcular previamente os indicadores e fornecer à IA apenas o contexto necessário para responder.

A IA não deve acessar diretamente o banco de dados, executar SQL arbitrário ou modificar registros financeiros.

Exemplos de análises:

- Comparação entre períodos.
- Despesas que aumentaram.
- Diferenças entre metas e resultados.
- Evolução de vendas e recebimentos.
- Alertas de contas vencidas e saldos a receber.

Requisitos:

- API key configurada por variável de ambiente.
- Nunca incluir a chave no código versionado ou no JavaScript do navegador.
- Definir timeouts, tratamento de erros e limites de utilização.
- Registrar utilização e custos quando houver dados disponíveis.
- Tratar indisponibilidade da API sem impedir o funcionamento financeiro.
- Não prometer precisão de previsões ou aconselhamento financeiro profissional.
- Informar quando não houver dados suficientes.
- Não inventar indicadores nem apresentar estimativas como valores reais.
- Utilizar dados agregados sempre que possível.
- Minimizar dados pessoais enviados à API.
- Não enviar nomes, telefones ou outras informações identificáveis sem necessidade e avaliação adequada de privacidade.
- Verificar as condições de uso e tratamento de dados do serviço antes de utilizar informações financeiras reais.

Durante o desenvolvimento, usar dados fictícios e testes controlados. A funcionalidade de IA deve poder ser desativada por configuração.

## 15. PWA e proteção de dados

Implementar:

- Web App Manifest.
- Ícones apropriados.
- Service Worker.
- Experiência instalável em navegadores compatíveis.
- Layout responsivo para celular e computador.

A primeira versão deve exigir conexão para registrar e confirmar operações financeiras. Não implementar sincronização offline de transações neste MVP.

O Service Worker não deve armazenar em cache páginas autenticadas, respostas financeiras privadas ou dados pessoais de forma que possam ser acessados após logout.

O cache deve priorizar arquivos estáticos públicos. Revisar o comportamento de logout e expiração da sessão.

## 16. Segurança

- Utilizar proteção CSRF do Django.
- Validar dados no servidor.
- Utilizar consultas do ORM em vez de SQL concatenado.
- Proteger operações por autenticação e autorização.
- Evitar exposição de dados sensíveis em logs e mensagens de erro.
- Configurar corretamente variáveis de ambiente.
- Não versionar `.env`, banco de produção, segredos ou arquivos de backup.
- Utilizar `DEBUG=False` em produção.
- Configurar `ALLOWED_HOSTS`, cookies seguros e HTTPS conforme o ambiente de produção.
- Preservar histórico de operações financeiras.
- Preferir cancelamentos e estornos auditáveis em vez de exclusões silenciosas.
- Usar `transaction.atomic()` em operações financeiras compostas.
- Implementar verificações de integridade no backend e, quando apropriado, no banco de dados.

## 17. PostgreSQL, persistência e backup

PostgreSQL é o banco escolhido, conforme decisão do usuário.

O banco atualmente configurado é de desenvolvimento e seus dados são
descartáveis, conforme confirmado pelo usuário. Não volte a solicitar essa
confirmação para atividades de desenvolvimento nesse banco. Ainda assim,
verifique o destino antes de operações destrutivas, preserve o isolamento
entre empresas e não estenda essa autorização a outros ambientes ou a dados
de produção. Quando houver dúvida sobre o destino, confirme antes de agir.

- Utilizar armazenamento persistente em produção.
- Documentar e testar backup consistente e restauração em ambiente isolado.
- Separar credenciais de aplicação e administração, com privilégios mínimos.
- Evitar operações demoradas dentro de transações.
- Tratar concorrência, bloqueios e erros de conexão.

Não migrar para outro banco sem autorização.

## 18. Testes obrigatórios

Criar testes para, no mínimo:

- Isolamento de dados entre empresas.
- Autenticação e autorização.
- Registro e finalização de vendas.
- Venda dividida entre Pix, dinheiro e fiado.
- Rejeição de divergência no fechamento da venda.
- Pagamentos parciais e totais de recebíveis.
- Rejeição de pagamento superior ao saldo devido.
- Finalização de comanda sem duplicação de vendas.
- Pagamento parcial e integral de contas a pagar.
- Cálculo de indicadores sem dupla contagem.
- Planejamento por dia da semana e calendário real.
- Sobrescrita de previsão diária.
- Fechamento e reabertura de caixa.
- Bloqueio de lançamentos em datas fechadas.
- Tratamento de falhas da API Gemini.
- Proteção CSRF e validação de permissões.

Não considerar uma funcionalidade concluída apenas porque sua tela foi criada.

## 19. Documentação e entrega

Manter atualizados:

- README.md com instalação, execução e configuração.
- `.env.example` sem segredos reais.
- `requirements.txt`.
- Migrações do Django.
- Instruções para criar o usuário administrador.
- Instruções de backup e restauração.
- Instruções para configurar a API Gemini.
- Instruções para executar os testes.
- Limitações conhecidas do MVP.

## 20. Regra final para o agente

Antes de implementar qualquer funcionalidade:

1. Ler este arquivo e os requisitos relacionados.
2. Inspecionar o código existente.
3. Identificar impactos sobre os fluxos financeiros.
4. Implementar a regra de negócio no backend.
5. Criar ou atualizar os testes.
6. Executar verificações relevantes.
7. Corrigir os erros encontrados.
8. Informar o que foi implementado, o que foi testado e o que permanece pendente.

Nunca afirmar que testes passaram sem executá-los.

Em caso de conflito entre uma alteração solicitada e as regras de integridade financeira ou segurança, explicar o conflito e propor uma implementação segura.

Não alterar as tecnologias ou decisões centrais do projeto sem autorização explícita.
