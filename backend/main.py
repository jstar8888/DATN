from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from database.supabase_general_service import use_request_access_token
from routers import (
    api_agent as agent,
    api_authentication as authentication,
    api_lead as lead,
    api_member as member,
    api_pm as pm,
    api_general as general,
)

app = FastAPI(
    title="HR Management & AI Agent API",
    description="Backend FastAPI cho Đồ án tốt nghiệp: AI-Agent kết hợp RAG và Text-to-SQL",
    version="1.0.0",
)

app.include_router(authentication.router)
app.include_router(member.router)
app.include_router(lead.router)
app.include_router(pm.router)   
app.include_router(agent.router)
app.include_router(general.router)
app.include_router(general.behavior_router)


@app.middleware("http")
async def forward_supabase_access_token(
    request: Request, call_next
) -> Response:
    scheme, separator, access_token = request.headers.get(
        "authorization", ""
    ).partition(" ")
    if not separator or scheme.lower() != "bearer" or not access_token.strip():
        return await call_next(request)

    with use_request_access_token(access_token.strip()):
        return await call_next(request)


# Cấu hình CORS để Streamlit (frontend) có thể gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": "Chào mừng đến với API hệ thống Quản lý Nhân sự AI-Agent!"
    }


# Import và include các router nghiệp vụ (bạn có thể triển khai chi tiết các file router tương ứng)
# from backend.routers import auth_role, tasks, hr_records, ai_agent
# app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
# app.include_router(hr_records.router, prefix="/api/hr", tags=["HR Records"])
# app.include_router(ai_agent.router, prefix="/api/ai", tags=["AI Agent & RAG & SQL"])

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)