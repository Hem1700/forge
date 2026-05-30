class User {
  const User({
    required this.id,
    required this.email,
    required this.name,
    required this.role,
    this.avatarUrl,
    this.organization,
    this.isPlatformAdmin = false,
  });

  final String id;
  final String email;
  final String name;
  final String role;
  final String? avatarUrl;
  final String? organization;
  final bool isPlatformAdmin;

  factory User.fromJson(Map<String, dynamic> json) => User(
        id: json['id'].toString(),
        email: json['email'] as String,
        name: json['name'] as String? ?? json['email'] as String,
        role: json['role'] as String? ?? 'analyst',
        avatarUrl: json['avatar_url'] as String?,
        organization: json['org_name'] as String? ?? json['organization'] as String?,
        isPlatformAdmin: json['is_platform_admin'] as bool? ?? false,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'email': email,
        'name': name,
        'role': role,
        if (avatarUrl != null) 'avatar_url': avatarUrl,
        if (organization != null) 'organization': organization,
        'is_platform_admin': isPlatformAdmin,
      };

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
