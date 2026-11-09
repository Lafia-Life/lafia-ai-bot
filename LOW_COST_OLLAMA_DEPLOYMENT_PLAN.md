# Low-Cost Ollama Deployment Plan

Target environment: **single server with 2 vCPU / 8 GB RAM / 80 GB disk**  
Pricing snapshot date: **March 10, 2026**

---

## 1. Goal

Deploy this ChatLearning stack at the **lowest recurring monthly cost** by:
- Running the app and LLM locally on one server
- Avoiding paid LLM APIs (OpenAI/DeepSeek) for normal usage
- Using free DNS/TLS options where possible

---

## 2. Recommended architecture (minimum cost)

Run these containers on the same host:
- `app` (FastAPI app)
- `ollama` (local LLM, via compose `local-llm` profile)

Persistent storage:
- `chatlearning_data` Docker volume for uploads + Chroma data
- `ollama_data` Docker volume for model files

Use a lightweight model:
- `llama3.2:3b` (~2 GB model size), or
- `qwen2.5:3b` (~1.9 GB model size)

Do not use 7B+ models on this server if you want stable memory headroom and low latency.

---

## 3. Monthly recurring pricing

## 3.1 Core recurring cost (incremental)

| Item | Required | Monthly cost | Notes |
| --- | --- | --- | --- |
| Existing server (2 vCPU / 8 GB / 80 GB) | Yes | Already paid | Put your provider charge here |
| LLM API (OpenAI/DeepSeek) | No | **$0** | Local Ollama replaces API billing |
| TLS certificate (Let’s Encrypt) | Yes | **$0** | Free SSL |
| DNS (Cloudflare DNS) | Yes | **$0** | If you already own a domain |
| Backups (minimum mode) | No | **$0** | Not recommended for production |
| Backups (recommended) | Yes (recommended) | **~$4–$5** | ~80 GB snapshots at ~$0.05–$0.06/GB-month |

### Lowest recurring total
- **Absolute minimum:** `existing server cost + $0/month`
- **Recommended low-risk:** `existing server cost + ~$4 to $5/month`

---

## 3.2 Optional feature costs

| Optional feature | Cost type | Typical recurring |
| --- | --- | --- |
| Africa’s Talking SMS | Per SMS segment | Uganda local rates around UGX 25–35/SMS segment |
| Sender ID (Africa’s Talking) | Setup/maintenance | Example pricing includes UGX 250,000 monthly on some telcos |
| WhatsApp via Africa’s Talking | Monthly + per message | Example: $50/month maintenance + per-message fees |
| WhatsApp via Twilio | Per message | Twilio fee + Meta conversation fee |

If you want the absolute lowest recurring cost, keep SMS/WhatsApp disabled.

---

## 4. Capacity expectation on this server

With `2 vCPU / 8 GB` and a 3B model:
- Best for low to moderate concurrency
- Good fit for pilot and early production
- OCR/file ingestion and LLM responses should not run at very high concurrency

Practical guidance:
- Keep to one small model
- Run 1 app worker
- Add swap space (4 GB) for memory spikes

---

## 5. Step-by-step deployment

## 5.1 Prepare server

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl gnupg lsb-release git ufw
```

Open required ports:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## 5.2 Install Docker + Compose

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
docker --version
docker compose version
```

---

## 5.3 Clone and configure project

```bash
git clone https://github.com/egesamichael/lafia-ai-bot.git
cd chatlearning
cp .env.example .env
```

Edit `.env` and set:

```env
# Local Ollama mode (no paid LLM API)
OPENAI_API_KEY=dummy-key
OPENAI_BASE_URL=http://ollama:11434/v1
CHAT_MODEL=llama3.2:3b

# Keep embeddings local
EMBEDDING_BACKEND=local
LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2

# Optional channels (leave blank if unused)
AFRICAS_TALKING_API_KEY=
AFRICAS_TALKING_USERNAME=
MOODLE_BASE_URL=
MOODLE_TOKEN=
```

---

## 5.4 Start containers

```bash
export OLLAMA_MODEL=llama3.2:3b
docker compose --profile local-llm up -d --build
docker compose ps
```

First run pulls the model and may take several minutes.

---

## 5.5 Verify app health

```bash
curl -I http://127.0.0.1:8000
curl -s http://127.0.0.1:8000/api/sms/config-status
```

If needed:

```bash
docker compose logs -f app
docker compose logs -f ollama
```

---

## 5.6 Add Nginx reverse proxy + HTTPS

Install Nginx + Certbot:

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

Create Nginx site config at `/etc/nginx/sites-available/chatlearning`:

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable and reload:

```bash
sudo ln -s /etc/nginx/sites-available/chatlearning /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

Request TLS cert:

```bash
sudo certbot --nginx -d yourdomain.com
```

---

## 5.7 Add low-cost backup policy (recommended)

Minimum safe policy:
- Daily snapshot of whole server or Docker volumes
- Retention: 7 daily + 4 weekly

Estimated recurring:
- Around **$4–$5/month** for ~80 GB (provider-dependent).

---

## 6. Cost scenarios

## 6.1 Scenario A: absolute minimum

- Use existing server
- No backups
- No SMS
- No WhatsApp
- Local Ollama only

**Monthly total:** `existing server cost + $0`

## 6.2 Scenario B: recommended low-risk

- Existing server
- Daily backups (~80 GB)
- Local Ollama only

**Monthly total:** `existing server cost + ~$4 to $5`

## 6.3 Scenario C: add SMS support (example)

If SMS is enabled and you process `2,000` user questions/month with ~`3` SMS segments each:
- `6,000` SMS segments total
- At UGX `27` average: `162,000 UGX/month` variable SMS cost

Total becomes:
- `existing server cost + backup cost + SMS variable cost`

---

## 7. Operations checklist

Daily/weekly:
- Check `docker compose ps`
- Review `docker compose logs --tail=200 app`
- Verify free disk space: `df -h`
- Prune unused Docker artifacts monthly:

```bash
docker system prune -f
```

Model/storage hygiene:
- Keep only one Ollama model installed
- Remove unused models:

```bash
docker exec -it $(docker compose ps -q ollama) ollama list
docker exec -it $(docker compose ps -q ollama) ollama rm <model_name>
```

---

## 8. Final recommendation

For your server size and lowest recurring cost target:
1. Use **one small Ollama model (3B)**.
2. Keep **all AI and embeddings local**.
3. Start with **no paid channels**.
4. Spend only on **backups** as your first recurring add-on.

This gives you the lowest recurring cost while still remaining production-usable.

---

## 9. Pricing sources

- AWS Route 53 pricing: https://aws.amazon.com/route53/pricing/
- AWS Lightsail pricing (backup and transfer reference): https://aws.amazon.com/lightsail/pricing/
- OpenAI API pricing (comparison baseline): https://openai.com/api/pricing/
- OpenAI platform pricing: https://platform.openai.com/pricing
- DeepSeek pricing (comparison baseline): https://api-docs.deepseek.com/quick_start/pricing
- Africa’s Talking pricing: https://africastalking.com/pricing
- Twilio WhatsApp pricing: https://www.twilio.com/en-us/whatsapp/pricing
- Let’s Encrypt (free TLS): https://letsencrypt.org/
- Ollama model library: https://ollama.com/library
