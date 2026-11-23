# Chrome Web Store Listing: BHYT Clinical Copilot - Phòng Khám Tài Sanh

## 1. Store Metadata

- **Extension Name**: BHYT Clinical Copilot - Phòng Khám Tài Sanh
- **Short Name**: BHYT Copilot
- **Version**: 1.0.0
- **Category**: Productivity / Health & Medical
- **Default Language**: Tiếng Việt (Vietnamese)
- **Support Contact**: William (Biện Ngọc Tam) & Dr. Đỗ Thị Anh Thư - Phòng Khám YHCT Tài Sanh, Tuy Hòa, Phú Yên.

---

## 2. Store Descriptions

### Short Description (132 characters max)
Trợ lý BHYT thông minh: Tra cứu danh mục Bộ Y tế, cảnh báo xuất toán thời gian thực và tự động điền bệnh án 1-click trên phần mềm HIS.

### Detailed Description
BHYT Clinical Copilot là công cụ đắc lực hỗ trợ các y bác sĩ và nhân viên y tế tại phòng khám đa khoa, chuyên khoa Y học cổ truyền (YHCT) và trạm y tế tối ưu hóa quy trình khám chữa bệnh bảo hiểm y tế:

1. **Giám Sát & Cảnh Báo Xuất Toán Thời Gian Thực**:
   - Tự động nhận diện mã ICD-10, thuốc tân dược và thủ thuật YHCT ngay khi bác sĩ thao tác trên phần mềm quản lý bệnh viện (HIS).
   - Cảnh báo tức thì nếu kê đơn thuốc vượt tuyến chuyên môn kỹ thuật (Quy chuẩn Tuyến 4 - Phòng khám tư nhân theo Thông tư 20/2022/TT-BYT).
   - Nhắc nhở thiếu chỉ định xét nghiệm cận lâm sàng bắt buộc (VD: Kê đơn Statin/Atorvastatin thiếu kết quả Lipid máu).
   - Kiểm soát chặt chẽ định mức thủ thuật YHCT (Điện châm, Xoa bóp bấm huyệt không vượt quá 15 ngày/đợt điều trị).
   - Cảnh báo nguy cơ tương tác Đông - Tây y nguy hiểm (Đan sâm, Đương quy kết hợp thuốc chống đông gây nguy cơ xuất huyết).

2. **1-Click Tự Động Điền Bệnh Án Chuẩn Bộ Y Tế**:
   - Tự động sinh mô tả quá trình bệnh lý, triệu chứng cơ năng, khám thực thể lâm sàng và chẩn đoán YHCT/YHHĐ phù hợp với mã ICD-10 chỉ với một cú nhấp chuột.
   - Điền trực tiếp vào ô diễn biến bệnh/khám bệnh trên HIS, tương thích với mọi nền tảng web hiện đại.

3. **Tra Cứu Danh Mục BHYT Siêu Tốc (Offline)**:
   - Tra cứu hơn 15.800 mã ICD-10 chuẩn hóa Bộ Y tế kèm tên tiếng Việt và tiếng Anh.
   - Tra cứu danh mục thuốc tân dược và tỷ lệ thanh toán BHYT (Thông tư 20/2022/TT-BYT).
   - Tra cứu dược liệu, vị thuốc YHCT, tính vị quy kinh và chống chỉ định (Thông tư 27/2020/TT-BYT).
   - Hoạt động 100% offline nội bộ, không phụ thuộc kết nối internet bên ngoài, phản hồi tức thì.

---

## 3. Permissions Justification

| Permission | Plain-English Reason for Review Team |
| :--- | :--- |
| `storage` | Lưu trữ cấu hình tuyến khám chữa bệnh của phòng khám, trạng thái bộ lọc danh mục và thống kê số lượng hồ sơ được hỗ trợ trực tiếp trên trình duyệt của người dùng. |
| `activeTab` | Cho phép tiện ích đọc mã ICD-10 và đơn thuốc hiển thị trên tab phần mềm HIS đang mở khi bác sĩ bấm nút kiểm tra hoặc tự động điền bệnh án. |
| `tabs` | Cho phép tiện ích quản lý và hiển thị huy hiệu (badge) cảnh báo nguy cơ xuất toán trực tiếp trên tab HIS đang thao tác. |
| `alarms` | Lên lịch định kỳ dọn dẹp bộ nhớ tạm của các tab khám bệnh đã đóng để tối ưu hóa hiệu năng trình duyệt. |
| Host: `<all_urls>` | Cần thiết để tiện ích hoạt động trên các cổng thông tin HIS nội bộ của bệnh viện/phòng khám (các tên miền HIS nội bộ, mạng LAN bệnh viện hoặc phần mềm quản lý phòng khám). |

---

## 4. Privacy & Data Use Disclosure

- **Data Collection**: Tiện ích **KHÔNG** thu thập, lưu trữ hay truyền tải bất kỳ thông tin nhận dạng cá nhân (PII), họ tên hay dữ liệu y tế nhạy cảm của bệnh nhân ra máy chủ bên ngoài.
- **Offline Processing**: 100% quy trình đối soát quy tắc xuất toán và tra cứu mã ICD-10 được thực thi cục bộ ngay trong trình duyệt (In-Browser Execution) thông qua bộ dữ liệu chuẩn hóa đi kèm tiện ích.
- **Third-Party Sharing**: Tuyệt đối không chia sẻ dữ liệu với bất kỳ bên thứ ba hay mạng quảng cáo nào.

---

## 5. Version History

- **v1.0.0 (2026-11-23)**:
  - Bản phát hành ban đầu hoàn chỉnh theo chuẩn Manifest V3.
  - Tích hợp bộ quy tắc xuất toán theo Thông tư 20/2022/TT-BYT và Thông tư 27/2020/TT-BYT.
  - Tích hợp 15.827 mã ICD-10 Việt hóa.
  - Tính năng In-Browser Floating Dock & 1-Click Clinical Note Autofill.
  - Vượt qua 100% bộ kiểm thử tự động Playwright E2E.
