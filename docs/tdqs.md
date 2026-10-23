# Tool definition quality (TDQS)

Glama grades this server with the [Tool Definition Quality Score](https://tdqs.dev/spec)
(TDQS) and shows the grade on the README badge. `scripts/tdqs.py` runs the same scorer
locally, so a description change can be checked before Glama rescans the repository.

## What Glama measures

Each tool gets a score from 1.0 to 5.0, the weighted sum of six dimensions graded by a model:
purpose clarity (25%), usage guidelines (20%), behavioral transparency (20%), parameter
semantics (15%), conciseness (10%) and contextual completeness (10%). The server score is

```text
description quality = 0.6 x mean(tool scores) + 0.4 x min(tool scores)
coherence           = mean(disambiguation, naming, tool count, completeness)
overall             = 0.7 x description quality + 0.3 x coherence
```

Tiers: A from 3.5, B from 3.0 (the passing bar), C from 2.0. The min term means the weakest
tool pulls the whole server down. The rubric gives no credit for text that repeats the input
schema or the MCP annotations; read the spec's "Improving your score" checklist before
rewriting a description.

## Run it

Use the project virtualenv. The script builds the `tools/list` payload Glama sees (the 44
registry tools plus `search_bunkerweb_docs`, no log tools) whatever `.env` says, then runs
the `tdqs` CLI pinned in the script through `uvx`.

```bash
.venv/bin/python scripts/tdqs.py lint                         # offline, no model
.venv/bin/python scripts/tdqs.py score --format markdown      # full rubric, about 5 minutes
.venv/bin/python scripts/tdqs.py score --format json --output report.json   # with justifications
.venv/bin/python scripts/tdqs.py dump -o tools.json           # payload only
```

`lint` runs the deterministic checks (parameter coverage, missing annotations, output schema,
shadow candidates) and needs no key.

`score` needs a model behind an OpenAI-compatible API. By default it calls
`gpt-oss:20b-cloud` through a local [Ollama](https://ollama.com) signed in to ollama.com
(`ollama signin`, then `ollama pull gpt-oss:20b-cloud`). The model runs on Ollama's servers
and is in the free plan; nothing loads into local RAM or VRAM. To use another endpoint, set
`TDQS_BASE_URL`, `TDQS_API_KEY` and `TDQS_MODEL`; the Ollama request overrides then apply only
when `TDQS_BASE_URL` is unset, so set `TDQS_REQUEST_OVERRIDES` yourself if the provider needs
one. To score through tdqs.dev instead (30 calls
a day, GitHub sign-in, undisclosed model), pass `--hosted https://tdqs.dev` with a tdqs.dev key
in `TDQS_API_KEY`.

## Calibration

Glama does not publish its model, and scores are calibrated to a rubric and model pair. On
2026-10-21, against the published Glama breakdown of the same 45 definitions (overall C 2.9:
description quality 3.0, coherence 2.8):

| Model | Tools scored | Mean abs. error per tool | Rank correlation | Local overall |
| --- | --- | --- | --- | --- |
| `gpt-oss:20b-cloud` (default), two runs | 45 | 0.29 to 0.30 | 0.74 to 0.75 | B 3.3 |
| `gemma4:31b-cloud` | 45 | 0.46 | 0.76 | A 3.5 |
| `minimax-m3.1-flash:cloud` | 10 | 0.40 | not measured | not comparable |
| `qwen2.5-coder:7b` (local) | 10 | 0.55 | not measured | not comparable |

The default model scores about a quarter point above Glama per tool and ranks tools in a
similar order (Spearman, tied ranks averaged). It is the default over `gemma4:31b-cloud`
because its error is lower. Three runs of the full set gave server scores of 3.3, 3.3 and 3.2;
between two runs, single tools moved by 0.11 on average and by up to 0.6. Treat the local score
as a relative signal:

- Compare a change against a baseline run with the same model, not against Glama's number.
- On the 2026-10-21 baseline, Glama's overall score sat 0.3 to 0.4 below the local one.
- Read the per-tool justifications in the `--format json` report; they name what is missing.

Local models are slower, score further from Glama, and a 7B to 12B model needs 5 to 10 GB of
RAM when it does not fit in VRAM. Prefer the cloud default on a shared host.

## Result of the 2026-10-21 description pass

Every API tool description except `authenticate` and `diagnose`, whose wording tests pin, now
names the sibling to use instead, and every input parameter Glama sees has a schema description
(`tests/test_tdqs_script.py` keeps that coverage at 100%). The log tools were left unchanged.
Local runs with the default model:

| Run | Mean tool | Weakest tool | Description quality | Coherence | Overall |
| --- | --- | --- | --- | --- | --- |
| Before (two runs) | 3.6 | 2.7 | 3.2 | 3.5 | B 3.3 |
| Draft wording (two runs) | 4.5 | 3.7 to 3.9 | 4.2 to 4.3 | 3.5 to 3.8 | A 4.0 to 4.2 |
| Final wording, real stdio server (one run) | 4.6 | 3.5 | 4.2 | 3.8 | A 4.1 |

The final run scored the `bunkerweb-mcp` stdio entrypoint itself (`tdqs score --command`), not
the script's payload. The stdio server, the HTTP `/mcp/` endpoint and the Docker image built from
this tree all served the same 45 definitions, hash for hash. No tool scored below B and none was
flagged. Usage guidelines averaged 4.6 (2.0 before), behavioral transparency 4.5 (3.5) and
parameter semantics 3.4 (2.8). Glama's own grade changes only after it rescans a pushed commit.
Coherence still loses points on tool count (45 tools) and, on Glama, on naming; both need tool
renames or merges, which change the public tool API.
