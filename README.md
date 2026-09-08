<img src="sponsorscout/data/sponsorscout.png" alt="SponsorScout" width="420">

# SponsorScout

**Find verified jobs from official company career pages and ATS boards — right on your desktop.**

SponsorScout is a free, fully local desktop application. It scans official
company career pages and 17 ATS job boards (Greenhouse, Lever, Ashby, Workday
and more), scores every job for EU Blue Card eligibility and relocation
support, and helps you track your applications — all without any accounts,
cloud services or telemetry.

---

## 📥 Download

Ready-to-use installers are published on the GitHub Releases page:

👉 **[Download the latest release](https://github.com/Kazake95/SponsorScout/releases)**

| Platform | File |
|----------|------|
| Windows 10 / 11 | `sponsorscout-<version>-setup.exe` |
| Linux (Debian / Ubuntu) | `sponsorscout_<version>_amd64.deb` |

> The links above point to the Releases page — paste your published asset
> URLs here when the release is live.

---

## ✨ What SponsorScout Does

- **Scans official sources only** — 17 ATS platforms plus each company's own
  career page when no public ATS API exists.
- **Scores every job** — EU Blue Card eligibility, relocation support and
  remote-work type are detected from the job description.
- **Keeps everything local** — all data is stored in a SQLite database on your
  own computer. Nothing is uploaded anywhere.
- **Tracks your applications** — a simple pipeline: Saved → Applied →
  Interview → Offer → Rejected.
- **AI assistance (optional)** — job rating, CV tailoring and cover-letter
  generation, either through your normal web AI chat (ChatGPT, Gemini,
  Claude…) or a direct API key.
- **Two languages** — English and Italian, switchable at any time from the
  header dropdown.

---

## 🚀 Quick Start

```bash
# 1. Install the dependencies
pip install -r requirements.txt

# 2. Launch the app
python -m sponsorscout.main
```

On the very first launch a welcome dialog asks whether to run the initial
scan. Click **Yes** — it takes roughly 1–3 minutes and fills the database
with jobs from every seeded company.

---

## 🗂 The Five Tabs

### 1. Dashboard
A live overview of your database: total companies, verified jobs, sponsored
jobs, remote jobs and EU Blue Card jobs — plus a "Top companies by
sponsorship" table and a "Jobs by country" table. The **Rescan Companies**
button starts a fresh scan; **Refresh** reloads the numbers.

### 2. Search
The main job browser. Filter by title, company, country, location,
sponsorship, Blue Card, relocation and remote type, then sort by best match
or recency. Selecting a row opens the AI rating panel and the right-click
menu (open in browser, save to applications, copy the rating prompt).

### 3. Applications
Your personal application tracker. Select any saved job to set its status
(Saved / Applied / Interview / Offer / Rejected) and add notes.

### 4. Tools
The control centre:
- **Scanner** — start a scan across all seeded companies (Quick = fast,
  API-only; Full = browser crawl). Live output appears in the log window.
- **Scan History** — every past scan run; select one to view or download a
  detailed per-company log including errors.
- **Data Quality** — remove duplicates, clear expired jobs, or wipe scanned
  data.
- **Freshness Check** — re-verifies saved jobs against their live pages and
  marks dead listings as expired.
- **AI Settings** — provider, API key and model configuration.

### 5. Data Management
Edit the company lists that SponsorScout scans. Two editors are provided —
**ATS portals** and **Career portals**. You can add, edit or remove
companies; changes are saved to your personal seed files and take effect on
the next scan. A "Reset to bundled defaults" button restores the original
lists.

---

## 🌐 Language Switching

Use the dropdown in the top-right corner of the header to switch between
**English** and **Italiano**. Your choice is remembered and restored on the
next launch.

---

## ⚙️ How Scanning Works

1. SponsorScout reads its **seed files** — curated lists of companies with
   their career URLs and ATS type.
2. Companies with a known ATS are scanned through the official **job-board
   API** (fast).
3. Companies without a public ATS are crawled through their **career page**
   with a headless browser.
4. Every job is classified (Blue Card / relocation / remote) and
   deduplicated.
5. Results are stored in the local SQLite database and appear immediately in
   the Dashboard and Search tabs.

Seed files live in your user data folder and can be edited in the Data
Management tab.

---

## 💾 Where Your Data Lives

| Platform | Location |
|----------|----------|
| Windows | `%APPDATA%\SponsorScout` |
| Linux / macOS | `~/.sponsorscout` |

Contents: `sponsorscout.db` (all jobs, companies and scan history),
`seeds/` (your editable company lists), `locale.json` (language preference),
plus AI prompt templates.

---

## 🏗 Building From Source

**Windows (Inno Setup installer):**

```powershell
.\build_exe.ps1
```

Output: `dist\sponsorscout-<version>-setup.exe` (requires Inno Setup 6).

**Linux (.deb package):**

```bash
./build_deb.sh
```

Output: `dist/sponsorscout_<version>_amd64.deb`.

---

## 📋 Requirements

- Python 3.10 or newer
- PySide6, requests, beautifulsoup4, lxml, Pillow (installed via
  `requirements.txt`)
- Playwright Chromium (downloaded automatically for the career-page crawler)

---

## 🤖 AI Providers (optional)

Configure in **Tools → AI Settings**:

- Google AI Studio (free tier)
- NVIDIA NIM (free credits)
- OpenAI
- Any OpenAI-compatible endpoint (vLLM, Ollama, LM Studio)

Or skip the API entirely and use the built-in browser AI chat workflow with
your normal ChatGPT / Gemini / Claude account.

---

## 📄 License

MIT — see [LICENSE](LICENSE).
