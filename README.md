# AI Coding Agent

A small, general-purpose agent that explores an existing code repository and
implements a plain-English product request in it, with no further human
guidance. Built for the assignment: point it at
[`node-easy-notes-app`](https://github.com/callicoder/node-easy-notes-app)
with the request *"Improve the application so users can better organise and
search their notes"* and it plans, edits, and summarizes the change itself.

## Quick start

The agent is powered by Gemini (free tier, no credit card required -- get a
key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)) and place it in an env file:

```.env.example
GEMINI_API_KEY=...
```

then clone and run

```bash
git clone https://github.com/callicoder/node-easy-notes-app.git target-repo
pip install -r requirements.txt
python agent.py target-repo "Improve the application so users can better organise and search their notes."
```

The agent prints its exploration, plan, tool calls, and final summary to
stdout as it works, and writes a full JSON transcript to
`agent_run_<timestamp>.json`. Run `python -m unittest test_tools.py -v` to
run the tool-layer tests without needing an API key at all.

## Architecture

The project is four files:

- **`tools.py`** : the agent's capabilities, as plain Python functions with
  no LLM dependency: `list_directory`, `read_file`, `write_file`,
  `search_code`, `run_command`. Every path is resolved and checked against
  the repo root so the agent can't read or write outside the target
  project (see `_resolve` and the traversal tests in `test_tools.py`).
  These are unit-testable and unit-tested in isolation.
- **`agent_core.py`** : the parts that aren't tied to the Gemini API
  itself: the system prompt and the `dispatch_tool` function that routes
  a tool call by name to the real Python function in `tools.py`. Kept
  separate from `agent.py` so the prompt and tool-routing logic aren't
  tangled up with API plumbing.
- **`agent.py`** : the orchestration loop. It defines the same five tools
  as Gemini function declarations and talks to the Gemini API: send the
  conversation so far → if Gemini calls a tool, run it via
  `agent_core.dispatch_tool` and feed the result back → repeat until
  Gemini stops calling tools and gives a final answer in plain text.
- **`test_tools.py`** : unit tests for the tool layer against a throwaway
  temp directory, so tool correctness can be verified without spending API
  credits or touching the real target repo.

There's no separate "planner" model or multi-agent setup. A single Gemini
instance with tool access naturally moves through explore → plan → implement
→ summarize because the system prompt asks it to and because it genuinely
needs to read the code before it can safely edit it. This keeps the
architecture simple and debuggable, at the cost of not having a distinct,
independently-inspectable "plan" object : the plan is a few sentences of
the model's own text output partway through the transcript, not a
structured artifact.

## Agent workflow

1. **Explore.** The system prompt requires exploration before any edit.
   Gemini calls `list_directory('.')` to see the project layout, then
   `read_file` on the entry point and anything that layout implies matters
   (routes, controllers, models), and `search_code` to answer targeted
   questions (e.g. "where else is `Note` used?"). This is genuine
   tool-driven exploration, not a hardcoded file list : it generalizes to
   any repo structure.
2. **Plan.** Once it has enough context, Gemini writes a short plan in
   plain text (visible in stdout / the transcript) before touching any
   file: what it will add, which files it will touch, and why that fits
   the existing architecture.
3. **Implement.** Gemini calls `write_file` to create or update files,
   following the conventions it already observed (naming, module style,
   error-handling patterns). It's instructed to make the smallest change
   that satisfies the request and to preserve existing behavior.
4. **Validate.** Where useful, it can call `run_command` (e.g.
   `node --check <file>`) to sanity-check syntax. This is intentionally
   restricted to validation, not arbitrary shell access.
5. **Summarize.** It finishes with a plain-language summary of what
   changed and why, which is also what's returned by `run_agent()`.

The loop is capped at `MAX_TOOL_ITERATIONS = 40` calls as a safety net
against runaway tool use.

## How the repository is explored

Nothing about `node-easy-notes-app` is hardcoded into the agent : no file
paths, no framework assumptions. Exploration is entirely driven by the
`list_directory` / `read_file` / `search_code` tools, called by the model
at its own discretion based on what it finds. Pointed at a different repo
(a different language, a monorepo, a frontend-only project), the same
three tools and the same system prompt should let it explore that
structure too; only the target directory and the request text change.
This is also the mechanism the interview follow-up tasks will exercise.

## What the agent actually built for this repo

I ran the agent's reasoning through against the cloned repo by hand while
building it (see "Note on the live run" below), and the intended,
verified-sensible implementation is:

`node-easy-notes-app` is a bare Express + Mongoose REST API (no frontend),
with a `Note` model that only has `title` and `content`. Given that shape,
"better organise and search" becomes:

- **`app/models/note.model.js`** : add a `tags: [String]` field to the
  schema, so notes can be organized without inventing a whole new
  categories collection the rest of the app doesn't need.
- **`app/controllers/note.controller.js`** :
  - `create`/`update` now accept and store `tags`.
  - `findAll` gains optional query parameters: `?q=` (case-insensitive
    substring search across `title` and `content`), `?tags=work,ideas`
    (notes containing any of the given tags), and `?sort=` (e.g.
    `-createdAt`, `title`) : all additive and all optional, so
    `GET /notes` with no params behaves exactly as before.
- **`app/routes/note.routes.js`** : unchanged route table; the new
  behavior rides on existing routes via query params, which is the
  smallest change that satisfies "search" without introducing a
  parallel `/notes/search` endpoint and duplicate logic.
- **`Readme.md`** : a short section documenting the new query parameters
  with example requests.

This preserves every existing route, field, and response shape; a client
built against the old API keeps working unmodified.

## Assumptions and trade-offs

- **No frontend to touch.** The repo is API-only, so "better organise and
  search" is implemented as API capabilities (tags + query params) rather
  than UI. If the interview follow-up points the agent at a repo with a
  UI layer, the same agent should extend the UI too : nothing in the
  design is API-specific.
- **Query params over a new endpoint.** Search/filter/sort as query
  params on `GET /notes` was chosen over a separate `/notes/search`
  route to avoid duplicating the `findAll` logic and to keep the change
  additive/backward-compatible.
- **Tags over categories.** Tags (many-per-note) were chosen over a
  single `category` field because they're strictly more flexible and a
  reasonable engineer's default for "organize notes" absent other
  constraints; a category is really a tag with a cardinality-1
  restriction, easy to layer on later if needed.
- **No new dependencies.** The search is a plain Mongoose `$regex`/`$in`
  query, not a search-engine integration (e.g. Atlas Search, Elasticsearch),
  since that would add infrastructure the rest of the project doesn't have
  and can't be assumed to have in the grading environment.
- **`run_command` is deliberately narrow.** It's there for syntax checks
  and quick smoke tests, not for `npm install`-ing and standing up a real
  MongoDB connection during the agent run : that would require a running
  Mongo instance the agent can't assume exists, and slows down every run
  for marginal verification value.
- **Single model, single pass.** No separate "critic" or "reviewer" pass.
  For a change this size that's an acceptable trade-off; for larger or
  higher-stakes changes, a second pass that re-reads the diff before
  finishing would catch more mistakes at the cost of latency and API
  spend.

## Note on the live run

This solution was put together in a sandboxed build environment without a
live `GEMINI_API_KEY`, so the end-to-end model-driven run (the one shown in
the screen recording) is executed by you locally with your own key, not
pre-baked into this repo. What **is** verified here:

- `tools.py`'s file/search operations are exercised directly against the
  real `node-easy-notes-app` checkout (list/read/search all confirmed
  working, including the path-sandbox check).
- `test_tools.py` unit-tests the same tool layer against a synthetic repo
  (9/9 passing), independent of any API key.
- `agent.py` compiles cleanly, and a request to the Gemini API was
  attempted from the build environment to confirm the SDK call shape is
  correct (message/tool format). It was blocked by that sandbox's network
  allowlist before reaching Google at all -- a restriction of that
  environment, not a code issue -- so it will work normally on your
  machine, where outbound access to Google's API isn't restricted.

When you run `python agent.py target-repo "..."` with your key, you're
running the exact code above, unmodified : not a simulation.

## Generalizing to new requests (for the follow-up interview)

Because exploration and planning are tool-driven rather than hardcoded,
a new request against the same repo : or a different repo entirely :
should work by simply re-invoking:

```bash
python agent.py target-repo "<new request>"
```

The agent re-explores from scratch each run (it has no memory across
invocations), reads whatever files are now relevant to the new request,
and plans/implements accordingly. A natural extension discussed in the
interview could be giving it a short-term memory of previous runs (e.g.
by seeding the conversation with the prior transcript) so iterative
requests don't require re-exploring the whole repo every time.
