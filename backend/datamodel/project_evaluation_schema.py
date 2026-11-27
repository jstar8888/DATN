# project_evaluation_schema.py
from typing import List, Literal
from pydantic import BaseModel, Field, field_validator


class ProjectStatusStat(BaseModel):
    status: str = Field(..., description="Trạng thái dự án hoặc nhóm đánh giá")
    count: int = Field(..., ge=0, description="Số lượng dự án")


class ProjectWorkloadBarItem(BaseModel):
    project_id: str
    project_name: str
    avg_progress_percent: float = Field(..., ge=0, le=100)
    estimated_hours: float = Field(..., ge=0)
    actual_hours: float = Field(..., ge=0)
    task_count: int = Field(..., ge=0)
    overdue_or_at_risk_tasks: int = Field(..., ge=0)


class ProjectRiskWarning(BaseModel):
    project_id: str
    project_name: str
    risk_level: Literal["Cao", "Trung bình", "Thấp"]
    feasibility_status: Literal["Khả thi", "Cần theo dõi", "Rủi ro kém khả thi"]
    progress_percent: float = Field(..., ge=0, le=100)
    reasons: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)


class AllProjectsEvaluationResult(BaseModel):
    executive_summary: str = Field(..., description="Tóm tắt toàn cảnh danh mục dự án")
    pie_by_status: List[ProjectStatusStat] = Field(default_factory=list)
    pie_by_feasibility: List[ProjectStatusStat] = Field(default_factory=list)
    bar_projects_comparison: List[ProjectWorkloadBarItem] = Field(default_factory=list)
    risk_warnings: List[ProjectRiskWarning] = Field(default_factory=list)

    @field_validator("bar_projects_comparison")
    @classmethod
    def deduplicate_projects(cls, items: List[ProjectWorkloadBarItem]) -> List[ProjectWorkloadBarItem]:
        seen = set()
        cleaned = []
        for item in items:
            if item.project_id not in seen:
                seen.add(item.project_id)
                cleaned.append(item)
        return cleaned