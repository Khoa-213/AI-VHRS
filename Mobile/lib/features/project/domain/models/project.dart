import 'package:equatable/equatable.dart';

/// Represents a handwriting project in the AI-VHRS system.
class Project extends Equatable {
  final String id;
  final String name;
  final String paperSizeId;
  final String penTypeId;
  final String status;
  final String? inputMethod; // 'image_upload', 'text_font', 'canvas_draw'
  final String? thumbnailUrl;
  final double? estimatedPrice;
  final DateTime createdAt;
  final DateTime? updatedAt;

  const Project({
    required this.id,
    required this.name,
    required this.paperSizeId,
    required this.penTypeId,
    required this.status,
    this.inputMethod,
    this.thumbnailUrl,
    this.estimatedPrice,
    required this.createdAt,
    this.updatedAt,
  });

  factory Project.fromJson(Map<String, dynamic> json) {
    return Project(
      id: json['id'] as String,
      name: json['name'] as String,
      paperSizeId: json['paper_size_id'] as String,
      penTypeId: json['pen_type_id'] as String,
      status: json['status'] as String,
      inputMethod: json['input_method'] as String?,
      thumbnailUrl: json['thumbnail_url'] as String?,
      estimatedPrice: (json['estimated_price'] as num?)?.toDouble(),
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: json['updated_at'] != null
          ? DateTime.parse(json['updated_at'] as String)
          : null,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'paper_size_id': paperSizeId,
      'pen_type_id': penTypeId,
      'status': status,
      'input_method': inputMethod,
      'thumbnail_url': thumbnailUrl,
      'estimated_price': estimatedPrice,
      'created_at': createdAt.toIso8601String(),
      'updated_at': updatedAt?.toIso8601String(),
    };
  }

  @override
  List<Object?> get props => [id, name, status, createdAt];
}
