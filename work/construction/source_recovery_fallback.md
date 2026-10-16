# Exact source recovery through GitHub Git Data

This construction-only fallback restores a branch tree when native Git transport is unavailable and an authorized GitHub integration can read the repository.

1. Preserve the original checkout. Inspect its committed HEAD, tree, object completeness, and dirty status. Create an isolated local clone from committed objects with git clone --local --no-hardlinks; do not copy the source worktree or its untracked files.
2. Read the live construction branch through GitHub. Record the exact remote commit and root tree. Read the base commit/tree and confirm ancestry with the GitHub compare endpoint.
3. Request the target root tree recursively. Require the returned tree SHA to equal the commit's tree SHA and require truncated to be false. Obtain the full base-to-target changed path set and the target tree's SHA and mode for every changed path.
4. Retrieve each changed blob through GitHub's repository file/blob API in bounded batches. Require the response blob SHA to equal the target tree entry. Preserve response bytes exactly; for base64 responses, decode bytes without text normalization. Write each path in the isolated clone and set its Git mode (100644 or 100755). Remove paths reported deleted by the comparison.
5. Verify each hydrated path with git hash-object. Stage only the reconstructed delta and compute git write-tree. Continue only if this root tree exactly equals the live remote tree. A matching tree proves source identity; it does not prove that a local commit SHA equals the upstream commit.
6. Optionally create a clearly named synthetic local snapshot commit for development. Keep the true remote commit/tree in recovery metadata. Never publish that synthetic commit as upstream history.
7. Compile and run a focused repository-native test from the recovered path. If the canonical environment cannot be provisioned because a dependency source is unavailable, report that block; do not bypass network policy. Use the explicit project test opt-in only for a focused test when the test owner and exact source path are fixed.
8. For publication, create blobs and a tree based on the verified remote tree, create a commit parented to the exact live branch head, reacquire the branch immediately before update, and move it only through expected-HEAD compare-and-swap. Independently read back the commit, tree, every changed blob, parent, and ref.

The recovery receipt should include baseline commit/tree, target commit/tree, compare counts, hydrated path count, per-blob and mode verification, final git write-tree, local synthetic commit if used, validation commands, and transport/setup blockers. Missing blobs, truncated trees, SHA mismatches, or a different final tree make the reconstruction incomplete.
