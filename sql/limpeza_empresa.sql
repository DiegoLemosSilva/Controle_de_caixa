-- USO EM DESENVOLVIMENTO: não validado para produção.
-- Não é ON DELETE CASCADE: é um gatilho que executa como o operador.
-- Instale apenas após conferir o banco e o schema de destino.
-- Esta rotina não remove sessões Django serializadas nem logs cujo objeto
-- não pode ser associado à empresa. Veja a documentação antes de usar.

CREATE OR REPLACE FUNCTION limpeza_empresa_antes_delete()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path FROM CURRENT
AS $$
DECLARE
    usuarios bigint[];
    permissao boolean;
    registro record;
BEGIN
    SELECT rolsuper OR rolbypassrls INTO permissao
      FROM pg_catalog.pg_roles WHERE rolname = current_user;
    IF permissao IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'A limpeza requer papel administrativo com visibilidade integral (BYPASSRLS).';
    END IF;

    -- Falhar se uma FK puder produzir efeitos automáticos fora deste plano.
    IF EXISTS (
        SELECT 1
          FROM pg_catalog.pg_constraint c
         WHERE c.contype = 'f'
           AND c.confdeltype NOT IN ('a', 'r')
           AND c.confrelid = ANY (ARRAY[
               'businesses_business'::regclass, 'businesses_businessowner'::regclass,
               'auth_user'::regclass, 'customers_customer'::regclass,
               'products_product'::regclass, 'sales_sale'::regclass,
               'sales_comanda'::regclass, 'sales_salepayment'::regclass,
               'sales_comandaitem'::regclass, 'sales_comandapayment'::regclass,
               'receivables_receivable'::regclass, 'receivables_receivablepayment'::regclass,
               'payables_payable'::regclass, 'payables_payablepayment'::regclass,
               'cash_cashsession'::regclass, 'cash_cashsessionevent'::regclass,
               'cash_cashcountadjustment'::regclass, 'planning_financialplan'::regclass,
               'ai_assistant_aiinteraction'::regclass
           ]::oid[])
    ) THEN
        RAISE EXCEPTION 'Existem chaves com ações automáticas que exigem revisão antes da limpeza.';
    END IF;

    PERFORM 1 FROM businesses_businessowner WHERE business_id = OLD.id FOR UPDATE;
    SELECT COALESCE(array_agg(user_id), ARRAY[]::bigint[])
      INTO usuarios FROM businesses_businessowner WHERE business_id = OLD.id;
    PERFORM 1 FROM auth_user WHERE id = ANY(usuarios) FOR UPDATE;

    -- Logs genéricos não têm FK para o objeto registrado. Remover apenas
    -- aqueles que apontam para objetos desta empresa ou seus usuários.
    FOR registro IN
        SELECT * FROM (VALUES
            ('businesses', 'business', 'businesses_business', 'obj.id = $1'),
            ('businesses', 'businessowner', 'businesses_businessowner', 'business_id = $1'),
            ('auth', 'user', 'auth_user', 'obj.id = ANY($2)'),
            ('customers', 'customer', 'customers_customer', 'business_id = $1'),
            ('products', 'product', 'products_product', 'business_id = $1'),
            ('sales', 'sale', 'sales_sale', 'business_id = $1'),
            ('sales', 'salepayment', 'sales_salepayment', 'sale_id IN (SELECT id FROM sales_sale WHERE business_id = $1)'),
            ('sales', 'comanda', 'sales_comanda', 'business_id = $1'),
            ('sales', 'comandaitem', 'sales_comandaitem', 'comanda_id IN (SELECT id FROM sales_comanda WHERE business_id = $1)'),
            ('sales', 'comandapayment', 'sales_comandapayment', 'comanda_id IN (SELECT id FROM sales_comanda WHERE business_id = $1)'),
            ('receivables', 'receivable', 'receivables_receivable', 'business_id = $1'),
            ('receivables', 'receivablepayment', 'receivables_receivablepayment', 'receivable_id IN (SELECT id FROM receivables_receivable WHERE business_id = $1)'),
            ('payables', 'payable', 'payables_payable', 'business_id = $1'),
            ('payables', 'payablepayment', 'payables_payablepayment', 'payable_id IN (SELECT id FROM payables_payable WHERE business_id = $1)'),
            ('cash', 'cashsession', 'cash_cashsession', 'business_id = $1'),
            ('cash', 'cashsessionevent', 'cash_cashsessionevent', 'session_id IN (SELECT id FROM cash_cashsession WHERE business_id = $1)'),
            ('cash', 'cashcountadjustment', 'cash_cashcountadjustment', 'business_id = $1'),
            ('planning', 'financialplan', 'planning_financialplan', 'business_id = $1'),
            ('ai_assistant', 'aiinteraction', 'ai_assistant_aiinteraction', 'business_id = $1')
        ) AS modelos(app, modelo, tabela, condicao)
    LOOP
        -- Logs cujo objeto não existe são preservados: não é possível
        -- atribuí-los com segurança à empresa que está sendo removida.
        EXECUTE format(
            'DELETE FROM django_admin_log l USING django_content_type ct '
            'WHERE l.content_type_id = ct.id AND ct.app_label = %L AND ct.model = %L '
            'AND EXISTS (SELECT 1 FROM %I obj WHERE obj.id::text = l.object_id AND %s)',
            registro.app, registro.modelo, registro.tabela, registro.condicao
        ) USING OLD.id, usuarios;
    END LOOP;

    -- Filhos antes dos pais; as restrições entre empresas permanecem ativas.
    DELETE FROM sales_comandapayment
      WHERE comanda_id IN (SELECT id FROM sales_comanda WHERE business_id = OLD.id);
    DELETE FROM sales_comandaitem
      WHERE comanda_id IN (SELECT id FROM sales_comanda WHERE business_id = OLD.id);
    DELETE FROM receivables_receivablepayment
      WHERE receivable_id IN (SELECT id FROM receivables_receivable WHERE business_id = OLD.id);
    DELETE FROM payables_payablepayment
      WHERE payable_id IN (SELECT id FROM payables_payable WHERE business_id = OLD.id);
    DELETE FROM sales_salepayment
      WHERE sale_id IN (SELECT id FROM sales_sale WHERE business_id = OLD.id);
    DELETE FROM cash_cashsessionevent
      WHERE session_id IN (SELECT id FROM cash_cashsession WHERE business_id = OLD.id);

    DELETE FROM receivables_receivable WHERE business_id = OLD.id;
    DELETE FROM sales_comanda WHERE business_id = OLD.id;
    DELETE FROM sales_sale WHERE business_id = OLD.id;
    DELETE FROM payables_payable WHERE business_id = OLD.id;
    DELETE FROM cash_cashcountadjustment WHERE business_id = OLD.id;
    DELETE FROM cash_cashsession WHERE business_id = OLD.id;
    DELETE FROM planning_financialplan WHERE business_id = OLD.id;
    DELETE FROM ai_assistant_aiinteraction WHERE business_id = OLD.id;
    DELETE FROM products_product WHERE business_id = OLD.id;
    DELETE FROM customers_customer WHERE business_id = OLD.id;
    DELETE FROM businesses_businessowner WHERE business_id = OLD.id;

    DELETE FROM auth_user_groups WHERE user_id = ANY(usuarios);
    DELETE FROM auth_user_user_permissions WHERE user_id = ANY(usuarios);

    -- Não apagar logs de outras empresas. Logs existentes para os usuários
    -- ou referências financeiras externas impedirão a exclusão pela FK.
    DELETE FROM auth_user WHERE id = ANY(usuarios);
    RETURN OLD;
END;
$$;

CREATE TRIGGER limpeza_empresa_antes_delete
BEFORE DELETE ON businesses_business
FOR EACH ROW EXECUTE FUNCTION limpeza_empresa_antes_delete();
