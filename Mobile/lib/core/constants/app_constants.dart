/// Application-wide constant values for paper sizes, pen types, and other config.
class AppConstants {
  AppConstants._();

  // App Info
  static const String appName = 'AI-VHRS';
  static const String appTagline = 'Robotic Handwriting Service';
  static const String appVersion = '1.0.0';

  // Paper Sizes
  static const List<PaperSize> paperSizes = [
    PaperSize(id: 'a4', name: 'A4', width: 210, height: 297, unit: 'mm'),
    PaperSize(id: 'a5', name: 'A5', width: 148, height: 210, unit: 'mm'),
    PaperSize(id: 'card', name: 'Card', width: 90, height: 55, unit: 'mm'),
    PaperSize(id: 'letter', name: 'Letter', width: 216, height: 279, unit: 'mm'),
    PaperSize(id: 'custom', name: 'Custom', width: 0, height: 0, unit: 'mm'),
  ];

  // Pen Types
  static const List<PenType> penTypes = [
    PenType(id: 'ballpoint', name: 'Ballpoint Pen', strokeWidth: 0.5),
    PenType(id: 'gel', name: 'Gel Pen', strokeWidth: 0.7),
    PenType(id: 'fountain', name: 'Fountain Pen', strokeWidth: 1.0),
    PenType(id: 'marker', name: 'Marker', strokeWidth: 2.0),
    PenType(id: 'brush', name: 'Brush Pen', strokeWidth: 3.0),
  ];

  // Canvas Defaults
  static const double defaultStrokeWidth = 2.0;
  static const double minStrokeWidth = 0.5;
  static const double maxStrokeWidth = 10.0;

  // Image Processing
  static const int maxImageWidth = 2048;
  static const int maxImageHeight = 2048;
  static const double defaultContrastThreshold = 128.0;
  static const double minContrastThreshold = 0.0;
  static const double maxContrastThreshold = 255.0;

  // Request Status Flow
  static const List<String> statusFlow = [
    'awaiting_payment',
    'paid',
    'approved',
    'writing',
    'done',
  ];

  // Pagination
  static const int defaultPageSize = 20;
}

/// Represents a paper size option for projects.
class PaperSize {
  final String id;
  final String name;
  final double width;
  final double height;
  final String unit;

  const PaperSize({
    required this.id,
    required this.name,
    required this.width,
    required this.height,
    required this.unit,
  });

  String get displaySize => '$width × $height $unit';
}

/// Represents a pen type option for the robot writer.
class PenType {
  final String id;
  final String name;
  final double strokeWidth;

  const PenType({
    required this.id,
    required this.name,
    required this.strokeWidth,
  });
}
