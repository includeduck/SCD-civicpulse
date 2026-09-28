# Merge conflict, resolved on the command line (#48)

**Where:** PR #51 (`fix/dictate-routing-verbs`) and PR #50 (`fix/harden-prompt-injection`, merged into `dev` as `3c02c78`) both branched from `dev` at `3dd0455`, and both edited `backend/tests/test_triage_injection.py`.

**Merge commit:** `ad4665f`, "Merge branch 'dev' into fix/dictate-routing-verbs" (parents `22e4823` from #51 and `3c02c78` from `dev`).

## How it happened

The plan was for #51 to merge first and Talha to resolve the conflict in #50. Talha was unavailable to approve #51, so the order was flipped: #50 (already approved) was merged first, and the conflict surfaced on #51 instead. #48 is assigned to both partners.

```text
$ git fetch origin
$ git merge origin/dev --no-edit
Auto-merging backend/app/providers/triage/injection.py
Auto-merging backend/tests/test_triage_injection.py
CONFLICT (content): Merge conflict in backend/tests/test_triage_injection.py
Automatic merge failed; fix conflicts and then commit the result.

$ git status --short
M  backend/app/providers/triage/injection.py
UU backend/tests/test_triage_injection.py
M  docs/AI-USAGE.md
M  docs/TRIAGE.md
```

`injection.py` merged by itself: #51 added `send|forward|refer` to the category `dictate_output` rule, while #50 added new rules in other places (its temporary edit to that rule was reverted during review). The test file did not.

## The conflict markers

Both branches appended genuine-complaint controls to the end of the `GENUINE` list, at the same lines:

```text
    "Road ko repair karne ki instructions board par likhi hain magar kaam nahin hua",
<<<<<<< HEAD
    "Please send a plumber to fix the burst water pipe in Street 5",
    "Kindly forward the team to the site, the road is flooded",
=======
    # Additional controls with department and urgency keywords (Issue #44)
    "Water supply department has not sent a water tanker to Sector G-9 for three days",
    "Transformer se sparks nikal rahe hain, bohat urgent matter hai barah-e-karam jaldi team bhejein",
    "Health and sanitation department: please clear the garbage bins outside the hospital gate",
    # Citizen phrasing asking for priority or department referral (must remain unflagged)
    "Sewerage overflow near the school, please make this top priority",
    "Bijli ke mehkame ko bhejein please, transformer jal gaya hai",
>>>>>>> origin/dev
]
```

`HEAD` is #51 (controls for its new `send`/`forward` verbs); `origin/dev` is #50 (controls for its homoglyph, authority and department rules).

## Resolution and why

**Kept both sides**, #51's two lines followed by #50's six, and removed the markers.

Neither version could win outright, because each side's cases guard a different change. Dropping #51's lines would stop protecting "send a plumber" from the new `send` verb. Dropping #50's would let a later edit reintroduce the "top priority" and "mehkame ko bhejein" false positives removed in #50's review. The combined list was checked against the *merged* detector, which has both sides' rules. That matters because #51's new verbs could have flagged one of #50's sentences (for example "jaldi team bhejein"). None did:

```text
$ pytest -q
275 passed, 10 skipped
Required test coverage of 90.0% reached. Total coverage: 97.95%
$ ruff check . && ruff format --check . && mypy app
All checks passed! / 72 files already formatted / Success: no issues found in 42 source files
```

Then `git add backend/tests/test_triage_injection.py && git commit`, and CI re-ran on #51 with the merge.
