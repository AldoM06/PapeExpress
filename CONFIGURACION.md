# Configuración: Telegram + Stripe

## 1. Notificaciones a Telegram

### Crear el bot
1. Abre Telegram y busca **@BotFather**
2. Escribe `/newbot` y sigue las instrucciones
3. Copia el **token** que te da (ej: `7123456789:AAF...`)

### Obtener el Chat ID
- **Grupo**: Agrega el bot al grupo, luego ve a:
  `https://api.telegram.org/bot<TU_TOKEN>/getUpdates`
  El `chat.id` del grupo empieza con `-100...`
- **Canal**: Agrega el bot como admin al canal. El ID también empieza con `-100...`

### Configurar en Django
Edita `papeexpress/settings.py`:
```python
TELEGRAM_BOT_TOKEN = '7123456789:AAF-tu-token-aqui'
TELEGRAM_CHAT_ID   = '-1001234567890'
```

### ¿Cuándo llegan notificaciones?
- ✅ Cuando una figura avanza de etapa (con emoji, % de avance, quién lo actualizó)
- 🛒 Cuando un socio registra un pedido nuevo
- 💳 Cuando se confirma un pago con Stripe

---

## 2. Pagos con Stripe

### Crear cuenta
1. Ve a [stripe.com](https://stripe.com) y crea una cuenta
2. En el **Dashboard** → **Developers** → **API Keys**
3. Copia la **Publishable key** (`pk_test_...`) y la **Secret key** (`sk_test_...`)

### Webhook (para confirmación automática)
1. En Stripe Dashboard → **Developers** → **Webhooks**
2. Agrega endpoint: `https://tudominio.com/socios/webhook/stripe/`
3. Selecciona el evento: `checkout.session.completed`
4. Copia el **Signing secret** (`whsec_...`)

### Configurar en Django
```python
STRIPE_PUBLIC_KEY     = 'pk_test_...'
STRIPE_SECRET_KEY     = 'sk_test_...'
STRIPE_WEBHOOK_SECRET = 'whsec_...'
```

### ¿Cómo funciona el flujo de pago?
1. Socio elige figura + cantidad en el **Portal de Socios** (`/socios/portal/`)
2. Confirma el pedido → redirige a **Stripe Checkout** (página segura de Stripe)
3. Socio paga con tarjeta
4. Stripe notifica al webhook → se actualiza el estado a **Pagado**
5. El inventario (`cantidad_disponible`) se descuenta automáticamente
6. Llega notificación a **Telegram** confirmando el pago

### Modo prueba
Usa la tarjeta de prueba de Stripe:
- Número: `4242 4242 4242 4242`
- Fecha: cualquier fecha futura
- CVC: cualquier 3 dígitos

---

## 3. Archivos de figuras Fomy

En el detalle de cada figura puedes subir/actualizar/eliminar:

| Archivo | Extensión | Uso |
|---------|-----------|-----|
| Plantilla Studio3 | `.studio3` | Archivo para la máquina de corte Silhouette |
| Instrucciones PDF | `.pdf` | Guía de armado para el equipo |
| Instrucciones Word | `.docx` | Versión editable para actualizar |
| Fotos (hasta 4) | `.jpg`, `.png` | Referencia visual de cómo debe quedar |

---

## 4. Portal de socios

- URL: `/socios/portal/`
- Solo accesible para usuarios con `rol = 'socio'`
- Para asignar el perfil de socio a un usuario:
  1. Ve al admin Django → **Socios Comerciales**
  2. Edita el socio y selecciona el usuario en el campo **Usuario**

---

## 5. Sistema POS

### Sucursales incluidas
- **Hércules** — Mayoreo y Menudeo
- **Maury** — Menudeo (ofertas y promociones)
- **Roshita** — Menudeo

### Accesos
| URL | Descripción |
|-----|-------------|
| `/pos/` | Pantalla de cobro (cajero) |
| `/pos/admin-pos/` | Dashboard de ventas y ganancias |
| `/pos/inventario/` | Control de inventario |
| `/pos/creditos/` | Ventas a crédito y abonos |
| `/pos/anticipos/` | Pedidos con anticipo |
| `/pos/compras/` | Entradas de mercancía + análisis IA |
| `/pos/precios/comparar/` | Comparativa entre proveedores |

### Asignar usuarios a sucursales
1. Ve al Admin Django → **Usuarios de Sucursal**
2. Asigna el usuario a su sucursal y rol (cajero, gerente, almacén)
3. El POS detecta automáticamente la sucursal al iniciar sesión

### Precios por sucursal
Cada producto tiene **3 niveles de precio** por sucursal:
- Precio 1 = Menudeo
- Precio 2 = Mayoreo
- Precio 3 = Especial/Promoción

El cajero puede cambiar el nivel de precio por ítem directamente en el POS.

### Análisis de tickets con IA
1. Al registrar una compra, sube la foto del ticket
2. En la lista de compras aparece el botón **"Analizar IA"**
3. Claude extrae: proveedor, fecha, productos y precios automáticamente
4. Requiere `ANTHROPIC_API_KEY` en el `.env`

### Alertas de inventario (Telegram)
- **Inmediata**: cuando una venta baja el stock al mínimo
- **Mediodía**: barrido automático a las 12:00 con todos los productos críticos
- Manual: botón **"Barrido Telegram"** en el dashboard
