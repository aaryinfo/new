# 🚂 Deploy to Railway.app (Recommended)

## Why Railway Instead of Vercel?

Your app **requires**:
- ✅ Background threads (stock scanning)
- ✅ Continuous processes (agent loop)
- ✅ File system persistence (CSV storage)
- ✅ No timeout limits
- ✅ Long-running operations

**Vercel doesn't support these** (serverless limitations)  
**Railway supports everything** (traditional server environment)

## Quick Deploy (5 Minutes)

### Step 1: Install Railway CLI

```bash
npm i -g @railway/cli
```

### Step 2: Login to Railway

```bash
railway login
```

This opens your browser to authenticate.

### Step 3: Deploy

```bash
# Navigate to your project
cd "c:\Users\aaryi\Downloads\files (14) - whole project to upload"

# Initialize Railway project
railway init

# Deploy
railway up
```

### Step 4: Get Your URL

```bash
# Generate public URL
railway domain

# Open in browser
railway open
```

## What Railway Provides

✅ **Full Flask Support**
- All features work perfectly
- Background threads run normally
- No timeout limits
- Persistent file storage

✅ **Free Tier**
- $5 free credit per month
- 500 hours of runtime
- 1GB RAM
- 1GB storage
- Perfect for your app

✅ **Easy Deployment**
- One command deployment
- Auto-redeploy on git push
- Built-in monitoring
- Easy environment variables

## Alternative: Deploy via GitHub

### Step 1: Go to Railway Dashboard
https://railway.app/new

### Step 2: Connect GitHub
- Click "Deploy from GitHub repo"
- Select `aaryinfo/new`
- Click "Deploy Now"

### Step 3: Configure
Railway auto-detects Python and Flask:
- Build Command: `pip install -r requirements.txt`
- Start Command: `python app.py`

### Step 4: Add Domain
- Go to Settings → Networking
- Click "Generate Domain"
- Your app is live!

## Environment Variables (Optional)

Add these in Railway dashboard if needed:

```
MONGO_URI=your_mongodb_connection_string
ANTHROPIC_API_KEY=your_claude_api_key
KITE_API_KEY=your_zerodha_key
KITE_ACCESS_TOKEN=your_zerodha_token
```

## Comparison: Vercel vs Railway

| Feature | Vercel | Railway |
|---------|--------|---------|
| Background Threads | ❌ No | ✅ Yes |
| Timeout | ⏱️ 10 sec | ✅ None |
| File Storage | ❌ Ephemeral | ✅ Persistent |
| Long Processes | ❌ No | ✅ Yes |
| Stock Scanning | ❌ Broken | ✅ Works |
| Agent Trading | ❌ Broken | ✅ Works |
| Real-time Updates | ❌ No | ✅ Yes |
| Price | 🆓 Free | 🆓 Free ($5/mo credit) |

## What Works on Railway

✅ **All Features:**
- Real-time stock scanning (206 F&O stocks)
- Background data refresh
- AI Agent auto-trading
- Trading journal with CSV persistence
- Daily reports
- Charts and analysis
- All API endpoints
- WebSocket support (if needed)

## Troubleshooting

### If `railway` command not found:
```bash
# Reinstall Railway CLI
npm i -g @railway/cli --force

# Or use npx
npx @railway/cli login
npx @railway/cli up
```

### If deployment fails:
1. Check Railway logs in dashboard
2. Verify `requirements.txt` is complete
3. Ensure `app.py` is in root directory

### If app doesn't start:
1. Check Railway logs for errors
2. Verify Python version (Railway uses 3.11 by default)
3. Check that port 5000 is used (Railway auto-detects)

## Cost Estimate

**Free Tier:**
- $5 credit per month
- ~500 hours runtime
- Perfect for development/testing

**Paid (if needed):**
- $5/month for 500 hours
- $0.01 per additional hour
- Your app: ~$5-10/month

## Current Status

✅ **Vercel:** Minimal version deployed (limited features)  
🚀 **Railway:** Ready to deploy (full features)  

## Recommendation

**Deploy to Railway now** for full functionality:

```bash
npm i -g @railway/cli
railway login
cd "c:\Users\aaryi\Downloads\files (14) - whole project to upload"
railway up
```

Your app will work perfectly with all features! 🎉

---

**Need Help?**
- Railway Docs: https://docs.railway.app
- Railway Discord: https://discord.gg/railway
- Railway Status: https://status.railway.app
