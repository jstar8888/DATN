"""
guardrails.py

Guardrails module for HR Chatbot using LangGraph.

Responsibilities:
1. Input security (Chống prompt injection, jailbreak, prompt extraction, input validation)
2. Semantic & Business Scope Module (Tích hợp toàn bộ định nghĩa miền nghiệp vụ HR, 
   phạm vi SQL/RAG và quy tắc từ chối các câu hỏi ngoài mục đích hệ thống)
3. Tool permission (Enforce backend-defined tool allowlist)
4. Output security (Phát hiện rò rỉ credential, secret, thông tin nội bộ)
5. LangGraph integration (Input guardrail node, output guardrail node, conditional routing)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Optional


# ============================================================
# 1. CORE TYPES
# ============================================================

class GuardrailAction(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    OUT_OF_SCOPE = "out_of_scope"
    REVIEW = "review"


@dataclass(frozen=True)
class GuardrailResult:
    action: GuardrailAction
    stage: str
    reason: str = ""
    matched_rule: Optional[str] = None

    @property
    def allowed(self) -> bool:
        return self.action == GuardrailAction.ALLOW


# ============================================================
# 2. SEMANTIC & BUSINESS SCOPE MODULE (NGỮ CẢNH & PHẠM VI HỆ THỐNG)
# ============================================================

class HRSemanticScopeDefinition:
    """
    Module chứa toàn bộ ngữ cảnh hệ thống, định nghĩa ranh giới nghiệp vụ HR,
    phân loại phạm vi dữ liệu SQL, RAG và quy tắc chặn triệt để câu hỏi ngoài mục đích.
    """

    @classmethod
    def get_semantic_system_prompt_context(cls) -> str:
                return """
        ====================================================================
        NGUYÊN TẮC TỔNG QUÁT VỀ RANH GIỚI MIỀN NGHIỆP VỤ (HR DOMAIN BOUNDARY)
        ====================================================================

        Hệ thống này ĐỘC QUYỀN vận hành trong không gian nội bộ của một tổ chức/doanh nghiệp, tập trung 100% vào nghiệp vụ Quản trị Nhân sự (HR) và dữ liệu vận hành nội bộ.

        1. NGUYÊN TẮC LOẠI TRỪ TỔNG QUÁT (GLOBAL OUT-OF-SCOPE RULE):
        - Bất kỳ câu hỏi nào thuộc về thế giới bên ngoài, kiến thức xã hội chung, địa chính trị, chiến tranh, lịch sử thế giới, khoa học tự nhiên, giải trí đại chúng, hoặc các vấn đề không liên quan trực tiếp đến nhân viên, quản lý, quy chế và tài liệu nội bộ của công ty đều phải được xác định là **NGOÀI PHẠM VI (OUT-OF-SCOPE)**.
        - Ví dụ các chủ đề phải từ chối ngay lập tức: Chiến tranh, tình hình chính trị quốc tế (như chiến tranh Iran, xung đột toàn cầu), kiến thức phổ thông ngoài doanh nghiệp, mẹo vặt cuộc sống, v.v.

        2. PHẠM VI HỢP LỆ DUY NHẤT (IN-SCOPE):
        Mọi yêu cầu hợp lệ bắt buộc phải xoay quanh một trong hai nguồn:
        - **SQL Source (Dữ liệu cấu trúc nội bộ)**: Dữ liệu thực tế ghi nhận trong hệ thống công ty bao gồm: Nhân sự (employee), vị trí/leader (project_leaders), dự án (project), công việc/task, chấm công (attendance), làm thêm giờ/OT (overtime), đơn nghỉ phép (leave_request), vi phạm/hành vi (behavior), báo cáo công việc (daily_work_report).
        - **RAG Source (Tài liệu & Chính sách nội bộ)**: Các văn bản, quy chế, nội quy giờ làm việc, chính sách đãi ngộ, quy trình nội bộ do chính công ty ban hành.
        """


# ============================================================
# 3. GUARDRAIL CONFIGURATION
# ============================================================

@dataclass
class GuardrailConfig:
    # Input / Output length limits
    max_input_chars: int = 12000
    max_output_chars: int = 20000

    # Prompt injection / jailbreak / prompt extraction patterns
    injection_patterns: tuple[tuple[str, str], ...] = (
        (
            "ignore_previous_instructions_vi",
            r"(bỏ qua|phớt lờ|quên)\s+(toàn bộ\s+)?"
            r"(mọi\s+)?(chỉ dẫn|hướng dẫn|quy tắc)\s+"
            r"(trước đó|ở trên|trước)",
        ),
        (
            "ignore_previous_instructions_en",
            r"\b(ignore|disregard|forget)\s+(all\s+)?"
            r"(previous|prior|above)\s+(instructions|rules|messages)\b",
        ),
        (
            "jailbreak_role",
            r"\b(you are now|act as|pretend to be)\s+"
            r"(an unrestricted|a no.?rules|developer|system)\b",
        ),
        (
            "jailbreak_vi",
            r"(hãy|từ giờ hãy)\s+(đóng vai|giả vờ)\s+"
            r"(một\s+)?(ai không giới hạn|mô hình không giới hạn)",
        ),
        (
            "prompt_extraction",
            r"(tiết lộ|hiển thị|in ra|show|reveal|print)\s+"
            r".{0,80}(system prompt|prompt hệ thống|"
            r"chỉ dẫn nội bộ|developer message|hidden instructions)",
        ),
        (
            "prompt_extraction_direct",
            r"(system prompt|prompt hệ thống|developer message)"
            r".{0,80}(là gì|nội dung|đầy đủ|reveal|show|print|copy)",
        ),
        (
            "policy_bypass",
            r"(vượt qua|bỏ qua|tắt)\s+(cơ chế\s+)?"
            r"(bảo mật|phân quyền|kiểm soát truy cập|guardrail)",
        ),
    )

    # Obvious secret patterns in model output
    output_secret_patterns: tuple[tuple[str, str], ...] = (
        ("api_key", r"\b(sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,})\b"),
        ("bearer_token", r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}"),
        ("private_key", r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        ("password_assignment", r"(?i)\b(password|passwd|secret)\s*[:=]\s*\S+"),
    )

    # Tool allowlist
    allowed_tools: frozenset[str] = field(default_factory=frozenset)

    # User-facing messages
    blocked_input_message: str = (
        "Yêu cầu không thể được xử lý vì có dấu hiệu vi phạm quy tắc an toàn."
    )

    out_of_scope_message: str = (
        "Tôi chỉ hỗ trợ các nội dung thuộc hệ thống và nghiệp vụ nhân sự "
        "của công ty."
    )

    output_blocked_message: str = (
        "Tôi không thể cung cấp nội dung này vì có nguy cơ làm lộ "
        "thông tin nhạy cảm hoặc thông tin nội bộ."
    )


# ============================================================
# 4. HELPER FUNCTIONS
# ============================================================

def normalize_text(text: str) -> str:
    """Normalize whitespace and lowercase text."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def find_matching_rule(
    text: str,
    patterns: Iterable[tuple[str, str]],
) -> Optional[str]:
    for rule_name, pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return rule_name
    return None


# ============================================================
# 5. INPUT SECURITY CHECK
# ============================================================

def check_input_security(
    question: str,
    config: Optional[GuardrailConfig] = None,
) -> GuardrailResult:
    config = config or GuardrailConfig()

    if not isinstance(question, str) or not question.strip():
        return GuardrailResult(
            action=GuardrailAction.BLOCK,
            stage="input_security",
            reason="empty_input",
        )

    if len(question) > config.max_input_chars:
        return GuardrailResult(
            action=GuardrailAction.BLOCK,
            stage="input_security",
            reason="input_too_long",
        )

    normalized = normalize_text(question)
    matched_rule = find_matching_rule(normalized, config.injection_patterns)

    if matched_rule:
        return GuardrailResult(
            action=GuardrailAction.BLOCK,
            stage="input_security",
            reason="possible_prompt_injection",
            matched_rule=matched_rule,
        )

    return GuardrailResult(
        action=GuardrailAction.ALLOW,
        stage="input_security",
    )


# ============================================================
# 6. BUSINESS SCOPE CHECK (KIỂM TRA NGOÀI PHẠM VI DỰA TRÊN NGỮ CẢNH)
# ============================================================

def check_business_scope(
    question: str,
    conversation_context: str = "",
    config: Optional[GuardrailConfig] = None,
) -> GuardrailResult:
    config = config or GuardrailConfig()
    combined_text = normalize_text(f"{conversation_context} {question}")

    if not combined_text:
        return GuardrailResult(
            action=GuardrailAction.BLOCK,
            stage="business_scope",
            reason="empty_input",
        )

    # Các từ khóa hoặc pattern nhận diện chủ đề ngoài phạm vi (Weather, Sports, Finance, Cooking, Entertainment...)
    explicit_out_of_scope_patterns = (
        ("weather", r"\b(thời tiết|weather|dự báo thời tiết)\b"),
        ("sports", r"\b(tỷ số bóng đá|kết quả trận đấu|lịch thi đấu)\b"),
        ("finance", r"\b(chứng khoán|giá cổ phiếu|crypto|bitcoin)\b"),
        ("cooking", r"\b(công thức nấu ăn|nấu món ăn|recipe)\b"),
        ("entertainment", r"\b(review phim|phim mới|diễn viên nổi tiếng)\b"),
    )

    matched_rule = find_matching_rule(combined_text, explicit_out_of_scope_patterns)
    if matched_rule:
        return GuardrailResult(
            action=GuardrailAction.OUT_OF_SCOPE,
            stage="business_scope",
            reason="clearly_unrelated_to_hr",
            matched_rule=matched_rule,
        )

    # Cho phép đi tiếp (ALLOW hoặc REVIEW để Router quyết định sâu hơn dựa trên ngữ cảnh hệ thống)
    return GuardrailResult(
        action=GuardrailAction.ALLOW,
        stage="business_scope",
    )


# ============================================================
# 7. TOOL PERMISSION
# ============================================================

def check_tool_permission(
    tool_name: str,
    allowed_tools: Iterable[str],
) -> GuardrailResult:
    allowed = set(allowed_tools)
    if tool_name not in allowed:
        return GuardrailResult(
            action=GuardrailAction.BLOCK,
            stage="tool_permission",
            reason="tool_not_allowlisted",
            matched_rule=tool_name,
        )
    return GuardrailResult(
        action=GuardrailAction.ALLOW,
        stage="tool_permission",
    )


def guard_tool_call(
    tool_name: str,
    tool_callable: Callable[..., Any],
    *,
    allowed_tools: Iterable[str],
    **kwargs: Any,
) -> Any:
    result = check_tool_permission(
        tool_name=tool_name,
        allowed_tools=allowed_tools,
    )
    if not result.allowed:
        raise PermissionError(f"Tool '{tool_name}' is not allowed.")
    return tool_callable(**kwargs)


# ============================================================
# 8. OUTPUT SECURITY
# ============================================================

def check_output_security(
    answer: str,
    config: Optional[GuardrailConfig] = None,
) -> GuardrailResult:
    config = config or GuardrailConfig()

    if not isinstance(answer, str) or not answer.strip():
        return GuardrailResult(
            action=GuardrailAction.REVIEW,
            stage="output_security",
            reason="empty_output",
        )

    if len(answer) > config.max_output_chars:
        return GuardrailResult(
            action=GuardrailAction.BLOCK,
            stage="output_security",
            reason="output_too_long",
        )

    matched_rule = find_matching_rule(answer, config.output_secret_patterns)
    if matched_rule:
        return GuardrailResult(
            action=GuardrailAction.BLOCK,
            stage="output_security",
            reason="possible_secret_leak",
            matched_rule=matched_rule,
        )

    prompt_leak_signals = (
        "system prompt của tôi",
        "chỉ dẫn hệ thống của tôi",
        "my system prompt",
        "developer instructions say",
    )

    normalized = normalize_text(answer)
    if any(signal in normalized for signal in prompt_leak_signals):
        return GuardrailResult(
            action=GuardrailAction.REVIEW,
            stage="output_security",
            reason="possible_internal_instruction_disclosure",
        )

    return GuardrailResult(
        action=GuardrailAction.ALLOW,
        stage="output_security",
    )


# ============================================================
# 9. COMBINED EVALUATION & LANGGRAPH NODES
# ============================================================

def evaluate_question(
    question: str,
    conversation_context: str = "",
    config: Optional[GuardrailConfig] = None,
) -> GuardrailResult:
    security_result = check_input_security(question=question, config=config)
    if not security_result.allowed:
        return security_result

    return check_business_scope(
        question=question,
        conversation_context=conversation_context,
        config=config,
    )


def input_guardrail_node(
    state: Mapping[str, Any],
    config: Optional[GuardrailConfig] = None,
) -> dict[str, Any]:
    config = config or GuardrailConfig()

    result = evaluate_question(
        question=state.get("question", ""),
        conversation_context=state.get("conversation_context", ""),
        config=config,
    )

    update = {
        "guardrail_action": result.action.value,
        "guardrail_stage": result.stage,
        "guardrail_reason": result.reason,
        "guardrail_rule": result.matched_rule,
        # Đính kèm khối ngữ cảnh hệ thống hoàn chỉnh để truyền sang Router/LLM
        "semantic_system_context": HRSemanticScopeDefinition.get_semantic_system_prompt_context(),
    }

    if result.action == GuardrailAction.BLOCK:
        update["final_answer"] = config.blocked_input_message
    elif result.action == GuardrailAction.OUT_OF_SCOPE:
        update["final_answer"] = config.out_of_scope_message

    return update


def route_after_input_guardrail(state: Mapping[str, Any]) -> str:
    action = state.get("guardrail_action", GuardrailAction.BLOCK.value)

    if action in (GuardrailAction.BLOCK.value, GuardrailAction.OUT_OF_SCOPE.value):
        return "stop"
    if action == GuardrailAction.REVIEW.value:
        return "review"
    return "router"


def output_guardrail_node(
    state: Mapping[str, Any],
    config: Optional[GuardrailConfig] = None,
) -> dict[str, Any]:
    config = config or GuardrailConfig()
    result = check_output_security(answer=state.get("final_answer", ""), config=config)

    update = {
        "guardrail_output_action": result.action.value,
        "guardrail_output_reason": result.reason,
    }

    if result.action == GuardrailAction.BLOCK:
        update["final_answer"] = config.output_blocked_message

    return update


def route_after_output_guardrail(state: Mapping[str, Any]) -> str:
    action = state.get("guardrail_output_action", GuardrailAction.BLOCK.value)
    if action == GuardrailAction.BLOCK.value:
        return "stop"
    if action == GuardrailAction.REVIEW.value:
        return "review"
    return "end"