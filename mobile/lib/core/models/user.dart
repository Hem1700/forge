class User {
  const User({
    required this.id,
    required this.email,
    required this.name,
    required this.role,
    this.avatarUrl,
    this.organization,
    this.isPlatformAdmin = false,
    this.position,
  });

  final String id;
  final String email;
  final String name;
  final String role;
  final String? avatarUrl;
  final String? organization;
  final bool isPlatformAdmin;
  final String? position;

  factory User.fromJson(Map<String, dynamic> json) => User(
        id: json['id'].toString(),
        email: json['email'] as String,
        name: json['name'] as String? ?? json['email'] as String,
        role: json['role'] as String? ?? 'analyst',
        avatarUrl: json['avatar_url'] as String?,
        organization: json['org_name'] as String? ?? json['organization'] as String?,
        isPlatformAdmin: json['is_platform_admin'] as bool? ?? false,
        position: json['position'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'email': email,
        'name': name,
        'role': role,
        if (avatarUrl != null) 'avatar_url': avatarUrl,
        if (organization != null) 'organization': organization,
        'is_platform_admin': isPlatformAdmin,
        if (position != null) 'position': position,
      };

  User copyWith({String? email, String? position}) => User(
        id: id,
        email: email ?? this.email,
        name: email ?? name,
        role: role,
        avatarUrl: avatarUrl,
        organization: organization,
        isPlatformAdmin: isPlatformAdmin,
        position: position ?? this.position,
      );

  bool get isAdmin => role == 'admin' || role == 'super_admin';
  bool get isManager => role == 'manager' || isAdmin;

  String get initials {
    final parts = name.trim().split(' ');
    if (parts.length >= 2) {
      return '${parts.first[0]}${parts.last[0]}'.toUpperCase();
    }
    return name.isNotEmpty ? name[0].toUpperCase() : email[0].toUpperCase();
  }
}
