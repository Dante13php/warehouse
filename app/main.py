from fastapi import FastAPI

from app.controllers.auth.router import router as auth_router

# PRODUCTION REQUIREMENT: This application must be deployed behind a TLS-terminating
# reverse proxy (e.g., nginx, Caddy, or a cloud load balancer). The app itself does
# not terminate TLS. All plaintext traffic must be blocked at the network boundary.
app = FastAPI(title="Warehouse")

app.include_router(auth_router)
