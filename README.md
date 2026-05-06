# AI Business Lead Engine

> Go from "search Google Maps manually" to a prioritized outreach list with personalized cold emails, DMs, call scripts, and CRM status tracking — all in a few terminal commands.

Built for founders selling AI automation services to local businesses.

---

## What It Does

```
Google Maps API
    ↓
batch_collect.py          ← multi-city × multi-niche batch collection
    ↓
enrich_leads.py           ← website scraping + lead scoring (0–100)
    ↓
generate_outreach.py      ← AI-personalized emails, DMs, call scripts
    ↓
prepare_email_campaign.py ← mail-merge CSV for Instantly / Lemlist / GMass
    ↓
update_status.py          ← CRM status tracking in the same CSV
```

---

## Who It's For

Founders selling:
- AI receptionist / missed-call SMS recovery
- Appointment booking automation
- Website chatbots / lead capture
- Review request automation
- Social content engines

Target niches: auto detailers, window tint shops, wrap shops, body shops, performance shops, dental clinics, med spas, CPR/driving schools, home services.

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/Noctilucenty/maps-ai-leads.git
cd maps-ai-leads
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```
GOOGLE_MAPS_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here        # optional — templates work without it
FOUNDER_NAME=Leon
OPENAI_MODEL=gpt-4o-mini
```

### 3. Get API keys

**Google Maps API key:**
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → Enable **Places API**
3. Create credentials → API Key
4. Restrict by IP for safety

**OpenAI API key** (optional):
- Get from [platform.openai.com](https://platform.openai.com)
- Without it, outreach generation uses built-in templates (still good)

---

## Full Workflow

### Step 1 — Collect leads (multi-city × multi-niche batch)

```bash
python scripts/batch_collect.py \
  --cities examples/cities.txt \
  --niches examples/niches.txt \
  --state CA \
  --output data/raw/batch_leads.csv \
  --max-results 60
```

- Runs every `niche × city` combination automatically
- Saves partial results if interrupted; re-run to resume (checkpoint file)
- Adds `niche`, `city`, and `source_query` columns
- Deduplicates by `place_id` at the end

**Or single query:**

```bash
python scripts/collect_leads.py \
  --mode text \
  --query "auto detailing shops in Oakland CA" \
  --output data/raw/leads.csv
```

---

### Step 2 — Enrich websites + score leads

```bash
python scripts/enrich_leads.py \
  --input data/raw/batch_leads.csv \
  --output data/enriched/enriched_leads.csv \
  --max-workers 8
```

This scrapes each business website for:
- Email addresses
- Social profiles (Instagram, Facebook, LinkedIn, etc.)
- Contact forms
- Booking systems
- Tech stack (WordPress, Wix, GoDaddy, etc.)

Then scores every lead **0–100** based on opportunity signals and assigns:
- `lead_score` — opportunity score
- `pain_points` — what's missing (e.g. "No email contact visible")
- `pitch_angle` — what to lead with
- `recommended_offer` — which product to pitch
- `priority` — high / medium / low / skip

---

### Step 3 — Generate personalized outreach

```bash
# With OpenAI (best results):
python scripts/generate_outreach.py \
  --input data/enriched/enriched_leads.csv \
  --output data/outreach/outreach_ready.csv \
  --top 50 \
  --model gpt-4o-mini

# Without OpenAI (template fallback, still solid):
python scripts/generate_outreach.py \
  --input data/enriched/enriched_leads.csv \
  --output data/outreach/outreach_ready.csv \
  --templates-only
```

Generates for each lead:
- `cold_email_subject` + `cold_email_body`
- `follow_up_1` + `follow_up_2`
- `instagram_dm`
- `linkedin_dm`
- `sms_script`
- `call_script`
- `loom_video_script`

Resume without re-processing already-done leads:

```bash
python scripts/generate_outreach.py \
  --input data/enriched/enriched_leads.csv \
  --output data/outreach/outreach_ready.csv \
  --skip-existing
```

---

### Step 4 — Prepare email campaign

```bash
python scripts/prepare_email_campaign.py \
  --input data/outreach/outreach_ready.csv \
  --output data/campaigns/email_campaign.csv \
  --min-score 60 \
  --limit 100
```

Output CSV columns map directly to:
- **Instantly**: `Email → recipient_email`, `Subject → subject`, etc.
- **Lemlist / Smartlead / GMass / Mailmeteor**: same mapping

Only includes rows that have both an email address AND generated outreach.

---

### Step 5 — Track CRM status

```bash
# Mark as contacted:
python scripts/update_status.py \
  --file data/outreach/outreach_ready.csv \
  --business "Dragon Auto Works" \
  --status contacted \
  --notes "Sent cold email via Gmail"

# Mark as replied with prospect's response:
python scripts/update_status.py \
  --file data/outreach/outreach_ready.csv \
  --place-id "ChIJNY1h0VnLj4AR..." \
  --status replied \
  --owner-response "Interested — wants a 15-min call"

# Schedule follow-up:
python scripts/update_status.py \
  --file data/outreach/outreach_ready.csv \
  --business "Dragon Auto Works" \
  --status follow_up_1_sent \
  --next-follow-up "2026-05-12" \
  --priority high

# View pipeline summary:
python scripts/update_status.py \
  --file data/outreach/outreach_ready.csv \
  --summary
```

**Valid statuses:**
`new` → `enriched` → `outreach_generated` → `contacted` → `follow_up_1_sent` → `follow_up_2_sent` → `replied` → `interested` → `demo_sent` → `call_booked` → `closed_won` / `closed_lost` / `not_interested`

---

## Project Structure

```
maps-ai-leads/
├── app/                        ← importable Python package
│   ├── config.py               ← env var config
│   ├── collectors/
│   │   └── google_maps.py      ← GoogleMapsLeadCollector class
│   ├── enrichers/
│   │   └── website.py          ← SiteEnricher + enrich_dataframe()
│   ├── scoring/
│   │   └── lead_score.py       ← score_lead() → 0–100 + pain points
│   ├── outreach/
│   │   ├── templates.py        ← built-in outreach templates
│   │   └── generator.py        ← OutreachGenerator (AI + template fallback)
│   ├── crm/
│   │   └── status.py           ← update_status(), pipeline_summary()
│   └── utils/
│       ├── csv_utils.py        ← load/save/dedupe/append CSV
│       ├── text_utils.py       ← clean_int, clean_float, safe_str
│       └── logging_utils.py    ← get_logger()
├── scripts/                    ← CLI entry points
│   ├── collect_leads.py        ← single-query collection
│   ├── batch_collect.py        ← multi-city × multi-niche batch
│   ├── enrich_leads.py         ← website scraping + scoring
│   ├── generate_outreach.py    ← AI outreach generation
│   ├── update_status.py        ← CRM status tracker
│   └── prepare_email_campaign.py ← mail-merge CSV export
├── data/
│   ├── raw/                    ← raw leads from Maps API
│   ├── enriched/               ← scored + website-enriched leads
│   ├── outreach/               ← outreach + CRM columns
│   └── campaigns/              ← final mail-merge CSVs
├── examples/
│   ├── cities.txt              ← one city per line
│   └── niches.txt              ← one niche per line
├── tests/
│   ├── test_scoring.py
│   ├── test_deduping.py
│   └── test_templates.py
├── google_maps_lead_collector.py   ← original script (still works)
├── site_enricher.py                ← original script (still works)
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_MAPS_API_KEY` | Yes | — | Google Places API key |
| `OPENAI_API_KEY` | No | — | OpenAI key (templates used if missing) |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | Model for outreach generation |
| `FOUNDER_NAME` | No | `the team` | Appears in outreach messages |
| `REQUEST_TIMEOUT` | No | `15` | HTTP timeout for website scraping |
| `RATE_LIMIT_SECONDS` | No | `1.2` | Delay between Google Maps API calls |
| `DEFAULT_MAX_RESULTS` | No | `60` | Approx results per query |

---

## Example Lead Scoring Output

| Business | Rating | Reviews | Score | Pain Points | Pitch |
|---|---|---|---|---|---|
| Dragon Auto Works | 4.7 | 120 | 85 | No email; No booking | AI booking + missed-call SMS |
| City Dental | 4.8 | 340 | 62 | No contact form | After-hours lead capture |
| Quick Tint Shop | 4.2 | 15 | 70 | No email; No social | AI receptionist + quote capture |

---

## Running Tests

```bash
pytest tests/ -v
```

All tests run without API keys — no network calls.

---

## Compliance & Responsible Use

- This tool uses the official **Google Places API** — follow [Google's Terms of Service](https://developers.google.com/maps/terms).
- Outreach is your responsibility. Follow [CAN-SPAM](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business), [TCPA](https://www.fcc.gov/consumers/guides/stopping-unwanted-robocalls-and-texts), and local laws.
- Do not spam. Send personalized, relevant messages to businesses that could genuinely benefit.
- Never commit `.env` or lead data CSVs to git. The `.gitignore` is configured to prevent this.

---

## Roadmap

- [ ] Email verification (MX + SMTP probe)
- [ ] Multi-language outreach templates
- [ ] Streamlit dashboard for browsing + filtering leads
- [ ] Airtable / HubSpot CRM sync
- [ ] Niche-specific scoring profiles
- [ ] AI-generated Loom video storyboards

---

## License

MIT — see [LICENSE](LICENSE)
