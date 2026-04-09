# CLAUDE.md — HackRadar: Hackathon Technology Discovery Pipeline

## WHO IS BUILDING THIS AND WHY

This project is being built by Rehan, a CS student at UT Austin (class of 2028) who competes in hackathons. He recently won his first hackathon (Hack Hack Goose by Freetail Hackers) by discovering Meta's TRIBE v2 brain activity prediction model — which had been released only 12 days before the event — and building NeuroDesign, an app that uses the model to compare how images activate different brain regions, rendered as interactive 3D brains with React Three Fiber.

The key insight from that win: **the technology itself was the competitive advantage, not the code.** Nobody else at the hackathon had even heard of TRIBE v2. It was buried in a Meta FAIR blog post, had zero existing products built on it, was completely free and open-source, and was deeply impressive and niche. Finding it before anyone else is what won the hackathon.

**The problem:** Rehan found TRIBE v2 by luck. There's no systematic way tover these kinds of hidden gems — bleeding-edge, open-source, niche, underexploited technology drops from research labs, open-source projects, new APIs, browser features, datasets, and tools. Existing aggregators (newsletters, trending pages) surface what's already popular. By the time something trends, 50 other hackathon teams have seen it too.

**The solution:** HackRadar — a daily automated pipeline that scrapes directly from the sources where new tech gets published (research blogs, arXiv, HuggingFace, GitHub, Hacker News, Product Hunt, browser platform updates, etc.), uses an LLM to score each item for hackathon viability based on Rehan's specific criteria, and a ranked of the top finds.

**The validation test:** If we run this pipeline as if the date were March 27, 2026 (the day after TRIBE v2 dropped), it MUST surface TRIBE v2 scored highly in the results — without any hardcoded bias tord it. If it doesn't catch TRIBE v2, the system has failed and needs to be fixed.

## REHAN'S PROFILE (context for scoring)

- **Stack:** React/Next.js, TypeScript, Python, PostgreSQL, React Three Fiber, Tailwind. Comfortable picking up new tools and frameworks quickly.
- **Compute access:** Free T4 GPUs via Google Colab/Kaggle. Can also use free tiers of various cloud services.
- **Hackathon style:** Finds bleeding-edge niche tech → builds an impressive interactive demo in 24-48 hours. The tech IS the project — the demo just makes it accessible.
- **Winning project exe:** NeuroDesign — took TRIBE v2 (brain activity prediction foundation model) + Gemma 4 + React Three Fiber to build an app where you compare how images activate different brain regions, visualized as interactive 3D brains. GitHub: https://github.com/rehanmollick/NeuroDesign
- **Interests:** EVERYTHING. Neuroscience, audio/music, robotics, biology, chemistry, computer vision, NLP, creative tools, hardware APIs, browser APIs, developer tools, games, AR/VR, blockchain if it's actually useful. Domain doesn't matter — wow-factor and novelttter.
- **Key strength:** Rehan uses Claude Code heavily and can automate significant portions of development. He's also willing to start working on setup/infrastructure days before a hackathon. So "buildability" should NOT be overly conservative — if something requires complex setup but is doable with AI-assisted coding and a few days of prep, that's still very viable.
- **Other tools:** Has Claude Max subscription, uses gstack (https://github.com/garrytan/gstack), MCP servers, sub-agents, git worktrees for parallel development.

## WHAT WE'RE BUILDING

A Python project (but you're free to use whatever language/tools make the most sense) that runs daily and:

1. **Scrapes** new technology relses from ~20+ sources
2. **Deduplicates** items that appear across multiple sources
3. **Enriches** items with metadata (GitHub stars, model size, license, etc.)
4. **Scores** each item using an LLM with hackathon-specific criteria

### Architecture Guidance

You have full flexibility on implementation details. The spec below is a guide, not a rigid constraint. If you find a better approach to any of these problems — a better library, a smarter architecture, a source I didn't think of — go for it. Use your judgment. The only hard requirements are:

It must be free or very low cost to run daily** (no paid APIs unless they have generous free tiers)
- **It must catch TRIBE v2 in the validation test**
- **It must be reliable** — if one source goes down, the rest should still work
- **It must be modular** — easy to add/remove sources over time
- **Email delivery must actually work**

---

## SOURCE LIST

### Category 1: AI Research Lab Blogs

These are the primary sources for "TRIBE v2-type" drops. Research labs quietly publish open-source models and tools on their blogs before any aggregator picks them up.

| Source | URL | Method |
|--------|-----|--------|
| Meta AI Blog | ai.meta.com/blog | RSS or scrape |
| Google DeepMind Blog | deepmind.google/blog | RSS or scrape |
| Google Research Bl blog.research.google | RSS or scrape |
| Microsoft Research Blog | microsoft.com/en-us/research/blog | RSS or scrape |
| Apple Machine Learning Research | machinelearning.apple.com | RSS or scrape |
| Stability AI Blog | stability.ai/blog | RSS or scrape |
| Mistral Blog | mistral.ai/news | RSS or scrape |
| NVIDIA Research / Developer Blog | developer.nvidia.com/blog | RSS or scrape |
| Anthropic Research | anthropic.com/research | RSS or scrape |
| OpenAI Research | openai.com/research | RSS or scrape |

**Note:** Not all of these have clean RSS feeds. You may need to scrape HTML. Use whatever works — feedparser, BeautifulSoup, requests, Playwright if needed for JS-rendered pages. Be pragmatic.

###ategory 2: Paper & Model Repositories

| Source | Method | Notes |
|--------|--------|-------|
| arXiv new submissions | arXiv API (official, free) | Categories: cs.AI, cs.CV, cs.CL, cs.HC, cs.NE, cs.SD, cs.RO, cs.GR, cs.MM, q-bio, eess.AS, eess.SP, stat.ML. Use the `arxiv` Python package or direct API. |
| HuggingFace new models | HuggingFace API (free) | Filter for models uploaded in last 48h. Check for open weights, license, demo Space. |
| HuggingFace Daily Papers | Scrape huggingface.co/papers or API | Curated by AK, high signal. |
| Papers With Code (latest) | Scrape or API | Focus on papers that have linked code implementations. |

**arXiv volume note:** arXiv gets hundreds of papers daily across these categories. Pre-filter by abstract keywords (model, framework, tool, dataset, benchmark, open-source, demo, API, real-time, interactive, novel) to reduce volume to ~15-20 candidates before LLM scoring. This keeps Gemini API calls within free tier limits while still catching niche releases like TRIBE v2.

### Category 3: Code Repositories (GitHub API)

| Source | Method | Note|
|--------|--------|-------|
| New repos from research orgs | GitHub API | Orgs: facebookresearch, google-deepmind, google-research, microsoft, apple, stability-ai, mistralai, deepseek-ai, QwenLM, NVIDIA, huggingface, openai. Check for repos created in last 48h. |
| GitHub Trending | Scrape github.com/trending or use unofficial APIs | Daily trending, all languages + Python + TypeScript + Rust. Star velocity matters. |

### Category 4: Developer Tools, APIs, Browser Features

| Source | Method | Notes |
|--------|--------|-------|
| Hacker News "Show HN" | HN API (free, excellent) | Filter for "Show HN" posts with significant upvotes. These are often new tools/APIs/projects. |
| Product Hunt | Product Hunt GraphQL API (free tier) | Developer tools, API, and AI categories. Filter for new launches. |
| Chrome Platform Status | chromestatus.com/features | New browser APIs and web platform features. RSS or scrape. |
| Web.dev Blog | web.dev/blog | New web capabilities, browser feature announcements. |
| MDN Web Docs "New" | developer.mozilla.org | New web API documentation. |
| DevHunt | devhunt.org | Developer tool launches specifically. |

### Category 5: Datasets, Competitions, Misc

| Source | Method | Notes |
|--------|--------|-------|
| Kaggle new datasets | Kaggle API (free) | New interesting datasets that could power a hackathon project. |
| Kaggle new competitions | Kaggle API (free) | Competitions sometimes reveal interesting problem spaces/data. |
| HuggingFace new datasets | HF API | New dataset uploads. |

### Category 6: Twitter/X (Bonus Layer — May Be Unreliable)

| Source | Method | Notes |
|--------|--------|-------|
| Curated account list | Nitter scraping (ntscraper or similar) | ~30-40 accounts: @AIatMeta, @GoogleDeepMind, @GoogleAI, @MSFTResearch, @ylecun, @_akhaliq, @kaborore, etc. |

**Important:** Twitter scraping via Nitter is fragile and may break. Implement this as a best-effort bonus layer. If it fails, log the error and continue. The pipeline should never depend on Twitter working.

You're also free to add any other sources you think are valuable. This list is a starting point, not exhaustive.

---

## DATA PIPELINE

### Step 1: Scrape

- Pull from all sources with a 48-hour lookback window (overlap to avoid missing things at day boundaries)
- For each item, extract a normalized record:
  ```
  {
  "title": str,
    "description": str,          # abstract, blog excerpt, README excerpt, etc.
    "date": datetime,
    "source": str,                # which source this came from
    "source_url": str,            # link to the original page
    "github_url": str | null,     # link to code repo if available
    "huggingface_url": str | null,# link to HF model/space if available  
    "demo_url": str | null,       # link to live demo if available
    "paper_url": str | null,      # link to paper if available
    "category": str               # ai_research | tool | api | browser | dataset | misc
  }
  ```
- Handle errors gracefully per-source. If Meta's blog is down, skip it and continue.

### Step 2: Deduplicate

- The same project often appears across multiple sources (arXiv paper + HuggingFace model + blog post + GitHub repo)
- Merge duplicates into a single record, keeping ALL URLs
- Match on: exact URL overlap, fuzzy title matching, GitHub/HF repo name matching
- When merging, appearing on MORE sources is a positive signal (more visibility = lab is actively promoting it)

### Step 3: Enrich

- If a GitHub repo exists: fetch star count, primary language, license, creation date, README first ~500 chars
- If a HuggingFace model exists: fetch parameter count (model size), license, whether a demo Space exists, download count
- If it's a paper: check if it links to code, if it links to a demo, if models are available

### Step 4: Score (LLM)

Send items to the LLM in batches with the scoring prompt below. Use whatever free/cheap LLM works best:
- Gemini 2.5 Flash (generous free tier)
- Anthropic API (if Rehan wants to use his own credits — he has Claude Max)
- Any other model with free tier that's good at structured JSON output

The LLM call is the most expensive/slow part. Optimize by:
- Batching multiple items per call (e.g., 5-10 items per request)
- Only sending the essential info (title, description excerpt, URLs, enrichment data)
- Being smart about what you send — a 5000-word blog post should be summarized/truncated before scoring

### Step 5: Rank, Filter & Email

- Sort by weighted total score
- Take top 10-15 items
- Format as a clean, scannable email
- Send daily

---

## SCORING PROMPT

This is the brain of the system. Get this right and everything works.

```
You are a technology scout for a hackathon competitor. Your job is to evaluate newly released technology — AI models, tools, APIs, browser features, datasets, SDKs, open-source projects, anything — and determine if it could be the bf a winning hackathon project.

CONTEXT ON THE HACKER YOU'RE SCOUTING FOR:
- CS student who builds with React/Next.js, Python, TypeScript, PostgreSQL, React Three Fiber
- Comfortable picking up any new tool or framework quickly, especially with AI-assisted coding (Claude Code)
- Has access to free T4 GPUs (Google Colab/Kaggle) and free tiers of major cloud platforms
- Wins hackathons by finding bleeding-edge, niche technology that nobody else has built products around — then building impressive interactive demos
- Willing to invest days of prep time before a hackathon for complex setup. Has AI coding tools that dramatically speed up development. Don't underestimate what's buildable.
- Example winning project: took Meta's TRIBE v2 brain activity prediction model (released 12 days before hackathon, zero existing products) and built an interactive 3D brain visualation app comparing how images activate different neural regions using React Three Fiber
- Interested in ALL domains without exception: neuroscience, audio, robotics, biology, chemistry, vision, NLP, creative tools, hardware, browser APIs, dev tools, games, AR/VR — anything that produces a wow-factor demo

SCORING CRITERIA (score each 1-10):

1. OPEN & FREE TO USE (weight: 20%)
   10 = fully open-source code + weights, runs on free-tier hardware, or generous free API. Ready to use today.
   7 = open-source but needs beefy GPU (>16GB VRAM), or free API with moderate rate limits
   5 = free tier exists but limited, or requires some paid infrastructure
   3 = mostly paid but has a trial or limited free access
   1 = closed source, paywalled, enterprise-only, or paper with no code

2. NOVELTY & UNEXPLOITED (wght: 35%)
   10 = released in last 7 days, zero products or demos built on it beyond authors' own
   8 = released in last 14 days, maybe 1-2 basic community experiments
   6 = released in last 30 days, small but growing community awareness
   4 = released in last 3 months, moderate adoption, some projects exist
   2 = well-known, widely adopted, many existing products
   THIS IS THE MOST IMPORTANT CRITERION. The entire strategy is finding things before others. When in doubt, score lower — if lots of people already know about it, it's not useful for hackathon differentiation.

3. WOW FACTOR & DEMO POTENTIAL (weight: 25%)
   10 = cross-dciplinary, visually stunning or mind-bending potential, would make judges say "wait, what?" Examples: brain activity prediction, real-time audio separation by voice description, molecular visualization, novel 3D/AR/spatial experiences, anything that bridges AI with a surprising domain
   7 = technically impressive with clear visual/interactive demo potential
   5 = solid tech, decent demo potential but not jaw-dropping
   3 = useful but incremental, hard to make visually exciting
   1 = purely theoretical, no demo potential, marginal improvement

4. BUILDABILITY (weight: 20%)
   10 = excellent docs, clear inference script or API, straightforward integration
   8 = good docs, some setup required but well-documented
   6 = moderate complexity, might need to read source code, but doable with AI coding assistance and some prep time
   4 = complex multi-step setup, sparse docs, but theoretically possible with significant effort
   2 = requires custom training from scratch, massive compute, or deep domain expertise with no shortcuts
   
   IMPORTANT: Do NOT be overly conservative here. The builder has Claude Code, automation tools, and is willing to spend days prepping before a hackathon. Complex setup is fine if the payoff is worth it. Score based on "could a strong developer with AI tools get this working in a few days of prep + a hackathon weekend" — not "could someone do this in 3 hours with no help."

CALCULATE TOTAL as weighted average: (OPEN * 0.20) + (NOVELTY * 0.35) + (WOW * 0.25) + (BUILD * 0.20)

FOR ITEMS SCORING 6.5+, also provide:
- "summary": 2-3 sentences on what this technology does and why it's interesting
- "hackathon_idea": A specific, concretproject idea. Not vague — describe the actual product, what a user would see/do, and why it's impressive.
- "tech_stack": Suggested stack for the demo
- "why_now": Why hasn't this been built yet? What's the timing opportunity?
- "effort_estimate": Rough estimate of setup + build time
- "links": All relevant URLs (paper, code, model, demo, docs)

FOR ITEMS SCORING BELOW 6.5:
- Just return scores and a 1-sentence summary

Respond ONLY in valid JSON array format. No markdown, no preamble, no explanation outside the JSON.
```

---

## VALIDATION TEST: TRIBE v2

### How to run the test

1. Set the pipeline's scrape window to March 25-27, 2026
2. Run the fu pipeline against all sources
3. Verify that TRIBE v2 appears in the output

### Expected behavior

TRIBE v2 should be discoverable from AT LEAST these sources:
- **Meta AI Blog:** Blog post at ai.meta.com/blog/tribe-v2-brain-predictive-foundation-model/ (published March 26, 2026)
- **HuggingFace:** Model at huggingface.co/facebook/tribev2
- **GitHub:** Repo at github.com/facebookresearch/tribev2

After deduplication, these should merge into ONE item.

### Expected scores (approximately)
- OPEN & FREE: 9-10 (open model on HF, code on GitHub, interactive demo, runs on free hardware)
- NOVELTY: 9-10 (released yesterday, zero products built on it)
- WOW FACTOR: 9-10 (brain activity prediction + neuroscience + AI = jaw-dropping cross-disciplinary)
- BUILDABILITY: 8-9 (HuggingFace model, good docs from Meta FAIR, clear inference path)
- **TOTAL: ~9.0+**

It should appear in the top 3-5 items of the daily digest.

### If the test fails

Debug in this order:
1. **Was it scraped?** Check if any source picked up the TRIBE v2 blog post, model, or repo. If not → fix the scraper for that source.
2. **Was it deduplicated correctly?** Check if multiple entries merged. If they stayed separate → fix dedup logic.
3. **Was it scored correctly?** Check the LLM's scores. If it scored low → adjust the scoring prompt or the context sent to the LLM.
4. **Was it in the email?** Check if it made the top-N cutoff. If not → adjust the threshold.

---

## EMAIL FORMAT

Subject line: `🔬 HackRadar — [Date] ([N] high-signal finds)`

Body should be clean, scannable HTML. For each top item:
- Score (total + breakdown)
- Title with link
- 2-3 sentence summary
- Hackathona
- Suggested tech stack
- Direct links to paper / code / model / demo

Keep it tight. No fluff. Rehan wants to scan this in 2 minutes and know if anything is worth investigating.

---

## HOSTING & SCHEDULING

Run this daily. Options (all free):
- **GitHub Actions** — 2,000 free minutes/month, cron schedule, secrets management built in
- **Railway free tier** — if you need a persistent process
- **Render free tier** — cron jobs available
- **Local cron** — if Rehan wants to run it on his own machine

Pick whatever is simplest and most reliable. GitHub Actions is probably the easiest starting point.

---

## GENERAL GUIDANCE FOR CLAUDE CODE

- **Be flexible.** This spec is a guide, not a straitjacket. If you find a better library, a smarter approach, a source I didn't list, or a simpler architecture — go for it. Rehan cares about results, noe to a spec.
- **Start with the highest-signal sources first.** Get the Meta AI blog + arXiv + HuggingFace + GitHub research org scrapers working and tested before adding everything else. Those four alone would catch TRIBE v2.
- **The scoring prompt is the most important thing.** Spend time on making sure the LLM scoring is calibrated well. If the scores feel off, iterate on the prompt.
- **Error handling matters.** Sources will go down, formats will change, rate limits will hit. Build resilient scrapers that log errors and continue.
- **Make it easy to add sources.** New research labs will emerge, new platforms will launch. Adding a new source should be as simple as writing one small module.
- **Test with the TRIBE v2 benchmark** but also sanity-check with other recent drops you know about (Meta SAM Audio, Google Gemma 4, WebMCP in Chrome, etc.) to make sure the scoring generalizes.
- **Rehan has infinite scope and time.** Don't limit yourself to MVP thinking. Build it right. But also don't over-engineer — ship something that works, then iterate.
- **Cost constraint is real.** Everything should run on free tiers. If a paid service is dramatically better, flag it as an option but always have a free fallback.
- **If you're unsure about a decision, make your best call and document why.** Rehan trusts your judgment on implementation details.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
