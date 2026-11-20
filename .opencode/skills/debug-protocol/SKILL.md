---
name: debug-protocol
description: Use on the first failing command, test, container or pipeline run, before changing anything. Keeps debugging to one hypothesis at a time and stops after repeated failures instead of thrashing.
---

# debug-protocol

1. Reproduce. Run the failing command again and keep the exact command and the exact error text.
2. Read the whole error, including the first error in the log, not only the last line. For containers read `podman logs <name>` and `podman inspect` (exit code, `OOMKilled`).
3. State one hypothesis and the evidence for it, in one or two sentences, in the verification file.
4. Change one thing. Run the same command again. Record the result.
5. If the hypothesis is wrong, discard the change (do not stack edits) and go back to step 3.
6. After **three** failed attempts on the same problem, stop. Write what was tried, what each attempt showed, and what you suspect. Ask Ivan.

Do not:

- change a version, a limit, or a design decision to make an error go away (memory limits, image tags, architecture). Report instead.
- delete volumes, images or data to "start clean" without asking.
- claim a fix without re-running the exact failing command and showing the output.
