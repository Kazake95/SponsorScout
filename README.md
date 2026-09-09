<img src="sponsorscout/data/sponsor scout.png" alt="Sponsor Scout" width="420">

# SponsorScout

[🇬🇧 English](#-english) · [🇮🇹 Italiano](#-italiano)

---

# 🇬🇧 English

## 📥 Download

Ready-to-use installers are published on the GitHub Releases page:

👉 **[Download the latest release](https://github.com/Kazake95/SponsorScout/releases/tag/SponsorScout_v_0.1.1)**

| Platform | File |
|----------|------|
| Windows 10 / 11 | `sponsorscout-<version>-setup.exe` |
| Linux (Debian / Ubuntu) | `sponsorscout_<version>_amd64.deb` |

> The links above point to the Releases page — paste your published asset
> URLs here when the release is live.

---

## ✨ What SponsorScout Does

- **Scans official sources only** — 8 ATS job boards (Ashby, Greenhouse,
  Lever, SmartRecruiters, Personio, Recruitee, Workable, Workday) via their
  public APIs, plus each company's own career page with a headless browser
  when there is no public ATS API.
- **Classifies every job** — EU Blue Card eligibility, relocation / visa
  support and remote-work type are detected from the job description.
- **Keeps everything local** — all data is stored in a SQLite database on your
  own computer. Nothing is uploaded anywhere.
- **Tracks your applications** — a simple pipeline: Saved → Applied →
  Interview → Offer → Rejected.
- **Gives you control** — deduplicate or wipe scanned data, re-verify jobs for
  freshness, and download detailed per-company scan logs.
- **Two languages** — English and Italian, switchable at any time from the
  header dropdown.

---

## 🚀 Quick Start

1. **Download** the installer for your platform from the link above.
2. **Install** it — you don't need Python or anything else; the app and its
   bundled browser come with the installer.
3. **Launch SponsorScout.** On the very first start a welcome box asks whether
   to run an initial scan — click **Yes**. It fetches jobs from every seeded
   company's official job board and career page, and fills the database (takes
   1–3 minutes).
4. Browse the results in the **Search** tab, filter by sponsorship / Blue
   Card / relocation / remote, and start tracking applications from the
   **Applications** tab.

That's it — everything runs locally on your computer.

---

## 🗂 The Five Tabs

### 1. Dashboard
A live overview of your database: total companies, verified jobs, sponsored
jobs, remote jobs and EU Blue Card jobs — plus a "Top companies by
sponsorship" table and a "Jobs by country" table. The **Rescan Companies**
button starts a fresh scan; **Refresh** reloads the numbers.

### 2. Search
The main job browser. Filter by title, company, location, country,
sponsorship, Blue Card, relocation and remote-work type (with a regex search
toggle), then sort by best match or recency. Right-click a row to open it in
your browser or save it to your applications.

### 3. Applications
Your personal application tracker. Select any saved job to set its status
(Saved / Applied / Interview / Offer / Rejected) and add notes.

### 4. Tools
The control centre:
- **Scanner** — start a scan across all seeded companies using either
  **Quick** (fast, API-only) or **Full browser** (thorough, also crawls
  career pages). The two modes return different job counts — see [Quick vs
  Full Browser Scan](#-quick-scan-vs-full-browser-scan). Live output appears
  in the log window.
- **Scan History** — every past scan run; select one to view or download a
  detailed per-company log including errors.
- **Data Quality** — remove duplicate jobs/companies, clear expired jobs, or
  wipe all scanned data.
- **Freshness Check** — re-verifies saved jobs against their live pages and
  marks dead listings as expired.

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

## 🔍 Quick Scan vs Full Browser Scan

There are **two scan modes**, and choosing the right one matters because they
produce **different job results**:

### ⚡ Quick Scan (API-only)
- Pulls jobs **only from the official job-board APIs** of companies that use a
  known ATS (Ashby, Greenhouse, Lever, SmartRecruiters, Personio, Recruitee,
  Workable, Workday).
- **Fast** — usually completes in seconds to a minute.
- **Partial results** — any company that does *not* expose a public ATS API
  (i.e. only has a career page) is skipped, so **its jobs will not appear**.

### 🧭 Full Browser Scan
- Does **everything the Quick scan does**, then also **crawls each company's
  own career page** with a headless browser.
- **Slower** — it must load and parse every page, taking minutes.
- **Most complete results** — captures jobs from companies with no known ATS,
  so you see the full picture.

> **Why it matters:** the two modes can return very different job counts.
> A **Quick scan** is fast but *partial* (only ATS-backed companies), while a
> **Full browser scan** is slower but *far more complete* because it also
> covers career-page-only companies. For a thorough job search, prefer a
> Full browser scan; use Quick when you just want a fast refresh.

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
| Linux | `~/.sponsorscout` |

Contents: `sponsorscout.db` (all jobs, companies and scan history), `seeds/`
(your editable company lists), `locale.json` (language preference) and the
raw scan-log CSVs under `scan_output/`.

You can override the location with the `SPONSORSCOUT_DATA_DIR` (or
`SPONSORSCOUT_DB_PATH`) environment variable.

---

## 🏗 Building From Source

Install the build deps first: `pip install -r requirements.txt
-r requirements-dev.txt`.

**Windows (Inno Setup installer):**

```powershell
.\build_exe.ps1
```

Output: `dist\sponsorscout-<version>-setup.exe` (requires Inno Setup 6/7).
The script also bundles the Playwright Chromium browser into the installer.

**Linux (.deb package):**

```bash
./build_deb.sh
```

Output: `dist/sponsorscout_<version>_amd64.deb`.
The script also bundles the Playwright Chromium browser into the .deb.

---

## 📋 Requirements

- Python 3.10 or newer
- Runtime deps installed via `requirements.txt`: **PySide6**, **requests**,
  **playwright**
- Playwright Chromium (`python -m playwright install chromium`) — used for
  JS-rendered career-page crawling (both installers bundle it already)
- Build/test-only deps in `requirements-dev.txt`: **pyinstaller**, **pytest**

---

## 📄 License

MIT — see [LICENSE](LICENSE).

---

# 🇮🇹 Italiano

## 📥 Scarica

I programmi di installazione pronti all'uso sono pubblicati nella pagina GitHub Releases:

👉 **[Scarica l'ultima versione](https://github.com/Kazake95/SponsorScout/releases/tag/SponsorScout_v_0.1.1)**

| Piattaforma | File |
|-------------|------|
| Windows 10 / 11 | `sponsorscout-<versione>-setup.exe` |
| Linux (Debian / Ubuntu) | `sponsorscout_<versione>_amd64.deb` |

> I collegamenti sopra portano alla pagina Releases — incolla qui gli URL
> diretti dei file quando la versione sarà pubblicata.

---

## ✨ Cosa Fa SponsorScout

- **Scansiona solo fonti ufficiali** — 8 bacheche ATS (Ashby, Greenhouse,
  Lever, SmartRecruiters, Personio, Recruitee, Workable, Workday) tramite le
  loro API pubbliche, più la pagina carriera di ogni azienda con un browser
  headless quando non esiste un'API ATS pubblica.
- **Classifica ogni lavoro** — l'idoneità alla Carta Blu UE, il supporto al
  trasferimento / visto e il tipo di lavoro remoto vengono rilevati dalla
  descrizione del lavoro.
- **Mantiene tutto in locale** — tutti i dati sono salvati in un database
  SQLite sul tuo computer. Nulla viene caricato online.
- **Gestisce le tue candidature** — un semplice percorso: Salvata →
  Inviata → Colloquio → Offerta → Rifiutata.
- **Ti dà il controllo** — deduplica o elimina i dati scansionati, riverifica
  i lavori per l'aggiornamento e scarica i registri dettagliati per azienda.
- **Due lingue** — Italiano e Inglese, selezionabili in qualsiasi momento
  dal menu in alto.

---

## 🚀 Avvio Rapido

1. **Scarica** l'installer per la tua piattaforma dal collegamento qui sopra.
2. **Installa** — non serve Python né altro; l'app e il browser incluso sono
   già nell'installer.
3. **Avvia SponsorScout.** Al primo avvio una finestra chiede se eseguire una
   scansione iniziale — clicca **Sì**. Recupera i lavori da ogni azienda
   nell'elenco, dalla sua bacheca ufficiale e dalla pagina carriera, e
   riempie il database (richiede 1-3 minuti).
4. Sfoglia i risultati nella scheda **Cerca**, filtra per sponsorizzazione /
   Carta Blu / trasferimento / remoto e inizia a gestire le candidature dalla
   scheda **Candidature**.

È tutto — tutto funziona in locale sul tuo computer.

---

## 🗂 Le Cinque Schede

### 1. Pannello (Dashboard)
Una panoramica live del database: aziende totali, lavori verificati, lavori
sponsorizzati, lavori remoti e lavori con Carta Blu UE — più una tabella
"Migliori aziende per sponsorizzazione" e una "Lavori per paese". Il pulsante
**Riscansiona Aziende** avvia una nuova scansione; **Aggiorna** ricarica i
numeri.

### 2. Cerca (Search)
Il browser principale dei lavori. Filtra per posizione, azienda, località,
paese, sponsorizzazione, Carta Blu, trasferimento e tipo di lavoro remoto
(con l'opzione di ricerca tramite regex), poi ordina per corrispondenza
migliore o più recenti. Con il tasto destro su una riga puoi aprirla nel
browser o salvarla nelle candidature.

### 3. Candidature (Applications)
Il tuo registro personale delle candidature. Seleziona un lavoro salvato per
impostarne lo stato (Salvata / Inviata / Colloquio / Offerta / Rifiutata) e
aggiungere note.

### 4. Strumenti (Tools)
Il centro di controllo:
- **Scanner** — avvia una scansione su tutte le aziende nell'elenco usando
  **Veloce** (rapida, solo API) o **Completa / browser** (approfondita,
  esplora anche le pagine carriera). Le due modalità restituiscono conteggi di
  lavori diversi — vedi [Scansione Veloce vs Scansione Completa](#-scansione-veloce-vs-scansione-completa). L'output live appare
  nella finestra di log.
- **Cronologia Scansioni** — ogni scansione passata; selezionane una per
  visualizzare o scaricare un registro dettagliato per azienda, errori
  inclusi.
- **Qualità Dati** — rimuovi lavori/aziende duplicati, cancella lavori scaduti
  o elimina tutti i dati scansionati.
- **Verifica Aggiornamento** — riverifica i lavori salvati sulle loro
  pagine live e segna gli annunci non più disponibili come scaduti.

### 5. Gestione Dati (Data Management)
Modifica gli elenchi di aziende che SponsorScout scansiona. Sono forniti due
editor — **Portali ATS** e **Portali Career**. Puoi aggiungere, modificare o
rimuovere aziende; le modifiche vengono salvate nei tuoi file seed personali
e hanno effetto dalla prossima scansione. Il pulsante "Ripristina
predefiniti" ripristina gli elenchi originali.

---

## 🌐 Cambio Lingua

Usa il menu a tendina nell'angolo in alto a destra dell'intestazione per
passare da **Italiano** a **English**. La tua scelta viene salvata e
ripristinata al prossimo avvio. Puoi anche leggere la documentazione in
inglese nel file [README.md](README.md).

---

## 🔍 Scansione Veloce vs Scansione Completa

Ci sono **due modalità di scansione** e scegliere quella giusta è importante
perché producono **risultati di lavori diversi**:

### ⚡ Scansione Veloce (solo API)
- Recupera i lavori **solo dalle API ufficiali delle bacheche** delle aziende
  che usano un ATS noto (Ashby, Greenhouse, Lever, SmartRecruiters, Personio,
  Recruitee, Workable, Workday).
- **Rapida** — di solito completa in secondi o al massimo un minuto.
- **Risultati parziali** — ogni azienda che *non* espone un'API ATS pubblica
  (cioè con solo una pagina carriera) viene saltata, quindi **i suoi lavori
  non compariranno**.

### 🧭 Scansione Completa (con browser)
- Fa **tutto ciò che fa la scansione Veloce**, poi **esplora anche la pagina
  carriera di ogni azienda** con un browser headless.
- **Più lenta** — deve caricare e analizzare ogni pagina, impiegando minuti.
- **Risultati più completi** — cattura i lavori delle aziende senza un ATS
  noto, così vedi il quadro completo.

> **Perché è importante:** le due modalità possono restituire conteggi di
> lavori molto diversi. Una **scansione Veloce** è rapida ma *parziale* (solo
> aziende con ATS), mentre una **scansione Completa** è più lenta ma *molto
> più esaustiva* perché copre anche le aziende con sola pagina carriera. Per
> una ricerca completa preferisci la scansione Completa; usa la Veloce quando
> vuoi solo un aggiornamento rapido.

---

## ⚙️ Come Funziona la Scansione

1. SponsorScout legge i suoi **file seed** — elenchi curati di aziende con
   i loro URL carriera e tipo di ATS.
2. Le aziende con un ATS noto vengono scansionate tramite l'**API ufficiale
   della bacheca** (veloce).
3. Le aziende senza ATS pubblico vengono esplorate attraverso la loro
   **pagina carriera** con un browser headless.
4. Ogni lavoro viene classificato (Carta Blu / trasferimento / remoto) e
   deduplicato.
5. I risultati vengono salvati nel database SQLite locale e appaiono
   immediatamente nelle schede Pannello e Cerca.

I file seed si trovano nella cartella dati dell'utente e possono essere
modificati nella scheda Gestione Dati.

---

## 💾 Dove Sono i Tuoi Dati

| Piattaforma | Posizione |
|-------------|-----------|
| Windows | `%APPDATA%\SponsorScout` |
| Linux | `~/.sponsorscout` |

Contenuto: `sponsorscout.db` (tutti i lavori, aziende e cronologia delle
scansioni), `seeds/` (i tuoi elenchi di aziende modificabili),
`locale.json` (preferenza lingua) e i CSV di log grezzi in `scan_output/`.

Puoi cambiare la posizione con le variabili d'ambiente `SPONSORSCOUT_DATA_DIR`
(o `SPONSORSCOUT_DB_PATH`).

---

## 🏗 Compilare dai Sorgenti

Installa prima le dipendenze di build: `pip install -r requirements.txt
-r requirements-dev.txt`.

**Windows (installer Inno Setup):**

```powershell
.\build_exe.ps1
```

Output: `dist\sponsorscout-<versione>-setup.exe` (richiede Inno Setup 6/7).
Lo script include anche il browser Playwright Chromium nell'installer.

**Linux (pacchetto .deb):**

```bash
./build_deb.sh
```

Output: `dist/sponsorscout_<versione>_amd64.deb`.
Lo script include anche il browser Playwright Chromium nel pacchetto .deb.

---

## 📋 Requisiti

- Python 3.10 o successivo
- Dipendenze di runtime tramite `requirements.txt`: **PySide6**, **requests**,
  **playwright**
- Playwright Chromium (`python -m playwright install chromium`) — usato per
  lo scanning delle pagine carriera JS (entrambi gli installer lo includono
  già)
- Dipendenze solo per build/test in `requirements-dev.txt`: **pyinstaller**,
  **pytest**

---

## 📄 Licenza

MIT — vedi [LICENSE](LICENSE).
