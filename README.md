# Apify Auto Account Creator

Công cụ tạo và trích xuất API Token hàng loạt cho nền tảng Apify.com.

> **Credits & Author:** [PotatoTrollVn](https://github.com/PotatoTrollVn)

## Giới thiệu

Tool này cho phép bạn:
1. Tự động sinh ra các temp mail bằng dịch vụ **Mail.tm**.
2. Tự động đăng ký các tài khoản Apify một cách vô hình nhờ **DrissionPage** (ẩn danh, vượt Cloudflare).
3. Tự động truy cập hòm thư, ấn link xác nhận, đăng nhập Apify và trích xuất **API Key**.
4. Tự động kiểm tra (Verify) xem Key nào hợp lệ, sau đó loại bỏ các key lỗi/sắp hết hạn để lọc ra danh sách API Key sạch sẽ nhất.

## Cài đặt

Yêu cầu Python 3.10+ và thư viện DrissionPage:
```bash
pip install DrissionPage requests
```

## Sử dụng

Cách nhanh nhất là chạy file `main.py`. Nó sẽ tự động kích hoạt tuần tự toàn bộ quy trình từ Tạo Email -> Đăng Ký -> Lấy Token -> Kiểm tra Token.

```bash
python main.py
```

### Chạy lẻ từng chức năng:
- Tạo Email: `python generate_email.py`
- Đăng Ký: `python auto_register.py`
- Trích xuất API Key: `python auto_verify.py`
- Lọc và dọn dẹp API Key hỏng: `python check_tokens.py`

## Kết quả
Sau khi chạy xong, danh sách API Keys hợp lệ sẽ nằm ở file `apify_token.json`.
Tất cả các tài khoản đã đăng ký thành công nằm ở `registered_accounts.json`.
