// Drives one capture through upload, host-side reading, and into review.
//
// The screen stays declarative: it renders whatever stage this controller
// reports. Everything that can go wrong on a private LAN -- a sleeping host, a
// slow upload, OCR that cannot read the photo -- is a state here rather than an
// exception a widget has to catch.

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/data/receipts_repository.dart';
import '../../core/network/api_models.dart';
import '../../core/network/mobile_api.dart';
import '../../core/state/app_state.dart';

/// The five stages the host reports, in the order a person sees them.
const captureStageLabels = <String, String>{
  'upload': 'Sending photos',
  'detect': 'Finding receipt sections',
  'read': 'Reading merchant and totals',
  'extract': 'Checking the numbers',
  'file': 'Preparing review',
};

enum CaptureFlowStage {
  /// Nothing has been sent yet.
  idle,

  /// Photos are on their way to the host.
  uploading,

  /// The host is reading the receipt.
  processing,

  /// A receipt is ready for a person to check or has been filed.
  ready,

  /// The host could not read this receipt.
  failed,
}

class CaptureFlowState {
  const CaptureFlowState({
    this.stage = CaptureFlowStage.idle,
    this.uploadFraction = 0,
    this.progress,
    this.batchId,
    this.receiptId,
    this.message,
    this.isDuplicate = false,
  });

  final CaptureFlowStage stage;

  /// Upload completion from 0 to 1, shown before the host takes over.
  final double uploadFraction;
  final UploadProgress? progress;
  final String? batchId;

  /// Available once the host has a draft receipt to open.
  final String? receiptId;
  final String? message;
  final bool isDuplicate;

  bool get canRetry => stage == CaptureFlowStage.failed && batchId != null;

  /// Overall completion across upload and host reading. Uploading is treated as
  /// the first fifth so the bar never stalls at zero on a slow network.
  double get overallFraction => switch (stage) {
    CaptureFlowStage.idle => 0,
    CaptureFlowStage.uploading => uploadFraction * 0.2,
    CaptureFlowStage.processing => 0.2 + ((progress?.progress ?? 0) / 100) * 0.8,
    _ => 1,
  };

  List<ProcessingStage> get stages => progress?.stages ?? const [];

  CaptureFlowState copyWith({
    CaptureFlowStage? stage,
    double? uploadFraction,
    UploadProgress? progress,
    String? batchId,
    String? receiptId,
    String? message,
    bool? isDuplicate,
    bool clearMessage = false,
  }) => CaptureFlowState(
    stage: stage ?? this.stage,
    uploadFraction: uploadFraction ?? this.uploadFraction,
    progress: progress ?? this.progress,
    batchId: batchId ?? this.batchId,
    receiptId: receiptId ?? this.receiptId,
    message: clearMessage ? null : (message ?? this.message),
    isDuplicate: isDuplicate ?? this.isDuplicate,
  );
}

class CaptureFlowController extends AutoDisposeNotifier<CaptureFlowState> {
  /// How long to keep asking before giving the person a way out.
  ///
  /// Polling used to reschedule itself forever whenever the service was
  /// unreachable, so a sleeping service left the screen turning over with no
  /// timeout and no cancel.
  static const _pollBudget = Duration(minutes: 3);

  Timer? _poll;
  DateTime? _pollingSince;
  bool _disposed = false;

  @override
  CaptureFlowState build() {
    ref.onDispose(() {
      _disposed = true;
      _poll?.cancel();
    });
    return const CaptureFlowState();
  }

  MobileApi get _api => ref.read(mobileApiProvider);

  /// Send the captured pages and follow them until the host settles.
  Future<void> start(List<String> paths) async {
    if (paths.isEmpty) return;
    state = const CaptureFlowState(stage: CaptureFlowStage.uploading);
    try {
      final ticket = await _api.uploadPhotos(
        paths,
        onProgress: (sent, total) {
          if (_disposed || total <= 0) return;
          state = state.copyWith(uploadFraction: sent / total);
        },
      );
      if (_disposed) return;
      state = state.copyWith(
        stage: CaptureFlowStage.processing,
        batchId: ticket.batchId,
        uploadFraction: 1,
      );
      // The photos are safely on the host now, so the local copies are no
      // longer the only record and the capture tray can be cleared.
      ref.read(appControllerProvider.notifier).clearCapture();
      _pollingSince = null;
      _schedulePoll();
    } on ApiFailure catch (failure) {
      if (_disposed) return;
      state = state.copyWith(
        stage: CaptureFlowStage.failed,
        message: failure.message,
      );
    }
  }

  /// Ask the host to read the already-uploaded photos again.
  Future<void> retry() async {
    final batchId = state.batchId;
    if (batchId == null) return;
    state = state.copyWith(
      stage: CaptureFlowStage.processing,
      clearMessage: true,
    );
    _pollingSince = null;
    try {
      await _api.retryUpload(batchId);
      _schedulePoll();
    } on ApiFailure catch (failure) {
      if (_disposed) return;
      state = state.copyWith(
        stage: CaptureFlowStage.failed,
        message: failure.message,
      );
    }
  }

  void _schedulePoll() {
    _poll?.cancel();
    final since = _pollingSince ??= DateTime.now();
    if (DateTime.now().difference(since) >= _pollBudget) {
      state = state.copyWith(
        stage: CaptureFlowStage.failed,
        message:
            'Your receipt is still being read and is taking longer than '
            'usual. Your photos are safe — try again, or come back to it '
            'from Receipts.',
      );
      return;
    }
    _poll = Timer(const Duration(milliseconds: 900), _pollOnce);
  }

  /// Stop following this upload. The batch keeps processing on the service.
  void stopFollowing() {
    _poll?.cancel();
    _pollingSince = null;
  }

  Future<void> _pollOnce() async {
    final batchId = state.batchId;
    if (_disposed || batchId == null) return;
    try {
      final progress = await _api.uploadStatus(batchId);
      if (_disposed) return;
      state = state.copyWith(
        progress: progress,
        receiptId: progress.receiptId,
        isDuplicate: progress.isDuplicate,
      );
      if (!progress.isSettled) {
        _schedulePoll();
        return;
      }
      if (progress.outcome == UploadOutcome.failed) {
        state = state.copyWith(
          stage: CaptureFlowStage.failed,
          message: progress.message,
        );
        return;
      }
      state = state.copyWith(
        stage: CaptureFlowStage.ready,
        message: progress.message,
      );
      // The ledger and household totals have changed, so refresh them before
      // the person lands back on Home.
      await ref.read(appControllerProvider.notifier).refresh();
    } on ApiFailure catch (failure) {
      if (_disposed) return;
      if (failure.isUnreachable) {
        // A host that briefly drops off the network should not lose the batch;
        // keep polling so the screen recovers on its own.
        _schedulePoll();
        return;
      }
      state = state.copyWith(
        stage: CaptureFlowStage.failed,
        message: failure.message,
      );
    }
  }
}

final captureFlowProvider =
    AutoDisposeNotifierProvider<CaptureFlowController, CaptureFlowState>(
      CaptureFlowController.new,
    );
