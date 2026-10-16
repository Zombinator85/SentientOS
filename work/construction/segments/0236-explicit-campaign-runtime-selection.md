# Sequence 236 - Explicit campaign runtime selection

The campaign-to-signal runtime test now enters through the actual digest-validated selection-config loader. It verifies the reconstructed owner is read-only and selected IDs are exact before an admitted signal-plane operation. A selection-config mutation with a stale digest fails closed without owner recovery or ambient campaign discovery.

Validation: three focused selection, contradiction/restart, and resource-reread tests passed. The affected test module compiled and `git diff --check` passed.

Next: continue Program A process recovery/temporal ordering and Program B's later candidate-selection trajectory; Program C still needs the distinct-task resource recommendation and broader outcome progression.
