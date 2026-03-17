# DeOrganized API — Work Log

## 2026-03-16 — Buidl Battle Sprint: Proxy Layer + Three-Service Architecture

### What was done

#### 1. Discovered three-service Railway architecture

The backend is three separate Railway deployments with a shared API key (`X-API-Key`):

| Service | Env var | Purpose |
|---------|---------|---------|
| DAP Service | `DAP_SERVICE_URL` | Credit economy — register, balance, transactions |
| Agent API (Long Elio) | `AGENT_API_URL` | Content generation, news pipeline, agent chat, wallet |
| Social Agent | `SOCIAL_AGENT_URL` | Nostr/Twitter broadcaster, social wallet, DAP credits |

`AGENT_CONTROLLER_URL` exists but is only used by the DCPE operations proxy (`/ops/`) — not by the new content/agent endpoints.

#### 2. Created `feature/content-engine` branch

Branch off `main` in `deorganizedapi`. All proxy work lives here until connected to the frontend.

#### 3. Added 16 proxy endpoints in `api/views_ops.py` + `api/urls_content.py`

Mounted at `/api/` via `deorganized/urls.py`.

**DAP Credit Service** (`DAP_BASE` → `DAP_SERVICE_URL`):

| Django URL | Upstream | Notes |
|-----------|----------|-------|
| `GET /api/dap/status/` | `GET /api/status` | Auth required |
| `POST /api/dap/register/` | `POST /api/register` | Body forwarded |
| `GET /api/dap/balance/<address>/` | `GET /api/users/<address>/balance` | |
| `GET /api/dap/transactions/<address>/` | `GET /api/users/<address>/transactions` | |

**Content Generation / Long Elio** (`AGENT_BASE` → `AGENT_API_URL`):

| Django URL | Upstream | Notes |
|-----------|----------|-------|
| `POST /api/content/generate/` | `POST /api/dap/generate` | Auth required |
| `GET /api/content/status/` | `GET /news/status` | |
| `GET /api/content/latest/` | `GET /news/latest` | |
| `GET /api/content/history/` | `GET /news/history` | |
| `GET /api/content/thumbnail/<date>/<format>/` | `GET /news/thumbnail/<date>/<format>` | Binary image pass-through (`HttpResponse`, not JSON) |
| `GET /api/agent/wallet/` | `GET /wallet` | |
| `POST /api/agent/chat/` | `POST /agent/chat` | Body forwarded |

**Social Agent** (`SOCIAL_BASE` → `SOCIAL_AGENT_URL`):

| Django URL | Upstream | Notes |
|-----------|----------|-------|
| `GET /api/agent/social/wallet/` | `GET /api/wallet` | STX/sBTC/USDCx balances |
| `GET /api/agent/social/status/` | `GET /api/status` | |
| `GET /api/agent/social/balance/` | `GET /api/dap/balance` | DAP credits |
| `GET /api/agent/social/transactions/` | `GET /api/dap/transactions` | |

#### 4. Fixed base URL bug (commit `695cd0a`)

Initial commit had all new endpoints pointing to `AGENT_CONTROLLER_URL`. Fixed by:
- Adding `DAP_BASE = lambda: os.environ.get('DAP_SERVICE_URL', '').rstrip('/')`
- Changing `AGENT_BASE` to use `AGENT_API_URL` (not controller)
- Fixing 5 upstream URL paths that were wrong

#### 5. Added required env vars to `.env` (local only — not committed)

```
DAP_SERVICE_URL=https://deorganized-dap-service-production.up.railway.app
AGENT_API_URL=https://deorganized-agent-production.up.railway.app
AGENT_CONTROLLER_URL=https://deorganized-agentcontroller-production.up.railway.app
SOCIAL_AGENT_URL=https://deorganized-social-agent-production.up.railway.app
AGENT_API_KEY=<secret>
```

**TODO:** These must also be set on the Railway service for `deorganizedapi` before the PR is merged.

---

### Architecture decisions

- **Proxy pattern** (not direct service calls from frontend): All three Railway services are internal — auth, rate limiting, and URL management are centralized here.
- **`content_thumbnail` is binary, not JSON**: Passes `resp.content` through as `HttpResponse` with the upstream `content-type`. All other endpoints use `JsonResponse(resp.json(), status=resp.status_code)`.
- **Auth**: All new endpoints require `@login_required` (JWT Bearer via `rest_framework_simplejwt`). DAP balance/transactions endpoints also enforce that the requesting user's address matches the URL param (TBD — currently open).

---

### Known bugs / open items

| Issue | Detail |
|-------|--------|
| `social_agent_wallet` sBTC/USDCx returns 0 | FT map key identifier mismatch in `stx-client.js`. Hiro API key format needs to match actual token contract IDs. |
| Railway env vars not set | `deorganizedapi` Railway service needs DAP/Agent/Social URLs + API key before proxy endpoints work in production. |
| No PR open yet | `feature/content-engine` branch exists but PR is blocked on frontend connection. |

---

### What's next (before March 20 deadline)

**Phase 2 — ContentEngine.tsx** (deorganized frontend repo, new branch):
- New tab component following the `MerchTracker` pattern
- `useAuth()` + `useEffect` data loading
- Sections: DAP wallet (register, credits, top-up flow), Generation trigger (news-package / stacks-package), Output viewer (article + thread), Thumbnail display
- Add `content-engine` tab to `CreatorDashboard.tsx`
- API functions in `lib/api.ts`

**Phase 3 — Agent Controller panel** (AdminDashboard):
- Long Elio wallet, chat interface
- Social Agent vitals (status, balance)

**Phase 4 — News Production Studio** (AdminDashboard):
- Generation trigger with credit cost display
- Content review tabs (article, thread, thumbnail)

---

### Frontend patterns (for ContentEngine.tsx)

- API base: `import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'`
- Raw `fetch`, no Axios, Bearer token as param per function
- Components: no props, `useAuth()` for token, `useEffect` on `accessToken`, local `loading`/`error` state
- Animations: `AnimatePresence` + `motion.div` fade+scale
- Tailwind tokens: `bg-canvas`, `bg-surface`, `text-ink`, `text-gold`, `bg-gold-gradient`, `border-borderSubtle`
- Tab render: `{activeTab === 'x' && <motion.div key="x" ...><Component /></motion.div>}`
