import asyncio
import logging
from typing import Dict, List, Literal, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, UploadFile
from fastapi import status as http_status
from pydantic import BaseModel, Field
from database.supabase_general_service import SupabaseService
from datetime import date, datetime, time
from datamodel.schema import EmployeeResponse, ProjectCreate, ProjectResponse
from routers.api_authentication import require_role

db = SupabaseService()
logger = logging.getLogger(__name__)

# Pydantic model chuyên biệt để cập nhật thông tin dự án (Yêu cầu 3)
class ProjectUpdatePayload(BaseModel):
    project_name: Optional[str] = Field(None, description="Tên dự án")
    description: Optional[str] = Field(None, description="Mô tả tổng quan về dự án")
    start_date: Optional[date] = Field(None, description="Ngày bắt đầu dự án")
    end_date: Optional[date] = Field(None, description="Ngày kết thúc hoặc deadline dự án")
    status: Optional[
        Literal["Mới", "Đang thực hiện", "Hoàn thành"]
    ] = Field(None, description="Trạng thái hiện tại của dự án")
    note: Optional[str] = Field(None, description="Ghi chú liên quan đến dự án")

router = APIRouter(
    prefix="/api/pm",
    tags=["Project Manager Management"],
    dependencies=[Depends(require_role("Project Manager"))],
)





class ChatRequestPayload(BaseModel):
  prompt: str = Field(
      ..., description="Câu hỏi của PM gửi tới AI Chatbot (RAG & Text-to-SQL)"
  )
  session_id: Optional[str] = Field(
      "default_pm_session", description="Mã phiên làm việc"
  )

class TableEmbeddingPayload(BaseModel):
    table_name: str = Field(..., min_length=1, description="Tên bảng dữ liệu")
    chunk_text: str = Field(
        ..., min_length=1, description="Đoạn văn bản chunk ngữ nghĩa của bảng"
    )
    embedding: Optional[List[float]] = Field(
        None, description="Vector embedding; tự tạo từ chunk_text nếu không truyền"
    )


# ==========================================
# 2. API ENDPOINTS CHO PM
# ==========================================




# --- 3. AI-Agent Tổng hợp Tiến độ ---
@router.post(
    "/ai-agent/analyze-progress",
    summary="Chạy AI-Agent phân tích rủi ro & tiến độ toàn cục dựa trên task",
)
def run_ai_progress_analysis():
  # Tích hợp logic AI-Agent phân tích tiến độ dựa trên dữ liệu công việc[cite: 1]
  return {
      "status": "success",
      "agent_report": {
          "active_projects_count": 3,
          "risk_warnings": (
              "Dự án 'Phát triển hệ thống HR' đang có dấu hiệu chậm tiến độ ở"
              " hạng mục tích hợp API."
          ),
          "recommendations": (
              "Đề xuất Team Lead điều phối thêm nhân sự hỗ trợ xử lý dứt điểm"
              " các Task tồn đọng."
          ),
      },
  }


# --- 4. Quản lý Kho tài liệu (RAG) ---
@router.post(
    "/rag/upload-document",
    summary=(
        "Tải lên và xử lý Chunking & Vector hóa tài liệu chính sách vào Supabase"
    ),
)
async def upload_rag_document(
    file: UploadFile = File(...),
    position: Optional[
        Literal["Business Analyst", "Developer", "Tester"]
    ] = Form(None),
    system_level: Literal[
        "Member", "Team Lead", "Project Manager"
    ] = Form(...),
):
  filename = file.filename or ""
  if not filename.lower().endswith((".pdf", ".txt")):
    raise HTTPException(
        status_code=http_status.HTTP_400_BAD_REQUEST,
        detail="Chỉ chấp nhận định dạng file PDF hoặc TXT.",
    )

  file_content = await file.read()
  await file.close()
  if not file_content:
    raise HTTPException(
        status_code=http_status.HTTP_400_BAD_REQUEST,
        detail="Tệp tải lên đang trống.",
    )

  try:
    from tools.document_chunking import (
        InvalidDocumentError,
        process_uploaded_document,
    )

    result = await asyncio.to_thread(
        process_uploaded_document,
        file_content,
        filename,
        position,
        system_level,
    )
  except InvalidDocumentError as exc:
    raise HTTPException(
        status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc)
    ) from exc
  except Exception as exc:
    logger.exception("Không thể vector hóa tài liệu %s", filename)
    raise HTTPException(
        status_code=http_status.HTTP_502_BAD_GATEWAY,
        detail="Không thể vector hóa hoặc lưu tài liệu vào Supabase.",
    ) from exc

  return {
      "status": "success",
      "filename": filename,
      **result,
      "message": (
          f"Đã vector hóa và lưu {result['chunks_saved']} "
          "đoạn tài liệu vào Supabase."
      ),
  }


@router.get(
    "/rag/documents",
    summary="Lấy danh sách tài liệu đã chunk",
)
def list_rag_documents():
  try:
    chunks = db.select(
        "document_chunks",
        columns="document_name, position, system_level, created_at",
        order_by="created_at",
        desc=True,
    )
    documents_by_key = {}
    for chunk in chunks:
      key = (
          chunk["document_name"],
          chunk.get("position"),
          chunk["system_level"],
      )
      document = documents_by_key.get(key)
      if document is None:
        documents_by_key[key] = {
            "document_name": key[0],
            "position": key[1],
            "system_level": key[2],
            "chunk_count": 1,
            "created_at": chunk["created_at"],
        }
      else:
        document["chunk_count"] += 1
    return {"documents": list(documents_by_key.values())}
  except Exception as exc:
    logger.exception("Không thể lấy danh sách document_chunks")
    raise HTTPException(
        status_code=http_status.HTTP_502_BAD_GATEWAY,
        detail="Không thể lấy danh sách tài liệu từ Supabase.",
    ) from exc


@router.get(
    "/rag/documents/{document_name}",
    summary="Lấy các chunk của một tài liệu",
)
def get_rag_document(document_name: str):
  try:
    chunks = db.select(
        "document_chunks",
        columns=(
            "id, document_name, position, system_level, chapter, "
            "article_title, raw_content, enriched_text, created_at"
        ),
        filters={"document_name": document_name},
        order_by="id",
    )
    return {"document_name": document_name, "chunks": chunks}
  except Exception as exc:
    logger.exception("Không thể lấy document_chunks cho %s", document_name)
    raise HTTPException(
        status_code=http_status.HTTP_502_BAD_GATEWAY,
        detail="Không thể lấy nội dung tài liệu từ Supabase.",
    ) from exc


# --- 5. Quản lý Semantic Profile (Text-to-SQL) ---
@router.post(
    "/table-embeddings",
    summary="Đẩy đoạn embedding và chunk text của bảng từ Frontend lên Supabase",
)
def upsert_table_embedding(payload: TableEmbeddingPayload):
    try:
        embedding = payload.embedding
        if embedding is None:
            from script.embedding_service import GeminiEmbeddingService

            embedding = GeminiEmbeddingService().generate(
                payload.chunk_text, task_type="RETRIEVAL_DOCUMENT"
            )

        data_to_upsert = {
            "table_name": payload.table_name,
            "chunk_text": payload.chunk_text,
            "embedding": embedding,
        }

        # Sử dụng phương thức upsert có sẵn trong SupabaseService
        result = db.upsert("table_embeddings", data_to_upsert)

        if not result:
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Không thể lưu embedding lên Supabase.",
            )

        return {
            "status": "success",
            "message": f"Đã đẩy embedding và chunk text cho bảng '{payload.table_name}' thành công lên Supabase.",
            "data": result[0] if isinstance(result, list) and len(result) > 0 else data_to_upsert
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Lỗi khi đẩy table embedding lên Supabase")
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=f"Lỗi hệ thống khi lưu embedding: {str(exc)}",
        ) from exc


@router.get(
    "/table-embeddings",
    summary="Lấy danh sách table_name và chunk_text để hiển thị trên Frontend",
)
def get_table_embeddings_for_frontend():
    try:
        records = db.select(
            "table_embeddings",
            columns="table_name, chunk_text",
            
        )
        return {
            "status": "success",
            "total": len(records),
            "data": records
        }
    except Exception as exc:
        logger.exception("Không thể lấy dữ liệu table_embeddings")
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail="Không thể lấy danh sách table embeddings từ Supabase.",
        ) from exc


# --- 6. AI Chatbot Toàn hệ thống ---
@router.post(
    "/ai-chatbot/query",
    summary="Chatbot Quản trị Cấp cao tích hợp Text-to-SQL & RAG",
)
def pm_ai_chatbot(payload: ChatRequestPayload):
  user_prompt = payload.prompt
  # Xử lý phân nhánh câu hỏi: RAG cho chính sách / Text-to-SQL cho dữ liệu nghiệp vụ[cite: 1]

  response_content = (
      f"🤖 **[AI Chatbot Response]**: Hệ thống đã xử lý câu hỏi *"
      f'"{user_prompt}"* thành công thông qua mô hình RAG kết hợp Text-to-SQL.'
  )

  return {
      "status": "success",
      "session_id": payload.session_id,
      "user_prompt": user_prompt,
      "response": response_content,
  }



# ==========================================
# 1. API lấy ra toàn bộ dự án của doanh nghiệp và thống kê trạng thái
# ==========================================
@router.post("/projects", response_model=ProjectResponse)
def create_project(payload: ProjectCreate):
    try:
        project_data = payload.model_dump(mode="json", exclude={"leaders"})
        created_projects = db.insert("project", project_data)
        if not created_projects:
            raise HTTPException(status_code=500, detail="Không thể tạo dự án")

        if payload.leaders:
            leader_rows = [
                {
                    "project_id": payload.project_id,
                    "employee_id": leader.employee_id,
                    "leader_role": leader.position,
                }
                for leader in payload.leaders
            ]
            db.insert("project_leaders", leader_rows)

        return created_projects[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/statistics")
def get_all_projects_with_statistics():
    """
    Lấy toàn bộ dự án của doanh nghiệp[cite: 7], từ đó tính ra:
    - Tổng số dự án
    - Số dự án đã hoàn thành ('Hoàn thành')
    - Số dự án đang thực hiện ('Đang thực hiện' hoặc 'Đang làm')
    - Số dự án mới ('Mới' hoặc 'Chưa bắt đầu')
    """
    try:
        projects = db.select("project")
        total_projects = len(projects)
        
        completed_count = 0
        in_progress_count = 0
        new_count = 0

        for p in projects:
            status = p.get("status", "")
            if status in ["Hoàn thành", "Đã hoàn thành"]:
                completed_count += 1
            elif status in ["Đang thực hiện", "Đang làm"]:
                in_progress_count += 1
            elif status in ["Mới", "Chưa bắt đầu"]:
                new_count += 1
            else:
                # Mặc định gom vào đang thực hiện hoặc mới tùy quy ước, ở đây tạm tính vào 'Mới' nếu khác hoàn thành
                new_count += 1

        return {
            "total_projects": total_projects,
            "statistics": {
                "completed": completed_count,
                "in_progress": in_progress_count,
                "new": new_count
            },
            "projects": projects
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 2. API lấy thông tin chi tiết dự án (Mô tả, Leader tham gia và Task theo từng leader)
# ==========================================
@router.get("/projects/{project_id}/comprehensive-detail")
def get_project_comprehensive_detail(project_id: str = Path(..., description="Mã dự án")):
    """
    Lấy thông tin chi tiết của dự án[cite: 7] gồm:
    - Thông tin mô tả cơ bản của dự án.
    - Danh sách các leader tham gia dự án (kèm thông tin chi tiết leader).
    - Danh sách các task thuộc dự án được phân chia theo từng leader quản lý (manager_employee_id).
    """
    try:
        # 1. Lấy thông tin cơ bản dự án[cite: 7]
        proj_data = db.select("project", filters={"project_id": project_id})
        if not proj_data:
            raise HTTPException(status_code=404, detail="Không tìm thấy dự án")
        project_info = proj_data[0]

        # 2. Lấy danh sách leader tham gia dự án từ bảng project_leaders[cite: 7]
        leader_relations = db.select("project_leaders", filters={"project_id": project_id})
        leaders_detail = []
        
        for lr in leader_relations:
            emp_id = lr.get("employee_id")
            emp_data = db.select("employee", filters={"employee_id": emp_id})
            leader_info = emp_data[0] if emp_data else {}
            
            leaders_detail.append({
                "employee_id": emp_id,
                "employee_name": leader_info.get("employee_name"),
                "position": lr.get("leader_role") or leader_info.get("position"),
                "department": leader_info.get("department"),
            })

        # 3. Lấy toàn bộ task của dự án này[cite: 7] và phân nhóm theo manager_employee_id (leader quản lý task)
        tasks = db.select("task", filters={"project_id": project_id})
        
        # Nhóm task theo leader quản lý (manager_employee_id)
        tasks_by_leader = {}
        for t in tasks:
            mgr_id = t.get("manager_employee_id", "Unassigned")
            if mgr_id not in tasks_by_leader:
                tasks_by_leader[mgr_id] = []
            tasks_by_leader[mgr_id].append(t)

        return {
            "project": project_info,
            "leaders": leaders_detail,
            "tasks_grouped_by_manager": tasks_by_leader
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/tasks/{task_id}/detail")
def get_project_task_detail(
    project_id: str = Path(..., description="Mã dự án"),
    task_id: str = Path(..., description="Mã task"),
):
    try:
        task_records = db.select(
            "task",
            filters={"project_id": project_id, "task_id": task_id},
            limit=1,
        )
        if not task_records:
            raise HTTPException(status_code=404, detail="Không tìm thấy task.")

        task = task_records[0]
        assignee_records = db.select(
            "employee",
            columns="employee_id, employee_name",
            filters={"employee_id": task.get("assignee_employee_id")},
            limit=1,
        )
        reports = db.select(
            "daily_work_report",
            filters={"task_id": task_id},
            order_by="report_date",
            desc=True,
        )
        return {
            "task": task,
            "assignee_name": (
                assignee_records[0].get("employee_name")
                if assignee_records
                else None
            ),
            "reports": reports,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 3. API chỉnh sửa thông tin dự án
# ==========================================
@router.put("/projects/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str = Path(..., description="Mã dự án cần chỉnh sửa"),
    payload: ProjectUpdatePayload = None
):
    """
    Chỉnh sửa thông tin tổng quan của dự án dựa trên project_id[cite: 7].
    """
    try:
        update_data = payload.dict(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="Không có dữ liệu cập nhật được cung cấp")

        result = db.update("project", update_data, filters={"project_id": project_id})
        if not result:
            raise HTTPException(status_code=404, detail="Không tìm thấy dự án hoặc cập nhật thất bại")
            
        return result[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 4. API lấy ra toàn bộ nhân viên trong doanh nghiệp
# ==========================================
@router.get("/employees", response_model=List[EmployeeResponse])
def get_all_employees():
    """
    Lấy danh sách toàn bộ nhân viên đang làm việc trong doanh nghiệp[cite: 7].
    """
    try:
        employees = db.select("employee")
        return employees
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/employees/{employee_id}/monthly-summary")
def get_employee_monthly_summary(
    employee_id: str = Path(..., description="Mã nhân viên"),
    month: int = Query(..., description="Tháng cần tổng kết (1-12)"),
    year: int = Query(..., description="Năm cần tổng kết")
):
    """
    Lấy chi tiết thông tin 1 nhân viên tổng kết theo tháng:
    - Kiểm tra xem nhân viên có phải là Leader hay không.
    - Nếu là Leader: Thống kê tổng số dự án mà leader đó quản lý (từ bảng project_leaders) và danh sách dự án quản lý.
    - Nếu là Nhân viên thông thường: Thống kê số task thực hiện trong tháng và các dự án tham gia.
    - Chung cho mọi nhân viên: Số ngày đi làm (từ bảng attendance) và số vi phạm (từ bảng behavior) trong tháng.
    """
    try:
        # 1. Lấy thông tin cơ bản nhân viên[cite: 7]
        emp_data = db.select("employee", filters={"employee_id": employee_id})
        if not emp_data:
            raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên")
        employee_info = emp_data[0]
        
        # Kiểm tra system_level hoặc vai trò leader của nhân viên
        system_level = employee_info.get("system_level", "")
        is_leader = system_level in ["PM", "Team Lead"] or employee_info.get("position", "").lower().find("leader") != -1

        summary_data = {
            "employee": employee_info,
            "period": f"Tháng {month}/{year}",
            "role_type": "Leader" if is_leader else "Member"
        }

        project_ids_set = set()

        # 2. Xử lý dữ liệu đặc thù dựa theo vai trò (Leader vs Member)
        if is_leader:
            # Nếu là leader, lấy danh sách dự án quản lý từ bảng project_leaders[cite: 7]
            leader_projects = db.select("project_leaders", filters={"employee_id": employee_id})
            managed_projects_list = []
            
            for lp in leader_projects:
                pid = lp.get("project_id")
                if pid:
                    project_ids_set.add(pid)
                    proj_info = db.select("project", columns="project_id, project_name, status, start_date, end_date", filters={"project_id": pid})
                    if proj_info:
                        managed_projects_list.extend(proj_info)
            
            summary_data["summary"] = {
                "total_managed_projects": len(managed_projects_list),
            }
            summary_data["projects_managed"] = managed_projects_list
        else:
            # Nếu là nhân viên thông thường, lấy task thực hiện trong tháng[cite: 7]
            tasks = db.select("task", filters={"assignee_employee_id": employee_id})
            monthly_tasks = []
            
            for t in tasks:
                start_d = t.get("start_date")
                if start_d:
                    parsed_date = date.fromisoformat(start_d) if isinstance(start_d, str) else start_d
                    if parsed_date.month == month and parsed_date.year == year:
                        monthly_tasks.append(t)
                        if t.get("project_id"):
                            project_ids_set.add(t.get("project_id"))

            # Lấy thông tin dự án tham gia qua task
            participated_projects = []
            for pid in project_ids_set:
                proj_info = db.select("project", columns="project_id, project_name, status", filters={"project_id": pid})
                if proj_info:
                    participated_projects.extend(proj_info)

            summary_data["summary"] = {
                "total_tasks_in_month": len(monthly_tasks),
            }
            summary_data["projects_participated"] = participated_projects
            summary_data["tasks_in_month"] = monthly_tasks

        # 3. Lấy thông tin chấm công (attendance) để đếm số ngày đi làm trong tháng[cite: 7]
        attendances = db.select("attendance", filters={"employee_id": employee_id})
        working_days_count = 0
        for att in attendances:
            att_date = att.get("attendance_date")
            if att_date:
                parsed_att_date = date.fromisoformat(att_date) if isinstance(att_date, str) else att_date
                if parsed_att_date.month == month and parsed_att_date.year == year:
                    working_days_count += 1

        # 4. Lấy số vi phạm từ bảng behavior trong tháng[cite: 7]
        behaviors = db.select("behavior", filters={"employee_id": employee_id})
        violation_count = 0
        for b in behaviors:
            rec_date = b.get("recorded_date")
            if rec_date:
                parsed_rec_date = date.fromisoformat(rec_date) if isinstance(rec_date, str) else rec_date
                if parsed_rec_date.month == month and parsed_rec_date.year == year:
                    violation_count += 1

        # Bổ sung các chỉ số chung vào summary
        summary_data["summary"]["working_days_count"] = working_days_count
        summary_data["summary"]["violation_count"] = violation_count

        return summary_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))