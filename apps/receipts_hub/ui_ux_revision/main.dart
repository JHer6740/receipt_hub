import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:receipts_hub/app.dart';
import 'package:receipts_hub/core/routing/app_router.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(
    ProviderScope(
      child: ReceiptsHubApp(
        restoreSession: false,
        router: createAppRouter(initialLocation: '/household/join'),
      ),
    ),
  );
}
