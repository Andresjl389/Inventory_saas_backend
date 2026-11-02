# Inventory SaaS — Backend

Backend multi-tenant construido sobre la arquitectura descrita en `BACKEND.md`:
FastAPI + PostgreSQL con Row Level Security, arquitectura hexagonal y aislamiento
de tenants en tres capas.

> Estado: **Fases 1 a 5 implementadas**, más el fiado. 76 endpoints, 26 tablas,
> 278 tests.
> Identity, empresas, miembros, tenant context, RLS, categorías, productos,
> bodegas, inventario con ledger, clientes, proveedores, ventas, compras,
> **super admin de plataforma**, roles y permisos en base de datos, auditoría,
> reportes, notificaciones, jobs en background, planes y suscripciones.
> Incluye consola de supervisión de empresas y carga masiva desde Excel con
> mapeo de columnas. El almacenamiento de archivos va sobre una carpeta local;
> el adaptador S3 es lo único que falta de la arquitectura original.

---

> **¿Vas a construir el frontend?** Empieza por
> [`docs/FRONTEND.md`](docs/FRONTEND.md): autenticación, el header de empresa,
> permisos, los flujos completos y las trampas que el esquema OpenAPI no cuenta.

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

`GET /auth/me` expone `is_superuser`, que es lo que permite al cliente
distinguirlo: un operador no es miembro de ninguna empresa, así que
`GET /companies` le devuelve una lista vacía y un frontend que solo mirara eso
lo mandaría a la pantalla de «no perteneces a ninguna empresa». Su selector de
empresa es la consola (`/admin/companies/supervision`), no ese endpoint.

**Es el único que puede crear empresas.** No hay autoservicio: el registro
público crea una cuenta y nada más, `POST /api/v1/companies` no existe, y la
policy de INSERT sobre `companies` exige el flag de plataforma — así que la
regla de la aplicación y la de la base dicen lo mismo y un endpoint futuro no
puede reabrir la puerta por descuido.

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
| `GET /admin/companies/supervision` | **Tabla de supervisión**: cada empresa con su plan y sus números reales |
| `GET /admin/companies/{id}/overview` | Una empresa en detalle, con su uso contra los límites del plan |
| `GET /admin/onboarding/template` | Libro con una hoja por entidad |
| `POST /admin/companies/{id}/onboarding` | **Cargar una empresa entera** desde ese libro |
| `POST /admin/companies` | Aprovisionar empresa + dueño + plan |
| `GET /admin/companies` | Todas las empresas, con búsqueda y filtro por estado |
| `PATCH /admin/companies/{id}` | Editar, **suspender** o reactivar |
| `GET /admin/companies/{id}/members` | Quién pertenece a esa empresa |
| `POST /admin/companies/{id}/members` | **Vincular una persona a una empresa por id** |
| `PATCH /admin/companies/{id}/members/{user_id}` | Cambiar su rol o desactivarla |
| `GET/POST /admin/users`, `PATCH /admin/users/{id}` | Crear cuentas, resetear claves, desactivar, otorgar rol de plataforma |
| `GET/POST /admin/plans`, `PATCH /admin/plans/{id}` | Catálogo de planes |
| `PUT /admin/companies/{id}/subscription` | Poner una empresa en un plan |
| `GET /admin/audit` | Auditoría de toda la plataforma |

Suspender una empresa la deja fuera en la siguiente petición de sus miembros
(`403 INVALID_COMPANY`), pero el operador sigue pudiendo entrar — que suele ser
exactamente el motivo por el que la está mirando.

### Supervisar sin romper el aislamiento

```bash
curl "localhost:8000/api/v1/admin/companies/supervision?with_metrics=true" \
  -H "Authorization: Bearer $ADMIN"
```

Devuelve, por empresa: plan y estado de la suscripción, miembros, productos,
bodegas, clientes, proveedores, ventas y facturación de los últimos 30 días,
unidades y valor del inventario a costo, y cuándo fue la última venta.

Las tablas de negocio **no** tienen escape de RLS para el operador, así que
estos números no salen de una consulta entre empresas: cada empresa de la
página se **entra** por turno con su propio contexto de tenant y se consulta
como lo haría una petición suya. Es el único punto del sistema donde una
petición de operador toca más de una empresa, lo hace en secuencia y está
acotado al tamaño de la página. `with_metrics=false` se salta ese trabajo.

`GET /admin/companies/{id}/overview` hace lo mismo para una sola, y añade el
uso contra los topes del plan:

```json
{"usage": [{"resource": "warehouses", "used": 2, "limit": 5, "over_limit": false}]}
```

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
de plataforma con permisos totales — pero de **una sola empresa**.

Dentro de ella puede todo lo que puede el dueño: catálogo, inventario, ventas,
compras, roles, equipo, reportes e importaciones. Hay un test que recorre esas
operaciones una por una, y otro que comprueba el límite: el mismo operador, en
dos empresas, ve un producto en cada una y nunca los dos juntos.

### Quién administra qué

```text
Super admin  ──crea──>  Empresa + su OWNER
                             │
                             └──gestiona──>  roles, permisos, miembros,
                                             y todo el negocio de su empresa
```

Cada empresa sale del aprovisionamiento con **una persona responsable**: el
`OWNER`, que tiene el comodín `*`. Desde ahí arma su propio equipo, incluidos
otros `ADMIN`. El operador de plataforma no participa en el día a día de una
empresa; solo entra cuando hay que repararla.

Para dar de alta a alguien hay dos caminos, y los dos apuntan a una empresa que
**ya existe**, identificada por su id:

```bash
# La dueña agrega a su equipo (crea la cuenta si no existe)
curl -X POST localhost:8000/api/v1/companies/current/members "${AUTH[@]}" -d '{
  "email":"vendedor@acme.com", "role":"SELLER",
  "password":"clave-inicial", "first_name":"Luis"}'

# El operador vincula a alguien a cualquier empresa (ruta de reparación)
curl -X POST localhost:8000/api/v1/admin/companies/$ID/members \
  -H "Authorization: Bearer $ADMIN" -d '{"email":"rescate@acme.com","role":"ADMIN"}'
```

Todavía no hay invitaciones por correo: quien da de alta fija la primera
contraseña y la entrega. Nada verifica que la dirección sea de esa persona.

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

> El registro público (`POST /api/v1/auth/register`) crea **solo una cuenta**,
> sin empresa. Quien la administra te agrega después.

```bash
# 1. El operador crea la empresa y nombra a su dueña
curl -X POST localhost:8000/api/v1/admin/companies -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' -d '{
    "name":"Acme", "owner_email":"ada@example.com", "owner_password":"sup3r-secret-pw"
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
│   ├── files/           StoredFile, puerto FileStorage, generación de claves
│   ├── imports/         catálogo de campos, coerción, mapeo de columnas
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
│   ├── files/           subir, listar, descargar, borrar adjuntos
│   ├── imports/         analizar, mapear, simular, cargar + onboarding
│   ├── reports/         ventas, valorización, stock bajo
│   └── notifications/   bandeja de la empresa
│
├── infrastructure/    Detalles reemplazables.
│   ├── database/        modelos SQLAlchemy, repositorios, sesión,
│   │                    tenant_context.py, rls.py, migration_helpers.py
│   ├── imports/         lector .xlsx/.csv, plantillas
│   ├── storage/         adaptador local (atómico) + factory
│   └── jobs/            worker Arq, stock bajo, barrido de huérfanos
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
grep -rE "fastapi|sqlalchemy|redis" app/domain/              # sin frameworks
grep -r "from app.infrastructure" app/domain/ app/application/  # sin infraestructura
```

Ninguno de los dos devuelve nada. La generación de claves de almacenamiento,
por ejemplo, vive en `app/domain/files/keys.py` y no en el adaptador: cómo se
organizan los archivos de un tenant es una decisión de la aplicación, y el
adaptador solo recibe una clave que no eligió.

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

Crear una empresa ya no es una operación de tenant: la hace el operador con el
flag de plataforma levantado, así que la policy de INSERT sobre `companies` es
simplemente `app.is_platform_admin()`. El puerto `TenantScope`, que existía
solo para el viejo bootstrap desde el formulario de registro, se eliminó con él.

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
├── 0011_notifications.py           notifications, products.min_stock
├── 0012_files.py                   files + permisos files.read / files.write
└── 0013_imports.py                 import_jobs, import_errors + permisos
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

## 9. Fiado: la cuenta corriente del cliente

Lo que el cuaderno hacía mal —un número que alguien tacha y vuelve a escribir—
aquí es un libro append-only, con el mismo patrón que el inventario:

```text
customer_balances.balance == SUM(customer_account_entries.amount)
```

El `amount` lleva signo: positivo aumenta la deuda (una venta fiada), negativo
la reduce (un abono). Guardar el signo en vez de una magnitud más un tipo es lo
que vuelve ese invariante una suma trivial de verificar, y hay un test que lo
hace. El libro no tiene policies de UPDATE ni DELETE: en la base no hay forma
de tachar.

### Cómo se fía

Una venta lleva `payment_method` y `amount_paid`; lo que falte queda a deber:

```bash
# De contado (por defecto): paga todo
curl -X POST localhost:8000/api/v1/sales "${AUTH[@]}" -d '{
  "warehouse_id":"'$W'", "complete":true,
  "items":[{"product_id":"'$P'","quantity":"2"}]}'

# Fiado completo
... "customer_id":"'$C'", "payment_method":"CREDIT" ...

# «Le doy 5 mil y le quedo debiendo»
... "customer_id":"'$C'", "payment_method":"CASH", "amount_paid":"5000" ...
```

- Fiar **exige cliente**: no se le fía a nadie (`CREDIT_SALE_NEEDS_CUSTOMER`).
- `customers.credit_limit` es el cupo; 0 = sin tope. Una venta que lo supere se
  rechaza entera con el saldo y el cupo en `details`.
- Cancelar o devolver una venta fiada **borra la deuda que dejó**, en la misma
  transacción que devuelve el stock.

### Abonos y cuentas claras

```text
GET  /credit/summary                          cuánto me deben en total
GET  /credit/accounts                         quién debe, el que más primero
GET  /credit/accounts/{customer_id}           saldo e historial de uno
POST /credit/accounts/{customer_id}/payments  registrar un abono
POST /credit/accounts/{customer_id}/adjustments  perdón o corrección, con nota
```

Un abono mayor a la deuda se rechaza: casi siempre es un error de digitación
(50000 por 5000), y los anticipos son otro producto.

### Saldo a favor

El saldo puede quedar **negativo**, y eso significa que la tienda le debe al
cliente. Pasa al devolver una venta que ya tenía abonos: el cliente pagó por
algo que ya no tiene. El sistema no puede saber si el tendero le entregó la
plata o se la dejó para la próxima, así que lo registra y lo muestra —`owes` e
`in_favor` vienen separados para que la pantalla no razone sobre signos— y el
tendero lo salda con un ajuste cuando corresponda.

---

## 10. Reportes, notificaciones y jobs

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

## 11. Archivos adjuntos

Los bytes viven fuera de PostgreSQL (`BACKEND.md` §42). Hoy en una carpeta
local; mañana en un bucket S3 sin tocar nada por encima del adaptador.

```bash
# Imagen de un producto
curl -X POST localhost:8000/api/v1/files \
  -H "Authorization: Bearer $TOKEN" -H "X-Company-ID: $COMPANY_ID" \
  -F "file=@martillo.png" -F "owner_type=PRODUCT" -F "owner_id=$PRODUCT_ID"

# Las imágenes de ese producto
curl "localhost:8000/api/v1/files?owner_type=PRODUCT&owner_id=$PRODUCT_ID" "${AUTH[@]}"

# Descargar (la respuesta trae download_url ya armada)
curl "localhost:8000/api/v1/files/$FILE_ID/content" "${AUTH[@]}" -o martillo.png
```

`owner_type` acepta `PRODUCT`, `SALE`, `PURCHASE`, `COMPANY`, `IMPORT`,
`EXPORT`, `REPORT`. Los tres primeros exigen un `owner_id` que exista **en esa
empresa**: `files.owner_id` no tiene foreign key (apunta a la tabla que diga
`owner_type`, y una columna no puede referenciar varias), así que la validación
vive en la aplicación.

### Cómo se guarda

La ruta se genera en el servidor y **nunca** sale del nombre que manda el
cliente:

```text
uploads/{company_id}/{owner_type}/{yyyy}/{mm}/{uuid}{ext}
```

La extensión sale del **content type**, no del filename. Eso elimina como
categoría el path traversal, las extensiones dobles y los `foto.png.php`, en
vez de tener que filtrarlos. El nombre original se guarda aparte, saneado, y
solo se devuelve en la cabecera `Content-Disposition`.

Otras propiedades que el adaptador garantiza:

- **Escrituras atómicas**: los bytes caen en `uploads/.tmp/*.part` y se mueven
  con `os.replace`. Una subida fallida nunca deja medio archivo legible.
- **Límite en streaming**: el tope (`MAX_UPLOAD_SIZE_MB`, 10 por defecto) se
  aplica chunk a chunk, no leyendo el cuerpo entero primero; un `Content-Length`
  demasiado grande se rechaza antes de tocar el disco.
- **Aislamiento**: la tabla `files` lleva RLS como cualquier otra. El id de otra
  empresa es un 404, nunca una descarga.
- **Solo imágenes se sirven `inline`**; todo lo demás va como `attachment`, con
  `X-Content-Type-Options: nosniff`.

### El orden de las dos escrituras

Una subida escribe **primero el blob y después la fila**. Si la petición falla
en medio, queda un blob huérfano — disco desperdiciado — en vez de una fila
apuntando a nada, que para el usuario es una descarga rota. El barrido diario
(3:30) reclama esos huérfanos, y solo toca blobs con más de una hora, para no
borrar una subida cuya fila todavía está en una transacción sin confirmar.

Al borrar es al revés: la fila se va en la transacción y el blob después del
commit (`BackgroundTasks`), así que un rollback no puede dejar una fila
apuntando a bytes que ya no están.

```bash
make sweep-files                       # dry run
uv run python -m app.cli sweep-files   # de verdad
```

### Migrar a S3

`app/domain/files/storage.py` define el puerto (`save`, `open`, `delete`,
`exists`). Escribe `app/infrastructure/storage/s3.py`, regístralo en
`factory.py` y cambia `STORAGE_BACKEND=s3`. Nada más cambia: ni los endpoints,
ni los casos de uso, ni la tabla. Hoy `factory.py` falla ruidosamente si pides
`s3`, en vez de escribir en silencio al disco del contenedor.

---

## 12. Carga masiva desde Excel

El problema real no es leer un .xlsx: es que los datos llegan como llegan.
Encabezados que nadie nombró igual dos veces, `$ 15.000` junto a `8.500,50`,
un título suelto en A1, filas en blanco en la mitad, columnas repetidas, "SÍ"
donde va un booleano. El importador está construido alrededor de eso.

### Dos fases, y esa es la idea

```text
1. Subir      POST /imports  (archivo + entidad)
                 → lee el archivo, propone un mapeo, muestra una vista previa
                 → NO escribe nada
2. Ajustar    PATCH /imports/{id}/mapping
                 → el usuario corrige columnas y, si hace falta, fija el
                   separador decimal o el formato de fecha
3. Simular    POST /imports/{id}/validate
                 → ejecuta la carga real dentro de un savepoint y lo revierte
4. Cargar     POST /imports/{id}/run
```

La simulación **no** es una segunda validación más débil: corre el mismo
cargador y deshace el savepoint. Por eso sus números incluyen las restricciones
de la base — SKU único, claves foráneas, checks — que una validación aparte
tendría que reimplementar y acabaría contradiciendo.

### El mapeo (las "etiquetas")

La respuesta de `POST /imports` trae lo que una pantalla tipo Power Query
necesita:

```json
{
  "columns": [
    {"source": "Referencia", "suggested_target": "sku", "confidence": 1.0,
     "reason": "exact", "needs_review": false, "samples": ["mar-01", "DES-02"]},
    {"source": "Centro de costo interno", "suggested_target": null,
     "confidence": 0.0, "reason": "unmatched", "samples": ["CC-900"]}
  ],
  "target_fields": [{"key": "sku", "label": "SKU", "required": true, "...": "..."}],
  "missing_required": [],
  "preview": [{"row_number": 4, "cells": [
    {"field_key": "sale_price", "raw": "$ 15.000", "value": "15000"}]}]
}
```

- El emparejamiento ignora acentos, mayúsculas y puntuación, y conoce sinónimos
  de otros sistemas: `referencia`, `pvp`, `familia`, `ean`, `nit`, `celular`…
- **Un campo destino nunca se propone dos veces**: si no, con dos columnas
  llamadas "Precio" el resultado dependería del orden.
- `needs_review` marca los aciertos plausibles pero no seguros. "Centro de
  costo interno" se parece a una columna de costo y no lo es; por eso se sugiere
  con poca confianza en vez de aceptarse en silencio.
- La **vista previa muestra el valor crudo y el convertido lado a lado**, que es
  lo que hace visible un separador mal interpretado antes de escribir nada.

### Números y textos desordenados

| Entra | Sale |
|---|---|
| `$ 15.000` | `15000` |
| `1.234,56` | `1234.56` |
| `1,234.56` | `1234.56` |
| `12.50` | `12.50` |
| `SÍ`, `X`, `activo` | `true` |
| `N/A`, `-`, `sin dato` | vacío |
| `4.0` (lo que openpyxl devuelve por un SKU `4`) | `"4"` |
| `CC-1`, `10 unidades` | **error de fila**, no `-1` ni `10` |

`15.000` se lee como quince mil, no como quince: un grupo de tres dígitos es
mucho más veces un separador de miles. Cuando no lo es, se manda
`decimal_separator` en el mapeo y la vista previa lo confirma.

Un valor con letras nunca se "rescata" quitándoselas. Limpiar `CC-1` hasta `-1`
importaría un precio equivocado sin que nadie se entere; fallar la fila es peor
al momento y mucho mejor a la semana.

### Dos caminos, un solo motor

**El cliente** baja `GET /imports/templates/{entidad}` — un libro con los
encabezados, una fila de ejemplo y una segunda hoja que documenta cada campo.
Como los encabezados *son* las etiquetas, al subirlo el mapeo se resuelve exacto
y el paso 2 le resulta invisible.

**El operador** usa los mismos endpoints con `X-Company-ID` de la empresa
destino, o carga una empresa entera de una vez:

```bash
curl localhost:8000/api/v1/admin/onboarding/template -H "Authorization: Bearer $ADMIN" -o carga.xlsx
curl -X POST "localhost:8000/api/v1/admin/companies/$ID/onboarding?dry_run=true" \
  -H "Authorization: Bearer $ADMIN" -F "file=@carga.xlsx"
```

Ese libro trae una hoja por entidad y se cargan **en orden de dependencia**
(categorías → bodegas → productos → clientes → proveedores → stock) dentro de un
único savepoint: o la empresa queda montada o no se tocó nada. Una hoja vacía se
omite. Aquí el todo-o-nada pesa más que en una carga suelta: una empresa a medio
construir es peor que una vacía, porque el operador no puede saber de un vistazo
qué mitad falta.

### Qué se puede cargar

`CATEGORIES`, `WAREHOUSES`, `PRODUCTS`, `CUSTOMERS`, `SUPPLIERS` y `STOCK`
(saldos iniciales). Todas **hacen upsert**: volver a subir un archivo corregido
es normal, no una tarea de limpieza. El stock inicial genera movimientos
`ADJUSTMENT`, así que el inventario tiene historial desde el primer día.

`GET /imports/schemas` devuelve el catálogo completo de campos, en el orden en
que conviene importarlos.

### Errores

Se reportan por **número de fila del archivo del usuario** (contando el
encabezado y las filas en blanco, para que la encuentre) y por nombre de su
columna, no de nuestro campo:

```json
{"row_number": 5, "column": "PVP", "field_key": "sale_price",
 "value": "mil pesos", "message": "'mil pesos' is not a valid number"}
```

Una fila con problemas se salta y el resto carga. Se paginan en
`GET /imports/{id}/errors`. Lo que el cargador puede anticipar (una categoría
que no existe, una bodega desconocida, un código de barras repetido) es un error
de fila; cualquier otra cosa aborta la carga entera.

Un caso que vale la pena mencionar: los códigos de barras son únicos por
empresa y los archivos los repiten constantemente. Antes eso reventaba la
importación completa contra una restricción de la base. Ahora el producto se
importa **sin** código de barras y el conflicto se reporta: el producto vale más
que su código, y el usuario arregla los códigos después en vez de perder el
catálogo.

---

## 13. Lectura de facturas: el modelo propio

> **Estado: diferido.** Todo lo de esta sección está construido, probado y
> apagado: `INVOICE_EXTRACTOR=disabled` es el valor por defecto porque el
> modelo espera a que el servidor tenga GPU. Mientras tanto
> `POST /invoices/scans` responde `503 INVOICE_SCANNING_DISABLED` y
> `GET /health` lo publica en `features.invoice_scanning`, así que el frontend
> puede ocultar el botón en vez de descubrirlo fallando.
>
> **Encenderlo son dos variables de entorno** (`INVOICE_EXTRACTOR=local` y
> `INVOICE_LOCAL_URL`), ni una línea de código. Hay una prueba que lo afirma,
> para que no se descubra dentro de seis meses que quedó algo a medias.

El escaneo de facturas está pensado para correr contra **nuestro propio modelo,
en nuestro servidor**. No por ideología: una tienda escanea decenas de facturas
al mes y el costo por documento de una API externa crece con cada cliente del
SaaS, mientras que una GPU se paga una vez. Y un modelo propio se puede afinar
con nuestras facturas, que es algo que ninguna API permite.

Hay un punto de equilibrio que conviene tener presente al prenderlo: por debajo
de unos cientos de documentos al mes, la luz de una GPU encendida 24/7 cuesta
más que pagar por documento en una API. Lo que no cambia con el volumen es la
independencia, que las facturas no salgan del servidor, y poder afinar.

### La arquitectura, en una línea

El dominio define un puerto; la infraestructura trae adaptadores.

```text
app/domain/invoices/extraction.py     InvoiceExtractor (puerto) + ExtractedInvoice
app/domain/invoices/rendering.py      DocumentRasterizer (puerto)
app/domain/invoices/matching.py       emparejar renglón ↔ catálogo (sin modelo)
app/domain/invoices/scoring.py        medir una lectura contra la verdad

app/infrastructure/invoices/prompting.py        prompt + esquema, uno solo
app/infrastructure/invoices/local_extractor.py  ← el camino: servidor propio
app/infrastructure/invoices/claude_extractor.py   la vara de medir (extra)
app/infrastructure/invoices/text_extractor.py     pruebas y desarrollo
app/infrastructure/invoices/rasterizer.py       PDF y fotos → imágenes
app/infrastructure/invoices/corpus.py           datos de entrenamiento + eval
```

Nada por encima del adaptador sabe qué modelo hay detrás. Cambiar de modelo —o
pasar a uno afinado con nuestras facturas— es cambiar `INVOICE_LOCAL_MODEL`.

### El servidor de inferencia

El adaptador habla el dialecto OpenAI (`POST /v1/chat/completions`), que es el
que exponen vLLM, llama.cpp, Ollama, TGI y LM Studio. Con GPU, vLLM es la
opción:

```bash
vllm serve Qwen/Qwen2.5-VL-7B-Instruct \
  --port 8080 \
  --max-model-len 8192 \
  --limit-mm-per-prompt image=4 \
  --gpu-memory-utilization 0.90
```

```env
INVOICE_EXTRACTOR=local
INVOICE_LOCAL_URL=http://gpu-interno:8080/v1
INVOICE_LOCAL_MODEL=Qwen/Qwen2.5-VL-7B-Instruct
INVOICE_LOCAL_JSON_MODE=json_schema
```

Qué modelo según lo que haya en el servidor. Son puntos de partida: la decisión
real la da `make invoice-eval` sobre facturas propias, no esta tabla.

| Servidor | Modelo para empezar | Licencia | Nota |
|---|---|---|---|
| GPU 24 GB (RTX 3090/4090, A10) | Qwen2.5-VL-7B-Instruct | Apache 2.0 | El punto dulce; es el valor por defecto |
| GPU 12-16 GB | Qwen2.5-VL-7B AWQ/GPTQ (4 bit) | Apache 2.0 | Cuantizado entra holgado; pierde poco en esta tarea |
| GPU 48 GB+ | Qwen2.5-VL-32B / 72B | **verificar** | Mejor en facturas borrosas o a mano |
| GPU chica o CPU | PaddleOCR-VL, DeepSeek-OCR y similares | Apache 2.0 / MIT | ~1 GB de VRAM, pero **no** rellenan un esquema JSON: hacen OCR a texto y hace falta un segundo paso |

> **Revisa el `LICENSE` del tamaño exacto que descargues, no el de la familia.**
> Dentro de un mismo modelo las licencias cambian por tamaño: el 7B es Apache
> 2.0 (uso comercial libre), pero los repos de 3B y 72B apuntan a la licencia
> propia de Qwen, que no es Apache y puede restringir el uso comercial. Para un
> SaaS eso no es un detalle. Por eso el valor por defecto es el 7B.

Los modelos especializados en documentos (PaddleOCR-VL, DeepSeek-OCR,
Granite-Docling) son otra familia: pesan una fracción y corren en casi
cualquier cosa, pero están hechos para convertir el documento en texto o
markdown, no para rellenar un esquema JSON a partir de un prompt. Encajarlos
aquí es un adaptador más —OCR a texto, y el texto a JSON con un modelo de
texto chico o con reglas— y es el camino si el servidor no tiene GPU.

Lo que **no** conviene es entrenar un modelo de visión desde cero. Lo que sí
tiene sentido, cuando haya corpus, es afinar (LoRA) uno de estos sobre nuestras
propias facturas: los mismos proveedores, los mismos formatos, mes tras mes. De
ahí sale la ventaja real, y para eso existe el corpus de la sección siguiente.

### Las tres cosas que hacen usable un modelo de 7B

Ninguna es el modelo, y las tres están en el adaptador:

1. **Decodificación guiada** (`INVOICE_LOCAL_JSON_MODE=json_schema`). El
   esquema JSON se manda forzado —`response_format` y `guided_json`, porque
   según la versión vLLM mira uno u otro— y el modelo deja de inventar campos.
   Sin esto, el mismo modelo falla muchas facturas por formato, no por lectura.
   Si el servidor no soporta `json_schema`, `json_object` manda el esquema en el
   prompt y el adaptador sabe desenvolver un ```json``` si llega envuelto.
2. **Temperatura 0.** Leer no es escribir: la misma factura tiene que dar el
   mismo resultado dos veces, o la revisión deja de ser auditable.
3. **Imágenes acotadas.** El rasterizador rota según EXIF (una foto de celular
   viene acostada en los bytes) y recorta al lado largo
   (`INVOICE_MAX_IMAGE_SIDE=1600`). El costo de un modelo de visión es por
   píxel: mandar los 12 megapíxeles completos es pagar cuatro veces por leer lo
   mismo, y en una GPU propia es la diferencia entre dos segundos y diez.

Los PDF de facturación electrónica se rasterizan con pdfium, hasta
`INVOICE_MAX_PAGES` hojas, y van como una sola factura en el mismo mensaje.

### El modelo transcribe, no interpreta

El prompt pide las cifras **como texto**, tal como están impresas ("15.000",
"2,5"), y quien las vuelve números es el mismo `to_decimal` del importador de
Excel. Pedirle números al modelo sería pedirle que adivine si 15.000 son quince
mil o quince: decisión ya resuelta y probada en `coercion.py`, y que un modelo
pequeño resuelve mal con frecuencia.

Por el mismo motivo el adaptador es tolerante con lo que no cambia el
significado: un modelo chico devuelve `"quantity": 2` en vez de `"2"`, o una
confianza de `95` en vez de `0.95`. Eso se acomoda; perder la factura entera por
una comilla sería absurdo. Lo que **no** se acomoda es lo ilegible: una cantidad
que no se pudo leer queda en 1 con advertencia, y un costo ilegible queda en 0
con advertencia, porque inventar un precio sí falsea la compra.

### Medir y afinar: el corpus

Cada escaneo confirmado guarda tres cosas, y juntas valen más que el modelo:
la imagen original, la **lectura cruda** (`extraction.read`) y la versión
**corregida por quien tenía el papel en la mano**. Eso es un par
(imagen, JSON correcto) por factura: el formato de entrenamiento de un modelo
de visión y el de la evaluación, acumulándose solo, sin que nadie etiquete nada
a propósito.

```bash
make invoice-corpus out=data/facturas   # exporta los pares ya revisados
make invoice-eval corpus=data/facturas  # corre el lector configurado y lo puntúa
```

```json
{"documents": 42, "read_ok": 42, "clean_readings": "31/42",
 "header_accuracy": 0.94, "line_accuracy": 0.89,
 "missed_lines": 7, "extra_lines": 2,
 "seconds_median": 2.4, "seconds_worst": 6.1}
```

Cómo leerlo:

- **`line_accuracy`** es el número que importa: un renglón cuenta solo si
  coinciden descripción, cantidad y costo.
- **`missed_lines` pesa más que `extra_lines`.** Un renglón inventado salta a la
  vista en la revisión; uno que falta entra al inventario como mercancía que
  nunca llegó.
- **`clean_readings`** es la experiencia real: cuántas facturas no habrían
  necesitado ni una corrección.
- La exportación ya trae esos mismos números calculados sobre el tráfico real,
  comparando la lectura cruda contra lo que la gente corrigió. Es una
  evaluación gratis que se actualiza todos los días.

Con `INVOICE_EXTRACTOR=claude` y `uv sync --extra claude` el mismo
`make invoice-eval` corre contra la API de Anthropic con **el mismo prompt y el
mismo esquema**. Para eso se quedó ese adaptador: para que «el modelo propio ya
alcanza» sea una medición y no una impresión.

> La exportación recorre empresa por empresa porque las políticas RLS de
> `invoice_scans` no tienen escape de plataforma: ni este proceso puede leer dos
> tenants a la vez. Es más código, y es justamente la propiedad que queremos.

### Desarrollo sin GPU y sin red

`INVOICE_EXTRACTOR=text` usa un lector determinista que entiende un `.txt` con
el formato de abajo. Todo el flujo —emparejar, revisar, confirmar, mover
inventario— es idéntico, y es lo que usan las pruebas: la suite no habla con
ningún modelo.

```text
Proveedor: Distribuidora El Sol
NIT: 900.123.456-7
Factura: F-00123
Fecha: 15/10/2026
Total: 41.000
---
2 | ARROZ DIANA X500GR | 2.500
3 | ACEITE PREMIER 1L | 12.000 | 7702007037128
```

---

## 14. Cómo añadir un módulo nuevo

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

## 15. Errores

Formato único (`BACKEND.md` §38):

```json
{"error": {"code": "PRODUCT_NOT_FOUND", "message": "Product not found", "details": {}}}
```

Las excepciones de dominio heredan de `AppError` y llevan su `code` y su
`status_code`; `presentation/api/middleware/error_handler.py` es el único punto
que las traduce a HTTP.

---

## 16. Decisiones de diseño

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
- **Registrarse crea una cuenta, no una empresa.** Antes el formulario aceptaba
  un nombre de empresa y creaba el tenant a partir de él, así que cada error de
  digitación era una empresa nueva y nadie podía saber cuál era la de verdad.
  Ahora las crea el operador, que nombra al dueño en la misma llamada.
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
- **La ruta de un archivo se genera en el servidor**, con la extensión derivada
  del content type. Filtrar nombres maliciosos es una carrera que se pierde;
  no usarlos nunca no lo es.
- **Blob primero, fila después.** El modo de fallo que queda es disco
  desperdiciado, no una descarga rota. Al borrar el orden se invierte por la
  misma razón.
- **`STORAGE_BACKEND=s3` falla ruidosamente** en vez de caer al disco local. Un
  despliegue que escribe facturas al disco efímero de un contenedor y las
  pierde en el siguiente deploy es peor que uno que no arranca.
- **La simulación de una importación es la importación**, revertida con un
  savepoint. Una validación aparte sería una segunda implementación de las
  reglas y acabaría discrepando de la primera justo cuando importa.
- **El saldo de fiado se deriva, nunca se escribe.** Mismo patrón que el stock:
  un libro append-only y una caché escrita bajo el mismo bloqueo. El cuaderno de
  fiado falla justo donde un número se puede tachar.
- **Un saldo negativo tiene nombre**: la tienda le debe al cliente. Esconderlo
  sería lo contrario de «cuentas claras».
- **El importador nunca adivina en silencio.** Propone un mapeo con su
  confianza y enseña el valor convertido al lado del crudo; lo que no puede
  leer es un error de fila, no un valor inventado.
- **El operador supervisa entrando a cada empresa por turno**, no con una
  consulta entre tenants. Cuesta unas cuantas consultas por página y a cambio
  el aislamiento no tiene una excepción más que mantener.
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

## 17. Lo que falta

- **Adaptador S3.** El puerto, los endpoints y la tabla ya están; falta
  escribir `app/infrastructure/storage/s3.py` y registrarlo en `factory.py`.
  Hasta entonces, la carpeta local necesita un volumen persistente (el compose
  ya trae uno) y no sirve para más de un nodo.
- **La lectura de facturas está apagada** (`INVOICE_EXTRACTOR=disabled`) hasta
  que el servidor tenga GPU. El módulo entero —puerto, adaptadores, revisión,
  compra, corpus, evaluación— está construido y probado; falta el modelo
  detrás (sección 13).
- **El modelo propio no está afinado.** Cuando se encienda correrá un modelo
  abierto tal como viene; la ventaja del corpus propio se materializa cuando
  haya suficientes facturas revisadas y se haga un LoRA sobre ellas.
- **La lectura es síncrona.** Ocupa la petición varios segundos. Si crece el
  volumen, el paso natural es moverla al worker Arq que ya existe.
- **Imágenes sin procesar.** No se generan miniaturas ni se valida que un
  `image/png` sea realmente un PNG más allá de la cabecera declarada.
- **Importaciones síncronas**, con un tope de 20.000 filas por archivo. Un
  archivo más grande debe partirse; el paso natural es mover la carga al worker
  Arq que ya existe y dejar el endpoint devolviendo un job que se consulta.
- **No se importa historial de ventas ni compras.** El importador cubre el
  catálogo y los saldos iniciales, que es lo que hace falta para arrancar;
  traer movimientos históricos es otro problema (numeración, fechas, estados).
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
