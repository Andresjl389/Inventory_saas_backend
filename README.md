# Inventory SaaS — Backend

Backend multi-tenant construido sobre la arquitectura descrita en `BACKEND.md`:
FastAPI + PostgreSQL con Row Level Security, arquitectura hexagonal y aislamiento
de tenants en tres capas.

> Estado: **prototipo de Fase 1 + slice vertical de Fase 2**.
> Implementado: setup, base de datos, Alembic con RLS, identity, companies,
> company members, tenant context, categorías y productos.
> Pendiente: bodegas, inventario, clientes, proveedores, ventas y compras.

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

---

## 3. Estructura

```
app/
├── domain/            Entidades, value objects, puertos (Protocols), reglas.
│   ├── shared/          BaseEntity, TenantEntity, paginación
│   ├── identity/        User, Email
│   ├── tenants/         Company, CompanyMember, TenantContext, permisos
│   └── products/        Category, Product
│
├── application/       Casos de uso y DTOs. Orquesta el dominio.
│   ├── identity/        RegisterUser, AuthenticateUser, RefreshTokens
│   ├── tenants/         CreateCompany, ListMyCompanies, manage members
│   └── products/        CRUD de categorías y productos
│
├── infrastructure/    Detalles reemplazables.
│   ├── database/        modelos SQLAlchemy, repositorios, sesión,
│   │                    tenant_context.py, rls.py
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

---

## 5. Migraciones

Todo — tablas, índices, constraints, funciones, RLS y policies — vive en
Alembic. Una base vacía queda lista con:

```bash
alembic upgrade head
```

```
alembic/versions/
├── 0001_extensions_and_base.py   pgcrypto, schema app, app.current_company_id(), app.current_user_id()
├── 0002_identity_and_tenants.py  users, companies, company_members + policies a medida
└── 0003_products.py              categories, products + policies estándar
```

`app/infrastructure/database/rls.py` expone `enable_tenant_rls(op, "tabla")`,
que activa `ENABLE`/`FORCE ROW LEVEL SECURITY` y crea las cuatro policies
(SELECT/INSERT/UPDATE/DELETE). Los `downgrade()` eliminan policies, RLS y tablas
en orden inverso; el ciclo `upgrade head → downgrade base → upgrade head` está
verificado.

---

## 6. Cómo añadir un módulo nuevo

Tomando `products` como plantilla, para p. ej. `warehouses`:

1. **Dominio** — `app/domain/inventory/entities/warehouse.py` (hereda de
   `TenantEntity`), `exceptions.py` y el puerto
   `repositories/warehouse_repository.py` (un `Protocol`).
2. **Aplicación** — DTOs Pydantic y casos de uso que reciben `TenantContext`.
3. **Infraestructura** — modelo SQLAlchemy con `TenantMixin`, repositorio
   SQLAlchemy y su mapper.
4. **Migración** — `0004_inventory.py`: tabla, índices `(company_id, ...)`,
   constraints y `enable_tenant_rls(op, "warehouses")`.
5. **Presentación** — router en `api/v1/`, alta en `api/v1/router.py`,
   proveedor del repositorio en `dependencies/repositories.py` y permisos nuevos
   en `ROLE_PERMISSIONS`.
6. **Tests** — unitarios de la entidad, RLS de aislamiento y tests de API.

---

## 7. Errores

Formato único (`BACKEND.md` §38):

```json
{"error": {"code": "PRODUCT_NOT_FOUND", "message": "Product not found", "details": {}}}
```

Las excepciones de dominio heredan de `AppError` y llevan su `code` y su
`status_code`; `presentation/api/middleware/error_handler.py` es el único punto
que las traduce a HTTP.

---

## 8. Decisiones tomadas en el prototipo

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

## 9. Siguiente paso sugerido

Fase 2 completa: `warehouses`, `product_stock` y `stock_movements` con
`SELECT ... FOR UPDATE` sobre `product_stock` dentro de la transacción, tal como
describe `BACKEND.md` §28–29.
