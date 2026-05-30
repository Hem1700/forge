import 'package:flutter/material.dart';

// FORGE Design System
class ForgeColors {
  static const background = Color(0xFF070910);
  static const surface = Color(0xFF0d0f16);
  static const surface2 = Color(0xFF121520);
  static const border = Color(0xFF1a1d28);
  static const accent = Color(0xFF06B6D4);
  static const accentMid = Color(0xFF0891B2);
  static const accentDim = Color(0xFF0e3a42);
  static const accentBg = Color(0xFF010c0f);
  static const textPrimary = Color(0xFFe8eaf0);
  static const textSecondary = Color(0xFF8890a8);
  static const textTertiary = Color(0xFF444a60);
  static const error = Color(0xFFCF6679);
  static const success = Color(0xFF4CAF82);
  static const warning = Color(0xFFE5A832);
}

class AppTheme {
  static ThemeData get light {
    const colorScheme = ColorScheme(
      brightness: Brightness.light,
      primary: Color(0xFF0891B2),
      onPrimary: Colors.white,
      primaryContainer: Color(0xFFCCF2F8),
      onPrimaryContainer: Color(0xFF00414F),
      secondary: Color(0xFF06B6D4),
      onSecondary: Colors.white,
      secondaryContainer: Color(0xFFD4F4FA),
      onSecondaryContainer: Color(0xFF0D0F16),
      tertiary: Color(0xFF4A5273),
      onTertiary: Colors.white,
      tertiaryContainer: Color(0xFFEEF0F8),
      onTertiaryContainer: Color(0xFF0D0F16),
      error: ForgeColors.error,
      onError: Colors.white,
      errorContainer: Color(0xFFFFDADE),
      onErrorContainer: Color(0xFF410002),
      surface: Colors.white,
      onSurface: Color(0xFF0D0F16),
      surfaceContainerHighest: Color(0xFFEEF0F8),
      onSurfaceVariant: Color(0xFF4A5273),
      outline: Color(0xFFDDE0ED),
      outlineVariant: Color(0xFF8890A8),
      shadow: Colors.black,
      scrim: Colors.black54,
      inverseSurface: Color(0xFF0D0F16),
      onInverseSurface: Color(0xFFE8EAF0),
      inversePrimary: ForgeColors.accent,
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: const Color(0xFFF4F6FC),
      canvasColor: const Color(0xFFF4F6FC),

      appBarTheme: const AppBarTheme(
        backgroundColor: Color(0xFFF4F6FC),
        foregroundColor: Color(0xFF0D0F16),
        elevation: 0,
        scrolledUnderElevation: 0,
        surfaceTintColor: Colors.transparent,
        titleTextStyle: TextStyle(
          color: Color(0xFF0D0F16),
          fontSize: 17,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.3,
        ),
      ),

      cardTheme: CardThemeData(
        color: Colors.white,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: const BorderSide(color: Color(0xFFDDE0ED), width: 1),
        ),
        margin: EdgeInsets.zero,
      ),

      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        hintStyle: const TextStyle(color: Color(0xFF8890A8), fontSize: 15),
        labelStyle: const TextStyle(color: Color(0xFF4A5273), fontSize: 14),
        floatingLabelStyle: const TextStyle(color: Color(0xFF0891B2), fontSize: 12),
        prefixIconColor: const Color(0xFF4A5273),
        suffixIconColor: const Color(0xFF4A5273),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFFDDE0ED)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFFDDE0ED)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFF0891B2), width: 1.5),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: ForgeColors.error),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: ForgeColors.error, width: 1.5),
        ),
        errorStyle: const TextStyle(color: ForgeColors.error, fontSize: 12),
      ),

      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.transparent,
          foregroundColor: const Color(0xFF0891B2),
          elevation: 0,
          shadowColor: Colors.transparent,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: const BorderSide(color: Color(0xFF0891B2), width: 1.5),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          textStyle: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.3,
          ),
        ),
      ),

      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: const Color(0xFF4A5273),
          side: const BorderSide(color: Color(0xFFDDE0ED)),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w500),
        ),
      ),

      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: const Color(0xFF0891B2),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
        ),
      ),

      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: Colors.white,
        selectedItemColor: Color(0xFF0891B2),
        unselectedItemColor: Color(0xFF8890A8),
        type: BottomNavigationBarType.fixed,
        elevation: 0,
      ),

      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: Colors.white,
        indicatorColor: const Color(0xFFCCF2F8),
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return const TextStyle(color: Color(0xFF0891B2), fontSize: 11, fontWeight: FontWeight.w600);
          }
          return const TextStyle(color: Color(0xFF8890A8), fontSize: 11);
        }),
        iconTheme: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return const IconThemeData(color: Color(0xFF0891B2), size: 22);
          }
          return const IconThemeData(color: Color(0xFF8890A8), size: 22);
        }),
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      ),

      dividerTheme: const DividerThemeData(
        color: Color(0xFFDDE0ED),
        thickness: 1,
        space: 1,
      ),

      chipTheme: ChipThemeData(
        backgroundColor: const Color(0xFFEEF0F8),
        selectedColor: const Color(0xFFCCF2F8),
        labelStyle: const TextStyle(color: Color(0xFF4A5273), fontSize: 13),
        side: const BorderSide(color: Color(0xFFDDE0ED)),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      ),

      snackBarTheme: SnackBarThemeData(
        backgroundColor: const Color(0xFF0D0F16),
        contentTextStyle: const TextStyle(color: Color(0xFFE8EAF0)),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        behavior: SnackBarBehavior.floating,
      ),

      dialogTheme: DialogThemeData(
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: const BorderSide(color: Color(0xFFDDE0ED)),
        ),
        titleTextStyle: const TextStyle(
          color: Color(0xFF0D0F16),
          fontSize: 17,
          fontWeight: FontWeight.w600,
        ),
        contentTextStyle: const TextStyle(color: Color(0xFF4A5273), fontSize: 14),
      ),

      listTileTheme: const ListTileThemeData(
        tileColor: Colors.transparent,
        selectedTileColor: Color(0xFFCCF2F8),
        selectedColor: Color(0xFF0891B2),
        iconColor: Color(0xFF4A5273),
        textColor: Color(0xFF0D0F16),
        contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      ),

      textTheme: const TextTheme(
        displayLarge: TextStyle(color: Color(0xFF0D0F16), fontWeight: FontWeight.w700, letterSpacing: -1),
        displayMedium: TextStyle(color: Color(0xFF0D0F16), fontWeight: FontWeight.w700, letterSpacing: -0.5),
        displaySmall: TextStyle(color: Color(0xFF0D0F16), fontWeight: FontWeight.w600),
        headlineLarge: TextStyle(color: Color(0xFF0D0F16), fontWeight: FontWeight.w600, letterSpacing: -0.5),
        headlineMedium: TextStyle(color: Color(0xFF0D0F16), fontWeight: FontWeight.w600),
        headlineSmall: TextStyle(color: Color(0xFF0D0F16), fontWeight: FontWeight.w600),
        titleLarge: TextStyle(color: Color(0xFF0D0F16), fontWeight: FontWeight.w600, fontSize: 17, letterSpacing: -0.3),
        titleMedium: TextStyle(color: Color(0xFF0D0F16), fontWeight: FontWeight.w500, fontSize: 15),
        titleSmall: TextStyle(color: Color(0xFF4A5273), fontWeight: FontWeight.w500, fontSize: 13),
        bodyLarge: TextStyle(color: Color(0xFF0D0F16), fontSize: 15),
        bodyMedium: TextStyle(color: Color(0xFF4A5273), fontSize: 14),
        bodySmall: TextStyle(color: Color(0xFF8890A8), fontSize: 12),
        labelLarge: TextStyle(color: Color(0xFF0D0F16), fontWeight: FontWeight.w600, fontSize: 14),
        labelMedium: TextStyle(color: Color(0xFF4A5273), fontSize: 12),
        labelSmall: TextStyle(color: Color(0xFF8890A8), fontSize: 11),
      ),
    );
  }

  static ThemeData get dark {
    const colorScheme = ColorScheme(
      brightness: Brightness.dark,
      primary: ForgeColors.accent,
      onPrimary: ForgeColors.background,
      primaryContainer: ForgeColors.accentDim,
      onPrimaryContainer: ForgeColors.accent,
      secondary: ForgeColors.accentMid,
      onSecondary: ForgeColors.background,
      secondaryContainer: ForgeColors.accentDim,
      onSecondaryContainer: ForgeColors.textPrimary,
      tertiary: ForgeColors.textSecondary,
      onTertiary: ForgeColors.background,
      tertiaryContainer: ForgeColors.surface2,
      onTertiaryContainer: ForgeColors.textPrimary,
      error: ForgeColors.error,
      onError: ForgeColors.background,
      errorContainer: Color(0xFF4D1F27),
      onErrorContainer: ForgeColors.error,
      surface: ForgeColors.surface,
      onSurface: ForgeColors.textPrimary,
      surfaceContainerHighest: ForgeColors.surface2,
      onSurfaceVariant: ForgeColors.textSecondary,
      outline: ForgeColors.border,
      outlineVariant: ForgeColors.textTertiary,
      shadow: Colors.black,
      scrim: Colors.black87,
      inverseSurface: ForgeColors.textPrimary,
      onInverseSurface: ForgeColors.background,
      inversePrimary: ForgeColors.accentMid,
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: ForgeColors.background,
      canvasColor: ForgeColors.background,

      // App bar
      appBarTheme: const AppBarTheme(
        backgroundColor: ForgeColors.background,
        foregroundColor: ForgeColors.textPrimary,
        elevation: 0,
        scrolledUnderElevation: 0,
        surfaceTintColor: Colors.transparent,
        titleTextStyle: TextStyle(
          color: ForgeColors.textPrimary,
          fontSize: 17,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.3,
        ),
      ),

      // Cards
      cardTheme: CardThemeData(
        color: ForgeColors.surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: const BorderSide(color: ForgeColors.border, width: 1),
        ),
        margin: EdgeInsets.zero,
      ),

      // Input fields
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: ForgeColors.surface,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        hintStyle: const TextStyle(color: ForgeColors.textTertiary, fontSize: 15),
        labelStyle: const TextStyle(color: ForgeColors.textSecondary, fontSize: 14),
        floatingLabelStyle: const TextStyle(color: ForgeColors.accent, fontSize: 12),
        prefixIconColor: ForgeColors.textSecondary,
        suffixIconColor: ForgeColors.textSecondary,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: ForgeColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: ForgeColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: ForgeColors.accent, width: 1.5),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: ForgeColors.error),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: ForgeColors.error, width: 1.5),
        ),
        errorStyle: const TextStyle(color: ForgeColors.error, fontSize: 12),
      ),

      // Elevated buttons (primary action with glow)
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.transparent,
          foregroundColor: ForgeColors.accent,
          elevation: 0,
          shadowColor: Colors.transparent,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: const BorderSide(color: ForgeColors.accent, width: 1.5),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          textStyle: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.3,
          ),
        ),
      ),

      // Outlined buttons (ghost style)
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: ForgeColors.textSecondary,
          side: const BorderSide(color: ForgeColors.border),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w500),
        ),
      ),

      // Text buttons
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: ForgeColors.accent,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
        ),
      ),

      // Bottom navigation
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: ForgeColors.surface,
        selectedItemColor: ForgeColors.accent,
        unselectedItemColor: ForgeColors.textTertiary,
        type: BottomNavigationBarType.fixed,
        elevation: 0,
      ),

      // Navigation bar (Material 3)
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: ForgeColors.surface,
        indicatorColor: ForgeColors.accentDim,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return const TextStyle(color: ForgeColors.accent, fontSize: 11, fontWeight: FontWeight.w600);
          }
          return const TextStyle(color: ForgeColors.textTertiary, fontSize: 11);
        }),
        iconTheme: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return const IconThemeData(color: ForgeColors.accent, size: 22);
          }
          return const IconThemeData(color: ForgeColors.textTertiary, size: 22);
        }),
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      ),

      // Dividers
      dividerTheme: const DividerThemeData(
        color: ForgeColors.border,
        thickness: 1,
        space: 1,
      ),

      // Chips
      chipTheme: ChipThemeData(
        backgroundColor: ForgeColors.surface2,
        selectedColor: ForgeColors.accentDim,
        labelStyle: const TextStyle(color: ForgeColors.textSecondary, fontSize: 13),
        side: const BorderSide(color: ForgeColors.border),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      ),

      // Snack bars
      snackBarTheme: SnackBarThemeData(
        backgroundColor: ForgeColors.surface2,
        contentTextStyle: const TextStyle(color: ForgeColors.textPrimary),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        behavior: SnackBarBehavior.floating,
      ),

      // Dialog
      dialogTheme: DialogThemeData(
        backgroundColor: ForgeColors.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: const BorderSide(color: ForgeColors.border),
        ),
        titleTextStyle: const TextStyle(
          color: ForgeColors.textPrimary,
          fontSize: 17,
          fontWeight: FontWeight.w600,
        ),
        contentTextStyle: const TextStyle(color: ForgeColors.textSecondary, fontSize: 14),
      ),

      // List tiles
      listTileTheme: const ListTileThemeData(
        tileColor: Colors.transparent,
        selectedTileColor: ForgeColors.accentDim,
        selectedColor: ForgeColors.accent,
        iconColor: ForgeColors.textSecondary,
        textColor: ForgeColors.textPrimary,
        contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      ),

      // Text theme
      textTheme: const TextTheme(
        displayLarge: TextStyle(color: ForgeColors.textPrimary, fontWeight: FontWeight.w700, letterSpacing: -1),
        displayMedium: TextStyle(color: ForgeColors.textPrimary, fontWeight: FontWeight.w700, letterSpacing: -0.5),
        displaySmall: TextStyle(color: ForgeColors.textPrimary, fontWeight: FontWeight.w600),
        headlineLarge: TextStyle(color: ForgeColors.textPrimary, fontWeight: FontWeight.w600, letterSpacing: -0.5),
        headlineMedium: TextStyle(color: ForgeColors.textPrimary, fontWeight: FontWeight.w600),
        headlineSmall: TextStyle(color: ForgeColors.textPrimary, fontWeight: FontWeight.w600),
        titleLarge: TextStyle(color: ForgeColors.textPrimary, fontWeight: FontWeight.w600, fontSize: 17, letterSpacing: -0.3),
        titleMedium: TextStyle(color: ForgeColors.textPrimary, fontWeight: FontWeight.w500, fontSize: 15),
        titleSmall: TextStyle(color: ForgeColors.textSecondary, fontWeight: FontWeight.w500, fontSize: 13),
        bodyLarge: TextStyle(color: ForgeColors.textPrimary, fontSize: 15),
        bodyMedium: TextStyle(color: ForgeColors.textSecondary, fontSize: 14),
        bodySmall: TextStyle(color: ForgeColors.textTertiary, fontSize: 12),
        labelLarge: TextStyle(color: ForgeColors.textPrimary, fontWeight: FontWeight.w600, fontSize: 14),
        labelMedium: TextStyle(color: ForgeColors.textSecondary, fontSize: 12),
        labelSmall: TextStyle(color: ForgeColors.textTertiary, fontSize: 11),
      ),
    );
  }
}

// Widget helper for the cyan glow effect on primary buttons
class ForgeGlowButton extends StatelessWidget {
  const ForgeGlowButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.isLoading = false,
    this.fullWidth = true,
    this.icon,
  });

  final String label;
  final VoidCallback? onPressed;
  final bool isLoading;
  final bool fullWidth;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final button = Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        boxShadow: onPressed != null
            ? [
                BoxShadow(
                  color: ForgeColors.accent.withValues(alpha: 0.25),
                  blurRadius: 20,
                  spreadRadius: 0,
                  offset: const Offset(0, 4),
                ),
                BoxShadow(
                  color: ForgeColors.accent.withValues(alpha: 0.1),
                  blurRadius: 40,
                  spreadRadius: -4,
                ),
              ]
            : null,
      ),
      child: ElevatedButton(
        onPressed: isLoading ? null : onPressed,
        style: ElevatedButton.styleFrom(
          minimumSize: fullWidth ? const Size(double.infinity, 50) : null,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
        ),
        child: isLoading
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor: AlwaysStoppedAnimation(ForgeColors.accent),
                ),
              )
            : Row(
                mainAxisSize: fullWidth ? MainAxisSize.max : MainAxisSize.min,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  if (icon != null) ...[
                    Icon(icon, size: 18),
                    const SizedBox(width: 8),
                  ],
                  Text(label),
                ],
              ),
      ),
    );

    return button;
  }
}
