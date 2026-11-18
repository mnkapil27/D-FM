# Facebook Ads MCP Server

Your own server that lets **Claude manage Facebook and Instagram ads for all your clients**.

- It talks **directly** to Meta (graph.facebook.com). No third-party tools.
- One token (from your Business Manager) works for **all clients**.
- Every client has its own **ad account** and **Page**, written in one file (`clients.json`).
- **Safe by default:** nothing changes unless you say `confirm=true`. New campaigns, ad sets and ads are always created **PAUSED**. You can set a **max budget** per client.

---

## What Claude can do with it

| Tool | What it does |
|---|---|
| `list_clients` | Shows your clients from `clients.json` |
| `discover_ad_accounts` | Shows every ad account your token can see (helps you fill `clients.json`) |
| `discover_pages` | Shows every Page your token can see |
| `get_insights` | Spend, impressions, clicks, CPC, CTR, leads, CPL, purchases, ROAS for one client. By account, campaign, ad set or ad. Any date range. |
| `get_all_clients_insights` | One line per client for all clients. Good for a daily/weekly report. |
| `list_campaigns` / `list_adsets` / `list_ads` | See what is running and the budgets |
| `create_campaign` / `create_adset` / `create_ad` | Make new ones (always PAUSED) |
| `update_budget` | Change daily or lifetime budget (checks your max limit) |
| `set_status` | Pause or activate a campaign, ad set or ad |
| `get_page_insights` | Page followers and Page numbers |
| `list_lead_forms` | Instant forms on the Page (for lead ads) |

**Money is in the ad account currency.** `25` means 25 INR (or 25 USD). Not cents. The server converts it for Meta.

You can talk to Claude normally, for example:

- "Show me spend, leads and CPL for all clients last 7 days."
- "For Pizza Hub, which campaign has the best CPL this month?"
- "Pause the campaign 'Diwali Offer' for Smile Dental."
- "Increase the Pizza Hub ad set budget to 1500 per day."
- "Create a lead campaign for Smile Dental, ad set for Ahmedabad age 25-55, budget 800/day."

Claude will first show you a **preview**. It only does the change after you say yes.

---

## Step 1. Create the Meta Developer App

1. Go to <https://developers.facebook.com/apps> and log in with your Facebook profile.
2. Click **Create App**.
3. Choose the use case **"Other"**, then app type **"Business"**. (If you see a use case called "Create & manage ads with Marketing API", you can choose that.)
4. Give it a name, for example `My Agency Ads Tool`. Select your **Business Manager** (Business portfolio). Click **Create**.
5. In the app dashboard, find **Marketing API** and click **Set up**.
6. Go to **App settings → Basic**. Add a Privacy Policy URL (your website page is ok). Save.

## Step 2. Create the System User and the token

A System User is a "robot user" inside your Business Manager. Its token does not expire when your password changes.

1. Go to <https://business.facebook.com/settings> (Business Settings).
2. **Accounts → Apps**: check that your new app is there. If not, click **Add** and add it by App ID.
3. **Users → System users → Add**. Name: `claude-ads`. Role: **Admin**. Click **Create**.
4. Click the system user, then **Assign assets** (or **Add assets**):
   - **Ad accounts**: select every client ad account. Give **Manage ad accounts / Full control**.
   - **Pages**: select every client Page. Give **Full control** (or at least "Create ads" + "View insights" + "Content").
   - **Apps**: select your app. Give **Full control** (Develop app).

   Client accounts that belong to the client's own Business Manager must first be **shared with your Business as a partner**. Then they show up here.
5. Still on the system user, click **Generate new token**.
   - App: choose your app.
   - Token expiration: **Never**.
   - Permissions: tick these:
     - `ads_management`
     - `ads_read`
     - `business_management`
     - `pages_read_engagement`
     - `pages_manage_ads`
     - `pages_show_list` (to list Pages)
     - `read_insights` (for Page insights)
     - `leads_retrieval` (optional, for lead forms)
6. Click **Generate**. **Copy the token now** (it starts with `EAA...`). Meta shows it only once.

> **Keep the token secret.** It can spend money on all your clients' ad accounts. Never put it in a chat, an email, or on GitHub. Put it only in `.env` (your computer) or in the hosting dashboard (Render / Railway).

**If you get permission errors later:** in the developer app open **App Review → Permissions and Features** and request **Advanced Access** for `ads_management` and `ads_read`. Standard access also has lower rate limits. Meta may ask for Business Verification.

## Step 3. Fill your client list

1. Copy the example file:
   ```
   cp clients.example.json clients.json
   ```
2. Open `clients.json` and add one block per client:
   ```json
   {
     "clients": {
       "pizza_hub": {
         "name": "Pizza Hub",
         "ad_account_id": "act_123456789012345",
         "page_id": "102030405060708",
         "max_daily_budget": 2000,
         "max_lifetime_budget": 50000,
         "notes": "Lead ads, Ahmedabad only"
       }
     }
   }
   ```
   - `pizza_hub` = short name. Use small letters and `_`. You will use this name with Claude.
   - `ad_account_id` = from Ads Manager URL (`act=123...`) or Business Settings → Ad accounts. `act_` in front is added for you if you forget.
   - `page_id` = Page → About → Page transparency, or Business Settings → Pages.
   - `max_daily_budget` / `max_lifetime_budget` = optional safety limit, in the account currency. Claude can **never** set a budget above this.
3. Easy way to find all IDs: start the server (Step 4) and ask Claude "run discover_ad_accounts and discover_pages".

`clients.json` is in `.gitignore`, so it is not uploaded to GitHub by mistake.

## Step 4. Run it on your computer

You need **Python 3.10 or newer**.

```bash
cd facebook-ads-mcp
python -m venv .venv
# Mac / Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and fill:

- `META_ACCESS_TOKEN` = the System User token from Step 2.
- `MCP_AUTH_TOKEN` = a long random password. Make one with:
  ```
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

Start the server:

```bash
python -m fb_ads_mcp
```

Check it works: open <http://localhost:8000/health>. You should see `{"ok": true, ...}`.

Run the tests (no real Meta calls):

```bash
pip install pytest httpx
python -m pytest -q
```

### Use it in Claude Desktop or Claude Code on your computer (no hosting)

Claude Desktop: open **Settings → Developer → Edit Config** and add:

```json
{
  "mcpServers": {
    "facebook-ads": {
      "command": "/full/path/to/facebook-ads-mcp/.venv/bin/python",
      "args": ["-m", "fb_ads_mcp", "--stdio"],
      "cwd": "/full/path/to/facebook-ads-mcp"
    }
  }
}
```

(On Windows the python path is `C:\\...\\facebook-ads-mcp\\.venv\\Scripts\\python.exe`.) Restart Claude Desktop.

Claude Code:

```bash
claude mcp add facebook-ads -- /full/path/.venv/bin/python -m fb_ads_mcp --stdio
```

## Step 5. Deploy it online (so Claude on web and phone can use it)

### Option A: Render

1. Put this code in a **private** GitHub repo (see "Put the code on GitHub" below).
2. Go to <https://render.com> → **New → Blueprint** → choose your repo. Render reads `render.yaml`.
   (Or **New → Web Service**, Build command `pip install -r requirements.txt`, Start command `python -m fb_ads_mcp`.)
3. In **Environment**, add:
   - `META_ACCESS_TOKEN` = your token
   - `MCP_AUTH_TOKEN` = your random password
   - `CLIENTS_JSON` = the whole content of your `clients.json` (paste it all)
4. Deploy. You get a URL like `https://facebook-ads-mcp.onrender.com`.
5. Test: open `https://facebook-ads-mcp.onrender.com/health`.

Use a paid plan (Starter). The free plan sleeps, and Claude may time out on the first call.

### Option B: Railway

1. Go to <https://railway.app> → **New Project → Deploy from GitHub repo** → choose your repo.
2. In **Variables**, add the same 3 variables: `META_ACCESS_TOKEN`, `MCP_AUTH_TOKEN`, `CLIENTS_JSON`.
3. Railway uses the `Procfile` (or the `Dockerfile`). In **Settings → Networking**, click **Generate Domain**.
4. Test: open `https://your-app.up.railway.app/health`.

**When you add a new client:** update `CLIENTS_JSON` in Render/Railway and redeploy (or restart).

## Step 6. Add it to Claude as a custom connector

1. In Claude, open **Settings → Connectors** (on Team/Enterprise, an owner does this in **Admin settings → Connectors**).
2. Click **Add custom connector**.
3. Name: `Facebook Ads`.
4. URL: your server URL + `/mcp?key=` + your `MCP_AUTH_TOKEN`:
   ```
   https://facebook-ads-mcp.onrender.com/mcp?key=YOUR_MCP_AUTH_TOKEN
   ```
5. Leave OAuth fields empty. Click **Add**.
6. In a new chat, click the **tools / connectors** button and turn on **Facebook Ads**.
7. Try: "List my clients" then "Show spend and leads for all clients yesterday".

Anyone with this URL can control your ads. **Do not share the URL.** If it leaks, change `MCP_AUTH_TOKEN` in Render/Railway and update the connector URL.

---

## Safety rules (built in)

1. **Confirm flag.** `create_*`, `update_budget` and `set_status` only show a preview when `confirm` is false (the default). The change happens only with `confirm=true`. Claude is told to ask you before it sends `confirm=true`.
2. **Always PAUSED.** New campaigns, ad sets and ads are created paused. You (or Claude, with confirm) activate them later.
3. **Budget limit.** `max_daily_budget` / `max_lifetime_budget` per client, or `GLOBAL_MAX_DAILY_BUDGET` / `GLOBAL_MAX_LIFETIME_BUDGET` in `.env` for all. Higher budgets are blocked even with confirm.
4. **Right client only.** Before any change, the server checks that the campaign / ad set / ad really belongs to that client's ad account. So Claude cannot change client A's ads by mistake while working on client B.
5. **Only known accounts.** Tools only work for clients in `clients.json` (unless you set `ALLOW_UNKNOWN_ACCOUNTS=true`).
6. **Secret key** on the online server (`MCP_AUTH_TOKEN`). Without the key, every request gets "401 unauthorized".

## Settings (`.env`)

| Name | Needed | What |
|---|---|---|
| `META_ACCESS_TOKEN` | yes | System User token |
| `MCP_AUTH_TOKEN` | yes (online) | Secret key for the URL |
| `META_API_VERSION` | no | Default `v23.0`. Change if Meta says the version is too old. |
| `CLIENTS_FILE` | no | Default `clients.json` |
| `CLIENTS_JSON` | no | Whole client list as JSON (use on Render/Railway) |
| `GLOBAL_MAX_DAILY_BUDGET` | no | Max daily budget for all clients |
| `GLOBAL_MAX_LIFETIME_BUDGET` | no | Max lifetime budget for all clients |
| `ALLOW_UNKNOWN_ACCOUNTS` | no | `true` lets tools use any `act_...` id |
| `PORT` / `HOST` | no | Server port (Render/Railway set `PORT` for you) |

## Put the code on GitHub

1. On GitHub click **New repository**. Name: `facebook-ads-mcp`. Choose **Private**. Do not add a README. Create.
2. In this folder run:
   ```bash
   git init
   git add .
   git commit -m "Facebook Ads MCP server"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/facebook-ads-mcp.git
   git push -u origin main
   ```
   `.env` and `clients.json` are ignored, so your token and client list stay on your computer.

## Common problems

| Message | Fix |
|---|---|
| `META_ACCESS_TOKEN is not set` | Fill `.env` or the hosting variables |
| `(190) Invalid OAuth access token` | Token is wrong or deleted. Make a new one (Step 2.5) |
| `(200) Permissions error` / `(10)` | System User is not assigned to that ad account or Page (Step 2.4), or a permission is missing in the token |
| `(100) Invalid parameter` | Meta did not like a value (for example targeting or objective). The message says which one. |
| `(17)` / `(613)` rate limit | Too many calls. Wait a few minutes. Ask for Advanced Access. |
| Page metric error | Meta sometimes renames Page metrics. Pass other names in `metrics`. Followers still work. |
| `401 unauthorized` | The `?key=` in the connector URL is not the same as `MCP_AUTH_TOKEN` |
| Wrong budget amount | Budgets are in account currency, not cents. 500 = 500 INR. |

## Files

```
fb_ads_mcp/
  server.py     all the tools
  meta_api.py   small client for graph.facebook.com
  insights.py   turns Meta numbers into spend / leads / CPL / CPC / ROAS
  config.py     reads .env and clients.json
  __main__.py   starts the server (HTTP with secret key, or --stdio)
tests/          offline tests
clients.example.json, .env.example, render.yaml, Procfile, Dockerfile
```
