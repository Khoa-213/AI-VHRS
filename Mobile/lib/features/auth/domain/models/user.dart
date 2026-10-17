import 'package:equatable/equatable.dart';

/// Account roles from the backend (`roles.code`).
class UserRole {
  UserRole._();

  static const customer = 'CUSTOMER';
  static const staff = 'STAFF';
  static const technicalStaff = 'TECHNICAL_STAFF';
  static const manager = 'MANAGER';
  static const admin = 'ADMIN';
}

/// An AI-VHRS account, as returned by the backend (`AccountOut`).
class User extends Equatable {
  /// Backend ids are integers; kept as a string so storage and routes stay simple.
  final String id;
  final String email;
  final String fullName;
  final String? phoneNumber;
  final bool phoneVerified;

  /// One of [UserRole].
  final String role;

  /// ACTIVE, LOCKED or DISABLED.
  final String status;

  /// Saved delivery addresses, raw from the API (receiver, phone, street, codes, is_default).
  final List<Map<String, dynamic>> addresses;
  final String? avatarUrl;
  final DateTime createdAt;
  final DateTime? lastLoginAt;

  const User({
    required this.id,
    required this.email,
    required this.fullName,
    this.phoneNumber,
    this.phoneVerified = false,
    this.role = UserRole.customer,
    this.status = 'ACTIVE',
    this.addresses = const [],
    this.avatarUrl,
    required this.createdAt,
    this.lastLoginAt,
  });

  bool get isCustomer => role == UserRole.customer;

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: '${json['id']}',
      email: json['email'] as String,
      fullName: json['full_name'] as String,
      phoneNumber: json['phone'] as String?,
      phoneVerified: json['phone_verified'] as bool? ?? false,
      role: json['role'] as String? ?? UserRole.customer,
      status: json['status'] as String? ?? 'ACTIVE',
      addresses: [
        for (final a in (json['addresses'] as List? ?? const []))
          if (a is Map) Map<String, dynamic>.from(a),
      ],
      avatarUrl: json['avatar_url'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String),
      lastLoginAt: json['last_login_at'] != null ? DateTime.parse(json['last_login_at'] as String) : null,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'email': email,
      'full_name': fullName,
      'phone': phoneNumber,
      'phone_verified': phoneVerified,
      'role': role,
      'status': status,
      'addresses': addresses,
      'avatar_url': avatarUrl,
      'created_at': createdAt.toIso8601String(),
      'last_login_at': lastLoginAt?.toIso8601String(),
    };
  }

  User copyWith({String? fullName, String? phoneNumber}) {
    return User(
      id: id,
      email: email,
      fullName: fullName ?? this.fullName,
      phoneNumber: phoneNumber ?? this.phoneNumber,
      phoneVerified: phoneVerified,
      role: role,
      status: status,
      addresses: addresses,
      avatarUrl: avatarUrl,
      createdAt: createdAt,
      lastLoginAt: lastLoginAt,
    );
  }

  @override
  List<Object?> get props => [id, email, fullName, phoneNumber, phoneVerified, role, status, addresses];
}
