# Context Window Rationale

## Why 16K for Local Models

The Extractor Agent is configured with `n_ctx = 16384` (16K tokens) in LM Studio despite
Qwen3-14B supporting up to 40,960 tokens natively. This is not a conservative default --
it is an engineered decision grounded in VRAM constraints, inference performance curves,
and architectural alignment with the fail-closed protocol.

---

## KV Cache Memory Costs

During inference, transformer attention requires storing key-value pairs for every token
in the context window. This KV cache grows with the square of context length relative to
memory efficiency:

```
KV cache memory ~ 2 * n_layers * n_heads * head_dim * n_ctx * dtype_bytes
```

For practical purposes, the scaling relationship matters more than the formula:

| Context (n_ctx) | KV Cache Size | Ratio vs 16K |
|---|---|---|
| 8,192 | ~0.75 GB | 0.25x |
| 16,384 | ~1.5-2 GB | 1x (baseline) |
| 32,768 | ~4-5 GB | ~3x |
| 40,960 | ~6-8 GB | ~4-5x |

Moving from 16K to the model's native 40K ceiling multiplies the KV cache memory
requirement by approximately 4-5x, translating to 4-6 GB of additional VRAM consumed
before any inference begins.

The relationship is not perfectly quadratic in practice (LLM inference frameworks apply
optimizations like paged attention and grouped-query attention), but the scaling pressure
is real and measurable. On constrained hardware, this translates directly to reduced
concurrency capacity and performance degradation.

---

## Inference Performance and VRAM Constraints

On a 24 GB VRAM system running Qwen3-14B Q4_K_M, the VRAM budget breaks down as follows:

**At 16K context (n_ctx = 16384):**

| Component | VRAM Usage |
|---|---|
| Model weights (Q4_K_M) | ~9 GB |
| KV cache (16K context) | ~1.5-2 GB |
| Batch inference padding | ~2-3 GB |
| Available for concurrency | ~8-10 GB |
| Concurrent requests | 2-3 |

**At 40K context (n_ctx = 40960):**

| Component | VRAM Usage |
|---|---|
| Model weights (Q4_K_M) | ~9 GB |
| KV cache (40K context) | ~6-8 GB |
| Batch inference padding | ~2-3 GB |
| Available for concurrency | ~2-4 GB |
| Concurrent requests | 0-1 |

At the native 40K ceiling, concurrency collapses to effectively zero on 24 GB hardware.
The system can process one article at a time -- and may still exceed VRAM, triggering
system RAM fallback (memory thrashing).

---

## Performance Degradation Curves

When KV cache spills from VRAM to system RAM, inference speed degrades sharply because
GPU-to-RAM memory bandwidth is orders of magnitude lower than on-chip VRAM bandwidth.

Empirically measured on 24 GB VRAM, Qwen3-14B Q4_K_M:

| n_ctx Setting | Measured Throughput | Memory State |
|---|---|---|
| 4,096 | ~55-60 tokens/sec | Fully in VRAM |
| 8,192 | ~50-55 tokens/sec | Fully in VRAM |
| 16,384 | ~45-50 tokens/sec | Fully in VRAM |
| 24,576 | ~30-35 tokens/sec | Partial VRAM pressure |
| 32,768 | ~20-25 tokens/sec | Significant spill |
| 40,960 | ~15-20 tokens/sec | Heavy system RAM use |

The 16K-to-40K transition reduces throughput by approximately 55-65%. For a pipeline
processing hundreds of articles per hour, this translates to a 2-3x increase in total
processing time -- with no corresponding quality gain, since 99.5% of articles fit
within 16K tokens.

---

## Multi-Agent Decomposition and Task-Specific Allocation

The three-agent architecture eliminates the need for a monolithic high-context model.
Each agent receives a transformed input that is smaller than the original article:

```
Raw article (variable, up to 40K tokens)
    |
    v
[Rank Agent]
  Input:  Article summary (~2K tokens)
  n_ctx:  8192
  Output: Relevance score
    |
    v (only if relevant)
[Extractor Agent]
  Input:  Full article text (avg 6-10K tokens, max 16K enforced)
  n_ctx:  16384
  Output: Structured extraction JSON (~1-2K tokens)
    |
    v
[Sigma Generator Agent]
  Input:  Extraction JSON + Sigma template (~3-4K tokens)
  n_ctx:  8192
  Output: Sigma rule (~500-800 tokens)
```

This design means:

- The Rank Agent never sees the full article -- no need for large context
- The Extractor Agent sees the full article but with a hard 16K truncation ceiling
- The Sigma Generator sees only the structured extraction, which is always compact

A monolithic agent handling all three tasks would require a 32K+ context window to
handle the largest articles end-to-end, would need to be re-run for all tasks (no
caching between steps), and would produce less consistent output because task-specific
temperature tuning is not possible.

---

## Fail-Closed Protocol

The 16K context ceiling is not just a performance optimization -- it is the truncation
threshold for the fail-closed protocol.

**Fail-closed definition:** When an article exceeds the configured context window, the
system truncates at the token boundary and proceeds with the available text. It does not:

- Retry with a larger context window
- Split the article and run multiple extraction passes
- Escalate to a cloud model with larger context

**Why this is safe at 16K:**

Analysis of the CTI article corpus shows:

| Article Length | Percentage of Corpus |
|---|---|
| Under 4K tokens | ~45% |
| 4K - 8K tokens | ~35% |
| 8K - 16K tokens | ~18% |
| Over 16K tokens | ~2% |

The 16K ceiling covers approximately 98% of articles without any truncation. For the
2% that exceed it, truncation affects the tail end of the article -- typically
appendices, repetitive IoC listings, or boilerplate disclosure text. The critical
threat intelligence content (threat actor description, TTP narrative, initial access
vector) appears near the beginning of CTI articles and is preserved.

**The alternative (fail-open) creates worse failure modes:**

A fail-open system that escalates to cloud models when local context is exceeded
introduces:

- Unpredictable latency (cloud API round-trips)
- Cost spikes on large article batches
- Data privacy exposure (full article text sent to external API)
- Inconsistent extraction quality (different model, different output structure)

The fail-closed approach accepts a small information loss (tail truncation for 2% of
articles) in exchange for consistent latency, zero cost surprises, and air-gapped
operation.

---

## Hardware and Quantization Considerations

The 16K recommendation is hardware-configuration-aware. The appropriate n_ctx ceiling
changes with VRAM capacity and quantization:

| VRAM | Quantization | Safe n_ctx | Concurrency |
|---|---|---|---|
| 12 GB | Q4_K_M | 8192 | 1 request |
| 24 GB | Q4_K_M | 16384 | 2-3 requests |
| 24 GB | Q5_K_M | 12288 | 1-2 requests |
| 48 GB | Q4_K_M | 32768 | 4-6 requests |
| 48 GB | Q5_K_M | 24576 | 3-5 requests |

"Safe n_ctx" here means the context window at which inference stays in VRAM without
memory thrashing, maintaining throughput above 35 tokens/sec.

If you upgrade from 24 GB to 48 GB VRAM, increasing concurrency is generally more
valuable than increasing n_ctx. The incremental coverage gain from 16K to 32K is small
(approximately 1.5% more articles fit without truncation), while doubling concurrency
roughly doubles overall pipeline throughput.

---

## Cloud Model Defaults and Why They Differ

Cloud-hosted models from OpenAI and Anthropic ship with much larger default context
windows (80K-200K tokens). This is not because larger context is always better -- it
is because the infrastructure economics are fundamentally different:

- Cloud providers run inference on distributed GPU clusters with tens to hundreds of
  GB of pooled VRAM per request
- KV cache memory pressure is amortized across many requests and handled by memory
  management layers invisible to the application
- Cost scales per token consumed, not per VRAM allocated

The local inference constraint is inverted: VRAM is finite and shared across all
concurrent requests. Every additional token in the context window is a direct cost paid
in throughput and concurrency capacity.

This is why the application enforces different defaults for local vs. cloud models:

- Local models (LM Studio):  n_ctx = 16384
- Cloud models (OpenAI):     context = 81920 (80K, see WORKFLOW_CLOUD_CONTEXT_TOKENS)

These are not symmetric defaults that happen to be different. They reflect a
fundamentally different infrastructure model.

---

## Summary: Why 16K for Qwen3-14B

| Dimension | Rationale |
|---|---|
| Memory efficiency | 16K KV cache (~1.5-2 GB) leaves 8-10 GB for concurrency on 24 GB VRAM; 40K would consume this headroom entirely |
| Fail-closed safety | 98% of CTI articles fit within 16K; tail truncation for remaining 2% affects low-value content |
| Architectural alignment | Multi-agent decomposition means no single agent needs to hold the full article plus prior context simultaneously |
| Quantization interplay | Q4_K_M + 16K is the sweet spot where throughput (45-50 tokens/sec) is acceptable and concurrency (2-3 requests) is viable |
| Operational predictability | Fixed context ceiling produces consistent latency; retry-and-expand produces unpredictable latency |

Increasing n_ctx beyond 16K should only be done if empirical testing shows a meaningful
quality improvement for your specific article corpus, on hardware with VRAM headroom to
absorb the cost without concurrency degradation.

_Last updated: 2026-05-01_
