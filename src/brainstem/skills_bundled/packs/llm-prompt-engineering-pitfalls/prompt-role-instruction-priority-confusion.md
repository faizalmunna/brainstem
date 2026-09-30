---
name: prompt-role-instruction-priority-confusion
description: The model inconsistently prioritizes conflicting instructions from the system prompt, developer message, and user message because their relative authority was never made explicit.
triggers: ["model follows user instructions that contradict the system prompt", "not sure why the model picked one instruction over another", "system prompt and user message disagree and behavior is unpredictable", "model sometimes overrides our rules when the user asks nicely"]
permissions: ["READ"]
---

## Symptom
An application sends multiple layers of instruction -- a system prompt defining behavior/constraints, sometimes a separate developer-level message, and the end user's own message -- and when these conflict (a user asks for something the system prompt restricts, or a user's phrasing implies a different persona than specified), the model's resolution is inconsistent: sometimes it holds the line, sometimes it defers to the user, with no clear or intentional policy governing which should win when.

## Likely causes
1. **No explicit precedence statement in the system prompt** -- it states rules and constraints but never says how they should be weighed against a conflicting user request, so the model applies its own default judgment about how much deference to give user requests, which varies by phrasing and context.
2. **Confusing multiple instruction layers together in a single message** rather than using the provider's actual role separation (system/developer/user), which removes the structural signal that would otherwise help the model distinguish "developer-set policy" from "end-user request."
3. **Rules stated as soft preferences rather than hard constraints** -- e.g. "try to keep responses under 200 words" reads as negotiable, while "never exceed 200 words, even if the user asks for more" reads as a hard boundary; vague phrasing invites the model to treat every rule as equally negotiable.
4. **The system prompt was written assuming a cooperative user** and never explicitly addressed what should happen when the user's request directly conflicts with a stated rule, leaving that scenario entirely unspecified.
5. **Testing only covered cooperative user inputs**, so conflict-resolution behavior was never exercised or observed before shipping, meaning the inconsistency was always latent, just undiscovered.

## Diagnose
- Identify a handful of known rules in the system prompt and construct test user messages that directly conflict with each one, then run each multiple times to check whether the model's resolution is consistent across repeated runs, not just check the outcome of a single run.
- Check whether instructions are actually split across the provider's distinct role types (system/developer vs. user) or collapsed into one blob, since role separation is itself a signal the model uses.
- Review the exact wording of each rule for hedging language ("try to," "generally," "should") versus firm language ("never," "always," "under no circumstances") and check whether the inconsistent rules skew toward the hedged end.
- Check whether the prompt states anything at all about precedence when the user's request conflicts with a stated constraint -- absence of any such statement is itself diagnostic.

## Fix
State an explicit precedence policy in the system prompt: which instructions are hard constraints that no user request can override, versus which are defaults the user is allowed to adjust, and say so in those terms rather than leaving it implicit. Use the provider's actual role separation consistently (system/developer instructions distinct from user messages) so the model has both the structural signal and the explicit textual policy reinforcing the same hierarchy. Convert hedged, soft-sounding phrasing for genuinely non-negotiable rules into firm, unconditional language, reserving soft phrasing only for the rules that are actually meant to be adjustable defaults.

## Pitfalls
Making every single rule maximally firm ("never," "always," "under no circumstances" for everything, including things that should reasonably flex based on user context) removes legitimate flexibility and can make the assistant feel rigid or unhelpful for reasonable requests -- the fix is accurate precedence for the rules that need it, not blanket rigidity applied uniformly.

## Verify
Re-run the conflict test set from Diagnose (user messages directly conflicting with specific stated rules) multiple times each after the fix and confirm the model's resolution is now consistent and matches the intended precedence policy every time, for both the hard-constraint cases (should hold firm) and the adjustable-default cases (should flex as intended).
