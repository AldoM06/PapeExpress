# PapeExpress 📦

Sitio web completo para **PapeExpress** — Fabricantes y distribuidores de papelería.  
Construido con **Django 4.2 + Bootstrap 5 + Channels (WebSocket)**.

---

## 🚀 Instalación rápida

```bash
# 1. Clona o descomprime el proyecto
cd papeexpress

# 2. Ejecuta el setup automático (crea venv, migra, carga datos demo, crea admin)
chmod +x setup.sh
./setup.sh

# 3. Inicia el servidor
source venv/bin/activate
python manage.py runserver
```

Abre tu navegador en **http://127.0.0.1:8000**

---

## 🔑 Acceso inicial

| URL | Usuario | Contraseña |
|-----|---------|------------|
| `/admin/` | `admin` | `admin123` |
| `/accounts/login/` | `admin` | `admin123` |

> ⚠️ **Cambia la contraseña antes de poner en producción**

---

## 📋 Estructura del proyecto

```
papeexpress/
├── papeexpress/        # Configuración Django + ASGI/WebSocket
├── core/               # Productos, Categorías, Contacto, Config del sitio
├── accounts/           # Usuarios con roles, login, dashboards
├── produccion/         # Pipeline de figuras Fomy + WebSocket tiempo real
├── socios/             # Socios comerciales + mapa Leaflet
├── templates/          # Todos los templates HTML
│   ├── base.html
│   ├── index.html          ← Hero 3D animado con partículas
│   ├── productos.html      ← Catálogo con filtros
│   ├── nosotros.html       ← Historia / Misión / Visión
│   ├── contacto.html       ← Formulario de contacto
│   ├── registration/       ← Login y registro
│   ├── dashboard/          ← Dashboards por rol
│   ├── produccion/         ← Kanban y detalle de figuras
│   └── socios/             ← Mapa interactivo
└── static/
    ├── css/main.css
    └── js/main.js
```

---

## 👥 Roles de usuario

| Rol | Acceso |
|-----|--------|
| `admin` | Panel completo, admin Django |
| `socio` | Dashboard con producción en **tiempo real** (WebSocket) |
| `ventas` | Catálogo, contactos, red de socios |
| `almacen` | Inventario, figuras fomy |
| `diseño` / `produccion` | Pipeline de producción |
| `cliente` | Catálogo y contacto |

---

## ✨ Funcionalidades principales

### 🏠 Página de inicio
- Hero con animación de **partículas 3D** (canvas)
- Tarjeta flotante 3D mostrando estado de producción
- Productos en portada (se activan/desactivan desde el admin)
- Historia, categorías y CTA

### 📦 Catálogo de productos
- **Productos de reventa** (papelería general)
- **Productos fabricados** (figuras fomy y libretas)
- Filtros por categoría y tipo
- Imágenes, precio normal y mayoreo
- Opción `mostrar_en_portada` en el admin

### 🎨 Pipeline de producción (Figuras Fomy)
9 etapas con seguimiento visual:
1. Propuesta → 2. Diseño → 3. Armado Digital → 4. Muestra →
5. Materiales y Costos → 6. Corte → 7. Armado → 8. Embolsado → 9. Etiquetado

- Kanban visual por etapas
- Historial de cambios
- **WebSocket**: los socios comerciales ven el estado en **tiempo real**

### 🗺️ Mapa de socios
- Mapa interactivo con **Leaflet.js** + OpenStreetMap
- Marcadores con popups informativos
- Lista lateral con clic para centrar el mapa
- Se gestionan desde el admin (latitud/longitud)

### 🔐 Sistema de autenticación
- Login/registro con formularios personalizados
- Redirección automática al dashboard según rol
- Protección de vistas con `@login_required`

---

## ⚙️ Gestión desde el Admin Django

Ingresa a `/admin/` para:

- **Productos**: activar/desactivar, marcar para portada, subir imágenes
- **Figuras de Fomy**: avanzar etapas, registrar costos, indicar si hay fomy disponible
- **Socios Comerciales**: agregar con coordenadas para que aparezcan en el mapa
- **Mensajes de contacto**: ver y marcar como leídos
- **Configuración del sitio**: historia, misión, visión, redes sociales
- **Usuarios**: asignar roles

---

## 🔧 Variables de entorno para producción

Crea un archivo `.env` y configura:

```env
SECRET_KEY=tu-clave-secreta-muy-larga
DEBUG=False
ALLOWED_HOSTS=tupdominio.com,www.tudominio.com
DATABASE_URL=postgresql://user:pass@host/dbname

# Para WebSocket en producción, reemplaza InMemoryChannelLayer con Redis:
# REDIS_URL=redis://localhost:6379
```

---

## 📡 WebSocket (tiempo real)

El dashboard de socios conecta via WebSocket a `/ws/produccion/`.  
En desarrollo usa `InMemoryChannelLayer`.  
**En producción** instala Redis y cambia en `settings.py`:

```python
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {'hosts': [('127.0.0.1', 6379)]},
    }
}
```

Inicia con Daphne en lugar de runserver:
```bash
daphne papeexpress.asgi:application
```

---

## 📸 Logo

Coloca tu logo en `static/img/logo.png` y actualiza el navbar en `templates/base.html`.

---

## 🛠 Tecnologías

- **Backend**: Django 4.2, Django Channels 4, Daphne
- **Frontend**: Bootstrap 5.3, Bootstrap Icons, Leaflet.js
- **Tipografía**: Playfair Display + Inter (Google Fonts)
- **BD**: SQLite (dev) / PostgreSQL (prod)
- **Tiempo real**: WebSocket via Django Channels
- **Mapa**: Leaflet.js + OpenStreetMap (gratuito, sin API key)
