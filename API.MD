# Fomezinha — Endpoints da API

**Base URL:** `https://fomezinha.com.br`  
**Todas as rotas protegidas exigem header:** `Authorization: Bearer <accessToken>`  
**Content-Type:** `application/json`

---

## 🔑 Endpoints usados pelo Print Client

Estes são os únicos endpoints necessários para o software de impressão:

| Método | URL | Descrição |
|--------|-----|-----------|
| `POST` | `/api/auth/login` | Login — obtém o token |
| `POST` | `/api/auth/refresh` | Renova o token |
| `GET`  | `/api/restaurants` | Lista os restaurantes do usuário |
| `GET`  | `/api/orders/:restaurantId` | Lista pedidos (filtrável por status) |
| `PUT`  | `/api/orders/:id/status` | Atualiza status do pedido |

### Exemplo de fluxo completo:

```
1. POST https://fomezinha.com.br/api/auth/login
   Body: { "email": "...", "password": "..." }
   → retorna: { accessToken, refreshToken, user }

2. GET https://fomezinha.com.br/api/restaurants
   Header: Authorization: Bearer <accessToken>
   → retorna: [ { id, name, slug, ... } ]

3. GET https://fomezinha.com.br/api/orders/<restaurantId>?status=PENDING&limit=50
   Header: Authorization: Bearer <accessToken>
   → retorna: { orders: [...], total, page, totalPages }

4. PUT https://fomezinha.com.br/api/orders/<orderId>/status
   Header: Authorization: Bearer <accessToken>
   Body: { "status": "RECEIVED" }
```

### Status de pedido válidos:
`PENDING` → `RECEIVED` → `ACCEPTED` → `PREPARING` → `OUT_FOR_DELIVERY` → `DELIVERED` / `CANCELLED`

### Socket.IO (tempo real — alternativa ao polling):
```
URL: https://fomezinha.com.br
Evento para entrar na sala: join-restaurant  →  payload: restaurantId
Evento recebido p/ novo pedido: new-order    →  payload: { order }
```

---

## 🔐 Autenticação

### `POST /api/auth/login`
```json
// Request
{ "email": "loja@email.com", "password": "senha123" }

// Response 200
{
  "user": { "id": "...", "name": "...", "email": "...", "role": "ADMIN" },
  "accessToken": "eyJ...",
  "refreshToken": "eyJ..."
}
```

### `POST /api/auth/refresh`
```json
// Request
{ "refreshToken": "eyJ..." }

// Response 200
{ "accessToken": "eyJ...", "refreshToken": "eyJ..." }
```

### `POST /api/auth/register`
```json
{ "name": "...", "email": "...", "password": "...", "phone": "..." }
```

### `GET /api/auth/me`
Retorna dados do usuário logado.

---

## 🏪 Restaurantes — `/api/restaurants`

| Método | URL | Descrição |
|--------|-----|-----------|
| `GET`  | `/api/restaurants` | Lista restaurantes do usuário |
| `GET`  | `/api/restaurants/:id` | Busca restaurante por ID |
| `POST` | `/api/restaurants` | Cria restaurante |
| `PUT`  | `/api/restaurants/:id` | Atualiza restaurante |
| `DELETE` | `/api/restaurants/:id` | Exclui restaurante |
| `GET`  | `/api/restaurants/:id/products/options` | Produtos e variações para PDV |

### `GET /api/public/restaurant/:slug` *(público, sem auth)*
Retorna dados públicos do restaurante (cardápio, etc.).

---

## 📦 Pedidos — `/api/orders`

| Método | URL | Descrição | Auth |
|--------|-----|-----------|------|
| `GET`  | `/api/orders/:restaurantId` | Lista pedidos | ✅ |
| `PUT`  | `/api/orders/:id/status` | Atualiza status | ✅ |
| `POST` | `/api/orders/public` | Cliente cria pedido | ❌ |
| `POST` | `/api/orders/public/pdv` | Pedido via PDV | ✅ |
| `GET`  | `/api/orders/public/:id` | Rastrear pedido (cliente) | ❌ |
| `GET`  | `/api/orders/public/last-order?phone=&restaurantId=` | Último pedido do cliente | ❌ |

### `GET /api/orders/:restaurantId`
Query params: `status`, `page`, `limit`

```json
// Response 200
{
  "orders": [
    {
      "id": "uuid",
      "orderNumber": 42,
      "status": "PENDING",
      "orderType": "DELIVERY",
      "customerName": "João Silva",
      "customerPhone": "(11) 99999-0000",
      "deliveryAddress": "Rua X, 123",
      "paymentMethod": "PIX",
      "total": "49.90",
      "deliveryFee": "5.00",
      "changeFor": null,
      "observations": "Sem cebola",
      "createdAt": "2026-06-09T17:00:00.000Z",
      "table": null,
      "items": [
        {
          "id": "...",
          "quantity": 2,
          "unitPrice": "22.45",
          "totalPrice": "44.90",
          "observations": "Bem passado",
          "product": { "name": "X-Bacon", "image": "..." },
          "flavors": [],
          "additionals": [],
          "variations": []
        }
      ]
    }
  ],
  "total": 5,
  "page": 1,
  "totalPages": 1
}
```

### `PUT /api/orders/:id/status`
```json
// Request
{ "status": "RECEIVED" }

// Para cancelar:
{ "status": "CANCELLED", "cancelReason": "Cliente pediu cancelamento" }
```

---

## 🍽️ Categorias — `/api/categories`

| Método | URL | Descrição |
|--------|-----|-----------|
| `GET`  | `/api/categories/:restaurantId` | Lista categorias |
| `POST` | `/api/categories` | Cria categoria |
| `PUT`  | `/api/categories/:id` | Atualiza categoria |
| `DELETE` | `/api/categories/:id` | Exclui categoria |

---

## 🍕 Produtos — `/api/products`

| Método | URL | Descrição |
|--------|-----|-----------|
| `GET`  | `/api/products/category/:categoryId` | Produtos de uma categoria |
| `GET`  | `/api/products/:id` | Produto por ID |
| `POST` | `/api/products` | Cria produto |
| `PUT`  | `/api/products/:id` | Atualiza produto |
| `PATCH` | `/api/products/:id/toggle` | Ativa/desativa produto |
| `DELETE` | `/api/products/:id` | Exclui produto |

---

## ⚙️ Configurações — `/api/settings`

| Método | URL | Descrição |
|--------|-----|-----------|
| `GET`  | `/api/settings/:restaurantId` | Busca configurações |
| `PUT`  | `/api/settings/:restaurantId` | Salva configurações |

---

## 🕐 Horários de Funcionamento — `/api/business-hours`

| Método | URL | Descrição |
|--------|-----|-----------|
| `GET`  | `/api/business-hours/:restaurantId` | Lista horários |
| `PUT`  | `/api/business-hours/:restaurantId` | Salva horários |
| `GET`  | `/api/business-hours/public/:restaurantId` | Verifica se está aberto (público) |

---

## 🪑 Mesas — `/api/tables`

| Método | URL | Descrição |
|--------|-----|-----------|
| `GET`  | `/api/tables/:restaurantId` | Lista mesas |
| `POST` | `/api/tables` | Cria mesa |
| `PUT`  | `/api/tables/:id` | Atualiza mesa |
| `DELETE` | `/api/tables/:id` | Exclui mesa |

---

## 💰 Caixa — `/api/cash-register`

| Método | URL | Descrição |
|--------|-----|-----------|
| `POST` | `/api/cash-register/open` | Abre caixa |
| `POST` | `/api/cash-register/close` | Fecha caixa |
| `POST` | `/api/cash-register/movement` | Registro de movimento (sangria/depósito) |
| `GET`  | `/api/cash-register/current/:restaurantId` | Caixa aberto atual |
| `GET`  | `/api/cash-register/restaurant/:restaurantId` | Histórico de caixas |
| `GET`  | `/api/cash-register/movements/:registerId` | Movimentos de um caixa |
| `GET`  | `/api/cash-register/:id` | Caixa por ID |

---

## 📊 Dashboard — `/api/dashboard`

| Método | URL | Descrição |
|--------|-----|-----------|
| `GET`  | `/api/dashboard/:restaurantId/overview` | Resumo geral (`?period=month`) |
| `GET`  | `/api/dashboard/:restaurantId/sales-chart` | Gráfico de vendas |
| `GET`  | `/api/dashboard/:restaurantId/top-products` | Produtos mais vendidos |
| `GET`  | `/api/dashboard/:restaurantId/order-types` | Pedidos por tipo |
| `GET`  | `/api/dashboard/:restaurantId/payment-methods` | Pedidos por pagamento |
| `GET`  | `/api/dashboard/:restaurantId/hourly-sales` | Vendas por hora |
| `GET`  | `/api/dashboard/:restaurantId/recent-orders` | Pedidos recentes |
| `GET`  | `/api/dashboard/:restaurantId/top-customers` | Clientes top |

---

## 🖨️ Impressão — `/api/printer`

| Método | URL | Descrição |
|--------|-----|-----------|
| `POST` | `/api/printer/register` | Registra impressora desktop |
| `GET`  | `/api/printer/list` | Lista impressoras do restaurante |
| `POST` | `/api/printer/print` | Envia pedido para impressão |
| `POST` | `/api/printer/status` | Atualiza status da impressora |
| `GET`  | `/api/printer/config/:restaurantId` | Config de impressão |

---

## 🔧 Grupos de Variações, Adicionais e Sabores

| Método | URL | Descrição |
|--------|-----|-----------|
| `GET`  | `/api/variation-groups/:restaurantId` | Lista grupos de variação |
| `POST` | `/api/variation-groups` | Cria grupo |
| `PUT`  | `/api/variation-groups/:id` | Atualiza grupo |
| `DELETE` | `/api/variation-groups/:id` | Exclui grupo |
| `GET`  | `/api/additional-groups/:restaurantId` | Lista grupos de adicionais |
| `POST` | `/api/additional-groups` | Cria grupo |
| `PUT`  | `/api/additional-groups/:id` | Atualiza grupo |
| `DELETE` | `/api/additional-groups/:id` | Exclui grupo |
| `GET`  | `/api/flavor-groups/:restaurantId` | Lista grupos de sabores |
| `POST` | `/api/flavor-groups` | Cria grupo |
| `PUT`  | `/api/flavor-groups/:id` | Atualiza grupo |
| `DELETE` | `/api/flavor-groups/:id` | Exclui grupo |

---

## 🎰 Sorteios/Gamificação — `/api/raffles`

| Método | URL | Descrição | Auth |
|--------|-----|-----------|------|
| `GET`  | `/api/raffles` | Lista sorteios | ✅ |
| `GET`  | `/api/raffles/active` | Sorteio ativo | ✅ |
| `GET`  | `/api/raffles/metrics` | Métricas | ✅ |
| `GET`  | `/api/raffles/ranking/:raffleId` | Ranking | ✅ |
| `POST` | `/api/raffles` | Cria sorteio | ✅ |
| `PUT`  | `/api/raffles/:id` | Atualiza sorteio | ✅ |
| `POST` | `/api/raffles/:id/draw` | Realiza sorteio | ✅ |
| `GET`  | `/api/raffles/winner/:resultId` | Detalhe do ganhador | ✅ |
| `GET`  | `/api/raffles/public/:slug` | Página pública do sorteio | ❌ |
| `POST` | `/api/raffles/customer/identify` | Login do cliente (por telefone) | ❌ |
| `POST` | `/api/raffles/referral/:code/click` | Registra clique em referral | ❌ |

---

## 🤖 IA — Assistente de Voz

| Método | URL | Descrição |
|--------|-----|-----------|
| `POST` | `/api/voice-assistant/interpret` | Interpreta comando de voz |
| `POST` | `/api/voice-assistant/execute` | Executa ação confirmada |

---

## 👤 Perfil — `/api/profile`

| Método | URL | Descrição |
|--------|-----|-----------|
| `GET`  | `/api/profile` | Dados do usuário logado |
| `PUT`  | `/api/profile` | Atualiza nome/email/telefone |
| `PUT`  | `/api/profile/password` | Altera senha |

---

## 🛠️ Utilitários

| Método | URL | Descrição | Auth |
|--------|-----|-----------|------|
| `GET`  | `/api/health` | Health check do servidor | ❌ |
| `GET`  | `/api/config/maps-key` | Chave do Google Maps | ✅ |
| `POST` | `/api/upload` | Upload de imagem | ✅ |

---

## 📡 Socket.IO — Eventos em Tempo Real

**URL de conexão:** `https://fomezinha.com.br`

| Evento (cliente → servidor) | Payload | Descrição |
|-----------------------------|---------|-----------|
| `join-restaurant` | `restaurantId` | Entra na sala do restaurante |
| `join-order` | `orderId` | Acompanha um pedido específico |
| `leave-order` | `orderId` | Sai da sala do pedido |
| `join-printers` | `restaurantId` | Registra impressora na sala |
| `printer-status` | `{ printerId, status }` | Atualiza status da impressora |

| Evento (servidor → cliente) | Payload | Descrição |
|-----------------------------|---------|-----------|
| `new-order` | `{ order }` | Novo pedido recebido |
| `order-updated` | `{ order }` | Pedido atualizado |
| `print-order` | `{ order, config }` | Pedido para impressão |
