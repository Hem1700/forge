# FORGE Mobile

Flutter mobile client for the FORGE Security Platform.

## Requirements

- Flutter SDK ≥ 3.10
- Dart SDK ≥ 3.10
- iOS: Xcode 15+ / Android: API 21+

## Getting started

```bash
flutter pub get
flutter run
```

For a specific device:

```bash
flutter run -d ios        # iOS Simulator
flutter run -d android    # Android Emulator
```

## Structure

```
lib/
  main.dart         # Entry point
  features/         # Feature modules (auth, scan, reports …)
  core/             # Shared services, routing, theme
```

The backend API is the same FastAPI service used by the web frontend (`backend/`). Configure the base URL in `lib/core/config.dart`.
