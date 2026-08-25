import 'package:flutter/material.dart';

import '../../core/design/app_components.dart';
import '../../core/design/app_theme.dart';

/// Shown while a stored session is restored.
///
/// Without this the app opened on the first-run screen every launch and a
/// returning user was asked to start over, because nothing read the session
/// before the router picked a location.
class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Semantics(
        label: 'Opening Receipts Hub',
        liveRegion: true,
        child: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: <Widget>[
              const ReceiptAppMark(size: 64),
              const SizedBox(height: 20),
              Text(
                'Receipts Hub',
                style: AppText.displayS.copyWith(
                  color: context.appColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
