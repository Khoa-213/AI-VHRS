import { useState } from 'react'
import { useT } from '../../i18n'
import PrivacyDialog from './PrivacyDialog'

/** Dev only (`/dev/privacy`): the privacy popup with sample text, no backend or order needed. */
const BODY = `Xưởng Nét Việt – AI-VHRS. Phiên bản 1.0.

Tại Xưởng Nét Việt, chúng tôi tôn trọng và cam kết bảo vệ thông tin cá nhân, hình ảnh, tài liệu và nét chữ mà Quý khách cung cấp.

### 1. Thông tin chúng tôi thu thập
- **Thông tin cá nhân:** Họ tên, email, số điện thoại và địa chỉ giao hàng.
- **Dữ liệu đơn hàng:** Hình ảnh, tài liệu PDF, mẫu chữ viết tay, nét vẽ và nội dung Quý khách cung cấp.
- **Dữ liệu xử lý:** Phác thảo, bộ nét chữ, dữ liệu vận hành robot và ảnh sản phẩm hoàn thành.
- **Thông tin giao dịch:** Mã giao dịch, số tiền, trạng thái thanh toán và lịch sử đơn hàng.

Chúng tôi không lưu số thẻ ngân hàng, mã bảo mật thẻ hoặc mật khẩu ví điện tử.

### 2. Mục đích sử dụng dữ liệu
- Xử lý yêu cầu, tạo phác thảo và báo giá.
- Phục dựng nét chữ và vận hành robot để tạo sản phẩm.
- Quản lý đơn hàng, thanh toán và giao nhận sản phẩm.
- Hỗ trợ khách hàng, xử lý khiếu nại và bảo đảm an toàn hệ thống.

**Cam kết:** Xưởng Nét Việt không sử dụng hình ảnh, tài liệu hoặc nét chữ của khách hàng để huấn luyện AI, nghiên cứu, quảng cáo hoặc bán cho bên thứ ba.

### 3. Bảo mật và chia sẻ thông tin
Chúng tôi áp dụng các biện pháp bảo vệ dữ liệu bao gồm kết nối HTTPS, phân quyền truy cập theo vai trò và ghi nhận lịch sử các thao tác quan trọng.

Dữ liệu chỉ được chia sẻ trong phạm vi cần thiết với nhân sự phụ trách, đơn vị thanh toán, vận chuyển, nhà cung cấp dịch vụ hỗ trợ hệ thống hoặc cơ quan có thẩm quyền theo quy định pháp luật.

### 4. Thời gian lưu trữ và xóa dữ liệu
- **Ảnh, tài liệu và nét chữ của đơn hàng:** Được xóa sau 90 ngày kể từ khi đơn hoàn tất.
- **Đơn hàng bị hủy:** Dữ liệu ảnh và nét chữ được xử lý xóa theo quy trình hủy đơn.
- **Bộ nét chữ được chọn lưu:** Được giữ để sử dụng cho các đơn tiếp theo đến khi Quý khách yêu cầu xóa.
- **Thông tin giao dịch và nhật ký:** Được lưu trong thời hạn cần thiết theo quy định pháp luật.

### 5. Quyền của Quý khách
Quý khách có quyền truy cập, chỉnh sửa, yêu cầu xóa, hạn chế xử lý dữ liệu hoặc rút lại sự đồng ý theo quy định của pháp luật Việt Nam.

### 6. Đồng ý và tiếp tục sử dụng dịch vụ
Bằng việc chọn "Đồng ý và xem phác thảo", Quý khách xác nhận đã đọc, hiểu và đồng ý với Chính sách quyền riêng tư này. Hệ thống sẽ ghi nhận thời điểm và phiên bản chính sách được chấp thuận.`

export default function PrivacyPreview() {
  const t = useT()
  const [open, setOpen] = useState(true)
  const [result, setResult] = useState('')
  return (
    <main style={{ padding: 40 }}>
      <button className="vh-btn vh-btn--primary vh-btn--md" onClick={() => setOpen(true)}>{t('ov.privacyRead')}</button>
      <p role="status">{result}</p>
      {open && (
        <PrivacyDialog
          policy={{ version: '1.0', title: 'Chính sách quyền riêng tư', body: BODY }}
          busy={false}
          onClose={() => setOpen(false)}
          onDecline={() => { setResult('declined'); setOpen(false) }}
          onAgree={() => { setResult('agreed'); setOpen(false) }}
        />
      )}
    </main>
  )
}
