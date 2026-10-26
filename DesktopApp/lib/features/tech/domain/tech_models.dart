// Status names match the FE strings exactly.
// ignore_for_file: constant_identifier_names


import 'package:equatable/equatable.dart';

/// Technician-side order model, mirroring `FE/src/types/index.ts`.
///
/// Status and catalog names are stored in English (as in the FE) and
/// translated at display time through `T.tn`.

/// Lifecycle of an order. Names match the FE status strings exactly.
enum OrderStatus {
  Sketching,
  Pending,
  Rejected,
  Accepted,
  Queued,
  Written,
  Rewriting,
  Shipped,
  Delivered;

  static OrderStatus parse(String? s) =>
      values.firstWhere((v) => v.name == s, orElse: () => Pending);
}

enum InputKind {
  text,
  upload,
  draw;

  /// Catalog label shown through `tn`, same as FE `MODE_LABEL`.
  String get label => switch (this) {
        text => 'TEXT',
        upload => 'IMAGE',
        draw => 'DRAWING',
      };

  static InputKind parse(String? s) =>
      values.firstWhere((v) => v.name == s, orElse: () => text);
}

/// Paper layouts from the FE catalog.
enum LayoutKind {
  classic('Centered', frame: false, top: false, left: false),
  framed('Framed', frame: true, top: false, left: false),
  letter('Letter', frame: false, top: true, left: true);

  final String label;
  final bool frame;

  /// Text starts at the top margin instead of being centred vertically.
  final bool top;

  /// Lines are left aligned instead of centred.
  final bool left;

  const LayoutKind(this.label, {required this.frame, required this.top, required this.left});

  static LayoutKind parse(String? s) =>
      values.firstWhere((v) => v.name == s, orElse: () => classic);
}

/// Everything the robot needs to know about one piece.
class OrderSpec extends Equatable {
  final String type;
  final String size;

  /// Width/height in mm, e.g. `105/148`. Already includes orientation.
  final String aspect;
  final bool land;
  final int mins;
  final String paper;
  final int paperColor;
  final String pen;
  final double penW;
  final String ink;
  final int inkColor;

  /// Flutter font family registered in pubspec (DancingScript, GreatVibes, Caveat).
  final String font;
  final String fontName;
  final InputKind mode;
  final String text;
  final int qty;

  /// Demo only: what an uploaded photo or drawing reads as.
  final String? simText;
  final String? fileName;

  const OrderSpec({
    required this.type,
    required this.size,
    required this.aspect,
    required this.land,
    required this.mins,
    required this.paper,
    required this.paperColor,
    required this.pen,
    required this.penW,
    required this.ink,
    required this.inkColor,
    required this.font,
    required this.fontName,
    required this.mode,
    required this.text,
    required this.qty,
    this.simText,
    this.fileName,
  });

  factory OrderSpec.fromJson(Map<String, dynamic> j) => OrderSpec(
        type: j['type'] as String,
        size: j['size'] as String,
        aspect: j['aspect'] as String,
        land: j['land'] as bool? ?? false,
        mins: j['mins'] as int? ?? 4,
        paper: j['paper'] as String,
        paperColor: j['paperColor'] as int,
        pen: j['pen'] as String,
        penW: (j['penW'] as num?)?.toDouble() ?? 2,
        ink: j['ink'] as String,
        inkColor: j['inkColor'] as int,
        font: j['font'] as String,
        fontName: j['fontName'] as String,
        mode: InputKind.parse(j['mode'] as String?),
        text: j['text'] as String? ?? '',
        qty: j['qty'] as int? ?? 1,
        simText: j['simText'] as String?,
        fileName: j['fileName'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'type': type,
        'size': size,
        'aspect': aspect,
        'land': land,
        'mins': mins,
        'paper': paper,
        'paperColor': paperColor,
        'pen': pen,
        'penW': penW,
        'ink': ink,
        'inkColor': inkColor,
        'font': font,
        'fontName': fontName,
        'mode': mode.name,
        'text': text,
        'qty': qty,
        if (simText != null) 'simText': simText,
        if (fileName != null) 'fileName': fileName,
      };

  @override
  List<Object?> get props => [type, aspect, paper, pen, ink, font, mode, text, qty, simText];
}

/// Technician and robot that staff picked after accepting the order.
class Assignment extends Equatable {
  final String techId;
  final String techName;
  final String robotId;
  final DateTime at;

  const Assignment({required this.techId, required this.techName, required this.robotId, required this.at});

  factory Assignment.fromJson(Map<String, dynamic> j) => Assignment(
        techId: j['techId'] as String,
        techName: j['techName'] as String,
        robotId: j['robotId'] as String,
        at: DateTime.parse(j['at'] as String),
      );

  Map<String, dynamic> toJson() =>
      {'techId': techId, 'techName': techName, 'robotId': robotId, 'at': at.toIso8601String()};

  @override
  List<Object?> get props => [techId, robotId, at];
}

/// Set when a technician starts the real robot. Cleared when the order is marked written.
class RobotRun extends Equatable {
  final String robotId;
  final int startedAt; // epoch ms
  /// Prototype only: how long the simulated run lasts.
  final int seconds;

  const RobotRun({required this.robotId, required this.startedAt, required this.seconds});

  factory RobotRun.fromJson(Map<String, dynamic> j) => RobotRun(
        robotId: j['robotId'] as String,
        startedAt: j['startedAt'] as int,
        seconds: j['seconds'] as int,
      );

  Map<String, dynamic> toJson() => {'robotId': robotId, 'startedAt': startedAt, 'seconds': seconds};

  @override
  List<Object?> get props => [robotId, startedAt, seconds];
}

class QcPhoto extends Equatable {
  /// English slot label (Whole sheet, Close-up, Packed).
  final String slot;

  /// Local file path of the downscaled PNG.
  final String path;

  const QcPhoto({required this.slot, required this.path});

  factory QcPhoto.fromJson(Map<String, dynamic> j) =>
      QcPhoto(slot: j['slot'] as String, path: j['path'] as String);

  Map<String, dynamic> toJson() => {'slot': slot, 'path': path};

  @override
  List<Object?> get props => [slot, path];
}

/// What the technician recorded at photo and QC, and what the customer is sent.
class QcReport extends Equatable {
  final List<String> checked;
  final int total;
  final List<QcPhoto> photos;
  final String note;
  final String by;
  final DateTime at;

  const QcReport({
    required this.checked,
    required this.total,
    required this.photos,
    required this.note,
    required this.by,
    required this.at,
  });

  factory QcReport.fromJson(Map<String, dynamic> j) => QcReport(
        checked: (j['checked'] as List).cast<String>(),
        total: j['total'] as int,
        photos: (j['photos'] as List).map((e) => QcPhoto.fromJson(e as Map<String, dynamic>)).toList(),
        note: j['note'] as String? ?? '',
        by: j['by'] as String? ?? '',
        at: DateTime.parse(j['at'] as String),
      );

  Map<String, dynamic> toJson() => {
        'checked': checked,
        'total': total,
        'photos': photos.map((p) => p.toJson()).toList(),
        'note': note,
        'by': by,
        'at': at.toIso8601String(),
      };

  @override
  List<Object?> get props => [checked, total, photos, note, by, at];
}

/// Set when QC failed and the order went back to the robot queue.
class QcFail extends Equatable {
  final List<String> reasons;
  final String note;
  final DateTime at;

  const QcFail({required this.reasons, required this.note, required this.at});

  factory QcFail.fromJson(Map<String, dynamic> j) => QcFail(
        reasons: (j['reasons'] as List).cast<String>(),
        note: j['note'] as String? ?? '',
        at: DateTime.parse(j['at'] as String),
      );

  Map<String, dynamic> toJson() => {'reasons': reasons, 'note': note, 'at': at.toIso8601String()};

  @override
  List<Object?> get props => [reasons, note, at];
}

class TechOrder extends Equatable {
  final String id;
  final String title;
  final String detail;
  final OrderStatus status;
  final int total;
  final String date;
  final OrderSpec spec;
  final LayoutKind layout;
  final String? name;
  final String? ocrText;
  final Assignment? assignment;
  final RobotRun? run;
  final QcReport? qc;
  final QcFail? qcFail;
  final String? depositMethod;

  const TechOrder({
    required this.id,
    required this.title,
    required this.detail,
    required this.status,
    required this.total,
    required this.date,
    required this.spec,
    this.layout = LayoutKind.classic,
    this.name,
    this.ocrText,
    this.assignment,
    this.run,
    this.qc,
    this.qcFail,
    this.depositMethod,
  });

  /// Copy with changes. Nullable fields are cleared by passing `clearX: true`.
  TechOrder copyWith({
    OrderStatus? status,
    RobotRun? run,
    bool clearRun = false,
    QcReport? qc,
    bool clearQc = false,
    QcFail? qcFail,
    bool clearQcFail = false,
    String? depositMethod,
  }) =>
      TechOrder(
        id: id,
        title: title,
        detail: detail,
        status: status ?? this.status,
        total: total,
        date: date,
        spec: spec,
        layout: layout,
        name: name,
        ocrText: ocrText,
        assignment: assignment,
        run: clearRun ? null : (run ?? this.run),
        qc: clearQc ? null : (qc ?? this.qc),
        qcFail: clearQcFail ? null : (qcFail ?? this.qcFail),
        depositMethod: depositMethod ?? this.depositMethod,
      );

  factory TechOrder.fromJson(Map<String, dynamic> j) => TechOrder(
        id: j['id'] as String,
        title: j['title'] as String,
        detail: j['detail'] as String? ?? '',
        status: OrderStatus.parse(j['status'] as String?),
        total: j['total'] as int? ?? 0,
        date: j['date'] as String? ?? '',
        spec: OrderSpec.fromJson(j['spec'] as Map<String, dynamic>),
        layout: LayoutKind.parse(j['layout'] as String?),
        name: j['name'] as String?,
        ocrText: j['ocrText'] as String?,
        assignment: j['assignment'] == null ? null : Assignment.fromJson(j['assignment'] as Map<String, dynamic>),
        run: j['run'] == null ? null : RobotRun.fromJson(j['run'] as Map<String, dynamic>),
        qc: j['qc'] == null ? null : QcReport.fromJson(j['qc'] as Map<String, dynamic>),
        qcFail: j['qcFail'] == null ? null : QcFail.fromJson(j['qcFail'] as Map<String, dynamic>),
        depositMethod: j['depositMethod'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'detail': detail,
        'status': status.name,
        'total': total,
        'date': date,
        'spec': spec.toJson(),
        'layout': layout.name,
        if (name != null) 'name': name,
        if (ocrText != null) 'ocrText': ocrText,
        if (assignment != null) 'assignment': assignment!.toJson(),
        if (run != null) 'run': run!.toJson(),
        if (qc != null) 'qc': qc!.toJson(),
        if (qcFail != null) 'qcFail': qcFail!.toJson(),
        if (depositMethod != null) 'depositMethod': depositMethod,
      };

  /// Minutes of writing for all pieces.
  int get minutes => ((spec.mins == 0 ? 4 : spec.mins) * (spec.qty == 0 ? 1 : spec.qty)).clamp(1, 1 << 30);

  /// Text the robot writes: typed text, or what the photo or strokes were read as.
  String get recognizedText {
    if (spec.mode == InputKind.text) return spec.text;
    if (ocrText != null) return ocrText!;
    return spec.simText ?? spec.text;
  }

  @override
  List<Object?> get props => [id, status, run, qc, qcFail, assignment, depositMethod];
}

// ─── Phases ───────────────────────────────────────────────────────────

/// Where an assigned order is from the technician's point of view (FE `phase.ts`).
enum Phase { qc, live, ready, wait, done }

bool _inQueue(TechOrder o) => o.status == OrderStatus.Queued || o.status == OrderStatus.Rewriting;

/// The robot run has reached its end time. Photo and QC comes next.
bool runDone(TechOrder o, int now) =>
    o.run != null && _inQueue(o) && now >= o.run!.startedAt + o.run!.seconds * 1000;

Phase? phaseOf(TechOrder o, int now) {
  if (o.run != null && _inQueue(o)) return runDone(o, now) ? Phase.qc : Phase.live;
  if (_inQueue(o)) return Phase.ready;
  if (o.status == OrderStatus.Accepted) return Phase.wait;
  if (const [OrderStatus.Written, OrderStatus.Shipped, OrderStatus.Delivered].contains(o.status)) {
    return Phase.done;
  }
  return null;
}

const finishedStatuses = [OrderStatus.Written, OrderStatus.Shipped, OrderStatus.Delivered];
