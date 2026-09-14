# Engineering Notes

> **CS4032 Software Construction and Design — Assignment 01**
>
> This document answers all 8 assignment engineering questions with exact file and line references.
> It is a living document — sections marked *TODO* will be completed as each phase is implemented.

---

## Q1 — How does the four-layer backend architecture enforce separation of concerns?

*TODO: Answer with file + line references after Phase 1.*

---

## Q2 — How does the rate limiter work correctly across multiple backend replicas?

*TODO: Answer with file + line references after Phase 6.*

---

## Q3 — Why is Redis AOF enabled, and what does it protect against?

*TODO: Answer after Phase 6.*

Redis AOF (Append-Only File) persistence is enabled to survive container restarts without losing the distributed rate-limit state and stats-cache keys.

**Justification:** Without AOF, a Redis restart resets all rate-limit windows, allowing a burst of requests immediately after recovery. With AOF, the windows survive and the rate-limit guarantee holds across restarts.

---

## Q4 — How is the AI triage fallback implemented and tested?

*TODO: Answer with file + line references after Phase 4–5.*

---

## Q5 — How does the frontend avoid baking the backend URL into the build?

*TODO: Answer with file + line references after Phase 8.*

---

## Q6 — How does the Compose network topology enforce the security constraint?

*TODO: Answer with evidence command after Phase 9.*

---

## Q7 — How is a zero-downtime rolling deployment achieved?

*TODO: Answer with file + line references after Phase 11–12.*

---

## Q8 — How is the HPA/VPA conflict handled?

*TODO: Answer after Phase 12.*
