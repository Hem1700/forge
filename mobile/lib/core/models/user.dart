class User {
  const User({
    required this.id,
    required this.email,
    required this.name,
    required this.role,
    this.avatarUrl,
    this.organization,
  });

  final String id;
  final String email;
  final String name;
  final String role;
  final String? avatarUrl;
  final String? organization;

  factory User.fromJson(Map<String, dynamic> json) => User(
        id: json['id'].toString(),
        email: json['email'] as String,
        name: json['name'] as String? ?? json['email'] as String,
        role: json['role'] as String? ?? 'analyst',
        avatarUrl: json['avatar_url'] as String?,
        organization: json['org_name'] as String? ?? json['organization'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'email': email,
        'name': name,
        'role': role,
        if (avatarUrl != null) 'avatar_url': avatarUrl,
        if (organization != null) 'organization': organization,
      };

  bool get isAdmin => role == 'admin';
  bool get isManager => role == 'manager' || isAdmin;
}
