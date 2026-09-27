"""DELIBERATELY FAILING: demonstrates that a red check blocks the merge (assignment §3.4, rubric I).

Added to PR #39 so the failed check and the blocked merge button could be
captured for docs/evidence/, then removed in the very next commit.
"""


def test_ci_gate_blocks_a_failing_pull_request():
    assert 1 + 1 == 3, "deliberate failure: CI must turn red and block the merge"
