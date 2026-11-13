"""Constantes compartilhadas para valores monetários e regras gerais."""

# Precisão monetária padrão definida em AGENTS.md (seção 6).
MONEY_MAX_DIGITS = 12
MONEY_DECIMAL_PLACES = 2

PAYMENT_METHOD_CASH = 'dinheiro'
PAYMENT_METHOD_PIX = 'pix'
PAYMENT_METHOD_DEBIT = 'debito'
PAYMENT_METHOD_CREDIT = 'credito'
PAYMENT_METHOD_OTHER = 'outro'
PAYMENT_METHOD_FIADO = 'fiado'

PAYMENT_METHOD_CHOICES = [
    (PAYMENT_METHOD_CASH, 'Dinheiro'),
    (PAYMENT_METHOD_PIX, 'Pix'),
    (PAYMENT_METHOD_DEBIT, 'Cartão de débito'),
    (PAYMENT_METHOD_CREDIT, 'Cartão de crédito'),
    (PAYMENT_METHOD_OTHER, 'Outro'),
]

# Usado apenas em contextos que precisam oferecer "Fiado" como uma opção
# de pagamento ao lado das formas normais (ex: pagamentos parciais de
# comanda). Os indicadores financeiros (Vendas, Recebimentos) continuam
# tratando Fiado separadamente das demais formas de pagamento.
COMANDA_PAYMENT_METHOD_CHOICES = PAYMENT_METHOD_CHOICES + [
    (PAYMENT_METHOD_FIADO, 'Fiado'),
]
