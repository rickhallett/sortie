# Landscape: Repos and Tools

Catalogued March 2026. Tools implementing adversarial, multi-model, or ensemble code review patterns.

---

## Tier 1: Direct Adversarial Code Review

Tools where multiple models review the same code and findings are compared.

| Tool | Author | Pattern | Novel Mechanism |
|---|---|---|---|
| [adversarial-review](https://github.com/alecnielsen/adversarial-review) | alecnielsen | 4-phase debate: independent, cross-review, meta-review, synthesis | Circuit breaker (max 21 API calls), true adversarial cross-validation |
| [adversarial-spec](https://github.com/zscole/adversarial-spec) | zscole | Iterative spec refinement via multi-LLM debate | Anti-rubber-stamping: early agreement forces deeper review |
| [claude-review-loop](https://github.com/hamelsmu/claude-review-loop) | hamelsmu | Claude writes, Codex reviews via Stop hook | Single-hook inter-agent handoff |
| [ai-code-reviewer](https://github.com/PierrunoYT/ai-code-reviewer) | PierrunoYT | Pre-commit/pre-push hooks triggering GPT + Claude + Gemini | Provider-tailored prompts, 30% token efficiency gain |
| [agent-debate](https://github.com/gumbel-ai/agent-debate) | gumbel-ai | Shared markdown file, agents use strikethrough to disagree | Evidence-backed (must cite file:line), converge-or-escalate |
| [multi_mcp](https://github.com/religa/multi_mcp) | religa | MCP server bridging API and CLI models | Bridges API + CLI invocation, CI pipeline mode |
| [CodeDebate](https://github.com/longyunfeigu/codedebate) | longyunfeigu | Models independently review then challenge each other | Auto-convergence detection, configurable round limits |
| [CRTX](https://github.com/CRTXAI/CRTX) | CRTXAI | Generate, test, fix, review with independent Arbiter | 3 escalation tiers, Arbiter always different model |
| [claude-consensus](https://github.com/AltimateAI/claude-consensus) | AltimateAI | Multiple models review independently then converge | Configurable quorum, 7+ models via OpenRouter |
| [OmniReview](https://github.com/nexiouscaliver/OmniReview) | nexiouscaliver | 3 agents in isolated worktrees with distinct roles | Cross-referenced, confidence-scored findings |
| [LLM Peer Review](https://github.com/mayankmankhand/llm-peer-review) | mayankmankhand | 3-round adversarial debate between Claude/GPT/Gemini | Structured agree/disagree output, human approval gate |

---

## Tier 2: Multi-Model Orchestration with Review

Broader orchestration frameworks that include adversarial review as one component.

| Tool | Author | Pattern | Novel Mechanism |
|---|---|---|---|
| [metaswarm](https://github.com/dsifry/metaswarm) | dsifry | "Writer never self-reviews" rule | 6-agent design review gate, unanimous or escalate |
| [claude-octopus](https://github.com/nyldn/claude-octopus) | nyldn | Triple mode: parallel/sequential/adversarial | 75% consensus quality gate, 32 personas |
| [Claude-Collab](https://github.com/Vision-Empower/Claude-Collab) | Vision-Empower | Enforced diversity with anti-groupthink | 30% mandatory dissent quota, 0.6 diversity threshold |
| [claude-code-my-workflow](https://github.com/pedrohcgs/claude-code-my-workflow) | pedrohcgs | Blind review (auditors isolated from each other) | Prevents anchoring bias, adversarial critic/fixer loop |
| [claude-code-skills](https://github.com/levnikolaevich/claude-code-skills) | levnikolaevich | Multi-model AI review with Codex + Gemini | 4-level quality gate (PASS/CONCERNS/REWORK/FAIL) |
| [claude-code-agentic-research-orchestrator](https://github.com/weorbitant/claude-code-agentic-research-orchestrator) | weorbitant | Three-way perspective synthesis | Task-based model selection |
| [OpenLens](https://github.com/Traves-Theberge/openlens) | Traves-Theberge | Pre-commit/pre-push hooks with parallel agents | SARIF output, confidence scoring, severity thresholds |
| [CrossCheck](https://github.com/sburl/CrossCheck) | sburl | Swiss cheese model: hooks + tests + multi-model review | Different model from different lab reviews each PR |

---

## Tier 3: Consensus and Ensemble Engines

General-purpose multi-model consensus tools applicable to code review.

| Tool | Author | Pattern | Novel Mechanism |
|---|---|---|---|
| [duh](https://github.com/msitarzewski/duh) | msitarzewski | Multi-model debate with preserved dissent | Minority opinions kept in record, full audit trail |
| [Consensus](https://github.com/duke-of-beans/Consensus) | duke-of-beans | Enterprise multi-model verification | Veto authority (any model can block), "Sacred Laws" |
| [ai-consensus](https://github.com/niftymonkey/ai-consensus) | niftymonkey | Iterative deliberation with evaluator | Configurable evaluator model, live demo |

---

## Tier 4: Multi-Agent Platforms

Platforms for running multiple coding agents in parallel.

| Tool | Author | Pattern | Novel Mechanism |
|---|---|---|---|
| [overstory](https://github.com/jayminwest/overstory) | jayminwest | Multi-agent orchestration with isolated worktrees | SQLite WAL messaging (~1-5ms), 4-tier conflict resolution |
| [parallel-code](https://github.com/johannesjo/parallel-code) | johannesjo | Desktop app: Claude + Codex + Gemini side by side | Mobile monitoring via QR code |
| [agent-orchestrator](https://github.com/ComposioHQ/agent-orchestrator) | ComposioHQ | Plans, spawns parallel agents, handles CI fixes | Full CI feedback loop, triple-agnostic |
| [pal-mcp-server](https://github.com/BeehiveInnovations/pal-mcp-server) | BeehiveInnovations | MCP server bridging all major CLIs | CLI subagent spawning, explicit consensus tool |
| [ruflo](https://github.com/ruvnet/ruflo) | ruvnet | Enterprise agent orchestration | Rust WASM policy engine, 3 swarm topologies |
| [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) | wanshuiyin | Overnight autonomous research with cross-model review | Zero-dependency markdown skills, Claude executes, GPT reviews |

---

## Tier 5: LLM-as-Judge Frameworks

Evaluation frameworks applicable to code review.

| Tool | Author | Description |
|---|---|---|
| [JudgeLM](https://github.com/baaivision/JudgeLM) | baaivision | Purpose-built judge models (7B/13B/33B), ICLR 2025 Spotlight. Bias mitigation via swap augmentation. |
| [OpenEvals](https://github.com/langchain-ai/openevals) | langchain-ai | Readymade LLM-as-judge evaluators with CI/CD integration. `create_llm_as_judge`. |
| [Awesome-LLM-as-a-judge](https://github.com/llm-as-a-judge/Awesome-LLM-as-a-judge) | llm-as-a-judge | Curated list including MCTS-Judge (tree search for code evaluation). |

---

## Tier 6: Gemini/Codex CLI Extensions

Building blocks for multi-model pipelines.

| Tool | Author | Description |
|---|---|---|
| [gemini-cli-extensions/code-review](https://github.com/gemini-cli-extensions/code-review) | Google | Official Code Review extension. `/pr-code-review` command. |
| [oh-my-gemini-cli](https://github.com/Joonghyun-Lee-Frieren/oh-my-gemini-cli) | Joonghyun-Lee-Frieren | Multi-agent team workflow pack. Sub-agent delegation, 4-phase orchestration. |

---

## Industry Implementations (Not Open Source)

| System | Company | Description |
|---|---|---|
| **HubSpot Sidekick** | HubSpot | Two-stage: reviewer agent + judge agent filters low-value comments. 90% faster TTF, 80% engineer approval. [InfoQ](https://www.infoq.com/news/2026/03/hubspot-ai-code-review-agent/) |
| **GitHub Agent HQ** | GitHub | Official multi-agent command center. Run Claude + Codex + Copilot simultaneously on same task. [Medium](https://medium.com/@sohail_saifi/githubs-agent-hq-lets-you-run-claude-codex-and-gemini-simultaneously-on-the-same-task-here-s-462c837116bc) |
| **RovoDev** | Atlassian | 12-month deployment, 2,000+ repos, 54,000+ review comments. [arxiv.org/abs/2601.01129](https://arxiv.org/abs/2601.01129) |
| **Qodo PR-Agent** | Qodo | Most mature open-source PR reviewer. GitHub Action, CLI, webhook. Single-model but multi-tool. |

---

## Patterns Summary

**Convergence mechanisms found across tools:**
- Anti-rubber-stamping (adversarial-spec): early agreement forces deeper review
- 75% consensus gate (claude-octopus)
- 30% mandatory dissent quota (Claude-Collab)
- Converge-or-escalate (agent-debate)
- Veto authority (Consensus)
- Preserved dissent (duh)

**Where sortie fits:**
Sortie is the only tool that combines all of: configurable model roster, parallel CLI invocation, 4th-model debrief synthesis with convergence analysis, severity-gated triage with configurable blocking, structured ledger for operational evaluation, and Claude Code Teams hook integration. Most tools do 2-3 of these; none do all 6.
