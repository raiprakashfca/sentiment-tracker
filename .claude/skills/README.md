# Project skills

Skills vendored from upstream repositories (see the inventory that drove this). Each folder is a standard Claude Code skill (`SKILL.md` + assets).

Not included (authored locally on the original machine, no public source): `ai-engineering-standard`, `startup-pipeline`, `website-build-stack`, `yalla-agent-stack`.

| Upstream | Skills |
|---|---|
| https://github.com/obra/superpowers | brainstorming dispatching-parallel-agents executing-plans finishing-a-development-branch receiving-code-review requesting-code-review subagent-driven-development systematic-debugging test-driven-development using-git-worktrees using-superpowers verification-before-completion writing-plans writing-skills |
| https://github.com/coreyhaines31/marketingskills | ad-creative ai-seo copy-editing copywriting cro launch marketing-ideas marketing-plan paywalls pricing product-marketing programmatic-seo prospecting schema social |
| https://github.com/Jeffallan/claude-skills | architecture-designer code-documenter code-reviewer prompt-engineer rag-architect react-expert secure-code-guardian security-reviewer sre-engineer websocket-engineer |
| https://github.com/anthropics/skills | brand-guidelines doc-coauthoring frontend-design web-artifacts-builder webapp-testing |
| https://github.com/anthropics/knowledge-work-plugins | accessibility-review design-critique research-synthesis user-research ux-copy campaign-plan email-sequence compliance-check vendor-check competitive-intelligence content-strategy tax-prep org-planning risk-assessment status-report system-design product-brainstorming write-spec brand-voice-enforcement guideline-generation |
| https://github.com/daymade/claude-code-skills | fact-checker i18n-expert product-analysis prompt-optimizer promptfoo-evaluation scrapling-skill youtube-downloader mermaid-tools skills-search |
| https://github.com/addyosmani/agent-skills | idea-refine planning-and-task-breakdown |
| https://github.com/pbakaus/impeccable | impeccable |
| https://github.com/emilkowalski/skill | emil-improve-animations (upstream: improve-animations) |
| https://github.com/nextlevelbuilder/ui-ux-pro-max-skill | design-system |
| https://github.com/diegosouzapw/OmniRoute | omniroute-cli-serve (upstream: cli-serve) |
| https://github.com/PaddlePaddle/PaddleOCR | paddleocr-doc-parsing paddleocr-text-recognition |
| https://github.com/ruvnet/ruflo | pii-detect security-audit |
| https://github.com/calesthio/OpenMontage | gsap-scrolltrigger web-design-guidelines openmontage-canvas-procedural-animation openmontage-music openmontage-video-understand (upstream: without the openmontage- prefix) |
| https://github.com/trailofbits/skills | audit-prep-assistant code-maturity-assessor diagramming-code second-opinion ask-questions-if-underspecified (recovered from git history; removed upstream) |
| https://github.com/c0x12c/ai-toolkit | article-writing backend-api-design competitive-teardown content-engine market-research python-testing-strategies |
| https://github.com/Panniantong/Agent-Reach | agent-reach-internet-router (upstream: agent-reach) |
| https://github.com/safishamsi/graphify | graphify (installed via `graphify install --project`; CLI: `pip install graphifyy`) |
| https://github.com/rebelytics/one-skill-to-rule-them-all | task-observer |

## CLIs some skills expect

| CLI | Install | Used by |
|---|---|---|
| `graphify` | `pip install graphifyy` | graphify (hooks in `.claude/settings.json`) |
| `scrapling` | `pip install "scrapling[all]"` | scrapling-skill |
| `yt-dlp` | `pip install yt-dlp` | youtube-downloader |
| `paddleocr` | `pip install paddleocr` | paddleocr-* |
| `promptfoo` | `npm i -g promptfoo` | promptfoo-evaluation |
| `mmdc` | `npm i -g @mermaid-js/mermaid-cli` | mermaid-tools |
| `omniroute` | `npm i -g omniroute` | omniroute-cli-serve |
| `agent-reach` | see upstream README | agent-reach-internet-router |
