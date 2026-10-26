# Sequence 721: reject unrepresentable parent numbers

Maintenance resident parent-supervision snapshots and launch receipts now validate finite integers without leaking `OverflowError` for integers beyond float range. Focused regressions passed 3/3; targeted mypy and compilation passed. The full parent module run passed 27/35; its eight fixture/commissioning failures were reproduced on verified baseline `efab72d7d062d320e6982e9b3b6b3891d3d7db53`.

Evidence record: `work/construction/evidence/0721-reject-unrepresentable-parent-numbers.json`
Evidence SHA-256: `6092bbc48c44ba92f03ee4ad30877d8dfe14ce15bc949c5bf5cee0c7e25012f4`
