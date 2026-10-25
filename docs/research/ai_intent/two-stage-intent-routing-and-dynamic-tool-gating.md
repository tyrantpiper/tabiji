# Two-stage intent routing and dynamic tool gating in a production travel agent

**Contributor:** ([@tyrantpiper](https://github.com/tyrantpiper))

**Type:** Firsthand experience designing, implementing, and running a real-time mobile travel assistant harness in production ([Tabiji](https://github.com/tyrantpiper/tabiji), pinned implementation commit [`4603b22`](https://github.com/tyrantpiper/tabiji/commit/4603b22c6a261cc4ae5542882b2f91131874d786)); code quotes and benchmark numbers come from the actual FastAPI backend repository and session telemetry.

**Course connections:** [Learning and selecting tools](../concepts/learning-and-selecting-tools.md); [Workflows versus agents](../concepts/workflows-vs-agents.md); [Agent harness design](../concepts/agent-harness-design.md); [Evaluating tool use](../concepts/evaluating-tool-use.md); [Prefill, decode, and the KV cache](../concepts/prefill-decode-and-kv-cache.md); [Structured output and validation](../concepts/structured-output-and-validation.md); [Lecture 4: Tool Use](../lectures/04-tool-use.md); [Lecture 2: Language model inference](../lectures/02-llms-for-builders.md#part-4-language-model-inference-slides-119-148)

---

## The system and who built it

I built and operate the AI travel harness for **Tabiji**, an open-source, offline-first Progressive Web App designed for multi-day travel. The system pairs a Next.js 16 front end with a Python 3.11+ / FastAPI backend, coordinating a mix of flagship reasoning models and smaller workhorse models for sub-second responses.

The travel assistant handles four distinct operational domains:

1. **Itinerary modification**: Inserting, reordering, and deleting time-slotted POIs across a multi-day timeline.
2. **Expense tracking**: Parsing multilingual receipts and logging multi-currency travel expenses (JPY, TWD, USD, EUR) to an active budget.
3. **Live fact-checking and web research**: Querying live transport timetables, real-time weather alerts, and official opening hours.
4. **Conversational guidance**: Cultural context, dietary translation, and general itinerary critique.

The core engineering problem this harness had to solve was **tool overload on latency-critical mobile devices**. When travelers walk down a street in Tokyo or Kyoto, they expect an answer in under a second. If an agent loads every possible tool schema on every turn, it pays a massive latency penalty before generating a single word, and it frequently triggers state-mutating tools when the user only asked a casual question.

This note documents the failure of a naive monolithic tool architecture and the two-stage hybrid router we built to replace it.

---

## The naive failure: monolithic toolsets and tool confusion

In our first release, we followed standard framework tutorials: define all tools, bundle them into a single list (`ALL_CHAT_TOOLS`), and pass them to the model's chat completions call on every single message.

The bundled toolset contained the 6 production schemas defined in `backend/services/model_manager.py`:

- `add_itinerary_item` (nested sub-items, lat/lng coordinates, transport mode, and category schema: ~980 tokens / 3,939 chars)
- `remove_itinerary_item` (place name, day number, and target item ID: ~180 tokens / 719 chars)
- `add_expense` (amount, currency code, payment method, category, and line items: ~530 tokens / 2,117 chars)
- `search_web` (multi-provider live search query and site filter: ~150 tokens / 611 chars)
- `fetch_webpage` (clean markdown extractor with CSS selector targeting: ~180 tokens / 739 chars)
- `get_world_time` (IANA timezone query and operating hours converter: ~150 tokens / 602 chars)

This naive setup broke in two distinct ways:

### 1. Prefill latency penalty (The KV-cache tax)

The JSON schemas for these 6 tools consumed **~1,840 to 2,180 tokens** (8,727 characters of JSON schema definition) per turn. Because mobile user prompts are short (median 18 tokens, e.g., _"Good morning"_ or _"Where is the nearest coin locker?"_), the tool definitions accounted for over **98% of the input context**.

On cloud API endpoints, prefilling these 1,840 tokens repeatedly inflated our median Time-To-First-Token (TTFT) from **340ms to 2,180ms**. For a mobile traveler waiting on a train platform, waiting over two seconds for a simple _"Good morning, ready for Day 2?"_ felt broken.

### 2. Attention dilution and tool false positives

When all tools were active, the model suffered from severe tool confusion on nuanced conversational inputs:

- When a user asked: _"Is 1,500 yen expensive for a bowl of ramen around Shibuya?"_, the model repeatedly invoked `add_expense(amount=1500, currency="JPY", title="ramen")`. The user was asking for price calibration, not logging an expenditure.
- When a user said: _"I don't think I want to visit Senso-ji anymore"_, the model sometimes invoked `add_itinerary_item` instead of `remove_itinerary_item`, hallucinating an addition of a replacement temple.

Passing all tools simultaneously made the model's tool choice nondeterministic on conversational edge cases.

---

## The two-stage hybrid harness architecture

To eliminate schema bloat and tool confusion, we decoupled intent classification from full reasoning by building a **Hybrid Two-Stage Router with Dynamic Tool Gating (H2S-TRDG)**.

The architecture combines deterministic code rules (System 1: 0ms execution) with a bounded small-model semantic classifier (System 2: 1.0s timeout), dynamically pruning the toolset before the flagship model ever sees the prompt.

| Stage                  | Mechanism                                       | Latency Scope                        | Tools Loaded into Flagship Model                                      |
| ---------------------- | ----------------------------------------------- | ------------------------------------ | --------------------------------------------------------------------- |
| **Stage 1: Fast-Path** | Deterministic Regex & Keyword State Machine     | **< 1 ms** (CPU)                     | None (chat), 1–2 (domain/composite), or all 6 deployed tools (search) |
| **Stage 2: Workhorse** | Open-weights 31B Dense Model (`gemma-4-31b-it`) | **300 - 600 ms** (Classifier call)   | 1–2 (domain/composite), or all 6 deployed tools (search)              |
| **Fallback Gate**      | Circuit-breaker timeout on Stage 2 (> 1.0s)     | **~1.0 s** (Classifier cancel limit) | Strips all tools (`CHAT`: `[]`); flagship explains safely             |

```mermaid
flowchart TD
    UserMsg[User Message] --> Stage1{Stage 1: 0ms Deterministic Regex}

    %% Fast path routes
    Stage1 -- "Pure Greeting / Thanks" --> FastChat[Intent: CHAT<br/>Tools: EMPTY]
    Stage1 -- "Explicit Removal Pattern" --> FastRemove[Intent: REMOVE_ITINERARY<br/>Tools: [REMOVE_TOOL]]
    Stage1 -- "Confirmed Expense Syntax" --> FastExpense[Intent: EXPENSE<br/>Tools: [EXPENSE_TOOL]]
    Stage1 -- "Explicit Search Trigger / URL" --> FastSearch[Intent: SEARCH<br/>Tools: Deployed ALL_CHAT_TOOLS]

    %% Ambiguous route
    Stage1 -- "Unmatched / Complex query" --> Stage2["Stage 2: 31B Workhorse Classifier<br/>(gemma-4-31b-it with 1.0s Timeout)"]

    Stage2 -- "Returns valid JSON <= 1.0s" --> PrunedInject[Inject Pruned Domain Toolset]
    Stage2 -- "Timeout > 1.0s or Error" --> SafeFallback[Fallback Gate: Intent CHAT, Tools EMPTY]

    FastChat --> Flagship[Flagship LLM Reasoning Engine]
    FastRemove --> Flagship
    FastExpense --> Flagship
    FastSearch --> Flagship
    PrunedInject --> Flagship
    SafeFallback --> Flagship

    Flagship --> ClientStream[Stream Response to User]
```

---

## Stage 1: Deterministic fast-path (System 1)

Stage 1 runs entirely in local Python memory before any remote network call, evaluating the stripped message directly against compiled regular expressions. (Input length truncation occurs separately in Stage 2, where `eval_text[:200]` caps prompt length before calling the classifier model).

### 1. Short-circuiting conversational turns

If a message is short and matches common greetings or acknowledgments, Stage 1 immediately assigns the intent `CHAT` and **strips all tool definitions completely**:

```python
GREETING_PATTERN = re.compile(
    r"^[\s]*(你好|您好|哈囉|hello|hi|hey|早安|午安|晚安|謝謝|感謝|thx|thanks|3q)[\s\!！\?？\.\~]*$",
    re.IGNORECASE
)

def _fast_path_classify(message: str) -> Optional[str]:
    trimmed = message.strip()
    # Unload all tools for simple greetings: 0ms, 0 tokens, 0% tool hallucination
    if len(trimmed) <= 8 and GREETING_PATTERN.match(trimmed):
        return "CHAT"
    ...
```

By unloading tool definitions on greetings, TTFT dropped from 2,180ms to 320ms, and the model never generated unwanted tool cards.

### 2. Heuristic Tool Exposure vs. Mutation Authorization

Stage 1 uses keyword heuristics to prune candidate tool schemas:

```python
EXPENSE_PATTERN = re.compile(
    r"(\b\d+[\.,]?\d*\s*(日圓|日幣|円|twd|nt\$|usd|jpy|eur)\b|(記帳|花了|買了|付了|餐費|車資))",
    re.IGNORECASE
)

# Reject questions containing price-inquiry markers
is_price_inquiry = bool(re.search(r"(多少|幾|嗎|？|\?|預算|預估|貴不貴|貴嗎|划算嗎)", trimmed))
has_expense = bool(EXPENSE_PATTERN.search(trimmed)) and not is_price_inquiry

if has_expense:
    return "EXPENSE"
```

**Boundary Limitation**: This pattern represents **heuristic tool exposure**, not an authorization boundary. For example, negative phrasing such as _"我不想記帳"_ matches `EXPENSE_PATTERN` while skipping `is_price_inquiry`, thereby routing to `EXPENSE` and exposing the tool.

True mutation safety is enforced downstream:

1. The flagship model interprets semantic negation in context and avoids calling the tool.
2. In Tabiji's frontend, state-mutating actions (such as `add_itinerary_item` and expense creation) are gated behind interactive Human-in-the-Loop cards (`components/chat/POIPreviewCard.tsx` / `components/chat/ExpensePreviewCard.tsx`) requiring user confirmation before committing changes to IndexedDB.

---

## Stage 2: 31B semantic classification with bounded timeout (System 2)

If Stage 1 cannot classify the input with high certainty (for instance: _"Let's find somewhere quiet near Ueno after the museum"_), the query enters Stage 2.

Here, an open-weights 31B dense model (`gemma-4-31b-it`, backed by `WORKHORSE_ROUTING` in `backend/utils/ai_config.py`, accessed via Google's hosted GenAI API endpoint) receives a strict JSON-only classification prompt. To ensure pre-classification does not stall the pipeline, the call is wrapped in `asyncio.wait_for` set to a **1.0-second timeout**:

```python
async def _workhorse_classify(message: str, api_key: Optional[str] = None) -> str:
    prompt = CHAT_INTENT_PROMPT.format(message=message[:200])
    try:
        raw_text = await asyncio.wait_for(
            call_extraction_server(prompt, intent_type="INTENT_PARSE", api_key=api_key),
            timeout=1.0  # Configured classifier timeout
        )
        match = re.search(r'\{[\s\S]*\}', raw_text)
        if match:
            data = json.loads(match.group())
            return intent_map.get(data.get("intent", "").lower(), "CHAT")
    except (asyncio.TimeoutError, Exception) as err:
        # Graceful degradation: never crash, fall back to pure CHAT (no tools)
        logger.warning(f"Stage 2 router timed out or failed ({err}); falling back to CHAT")
        return "CHAT"
    return "CHAT"
```

### Timeout Scope and Cancellation

`asyncio.wait_for(..., timeout=1.0)` acts as a bounded cancellation threshold for the pre-classification stage rather than a hard real-time guarantee. In Python's asyncio, cancellation is scheduled asynchronously, and network socket cleanup may take additional cycles. Downstream flagship invocation and streaming occur after Stage 2 and are governed by separate request-level timeouts. When Stage 2 times out, the router safely assigns `CHAT`, which strips all tools (`[]`) and allows the flagship model to answer conversationally.

---

## Dynamic toolset injection

Once the intent is determined, the dispatcher injects schemas into the flagship invocation:

```python
# Extracted from backend/services/intent_router.py (Commit 4603b22)
tool_map = {
    "CHAT": [],                                    # 0 schemas injected
    "ITINERARY": [ADD_ITINERARY_TOOL],             # 1 schema injected
    "REMOVE_ITINERARY": [REMOVE_ITINERARY_TOOL],   # 1 schema injected
    "EXPENSE": [EXPENSE_TOOL],                     # 1 schema injected
    "SEARCH": ALL_CHAT_TOOLS,                      # Deployed operational toolset
    "COMPOSITE": [ADD_ITINERARY_TOOL, EXPENSE_TOOL]# 2 schemas injected
}
```

_Note on Deployed vs. Target Contracts_: In our deployed repository (commit `4603b22`), `SEARCH` currently maps to `ALL_CHAT_TOOLS` as a pragmatic accommodation for composite search-and-add user journeys. Our isolated benchmark target profile maps `SEARCH` strictly to `SEARCH_TOOLS` (`search_web` + `fetch_webpage`, 1,350 characters of schema), reducing injected tokens from ~1,840 to ~420 tokens.

---

## Measured production impact

We evaluated this architecture in the Tabiji project, recording operational metrics across pre-release testing and production telemetry. The production metrics below reflect the **deployed operational configuration** (where `SEARCH` maps to all 6 tools `ALL_CHAT_TOOLS`). The substantial token and latency savings are driven by workload composition: 43.8% of turns are zero-token `CHAT` queries, and single-tool actions (180–980 tokens) dominate over search queries, yielding a 380-token weighted average per turn across production sessions:

| Metric                             | Monolithic Baseline (`ALL_CHAT_TOOLS`) | Hybrid Two-Stage Router (H2S-TRDG) | Change                              |
| ---------------------------------- | -------------------------------------- | ---------------------------------- | ----------------------------------- |
| **P50 TTFT (Time-To-First-Token)** | 2,180 ms                               | **340 ms**                         | **-84.4%** ⚡                       |
| **P99 Tail Latency**               | 3,850 ms                               | **1,120 ms**                       | **-70.9%** 🚀                       |
| **Schema Token Overhead per Turn** | 1,840 tokens                           | **380 tokens** (avg)               | **-79.3%** 💰                       |
| **Tool False Positive Rate**       | 4.6% (Synthetic baseline)              | **< 0.12%** (Observed production)  | _Complementary observations_ 🎯     |
| **Stage 1 Fast-Path Hit Rate**     | N/A (0%)                               | **43.8% of user turns**            | _Zero router latency / Zero tokens_ |
| **Stage 2 Timeout Trip Rate**      | N/A                                    | **0.8% of Stage 2 calls**          | _Degraded to CHAT without crashing_ |

### Measurement Cohort Caveats

- **Evaluated Configuration**: Production numbers reflect the deployed router mapping `SEARCH` to `ALL_CHAT_TOOLS`. The target profile (`SEARCH_TOOLS` = 2 tools / ~420 tokens) was measured in an isolated synthetic benchmark where search queries averaged 420 schema tokens rather than ~1,840 tokens.
- **Unit of Analysis**: Conversational turns (single user prompt-response pairs).
- **False-Positive Criteria**: Unintended state-mutating tool invocations (e.g., `add_expense` triggered on price inquiries or `add_itinerary_item` on cancellations).
- **Cohort Distinction**: The 4.6% baseline false-positive rate was measured on a pre-release benchmark of 500 synthetic edge-case queries. The < 0.12% rate reflects post-deployment telemetry across 1,200 multi-turn mobile sessions (~3,800 turns). Because these cohorts differ in prompt complexity and distribution, they represent separate observational data points rather than a perfectly matched A/B trial.

---

## What the gates cost me

This architecture solved our mobile latency and tool confusion problems, but it introduced distinct maintenance costs:

1. **Regex maintenance burden**: Language is messy. As users tried new phrases, our Stage 1 regex list grew. In bilingual or multilingual environments (e.g., users mixing English, Japanese kanji, and Traditional Chinese), regex patterns require careful regression testing to avoid false negatives.
2. **Two LLM calls on Stage 2 hits**: When Stage 1 misses, the system makes two sequential API calls: the 31B classifier (~350ms) followed by the flagship reasoning model. While total TTFT remained well below the monolithic baseline (because the flagship model's prompt was dramatically shorter), it does add complexity to distributed tracing and billing reconciliation.
3. **Composite intent fragmentation**: Users occasionally combine intents in a single sentence: _"Add Tokyo Skytree to Day 2 and record 2,500 yen for the ticket."_ Handling this required building a dedicated `COMPOSITE` branch that loads both tools, rather than assuming a single-label classification model.

---

## Connections to the course

| Rule in the pipeline                      | Course concept                                                                                                            | Why the connection holds                                                                                                 |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Dynamic tool gating via `tool_map`        | [Learning and selecting tools](../concepts/learning-and-selecting-tools.md)                                               | Pre-filtering tools preserves attention and avoids schema bloat.                                                         |
| Stage 1 regex vs. Stage 2 semantic model  | [Workflows versus agents](../concepts/workflows-vs-agents.md)                                                             | Code deterministically defines execution boundaries (workflow), while the LLM resolves semantic parameters (agent).      |
| Bounded 1.0s timeout with `CHAT` fallback | [Agent harness design](../concepts/agent-harness-design.md)                                                               | The harness encloses the pre-classifier with bounded latency, ensuring graceful degradation under network stalls.        |
| Stripping tools on conversational turns   | [Prefill, decode, and the KV cache](../concepts/prefill-decode-and-kv-cache.md)                                           | Eliminates schema prefill overhead on simple conversational turns.                                                       |
| Heuristic gating + `POIPreviewCard`       | [Structured output and validation](../concepts/structured-output-and-validation.md)                                       | Regex provides heuristic tool exposure; Human-in-the-Loop UI confirms actual state mutation.                             |
| Gemma 31B workhorse pre-routing           | [Lecture 2: Language model inference](../lectures/02-llms-for-builders.md#part-4-language-model-inference-slides-119-148) | Uses a cost-effective, low-latency 31B dense model for lightweight classification before invoking the flagship reasoner. |

---

## Open questions

1. **Embedding classification vs. small LLM**: Could a local small embedding model (e.g. running via ONNX WebAssembly in the client or server memory) replace the 31B Stage 2 classifier entirely, reducing Stage 2 latency from 350ms to < 20ms without losing semantic nuance?
2. **Dynamic schema generation**: Instead of pruning static schemas, could the router dynamically synthesize a single custom tool schema containing only the fields relevant to the current conversation turn?
3. **Multilingual generalization**: How can deterministic fast-paths scale to 10+ languages without exploding regex complexity? Is there a principled boundary between code-based pattern matching and lightweight token-level classification?

---

## Evidence boundary

The snippets and data quoted above are drawn directly from `backend/services/intent_router.py`, `backend/services/model_manager.py`, and `backend/utils/ai_config.py` in [Tabiji at commit `4603b22`](https://github.com/tyrantpiper/tabiji/commit/4603b22c6a261cc4ae5542882b2f91131874d786). Schema token lengths are calculated from the serialized JSON declarations in `ALL_CHAT_TOOLS` (8,727 characters) and `SEARCH_TOOLS` (1,350 characters). The 1,200-session telemetry data was captured between September and October 2026. The 4.6% baseline was evaluated on an earlier monolithic build across 500 synthetic test queries. The 1.0s threshold was configured empirically based on our mobile TTFT budget.
