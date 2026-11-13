# Operação PostgreSQL e Neon

## Configuração e segurança

O PostgreSQL é o banco da aplicação. Configure `DATABASE_URL` no `.env`
existente ou no ambiente, usando a credencial restrita da aplicação, TLS e
sem versionar credenciais. `DATABASE_ADMIN_URL`, quando armazenada no mesmo
`.env`, é reservada à manutenção e não é usada automaticamente pelo Django.
Proteja o acesso ao arquivo, pois ele pode conter ambas as credenciais.

Separe as credenciais de administração e migração das credenciais da
aplicação. O papel da aplicação não deve ser dono das tabelas nem ter
privilégios de superusuário ou BYPASSRLS. Se uma credencial for exposta,
rotacione-a e atualize a configuração sem registrar o segredo.

Não execute migrações, importações ou testes de ensaio no banco em uso.
Use um banco ou branch comprovadamente descartável, com credenciais
apropriadas, e verifique explicitamente o destino antes de qualquer operação.

## Backup e recuperação

Defina responsáveis, retenção, RPO e RTO. Produza backups PostgreSQL
consistentes com `pg_dump` ou recursos de recuperação do provedor, proteja-os
fora do diretório da aplicação e teste a restauração em ambiente isolado.
Antes de restaurar sobre dados em uso, planeje a interrupção, o destino e a
reconciliação dos lançamentos posteriores ao backup. Nunca restaure
silenciosamente sobre registros mais recentes.

## Auditoria

O comando `python manage.py audit_database_migration` realiza uma auditoria
parcial e somente de leitura no banco configurado. Ele verifica caixas
abertos duplicados, alguns relacionamentos entre empresas e limites de
texto. Não comprova a integridade de todas as chaves, dos valores
monetários, totais, datas, sequências, permissões ou políticas RLS.
Em caso de inconsistência, investigue antes de corrigir dados.

## Isolamento entre empresas

O RLS experimental foi descontinuado. Em instalações novas,
`core.0002_financial_rls` não habilita políticas; em bancos existentes,
`core.0003_disable_application_rls` desativa o RLS nas tabelas dos aplicativos
deste projeto no schema ativo, mantendo políticas inativas e preservando os dados.
Execute a migração com o proprietário das tabelas após confirmar o destino.

O isolamento depende das consultas e validações da aplicação, inclusive no
Admin e nos serviços. A ausência de RLS
remove uma camada de proteção: filtros ausentes podem expor dados entre
empresas. Execute testes de isolamento e revise os fluxos antes de produção.

O Admin padrão depende das permissões Django e pode permitir acesso ou
alteração direta de registros financeiros. Restrinja seu acesso e revise
as permissões e os comandos de gerenciamento antes de produção.

## Concorrência financeira

A constraint de caixa aberto e os bloqueios por empresa protegem cenários
específicos. Os testes concorrentes existentes não comprovam todos os fluxos.
Antes de produção, revise especialmente cancelamentos, comandas,
fechamentos, reaberturas e alterações administrativas para assegurar que
compartilhem o mesmo protocolo de bloqueio. Teste com transações e conexões
PostgreSQL independentes, incluindo rollback, timeouts, pagamentos
concorrentes e finalizações duplicadas.

## Limpeza de empresa pelo PostgreSQL

O gatilho de `sql/limpeza_empresa.sql` foi instalado no schema `public` do
banco de desenvolvimento `neondb`. Ele não é uma constraint `ON DELETE
CASCADE`: executa uma limpeza antes da exclusão de uma empresa, usando as
permissões do operador. **Não está validado para produção.**

No DBeaver, conecte-se ao banco de desenvolvimento com uma credencial
administrativa que tenha visibilidade integral (`BYPASSRLS` ou superusuário).
Confira o banco e o ID da empresa antes de executar, em uma transação:

```sql
BEGIN;
SELECT current_database(), current_user;
SELECT id, name FROM public.businesses_business WHERE id = 123;

-- Somente após conferir o resultado acima:
DELETE FROM public.businesses_business WHERE id = 123 RETURNING id, name;

-- Confira o resultado e escolha apenas uma opção:
ROLLBACK; -- cancela a operação
-- COMMIT; -- confirma a exclusão definitiva
```

Substitua `123` pelo ID conferido. Desative o auto-commit no DBeaver e
execute os comandos por etapas; `ROLLBACK` e `COMMIT` são alternativas.
Em caso de erro, reverta a transação e investigue a causa.

Os ensaios em schema temporário cobriram a exclusão de dados fictícios dos
modelos selecionados, preservação de outra empresa e bloqueio por referências
cruzadas e logs externos. Também verificaram a recusa do papel da aplicação
em um schema de teste e cenários concorrentes específicos de inserção de
cliente. Não abrangem todos os fluxos concorrentes nem provam segurança para
implantação.

O rascunho remove logs genéricos do Admin apenas quando consegue associá-los
a objetos ainda existentes no momento da exclusão. Conforme decisão do
usuário, logs sem objeto e sem empresa identificável são preservados. Caso
um desses logs esteja vinculado a um usuário que seria excluído, a chave
estrangeira pode bloquear toda a operação. Logs ou referências de outras
empresas associados aos usuários também podem bloquear a exclusão.
Backups e cópias externas não são automaticamente eliminados.

A exclusão, quando implementada e autorizada, será irreversível e exigirá
backup consistente com restauração testada, identificação inequívoca da
empresa, credencial administrativa apropriada e confirmação da transação.
Não conceda essa capacidade ao papel da aplicação. Referências de outra
empresa podem impedir a exclusão inteira e exigem investigação, não sua
remoção indiscriminada.

Conforme decisão do usuário, sessões Django serializadas não serão apagadas
pela rotina. Excluir a conta impede sua autenticação, mas a linha e seus
dados podem permanecer mesmo depois de expirarem. A remoção de sessões
expiradas exige uma rotina própria, como `python manage.py clearsessions`,
avaliada e agendada separadamente.

## Testes

Execute testes apenas contra um servidor ou branch descartável, com
credenciais apropriadas para criação do banco de testes Django. Confirme a
URL efetiva e defina a URL do ambiente descartável como `DATABASE_URL` apenas
na sessão de testes. Não forneça ao teste credenciais com acesso destrutivo ao
banco real. Valide as migrações e o isolamento por empresa no ambiente isolado.
