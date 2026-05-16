# NSE F&O Scanner — AI-Powered Intraday Intelligence

## 🚀 Quick Deploy to Vercel

### Step 1 — Deploy to Vercel
```bash
# Install Vercel CLI
npm i -g vercel

# Login
vercel login

# Add optional environment variables (if needed)
vercel env add MONGO_URI          # optional - for MongoDB persistence
vercel env add ANTHROPIC_API_KEY  # optional - for Claude AI decisions
vercel env add KITE_API_KEY       # optional - for Zerodha live trading
vercel env add KITE_ACCESS_TOKEN  # optional - for Zerodha live trading

# Deploy
vercel --prod
```

### Step 2 — Access Your Dashboard
- Open your Vercel deployment URL
- No authentication required - direct access to the dashboard
- All features available immediately

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
| `MONGO_URI` | ⚠️ | MongoDB Atlas URI (falls back to CSV files) |
| `ANTHROPIC_API_KEY` | ⚙️ | Claude AI for trade decisions |
| `KITE_API_KEY` | ⚙️ | Zerodha Kite API key (live trading) |
| `KITE_ACCESS_TOKEN` | ⚙️ | Zerodha daily access token |

## 💻 Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill env vars (optional)
cp .env.example .env
# Edit .env with your values (all optional)

# Run locally
python app.py
# → http://localhost:5000
```
