# NSE F&O Scanner — AI-Powered Intraday Intelligence

## 🚀 Quick Deploy to Vercel

### Step 1 — Supabase Setup
1. Go to [supabase.com](https://supabase.com) → **New Project**
2. After creation, go to **Settings → API** and copy:
   - **Project URL** → `SUPABASE_URL`
   - **anon public key** → `SUPABASE_ANON_KEY`
   - **service_role key** → `SUPABASE_SERVICE_KEY`
   - **JWT Secret** (Settings → API → JWT Settings) → `SUPABASE_JWT_SECRET`
3. Go to **Authentication → Providers** → enable **Email** and optionally **Google**
4. In **Authentication → URL Configuration** set:
   - Site URL: `https://your-app.vercel.app`
   - Redirect URLs: `https://your-app.vercel.app/login.html`

### Step 2 — Supabase: Inject Keys into login.html
In `login.html`, replace these two lines with your actual values:
```js
const SUPA_URL  = 'https://YOUR_PROJECT.supabase.co';
const SUPA_ANON = 'YOUR_ANON_KEY_HERE';
```

### Step 3 — In index.html, set your Supabase URL and anon key
Find this section in `index.html`:
```js
const SUPABASE_URL  = '__SUPABASE_URL__';
const SUPABASE_ANON = '__SUPABASE_ANON__';
```
Replace with your actual values.

### Step 4 — Deploy to Vercel
```bash
# Install Vercel CLI
npm i -g vercel

# Login
vercel login

# Add environment variables (one-time setup)
vercel env add SUPABASE_URL
vercel env add SUPABASE_ANON_KEY
vercel env add SUPABASE_SERVICE_KEY
vercel env add SUPABASE_JWT_SECRET
vercel env add ADMIN_EMAIL
vercel env add MONGO_URI          # optional
vercel env add ANTHROPIC_API_KEY  # optional (for Claude AI decisions)
vercel env add KITE_API_KEY       # optional (for Zerodha live trading)
vercel env add KITE_ACCESS_TOKEN  # optional

# Deploy
vercel --prod
```

### Step 5 — Set Admin
- Sign up at `/login.html` using the email you set as `ADMIN_EMAIL`
- You automatically get the **ADMIN** role and see the admin panel

---

## 🏗 Project Structure
```
├── app.py          # Flask backend — scanner + AI agent + auth API
├── index.html      # Main dashboard (auth protected)
├── login.html      # Login / Signup / Forgot password page
├── vercel.json     # Vercel deployment config
├── requirements.txt
├── .env.example    # Copy to .env for local dev
└── .gitignore
```

## 👤 User Roles

| Role  | Access |
|-------|--------|
| **Admin** | Full dashboard + AI Agent controls + Admin Panel (user management, platform stats) |
| **User**  | Full dashboard + AI Agent view (read-only agent tab) |

## 🔐 Auth Flow
1. User visits `/` → redirected to `/login.html` if no valid session
2. User logs in via Email/Password or Google OAuth
3. Supabase issues JWT → stored in `localStorage`
4. Frontend sends `Authorization: Bearer <token>` on all API calls
5. Backend verifies JWT with `SUPABASE_JWT_SECRET`
6. Admin email (`ADMIN_EMAIL`) gets elevated permissions

## 🤖 AI Agent Rules (BUY LOW · SELL TOP)
- **Max 1 trade** at a time — quality over quantity
- **Min score 7/10** — only high-conviction institutional setups
- **BUY**: RSI < 40 (oversold) + price near support + stock not already pumped
- **SELL**: RSI > 65 (overbought) + price near resistance + stock not already dumped
- **45-minute cooldown** between trades
- **No re-entry** on same symbol same day
- **2% daily loss limit** — agent pauses if breached
- **Trailing stop** activates after 0.7% profit

## 🌍 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | ✅ | Your Supabase project URL |
| `SUPABASE_ANON_KEY` | ✅ | Supabase anon/public key |
| `SUPABASE_SERVICE_KEY` | ✅ | Supabase service role key (admin ops) |
| `SUPABASE_JWT_SECRET` | ✅ | JWT secret for token verification |
| `ADMIN_EMAIL` | ✅ | Email of the admin user |
| `MONGO_URI` | ⚠️ | MongoDB Atlas URI (falls back to memory) |
| `ANTHROPIC_API_KEY` | ⚙️ | Claude AI for trade decisions |
| `KITE_API_KEY` | ⚙️ | Zerodha Kite API key (live trading) |
| `KITE_ACCESS_TOKEN` | ⚙️ | Zerodha daily access token |

## 💻 Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill env vars
cp .env.example .env
# Edit .env with your values

# Run locally
python app.py
# → http://localhost:5000/login.html
# → http://localhost:5000
```
