import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/design/app_components.dart';
import '../../core/design/app_theme.dart';
import '../../core/state/app_state.dart';
import 'upload_flow.dart';

final _torchEnabledProvider = StateProvider.autoDispose<bool>((ref) => false);

/// Stage names to show before the service has reported its own.
///
/// These are labels for a real pipeline, not a script: the timer that used to
/// advance them on its own — and then open a fixed sample receipt — is gone.
const _processingStages = <String>[
  'Sending photos',
  'Finding receipt sections',
  'Reading merchant and totals',
  'Checking the numbers',
  'Preparing review',
];

class CaptureScreen extends ConsumerStatefulWidget {
  const CaptureScreen({super.key});

  @override
  ConsumerState<CaptureScreen> createState() => _CaptureScreenState();
}

class _CaptureScreenState extends ConsumerState<CaptureScreen>
    with WidgetsBindingObserver {
  final ImagePicker _imagePicker = ImagePicker();
  CameraController? _cameraController;
  CameraDescription? _cameraDescription;
  bool _initialisingCamera = true;
  String? _cameraMessage;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_initialiseCamera());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_cameraController?.dispose());
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final controller = _cameraController;
    if (controller == null || !controller.value.isInitialized) return;
    if (state == AppLifecycleState.inactive) {
      unawaited(controller.dispose());
      _cameraController = null;
    } else if (state == AppLifecycleState.resumed) {
      unawaited(_initialiseCamera(description: _cameraDescription));
    }
  }

  Future<void> _initialiseCamera({CameraDescription? description}) async {
    if (mounted) {
      setState(() {
        _initialisingCamera = true;
        _cameraMessage = null;
      });
    }
    try {
      final cameras = description == null
          ? await availableCameras()
          : <CameraDescription>[description];
      if (cameras.isEmpty) {
        if (mounted) {
          setState(() {
            _initialisingCamera = false;
            _cameraMessage = 'No camera was found. Gallery import still works.';
          });
        }
        return;
      }
      final selected = cameras.firstWhere(
        (camera) => camera.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );
      final previous = _cameraController;
      final controller = CameraController(
        selected,
        ResolutionPreset.high,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.jpeg,
      );
      _cameraController = controller;
      _cameraDescription = selected;
      await previous?.dispose();
      await controller.initialize();
      if (!mounted) {
        await controller.dispose();
        return;
      }
      ref.read(appControllerProvider.notifier).setCameraDenied(false);
      setState(() => _initialisingCamera = false);
    } on MissingPluginException {
      // Widget tests and desktop previews use the deterministic viewfinder.
      if (mounted) setState(() => _initialisingCamera = false);
    } on CameraException catch (error) {
      final denied =
          error.code == 'CameraAccessDenied' ||
          error.code == 'CameraAccessDeniedWithoutPrompt' ||
          error.code == 'CameraAccessRestricted';
      if (denied) {
        ref.read(appControllerProvider.notifier).setCameraDenied(true);
      }
      if (mounted) {
        setState(() {
          _initialisingCamera = false;
          _cameraMessage = denied
              ? null
              : 'The camera could not start. Gallery import still works.';
        });
      }
    } on Object {
      if (mounted) {
        setState(() {
          _initialisingCamera = false;
          _cameraMessage =
              'The camera could not start. Gallery import still works.';
        });
      }
    }
  }

  Future<void> _takePhoto() async {
    final appState = ref.read(appControllerProvider);
    if (appState.capturePages >= appState.maxCapturePages) {
      showOutcomeToast(
        context,
        'A receipt can have up to ${appState.maxCapturePages} photos',
        hasNavigation: false,
      );
      return;
    }
    final controller = _cameraController;
    // Without a camera there is no photo. Queueing a placeholder page here is
    // what used to send an unusable receipt into processing.
    if (controller == null || !controller.value.isInitialized) {
      showOutcomeToast(
        context,
        'The camera is not ready. Import from your gallery instead.',
        hasNavigation: false,
      );
      return;
    }
    try {
      final image = await controller.takePicture();
      ref.read(appControllerProvider.notifier).addCapturePage(image.path);
    } on CameraException {
      if (mounted) {
        showOutcomeToast(
          context,
          'Could not take this photo. Try again.',
          hasNavigation: false,
        );
      }
    }
  }

  Future<void> _importFromGallery() async {
    final appState = ref.read(appControllerProvider);
    final remaining = appState.maxCapturePages - appState.capturePages;
    if (remaining <= 0) {
      showOutcomeToast(
        context,
        'A receipt can have up to ${appState.maxCapturePages} photos',
        hasNavigation: false,
      );
      return;
    }
    try {
      final images = await _imagePicker.pickMultiImage(
        limit: remaining,
        imageQuality: 92,
        requestFullMetadata: false,
      );
      if (images.isEmpty || !mounted) return;
      // Imported pages join the tray like camera pages do. The person still
      // confirms the page order before anything is sent.
      ref
          .read(appControllerProvider.notifier)
          .addCapturePages(images.map((image) => image.path));
    } on MissingPluginException {
      if (mounted) {
        showOutcomeToast(
          context,
          'Gallery import is unavailable on this device.',
          hasNavigation: false,
        );
      }
    } on PlatformException {
      if (mounted) {
        showOutcomeToast(
          context,
          'Gallery access is unavailable',
          hasNavigation: false,
        );
      }
    }
  }

  Future<void> _toggleTorch(bool enabled) async {
    final next = !enabled;
    final controller = _cameraController;
    if (controller != null && controller.value.isInitialized) {
      try {
        await controller.setFlashMode(next ? FlashMode.torch : FlashMode.off);
      } on CameraException {
        if (mounted) {
          showOutcomeToast(
            context,
            'Torch is unavailable on this camera',
            hasNavigation: false,
          );
        }
        return;
      }
    }
    ref.read(_torchEnabledProvider.notifier).state = next;
  }

  @override
  Widget build(BuildContext context) {
    final capture = ref.watch(
      appControllerProvider.select(
        (state) => (pages: state.capturePages, denied: state.cameraDenied),
      ),
    );
    final torchEnabled = ref.watch(_torchEnabledProvider);
    const cameraInk = Color(0xFFF2EAD9);
    const cameraBackground = Color(0xFF221D16);

    void beginProcessing() {
      if (capture.pages == 0) return;
      context.go('/processing');
    }

    return Scaffold(
      backgroundColor: cameraBackground,
      body: SafeArea(
        child: Column(
          children: <Widget>[
            SizedBox(
              height: 56,
              child: Row(
                children: <Widget>[
                  IconButton(
                    tooltip: 'Cancel scan',
                    onPressed: () {
                      ref.read(appControllerProvider.notifier).clearCapture();
                      context.go('/home');
                    },
                    color: cameraInk,
                    icon: const Icon(Icons.close_rounded),
                  ),
                  const Expanded(
                    child: Text(
                      'Scan receipt',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: cameraInk,
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  SizedBox(
                    width: 76,
                    child: capture.pages == 0
                        ? const SizedBox.shrink()
                        : TextButton(
                            onPressed: beginProcessing,
                            style: TextButton.styleFrom(
                              foregroundColor: cameraInk,
                            ),
                            child: Text(
                              capture.pages > 1
                                  ? 'Read ${capture.pages}'
                                  : 'Read',
                            ),
                          ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: capture.denied
                  ? _CameraDeniedPanel(
                      onOpenSettings: () {
                        ref
                            .read(appControllerProvider.notifier)
                            .setCameraDenied(false);
                        unawaited(_initialiseCamera());
                      },
                      onImport: _importFromGallery,
                    )
                  : Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: Stack(
                        alignment: Alignment.center,
                        children: <Widget>[
                          Positioned.fill(
                            child:
                                _cameraController?.value.isInitialized ?? false
                                ? _LiveViewfinder(
                                    controller: _cameraController!,
                                  )
                                : _Viewfinder(
                                    loading: _initialisingCamera,
                                    message: _cameraMessage,
                                  ),
                          ),
                          if (capture.pages > 0)
                            Positioned(
                              top: 16,
                              child: Semantics(
                                liveRegion: true,
                                label: '${capture.pages} pages captured',
                                child: Container(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 14,
                                    vertical: 7,
                                  ),
                                  decoration: BoxDecoration(
                                    color: cameraBackground.withValues(
                                      alpha: .82,
                                    ),
                                    borderRadius: BorderRadius.circular(
                                      AppRadii.chip,
                                    ),
                                    border: Border.all(
                                      color: cameraInk.withValues(alpha: .24),
                                    ),
                                  ),
                                  child: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: <Widget>[
                                      Text(
                                        'Page ${capture.pages}',
                                        style: AppText.captionS.copyWith(
                                          color: cameraInk,
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                      const SizedBox(width: 8),
                                      InkWell(
                                        onTap: ref
                                            .read(
                                              appControllerProvider.notifier,
                                            )
                                            .clearCapture,
                                        borderRadius: BorderRadius.circular(
                                          AppRadii.chip,
                                        ),
                                        child: Padding(
                                          padding: const EdgeInsets.symmetric(
                                            horizontal: 4,
                                            vertical: 3,
                                          ),
                                          child: Text(
                                            'Clear',
                                            style: AppText.captionS.copyWith(
                                              color: cameraInk.withValues(
                                                alpha: .78,
                                              ),
                                              decoration:
                                                  TextDecoration.underline,
                                              decorationColor: cameraInk,
                                            ),
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            ),
                        ],
                      ),
                    ),
            ),
            if (!capture.denied)
              Padding(
                padding: const EdgeInsets.fromLTRB(28, 20, 28, 24),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: <Widget>[
                    _CameraControl(
                      tooltip: 'Import from gallery',
                      icon: Icons.photo_library_outlined,
                      onPressed: _importFromGallery,
                    ),
                    Semantics(
                      button: true,
                      label: 'Take photo',
                      child: InkWell(
                        customBorder: const CircleBorder(),
                        onTap: _takePhoto,
                        child: Container(
                          width: 72,
                          height: 72,
                          decoration: BoxDecoration(
                            color: const Color(0xFF92A273),
                            shape: BoxShape.circle,
                            border: Border.all(color: cameraInk, width: 4),
                          ),
                        ),
                      ),
                    ),
                    _CameraControl(
                      tooltip: torchEnabled
                          ? 'Turn torch off'
                          : 'Turn torch on',
                      icon: torchEnabled
                          ? Icons.flashlight_on_rounded
                          : Icons.flashlight_off_rounded,
                      selected: torchEnabled,
                      onPressed: () => _toggleTorch(torchEnabled),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class ProcessingScreen extends ConsumerStatefulWidget {
  const ProcessingScreen({this.showFailure = false, super.key});

  /// Forces the failure branch for deterministic widget previews.
  final bool showFailure;

  @override
  ConsumerState<ProcessingScreen> createState() => _ProcessingScreenState();
}

class _ProcessingScreenState extends ConsumerState<ProcessingScreen> {
  bool _started = false;

  @override
  void initState() {
    super.initState();
    // Send the captured pages as soon as this screen takes over, so the upload
    // starts while the person is still reading the first stage label.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _started || widget.showFailure) return;
      final app = ref.read(appControllerProvider);
      if (!app.connected || app.capturePagePaths.isEmpty) return;
      _started = true;
      ref.read(captureFlowProvider.notifier).start(app.capturePagePaths);
    });
  }

  @override
  Widget build(BuildContext context) {
    if (widget.showFailure) {
      return const _ProcessingFailure();
    }

    final app = ref.watch(appControllerProvider);

    // Nothing to process. Reachable by a deep link or a restart mid-capture;
    // it used to run a scripted progress bar and open a sample receipt.
    if (!app.connected) {
      return Scaffold(
        body: SafeArea(
          child: AppStatePanel(
            key: const Key('processing-disconnected'),
            icon: Icons.cloud_off_outlined,
            title: 'Cannot read this receipt yet',
            message:
                app.failureMessage ??
                'Receipts Hub is not responding. Your photos are still on '
                    'this device — try again in a moment.',
            actionLabel: 'Back to receipts',
            onAction: () => context.go('/receipts'),
          ),
        ),
      );
    }
    if (app.capturePagePaths.isEmpty &&
        ref.read(captureFlowProvider).batchId == null) {
      return Scaffold(
        body: SafeArea(
          child: AppStatePanel(
            key: const Key('processing-nothing-to-do'),
            icon: Icons.document_scanner_outlined,
            title: 'No photos to read',
            message: 'Take a photo of the receipt to get started.',
            actionLabel: 'Scan a receipt',
            onAction: () => context.go('/capture'),
          ),
        ),
      );
    }

    return _buildLive(context);
  }

  /// Real upload progress and the service's own reading stages.
  Widget _buildLive(BuildContext context) {
    final flow = ref.watch(captureFlowProvider);

    ref.listen<CaptureFlowState>(captureFlowProvider, (previous, next) {
      if (next.stage != CaptureFlowStage.ready) return;
      final receiptId = next.receiptId;
      final isDuplicate = next.isDuplicate;
      scheduleMicrotask(() {
        if (!context.mounted) return;
        if (receiptId == null) {
          context.go('/receipts');
          return;
        }
        // A duplicate is already in the ledger, so open it for viewing rather
        // than asking for a correction that would change nothing.
        context.go(
          isDuplicate ? '/receipts/$receiptId' : '/receipts/$receiptId/edit',
        );
      });
    });

    if (flow.stage == CaptureFlowStage.failed) {
      return _ProcessingFailure(
        message: flow.message,
        onRetry: flow.canRetry
            ? ref.read(captureFlowProvider.notifier).retry
            : null,
      );
    }

    final stages = flow.stages;
    final labels = stages.isEmpty
        ? _processingStages
        : <String>[
            for (final stage in stages)
              captureStageLabels[stage.name] ?? stage.name,
          ];
    final activeIndex = stages.indexWhere((stage) => stage.isActive);
    final doneCount = stages.where((stage) => stage.isComplete).length;

    return _ProcessingLayout(
      heading: flow.progress?.heading ?? 'Reading receipt',
      subtitle: flow.stage == CaptureFlowStage.uploading
          ? 'Sending your photos'
          : 'This usually takes a few seconds',
      progress: flow.overallFraction,
      labels: labels,
      activeIndex: activeIndex >= 0 ? activeIndex : doneCount,
      doneCount: doneCount,
    );
  }

}

class _ProcessingLayout extends StatelessWidget {
  const _ProcessingLayout({
    required this.heading,
    required this.subtitle,
    required this.progress,
    required this.labels,
    required this.activeIndex,
    required this.doneCount,
  });

  final String heading;
  final String subtitle;
  final double progress;
  final List<String> labels;
  final int activeIndex;
  final int doneCount;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.gutter),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              const SizedBox(height: 16),
              Row(
                children: <Widget>[
                  Container(
                    width: 74,
                    height: 100,
                    padding: const EdgeInsets.all(9),
                    decoration: BoxDecoration(
                      color: context.appColors.surface,
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: context.appColors.divider),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: List<Widget>.generate(
                        7,
                        (index) => Expanded(
                          child: Align(
                            alignment: Alignment.centerLeft,
                            child: FractionallySizedBox(
                              widthFactor: index.isEven ? .88 : .64,
                              child: Container(
                                height: 2,
                                color: index <= doneCount + 1
                                    ? context.appColors.textSecondary
                                    : context.appColors.divider,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 18),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(heading, style: AppText.screenTitle),
                        const SizedBox(height: 4),
                        Text(
                          subtitle,
                          style: AppText.caption.copyWith(
                            color: context.appColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 28),
              Semantics(
                label:
                    'Receipt processing ${((progress * 100).round())} percent complete',
                child: LinearProgressIndicator(
                  value: progress,
                  minHeight: 6,
                  borderRadius: BorderRadius.circular(3),
                ),
              ),
              const SizedBox(height: 24),
              for (var index = 0; index < labels.length; index += 1)
                _ProcessingStageRow(
                  key: ValueKey<String>(labels[index]),
                  label: labels[index],
                  isDone: index < doneCount,
                  isActive: index == activeIndex,
                ),
              const Spacer(),
              // Reading continues on the service, so leaving does not lose the
              // receipt — it will be waiting in Receipts.
              OutlinedButton(
                onPressed: () => context.go('/receipts'),
                child: const Text('Leave this running'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ProcessingFailure extends ConsumerWidget {
  const _ProcessingFailure({this.message, this.onRetry});

  /// What the service said went wrong, when it said anything useful.
  final String? message;

  /// Re-reads the photos already uploaded. Null when there is nothing to
  /// retry, in which case manual entry is the way forward.
  final Future<void> Function()? onRetry;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final receiptId = ref.watch(
      captureFlowProvider.select((flow) => flow.receiptId),
    );
    final retry = onRetry;
    return Scaffold(
      body: SafeArea(
        child: AppStatePanel(
          icon: Icons.document_scanner_outlined,
          title: 'Could not read this receipt',
          message:
              message ??
              'The photos arrived but could not be read. Try reading them '
                  'again, or enter the details yourself.',
          // Retry re-reads the photos already uploaded. With no batch to
          // retry there is nothing to repeat, so the only way forward is
          // manual entry in the footer below.
          actionLabel: retry == null ? null : 'Try reading again',
          onAction: retry,
        ),
      ),
      bottomNavigationBar: SafeArea(
        minimum: const EdgeInsets.fromLTRB(24, 0, 24, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            // Manual entry continues against the photos already uploaded, so
            // it only appears when the service has a draft to correct. It used
            // to fall back to a fixed sample receipt when it did not.
            if (receiptId != null) ...<Widget>[
              OutlinedButton(
                onPressed: () =>
                    context.go('/receipts/$receiptId/edit?manual=true'),
                child: const Text('Enter the details myself'),
              ),
              const SizedBox(height: 8),
            ],
            TextButton(
              onPressed: () => context.go('/receipts'),
              child: const Text('Back to receipts'),
            ),
          ],
        ),
      ),
    );
  }
}

class _ProcessingStageRow extends StatelessWidget {
  const _ProcessingStageRow({
    required this.label,
    required this.isDone,
    required this.isActive,
    super.key,
  });

  final String label;
  final bool isDone;
  final bool isActive;

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    final activeColor = isDone || isActive ? colors.primary : colors.divider;
    return Semantics(
      label:
          '$label, ${isDone
              ? 'complete'
              : isActive
              ? 'working'
              : 'pending'}',
      child: SizedBox(
        height: 48,
        child: Row(
          children: <Widget>[
            SizedBox(
              width: 24,
              child: isDone
                  ? Icon(Icons.check_rounded, size: 19, color: activeColor)
                  : Center(
                      child: Container(
                        width: isActive ? 9 : 6,
                        height: isActive ? 9 : 6,
                        decoration: BoxDecoration(
                          color: activeColor,
                          shape: BoxShape.circle,
                        ),
                      ),
                    ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                label,
                style: AppText.body.copyWith(
                  color: isDone || isActive
                      ? colors.textPrimary
                      : colors.textSecondary,
                  fontWeight: isActive ? FontWeight.w600 : FontWeight.w400,
                ),
              ),
            ),
            if (isActive)
              Text(
                'working',
                style: AppText.captionS.copyWith(color: colors.textSecondary),
              ),
          ],
        ),
      ),
    );
  }
}

class _CameraDeniedPanel extends StatelessWidget {
  const _CameraDeniedPanel({
    required this.onOpenSettings,
    required this.onImport,
  });

  final VoidCallback onOpenSettings;
  final VoidCallback onImport;

  @override
  Widget build(BuildContext context) {
    const ink = Color(0xFFF2EAD9);
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          const Icon(Icons.no_photography_outlined, color: ink, size: 42),
          const SizedBox(height: 20),
          const Text(
            'Camera access is off',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: ink,
              fontFamily: 'Display',
              fontSize: 22,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 10),
          Text(
            'Allow the camera to photograph receipts, or import photos you '
            'have already taken.',
            textAlign: TextAlign.center,
            style: AppText.bodyS.copyWith(color: ink.withValues(alpha: .72)),
          ),
          const SizedBox(height: 24),
          FilledButton(
            onPressed: onOpenSettings,
            style: FilledButton.styleFrom(
              backgroundColor: const Color(0xFF92A273),
              foregroundColor: const Color(0xFF221D16),
            ),
            child: const Text('Open settings'),
          ),
          const SizedBox(height: 10),
          OutlinedButton(
            onPressed: onImport,
            style: OutlinedButton.styleFrom(
              foregroundColor: ink,
              side: BorderSide(color: ink.withValues(alpha: .4)),
            ),
            child: const Text('Import from gallery'),
          ),
        ],
      ),
    );
  }
}

class _CameraControl extends StatelessWidget {
  const _CameraControl({
    required this.tooltip,
    required this.icon,
    required this.onPressed,
    this.selected = false,
  });

  final String tooltip;
  final IconData icon;
  final VoidCallback onPressed;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    const ink = Color(0xFFF2EAD9);
    return IconButton(
      tooltip: tooltip,
      onPressed: onPressed,
      style: IconButton.styleFrom(
        minimumSize: const Size(48, 48),
        foregroundColor: ink,
        backgroundColor: selected ? ink.withValues(alpha: .18) : null,
      ),
      icon: Icon(icon, size: 24),
    );
  }
}

class _LiveViewfinder extends StatelessWidget {
  const _LiveViewfinder({required this.controller});

  final CameraController controller;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: ColoredBox(
        color: const Color(0xFF2B251C),
        child: Stack(
          fit: StackFit.expand,
          children: <Widget>[
            Center(child: CameraPreview(controller)),
            const CustomPaint(painter: _ReceiptGuidePainter()),
          ],
        ),
      ),
    );
  }
}

/// The viewfinder before the camera hands over a preview.
///
/// It shows the framing guides and nothing else. It used to draw a fake
/// receipt — `FERNWAY GROCER · TOTAL $86.40` — which on a slow camera looked
/// exactly like a receipt the app had already read.
class _Viewfinder extends StatelessWidget {
  const _Viewfinder({this.loading = false, this.message});

  final bool loading;
  final String? message;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: DecoratedBox(
        decoration: const BoxDecoration(color: Color(0xFF2B251C)),
        child: Stack(
          alignment: Alignment.center,
          children: <Widget>[
            Positioned.fill(
              child: CustomPaint(painter: _ReceiptGuidePainter()),
            ),
            // Words rather than a spinner: an indeterminate indicator here is
            // motion a person has to watch to learn nothing, and the interface
            // system asks for state to be readable instead.
            Positioned(
              left: 20,
              right: 20,
              bottom: 18,
              child: Semantics(
                liveRegion: true,
                child: Text(
                  loading
                      ? 'Starting the camera'
                      : message ?? 'Fit the whole receipt inside the guides',
                  textAlign: TextAlign.center,
                  style: AppText.captionS.copyWith(
                    color: const Color(
                      0xFFF2EAD9,
                    ).withValues(alpha: message == null && !loading ? .72 : 1),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ReceiptGuidePainter extends CustomPainter {
  const _ReceiptGuidePainter();

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFFB7C991)
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;
    final rect = Rect.fromLTRB(30, 24, size.width - 30, size.height - 24);
    const length = 34.0;
    final path = Path()
      ..moveTo(rect.left + length, rect.top)
      ..lineTo(rect.left, rect.top)
      ..lineTo(rect.left, rect.top + length)
      ..moveTo(rect.right - length, rect.top)
      ..lineTo(rect.right, rect.top)
      ..lineTo(rect.right, rect.top + length)
      ..moveTo(rect.left, rect.bottom - length)
      ..lineTo(rect.left, rect.bottom)
      ..lineTo(rect.left + length, rect.bottom)
      ..moveTo(rect.right - length, rect.bottom)
      ..lineTo(rect.right, rect.bottom)
      ..lineTo(rect.right, rect.bottom - length);
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
