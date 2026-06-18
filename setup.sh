#!/bin/bash
# ════════════════════════════════════════════════
#  PapeExpress — Script de configuración inicial
# ════════════════════════════════════════════════
set -e

echo "╔══════════════════════════════════════════╗"
echo "║       PapeExpress — Setup inicial        ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# 1. Entorno virtual
echo "→ Creando entorno virtual..."
python3 -m venv venv
source venv/bin/activate

# 2. Copiar .env si no existe
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  → .env creado desde .env.example"
    echo "  ⚠️  Edita el archivo .env con tus credenciales reales"
fi

# 2. Dependencias
echo "→ Instalando dependencias..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "→ Verificando Poppler (necesario para pdf2image)..."
if ! command -v pdftoppm &>/dev/null; then
  echo "  ⚠️  Poppler no encontrado. Instálalo con:"
  echo "       macOS:  brew install poppler"
  echo "       Ubuntu: sudo apt install poppler-utils"
  echo "       Windows: descarga desde https://github.com/oschwartz10612/poppler-windows"
else
  echo "  ✓ Poppler encontrado: $(pdftoppm -v 2>&1 | head -1)"
fi

# 3. Migraciones
echo "→ Aplicando migraciones..."
python manage.py makemigrations accounts core produccion socios calculadora pos
python manage.py migrate

# 4. Datos de ejemplo
echo "→ Cargando configuración inicial del sitio..."
python manage.py shell -c "
from core.models import ConfiguracionSitio, Categoria, Producto
from produccion.models import FiguraFomy
from socios.models import SocioComercial

# Configuración del sitio
cfg = ConfiguracionSitio.get()
cfg.historia = 'PapeExpress nació como un pequeño taller familiar, con una misión clara: ofrecer papelería de calidad a precios accesibles para escuelas, papelerías y negocios locales. Con el tiempo desarrollamos nuestra propia línea de figuras de fomy y libretas con diseños únicos. Hoy contamos con una red de socios en múltiples estados.'
cfg.mision = 'Fabricar y distribuir papelería accesible y de calidad, apoyando el aprendizaje y la creatividad.'
cfg.vision = 'Ser la empresa de papelería mexicana más reconocida por la calidad de sus productos y la solidez de su red de distribución.'
cfg.telefono = '+52 55 0000-0000'
cfg.email = 'hola@papeexpress.mx'
cfg.direccion = 'Estado de México'
cfg.save()

# Categorías reventa
cats_reventa = ['Cuadernos y Libretas', 'Plumas y Marcadores', 'Colores y Pinturas', 'Material Escolar', 'Manualidades']
for n in cats_reventa:
    Categoria.objects.get_or_create(nombre=n, tipo='reventa')

# Categorías fabricados
cats_fab = ['Figuras de Fomy', 'Libretas Artesanales']
for n in cats_fab:
    Categoria.objects.get_or_create(nombre=n, tipo='fabricado')

# Productos de ejemplo
cat_cuad = Categoria.objects.get(nombre='Cuadernos y Libretas')
cat_fig = Categoria.objects.get(nombre='Figuras de Fomy')
cat_lib = Categoria.objects.get(nombre='Libretas Artesanales')

productos_demo = [
    ('Cuaderno Profesional 100 Hojas', cat_cuad, 35.00, True),
    ('Set de Plumas de Colores x12', Categoria.objects.get(nombre='Plumas y Marcadores'), 85.00, True),
    ('Caja de Colores Prismacolor 24', Categoria.objects.get(nombre='Colores y Pinturas'), 220.00, True),
    ('Libreta Artesanal Flores', cat_lib, 65.00, True),
    ('Figura Mariposa Fomy', cat_fig, 25.00, True),
    ('Figura Dinosaurio Fomy', cat_fig, 30.00, False),
]
for nombre, cat, precio, portada in productos_demo:
    Producto.objects.get_or_create(
        nombre=nombre,
        defaults={'categoria': cat, 'precio': precio, 'mostrar_en_portada': portada, 'disponible': True}
    )

# Figuras fomy de ejemplo
figuras_demo = [
    ('Mariposa Primavera', 'corte', 200, True),
    ('Dinosaurio Rex', 'armado', 150, True),
    ('Corazón San Valentín', 'embolsado', 300, True),
    ('Flor Tropical', 'diseño', 100, False),
    ('Estrella Navideña', 'propuesta', 50, False),
]
for nombre, etapa, cant, fomy in figuras_demo:
    FiguraFomy.objects.get_or_create(
        nombre=nombre,
        defaults={'etapa_actual': etapa, 'cantidad_planificada': cant, 'tiene_fomy': fomy}
    )

# Socios de ejemplo
socios_demo = [
    ('Papelería La Escolar', 'Papelería', 'Col. Centro', 'Ecatepec', 'Estado de México', 19.601, -99.061),
    ('Útiles y Más', 'Librería', 'Av. Insurgentes 500', 'Ciudad de México', 'CDMX', 19.432, -99.133),
    ('El Pincel Creativo', 'Tienda de manualidades', 'Plaza Principal', 'Tlalnepantla', 'Estado de México', 19.548, -99.195),
]
for nombre, tipo, dir, ciudad, estado, lat, lng in socios_demo:
    SocioComercial.objects.get_or_create(
        nombre=nombre,
        defaults={'tipo_negocio': tipo, 'direccion': dir, 'ciudad': ciudad, 'estado': estado, 'latitud': lat, 'longitud': lng, 'activo': True, 'mostrar_en_mapa': True}
    )
print('✓ Datos de ejemplo cargados')
"

# 5. Superusuario
echo ""
echo "→ Creando superusuario admin..."
python manage.py shell -c "
from accounts.models import Usuario
if not Usuario.objects.filter(username='admin').exists():
    u = Usuario.objects.create_superuser('admin', 'admin@papeexpress.mx', 'admin123')
    u.rol = 'admin'
    u.first_name = 'Administrador'
    u.save()
    print('✓ Usuario admin creado: admin / admin123')
else:
    print('✓ Usuario admin ya existe')
"

# 6. Archivos estáticos
echo "→ Recolectando archivos estáticos..."
python manage.py collectstatic --noinput -v 0 2>/dev/null || true


# POS — Datos iniciales
python manage.py shell -c "
from pos.models import ClientePOS, Sucursal, CategoriaPOS, ProductoPOS, PrecioPorSucursal, Inventario

cliente, _ = ClientePOS.objects.get_or_create(nombre='PaPeExpress', defaults={'rfc':'PEX000000000'})
suc_data = [('Hercules','mixto'),('Maury','menudeo'),('Roshita','menudeo')]
sucursales = {}
for nombre, tipo in suc_data:
    s, _ = Sucursal.objects.get_or_create(nombre=nombre, cliente=cliente, defaults={'tipo':tipo,'activa':True})
    sucursales[nombre] = s

cats = [('Cuadernos','📓','#0077CC'),('Colores','🎨','#FF0080'),('Plumas','🖊️','#FFD600'),
        ('Fomy','🎀','#FF2D7E'),('Manualidades','✂️','#00CFFF'),('Papelería general','📦','#FF8C00')]
cats_obj = {}
for nombre, icono, color in cats:
    c, _ = CategoriaPOS.objects.get_or_create(nombre=nombre, defaults={'icono':icono,'color':color})
    cats_obj[nombre] = c

prods = [('CU001','Cuaderno Profesional 100h','Cuadernos','pieza'),
         ('CO001','Caja Colores Prismacolor 24','Colores','caja'),
         ('PL001','Set Plumas de Color x12','Plumas','set'),
         ('FO001','Mariposa Fomy','Fomy','pieza'),
         ('FO002','Flores Primavera Fomy','Fomy','pieza'),
         ('PA001','Tijeras Escolar','Papelería general','pieza'),
         ('PA002','Resistol 850ml','Papelería general','pieza'),
         ('MA001','Foamy A4 colores surtidos','Manualidades','pieza')]
for codigo, nombre, cat, unidad in prods:
    prod, _ = ProductoPOS.objects.get_or_create(codigo=codigo,
        defaults={'nombre':nombre,'categoria':cats_obj[cat],'unidad':unidad,'activo':True})
    for suc in sucursales.values():
        PrecioPorSucursal.objects.get_or_create(producto=prod, sucursal=suc,
            defaults={'precio_1':20,'precio_2':17,'precio_3':14})
        Inventario.objects.get_or_create(producto=prod, sucursal=suc,
            defaults={'stock_actual':50,'stock_minimo':10,'stock_maximo':200,'costo_promedio':8})
print('POS: Hercules, Maury, Roshita + 8 productos listos')
"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║            ¡Setup completado!            ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Inicia el servidor:                     ║"
echo "║    python manage.py runserver            ║"
echo "║                                          ║"
echo "║  Admin Django: /admin/                   ║"
echo "║    Usuario: admin                        ║"
echo "║    Contraseña: admin123                  ║"
echo "║                                          ║"
echo "║  ⚠️  Cambia la contraseña en producción  ║"
echo "╚══════════════════════════════════════════╝"
