# 🍕 Fomezinha Print Client

Software de impressão automática de pedidos para o sistema Fomezinha.  
Roda na bandeja do sistema (sem janela fixa) e imprime automaticamente cada novo pedido.

---

## Requisitos

- **Windows 10/11** (ou Linux)
- **Python 3.11+** — [python.org/downloads](https://www.python.org/downloads/)  
  ⚠️ Marque **"Add Python to PATH"** durante a instalação

---

## Instalação rápida (Windows)

1. Baixe e extraia esta pasta
2. Dê duplo clique em **`instalar_windows.bat`**
3. O instalador fará tudo automaticamente:
   - Instala as dependências Python
   - Cria atalho na Área de Trabalho
   - Pergunta se quer iniciar com o Windows

---

## Uso

1. Abra **Fomezinha Print** (atalho na Área de Trabalho)
2. Na aba **Conexão**:
   - Preencha o endereço do servidor (ex: `https://fomezinha.com.br`)
   - E-mail e senha do lojista
   - Clique em **Conectar e Iniciar**
3. Na aba **Impressora**:
   - Selecione o tipo de impressora
   - Clique em **Imprimir Teste** para verificar
4. Feche a janela — o programa continua ativo na **bandeja do sistema** (ícone perto do relógio)

---

## Tipos de impressora

### 🖨️ Impressora do Sistema (mais simples)
Qualquer impressora instalada no Windows (térmica ou comum).  
Basta selecionar na lista.

### 🔌 Térmica USB/Serial (ESC/POS)
Requer `python-escpos` (já incluído).  
Para USB: instale o driver da impressora primeiro.  
Para Serial: informe a porta (ex: `COM3`).

### 🌐 Térmica de Rede (TCP/IP)
Informe o IP da impressora na rede local.  
Porta padrão: **9100**.

---

## Gerar executável (.exe) — sem precisar de Python

```bat
# No Windows, execute:
build_windows.bat

# O .exe estará em: dist\FomezinhaPrint.exe
```

Distribua o `.exe` para os clientes — **não precisam ter Python instalado**.

---

## Configurações salvas

Ficam em `%USERPROFILE%\.fomezinha-print\config.json`  
Log em `%USERPROFILE%\.fomezinha-print\app.log`

---

## Funcionalidades

- ✅ Polling automático de pedidos novos (intervalo configurável)
- ✅ Impressão em impressoras térmicas ESC/POS (USB, Rede, Serial)
- ✅ Impressão em qualquer impressora do sistema
- ✅ Som de alerta a cada novo pedido
- ✅ Aceite automático do pedido após imprimir (opcional)
- ✅ Ícone na bandeja — sem ocupar a barra de tarefas
- ✅ Inicia automaticamente com o Windows (opcional)
- ✅ Reautenticação automática se o token expirar
- ✅ Log completo de todas as operações
- ✅ Não fecha o navegador nem interfere em outros programas

---

## Recibo impresso

Cada pedido imprime automaticamente:
- Nome do restaurante
- Número do pedido, data e hora
- Tipo: DELIVERY / RETIRADA / MESA / BALCÃO
- Lista de itens com quantidade, preço, variações, adicionais, sabores e observações
- Total, forma de pagamento, troco
- Nome, telefone e endereço do cliente
- Observações gerais
