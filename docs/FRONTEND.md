# Guía de integración para el frontend

Todo lo necesario para construir la interfaz contra esta API, incluido lo que el
esquema OpenAPI no puede decirte: quién puede hacer qué, en qué orden van las
llamadas, qué cabecera lleva cada una y dónde están las trampas.

- **Base URL**: `http://localhost:8000` en desarrollo
- **Prefijo**: todo el negocio cuelga de `/api/v1`
- **Documentación viva**: `GET /docs` (Swagger) y `GET /api/v1/openapi.json`
- **Tipos**: genera el cliente, no lo escribas

```bash
npx openapi-typescript http://localhost:8000/api/v1/openapi.json -o src/api/schema.d.ts
```

El esquema es la fuente de verdad de *qué* campos hay. Esta guía explica el
*cómo* y el *quién*.

---

## 1. Los tres niveles de administración

Esto es lo primero que hay que entender, porque determina cuántas aplicaciones
estás construyendo (spoiler: dos).

```text
┌─────────────────────────────────────────────────────────────┐
│  SUPER ADMINISTRADOR  ·  users.is_superuser = true          │
│  Opera el SaaS. No pertenece a ninguna empresa.             │
│                                                              │
│  · Crea las empresas (es el único que puede)                │
│  · Nombra al dueño de cada una                              │
│  · Supervisa todas: métricas, planes, suspensión            │
│  · Entra a cualquiera para diagnosticar o cargarle datos    │
│  · Lee la auditoría de toda la plataforma                   │
└─────────────────────────────────────────────────────────────┘
                              │ crea
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  ADMINISTRADOR DE EMPRESA  ·  rol OWNER (o ADMIN)           │
│  Manda dentro de su empresa. No ve ninguna otra.            │
│                                                              │
│  · Arma su equipo: da de alta, cambia roles, desactiva      │
│  · Crea roles propios y decide sus permisos                 │
│  · Todo el negocio: catálogo, inventario, ventas, compras   │
│  · Reportes y auditoría de su empresa                       │
└─────────────────────────────────────────────────────────────┘
                              │ da de alta
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  MIEMBRO  ·  SELLER, INVENTORY_MANAGER, o un rol propio     │
│  Hace su trabajo, con los permisos que su rol le concede.   │
└─────────────────────────────────────────────────────────────┘
```

### Quién puede qué

| Acción | Super admin | Admin de empresa | Miembro |
|---|:--:|:--:|:--:|
| Crear una empresa | ✅ | ❌ | ❌ |
| Ver **todas** las empresas | ✅ | ❌ | ❌ |
| Suspender / reactivar una empresa | ✅ | ❌ | ❌ |
| Asignar plan y suscripción | ✅ | ❌ | ❌ |
| Vincular a alguien a **cualquier** empresa | ✅ | ❌ | ❌ |
| Crear cuentas de usuario | ✅ | ✅ (al dar de alta) | ❌ |
| Gestionar miembros de **su** empresa | ✅ | ✅ | ❌ |
| Crear y editar roles propios | ✅ | ✅ | ❌ |
| Operar el negocio (ventas, inventario…) | ✅ * | ✅ | según su rol |
| Auditoría de la plataforma | ✅ | ❌ | ❌ |
| Auditoría de su empresa | ✅ | ✅ | con `audit.read` |

\* **El super admin tiene control total de cualquier empresa.** Entra mandando
su `X-Company-ID` y usa los mismos endpoints que un miembro, con permisos
completos: catálogo, inventario, ventas, compras, roles, equipo, reportes e
importaciones. No necesita ser miembro y no hay nada reservado al administrador
de empresa.

La única restricción es de **alcance por petición**: nunca ve dos empresas en la
misma respuesta. Para comparar entre empresas está
`/admin/companies/supervision`, que las recorre una por una. Es lo que mantiene
el aislamiento como una propiedad del sistema y no como una promesa.

### Dos aplicaciones, no una

En la práctica vas a construir:

1. **La app del negocio** — catálogo, inventario, ventas, compras, equipo,
   roles, reportes. La usan el administrador de empresa y sus miembros.
2. **La consola de plataforma** — empresas, usuarios, planes, supervisión,
   auditoría global. La usa solo el super admin.

Pueden vivir en el mismo proyecto con rutas distintas (`/app` y `/admin`), pero
son públicos distintos, con menús y navegación distintos.

---

## 2. Los dos ejes: quién eres y en qué empresa estás

```text
Authorization: Bearer <access_token>   →  quién eres          (siempre)
X-Company-ID: <uuid>                   →  en qué empresa      (casi siempre)
```

Un usuario puede pertenecer a **varias empresas**. El token dice quién es, no
dónde está trabajando. El backend nunca confía en la cabecera por sí sola:
valida que seas miembro activo de esa empresa antes de dejarte hacer nada, en
cada petición.

Tres grupos **no** llevan `X-Company-ID`:

| Grupo | Por qué |
|---|---|
| `/api/v1/auth/*` | Todavía no hay empresa elegida |
| `GET /api/v1/companies` | Es la lista para elegir |
| `/api/v1/admin/*` | Son de plataforma; la empresa va en la ruta |

Si falta donde hace falta:

```json
{"error": {"code": "COMPANY_REQUIRED",
           "message": "X-Company-ID header is required for this endpoint",
           "details": {}}}
```

Ponla en el cliente HTTP una vez, no en cada llamada.

---

## 3. Cómo nace una empresa y cómo entra la gente

**No hay autoservicio.** Registrarse crea una cuenta y nada más. Las empresas
las crea el super admin, que nombra a su dueño en la misma llamada.

```text
1. El super admin crea la empresa               POST /admin/companies
   └─ la empresa nace con un OWNER designado
2. Ese OWNER inicia sesión                      POST /auth/login
   └─ GET /companies le devuelve su empresa
3. El OWNER arma su equipo                      POST /companies/current/members
   └─ crea la cuenta si la persona no la tiene
4. El OWNER define roles propios                POST /roles
```

### Registro: solo una cuenta

```http
POST /api/v1/auth/register
{"email": "ana@x.com", "password": "clave-larga",
 "first_name": "Ana", "last_name": "Gómez"}
```

```json
{"id": "8e30…", "email": "ana@x.com", "first_name": "Ana", "last_name": "Gómez",
 "is_active": true, "is_superuser": false, "created_at": "…"}
```

> **Cambió respecto a versiones anteriores.** El registro aceptaba
> `company_name` y creaba un tenant a partir de ese texto, así que cada error
> de digitación era una empresa nueva. Ese campo ya no existe; si lo mandas, se
> ignora. La respuesta tampoco trae `company_id`.

Una cuenta recién creada **no pertenece a ninguna empresa**: `GET /companies`
devuelve `[]`. Esa lista vacía es la señal para mostrar la pantalla de
«todavía no perteneces a ninguna empresa; pídele a tu administrador que te
agregue».

`POST /api/v1/companies` **no existe** (responde `405`). La regla también está
en la base de datos: la policy de RLS sobre `companies` exige el flag de
plataforma para insertar, así que ningún endpoint futuro puede reabrir la
puerta por descuido.

### El super admin crea la empresa

```http
POST /api/v1/admin/companies
Authorization: Bearer <token del super admin>

{"name": "Ferretería Central",
 "owner_email": "ana@x.com",
 "owner_password": "clave-inicial",   // solo si la cuenta no existe
 "plan_code": "STANDARD"}
```

```json
{
  "company": {"id": "9d86…", "name": "Ferretería Central", "status": "ACTIVE", "…": "…"},
  "owner": {"id": "8e30…", "email": "ana@x.com", "is_superuser": false, "…": "…"},
  "owner_created": false,
  "subscription": {"status": "TRIALING", "current_period_end": "…", "…": "…"}
}
```

- Si `owner_email` ya tiene cuenta, esa persona pasa a ser dueña y
  `owner_password` sobra.
- Si no la tiene, la contraseña es obligatoria, o llega
  `422 OWNER_PASSWORD_REQUIRED`.
- **`owner_created` te dice si hay que entregarle credenciales.** Muéstralo en
  la pantalla de confirmación.

### El administrador de empresa arma su equipo

```http
POST /api/v1/companies/current/members
Authorization: Bearer <token del OWNER>
X-Company-ID: 9d86…

{"email": "luis@x.com", "role": "SELLER",
 "password": "clave-inicial", "first_name": "Luis", "last_name": "Paz"}
```

```json
{"id": "4d0b…", "user_id": "75f6…", "email": "luis@x.com",
 "full_name": "Luis Paz", "role": "SELLER", "role_id": "2cc5…", "is_active": true}
```

- Si el correo **ya tiene cuenta**, se vincula esa cuenta y `password` sobra.
- Si **no la tiene**, hacen falta `password` y `first_name`. Si no van:

```json
{"error": {"code": "ACCOUNT_DETAILS_REQUIRED",
           "message": "No account exists for that email address. Send a password (and optionally a name) to create it.",
           "details": {}}}
```

Diseña el formulario para eso: pide el correo, y si el backend responde
`ACCOUNT_DETAILS_REQUIRED`, despliega los campos de nombre y contraseña. O
pídelos siempre y déjalos opcionales.

> **Todavía no hay invitaciones por correo.** Quien da de alta fija la primera
> contraseña y la entrega por fuera. Nada verifica que la dirección sea de esa
> persona. Ponlo en la copia de la pantalla para que el administrador lo sepa.

### Cambiar el rol de alguien

```http
PATCH /api/v1/companies/current/members/{user_id}
{"role": "INVENTORY_MANAGER", "is_active": true}
```

Nadie puede cambiarse el rol a sí mismo (`CANNOT_CHANGE_OWN_ROLE`): así el
último dueño no se degrada y deja la empresa sin administración. Deshabilita el
control en la fila del usuario actual.

### El super admin también puede vincular por id

La vía de reparación, cuando una empresa se queda sin administrador:

```http
POST  /api/v1/admin/companies/{company_id}/members    {"email", "role", …}
PATCH /api/v1/admin/companies/{company_id}/members/{user_id}   {"role", "is_active"}
```

Mismo cuerpo que la versión de empresa, pero la empresa va **en la ruta** y no
hace falta `X-Company-ID`. Ambas quedan en la auditoría (`MEMBER_ADDED`,
`MEMBER_ROLE_CHANGED`).

---

## 4. Detectar el rol en el frontend

Al arrancar la sesión necesitas responder dos preguntas.

### ¿Es super admin?

`GET /api/v1/auth/me` lo dice:

```json
{"id": "8e30…", "email": "ops@x.com", "first_name": "Ops", "last_name": "Admin",
 "is_active": true, "is_superuser": true, "created_at": "…"}
```

Sale de la columna de la base, nunca de un claim del token: si le quitas el rol
a alguien, surte efecto en su siguiente petición sin esperar a que expire el
JWT.

> **Esto importa más de lo que parece.** Un operador **no es miembro de ninguna
> empresa**, así que `GET /companies` le devuelve `[]`. Si tu guard de arranque
> solo mira esa lista, lo mandarás a la pantalla de «no perteneces a ninguna
> empresa» — cuando en realidad puede administrarlas todas. `is_superuser` es
> lo que te deja ramificar antes de llegar ahí.

### ¿Qué puede hacer dentro de su empresa?

```http
GET /api/v1/companies        → tu rol en cada empresa (campo "role")
GET /api/v1/roles            → los roles de esta empresa, con sus permisos
```

Cruza tu `role` con el rol correspondiente de `/roles` para obtener tu lista de
permisos. `OWNER` trae el comodín `"*"`.

Un detalle que muerde: `/roles` devuelve **primero los del sistema**, y una
empresa puede definir un rol propio con el mismo código. Al buscar el tuyo,
prefiere el que tiene `company_id` no nulo — es el que el backend aplica.

```ts
const can = (permission: string) =>
  myPermissions.includes("*") || myPermissions.includes(permission);
```

**Los permisos se leen en cada petición**, así que un cambio de rol surte
efecto sin volver a iniciar sesión. No los guardes en el token (no están ahí) ni
los caches indefinidamente: recárgalos al entrar y al cambiar de empresa.

### Regla de oro

Esconder un botón es cortesía, no seguridad. El backend rechaza igual y te dice
exactamente qué faltó:

```json
{"error": {"code": "INSUFFICIENT_ROLE",
           "message": "Role SELLER cannot perform 'products.create'",
           "details": {"required_permission": "products.create", "role": "SELLER"}}}
```

Usa `details.required_permission` para un mensaje útil («necesitas el permiso
*Crear productos*») en vez de un «no autorizado» seco.

### Cómo entra el operador a una empresa

Su selector **no** es `GET /companies` (que para él está vacío), sino la consola:
`GET /admin/companies/supervision`, que además viene paginada, con búsqueda y
con las métricas de cada empresa. Desde esa tabla, «Entrar a esta empresa» es
simplemente fijar el `X-Company-ID` y abrir la app del negocio.

```text
Consola  →  tabla de empresas  →  [Entrar]  →  setCompany(id)  →  app del negocio
```

A partir de ahí usa **los mismos endpoints que cualquier miembro**, con permisos
totales dentro de esa empresa: catálogo, inventario, ventas, compras, roles,
equipo, reportes e importaciones. Lo verificamos endpoint por endpoint; no hay
nada que un administrador de empresa pueda hacer y el operador no.

Lo único que **no** puede es ver dos empresas en la misma petición. Los
agregados entre empresas viven en `/admin/companies/supervision`, que los
calcula entrando a cada una por turno.

Deja visible en qué empresa está parado (`GET /companies/current` te da el
nombre) y una salida rápida a la consola; si no, es fácil creer que estás
mirando una empresa y estar en otra.

---

## 5. Roles y permisos

Los roles viven en la base de datos. Cada empresa tiene cuatro del sistema y
puede crear los suyos.

| Rol del sistema | Para quién | Resumen |
|---|---|---|
| `OWNER` | El dueño que nombra el super admin | Comodín `*`: todo dentro de su empresa |
| `ADMIN` | Segundo al mando | Todo menos el comodín |
| `INVENTORY_MANAGER` | Bodega y compras | Catálogo, inventario, compras, **escanear facturas**, reportes |
| `SELLER` | Mostrador | Ver catálogo y stock, crear ventas, clientes, **fiar y recibir abonos**, ver facturas escaneadas |

Los roles del sistema son **iguales para todas las empresas y nadie los puede
editar** (`403 SYSTEM_ROLE_IMMUTABLE`). Quien quiera «ADMIN menos algo» crea un
rol propio.

### Roles propios

```http
POST /api/v1/roles
{"code": "cajero", "name": "Cajero",
 "permissions": ["company.read", "products.read", "sales.read", "sales.create"]}
```

- El `code` se normaliza a mayúsculas: `cajero` → `CAJERO`.
- Un rol propio con el mismo código que uno del sistema **gana** dentro de esa
  empresa, así que se puede endurecer un built-in localmente.
- Solo un `OWNER` puede crear un rol con el comodín `*`
  (`CANNOT_GRANT_WILDCARD`): si no, un `ADMIN` podría fabricarse un rol más
  poderoso que el suyo.
- Un rol que todavía tiene miembros no se borra (`409 ROLE_IN_USE`).
- `PATCH` reemplaza la lista de permisos **entera**, no hace merge.

`GET /api/v1/roles/permissions` devuelve los 38 permisos con etiqueta y módulo
— es lo que necesitas para la pantalla de edición.

| Módulo | Permisos |
|---|---|
| system | `*` |
| company | `company.read` `company.update` `members.read` `members.manage` `roles.read` `roles.manage` |
| catalog | `categories.read` `categories.write` `products.read` `products.create` `products.update` `products.delete` |
| inventory | `warehouses.read` `warehouses.write` `inventory.read` `inventory.adjust` `inventory.transfer` |
| partners | `customers.read` `customers.write` `suppliers.read` `suppliers.write` |
| credit | `credit.read` `credit.manage` |
| sales | `sales.read` `sales.create` `sales.cancel` |
| purchases | `purchases.read` `purchases.create` `purchases.cancel` |
| invoices | `invoices.read` `invoices.scan` |
| imports | `imports.read` `imports.run` |
| files | `files.read` `files.write` |
| reports | `reports.read` |
| audit | `audit.read` |

---

## 6. Autenticación y sesión

```text
POST /api/v1/auth/register    público    crea una cuenta
POST /api/v1/auth/login       público    devuelve el par de tokens
POST /api/v1/auth/refresh     público    rota el par
GET  /api/v1/auth/me          bearer     el usuario del token
POST /api/v1/auth/logout      bearer     204, sin estado
```

```json
{"access_token": "eyJ…", "refresh_token": "eyJ…",
 "token_type": "bearer", "expires_in": 900}
```

**El access token dura 15 minutos**; el refresh, 14 días. Necesitas el
interceptor de refresco desde el primer día. `/auth/refresh` devuelve **ambos**
tokens: guarda los dos.

| Código | Qué hacer |
|---|---|
| `INVALID_CREDENTIALS` | Correo o clave mal |
| `INACTIVE_USER` | Cuenta desactivada: login con mensaje |
| `TOKEN_EXPIRED` / `INVALID_TOKEN` | Cerrar sesión, ir al login |

El logout **no revoca nada**: el cliente borra sus tokens, pero uno robado
sirve hasta que expira.

### Dónde guardar los tokens

`localStorage` es simple y vulnerable a XSS. Si la app maneja dinero — y esta lo
hace — vale el esfuerzo de dejar el access token en memoria y el refresh en una
cookie `httpOnly`. Decídelo antes de tener pantallas construidas encima.

---

## 7. Elegir empresa

Después del login, antes de cualquier otra cosa:

```json
[{"company_id": "9d86…", "company_name": "Ferretería Central",
  "role": "OWNER", "is_active": true}]
```

- **Una sola** → entra directo y guarda el `company_id`.
- **Varias** → selector; recuerda la elección y respétala al volver.
- **Ninguna** → pantalla de «todavía no perteneces a ninguna empresa».

> **Cuidado.** Cambiar de empresa es cambiar la cabecera *y recargar todo el
> estado*. No hay nada compartido entre empresas, y mezclar datos de dos es el
> bug más caro que puedes introducir. Limpia la caché del cliente de datos
> (`queryClient.clear()`) al cambiar.

### Si la empresa queda suspendida

El super admin puede suspenderla. Desde la siguiente petición de sus miembros
llega `403 INVALID_COMPANY`. Trátalo como un estado de la aplicación: pantalla
explicativa y vuelta al selector. El super admin **sí** sigue pudiendo entrar,
que suele ser el motivo por el que la está mirando.

---

## 8. Convenciones de la API

### Los decimales son strings. Siempre.

```json
{"sale_price": "15000.0000", "quantity": "2.0000", "total": "30000.0000"}
```

Cuatro decimales, como texto. **No uses `parseFloat` para dinero.** Usa
`decimal.js`, `dinero.js` o `BigInt` sobre centavos. Un `0.1 + 0.2` en una
factura es un problema real.

Al **enviar** también manda strings. El backend acepta número o string, pero un
`Number` grande en JavaScript ya perdió precisión antes de salir de tu código.

### Fechas

ISO 8601 en UTC con `Z`: `"2026-09-21T02:36:53.241334Z"`. Convierte a la zona
del usuario para mostrar; manda UTC de vuelta.

### Paginación

```json
{"items": [...], "total": 42, "page": 1, "size": 20, "pages": 3}
```

`?page=1&size=20`, con `size` máximo **100**. Las listas cortas y acotadas
(categorías, bodegas, roles, miembros) devuelven un array pelado.

### X-Request-ID

Cada respuesta trae uno y aparece en los logs del backend. Muéstralo en tus
pantallas de error — ahorra horas de diagnóstico.

### Enumeraciones

| Enum | Valores |
|---|---|
| `CompanyStatus` | `ACTIVE` `SUSPENDED` `INACTIVE` |
| `DocumentType` | `NIT` `CC` `CE` `PASSPORT` `RUT` `OTHER` |
| `SaleStatus` | `DRAFT` `COMPLETED` `CANCELLED` `REFUNDED` |
| `PaymentMethod` | `CASH` `TRANSFER` `CREDIT` |
| `EntryType` (fiado) | `SALE` `PAYMENT` `SALE_REVERSED` `ADJUSTMENT` |
| `PurchaseStatus` | `DRAFT` `COMPLETED` `CANCELLED` |
| `MovementType` | `PURCHASE` `SALE` `RETURN` `ADJUSTMENT` `TRANSFER_IN` `TRANSFER_OUT` |
| `ReferenceType` | `SALE` `PURCHASE` `TRANSFER` `MANUAL` |
| `SubscriptionStatus` | `TRIALING` `ACTIVE` `PAST_DUE` `CANCELLED` |
| `NotificationType` | `LOW_STOCK` `SUBSCRIPTION` `REPORT_READY` `SYSTEM` |
| `FileOwnerType` | `PRODUCT` `COMPANY` `SALE` `PURCHASE` `IMPORT` `EXPORT` `REPORT` |
| `ImportEntity` | `CATEGORIES` `PRODUCTS` `WAREHOUSES` `CUSTOMERS` `SUPPLIERS` `STOCK` |
| `ImportStatus` | `ANALYZED` `VALIDATED` `COMPLETED` `FAILED` `CANCELLED` |

Tradúcelos en el frontend; la API habla en códigos.

---

## 9. Errores

**Todos** tienen la misma envoltura. Nunca parsees el `message`; ramifica por
`code`.

```json
{"error": {"code": "DUPLICATE_SKU",
           "message": "A product with that SKU already exists in this company",
           "details": {}}}
```

| HTTP | Qué pasó | Qué hace la UI |
|---|---|---|
| 401 | Token inválido o expirado | Refrescar; si falla, login |
| 403 `INSUFFICIENT_ROLE` | Le falta un permiso | Mensaje con `required_permission` |
| 403 `INVALID_MEMBERSHIP` | No pertenece a esa empresa | Selector de empresa |
| 403 `INVALID_COMPANY` | Empresa suspendida | Pantalla de empresa bloqueada |
| 403 `NOT_PLATFORM_ADMIN` | Ruta de plataforma | Ocultar la consola de admin |
| 404 | No existe **o no es de esta empresa** | «No encontrado» |
| 405 | La ruta no existe (p. ej. `POST /companies`) | Bug del cliente |
| 409 | Choque de unicidad | Error junto al campo |
| 422 | Regla de negocio o validación | Mensaje específico |
| 503 | Dependencia caída | Reintentar |

Sobre el `404`: pedir el producto de **otra** empresa devuelve 404, no 403. Es
deliberado — un 403 confirmaría que ese id existe. Para tu UI es «no existe».

### Errores con contexto útil

```json
{"error": {"code": "INSUFFICIENT_STOCK",
  "details": {"available": "8.0000", "requested": "999.0000",
              "product_id": "e3de…", "warehouse_id": "386f…"}}}
```

Con eso dices «solo quedan 8 unidades» en vez de «error».

### Validación de esquema

`VALIDATION_ERROR` trae `location` para pintar el error junto al input:

```json
{"error": {"code": "VALIDATION_ERROR", "details": {"fields": [
  {"location": ["body", "sku"], "message": "String should have at least 1 character",
   "type": "string_too_short"}]}}}
```

### Los que más vas a tocar

**Cuentas y empresas**: `EMAIL_ALREADY_REGISTERED`, `ACCOUNT_DETAILS_REQUIRED`,
`OWNER_PASSWORD_REQUIRED`, `MEMBERSHIP_ALREADY_EXISTS`, `CANNOT_CHANGE_OWN_ROLE`,
`CANNOT_DEMOTE_SELF`, `CANNOT_DEACTIVATE_SELF`
**Roles**: `SYSTEM_ROLE_IMMUTABLE`, `DUPLICATE_ROLE_CODE`, `ROLE_IN_USE`,
`UNKNOWN_PERMISSION`, `CANNOT_GRANT_WILDCARD`, `ROLE_NOT_FOUND`
**Catálogo**: `DUPLICATE_SKU`, `DUPLICATE_BARCODE`, `DUPLICATE_CATEGORY_NAME`
**Inventario**: `INSUFFICIENT_STOCK`, `SAME_WAREHOUSE_TRANSFER`, `INACTIVE_WAREHOUSE`
**Ventas/compras**: `EMPTY_SALE`, `INVALID_SALE_TRANSITION`, `INACTIVE_CUSTOMER`,
`INACTIVE_PRODUCT`
**Fiado**: `CREDIT_SALE_NEEDS_CUSTOMER`, `OVERPAID_SALE`, `CREDIT_LIMIT_EXCEEDED`,
`PAYMENT_EXCEEDS_BALANCE`, `INVALID_ACCOUNT_ENTRY`
**Archivos**: `FILE_TOO_LARGE`, `UNSUPPORTED_FILE_TYPE`, `EMPTY_FILE`
**Importación**: `MISSING_REQUIRED_COLUMNS`, `UNKNOWN_TARGET_FIELD`,
`IMPORT_NOT_OPEN`, `UNREADABLE_FILE`

---

## 10. Flujos de negocio

### Venta (punto de venta)

```http
POST /api/v1/sales
{"warehouse_id": "…", "customer_id": "…", "complete": true,
 "items": [{"product_id": "…", "quantity": "2"}]}
```

- Sin `unit_price`, se usa el `sale_price` vigente del producto. Mándalo solo
  cuando haya precio negociado.
- `complete: true` bloquea el stock, valida, crea la venta, sus líneas y los
  movimientos, y descuenta — **todo en una transacción**.
- Los totales los calcula el backend desde las líneas: no se puede cobrar algo
  distinto a lo que suman los ítems.

> Si una línea se queda sin stock, **la venta entera se revierte**. No existe el
> estado a medias; no lo modeles en la UI.

```text
DRAFT ──/complete──> COMPLETED ──/cancel──> CANCELLED   (devuelve stock)
  │                      │
  │                      └──/refund──> REFUNDED         (devuelve stock)
  └──/cancel──> CANCELLED                               (no tocó stock)
```

`INVALID_SALE_TRANSITION` responde a un cambio imposible; deshabilita los
botones según `status`.

### Compra

Espejo de la venta, pero suma stock. Las líneas llevan `unit_cost`,
obligatorio. Al completar puedes refrescar el costo de los productos:

```http
POST /api/v1/purchases/{id}/complete?update_product_costs=true
```

Es *opt-in*: muchos negocios prefieren costo promedio ponderado.

### Inventario

```http
GET  /api/v1/inventory/stock?product_id=&warehouse_id=&only_non_zero=true
GET  /api/v1/inventory/movements?product_id=&reference_id=
POST /api/v1/inventory/adjustments  {"product_id","warehouse_id","quantity_delta":"-3","notes":"Rotura"}
POST /api/v1/inventory/transfers    {"product_id","source_warehouse_id","destination_warehouse_id","quantity":"5"}
```

`quantity_delta` es **con signo**: es la diferencia, no la cantidad final.

Los movimientos son el historial auditable, y `reference_id` apunta a la venta
o compra que lo originó — puedes enlazar del kardex al documento.

### Cuentas de fiado

```http
GET  /api/v1/credit/summary                            cuánto me deben en total
GET  /api/v1/credit/accounts?search=&only_with_balance= quién debe
GET  /api/v1/credit/accounts/{customer_id}             saldo e historial
POST /api/v1/credit/accounts/{customer_id}/payments    registrar un abono
POST /api/v1/credit/accounts/{customer_id}/adjustments perdón o corrección
```

La lista viene ordenada por saldo, el que más debe primero. Con
`only_with_balance=false` incluye a los que están al día, que es lo que
necesitas para elegir a quién fiarle.

La cuenta de un cliente trae el saldo ya descompuesto, para que la pantalla no
tenga que razonar sobre signos:

```json
{"customer_id": "…", "customer_name": "Doña Rosa", "phone": "3001112233",
 "balance": "2400.0000", "owes": "2400.0000", "in_favor": "0",
 "credit_limit": "20000.0000", "available_credit": "17600.0000",
 "entries": [{"entry_type": "PAYMENT", "amount": "-5000.0000",
              "notes": "Abono del viernes", "created_at": "…"}],
 "total_entries": 2, "page": 1, "size": 20, "pages": 1}
```

`entries` es el historial, lo más reciente primero, y cada peso del saldo se
explica con uno de ellos. Los tipos son `SALE`, `PAYMENT`, `SALE_REVERSED` y
`ADJUSTMENT`; el `amount` lleva signo (positivo debe más, negativo debe menos).

**Registrar un abono** devuelve la cuenta ya actualizada, que es justo lo que la
pantalla necesita pintar enseguida:

```json
POST /credit/accounts/{id}/payments
{"amount": "5000", "method": "CASH", "notes": "Abono del viernes"}
```

Un abono mayor a la deuda se rechaza (`PAYMENT_EXCEEDS_BALANCE`): casi siempre
es un error de digitación, 50000 por 5000.

> **El saldo puede ser negativo, y tiene nombre.** `in_favor` mayor que cero
> significa que **la tienda le debe al cliente**. Pasa al devolver una venta que
> ya tenía abonos. El tendero lo salda con un ajuste
> (`POST /adjustments` con monto positivo y una nota) cuando le entrega la plata.
> La cuenta sigue apareciendo en la lista: esconder una deuda de la tienda sería
> lo contrario de «cuentas claras».

Los ajustes exigen `notes`; un ajuste sin explicación es lo que vuelve turbias
las cuentas.

### Reportes

```http
GET /api/v1/reports/sales?since=&until=&limit=10
GET /api/v1/reports/inventory-valuation
GET /api/v1/reports/low-stock?limit=50
GET /api/v1/reports/audit?action=SALE_COMPLETED
```

El de ventas cuenta **solo las `COMPLETED`**: los borradores no ocurrieron y las
canceladas o devueltas ya regresaron el dinero.

### Notificaciones

`GET /api/v1/notifications?only_unread=true` devuelve `unread` aparte del
`total` — es lo que necesitas para el badge. **No hay websockets ni SSE**: haz
polling cada 60 s o al recuperar el foco. Las alertas de stock bajo las genera
un job diario a las 07:00.

---

## 11. Importación masiva desde Excel

Dos fases a propósito: nada se adivina en silencio.

```text
1. GET  /imports/schemas              campos destino de cada entidad
   GET  /imports/templates/{entity}   plantilla .xlsx (el camino fácil)
2. POST /imports                      multipart: file + entity
                                      → propone mapeo y vista previa, no escribe
3. PATCH /imports/{id}/mapping        el usuario corrige columnas
4. POST /imports/{id}/validate        simulación: ejecuta y revierte
   POST /imports/{id}/run             carga de verdad
```

El paso 2 devuelve todo lo que la pantalla de mapeo necesita:

```json
{
  "total_rows": 3,
  "columns": [
    {"source": "Referencia", "suggested_target": "sku", "confidence": 1.0,
     "reason": "exact", "needs_review": false, "samples": ["mar-01", "DES-02"]},
    {"source": "Centro de costo", "suggested_target": null,
     "confidence": 0.0, "reason": "unmatched", "samples": ["CC-900"]}
  ],
  "target_fields": [{"key": "sku", "label": "SKU", "type": "TEXT", "required": true,
                     "help": "…", "example": "MAR-01", "enum_values": []}],
  "missing_required": [],
  "preview": [{"row_number": 4, "cells": [
    {"field_key": "sale_price", "raw": "$ 15.000", "value": "15000", "error": null}]}]
}
```

Cómo renderizarlo:

- **Dos columnas**: a la izquierda `columns` con sus `samples` reales; a la
  derecha un `<select>` con `target_fields`.
- **`needs_review: true`** → marca visual. El acierto es plausible pero no
  seguro («Centro de costo» se parece a un costo y no lo es).
- **`missing_required`** → no dejes avanzar; el backend responde
  `MISSING_REQUIRED_COLUMNS` igual.
- **`preview` es lo más valioso**: muestra `raw` y `value` lado a lado. Ahí el
  usuario ve que su `1.500` se leyó como 1500 y no como 1,5. Si `error` no es
  nulo, pinta la celda en rojo.

Si los números se leen mal, se fija el criterio al corregir el mapeo:

```json
{"mapping": {"Referencia": "sku", "PVP": "sale_price"},
 "decimal_separator": ".", "date_format": "%d/%m/%Y",
 "options": {"create_missing_categories": true}}
```

> **La simulación no es una estimación.** `validate` corre el cargador real
> dentro de un savepoint y lo revierte, así que sus números incluyen las
> restricciones de la base. Enseña el resumen y pide confirmación antes de
> `run`.

```json
{"dry_run": true,
 "stats": {"total_rows": 100, "created": 95, "updated": 3, "skipped": 2, "errors": 2},
 "errors_preview": [{"row_number": 12, "column": "PVP", "field_key": "sale_price",
                     "value": "mil pesos", "message": "'mil pesos' is not a valid number"}]}
```

Los errores de fila se paginan en `GET /imports/{id}/errors`. El `row_number` es
el de **la hoja del usuario** (contando encabezado y filas en blanco) y
`column` es el nombre de **su** columna. Una tabla con esas dos cosas basta para
que arregle su archivo.

Detalles que afectan la UI:

- Todas las entidades hacen **upsert**: resubir un archivo corregido es normal.
- Orden recomendado: categorías → bodegas → productos → clientes → proveedores
  → stock.
- Un job terminado no se reejecuta (`IMPORT_NOT_OPEN`); sube el archivo otra vez.
- Tope de 20.000 filas (`IMPORT_TOO_LARGE`).
- Las importaciones son **síncronas**: pon un estado de carga que aguante, no un
  spinner de 3 segundos.

---

## 12. Escanear la factura del proveedor

> **Hoy esta capacidad viene apagada en el servidor.** `POST /invoices/scans`
> responde `503 INVOICE_SCANNING_DISABLED` hasta que haya un modelo detrás.
> Antes de mostrar el botón, consulta `GET /health`:
>
> ```json
> {"status": "ok", "features": {"invoice_scanning": false}}
> ```
>
> Con `false`, oculta la entrada (o déjala visible y deshabilitada con un
> «próximamente»). El resto de esta sección describe el flujo completo, que ya
> está construido: cuando la bandera pase a `true` no hay nada que cambiar en
> el frontend.

La promesa es la de la landing: le tomas una foto a la factura y la mercancía
entra. La regla que la hace confiable es la contraria a la magia: **ningún
renglón entra solo**. El lector propone, una persona decide, y solo entonces se
crea la compra.

```text
1. POST  /invoices/scans              multipart: file (+ warehouse_id)
                                      → lee el papel y propone; no escribe nada
2. PATCH /invoices/scans/{id}         las decisiones de la persona
   POST  /invoices/scans/{id}/rematch volver a buscar en el catálogo (gratis)
3. POST  /invoices/scans/{id}/confirm crea los productos nuevos y la compra
   POST  /invoices/scans/{id}/cancel  descartar el escaneo
```

Acepta JPG, PNG, WEBP y PDF, con el mismo tope de tamaño que los demás
archivos (`MAX_UPLOAD_SIZE_MB`). La foto queda guardada como archivo de la
empresa (`owner_type: "INVOICE"`), así que la factura original siempre se puede
volver a ver.

### Lo que devuelve el paso 1

```json
{
  "id": "…", "status": "EXTRACTED", "filename": "factura.jpg",
  "supplier_name": "Distribuidora El Sol", "supplier_tax_id": "900.123.456-7",
  "supplier_id": "…o null si no se pudo resolver con certeza",
  "warehouse_id": null,
  "invoice_number": "F-00123", "invoice_date": "2026-10-15",
  "declared_subtotal": "29000", "declared_tax": null, "declared_total": "41000",
  "lines_total": "41000", "total_mismatch": "0",
  "pending_count": 2, "review_count": 2,
  "extraction": {"source": "local:Qwen/Qwen2.5-VL-7B-Instruct",
                 "warnings": [], "lines_read": 3, "read": {"…": "la lectura cruda"}},
  "lines": [
    {"id": "…", "line_number": 1, "description": "ARROZ DIANA X500GR",
     "code": null, "quantity": "2", "unit_cost": "2500",
     "discount": "0", "tax": "0",
     "total": "5000", "declared_total": "5000", "total_mismatch": "0",
     "confidence": "1.0",
     "suggested_product_id": "…", "match_confidence": "0.914", "match_reason": "similar",
     "action": "LINK", "product_id": "…", "new_product": {}, "warnings": [],
     "needs_review": false}
  ]
}
```

Dos campos distintos a propósito, y la diferencia es todo el módulo:

- `suggested_product_id` + `match_confidence` + `match_reason` → **lo que el
  sistema cree**.
- `action` + `product_id` → **lo que se va a hacer**.

Solo un código de barras, un SKU o un nombre casi idéntico (`match_confidence
>= 0.9`) pasan de propuesta a decisión sin preguntar. Todo lo demás llega como
`PENDING`.

### Las cuatro decisiones por renglón

| `action` | Qué significa | Qué pide |
|---|---|---|
| `PENDING` | Sin decidir. **Bloquea la confirmación.** | — |
| `LINK` | Es este producto del catálogo | `product_id` |
| `CREATE` | Producto nuevo, nace de este renglón | nada; opcional `new_product` |
| `SKIP` | No es mercancía (flete, bolsas, envase) | — |

```json
PATCH /invoices/scans/{id}
{
  "warehouse_id": "…",
  "supplier_id": "…",
  "lines": [
    {"line_id": "…", "action": "LINK", "product_id": "…", "unit_cost": "2550"},
    {"line_id": "…", "action": "CREATE",
     "new_product": {"sale_price": "15000", "category_id": "…"}},
    {"line_id": "…", "action": "SKIP"}
  ]
}
```

- **Los renglones que no mandes quedan como están.** Una factura de cuarenta
  renglones se revisa en varias pasadas.
- La misma llamada corrige cifras: `quantity`, `unit_cost`, `discount`, `tax`,
  `description`. Es lo normal cuando la foto salió borrosa.
- `status` pasa a `REVIEWED` **solo** cuando `pending_count` llega a 0. Lo dice
  el trabajo que falta, no el botón que se apretó.
- `CREATE` sin `new_product`: el nombre sale de la descripción impresa, el SKU
  se genera y el costo lo pone la factura. El precio de venta queda en **0** —
  inventarlo sería peor que dejarlo visible.

### Cómo renderizar la revisión

- **Una fila por renglón, en el orden del papel** (`line_number`): quien revisa
  tiene la factura al lado.
- **`needs_review: true` → marca visual.** Es verdad cuando está `PENDING`,
  cuando se enlazó con confianza media, cuando hay `warnings`, o cuando
  `total_mismatch != 0`.
- **`warnings` por renglón** son lo que el lector no pudo leer («cantidad
  ilegible: se asumió 1, confírmala»). Píntalos; son la mitad del valor.
- **`total` vs `declared_total`**: el primero es la cuenta, el segundo lo que
  decía el papel. Si no coinciden, el renglón se leyó mal.
- **`total_mismatch` del encabezado** no siempre es un error: un flete
  descartado explica la diferencia. Enséñalo como aviso, no como bloqueo.
- **`match_reason`** da el texto del «por qué»: `barcode`, `sku`, `exact`,
  `contains`, `similar`, `unmatched`.

### Confirmar

```json
POST /invoices/scans/{id}/confirm
{"complete": true, "update_product_costs": false}
→ {"scan": {…"status": "CONFIRMED", "purchase_id": "…"},
   "purchase": {…}, "created_product_ids": ["…"]}
```

`complete: true` (el valor por defecto) completa la compra y **mueve el
inventario** por el mismo camino que una compra escrita a mano: mismos
movimientos, mismas validaciones. Con `false` queda en `DRAFT` para completarla
después desde Compras. `update_product_costs` refresca el costo de cada
producto con lo que dice la factura; está apagado por defecto porque muchos
negocios quieren promedio ponderado y no último costo.

Un escaneo confirmado es definitivo (`SCAN_NOT_OPEN`); para deshacerlo se
cancela la compra, que devuelve el stock.

### Errores propios del módulo

| Código | HTTP | Cuándo |
|---|---|---|
| `UNDECIDED_LINES` | 422 | Queda algún renglón `PENDING`. `details.pending` dice cuántos |
| `WAREHOUSE_REQUIRED` | 422 | Falta decir a qué bodega entra |
| `NOTHING_TO_PURCHASE` | 422 | Todos los renglones quedaron en `SKIP` |
| `EMPTY_INVOICE` | 422 | El documento no traía renglones (`details.warnings` explica) |
| `UNSUPPORTED_INVOICE_FILE` | 422 | No es foto ni PDF |
| `INVOICE_EXTRACTION_FAILED` | 422 | La lectura falló o el documento es ilegible |
| `SCAN_NOT_OPEN` | 422 | El escaneo ya se confirmó o se canceló |
| `INVOICE_SCANNING_DISABLED` | 503 | El servidor no tiene modelo configurado todavía (ver `GET /health`) |

### Detalles que afectan la UI

- **La lectura es síncrona y tarda.** Varios segundos para una factura normal.
  Pon un estado de carga que aguante y un reintento visible; no un spinner de
  tres segundos.
- **`rematch` es gratis** (no vuelve a leer la foto) y nunca deshace una
  decisión. Es el botón para después de crear a mano los productos que
  faltaban.
- **El proveedor se resuelve solo únicamente con coincidencia exacta** de NIT o
  de nombre normalizado. Si viene `supplier_id: null` con `supplier_name`
  lleno, ofrece el selector o un «crear proveedor» con ese nombre precargado.
- **Permisos**: `invoices.read` para ver, `invoices.scan` para escanear,
  revisar y confirmar.

---

## 13. Archivos e imágenes

```http
POST   /api/v1/files          multipart: file, owner_type, owner_id
GET    /api/v1/files?owner_type=PRODUCT&owner_id=…
GET    /api/v1/files/{id}/content
DELETE /api/v1/files/{id}
```

Para la imagen de un producto: `owner_type=PRODUCT`, `owner_id=<product_id>`.

> **La trampa más importante de esta guía.**
>
> `GET /files/{id}/content` exige `Authorization` y `X-Company-ID`. Un
> `<img src="/api/v1/files/…/content">` **no funciona**: el navegador no manda
> esas cabeceras. Hay que descargar el blob y crear un object URL.

```ts
async function fileObjectUrl(id: string): Promise<string> {
  const res = await api.get(`/files/${id}/content`, { responseType: "blob" });
  return URL.createObjectURL(res.data);
}
// y al desmontar: URL.revokeObjectURL(url)
```

Revócalo al desmontar, o tendrás una fuga de memoria en una grilla de productos.

Límites: **10 MB** y los tipos `image/jpeg`, `image/png`, `image/webp`,
`image/gif`, `application/pdf`, `text/csv`, `.xlsx`. Valida en el cliente para
dar feedback inmediato; el backend rechaza igual.

El campo `download_url` viene armado en la respuesta: úsalo en vez de construir
la ruta.

---

## 14. La consola del super admin

Rutas `/api/v1/admin/*`. **No llevan `X-Company-ID`**: la empresa va en la ruta.

```http
GET   /admin/stats                                  tablero global
GET   /admin/companies/supervision?with_metrics=    tabla de supervisión
GET   /admin/companies?search=&status=              listado simple
POST  /admin/companies                              aprovisionar
GET   /admin/companies/{id}                         una empresa
PATCH /admin/companies/{id}                         editar / suspender / reactivar
GET   /admin/companies/{id}/overview                detalle + uso del plan
GET   /admin/companies/{id}/members                 su equipo
POST  /admin/companies/{id}/members                 vincular por id
PATCH /admin/companies/{id}/members/{user_id}       cambiar rol
GET   /admin/companies/{id}/subscription            plan actual
PUT   /admin/companies/{id}/subscription            asignar plan
GET   /admin/users, POST /admin/users, PATCH /admin/users/{id}
GET   /admin/plans, POST /admin/plans, PATCH /admin/plans/{id}
GET   /admin/onboarding/template                    libro de carga inicial
POST  /admin/companies/{id}/onboarding              cargar una empresa entera
GET   /admin/audit                                  auditoría de la plataforma
```

### Tablero

```json
{"companies_total": 1, "companies_active": 1, "companies_suspended": 0,
 "users_total": 3, "users_active": 3, "platform_admins": 1}
```

### Tabla de supervisión

```json
{"items": [{
  "company": {"id": "9d86…", "name": "Ferretería Central", "status": "ACTIVE", "…": "…"},
  "plan_code": "STANDARD",
  "subscription_status": "TRIALING",
  "metrics": {"members": 2, "active_members": 2, "products": 0, "active_products": 0,
              "warehouses": 0, "customers": 0, "suppliers": 0, "sales_count": 0,
              "sales_revenue": "0", "purchases_count": 0, "stock_units": "0",
              "stock_value": "0.0000", "last_sale_at": null}
}], "total": 1, "page": 1, "size": 20, "pages": 1}
```

`with_metrics=false` es mucho más rápido: el backend entra a cada empresa por
turno para calcular sus números. Con 20 filas está bien; ofrece el modo rápido
para búsquedas.

### Detalle de una empresa

`GET /admin/companies/{id}/overview` añade la suscripción, el plan y el uso
contra sus topes:

```json
{"plan": {"code": "STANDARD", "max_users": 10, "max_products": 5000, "max_warehouses": 5},
 "usage": [{"resource": "warehouses", "used": 2, "limit": 5, "over_limit": false}],
 "days_since_last_sale": 0,
 "metrics": {"…": "…"}}
```

`limit: 0` significa **ilimitado**. Los topes hoy se muestran pero **no
bloquean** la creación del recurso.

### Suspender una empresa

```http
PATCH /admin/companies/{id}   {"status": "SUSPENDED"}
```

Sus miembros quedan fuera en la siguiente petición. El operador sigue entrando.

### Operar dentro de una empresa

El super admin puede usar **cualquier** endpoint normal mandando el
`X-Company-ID` de la empresa destino — no necesita ser miembro. Es como se
diagnostica un problema o se le carga data a un cliente. Aun así **solo ve una
empresa por petición**.

### Carga inicial de una empresa entera

```bash
curl localhost:8000/api/v1/admin/onboarding/template -H "Authorization: Bearer $ADMIN" -o carga.xlsx
curl -X POST "localhost:8000/api/v1/admin/companies/$ID/onboarding?dry_run=true" \
  -H "Authorization: Bearer $ADMIN" -F "file=@carga.xlsx"
```

Un libro con una hoja por entidad, cargadas en orden de dependencia dentro de
**un solo savepoint**: o la empresa queda montada o no se tocó nada. La
respuesta trae un resultado por hoja (`LOADED`, `LOADED_WITH_ERRORS`, `SKIPPED`,
`EMPTY`, `MISSING_COLUMNS`) más los totales. Corre siempre `dry_run=true`
primero.

---

## 15. Mapa de pantallas

### App del negocio

| Pantalla | Llamadas | Permiso |
|---|---|---|
| Login | `POST /auth/login` | — |
| Selector de empresa | `GET /companies` | bearer |
| Sin empresa | `GET /companies` → `[]` | bearer |
| Dashboard | `/reports/sales`, `/reports/low-stock`, `/notifications` | `reports.read` |
| Catálogo | `GET /products`, `GET /categories` | `products.read` |
| Ficha de producto | `GET /products/{id}`, `/files?owner_type=PRODUCT`, `/inventory/stock?product_id=` | `products.read` |
| Inventario | `GET /inventory/stock`, `GET /warehouses` | `inventory.read` |
| Kardex | `GET /inventory/movements?product_id=` | `inventory.read` |
| Ajuste / traslado | `POST /inventory/adjustments`, `/transfers` | `inventory.adjust` / `.transfer` |
| Punto de venta | `GET /products`, `GET /customers`, `POST /sales` | `sales.create` |
| **Cuentas claras** | `GET /credit/summary`, `GET /credit/accounts` | `credit.read` |
| **Cuenta de un cliente** | `GET /credit/accounts/{id}`, `POST .../payments` | `credit.read` / `.manage` |
| Ventas | `GET /sales?status=` | `sales.read` |
| Compras | `GET /purchases`, `POST /purchases` | `purchases.read` / `.create` |
| Clientes / Proveedores | `/customers`, `/suppliers` | `customers.*` / `suppliers.*` |
| **Equipo** | `GET /companies/current/members`, `GET /roles`, `POST /companies/current/members` | `members.read` / `.manage` |
| **Roles** | `GET /roles`, `GET /roles/permissions`, `POST PATCH DELETE /roles` | `roles.read` / `.manage` |
| **Escanear factura** | `POST /invoices/scans` → `PATCH` → `confirm` | `invoices.scan` |
| Facturas escaneadas | `GET /invoices/scans?status=` | `invoices.read` |
| Importar | `GET /imports/schemas` + el flujo de 4 pasos | `imports.run` |
| Reportes | `/reports/*` | `reports.read` |
| Auditoría | `GET /reports/audit` | `audit.read` |

Las dos en negrita son las del administrador de empresa.

### Consola de plataforma

| Pantalla | Llamadas |
|---|---|
| Tablero | `GET /admin/stats` |
| Empresas | `GET /admin/companies/supervision` |
| Crear empresa | `POST /admin/companies` |
| Detalle de empresa | `GET /admin/companies/{id}/overview`, `/members` |
| Equipo de una empresa | `POST PATCH /admin/companies/{id}/members` |
| Carga inicial | `GET /admin/onboarding/template`, `POST /admin/companies/{id}/onboarding` |
| Usuarios | `GET POST /admin/users`, `PATCH /admin/users/{id}` |
| Planes | `GET POST /admin/plans`, `PATCH /admin/plans/{id}` |
| Suscripciones | `PUT /admin/companies/{id}/subscription` |
| Auditoría | `GET /admin/audit` |

---

## 16. Cliente de ejemplo (TypeScript)

Resuelve las tres cosas que se repiten: la cabecera de empresa, el refresco de
token y la envoltura de error.

```ts
import axios, { AxiosError } from "axios";

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL + "/api/v1" });

const session = {
  get access() { return localStorage.getItem("access_token"); },
  get refresh() { return localStorage.getItem("refresh_token"); },
  get companyId() { return localStorage.getItem("company_id"); },
  set(tokens: { access_token: string; refresh_token: string }) {
    localStorage.setItem("access_token", tokens.access_token);
    localStorage.setItem("refresh_token", tokens.refresh_token);
  },
  setCompany(id: string) { localStorage.setItem("company_id", id); },
  clear() { localStorage.clear(); },
};

// Las dos cabeceras, una sola vez.
api.interceptors.request.use((config) => {
  if (session.access) config.headers.Authorization = `Bearer ${session.access}`;
  const url = config.url ?? "";
  const skip = url.startsWith("/auth") || url === "/companies" || url.startsWith("/admin");
  if (session.companyId && !skip) config.headers["X-Company-ID"] = session.companyId;
  return config;
});

// Refresco: una sola petición en vuelo, el resto espera.
let refreshing: Promise<void> | null = null;

api.interceptors.response.use(undefined, async (error: AxiosError<ApiError>) => {
  const original = error.config!;
  const code = error.response?.data?.error?.code;

  if (error.response?.status === 401 && !(original as any)._retried && session.refresh) {
    (original as any)._retried = true;
    refreshing ??= axios
      .post(`${api.defaults.baseURL}/auth/refresh`, { refresh_token: session.refresh })
      .then((r) => session.set(r.data))
      .catch(() => { session.clear(); location.href = "/login"; })
      .finally(() => { refreshing = null; });
    await refreshing;
    return api(original);
  }

  if (code === "INVALID_COMPANY" || code === "INVALID_MEMBERSHIP") {
    location.href = "/select-company";
  }
  return Promise.reject(error);
});

export interface ApiError {
  error: { code: string; message: string; details: Record<string, unknown> };
}

export const errorCode = (e: unknown) =>
  (e as AxiosError<ApiError>)?.response?.data?.error?.code;

export default api;
```

Arranque de la sesión, con los tres niveles resueltos:

```ts
export async function bootstrap() {
  const me = (await api.get("/auth/me")).data;

  // Un operador no es miembro de ninguna empresa: su lista viene vacía y su
  // selector es la consola, no este endpoint. Ramifica antes de mirarla.
  if (me.is_superuser) return { me, state: "plataforma" as const };

  const memberships = (await api.get("/companies")).data;
  if (!memberships.length) return { me, state: "sin-empresa" as const };

  const companyId = session.companyId ?? memberships[0].company_id;
  session.setCompany(companyId);

  const myRole = memberships.find((m: any) => m.company_id === companyId)?.role;
  const roles = (await api.get("/roles")).data;

  // Ojo: /roles devuelve primero los del sistema. Si la empresa definió uno
  // propio con el mismo código, ese es el que manda (igual que en el backend),
  // así que hay que preferir el que tiene company_id.
  const matches = roles.filter((r: any) => r.code === myRole);
  const permissions: string[] =
    (matches.find((r: any) => r.company_id !== null) ?? matches[0])?.permissions ?? [];

  return { me, memberships, companyId, myRole, permissions, state: "listo" as const };
}
```

Dinero, con `decimal.js`:

```ts
import Decimal from "decimal.js";

export const money = (value: string) => new Decimal(value);
export const formatMoney = (value: string, currency = "COP") =>
  new Intl.NumberFormat("es-CO", { style: "currency", currency })
    .format(new Decimal(value).toNumber());   // solo para mostrar
```

---

## 17. Entorno de desarrollo

```bash
docker compose up --build            # api, postgres, redis, worker
make superuser email=tu@correo.com   # el primer super admin
```

API en `http://localhost:8000`, Swagger en `/docs`.

**El primer super admin solo sale del CLI**: una base recién migrada no tiene
ninguno, y `/api/v1/admin/*` no es alcanzable hasta que exista. A partir de ahí
él puede crear otros desde `POST /admin/users` con `is_superuser: true`.

Para tener una empresa con datos: crea el super admin, aprovisiona una empresa
con `POST /admin/companies`, baja `GET /imports/templates/PRODUCTS`, llénala y
súbela.

### Leer facturas en desarrollo

Las facturas las lee **nuestro propio modelo**, en nuestro servidor
(`INVOICE_EXTRACTOR=local` apuntando a un endpoint compatible con OpenAI). Para
el frontend eso no cambia nada: el flujo, los campos y los errores son los
mismos; solo cambia `extraction.source`. Para trabajar sin GPU y sin red:

```env
INVOICE_EXTRACTOR=text        # lector determinista (el de las pruebas)
```

Con él, `POST /invoices/scans` acepta un `.txt` con este formato y el resto del
flujo es idéntico:

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

Los detalles de infraestructura —qué modelo, en qué GPU, cómo medirlo— están
en la sección 13 del README del backend. Lo único que el frontend necesita
saber es que la lectura tarda unos segundos y puede fallar con
`INVOICE_EXTRACTION_FAILED` si el servidor del modelo está caído.

### CORS

```env
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
```

Si tu dev server usa otro puerto, agrégalo ahí o las peticiones fallan antes de
llegar a la API. `X-Request-ID` está expuesto como cabecera de respuesta.

---

## 18. Limitaciones que afectan al frontend

Cosas que el backend todavía no hace y conviene saber **antes** de diseñar.

| Limitación | Qué implica |
|---|---|
| Sin tiempo real | Ni websockets ni SSE. Polling para notificaciones. |
| El logout no revoca | Un access token robado sirve 15 minutos más. |
| Las imágenes requieren autenticación | No sirve `<img src>` directo; hay que usar blobs (§13). |
| Sin invitaciones por correo | Quien da de alta fija la contraseña y la entrega. Nada verifica el correo. |
| Sin numeración consecutiva | Ventas y compras se identifican por UUID. «Factura #0001» no existe. |
| Importaciones síncronas | Tope de 20.000 filas; una carga grande bloquea la petición. |
| El escaneo de facturas está apagado | `503 INVOICE_SCANNING_DISABLED` hasta que el servidor tenga GPU. Mírala en `GET /health`. |
| El escaneo de facturas es síncrono | Cuando se encienda, la lectura tarda varios segundos y ocupa la petición. |
| Las cuotas de plan no bloquean | `max_users`, `max_products`, `max_warehouses` se muestran pero no impiden crear. |
| El registro público sigue abierto | Crea cuentas sin empresa. Si no lo quieres, quitar la ruta es un cambio chico. |
