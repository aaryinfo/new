# GitHub Setup & Vercel Deployment

## Step 1: Create GitHub Repository

1. Go to https://github.com/new
2. Create a new repository:
   - Name: `nse-fo-scanner` (or any name you prefer)
   - Description: "NSE F&O Stock Scanner with AI Agent"
   - Visibility: Public or Private
   - **DO NOT** initialize with README (we already have files)
3. Click "Create repository"

## Step 2: Push Your Code to GitHub

After creating the repository, GitHub will show you commands. Use these:

```bash
# Navigate to your project folder
cd "c:\Users\aaryi\Downloads\files (14) - whole project to upload"

# Update the remote URL (replace YOUR_USERNAME and YOUR_REPO_NAME)
git remote set-url origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git

# Push to GitHub
git push -u origin main
```

**Example:**
```bash
git remote set-url origin https://github.com/aaryinfo/nse-fo-scanner.git
git push -u origin main
```

## Step 3: Deploy to Vercel

### Option A: Via Vercel Dashboard (Easiest)

1. Go to https://vercel.com/new
2. Click "Import Git Repository"
3. Select your GitHub repository
4. Vercel will auto-detect Flask
5. Click "Deploy"
6. Done! Your app will be live in 2-3 minutes

### Option B: Via Vercel CLI

```bash
# Install Vercel CLI
npm i -g vercel

# Login
vercel login

# Link to your GitHub repo
vercel link

# Deploy
vercel --prod
```

## Step 4: Access Your App

Once deployed, Vercel will give you a URL like:
- `https://nse-fo-scanner.vercel.app`
- `https://your-project-name.vercel.app`

Open it in your browser - no login required!

## Troubleshooting

### If git push fails with authentication error:

**Option 1: Use GitHub CLI (Recommended)**
```bash
# Install GitHub CLI
winget install GitHub.cli

# Login
gh auth login

# Push
git push -u origin main
```

**Option 2: Use Personal Access Token**
1. Go to GitHub → Settings → Developer settings → Personal access tokens
2. Generate new token (classic)
3. Select scopes: `repo` (full control)
4. Copy the token
5. When pushing, use token as password:
   ```bash
   git push -u origin main
   # Username: your_github_username
   # Password: paste_your_token_here
   ```

**Option 3: Use GitHub Desktop**
1. Download GitHub Desktop: https://desktop.github.com
2. Open the app and sign in
3. Add your local repository
4. Commit and push via the GUI

## Alternative: Deploy Without GitHub

If you don't want to use GitHub, you can deploy directly:

```bash
# Install Vercel CLI
npm i -g vercel

# Login
vercel login

# Deploy from local folder
cd "c:\Users\aaryi\Downloads\files (14) - whole project to upload"
vercel --prod
```

This will upload your files directly to Vercel without GitHub.

## What's Already Done ✅

- ✅ All Supabase code removed
- ✅ vercel.json configured correctly
- ✅ No environment variables required
- ✅ Code committed to git
- ✅ Ready to push and deploy

## Next Steps

1. Create GitHub repository
2. Update git remote URL
3. Push code to GitHub
4. Deploy via Vercel dashboard
5. Access your live app!

---

**Need Help?**
- GitHub Docs: https://docs.github.com
- Vercel Docs: https://vercel.com/docs
- Git Basics: https://git-scm.com/book/en/v2/Getting-Started-Git-Basics
