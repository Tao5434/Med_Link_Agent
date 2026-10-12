"""API 路由注册表（需求 4.2 HTTP API 清单）。"""
from routers.api.appointment import appointment_router
from routers.api.chat import chat_router
from routers.api.department import department_router
from routers.api.record import record_router
from routers.api.report import report_router
from routers.api.session import session_router
from routers.api.settings import settings_router
from routers.api.user import user_router

api_routers = [
    chat_router,        # /api/health /api/chat /api/triage /api/consultation /api/medication
    session_router,     # /api/sessions
    record_router,      # /api/records
    report_router,      # /api/reports
    department_router,  # /api/departments
    appointment_router, # /api/appointments
    settings_router,    # /api/settings /api/metrics
    user_router,        # /api/user
]
