# Deploying Auto-Sell on EC2 + Coolify

Coolify is a self-hosted PaaS. You install it on an EC2 instance and it handles
deployments, HTTPS, environment variables, and service orchestration via a web UI —
similar to Railway but running on your own server.

---

## Part 1 — Provision the EC2 Instance

### 1.1 — Launch the instance

In the AWS Console → EC2 → Launch Instance:

| Setting | Value |
|---|---|
| AMI | Ubuntu 22.04 LTS (64-bit x86) |
| Instance type | **t3.medium** (2 vCPU, 4 GB RAM) minimum |
| Storage | 20 GB gp3 (default is fine) |
| Key pair | Create or select an existing key pair — you'll need the `.pem` file to SSH in |

### 1.2 — Configure the security group

Add these inbound rules:

| Type | Port | Source | Why |
|---|---|---|---|
| SSH | 22 | Your IP | SSH access |
| HTTP | 80 | 0.0.0.0/0 | Coolify redirects to HTTPS |
| HTTPS | 443 | 0.0.0.0/0 | All app traffic |
| Custom TCP | 8000 | Your IP | Coolify dashboard (temporary, close after setup) |

### 1.3 — Point a domain at the instance

Coolify manages HTTPS via Let's Encrypt but needs a real domain — IP-only deployments
won't get SSL certificates.

In your DNS provider (Cloudflare, Route 53, etc.), create:

```
A    autosell.yourdomain.com    →  <ec2-public-ip>
A    coolify.yourdomain.com     →  <ec2-public-ip>   (for the Coolify dashboard)
```

Use the elastic IP feature in EC2 to make the public IP permanent so it doesn't
change on instance restart: EC2 → Elastic IPs → Allocate → Associate with instance.

---

## Part 2 — Install Coolify

### 2.1 — SSH into the instance

```bash
chmod 400 your-key.pem
ssh -i your-key.pem ubuntu@<ec2-public-ip>
```

### 2.2 — Run the Coolify installer

```bash
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
```

This installs Docker, Docker Compose, and Coolify itself. It takes 2–5 minutes.

### 2.3 — Access the Coolify dashboard

Open `http://<ec2-public-ip>:8000` in your browser.

- Create your admin account on first load
- Go to **Settings → Instance** and set your Coolify dashboard domain to
  `coolify.yourdomain.com` — Coolify will then issue a Let's Encrypt cert and
  you can close port 8000 in the security group afterwards

---

## Part 3 — Add Your Server to Coolify

Coolify manages the EC2 instance as a "Server" resource.

1. In the Coolify dashboard: **Servers → Add Server**
2. Choose **Localhost** (since Coolify is running on the same EC2 instance)
3. Click **Validate** — it will SSH to itself and confirm Docker is available
4. You'll see the server appear as **Healthy**

---

## Part 4 — Provision Databases

Coolify can run managed Postgres and Redis containers on your server.

### 4.1 — Postgres (with pgvector)

1. **Databases → Add Database → PostgreSQL**
2. Change the Docker image from `postgres:16` to **`pgvector/pgvector:pg16`**
   (this is required — the standard image doesn't have the vector extension)
3. Set a strong password and note the generated `DATABASE_URL` — you'll paste
   this into your app's environment variables later
4. Click **Start**

After it starts, enable the pgvector extension:

1. Click the database → **Execute Command**
2. Run: `CREATE EXTENSION IF NOT EXISTS vector;`

### 4.2 — Redis

1. **Databases → Add Database → Redis**
2. Leave defaults, click **Start**
3. Note the generated `REDIS_URL`

---

## Part 5 — Connect Your GitHub Repository

1. **Sources → Add → GitHub App** (or use the public GitHub integration)
2. Follow the OAuth flow to give Coolify access to your repository
3. Select the `auto-sell` repo

---

## Part 6 — Create the Application Services

Auto-sell needs three services running from the same Docker image with different
start commands: **web**, **worker**, and **beat**.

In Coolify: **Projects → New Project → "auto-sell"** then add each service below.

### 6.1 — Web service (Django + Gunicorn)

1. **Add Resource → Application → Docker (from Dockerfile)**
2. Select your GitHub repo and the `main` branch
3. Leave the **Dockerfile** field pointing to `./Dockerfile`
4. **Start command**: leave blank (uses the `CMD` in the Dockerfile)
5. **Port**: `8000`
6. **Domain**: `autosell.yourdomain.com`
   - Enable **HTTPS** — Coolify will get a Let's Encrypt cert automatically
7. Add all environment variables (see Part 7 below)
8. Click **Deploy**

### 6.2 — Worker service (Celery)

1. **Add Resource → Application → Docker (from Dockerfile)**
2. Same repo and branch as the web service
3. **Start command** (override the Dockerfile CMD):
   ```
   celery -A auto_sell worker -l info
   ```
   Note: do **not** use `--pool=solo` here — that flag is macOS-only. Linux uses the
   default prefork pool which is correct for production.
4. **No port, no domain** — this service has no HTTP interface
5. Add the same environment variables as the web service
6. Click **Deploy**

### 6.3 — Beat service (Celery Beat)

1. **Add Resource → Application → Docker (from Dockerfile)**
2. Same repo and branch
3. **Start command**:
   ```
   celery -A auto_sell beat -l info
   ```
4. **No port, no domain**
5. Same environment variables
6. Click **Deploy**

> **Important:** Run exactly **one** beat service. Running two beat instances
> will cause duplicate task executions (e.g. the abandoned conversation sweep
> fires twice per hour).

---

## Part 7 — Environment Variables

Set these on **all three services** (web, worker, beat). In Coolify, go to each
service → **Environment Variables**.

```env
# Django
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_urlsafe(50))">
DEBUG=False
DJANGO_SETTINGS_MODULE=auto_sell.settings.production
ALLOWED_HOSTS=autosell.yourdomain.com

# Database — copy the value Coolify generated in Part 4.1
DATABASE_URL=postgres://...

# Redis — copy the value Coolify generated in Part 4.2
REDIS_URL=redis://...

# WhatsApp
WA_API_BASE=https://graph.facebook.com/v19.0

# DeepSeek
DEEPSEEK_API_KEY=sk-...

# Paystack
PAYSTACK_SECRET_KEY=sk_live_...
PAYSTACK_PUBLIC_KEY=pk_live_...

# Cloudflare R2
S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
S3_ACCESS_KEY=
S3_SECRET_KEY=
S3_BUCKET_NAME=auto-sell-media
S3_REGION=auto
S3_CDN_BASE_URL=https://pub-<hash>.r2.dev
```

Coolify has a **Shared Variables** feature under the Project — set them once
there and they apply to all services in the project automatically.

---

## Part 8 — Run Migrations and Create Superuser

After the web service deploys successfully:

1. Click the **web** service in Coolify
2. Go to **Execute Command** (or the terminal icon)
3. Run migrations:
   ```bash
   python manage.py migrate
   ```
4. Create the platform superuser:
   ```bash
   python manage.py createsuperuser
   ```

These only need to run once. Future deployments run migrations automatically if
you add a **Release Command** in Coolify → web service → Settings:
```
python manage.py migrate
```

---

## Part 9 — Register the Webhook with Meta

1. Go to [developers.facebook.com](https://developers.facebook.com) → Your App → WhatsApp → Configuration
2. Set the **Callback URL** to:
   ```
   https://autosell.yourdomain.com/api/webhooks/whatsapp/<tenant-slug>/
   ```
3. Set the **Verify Token** to whatever is in `Tenant.wa_webhook_verify_token`
   for your first tenant (set this in Django Admin after creating the tenant)
4. Click **Verify and Save**
5. Subscribe to the **messages** webhook field

---

## Part 10 — End-to-End Smoke Test

With everything running, verify the full flow:

1. **Webhook verification**: send a GET request to your webhook URL — Meta will
   call it automatically when you click Verify in the Meta dashboard
2. **Inbound message**: send a WhatsApp message from a test number to your
   business number → confirm the bot replies
3. **Catalog search**: mention a product name → confirm the bot returns relevant
   products from your catalog
4. **Payment link**: negotiate to a price → confirm a Paystack link is generated
   and sent
5. **Payment confirmation**: complete the test payment → confirm the conversation
   state changes to `completed` and the owner receives a WhatsApp alert
6. **Escalation**: send a message that triggers escalation (e.g. "speak to a
   manager") → confirm the owner receives the escalation alert and the bot
   goes silent afterwards

---

## Ongoing Operations

### Deploying updates

Push to your `main` branch. In Coolify, either:
- Click **Redeploy** on each service manually, or
- Enable **Auto Deploy** in each service's settings → triggers on every push

### Viewing logs

Coolify → service → **Logs** tab. Shows stdout/stderr in real time, which is
where Django's logging config (`LOGGING` in `base.py`) writes to.

### Scaling workers

If message volume increases, increase Celery worker concurrency by changing
the worker start command:
```
celery -A auto_sell worker -l info --concurrency=4
```
Or add a second worker service in Coolify pointing to the same repo.

### Monitoring

Coolify shows CPU, memory, and uptime per service on the dashboard. For deeper
observability, the Celery Flower dashboard can be added as a fourth service:
```
celery -A auto_sell flower --port=5555
```
with port 5555 exposed and a domain assigned.
