# Inventory SaaS — Backend

Backend multi-tenant construido sobre la arquitectura descrita en `BACKEND.md`:
FastAPI + PostgreSQL con Row Level Security, arquitectura hexagonal y aislamiento
de tenants en tres capas.

> Estado: **Fases 1, 2 y 3 implementadas**.
> Identity, companies, company members, tenant context, RLS, categorías,
> productos, bodegas, inventario con ledger de movimientos, clientes,
> proveedores, ventas y compras.
> Pendiente (Fase 4+): permisos en base de datos, audit logs, notificaciones,
> reportes, background jobs, suscripciones y facturación.

---

## 1. Arranque rápido

### Con Docker (todo el stack)

```bash
cp .env.example .env      # ajusta JWT_SECRET
docker compose up --build
```

Levanta `postgres`, `redis`, `backend` (aplica migraciones y arranca uvicorn) y
`worker`. La API queda en http://localhost:8000 y la documentación en
http://localhost:8000/docs.

### En local (Postgres propio)

```bash
make install              # uv sync --extra dev
make up                   # postgres + redis vía docker (opcional)
make migrate
make run
```

Si usas un PostgreSQL ya instalado, crea el rol y las bases así:

```sql
CREATE ROLE inventory LOGIN PASSWORD 'inventory'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE DATABASE inventory OWNER inventory;
CREATE DATABASE inventory_test OWNER inventory;
-- en cada base:
CREATE EXTENSION IF NOT EXISTS pgcrypto;
ALTER SCHEMA public OWNER TO inventory;
```

> **El rol de la aplicación nunca debe ser superusuario.** Los superusuarios de
> PostgreSQL ignoran RLS por completo. Además, todas las tablas usan
> `FORCE ROW LEVEL SECURITY`, así que las policies aplican incluso al dueño de
> la tabla.

### Tests

```bash
make test-db     # crea inventory_test, migra y ejecuta toda la suite
make test        # requiere TEST_DATABASE_URL apuntando a una base de pruebas
```

82 tests: unitarios de dominio (totales, transiciones de estado, signos de los
movimientos), aislamiento RLS contra PostgreSQL real, cobertura estructural de
RLS, permisos por rol, concurrencia de stock y flujos de API completos.

Los tests unitarios corren siempre; los de integración y API se saltan solos si
no hay PostgreSQL disponible.

---

## 2. Flujo de una petición

```
HTTP Request
    │
    ├─ RequestContextMiddleware        request_id + logging estructurado
    │
    ├─ get_current_user                valida el JWT, carga el usuario
    │                                  SET LOCAL app.current_user_id
    │
    ├─ get_tenant_context              lee X-Company-ID, valida membership
    │                                  activa y empresa ACTIVE
    │                                  SET LOCAL app.current_company_id
    │
    ├─ require_permission("...")       autorización de aplicación (rol → permisos)
    │
    ├─ Use Case  →  Repository  →  PostgreSQL
    │                                  RLS filtra por app.current_company_id()
    │
    └─ commit / rollback               una transacción por request
```

El frontend **propone** la empresa mediante la cabecera `X-Company-ID`; el
backend solo la acepta después de comprobar la membresía. El `company_id` jamás
se toma del cuerpo de la petición.

### Ejemplo end-to-end

```bash
# 1. Registro (crea usuario + empresa + membership OWNER)
curl -X POST localhost:8000/api/v1/auth/register -H 'Content-Type: application/json' -d '{
  "email":"ada@example.com","password":"sup3r-secret-pw",
  "first_name":"Ada","last_name":"Lovelace","company_name":"Acme"
}'

# 2. Login
curl -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"ada@example.com","password":"sup3r-secret-pw"}'

# 3. Empresas del usuario (sin X-Company-ID: aún no hay tenant elegido)
curl localhost:8000/api/v1/companies -H "Authorization: Bearer $TOKEN"

# 4. Operar dentro de una empresa
curl -X POST localhost:8000/api/v1/products \
  -H "Authorization: Bearer $TOKEN" -H "X-Company-ID: $COMPANY_ID" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Martillo","sku":"mar-01","cost_price":"10.50","sale_price":"19.99"}'
```

### Flujo de negocio completo

```bash
AUTH=(-H "Authorization: Bearer $TOKEN" -H "X-Company-ID: $COMPANY_ID" -H 'Content-Type: application/json')

# Bodega y producto
curl -X POST localhost:8000/api/v1/warehouses "${AUTH[@]}" -d '{"name":"Central"}'

# Compra recibida: entra stock y queda el movimiento PURCHASE
curl -X POST localhost:8000/api/v1/purchases "${AUTH[@]}" -d '{
  "warehouse_id":"'$W'", "supplier_id":"'$S'", "complete":true,
  "items":[{"product_id":"'$P'","quantity":"50","unit_cost":"8.00"}]}'

# Venta completada: bloquea el stock, valida disponibilidad y descuenta
curl -X POST localhost:8000/api/v1/sales "${AUTH[@]}" -d '{
  "warehouse_id":"'$W'", "customer_id":"'$C'", "complete":true,
  "items":[{"product_id":"'$P'","quantity":"5"}]}'

# Traslado entre bodegas (TRANSFER_OUT + TRANSFER_IN en una transacción)
curl -X POST localhost:8000/api/v1/inventory/transfers "${AUTH[@]}" -d '{
  "product_id":"'$P'", "source_warehouse_id":"'$W'",
  "destination_warehouse_id":"'$W2'", "quantity":"20"}'

# Stock actual y trazabilidad
curl "localhost:8000/api/v1/inventory/stock?product_id=$P" -H "Authorization: Bearer $TOKEN" -H "X-Company-ID: $COMPANY_ID"
curl "localhost:8000/api/v1/inventory/movements?product_id=$P" -H "Authorization: Bearer $TOKEN" -H "X-Company-ID: $COMPANY_ID"
```

Si una línea no tiene `unit_price`, se toma el `sale_price` vigente del
producto. Si cualquier línea se queda sin stock, **toda** la venta se revierte:
no existe el estado intermedio donde parte del pedido salió de la bodega.

---

## 3. Estructura

```
app/
├── domain/            Entidades, value objects, puertos (Protocols), reglas.
│   ├── shared/          BaseEntity, TenantEntity, paginación, money, document
│   ├── identity/        User, Email
│   ├── tenants/         Company, CompanyMember, TenantContext, permisos
│   ├── products/        Category, Product
│   ├── inventory/       Warehouse, ProductStock, StockMovement
│   ├── customers/       Customer
│   ├── suppliers/       Supplier
│   ├── sales/           Sale (agregado con SaleItem)
│   └── purchases/       Purchase (agregado con PurchaseItem)
│
├── application/       Casos de uso y DTOs. Orquesta el dominio.
│   ├── identity/        RegisterUser, AuthenticateUser, RefreshTokens
│   ├── tenants/         CreateCompany, ListMyCompanies, manage members
│   ├── products/        CRUD de categorías y productos
│   ├── inventory/       StockService + warehouses, ajustes, traslados
│   ├── customers/ suppliers/
│   ├── sales/           Create, Get, List, Complete, Cancel, Refund
│   └── purchases/       Create, Get, List, Complete, Cancel
│
├── infrastructure/    Detalles reemplazables.
│   ├── database/        modelos SQLAlchemy, repositorios, sesión,
│   │                    tenant_context.py, rls.py, migration_helpers.py
│   └── jobs/            worker Arq (placeholder de Fase 4)
│
├── presentation/      FastAPI.
│   └── api/
│       ├── v1/          routers
│       ├── dependencies/ auth, tenant, repositorios (composition root)
│       └── middleware/  request context, manejo de errores
│
└── shared/            config, security (bcrypt + JWT), excepciones, logging
```

**Regla de dependencias:** `presentation → application → domain`, e
`infrastructure` implementa los puertos del dominio. El dominio no importa
FastAPI, SQLAlchemy ni Redis: puedes comprobarlo con

```bash
grep -rE "fastapi|sqlalchemy|redis" app/domain/   # no debe devolver nada
```

---

## 4. Multi-tenancy y RLS

Tres capas, tal como exige `BACKEND.md` §48:

| Capa | Dónde | Qué impide |
|---|---|---|
| Autenticación | `dependencies/auth.py` | peticiones sin identidad válida |
| Autorización de aplicación | `require_permission` + repositorios filtrando por `company_id` | operaciones fuera del rol y consultas mal escritas |
| PostgreSQL RLS | migraciones (`enable_tenant_rls`) | cualquier fuga que se escape a las dos anteriores |

El contexto viaja a la base de datos como ajuste **local a la transacción**:

```python
await session.execute(
    text("SELECT set_config(:key, :value, true)"),
    {"key": "app.current_company_id", "value": str(company_id)},
)
```

Se usa `set_config(..., true)` en lugar de un `SET LOCAL` literal porque acepta
parámetros: el UUID nunca se concatena dentro del SQL.

Las policies leen `app.current_company_id()`, que devuelve `NULL` si nadie lo
fijó — y `company_id = NULL` nunca es verdadero, así que **una transacción sin
tenant no ve absolutamente nada**.

### Tablas con tratamiento especial

- `users`: no pertenece a un tenant, no lleva RLS.
- `companies`: visible si es el tenant activo **o** si el usuario tiene una
  membresía activa (esto alimenta el selector de empresa, que corre antes de
  elegir tenant).
- `company_members`: cada usuario ve sus propias membresías; dentro de un tenant
  ve el roster completo.

Crear una empresa es el único caso donde un caso de uso cambia el scope: genera
el UUID, entra en el scope del nuevo tenant (`TenantScope.enter`) y recién
entonces inserta la empresa y la membresía del OWNER. Así las policies de
INSERT no necesitan excepciones.

### El olvido que importa

El riesgo real no es que las policies estén mal escritas, sino que alguien
agregue una tabla nueva y no le ponga ninguna.
`tests/integration/test_rls_coverage.py` lo impide: consulta el catálogo de
PostgreSQL y exige que **toda** tabla con columna `company_id` tenga
`FORCE ROW LEVEL SECURITY` y sus cuatro policies. Una tabla sin RLS hace fallar
la suite con el nombre de la tabla y qué falta.

---

## 5. Migraciones

Todo — tablas, índices, constraints, funciones, RLS y policies — vive en
Alembic. Una base vacía queda lista con:

```bash
alembic upgrade head
```

```
alembic/versions/
├── 0001_extensions_and_base.py     pgcrypto, schema app, app.current_company_id(), app.current_user_id()
├── 0002_identity_and_tenants.py    users, companies, company_members + policies a medida
├── 0003_products.py                categories, products
├── 0004_inventory.py               warehouses, product_stock, stock_movements
├── 0005_customers_and_suppliers.py customers, suppliers
├── 0006_sales.py                   sales, sale_items
└── 0007_purchases.py               purchases, purchase_items
```

`alembic check` no detecta drift: los modelos SQLAlchemy y las migraciones
describen exactamente el mismo esquema, así que `--autogenerate` es confiable
para los módulos que vengan.

`app/infrastructure/database/rls.py` expone `enable_tenant_rls(op, "tabla")`,
que activa `ENABLE`/`FORCE ROW LEVEL SECURITY` y crea las cuatro policies
(SELECT/INSERT/UPDATE/DELETE). Los `downgrade()` eliminan policies, RLS y tablas
en orden inverso; el ciclo `upgrade head → downgrade base → upgrade head` está
verificado.

---

## 6. Inventario: el ledger

El stock no vive en un campo suelto. Hay dos tablas y una relación que se
cumple siempre:

```text
product_stock.quantity  ==  SUM(stock_movements.quantity)
```

`stock_movements` es un libro **append-only**: cada fila es un delta **con
signo** sobre un (producto, bodega). `product_stock` es la caché de lectura, y
se escribe en la misma transacción y bajo el mismo row lock que el movimiento
que la cambia, así que las dos no pueden discrepar. Hay un test que verifica la
igualdad contra PostgreSQL.

| Tipo | Signo | Se origina en |
|---|---|---|
| `PURCHASE` | + | compra completada |
| `SALE` | − | venta completada |
| `RETURN` | + | venta cancelada o devuelta |
| `TRANSFER_OUT` / `TRANSFER_IN` | − / + | traslado entre bodegas |
| `ADJUSTMENT` | ± | ajuste manual, reversión de compra |

El signo lo obliga un CHECK en la base de datos, no solo el dominio.

### Concurrencia

Todo cambio de stock pasa por `StockService.apply_movement`, el único escritor
de `product_stock`. Su primer paso es tomar el lock:

```sql
INSERT INTO product_stock (...) VALUES (..., 0)
ON CONFLICT (company_id, product_id, warehouse_id) DO NOTHING;

SELECT * FROM product_stock
WHERE company_id = ... AND product_id = ... AND warehouse_id = ...
FOR UPDATE;
```

El `INSERT ... ON CONFLICT` cierra la carrera del primer movimiento de un
producto en una bodega; el `FOR UPDATE` serializa a todos los demás. Primero se
bloquea y después se valida la disponibilidad: leer la cantidad antes del lock
dejaría que otra transacción invalidara la comprobación.

Las líneas de una venta se procesan ordenadas por `product_id`, para que dos
ventas simultáneas tomen los locks en la misma secuencia y no puedan trabarse
entre sí. Lo mismo hacen los traslados con las dos bodegas.

Hay un test que lanza dos ventas concurrentes sobre una única unidad: exactamente
una gana y la otra recibe `INSUFFICIENT_STOCK`.

### Ventas y compras

```text
DRAFT ──complete──> COMPLETED ──cancel──> CANCELLED   (devuelve el stock)
  │                     │
  │                     └──refund──> REFUNDED         (solo ventas)
  └──cancel──> CANCELLED                              (no tocó stock)
```

`POST /sales` con `"complete": true` crea y completa en **una sola
transacción** — el flujo de punto de venta de `BACKEND.md` §28. Los totales
siempre se derivan de las líneas: el cliente no puede pedir que le cobren un
importe distinto al que suman sus ítems.

Cancelar una compra ya recibida se registra como `ADJUSTMENT`, no como una
`PURCHASE` negativa, para que los reportes de volumen de compra no se netéen
solos.

---

## 7. Cómo añadir un módulo nuevo

Tomando `products` o `sales` como plantilla:

1. **Dominio** — `app/domain/<modulo>/entities/<entidad>.py` (hereda de
   `TenantEntity`), `exceptions.py` y el puerto
   `repositories/<entidad>_repository.py` (un `Protocol`).
2. **Aplicación** — DTOs Pydantic y casos de uso que reciben `TenantContext`.
3. **Infraestructura** — modelo SQLAlchemy con `TenantMixin`, repositorio
   SQLAlchemy y su mapper.
4. **Migración** — tabla, índices `(company_id, ...)`, constraints y
   `enable_tenant_rls(op, "<tabla>")`. Los helpers de
   `migration_helpers.py` (`uuid_pk`, `timestamps`, `money_column`…) evitan
   repetir las columnas de siempre. Si olvidas el RLS,
   `tests/integration/test_rls_coverage.py` falla.
5. **Presentación** — router en `api/v1/`, alta en `api/v1/router.py`,
   proveedor del repositorio en `dependencies/repositories.py` y permisos nuevos
   en `ROLE_PERMISSIONS`.
6. **Tests** — unitarios de la entidad, RLS de aislamiento y tests de API.

---

## 8. Errores

Formato único (`BACKEND.md` §38):

```json
{"error": {"code": "PRODUCT_NOT_FOUND", "message": "Product not found", "details": {}}}
```

Las excepciones de dominio heredan de `AppError` y llevan su `code` y su
`status_code`; `presentation/api/middleware/error_handler.py` es el único punto
que las traduce a HTTP.

---

## 9. Decisiones de diseño

- **Dinero en `NUMERIC(18,4)`**, nunca `FLOAT`. `Decimal` en todo el dominio.
- **Contraseñas con bcrypt**; se rechazan claves de más de 72 bytes en vez de
  truncarlas en silencio.
- **Login de tiempo constante**: se verifica un hash señuelo cuando el email no
  existe, para no permitir enumerar cuentas.
- **`eager_defaults`** en el `Base` de SQLAlchemy: `updated_at` lo calcula la
  base de datos y una sesión async no puede recargarlo perezosamente.
- **Borrado suave de productos** (`DELETE /products/{id}` desactiva): ventas y
  movimientos de stock seguirán referenciándolos.
- **Índice único parcial** para `barcode`: es opcional, así que solo los valores
  no nulos deben ser únicos.
- **Logout sin estado** por ahora. La revocación real necesita una denylist de
  `jti` en Redis; `decode_token` ya devuelve ese `jti`.
- **Permisos en código** (`ROLE_PERMISSIONS`), listos para migrar a las tablas
  `roles`/`permissions` de la Fase 4 sin tocar los routers.
- **`company_id` también en `sale_items` y `purchase_items`.** `BACKEND.md`
  dibuja esas tablas sin la columna, pero §22 pide RLS en toda tabla del tenant
  y una policy necesita un `company_id` con el que comparar. Sin ella, las
  líneas serían la vía por la que se filtra una venta cuyo encabezado sí está
  protegido.
- **Cantidades en `NUMERIC(18,4)`**, no enteros: hay negocios que venden por
  peso o por metro.
- **Precio de venta opcional en la línea.** Omitido, se usa el `sale_price` del
  producto; enviado, manda el de la línea — así funciona un precio negociado.
- **`update_product_costs` es opt-in** al completar una compra. Muchos negocios
  quieren costo promedio ponderado en vez de último costo, y eso es una
  decisión del negocio, no un default.

## 10. Siguiente paso sugerido

Fase 4: permisos en tablas (`roles`, `permissions`, `role_permissions`) para
reemplazar `ROLE_PERMISSIONS`, audit logs, alertas de stock bajo sobre el worker
Arq que ya está en el compose, y reportes.

Dos deudas conocidas del prototipo, por si pesan antes:

- **Logout sin revocación.** Hace falta una denylist de `jti` en Redis.
- **Numeración de documentos.** Ventas y compras se identifican por UUID; un
  consecutivo por empresa (factura #1, #2…) necesita su propia secuencia y es
  requisito en la mayoría de países.
