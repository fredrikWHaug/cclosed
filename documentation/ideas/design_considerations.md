# Design considerations — architecture dialogue (stored context)

> Verbatim transcript of the architecture discussion about keeping the firmware
> "plumbing" invariant while swapping classifiers, and an epistemic-honesty
> exchange about how confident that architecture advice actually is. Stored as
> important context for the classifier-pipeline architecture decision.

---

## Fredrik

Right. But these are design considerations that we will have to make. But are you saying we can keep the overarching architecture fairly consistent in terms of the plumbing as I call it, like what separate modules we have and how we interface between the different modules? This is the important thing I thing we need to decide upon now, and also consider whether this itself is a considerably variable concept that can be optimized or not.

## Claude

Yes — and this is the right thing to lock down now. My honest position: **the plumbing can be kept near-invariant, with the classifier as the single swappable module — but only if we adopt two conventions now.** Those two conventions *are* the decision. Let me lay out the invariant substrate, then the two forks that determine how invariant it really is, with my recommendation on each.

### The proposed invariant substrate

```
[SPI/Intan acquire] → [ring buffer] → [detect + align] → [classify] → [packetize + BLE]
        │                  │                │                 │              │
     invariant         invariant        invariant        SWAPPABLE      invariant
        │                  │                │                 │              │
   xfer/init          ring[N]          snippet out       classify.h      unit_id+ts
   (never             samples in,     ◄─ Contract A     ◄ Contract B ─►   out
    changes)          windows out      int16 snippet[N]  uint8 unit_id    fixed packet
```

Four of the five modules never change when you swap classifiers. The interfaces between them — **Contract A** (`int16 snippet[N]` in) and **Contract B** (`uint8 unit_id` + timestamp out) — are what you freeze once and never touch again.

### The two decisions that determine invariance

**Decision 1 — Where does feature extraction live?** This is the big one.
- **Option A (recommended): inside `classify()`.** Every classifier receives the *same raw `int16 snippet[N]`* and does its own feature work internally. Logistic-regression-on-FSDE computes FSDE inside its file; the CNN eats raw samples; Tier 0 takes max−min. **Plumbing stays 100% invariant** because the interface is always "raw snippet in."
- **Option B: feature extraction as its own pipeline stage** feeding a `feature[]` vector to `classify()`. But different classifiers want different features → the feature stage *and* the interface (how many features) become variable → the plumbing is no longer invariant.
- **My recommendation: Option A.** Freeze the contract at raw snippet. If two classifiers share a feature extractor (e.g. FSDE), factor it into a `features.c` helper they *choose* to call — shared code without it being a mandatory, interface-changing stage. This is the single most important convention for keeping the plumbing stable.

**Decision 2 — Where do detection and alignment live?**
- **Recommended: as a fixed upstream stage**, not inside `classify()`. Detection ("a spike occurred at index i") and alignment ("center the snippet on the peak") are logically independent of *which* classifier runs. Making them a fixed stage means every classifier receives a clean, peak-centered snippet and none of them re-implements detection. (Your pilot currently folds lag-search *into* `classify()` — that was fine for one method, but it's the thing to lift out to make the swap truly clean.)
- Consequence: `classify()` may assume its input is already aligned. That assumption becomes part of Contract A, documented in `classify.h`.

### Is the plumbing itself "considerably variable / optimizable"?

Honest answer: **within your paradigm, no — and that's the good news.** The *module structure and the two interfaces* should be frozen now; you nail them once and every classifier reuses them. What remains tunable is strictly *inside* modules and doesn't touch the interfaces:

- ring size, window length `N`, detection threshold/method, alignment method, packet batching — all internal knobs you can optimize freely later without breaking anything.

The plumbing only becomes genuinely *variable* if you leave the paradigm — and it's worth naming exactly when, so you know the boundaries of what you're freezing:
1. **Continuous/streaming classifiers** (an RNN or CNN that processes every sample with no discrete detection) — this removes the detect stage and changes Contract A from "a snippet" to "a sample stream." *Out of scope for your single-channel detect-then-classify thesis, but it's the one thing that would rearchitect the plumbing.*
2. **Multi-channel spatial classification** (multiple ring buffers + a spatial-feature stage, like the real chips) — future, not now.

So the discipline is: **freeze the module boundaries and Contracts A/B today; optimize inside modules forever; only revisit the plumbing if you deliberately switch paradigms.** Adopt Option A (features inside classify) + detection/alignment as a fixed upstream stage, and your plumbing is invariant across logistic regression, template matching, MLP, and snippet-based CNN/RNN — the entire realistic classifier space for the thesis — with `classify.c` as the one file that ever changes.

If you're good with those two conventions, that *is* the architecture, and we can freeze `classify.h` (the contract) as the first concrete artifact.

---

## Fredrik

Ok great but now let me ask you this: how do you know this? Or what makes you think you know this? Is this a battle-tested architecture for this kind of data streaming in terms of the interfaces? Or are you genuinely not sure since you have some kind of intuition? I'm not necessarily asking you to cite a book written about abstract system architectures for this kind of embedded streaming, I mean you could but I don't expect you to be able to. I just want to have an open dialog about this, because I have the best interest for myself in terms of my learning, this project, and my integrity. But I think it's unavoidable to have these kinds of discussions with AI these days, so I want to just ask you this question first: how do you know this, and how confidently are you that if we were to decide on this architecture, we wouldn't be wrong i.e. there exists a much better choice?

## Claude

Good question, and the honest answer has layers, because "how do I know this" is genuinely different at different levels of the claim. Let me separate what's battle-tested from what's my judgment, because they're not the same and you deserve to know which is which.

**What's canonical, not intuition.** The two load-bearing pieces are textbook, decades-old patterns that I'm recognizing, not inventing:
- **Producer-consumer via a ring buffer** — a single-producer/single-consumer ring is one of the most-studied concurrency primitives in existence (every RTOS, audio pipeline, DSP chain uses it). The claim "decouple acquisition from processing with a bounded ring" is as close to settled as embedded architecture gets.
- **A stable interface with a swappable implementation behind it** — this is just the strategy pattern / dependency inversion / hardware-abstraction-layer idea. "Freeze a header, vary the .c behind it" is bedrock C modularity.

These have names you can check independently of me: *SPSC ring buffer*, *strategy pattern*, *pipeline/dataflow architecture*, *HAL*. If I disappeared, you'd find all of them described the same way. At this level my confidence is very high, and it's not intuition — it's recognition of established patterns.

**What's my judgment, not canon.** The *specific decomposition* — exactly these five stages, features-inside-classify vs. features-as-a-stage, alignment upstream vs. inside — is me *instantiating* those patterns for your problem. That's informed (the fabricated-chip papers you just read literally diagram detect→feature→classify as stages, and your pilot already has the seam), but the exact boundary choices are defensible opinions, not theorems. Option B (features as their own stage) is a real alternative that some real pipelines prefer; I recommended A, but I can't prove A dominates B for your future. Here my confidence is *moderate* — good recommendation, genuinely contestable.

**The one thing that would make us "wrong."** The whole "invariant plumbing" claim is *conditional on the paradigm*: discrete detect-then-classify, single channel. That assumption is load-bearing. If the project's real trajectory turns out to be streaming neural nets (process every sample, no discrete detection) or multi-channel spatial sorting, the plumbing I described needs rework. I flagged that earlier, and it's the honest hedge: **the architecture is right *given the paradigm*, and the paradigm assumption is the thing most likely to be the actual mistake** — not the ring buffer, not the interface.

**And a failure mode you should hold me to.** AI architecture advice has two characteristic biases: it *over-engineers* (adds principled-sounding abstractions you don't need) and it *sounds more authoritative than the underlying confidence warrants*. I've tried to counter the first — I explicitly argued *against* splitting `ring.c`/`ble.c`/`spi.c`, kept it to the one split that serves your stated goal. But I can't fully self-certify that I'm not doing the second right now. I don't have reliable introspective access to distinguish "this is the canonical pattern" from "this pattern-completes to something that sounds right" — same caveat as when I botched those numeric comparisons earlier.

**So here's the integrity move, and it's better than trusting my confidence:** this architecture makes a *falsifiable* claim — "you can swap the classifier without touching `main.c`." Don't take that on faith. Test it cheaply and early: implement two *maximally different* classifiers behind the same `classify.h` — say, the Tier-0 threshold (integer, trivial) and template-matching (float, windowed) — and check whether `main.c` genuinely never changes. If it does, the abstraction leaked and we chose the boundary wrong, and you'll know in an afternoon rather than after building on it. That experiment tests the design harder than any amount of me asserting it's right — and it's the kind of thing that protects your integrity too, because then *you've* verified the claim, not outsourced it to me.

My net position: high confidence on the patterns, moderate on the specific boundaries, and the real risk isn't "a much better architecture exists for this paradigm" (this *is* the standard shape) — it's "the paradigm might shift." I'd commit to it *as a starting point designed to be cheaply falsified*, not as a thing to trust because I said so.
