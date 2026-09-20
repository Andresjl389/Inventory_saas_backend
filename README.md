# Inventory SaaS — Backend

Backend multi-tenant construido sobre la arquitectura descrita en `BACKEND.md`:
FastAPI + PostgreSQL con Row Level Security, arquitectura hexagonal y aislamiento
de tenants en tres capas.

> Estado: **Fases 1 a 5 implementadas**. 54 endpoints, 21 tablas, 117 tests.
> Identity, empresas, miembros, tenant context, RLS, categorías, productos,
> bodegas, inventario con ledger, clientes, proveedores, ventas, compras,
> **super admin de plataforma**, roles y permisos en base de datos, auditoría,
> reportes, notificaciones, jobs en background, planes y suscripciones.
> Pendiente: almacenamiento S3 (imágenes, facturas, exportaciones) y
> numeración consecutiva de documentos.

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

### Primer administrador de plataforma

Una base recién migrada no tiene ningún super admin, así que `/api/v1/admin/*`
no es alcanzable hasta ejecutar:

```bash
make superuser email=ops@tuempresa.com
# o, dentro de docker:
docker compose exec backend python -m app.cli create-superuser --email ops@tuempresa.com
```

Pide la contraseña por prompt a propósito: pasarla como flag la deja en el
historial del shell y en `ps`. Con `--promote` convierte en administrador a una
cuenta que ya existe.

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

## 2. Super admin: la consola de plataforma

El super admin es el operador del SaaS, no un miembro de ninguna empresa. Se
marca con `users.is_superuser` — una columna, nunca un claim del token — y ese
mismo chequeo es el que levanta `app.is_platform_admin` en la transacción, así
que el guard de la API y las policies de RLS no pueden contradecirse.

```bash
# Crear empresa + dueño + suscripción, todo en una transacción
curl -X POST localhost:8000/api/v1/admin/companies -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' -d '{
    "name":"Ferretería Central",
    "owner_email":"ana@ferreteria.com", "owner_password":"clave-de-la-dueña",
    "plan_code":"STANDARD"}'
```

Si `owner_email` ya tiene cuenta, esa persona pasa a ser la dueña; si no, se
crea y `owner_password` es obligatorio. Nunca queda una empresa a medio
aprovisionar: si algo falla, se revierte entera.

| Endpoint | Para qué |
|---|---|
| `GET /admin/stats` | Tablero: empresas y usuarios por estado |
| `POST /admin/companies` | Aprovisionar empresa + dueño + plan |
| `GET /admin/companies` | Todas las empresas, con búsqueda y filtro por estado |
| `PATCH /admin/companies/{id}` | Editar, **suspender** o reactivar |
| `GET /admin/companies/{id}/members` | Quién pertenece a esa empresa |
| `GET/POST /admin/users`, `PATCH /admin/users/{id}` | Crear cuentas, resetear claves, desactivar, otorgar rol de plataforma |
| `GET/POST /admin/plans`, `PATCH /admin/plans/{id}` | Catálogo de planes |
| `PUT /admin/companies/{id}/subscription` | Poner una empresa en un plan |
| `GET /admin/audit` | Auditoría de toda la plataforma |

Suspender una empresa la deja fuera en la siguiente petición de sus miembros
(`403 INVALID_COMPANY`), pero el operador sigue pudiendo entrar — que suele ser
exactamente el motivo por el que la está mirando.

### Hasta dónde llega el escape de RLS

Esta es la decisión de diseño que más importa de esta fase. El flag de
plataforma **no** abre las tablas de negocio:

| Tablas | Policy | Por qué |
|---|---|---|
| `companies`, `company_members`, `roles`, `subscriptions`, `audit_logs` | `... OR app.is_platform_admin()` | El operador legítimamente las lista entre tenants |
| `permissions`, `plans` | Lectura para todos, escritura solo para plataforma | Catálogos globales |
| `products`, `sales`, `stock_movements`, … | **Sin escape**, solo `company_id = app.current_company_id()` | Nunca hay una petición que lea el negocio de dos empresas a la vez |

Para ver los datos de una empresa, el operador **entra** en ella mandando
`X-Company-ID`. No tiene membresía, así que se le construye un `TenantContext`
de plataforma con permisos totales — pero de **una sola empresa**. Hay un test
que lo comprueba: el mismo admin, en dos empresas, ve un producto en cada una y
nunca los dos juntos.

---

## 3. Roles y permisos

Los roles viven en la base de datos (`roles`, `permissions`, `role_permissions`),
no en un enum. Una empresa puede definir los suyos sin un deploy.

```bash
curl -X POST localhost:8000/api/v1/roles "${AUTH[@]}" -d '{
  "code":"cajero", "name":"Cajero",
  "permissions":["company.read","products.read","sales.read","sales.create"]}'

curl -X POST localhost:8000/api/v1/companies/current/members "${AUTH[@]}" \
  -d '{"email":"caja@ferreteria.com","role":"CAJERO"}'
```

- Los cuatro roles del sistema (`OWNER`, `ADMIN`, `SELLER`, `INVENTORY_MANAGER`)
  tienen `company_id IS NULL`: son iguales para todas las empresas y ninguna
  puede editarlos. Quien quiera "ADMIN menos algo" clona y ajusta.
- Un rol propio con el mismo código que uno del sistema **gana** dentro de esa
  empresa (`resolve_for_company`), así que se puede endurecer un built-in
  localmente.
- Los permisos se leen de la base en **cada petición**, así que cambiar un rol
  surte efecto sin que nadie vuelva a iniciar sesión.
- `app/domain/authorization/permissions.py` es la única fuente de verdad del
  catálogo: la migración 0008 lo siembra desde ahí y un test verifica que no se
  separen.
- Solo un OWNER puede crear un rol con el comodín `*`. Si no, un ADMIN podría
  fabricarse un rol más poderoso que el suyo y asignárselo.

---

## 4. Flujo de una petición

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

## 5. Estructura

```
app/
├── domain/            Entidades, value objects, puertos (Protocols), reglas.
│   ├── shared/          BaseEntity, TenantEntity, paginación, money, document
│   ├── identity/        User, Email, platform admin
│   ├── authorization/   Role, Permission, catálogo de permisos
│   ├── tenants/         Company, CompanyMember, TenantContext, permisos
│   ├── products/        Category, Product
│   ├── inventory/       Warehouse, ProductStock, StockMovement
│   ├── customers/       Customer
│   ├── suppliers/       Supplier
│   ├── sales/           Sale (agregado con SaleItem)
│   ├── purchases/       Purchase (agregado con PurchaseItem)
│   ├── audit/           AuditEntry
│   ├── billing/         Plan, Subscription
│   ├── notifications/   Notification
│   └── reports/         puertos de lectura (agregaciones)
│
├── application/       Casos de uso y DTOs. Orquesta el dominio.
│   ├── identity/        RegisterUser, AuthenticateUser, RefreshTokens
│   ├── tenants/         CreateCompany, ListMyCompanies, manage members
│   ├── products/        CRUD de categorías y productos
│   ├── inventory/       StockService + warehouses, ajustes, traslados
│   ├── customers/ suppliers/
│   ├── sales/           Create, Get, List, Complete, Cancel, Refund
│   ├── purchases/       Create, Get, List, Complete, Cancel
│   ├── authorization/   CRUD de roles + catálogo de permisos
│   ├── platform/        aprovisionar empresas, usuarios, planes (super admin)
│   ├── audit/           AuditService + lectura
│   ├── reports/         ventas, valorización, stock bajo
│   └── notifications/   bandeja de la empresa
│
├── infrastructure/    Detalles reemplazables.
│   ├── database/        modelos SQLAlchemy, repositorios, sesión,
│   │                    tenant_context.py, rls.py, migration_helpers.py
│   └── jobs/            worker Arq, barrido de stock bajo, contexto de jobs
│
├── presentation/      FastAPI.
│   └── api/
│       ├── v1/          routers
│       ├── dependencies/ auth, tenant, repositorios (composition root)
│       └── middleware/  request context, manejo de errores
│
├── shared/            config, security (bcrypt + JWT), excepciones, logging
└── cli.py             create-superuser (bootstrap de la plataforma)
```

**Regla de dependencias:** `presentation → application → domain`, e
`infrastructure` implementa los puertos del dominio. El dominio no importa
FastAPI, SQLAlchemy ni Redis: puedes comprobarlo con

```bash
grep -rE "fastapi|sqlalchemy|redis" app/domain/   # no debe devolver nada
```

---

## 6. Multi-tenancy y RLS

Tres capas, tal como exige `BACKEND.md` §48:

| Capa | Dónde | Qué impide |
|---|---|---|
| Autenticación | `dependencies/auth.py` | peticiones sin identidad válida |
| Autorización de aplicación | `require_permission` + permisos leídos de la base | operaciones fuera del rol |
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

## 7. Migraciones

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
├── 0007_purchases.py               purchases, purchase_items
├── 0008_roles_and_permissions.py   roles, permissions, role_permissions,
│                                   app.is_platform_admin(), siembra del catálogo
├── 0009_audit_logs.py              audit_logs (append-only)
├── 0010_billing.py                 plans (sembrados), subscriptions
└── 0011_notifications.py           notifications, products.min_stock
```

La migración 0008 siembra desde `app.domain.authorization.permissions`, así que
el catálogo de permisos y los roles del sistema no pueden separarse del código.
Siembra **antes** de activar RLS: la migración corre sin contexto de tenant y
sin el flag de plataforma, así que sus propias policies rechazarían los INSERT.

`alembic check` no detecta drift: los modelos SQLAlchemy y las migraciones
describen exactamente el mismo esquema, así que `--autogenerate` es confiable
para los módulos que vengan.

`app/infrastructure/database/rls.py` expone `enable_tenant_rls(op, "tabla")`,
que activa `ENABLE`/`FORCE ROW LEVEL SECURITY` y crea las cuatro policies
(SELECT/INSERT/UPDATE/DELETE). Los `downgrade()` eliminan policies, RLS y tablas
en orden inverso; el ciclo `upgrade head → downgrade base → upgrade head` está
verificado.

---

## 8. Inventario: el ledger

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

## 9. Reportes, notificaciones y jobs

### Reportes

```text
GET /reports/sales?since=&until=&limit=     ingresos, ticket promedio, más vendidos
GET /reports/inventory-valuation            cuánto vale el stock, a costo y a venta
GET /reports/low-stock                      productos en o bajo su punto de reorden
GET /reports/audit                          auditoría de esta empresa
```

Son agregaciones, no entidades: pasarlas por los repositorios de entidades
significaría traer miles de filas para sumarlas en Python. Por eso el puerto
`ReportRepository` devuelve registros planos y el SQL vive en el adaptador.

Solo cuentan las ventas `COMPLETED`: los borradores no ocurrieron y las
canceladas o devueltas ya regresaron el dinero.

### Alertas de stock bajo

`products.min_stock` es el punto de reorden (0 = sin alerta). El job diario
recorre empresa por empresa **dentro del contexto de cada una**, así que está
sujeto al mismo RLS que una petición; el único paso entre tenants es listar qué
empresas visitar.

```bash
make worker      # arq: cron diario 07:00
make low-stock   # ejecutarlo una vez, ahora
```

Las notificaciones se deduplican con un índice único parcial
`(company_id, dedupe_key) WHERE dedupe_key IS NOT NULL AND is_read = false`:
un segundo barrido sobre un producto que sigue bajo mínimo no crea otra fila,
y dos workers simultáneos tampoco.

### Auditoría

`audit_logs` es **append-only**: tiene policies de SELECT e INSERT y
deliberadamente ninguna de UPDATE ni DELETE, ni siquiera para la plataforma. Un
test lo verifica contra `pg_policies`. Las filas con `company_id NULL` son
eventos de plataforma y solo las ve el operador.

El payload se limpia antes de escribirse: `password`, `password_hash`,
`access_token`, `refresh_token` y `authorization` nunca llegan al log.

---

## 10. Cómo añadir un módulo nuevo

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

## 11. Errores

Formato único (`BACKEND.md` §38):

```json
{"error": {"code": "PRODUCT_NOT_FOUND", "message": "Product not found", "details": {}}}
```

Las excepciones de dominio heredan de `AppError` y llevan su `code` y su
`status_code`; `presentation/api/middleware/error_handler.py` es el único punto
que las traduce a HTTP.

---

## 12. Decisiones de diseño

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
- **Permisos en base de datos**, leídos en cada petición. Cuesta un join por
  request y a cambio un cambio de rol surte efecto sin volver a iniciar sesión.
  Si el join pesa, el siguiente paso es cachearlo en Redis con invalidación al
  editar el rol — no volver al enum.
- **El super admin no es miembro de ninguna empresa.** Podría haberse modelado
  como una membresía especial, pero entonces todo el código de tenants tendría
  que preguntarse "¿y si este miembro es de plataforma?". Separarlos deja los
  dos caminos limpios.
- **El flag de plataforma se lee de la base, no del token.** Un token robado no
  puede promoverse solo, y quitarle el rol a alguien surte efecto en su
  siguiente petición sin esperar a que expire el JWT.
- **Nadie puede quitarse a sí mismo sus propios privilegios**: ni el operador su
  rol de plataforma, ni el dueño su rol en la empresa. Es la forma más fácil de
  dejar una instalación sin administrador.
- **Los planes usan 0 = ilimitado**, no NULL: "sin límite" es un valor real, y
  un NULL habría que tratarlo aparte en cada comparación.
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

## 13. Lo que falta

- **Almacenamiento S3** (`BACKEND.md` §42): imágenes de productos, facturas,
  reportes generados, importaciones y exportaciones. Es lo único de la
  arquitectura original que no está.
- **Numeración consecutiva de documentos.** Ventas y compras se identifican por
  UUID; una factura #1, #2… por empresa necesita su propia secuencia y es
  requisito legal en la mayoría de países.
- **Logout sin revocación.** Hace falta una denylist de `jti` en Redis;
  `decode_token` ya devuelve ese `jti`.
- **Cuotas de plan sin aplicar.** `plans.max_users`, `max_products` y
  `max_warehouses` se guardan y se muestran, pero todavía no bloquean la
  creación del recurso.
- **Invitaciones por correo.** Hoy un miembro nuevo debe tener cuenta; el super
  admin puede crearla desde `/admin/users`.
