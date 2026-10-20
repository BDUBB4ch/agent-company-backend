# Agent Company - v1

A local, personal 7-agent system for YieldCraft (formerly B Dubb Grows).
Runs on your own PC. Free by default (local Ollama); Claude is opt-in,
pay-per-use, per-agent.

## The roster

| Agent | Role |
|---|---|
| CIO | Your main contact - the chat bar talks to this one by default |
| Operations Director | Routes tasks to the right specialist |
| Business Operations | Business & financials |
| Legal Counsel | Copyright/compliance review before anything goes external |
| Marketing Officer | Marketing copy, tone |
| Creative Director | Visual concepts (images, logos) |
| Movie Director | Scripts, prompts, scene direction |

Click any agent's avatar in the sidebar to talk to them directly - the
main chat bar isn't locked to the CIO, you can go straight to a specialist
any time.

## The hard rule

**No agent posts, sends, or publishes anything. Ever.** Nothing in this
codebase calls a social media API, an email API, or your website's API to
actually push content live. Every external-facing draft lands in the
Approval Queue (top of the sidebar) - you approve or reject each one by
hand. Approving currently just marks it approved in the log; wiring an
approved item to actually go out (e.g. to WooCommerce, to your email
provider) is a deliberate next step you add per-channel when you're ready,
not something that happens automatically.

## Setup

### 1. Install Python dependencies
```bash
cd agent-company
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Install Ollama (free local LLM) - if you haven't already
Download from https://ollama.com, then pull a model:
```bash
ollama pull qwen2.5:14b
```
This fits comfortably in your RX 9070 XT's 16GB VRAM at Q4. ROCm 7.2+
gives you native AMD support - no CUDA needed, no manual workarounds.

### 3. (Optional) Set up Claude
Copy `.env.example` to `.env` and add your Anthropic API key if you want
some agents to use Claude instead of the free local model. Leave it blank
to run 100% free.

```bash
cp .env.example .env
# edit .env and add ANTHROPIC_API_KEY=sk-ant-...
```

By default, only the CIO uses Claude (it's the one you talk to most, so
it's worth the extra quality). Every other agent defaults to free local
Ollama. Change any agent's `"backend"` in `backend/agents.py` between
`"claude"` and `"ollama"` any time.

### 4. Run it
```bash
cd backend
python3 main.py
```
Then open **http://127.0.0.1:8420** in your browser.

## The brain

`backend/memory.py` is the knowledge base every agent automatically reads
from before responding. It already knows:
- The business is transitioning from B Dubb Grows LLC to YieldCraft Indoor
  Gardening Supply, and is being restructured
- What you sell (Bionova nutrients, HighDroGro tents, GrowMax water
  systems, grow lights, accessories) and that the platform is WooCommerce
- The hard legal line: no cannabis/controlled substances, ever, in any
  copy

To teach it something new, the easiest way for now is to just tell your
CIO or any agent in conversation - a "remember this" feature that writes
straight into the brain is a natural next addition once you're using the
system day to day and know what's worth automating there.

## What's NOT built yet (by design - this is v1)

- Actually connecting an approved item to WooCommerce/social/email (the
  approval queue works, the "send it for real" wiring per channel is a
  deliberate next phase)
- The visual "office" - this is a clean chat interface for now, not a 2D
  or 3D workspace
- Scheduled/recurring tasks
- Agents proposing their own avatar traits automatically (the system in
  `avatars.py` supports it - `choose_traits_prompt()` - it just isn't
  wired to run automatically on first launch yet)

## Cost

Everything defaults to $0. The only live cost is Claude API calls, shown
running in the top-right badge. If you never set an API key, that number
just stays at $0.00 forever and the CIO will tell you it needs a key
rather than silently failing.
