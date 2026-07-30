from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.admin.router import router as admin_router
from app.analytics.router import router as analytics_router
from app.attendance.router import router as attendance_router
from app.auth.router import router as auth_router
from app.errors import AppError, app_error_handler, http_error_handler
from app.fraud.router import router as fraud_router
from app.hr.router import router as hr_router
from app.ml.router import router as ml_router
from app.payroll.router import router as payroll_router
from app.remote_checkin.router import router as remote_checkin_router
from app.wallet.router import router as wallet_router
from app.worker.router import router as worker_router

app = FastAPI(title="GhostGuard API", version="0.1.0")

# Convert raw Python exceptions to clean 500 responses
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"UNHANDLED EXCEPTION on {request.method} {request.url.path}")
    print(f"Exception type: {type(exc).__name__}")
    print(f"Exception detail: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Check server logs."
            }
        },
    )

# Convert Pydantic 422 errors to readable format
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(f"VALIDATION ERROR on {request.method} {request.url.path}")
    print(f"Validation details: {exc.errors()}")
    errors = exc.errors()
    first = errors[0] if errors else {}
    field = first.get("loc", ["unknown"])[-1]
    msg = first.get("msg", "Invalid input")
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": f"Invalid value for '{field}': {msg}",
                "details": errors,
            }
        },
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://ghostguard.vercel.app",
    ],
    allow_origin_regex=r"https://ghostguard-.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(HTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(worker_router)
app.include_router(attendance_router)
app.include_router(fraud_router)
app.include_router(ml_router)
app.include_router(hr_router)
app.include_router(payroll_router)
app.include_router(remote_checkin_router)
app.include_router(wallet_router)
app.include_router(analytics_router)


@app.get("/health")
async def health_check():
    return {"success": True, "data": {"status": "ok"}, "message": "GhostGuard API is healthy."}
