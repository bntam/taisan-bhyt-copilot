# Tái Sanh BHYT Clinical Copilot & Xuất Toán Validator

Trợ lý AI trên trình duyệt chuyên biệt cho Bác sĩ & Phòng khám tại Việt Nam:
1. **Chống xuất toán BHYT thời gian thực (Zero BHYT Rejection):**
   - Tự động bắt lỗi kê thuốc vượt tuyến chuyên môn kỹ thuật (Tuyến 4 / Phòng khám tư nhân vs Tuyến 1, 2, 3).
   - Kiểm tra mã ICD-10 bắt buộc dùng mã chi tiết 4 ký tự (`MUST_USE_SUBCODE`) hoặc mã bị cấm dùng làm bệnh chính (`NOT_ALLOWED_PRIMARY`).
   - Cảnh báo thiếu xét nghiệm cận lâm sàng bắt buộc (VD: Statin thiếu Lipid máu).
   - Cảnh báo định mức ngày thực hiện thủ thuật Y học Cổ truyền / Phục hồi chức năng ($\le 15$ ngày/đợt).
2. **Cảnh báo tương tác Dược liệu YHCT & Thuốc Tân Dược (Herb-Drug Interaction Safety Guard):**
   - Phát hiện nguy cơ xuất huyết khi phối hợp Đan sâm, Đương quy với thuốc chống đông Tây y (Aspirin, Clopidogrel, Warfarin).
   - Cảnh báo hạ Kali máu và vô hiệu hóa thuốc hạ áp khi dùng Cam thảo với thuốc hạ áp/lợi tiểu.
3. **AI Clinical Note Autofill (1-Click điền bệnh án vào phần mềm HIS):**
   - Tự động sinh mô tả khám lâm sàng thực thể, triệu chứng cơ năng và chẩn đoán bát cương YHCT hợp thức hóa chỉ định BHYT theo đúng phác đồ Bộ Y tế.
4. **Cơ chế Tự động Cập nhật Dữ liệu (Auto-Update Catalog Engine):**
   - Tích hợp 15,827 mã ICD-10 tiếng Việt kèm cờ quy chế BHYT từ Cổng dữ liệu Bộ Y tế & Cổng Giám định BHYT.
   - Hỗ trợ auto-sync định kỳ qua cron hoặc kích hoạt on-demand qua API / MCP.
5. **Kiến trúc Plug-and-Play MCP (Model Context Protocol):**
   - Hỗ trợ kết nối hai chiều với Claude Code, Cursor, và các hệ thống bên thứ ba (LangCare voice, EMR nội bộ).

---

## Cấu Trúc Mã Nguồn

```
taisan-bhyt-copilot/
├── data/
│   ├── bhyt_catalog.db          # SQLite Database: 15,827 ICD-10 codes, Thuốc TT20, YHCT TT27, Thủ thuật TT13
│   └── sync_metadata.json       # Metadata phiên bản và lịch sử đồng bộ
├── data_engine/
│   └── sync_catalog.py          # Pipeline cào và chuẩn hóa danh mục BHYT
├── mcp_server/
│   ├── server.py                # Core Engine: Rules Validator, Search ICD, Note Generator
│   └── api.py                   # FastAPI Server cung cấp REST API cho Extension & MCP
├── extension/                   # Chrome Extension Manifest V3
│   ├── manifest.json
│   ├── popup/                   # Giao diện tra cứu & kiểm tra xuất toán
│   ├── content_scripts/         # Injected script vào HIS/EMR để autofill 1-click
│   └── background/              # Background service worker
├── scripts/
│   └── auto_update_cron.py      # Watchdog tự động cập nhật dữ liệu định kỳ
└── tests/
    └── test_audit_engine.py     # Bộ kiểm thử 8 ca xuất toán kinh điển (100% Pass)
```

## Chạy Thử Nghiệm

1. **Khởi chạy API & MCP Server:**
   ```bash
   python3 -m uvicorn mcp_server.api:app --host 127.0.0.1 --port 8123
   ```
2. **Chạy Unit Test:**
   ```bash
   python3 -m unittest tests/test_audit_engine.py
   ```
3. **Cập nhật dữ liệu BHYT mới nhất:**
   ```bash
   python3 scripts/auto_update_cron.py --force
   ```
4. **Cài đặt Chrome Extension:**
   - Mở Chrome: `chrome://extensions/`
   - Bật **Developer mode** $\rightarrow$ chọn **Load unpacked** $\rightarrow$ trỏ vào thư mục `extension/`.
