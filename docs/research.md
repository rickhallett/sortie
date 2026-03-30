# Research: Adversarial Multi-Model Code Review

Academic papers, empirical findings, and theoretical foundations informing sortie's design.

---

## Core Thesis

Models from different labs have different blind spots. Cross-family verification catches errors that same-model ensembles miss. Code is an ideal domain for multi-model verification because correctness has verifiable structure.

---

## Cross-Model Verification

**ReConcile: Round-Table Conference Improves Reasoning via Consensus among Diverse LLMs**
Chen, Saha, Bansal. ACL 2024.
Models from different families (ChatGPT, Bard, Claude 2) in multi-round discussion with confidence-weighted voting outperform single-model or same-family debate. Diversity across model families is the critical factor.
[arxiv.org/abs/2309.13007](https://arxiv.org/abs/2309.13007)

**When Does Verification Pay Off? A Closer Look at LLMs as Solution Verifiers**
arXiv, December 2024.
LLMs exhibit "self-enhancement bias" -- they accept incorrect solutions resembling their own reasoning patterns. Cross-family verifiers mitigate this. Verification yields largest gains on tasks with verifiable structure (logic, math, code).
[arxiv.org/abs/2512.02304](https://arxiv.org/abs/2512.02304)

**M2CVD: Enhancing Vulnerability Semantic through Multi-Model Collaboration for Code Vulnerability Detection**
Wang et al. ACM TOSEM, 2025.
Collaboration between LLMs and fine-tuned code models significantly outperforms either alone on real-world vulnerability detection.
[arxiv.org/abs/2406.05940](https://arxiv.org/abs/2406.05940)

**Evaluating Large Language Models for Code Review**
arXiv, May 2025.
GPT-4o and Gemini 2.0 Flash correctly classified code correctness 68.50% and 63.89% respectively -- neither dominates, different models have different blind spots.
[arxiv.org/abs/2505.20206](https://arxiv.org/abs/2505.20206)

---

## LLM-as-Judge for Code

**LLM-as-a-Judge for Software Engineering: Literature Review, Vision and the Road Ahead**
Zhuo, Treude. arXiv, October 2025.
Systematic review of 42 studies. The paradigm is execution-free, reference-free, and enables multi-facet evaluation. Identifies gaps in reliability, bias, reproducibility.
[arxiv.org/abs/2510.24367](https://arxiv.org/abs/2510.24367)

**From Code to Courtroom: LLMs as the New Software Judges**
arXiv, March 2025.
Three distinguishing characteristics: execution-free assessment, reference-free evaluation, multi-facet scoring of intrinsic code qualities.
[arxiv.org/abs/2503.02246](https://arxiv.org/abs/2503.02246)

**CodeJudge: Evaluating Code Generation with Large Language Models**
Tong, Zhang. EMNLP 2024.
Uses a taxonomy of common programming errors to guide LLM analysis, then summarizes to produce judgment -- evaluation without test cases or reference solutions.
[arxiv.org/abs/2410.02184](https://arxiv.org/abs/2410.02184)

**CodeJudgeBench: Benchmarking LLM-as-a-Judge for Coding Tasks**
arXiv, July 2025.
5,352 samples from competitive programming. "Thinking" models (o1, QwQ) drastically outperform standard instruction-tuned models as code judges. Models fine-tuned to be judges performed poorly on code.
[arxiv.org/abs/2507.10535](https://arxiv.org/abs/2507.10535)

**Don't Judge Code by Its Cover: Exploring Biases in LLM Judges for Code Evaluation**
arXiv, May 2025.
Six types of bias defined. All tested judges (GPT-4o, Gemini, Claude, LLaMA) are susceptible. GPT-4o accuracy drops by up to 26.7pp under biased conditions. Generating test cases before scoring does not mitigate.
[arxiv.org/abs/2505.16222](https://arxiv.org/abs/2505.16222)

**AXIOM: Benchmarking LLM-as-a-Judge for Code via Rule-Based Perturbation**
Wang et al. arXiv, December 2025.
45 perturbation rules applied to high-quality programs create balanced benchmarks. Previous benchmarks suffer from coarse labels or vague criteria.
[arxiv.org/abs/2512.20159](https://arxiv.org/abs/2512.20159)

---

## Multi-Agent Debate and Verification

**Improving Factuality and Reasoning in Language Models through Multiagent Debate**
Du, Li, Torralba, Tenenbaum, Mordatch. ICML 2024.
The foundational multi-agent debate paper. Multiple LLM instances propose and debate over rounds. Significantly enhances reasoning, reduces hallucinations. Directly applicable to black-box models.
[arxiv.org/abs/2305.14325](https://arxiv.org/abs/2305.14325)

**Towards Scalable Oversight with Collaborative Multi-Agent Debate in Error Detection (ColMAD)**
arXiv, October 2025.
Reframes debate as a non-zero-sum collaborative game. Achieves +4% improvement vs single-agent. Competitive debate *decreases* performance by up to 15%.
[arxiv.org/abs/2510.20963](https://arxiv.org/abs/2510.20963)

**AgentCoder: Multi-Agent-based Code Generation with Iterative Testing and Optimisation**
Huang et al. arXiv, December 2023.
Three-agent system (programmer, test designer, executor) achieves 96.3% pass@1 on HumanEval vs 90.2% SOTA, with lower token overhead (56.9K vs 138.2K).
[arxiv.org/abs/2312.13010](https://arxiv.org/abs/2312.13010)

**ChatDev: Communicative Agents for Software Development**
Qian et al. ACL 2024.
Multi-agent system with 7 roles using chat-chain communication. Cooperative communication through blend of natural and programming languages raises code quality vs document-passing approaches.
[arxiv.org/abs/2307.07924](https://arxiv.org/abs/2307.07924)

**Multi-Agent Debate Strategies to Enhance Requirements Engineering with Large Language Models**
arXiv, July 2025.
First application of multi-agent debate to requirements engineering. As of early 2025, no prior papers applied MAD to SE domain specifically.
[arxiv.org/abs/2507.05981](https://arxiv.org/abs/2507.05981)

**LLM-Based Multi-Agent Systems for Software Engineering: Literature Review**
He, Treude et al. arXiv, April 2024.
Comprehensive survey. Multi-agent architectures for code review and verification are still nascent compared to code generation.
[arxiv.org/abs/2404.04834](https://arxiv.org/abs/2404.04834)

---

## Convergence and Consensus Mechanisms

**Voting or Consensus? Decision-Making in Multi-Agent Debate**
Kaesberg, Becker, Wahle, Ruas, Gipp. ACL 2025 Findings.
Systematic evaluation of 7 decision protocols. Voting improves by 13.2% on reasoning tasks; consensus by 2.8% on knowledge. More rounds before voting *reduces* performance.
[arxiv.org/abs/2502.19130](https://arxiv.org/abs/2502.19130)

**Free-MAD: Consensus-Free Multi-Agent Debate**
Cui, Fu, Zhang. arXiv, September 2025.
Anti-conformity mechanism prevents majority influence from corrupting correct minority. Score-based on full trajectory, not final round. Reduces token costs to single-round.
[arxiv.org/abs/2509.11035](https://arxiv.org/abs/2509.11035)

**Probabilistic Consensus through Ensemble Validation**
Naik. arXiv, November 2024.
Precision: 73.1% (1 model) to 93.9% (2 models) to 95.6% (3 models). Cohen's kappa > 0.76.
[arxiv.org/abs/2411.06535](https://arxiv.org/abs/2411.06535)

**The Six Sigma Agent: Enterprise-Grade Reliability through Consensus-Driven Decomposed Execution**
arXiv, January 2026.
5 agents with 5% per-action error → 0.11% system error via consensus. Error scales as O(p^{ceil(n/2)}). Even cheap models achieve enterprise reliability through consensus.
[arxiv.org/abs/2601.22290](https://arxiv.org/abs/2601.22290)

**DiscoUQ: Structured Disagreement Analysis for Uncertainty Quantification in LLM Agent Ensembles**
arXiv, March 2026.
Structure of disagreement (evidence overlap, argument strength, divergence depth) matters more than presence. AUROC 0.802, best cost-performance: 1 extra LLM call per ambiguous case.
[arxiv.org/abs/2603.20975](https://arxiv.org/abs/2603.20975)

**Beyond Majority Voting: LLM Aggregation by Leveraging Higher-Order Information**
arXiv, October 2025.
Optimal Weight and Inverse Surprising Popularity algorithms use second-order information (what models predict others will say), provably mitigating limitations of majority voting.
[arxiv.org/abs/2510.01499](https://arxiv.org/abs/2510.01499)

**Debate, Deliberate, Decide (D3): A Cost-Aware Adversarial Framework**
arXiv, October 2024.
Structured debate with role-specialized agents. Two protocols: parallel advocacy (MORE) and iterative refinement (SAMRE) with explicit token budgets and convergence checks.
[arxiv.org/abs/2410.04663](https://arxiv.org/abs/2410.04663)

---

## Economics of Multi-Model Review

**RovoDev Code Reviewer: Large-Scale Online Evaluation at Atlassian**
arXiv, January 2026.
12-month deployment, 2,000+ repos, 54,000+ review comments. Real enterprise cost-benefit data on LLM code review at scale.
[arxiv.org/abs/2601.01129](https://arxiv.org/abs/2601.01129)

**Rethinking Code Review Workflows with LLM Assistance: An Empirical Study**
arXiv, May 2025.
Empirical study of how LLM assistance changes code review workflows, including time and cost tradeoffs.
[arxiv.org/abs/2505.16339](https://arxiv.org/abs/2505.16339)

---

## Benchmarks

**c-CRAB: Code Review Agent Benchmark**
arXiv, March 2026.
Current AI review identifies ~40% of issues human reviewers catch. Evaluates PR-Agent, Devin Review, Claude Code, Codex.
[arxiv.org/abs/2603.23448](https://arxiv.org/abs/2603.23448)

**CR-Bench: Evaluating the Real-World Utility of AI Code Review Agents**
arXiv, March 2026.
Introduces usefulness rate and signal-to-noise ratio for measuring developer acceptance.
[arxiv.org/abs/2603.11078](https://arxiv.org/abs/2603.11078)

**A Survey of Code Review Benchmarks and Evaluation Practices**
arXiv, February 2026.
156 datasets from 142 studies covering 32 code tasks (Jan 2020 -- June 2025).
[arxiv.org/abs/2602.13377](https://arxiv.org/abs/2602.13377)

---

## Key Implications for Sortie

1. **Cross-family triad is validated.** ReConcile confirms different families > same-family ensembles. Self-enhancement bias makes same-model review unreliable.

2. **Collaborative debrief, not competitive debate.** ColMAD shows competitive debate hurts (-15%). Sortie's debrief is collaborative synthesis -- correct choice.

3. **Convergence threshold of 2 is near-optimal.** 73% → 94% with 2 models, only 96% with 3. Diminishing returns confirm the default.

4. **Divergent findings as advisory is backed by Free-MAD.** Minority findings may be correct -- logging without blocking preserves the signal.

5. **Code is the ideal domain.** Verifiable structure means verification consistently pays off (unlike factual recall tasks).

6. **Current AI review catches ~40% of human findings.** Multi-model is additive -- three models catching different 40% slices significantly closes the gap.
