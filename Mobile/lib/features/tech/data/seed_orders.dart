import '../domain/tech_models.dart';

/// Sample orders already accepted by staff and assigned to a technician, so the
/// desk has something in every phase. Values come from the FE catalog
/// (`constants/catalog.ts`); names stay English and are translated with `tn`.

class _Type {
  final String name, size, aspect;
  final int mins;
  final bool land;
  const _Type(this.name, this.size, this.aspect, this.mins, {this.land = false});
}

const _card = _Type('Greeting card', 'A6 · 105×148 mm', '105/148', 4);
const _letter = _Type('Handwritten letter', 'A5 · 148×210 mm', '148/210', 9);
const _envelope = _Type('Addressed envelope', 'DL · 220×110 mm', '220/110', 2, land: true);
const _invite = _Type('Wedding invitation', '127×178 mm', '127/178', 6);

const _papers = {
  'Ivory': 0xFFF4EEE0,
  'Cotton rag': 0xFFFBFAF5,
  'Kraft': 0xFFC9A77E,
  'Giấy dó': 0xFFEBE0C8,
};
const _pens = {'Fountain pen': 2.0, 'Gel pen': 3.0, 'Calligraphy nib': 5.0, 'Brush pen': 8.0};
const _inks = {
  'Midnight blue': 0xFF1B2440,
  'Carbon black': 0xFF141414,
  'Sepia': 0xFF6B3F22,
  'Lacquer red': 0xFF9E2A1F,
  'Metallic gold': 0xFFB08732,
};

/// Font families registered in pubspec, keyed by the FE style name.
const scriptFonts = {'Script': 'DancingScript', 'Formal': 'GreatVibes', 'Casual': 'Caveat'};

OrderSpec _spec(
  _Type type, {
  String paper = 'Ivory',
  String pen = 'Fountain pen',
  String ink = 'Midnight blue',
  String style = 'Script',
  InputKind mode = InputKind.text,
  String text = '',
  String? simText,
  String? fileName,
  int qty = 1,
}) =>
    OrderSpec(
      type: type.name,
      size: type.size,
      aspect: type.aspect,
      land: type.land,
      mins: type.mins,
      paper: paper,
      paperColor: _papers[paper]!,
      pen: pen,
      penW: _pens[pen]!,
      ink: ink,
      inkColor: _inks[ink]!,
      font: scriptFonts[style]!,
      fontName: style,
      mode: mode,
      text: text,
      qty: qty,
      simText: simText,
      fileName: fileName,
    );

Assignment _asg(String techId, String techName, String robotId) =>
    Assignment(techId: techId, techName: techName, robotId: robotId, at: DateTime(2026, 10, 6, 8));

List<TechOrder> seedTechOrders() {
  // A run that finished an hour ago, so its order opens straight in photo and QC.
  final finishedRun = DateTime.now().subtract(const Duration(hours: 1)).millisecondsSinceEpoch;

  return [
    // ── T-01 Hà Trần ──
    TechOrder(
      id: 'VH-4821',
      title: 'Wedding invitation × 120',
      detail: 'Cotton rag · Metallic gold',
      status: OrderStatus.Queued,
      total: 9840000,
      date: '06 Oct 2026',
      layout: LayoutKind.framed,
      name: 'Thu Trang',
      spec: _spec(_invite, paper: 'Cotton rag', ink: 'Metallic gold', style: 'Formal', text: 'Thu & Khang', qty: 120),
      assignment: _asg('T-01', 'Hà Trần', 'FR3-01'),
      depositMethod: 'VNPay',
    ),
    TechOrder(
      id: 'VH-4844',
      title: 'Addressed envelope × 1',
      detail: 'Kraft · Carbon black',
      status: OrderStatus.Queued,
      total: 95000,
      date: '12 Oct 2026',
      layout: LayoutKind.letter,
      name: 'Lan Phương',
      spec: _spec(_envelope, paper: 'Kraft', ink: 'Carbon black', pen: 'Gel pen', style: 'Casual', text: 'Cô Lan\n12 Lý Thường Kiệt, Hà Nội'),
      assignment: _asg('T-01', 'Hà Trần', 'FR3-02'),
      run: RobotRun(robotId: 'FR3-02', startedAt: finishedRun, seconds: 45),
      depositMethod: 'MoMo',
    ),
    TechOrder(
      id: 'VH-4840',
      title: 'Handwritten letter × 1',
      detail: 'Giấy dó · Sepia',
      status: OrderStatus.Rewriting,
      total: 145000,
      date: '11 Oct 2026',
      layout: LayoutKind.letter,
      name: 'Quốc Bảo',
      spec: _spec(_letter,
          paper: 'Giấy dó',
          ink: 'Sepia',
          style: 'Casual',
          mode: InputKind.upload,
          fileName: 'thu-gui-me.jpg',
          simText: 'Gửi mẹ,\ncon nhớ mẹ nhiều lắm.\nTết này con về nhé.'),
      assignment: _asg('T-01', 'Hà Trần', 'FR3-03'),
      qcFail: QcFail(reasons: const ['Ink smudge'], note: 'Second line smudged by the pen holder.', at: DateTime(2026, 10, 13, 10)),
      depositMethod: 'VietQR',
    ),
    TechOrder(
      id: 'VH-4836',
      title: 'Greeting card × 10',
      detail: 'Ivory · Lacquer red',
      status: OrderStatus.Accepted,
      total: 405000,
      date: '13 Oct 2026',
      name: 'Minh Anh',
      spec: _spec(_card, ink: 'Lacquer red', text: 'Chúc Mừng Năm Mới', qty: 10),
      assignment: _asg('T-01', 'Hà Trần', 'FR3-01'),
    ),
    TechOrder(
      id: 'VH-4795',
      title: 'Thank-you card × 1',
      detail: 'Ivory · Midnight blue',
      status: OrderStatus.Written,
      total: 45000,
      date: '04 Oct 2026',
      name: 'Hoàng Nam',
      spec: _spec(_card, text: 'Cảm ơn bạn!'),
      assignment: _asg('T-01', 'Hà Trần', 'FR3-03'),
      qc: QcReport(checked: const [], total: 11, photos: const [], note: '', by: 'Hà Trần', at: DateTime(2026, 10, 5, 9)),
      depositMethod: 'VNPay',
    ),

    // ── T-02 Phúc Lê ──
    TechOrder(
      id: 'VH-4850',
      title: 'Greeting card × 10',
      detail: 'Ivory · Midnight blue',
      status: OrderStatus.Queued,
      total: 405000,
      date: '13 Oct 2026',
      name: 'Ngọc Hân',
      spec: _spec(_card, pen: 'Gel pen', mode: InputKind.draw, simText: 'chúc mừng sinh nhật\nbé Na tròn 5 tuổi', qty: 10),
      assignment: _asg('T-02', 'Phúc Lê', 'FR3-04'),
      depositMethod: 'ZaloPay',
    ),
    TechOrder(
      id: 'VH-4853',
      title: 'Handwritten letter × 1',
      detail: 'Cotton rag · Carbon black',
      status: OrderStatus.Accepted,
      total: 145000,
      date: '14 Oct 2026',
      layout: LayoutKind.letter,
      name: 'Đức Huy',
      spec: _spec(_letter, paper: 'Cotton rag', ink: 'Carbon black', style: 'Casual', text: 'Gửi em, người thương…'),
      assignment: _asg('T-02', 'Phúc Lê', 'FR3-05'),
    ),

    // ── T-03 Anh Vũ ──
    TechOrder(
      id: 'VH-4860',
      title: 'Wedding invitation × 60',
      detail: 'Cotton rag · Metallic gold',
      status: OrderStatus.Queued,
      total: 4920000,
      date: '12 Oct 2026',
      layout: LayoutKind.framed,
      name: 'Bảo Ngọc',
      spec: _spec(_invite, paper: 'Cotton rag', ink: 'Metallic gold', style: 'Formal', text: 'Trân trọng kính mời\nNgọc & Tuấn', qty: 60),
      assignment: _asg('T-03', 'Anh Vũ', 'FR3-06'),
      depositMethod: 'Card',
    ),
    TechOrder(
      id: 'VH-4862',
      title: 'Greeting card × 1',
      detail: 'Kraft · Sepia',
      status: OrderStatus.Queued,
      total: 50000,
      date: '14 Oct 2026',
      name: 'Thanh Tâm',
      spec: _spec(_card, paper: 'Kraft', ink: 'Sepia', pen: 'Calligraphy nib', text: 'An Khang Thịnh Vượng'),
      assignment: _asg('T-03', 'Anh Vũ', 'FR3-07'),
      run: RobotRun(robotId: 'FR3-07', startedAt: finishedRun, seconds: 45),
      depositMethod: 'MoMo',
    ),

    // ── T-04 Thảo Đinh ──
    TechOrder(
      id: 'VH-4870',
      title: 'Greeting card × 10',
      detail: 'Giấy dó · Lacquer red',
      status: OrderStatus.Queued,
      total: 455000,
      date: '13 Oct 2026',
      name: 'Gia Linh',
      spec: _spec(_card, paper: 'Giấy dó', ink: 'Lacquer red', pen: 'Brush pen', text: 'Phúc Lộc Thọ', qty: 10),
      assignment: _asg('T-04', 'Thảo Đinh', 'FR3-10'),
      depositMethod: 'VNPay',
    ),
    TechOrder(
      id: 'VH-4872',
      title: 'Addressed envelope × 1',
      detail: 'Ivory · Midnight blue',
      status: OrderStatus.Accepted,
      total: 25000,
      date: '14 Oct 2026',
      name: 'Khánh Vy',
      spec: _spec(_envelope, style: 'Casual', text: 'Anh Minh\n45 Nguyễn Huệ, TP. Hồ Chí Minh'),
      assignment: _asg('T-04', 'Thảo Đinh', 'FR3-11'),
    ),
  ];
}
