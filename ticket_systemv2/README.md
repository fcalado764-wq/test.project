# 🎟 Ticket Angola v2 — Sistema Completo

Sistema web de venda de bilhetes com painel de administração, pagamentos Stripe e base de dados PostgreSQL.

## Estrutura do Projecto

```
ticket_system_v2/
├── app.py
├── .env                    ← Configurações (NÃO partilhar)
├── requirements.txt
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── event_detail.html
│   ├── success.html
│   └── admin/
│       ├── base_admin.html
│       ├── login.html
│       ├── dashboard.html
│       ├── events.html
│       ├── event_form.html
│       └── purchases.html
├── static/
│   ├── css/style.css
│   ├── css/admin.css
│   └── js/main.js
└── tickets/                ← PDFs gerados automaticamente
```

## Instalação

### 1. Instalar dependências Python
```bash
/Users/macbook2019/.local/bin/python3.14 -m pip install -r requirements.txt --break-system-packages
```

### 2. Criar base de dados PostgreSQL
```sql
-- No terminal do PostgreSQL:
CREATE DATABASE ticket_angola;
```

### 3. Configurar o ficheiro .env
Edita o ficheiro `.env` com os teus dados:
```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=ticket_angola
DB_USER=postgres
DB_PASSWORD=a_tua_senha
```

### 4. Configurar Stripe (opcional para pagamentos reais)
1. Cria conta em https://stripe.com
2. Vai a Dashboard → Developers → API Keys
3. Copia as chaves de TESTE para o .env:
```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
```
> ⚠️ Sem as chaves Stripe, o sistema funciona em modo demonstração.

### 5. Executar
```bash
/Users/macbook2019/.local/bin/python3.14 app.py
```

Abre: http://localhost:5001

## Credenciais Admin

- URL: http://localhost:5001/admin
- Utilizador: `admin`
- Senha: `admin123`

> ⚠️ **Muda a senha após o primeiro login!**

## Funcionalidades

### Público
- ✅ Lista de eventos com filtros
- ✅ Página de detalhe do evento
- ✅ Pagamento com Stripe (AOA)
- ✅ Geração automática de bilhete PDF
- ✅ Download do bilhete

### Admin (/admin)
- ✅ Login seguro com senha encriptada
- ✅ Dashboard com estatísticas e receitas
- ✅ Criar / Editar / Desactivar eventos
- ✅ Ver todas as compras com estado de pagamento
- ✅ Download de PDFs das compras

## Testar Pagamentos Stripe

Usa os cartões de teste da Stripe:
- Número: `4242 4242 4242 4242`
- Data: qualquer data futura
- CVC: qualquer 3 dígitos
