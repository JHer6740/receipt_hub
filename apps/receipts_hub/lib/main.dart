import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';
import 'core/data/error_reporter.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Installed before the first frame, so a failure during startup is captured
  // rather than only printed to a console nobody is watching.
  errorReporter.install();
  runApp(const ProviderScope(child: ReceiptsHubApp(restoreSession: true)));
}
