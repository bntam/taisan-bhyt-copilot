# Tái Sanh BHYT Clinical Copilot & Xuất Toán Validator

Trợ lý AI trên trình duyệt chuyên biệt cho Bác sĩ & Phòng khám tại Việt Nam:
1. **Chống xuất toán BHYT thời gian thực (Zero BHYT Rejection):**
   - Tự động bắt lỗi kê thuốc vượt tuyến chuyên môn kỹ thuật (Tuyến 4 / Phòng khám tư nhân vs Tuyến 1, 2, 3).
   - Kiểm tra mã ICD-10 bắt buộc dùng mã chi tiết 4-5 ký tự (`MUST_USE_SUBCODE`) hoặc mã bị cấm dùng làm bệnh chính (`NOT_ALLOWED_PRIMARY`).
   - Cảnh báo thiếu xét nghiệm cận lâm sàng bắt buộc (VD: Statin thiếu Lipid máu).
   - Cảnh báo định mức ngày thực hiện thủ thuật Y học Cổ truyền / Phục hồi chức năng ($\le 15$ ngày/đợt).
2. **Cảnh báo tương tác Dược liệu YHCT & Thuốc Tân Dược (Herb-Drug Interaction Safety Guard):**
   - Phát hiện nguy cơ xuất huyết khi phối hợp Đan sâm, Đương quy với thuốc chống đông Tây y (Aspirin, Clopidogrel, Warfarin).
   - Cảnh báo hạ Kali máu và vô hiệu hóa thuốc hạ áp khi dùng Cam thảo với thuốc hạ áp/lợi tiểu.
3. **AI Clinical Note Autofill (1-Click điền bệnh án vào phần mềm HIS):**
   - Tự động sinh mô tả khám lâm sàng thực thể, triệu chứng cơ năng và chẩn đoán bát cương YHCT hợp thức hóa chỉ định BHYT theo đúng phác đồ Bộ Y tế.
4. **Cơ chế Tự động Cập nhật Dữ liệu (Auto-Update Catalog Engine):**
   - Tích hợp 15,827 mã ICD-10 tiếng Việt kèm cờ quy chế BHYT từ Cổng dữ liệu Bộ Y tế & Cổng Giám định BHYT.
   - Hỗ trợ FTS5 Full-Text Search siêu tốc không dấu và có dấu.
   - Hỗ trợ auto-sync định kỳ qua cron hoặc kích hoạt on-demand qua CLI, API, hoặc MCP.
5. **Kiến trúc Plug-and-Play MCP (Model Context Protocol):**
   - Hỗ trợ kết nối hai chiều với Claude Code, Cursor, và các hệ thống bên thứ ba (LangCare voice, EMR nội bộ).

---

## Cấu Trúc Mã Nguồn

```
taisan-bhyt-copilot/
├── data/
│   ├── bhyt_catalog.db          # SQLite Database: 15,827 ICD-10 codes, Thuốc TT20, YHCT TT27, Thủ thuật TT13
│   ├── sync_metadata.json       # Metadata phiên bản, SHA256 checksum và lịch sử đồng bộ
│   └── raw/                     # Cached datasets tải từ cổng Bộ Y tế / WHO
├── data_engine/
│   ├── db.py                    # SQLite connection, migration & FTS5 full-text indexing
│   ├── icd10_sync.py            # Pipeline cào & chuẩn hóa 15,827 mã ICD-10 kèm cờ BHYT
│   ├── thuoc_tt20_sync.py       # Danh mục thuốc tân dược Thông tư 20/2022/TT-BYT & QĐ 7603
│   ├── thu_thuat_tt13_sync.py   # Danh mục dịch vụ/thủ thuật TT 13/2019, TT 39/2018, TT 22/2023
│   ├── yhct_tt27_sync.py        # Danh mục thuốc YHCT TT 27/2020 & Ánh xạ QĐ 4443/QĐ-BYT
│   ├── xuat_toan_rules_sync.py  # 20+ quy tắc xuất toán kinh điển của BHXH Việt Nam
│   ├── updater.py               # Auto-Update Engine, backup snapshot & checksum verification
│   └── cli.py                   # Giao diện CLI tra cứu, kiểm toán và đồng bộ
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
    ├── test_db_init.py          # Kiểm thử Schema & FTS5 Virtual Tables
    ├── test_icd10_sync.py       # Kiểm thử 15,827 mã ICD-10 & cờ quy chế BHYT
    ├── test_thuoc_sync.py       # Kiểm thử danh mục thuốc TT20 & phân tuyến bệnh viện
    ├── test_thuthuat_sync.py    # Kiểm thử thủ thuật TT13 & định mức ngày điều trị
    ├── test_yhct_sync.py        # Kiểm thử dược liệu YHCT TT27 & tương tác Tây y
    ├── test_rules_sync.py       # Kiểm thử 20+ quy tắc xuất toán BHYT
    ├── test_updater.py          # Kiểm thử quy trình Auto-Update, Backup & Metadata
    ├── test_data_engine.py      # Kiểm thử tích hợp toàn diện Data Engine
    └── test_audit_engine.py     # Bộ kiểm thử 8 ca xuất toán kinh điển (100% Pass)
```

---

## Hướng Dẫn Sử Dụng & CLI

### 1. Quản trị Dữ liệu qua CLI
```bash
# Kiểm tra trạng thái Catalog
python3 data_engine/cli.py status

# Tra cứu mã ICD-10 toàn văn (FTS5)
python3 data_engine/cli.py search icd "thoát vị đĩa đệm"

# Tra cứu thuốc tân dược và điều kiện thanh toán
python3 data_engine/cli.py search drug "cefixim"

# Tra cứu vị thuốc YHCT và cảnh báo tương tác Tây y
python3 data_engine/cli.py search herb "đan sâm"

# Chạy kiểm toán đơn thuốc & thủ thuật trực tiếp
python3 data_engine/cli.py audit \
  --icd M54.5 \
  --drugs "Paracetamol 500mg, Ceftriaxone 1g" \
  --procedures "Điện châm điều trị" \
  --days 18 \
  --level 4
```

### 2. Đồng bộ & Cập nhật Dữ liệu Tự động
```bash
# Kiểm tra và cập nhật tự động (nếu có bản mới)
python3 scripts/auto_update_cron.py

# Cưỡng bức đồng bộ và tạo bản backup SQLite
python3 scripts/auto_update_cron.py --force
```

### 3. Khởi chạy REST API & MCP Server
```bash
python3 -m uvicorn mcp_server.api:app --host 127.0.0.1 --port 8123
```

### 4. Chạy Toàn Bộ Test Suite (23/23 Tests PASS)
```bash
python3 -m unittest discover -s tests
```

### 5. Cài đặt Chrome Extension
1. Mở trình duyệt Chrome: `chrome://extensions/`
2. Bật **Developer mode** ở góc phải trên.
3. Bấm **Load unpacked** $\rightarrow$ chọn thư mục `/root/taisan-bhyt-copilot/extension`.
