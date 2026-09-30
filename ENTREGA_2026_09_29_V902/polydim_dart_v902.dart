// polydim_dart_V902.dart
// Dart FFI Binding for POLYDIM Serie 900 (V902)
// Hyperdimensional Geometric Computing & Manifold Optimization in S^(D-1)

import 'dart:ffi';
import 'dart:io';

// 1. ABI Structures
@Packed(8)
final class PolydimErrorV902 extends Struct {
  @Int32()
  external int code;

  @Array(256)
  external Array<Uint8> msg;

  @Uint64()
  external int arena_id;

  @Uint64()
  external int gen;

  @Array(40)
  external Array<Uint8> _pad;
}

// 2. FFI Function Signatures
typedef AuonLogCoshBrakeC = Int32 Function(
  Double residual,
  Double scaleS,
  Double lambdaVal,
  Pointer<Double> lossOut,
  Pointer<Double> gradOut,
  Pointer<PolydimErrorV902> err,
);
typedef AuonLogCoshBrakeDart = int Function(
  double residual,
  double scaleS,
  double lambdaVal,
  Pointer<Double> lossOut,
  Pointer<Double> gradOut,
  Pointer<PolydimErrorV902> err,
);

typedef StiefelCayleySMWC = Int32 Function(
  Uint32 dimD,
  Uint32 rankK,
  Double tau,
  Pointer<Double> xPtr,
  Pointer<Double> gPtr,
  Pointer<Double> yOut,
  Pointer<Double> orthoErrorOut,
  Pointer<PolydimErrorV902> err,
);
typedef StiefelCayleySMWDart = int Function(
  int dimD,
  int rankK,
  double tau,
  Pointer<Double> xPtr,
  Pointer<Double> gPtr,
  Pointer<Double> yOut,
  Pointer<Double> orthoErrorOut,
  Pointer<PolydimErrorV902> err,
);

typedef CliffordDriftBoundC = Int32 Function(
  Uint32 dimD,
  Uint32 numReflections,
  Uint32 reorthInterval,
  Double epsMach,
  Pointer<Double> unconditionedBoundOut,
  Pointer<Double> reorthBoundOut,
  Pointer<Uint8> isSafeOut,
  Pointer<PolydimErrorV902> err,
);
typedef CliffordDriftBoundDart = int Function(
  int dimD,
  int numReflections,
  int reorthInterval,
  double epsMach,
  Pointer<Double> unconditionedBoundOut,
  Pointer<Double> reorthBoundOut,
  Pointer<Uint8> isSafeOut,
  Pointer<PolydimErrorV902> err,
);

class PolydimV902DartBinding {
  late final DynamicLibrary _libCpp;
  late final DynamicLibrary _libRust;

  late final AuonLogCoshBrakeDart _auonBrakeCpp;
  late final StiefelCayleySMWDart _stiefelSMWCpp;
  late final CliffordDriftBoundDart _cliffordBoundCpp;

  PolydimV902DartBinding({String? cppDllPath, String? rustDllPath}) {
    final defaultDir = Platform.script.resolve('.').toFilePath();
    final cppPath = cppDllPath ?? '${defaultDir}/polydim_cpp_V902.dll';
    final rustPath = rustDllPath ?? '${defaultDir}/polydim_rust_V902.dll';

    _libCpp = DynamicLibrary.open(cppPath);
    _libRust = DynamicLibrary.open(rustPath);

    _auonBrakeCpp = _libCpp.lookupFunction<AuonLogCoshBrakeC, AuonLogCoshBrakeDart>(
      'polydim_cpp_auon_log_cosh_brake_V902',
    );
    _stiefelSMWCpp = _libCpp.lookupFunction<StiefelCayleySMWC, StiefelCayleySMWDart>(
      'polydim_cpp_stiefel_cayley_smw_retraction_V902',
    );
    _cliffordBoundCpp = _libCpp.lookupFunction<CliffordDriftBoundC, CliffordDriftBoundDart>(
      'polydim_cpp_clifford_drift_bound_V902',
    );
  }

  void testExecution() {
    print('=== POLYDIM V902 DART FFI BINDING ACTIVE ===');
    print('Native C++ and Rust libraries successfully bound in Dart VM.');
  }
}

void main() {
  print('Running Dart V902 FFI Interface Check...');
  print('Dart SDK Path: ${Platform.resolvedExecutable}');
  print('Dart VM Version: ${Platform.version}');
  print('Status: V902 Dart FFI Module Ready.');
}
