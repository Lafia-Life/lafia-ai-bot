# Deployment Document

Pricing snapshot date: **March 10, 2026**.  
All prices are approximate and exclude taxes.

## 1. Services in this project

| Service | Required | Purpose in this codebase | Recommended deployment |
| --- | --- | --- | --- |
| FastAPI app (`app/main.py`) | Yes | Chat API, upload/scrape, SMS webhook, WhatsApp webhook routes | 1 Linux VM (Docker + `uvicorn`) |
| Chroma persistent store (`storage/chroma`) | Yes | Vector index for retrieval | Keep local on same VM disk (with backups) |
| File storage (`storage/uploads`) | Yes | Uploaded PDFs/images/videos | Same VM disk + snapshots |
| LLM API (OpenAI or DeepSeek) | Yes (for answers) | Chat generation + embeddings (if OpenAI backend) | Managed API (no self-hosting) |
| Africa's Talking SMS | Optional (required for SMS feature) | Inbound/outbound SMS via `/api/sms/webhook` | Managed API |
| WhatsApp channel | Optional | WhatsApp conversational channel | Twilio or Africa's Talking WhatsApp |
| Moodle instance | Optional | Course sync/integration via `MOODLE_BASE_URL` | Reuse existing Moodle; only host new one if needed |
| Ollama (`docker-compose` `local-llm` profile) | Optional | Local/offline LLM instead of cloud API | Separate VM if used in production |
| DNS | Yes | Domain routing | Amazon Route 53 |
| TLS certificate | Yes | HTTPS webhook + secure web access | Let's Encrypt |

## 2. Recommended server sizes

| Stage | Recommended server | Why | AWS Lightsail monthly price |
| --- | --- | --- | --- |
| Pilot (small team) | 2 vCPU / 4 GB RAM / 80 GB SSD | Enough for FastAPI + Chroma + OCR at low/medium traffic | **$24/mo** |
| Production (single instance) | 2 vCPU / 8 GB RAM / 160 GB SSD | Better headroom for concurrent chat + uploads + OCR | **$44/mo** |
| High traffic / HA | 2 x (2 vCPU / 8 GB RAM) + Lightsail Load Balancer | Redundancy + safer rollouts | **$88 + $18 = $106/mo** |
| Local Ollama in production (optional) | 4 vCPU / 16 GB RAM / 320 GB SSD | Needed for local model inference and model files | **$84/mo** |

## 3. Fixed infrastructure costs

| Item | Cost model | Recommended amount | Estimated monthly cost |
| --- | --- | --- | --- |
| App VM (production baseline) | Lightsail bundle | 8 GB plan | **$44.00** |
| DNS zone | Per hosted zone | 1 hosted zone | **$0.50** |
| Backups | $0.05 per GB-month snapshot | 100 GB snapshots | **$5.00** |
| TLS cert | Free | Let's Encrypt | **$0.00** |
| Data transfer overage | Starts at $0.09/GB outbound over allowance | Usually $0 until allowance exceeded | Variable |

**Baseline fixed monthly (single production instance):** **$49.50/mo**  
**HA fixed monthly (2 app servers + LB + snapshots + DNS):** **~$111.50/mo**

## 4. Variable usage costs

### 4.1 AI model costs

#### OpenAI (recommended cloud option)

| Model / Service | Pricing |
| --- | --- |
| GPT-5 mini | Input $0.25 / 1M tokens, Output $2.00 / 1M tokens |
| `text-embedding-3-small` | $0.02 / 1M tokens |

**Per-question example** (1,200 input + 400 output tokens):  
`(1200 * 0.25 / 1,000,000) + (400 * 2.00 / 1,000,000) = $0.00110 per answer`

#### DeepSeek (alternative cloud option)

| Model / Service | Pricing |
| --- | --- |
| `deepseek-chat` | Input cache hit: $0.028 / 1M, Input cache miss: $0.28 / 1M, Output: $0.42 / 1M |

**Per-question example** (1,200 input + 400 output tokens):  
- Cache miss input: `~$0.000504`  
- Cache hit input: `~$0.000202`

### 4.2 SMS costs (Uganda via Africa's Talking)

From Africa's Talking Uganda bulk SMS rates:
- MTN local traffic: **UGX 27** per SMS (basic tier)
- Airtel local traffic: **UGX 25** per SMS (basic tier)
- Other telcos: **UGX 35** per SMS (basic tier)

Typical SMS Q/A flow in this app is about **3 SMS segments per user question** (1 inbound + ~2 outbound response parts), so:
- Airtel-heavy traffic: `3 * 25 = 75 UGX` per answered question
- MTN-heavy traffic: `3 * 27 = 81 UGX` per answered question
- Mixed worst case: up to `3 * 35 = 105 UGX` per answered question

Sender ID costs shown on Africa's Talking pricing page:
- MTN Sender ID: **UGX 250,000 monthly maintenance**
- Airtel Sender ID: **UGX 250,000 setup**, no monthly maintenance listed

### 4.3 WhatsApp costs (optional)

#### Africa's Talking WhatsApp pricing
- Setup: **$85** (one-off)
- Monthly maintenance: **$50**
- Rest of Africa message pricing: Marketing **$0.032**, Utility **$0.007**, Authentication **$0.007**, Service **$0.002**

#### Twilio WhatsApp pricing (alternative)
- Twilio fee shown as **$0.005/message** plus Meta fee by region/category.

## 5. Monthly total examples

Assumptions:
- Single production server (8 GB Lightsail): **$49.50 fixed/month**
- 10,000 AI answers/month
- 2,000 SMS questions/month
- Each SMS question uses 3 SMS segments
- SMS average rate: **UGX 27** per segment

### Example A: OpenAI GPT-5 mini

- AI answers: `10,000 * $0.00110 = $11.00`
- SMS: `2,000 * 3 * 27 = 162,000 UGX`
- Fixed infra: `$49.50`

**Estimated monthly total:** **$60.50 + 162,000 UGX**

### Example B: DeepSeek (cache miss pricing)

- AI answers: `10,000 * $0.000504 = $5.04`
- SMS: `2,000 * 3 * 27 = 162,000 UGX`
- Fixed infra: `$49.50`

**Estimated monthly total:** **$54.54 + 162,000 UGX**

### Add-on if WhatsApp enabled (Africa's Talking)

- Add **$50/month** maintenance
- Add one-time **$85** setup
- Add per-message WhatsApp charges by message type

## 6. Deployment recommendation

For this repository, the best cost-to-reliability path is:
1. Start with **1 x Lightsail 8 GB** instance (`$44/mo`).
2. Use **OpenAI or DeepSeek API** (no GPU server initially).
3. Keep **Chroma + uploads on attached instance disk**, with **daily snapshots**.
4. Use **Africa's Talking SMS** only if SMS channel is needed.
5. Add **second app server + Lightsail Load Balancer** only when traffic grows or uptime requirements increase.

## 7. Source links

- AWS Lightsail pricing: https://aws.amazon.com/lightsail/pricing/
- AWS Route 53 pricing: https://aws.amazon.com/route53/pricing/
- Let's Encrypt (free TLS): https://letsencrypt.org/
- OpenAI API pricing: https://openai.com/api/pricing/
- OpenAI platform pricing (model table): https://platform.openai.com/pricing
- OpenAI `text-embedding-3-small` model pricing: https://developers.openai.com/api/docs/models/text-embedding-3-small
- DeepSeek model pricing: https://api-docs.deepseek.com/quick_start/pricing
- Africa's Talking pricing: https://africastalking.com/pricing
- Twilio WhatsApp pricing: https://www.twilio.com/en-us/whatsapp/pricing
