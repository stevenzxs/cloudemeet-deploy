# jitsi-mgr Integration Plan

## Status: Implementation in Progress

### 2026-11-26 r29 missing-material repair

- Root cause: the mgr build artifact was downloaded but the seven-image assembler never consumed it.
- Repair: same-run/attempt/source/config/version assignment and per-file hashes; package JAR/UI, public config and initialization tool; eighth Compose service reuses the same-batch API Java 17 image with explicit entrypoint, persistent data and gateway UI mount. No eighth image or separate installer.
- Shared first-install core generates target-only PKCS#8 keys and database secret, refuses overwrite, accepts only the expected initialized key directory, and checks payload before host changes. Explicit Spring datasource overrides avoid the prod profile's localhost PostgreSQL default; configured H2/PostgreSQL selects matching driver/dialect.
- Online material and joint-release gates reject missing or modified mgr payload; new revision >=15 cannot omit mgr evidence. Historical packages are not rewritten.
- Verification: 105 focused auxiliary tests passed (package, delivery assets/contracts, installer/start/deploy, network audit and online update). Full suite: 210 tests, 9 failure reports in existing skill-text assertions and WSL mounted-filesystem permissions; baseline archive also reproduces these categories (206 tests, 10 failure reports, 3 errors, 1 skip). No all-green suite claim.
- Not executed: product builds, revision allocation, Actions, publication, SSH, installation or media acceptance. r29 remains blocked and immutable; a future new batch is needed.
- Remaining integration/acceptance: actual UI BrowserRouter subpath navigation, JWKS/Prosody token flow, initial administrator behavior, real Java/H2 startup, target API/ACME and media verification. Image-only updater intentionally rejects external JAR/UI/config changes rather than silently migrating them.

### Completed ✅

1. **Configuration Files**
   - ✅ Updated `deploy/config/Caddyfile` - Added `/api/mgr/*` routing
   - ✅ Updated `deploy/config/docker-compose.yml` - Added jitsi-mgr service
   - ✅ Created `deploy/config/jitsi-mgr.env` - Service configuration

2. **Build Scripts**
   - ✅ Created `deploy/build-tools/build-jitsi-mgr-backend.py` - Backend JAR build
   - ✅ Created `deploy/build-tools/build-jitsi-mgr-frontend.py` - Frontend React build
   - ✅ Created `deploy/build-tools/init-jitsi-mgr.py` - Initialization script

3. **Routing Configuration**
   - ✅ Caddy: `/api/mgr/ui/*` → Frontend static files (gateway volume mount)
   - ✅ Caddy: `/api/mgr/*` → Backend reverse proxy (jitsi-mgr:8080)
   - ✅ Gateway volume mount for frontend artifacts

### Remaining Tasks 🔄

1. **Update AGENTS.md** (规范文档)
   - [ ] Add jitsi-mgr as 8th service to service list
   - [ ] Update "七服务" references to "八服务"
   - [ ] Add jitsi-mgr to build-tools/sources.json
   - [ ] Add jitsi-mgr to inputs.sha256
   - [ ] Update section 3.1 file responsibility list
   - [ ] Add jitsi-mgr to section 6 packaging flow

2. **Build Integration**
   - [ ] Add jitsi-mgr backend build to package.sh
   - [ ] Add jitsi-mgr frontend build to package.sh
   - [ ] Update network-audit.py for jitsi-mgr endpoints
   - [ ] Add jitsi-mgr to Dockerfile or use existing eclipse-temurin base

3. **Deployment Scripts**
   - [ ] Update deploy.py to initialize jitsi-mgr data/keys
   - [ ] Update start.py to verify jitsi-mgr artifacts
   - [ ] Update online_update.py for jitsi-mgr updates
   - [ ] Add health check for jitsi-mgr:8080

4. **Prosody Integration**
   - [ ] Configure Prosody to use jitsi-mgr JWKS endpoint
   - [ ] Update jitsi.env with JWKS_URL=/api/mgr/v1/auth/jwks
   - [ ] Test JWT validation flow

5. **Testing & Validation**
   - [ ] Build backend and frontend locally
   - [ ] Test initialization script
   - [ ] Deploy to test environment
   - [ ] Verify routing: /api/mgr/ui/ and /api/mgr/v1/*
   - [ ] Test admin login
   - [ ] Test user registration/approval flow
   - [ ] Test JWT generation and Prosody validation

6. **Documentation**
   - [ ] Update deploy/README.md
   - [ ] Add jitsi-mgr section to skills/cloudmeet-deploy/SKILL.md
   - [ ] Create jitsi-mgr INSTALL guide
   - [ ] Update knowledge base audit log

### Architecture Changes

**Before (7 services):**
- gateway, app-web, api, web, prosody, jicofo, jvb

**After (8 services):**
- gateway, app-web, api, **jitsi-mgr**, web, prosody, jicofo, jvb

**New Endpoints:**
- `https://{host}/api/mgr/ui/` - Frontend (React SPA)
- `https://{host}/api/mgr/v1/*` - Backend API
- `https://{host}/api/mgr/v1/auth/jwks` - JWT Public Keys (for Prosody)

**Data Storage:**
- `deploy/data/jitsi-mgr/` - H2 database (default) or PostgreSQL connection
- `deploy/data/jitsi-mgr/keys/` - JWT RSA key pair

**Artifacts:**
- `deploy/artifacts/jitsi-mgr.jar` - Spring Boot backend
- `deploy/artifacts/jitsi-mgr-ui/` - React frontend build

### Compliance Notes

- Following CloudMeet standard: external patches, volume mounts, no secrets in images
- JWT keys generated locally, not in Docker image
- Database password in .env, not in jitsi-mgr.env
- Frontend served by gateway (Caddy), not separate container
- All changes versioned in deploy/ config repo
- Requires AGENTS.md update (正常流程变更已确认)

### Next Immediate Actions

1. Test build scripts locally
2. Update AGENTS.md with jitsi-mgr service
3. Integrate into package.sh build flow
4. Test deployment on existing instance
