import os
from supabase import Client, create_client
from dotenv import load_dotenv

load_dotenv()

# 1. Cấu hình thông tin kết nối Supabase (Yêu cầu dùng SERVICE_ROLE_KEY để có quyền Admin)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# 2. Danh sách nhân sự gốc
EMPLOYEES_DATA = [
    {
        "id": "EMP001",
        "name": "Nguyễn Thành Nam",
        "position": "Developer",
        "department": "Phòng Kỹ thuật",
        "system_level": "Team Lead",
    },
    {
        "id": "EMP002",
        "name": "Trần Minh Quân",
        "position": "CEO",
        "department": "Phòng Giám đốc",
        "system_level": "Project Manager",
    },
    {
        "id": "EMP004",
        "name": "Phạm Thị Mai Anh",
        "position": "Business Analyst",
        "department": "Phòng Phân tích Nghiệp vụ",
        "system_level": "Team Lead",
    },
    {
        "id": "EMP005",
        "name": "Vũ Thu Hằng",
        "position": "Tester",
        "department": "Phòng Đảm bảo Chất lượng",
        "system_level": "Team Lead",
    },
    {
        "id": "EMP006",
        "name": "Hoàng Hải Nam",
        "position": "Developer",
        "department": "Phòng Kỹ thuật",
        "system_level": "Member",
    },
    {
        "id": "EMP007",
        "name": "Đỗ Quang Vinh",
        "position": "Developer",
        "department": "Phòng Kỹ thuật",
        "system_level": "Member",
    },
    {
        "id": "EMP008",
        "name": "Bùi Đức Mạnh",
        "position": "Developer",
        "department": "Phòng Kỹ thuật",
        "system_level": "Member",
    },
    {
        "id": "EMP009",
        "name": "Ngô Văn Tuấn",
        "position": "Developer",
        "department": "Phòng Kỹ thuật",
        "system_level": "Member",
    },
    {
        "id": "EMP010",
        "name": "Dương Quốc Bảo",
        "position": "Developer",
        "department": "Phòng Kỹ thuật",
        "system_level": "Member",
    },
    {
        "id": "EMP011",
        "name": "Lý Gia Hân",
        "position": "Developer",
        "department": "Phòng Kỹ thuật",
        "system_level": "Member",
    },
    {
        "id": "EMP012",
        "name": "Vương Tấn Phát",
        "position": "Developer",
        "department": "Phòng Kỹ thuật",
        "system_level": "Member",
    },
    {
        "id": "EMP013",
        "name": "Trịnh Công Sơn",
        "position": "Developer",
        "department": "Phòng Kỹ thuật",
        "system_level": "Member",
    },
    {
        "id": "EMP014",
        "name": "Nguyễn Quỳnh Nga",
        "position": "Business Analyst",
        "department": "Phòng Phân tích Nghiệp vụ",
        "system_level": "Member",
    },
    {
        "id": "EMP015",
        "name": "Trần Ngọc Linh",
        "position": "Business Analyst",
        "department": "Phòng Phân tích Nghiệp vụ",
        "system_level": "Member",
    },
    {
        "id": "EMP016",
        "name": "Phạm Minh Thư",
        "position": "Business Analyst",
        "department": "Phòng Phân tích Nghiệp vụ",
        "system_level": "Member",
    },
    {
        "id": "EMP017",
        "name": "Lê Khánh Chi",
        "position": "Business Analyst",
        "department": "Phòng Phân tích Nghiệp vụ",
        "system_level": "Member",
    },
    {
        "id": "EMP018",
        "name": "Vũ Đình Trọng",
        "position": "Business Analyst",
        "department": "Phòng Phân tích Nghiệp vụ",
        "system_level": "Member",
    },
    {
        "id": "EMP019",
        "name": "Hoàng Phương Thảo",
        "position": "Tester",
        "department": "Phòng Đảm bảo Chất lượng",
        "system_level": "Member",
    },
    {
        "id": "EMP020",
        "name": "Đinh Công Hùng",
        "position": "Tester",
        "department": "Phòng Đảm bảo Chất lượng",
        "system_level": "Member",
    },
    {
        "id": "EMP021",
        "name": "Bùi Thị Diệu Linh",
        "position": "Tester",
        "department": "Phòng Đảm bảo Chất lượng",
        "system_level": "Member",
    },
]


def convert_name_to_email(full_name: str) -> str:
  """Hàm chuyển đổi tên tiếng Việt có dấu thành định dạng email không dấu.

  Ví dụ: "Nguyễn Thành Nam" -> nguyen.thanh.nam@company.com
  """
  import unicodedata

  # Bỏ dấu tiếng Việt
  nfkd_form = unicodedata.normalize("NFKD", full_name)
  without_accent = "".join(
      [c for c in nfkd_form if not unicodedata.combining(c)]
  )
  # Thay thế đ/Đ và chuyển về chữ thường
  clean_name = without_accent.replace("đ", "d").replace("Đ", "D").lower()
  # Ghép các từ bằng dấu chấm
  parts = clean_name.split()
  return f"{'.'.join(parts)}@company.com"


def seed_users_and_link_employees():
  print(
      "🚀 Bắt đầu tạo tài khoản Supabase Auth và link sang bảng employees..."
  )

  for emp in EMPLOYEES_DATA:
    # Biến tên thành email dạng: nguyen.thanh.nam@company.com
    email = convert_name_to_email(emp["name"])
    password = "12345678"  # Mật khẩu mặc định từ 1 đến 8

    try:
      # 1. Tạo user trên Supabase Auth
      response = supabase.auth.admin.create_user({
          "email": email,
          "password": password,
          "email_confirm": True,  # Xác thực email tự động để test ngay
          "user_metadata": {
              "id": emp["id"],
              "name": emp["name"],
          },
      })

      # Lấy ra auth_uuid vừa được sinh ra từ bảng auth.users
      auth_uuid = response.user.id
      print(f"✅ Auth OK: {emp['name']} -> {email} (UUID: {auth_uuid})")

      # 2. Link và lưu thông tin sang bảng `employees` trên PostgreSQL Database
      db_payload = {
          "employee_id": emp["id"],  # Khóa chính của nhân viên (EMP001...)
          "auth_uuid": auth_uuid,  # Khóa ngoại trỏ sang auth.users.id
          "employee_name": emp["name"],
          "position": emp["position"],
          "department": emp["department"],
          "system_level": emp["system_level"],
      }

      # Thực hiện upsert vào bảng employees (đảm bảo bảng employees đã có cột auth_uuid kiểu UUID)
      supabase.table("employee").upsert(db_payload).execute()
      print(f"🔗 Đã link thành công {emp['id']} vào bảng employees.")

    except Exception as e:
      print(f"❌ Lỗi xử lý cho nhân sự {emp['id']} ({emp['name']}): {e}")

  print("🎉 Hoàn tất toàn bộ quá trình đồng bộ dữ liệu!")


if __name__ == "__main__":
  seed_users_and_link_employees()