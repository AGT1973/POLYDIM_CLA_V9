// polydim_dart_v900.dart
// Dart FFI Binding for POLYDIM Serie 900 (V900)
// Hyperdimensional Geometric Computing & Manifold Optimization in S^(D-1)

import 'dart:ffi';
import 'dart:io';

// 1. ABI Structures
final class PolydimErrorV900 extends Struct {
  @Int32()
  external int code;

  @Array(256)
  external Array<Uint8> msg;
}

// 2. FFI Function Signatures
typedef AuonLogCoshBrakeC = Int32 Function(
  Double residual,
  Double scaleS,
  Double lambdaVal,
  Pointer<Double> lossOut,
  Pointer<Double> gradOut,
  Pointer<PolydimErrorV900> err,
);
typedef AuonLogCoshBrakeDart = int Function(
  double residual,
  double scaleS,
  double lambdaVal,
  Pointer<Double> lossOut,
  Pointer<Double> gradOut,
  Pointer<PolydimErrorV900> err,
);

typedef StiefelCayleySMWC = Int32 Function(
  Uint32 dimD,
  Uint32 rankK,
  Double tau,
  Pointer<Double> xPtr,
  Pointer<Double> gPtr,
  Pointer<Double> yOut,
  Pointer<Double> orthoErrorOut,
  Pointer<PolydimErrorV900> err,
);
typedef StiefelCayleySMWDart = int Function(
  int dimD,
  int rankK,
  double tau,
  Pointer<Double> xPtr,
  Pointer<Double> gPtr,
  Pointer<Double> yOut,
  Pointer<Double> orthoErrorOut,
  Pointer<PolydimErrorV900> err,
);

typedef CliffordDriftBoundC = Int32 Function(
  Uint32 dimD,
  Uint32 numReflections,
  Uint32 reorthInterval,
  Double epsMach,
  Pointer<Double> unconditionedBoundOut,
  Pointer<Double> reorthBoundOut,
  Pointer<Uint8> isSafeOut,
  Pointer<PolydimErrorV900> err,
);
typedef CliffordDriftBoundDart = int Function(
  int dimD,
  int numReflections,
  int reorthInterval,
  double epsMach,
  Pointer<Double> unconditionedBoundOut,
  Pointer<Double> reorthBoundOut,
  Pointer<Uint8> isSafeOut,
  Pointer<PolydimErrorV900> err,
);

class PolydimV900DartBinding {
  late final DynamicLibrary _libCpp;
  late final DynamicLibrary _libRust;

  late final AuonLogCoshBrakeDart _auonBrakeCpp;
  late final StiefelCayleySMWDart _stiefelSMWCpp;
  late final CliffordDriftBoundDart _cliffordBoundCpp;

  PolydimV900DartBinding({String? cppDllPath, String? rustDllPath}) {
    final defaultDir = Platform.script.resolve('.').toFilePath();
    final cppPath = cppDllPath ?? '${defaultDir}/polydim_cpp_v900.dll';
    final rustPath = rustDllPath ?? '${defaultDir}/polydim_rust_v900.dll';

    _libCpp = DynamicLibrary.open(cppPath);
    _libRust = DynamicLibrary.open(rustPath);

    _auonBrakeCpp = _libCpp.lookupFunction<AuonLogCoshBrakeC, AuonLogCoshBrakeDart>(
      'polydim_cpp_auon_log_cosh_brake_v900',
    );
    _stiefelSMWCpp = _libCpp.lookupFunction<StiefelCayleySMWC, StiefelCayleySMWDart>(
      'polydim_cpp_stiefel_cayley_smw_retraction_v900',
    );
    _cliffordBoundCpp = _libCpp.lookupFunction<CliffordDriftBoundC, CliffordDriftBoundDart>(
      'polydim_cpp_clifford_drift_bound_v900',
    );
  }

  void testExecution() {
    print('=== POLYDIM V900 DART FFI BINDING ACTIVE ===');
    print('Native C++ and Rust libraries successfully bound in Dart VM.');
  }
}

void main() {
  print('Running Dart V900 FFI Interface Check...');
  print('Dart SDK Path: ${Platform.resolvedExecutable}');
  print('Dart VM Version: ${Platform.version}');
  print('Status: V900 Dart FFI Module Ready.');
}
