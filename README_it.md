<img src="sponsorscout/data/sponsorscout.png" alt="SponsorScout" width="420">

# SponsorScout

**Trova lavori verificati dalle pagine carriera ufficiali delle aziende e dalle bacheche ATS — direttamente sul tuo desktop.**

SponsorScout è un'applicazione desktop gratuita e completamente locale. Scansiona le pagine carriera ufficiali delle aziende e 17 bacheche ATS (Greenhouse, Lever, Ashby, Workday e altre), valuta ogni lavoro per l'idoneità alla Carta Blu UE e al supporto al trasferimento, e ti aiuta a gestire le tue candidature — tutto senza account, servizi cloud o telemetria.

---

## 📥 Scarica

I programmi di installazione pronti all'uso sono pubblicati nella pagina GitHub Releases:

👉 **[Scarica l'ultima versione](https://github.com/Kazake95/SponsorScout/releases)**

| Piattaforma | File |
|-------------|------|
| Windows 10 / 11 | `sponsorscout-<versione>-setup.exe` |
| Linux (Debian / Ubuntu) | `sponsorscout_<versione>_amd64.deb` |

> I collegamenti sopra portano alla pagina Releases — incolla qui gli URL
> diretti dei file quando la versione sarà pubblicata.

---

## ✨ Cosa Fa SponsorScout

- **Scansiona solo fonti ufficiali** — 17 piattaforme ATS più la pagina
  carriera di ogni azienda quando non esiste un'API ATS pubblica.
- **Valuta ogni lavoro** — l'idoneità alla Carta Blu UE, il supporto al
  trasferimento e il tipo di lavoro remoto vengono rilevati dalla
  descrizione del lavoro.
- **Mantiene tutto in locale** — tutti i dati sono salvati in un database
  SQLite sul tuo computer. Nulla viene caricato online.
- **Gestisce le tue candidature** — un semplice percorso: Salvata →
  Inviata → Colloquio → Offerta → Rifiutata.
- **Assistenza AI (opzionale)** — valutazione dei lavori, personalizzazione
  del CV e generazione della lettera di presentazione, tramite la tua
  normale chat AI web (ChatGPT, Gemini, Claude…) o una chiave API diretta.
- **Due lingue** — Italiano e Inglese, selezionabili in qualsiasi momento
  dal menu in alto.

---

## 🚀 Avvio Rapido

```bash
# 1. Installa le dipendenze
pip install -r requirements.txt

# 2. Avvia l'app
python -m sponsorscout.main
```

Al primo avvio una finestra di benvenuto chiede se eseguire la scansione
iniziale. Clicca **Sì** — richiede circa 1-3 minuti e riempie il database
con i lavori di ogni azienda nell'elenco.

---

## 🗂 Le Cinque Schede

### 1. Pannello (Dashboard)
Una panoramica live del database: aziende totali, lavori verificati, lavori
sponsorizzati, lavori remoti e lavori con Carta Blu UE — più una tabella
"Migliori aziende per sponsorizzazione" e una "Lavori per paese". Il pulsante
**Riscansiona Aziende** avvia una nuova scansione; **Aggiorna** ricarica i
numeri.

### 2. Cerca (Search)
Il browser principale dei lavori. Filtra per posizione, azienda, paese,
località, sponsorizzazione, Carta Blu, trasferimento e tipo di lavoro remoto,
poi ordina per corrispondenza migliore o più recenti. Selezionando una riga
si apre il pannello di valutazione AI e il menu con il tasto destro (apri
nel browser, salva nelle candidature, copia il prompt di valutazione).

### 3. Candidature (Applications)
Il tuo registro personale delle candidature. Seleziona un lavoro salvato per
impostarne lo stato (Salvata / Inviata / Colloquio / Offerta / Rifiutata) e
aggiungere note.

### 4. Strumenti (Tools)
Il centro di controllo:
- **Scanner** — avvia una scansione su tutte le aziende nell'elenco (Veloce
  = rapida, solo API; Completa = ricerca con browser). L'output live appare
  nella finestra di log.
- **Cronologia Scansioni** — ogni scansione passata; selezionane una per
  visualizzare o scaricare un registro dettagliato per azienda, errori
  inclusi.
- **Qualità Dati** — rimuovi duplicati, cancella lavori scaduti o elimina
  tutti i dati scansionati.
- **Verifica Aggiornamento** — riverifica i lavori salvati sulle loro
  pagine live e segna gli annunci non più disponibili come scaduti.
- **Impostazioni AI** — configurazione del provider, chiave API e modello.

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
| Linux / macOS | `~/.sponsorscout` |

Contenuto: `sponsorscout.db` (tutti i lavori, aziende e cronologia delle
scansioni), `seeds/` (i tuoi elenchi di aziende modificabili),
`locale.json` (preferenza lingua), più i modelli di prompt AI.

---

## 🏗 Compilare dai Sorgenti

**Windows (installer Inno Setup):**

```powershell
.\build_exe.ps1
```

Output: `dist\sponsorscout-<versione>-setup.exe` (richiede Inno Setup 6).

**Linux (pacchetto .deb):**

```bash
./build_deb.sh
```

Output: `dist/sponsorscout_<versione>_amd64.deb`.

---

## 📋 Requisiti

- Python 3.10 o successivo
- PySide6, requests, beautifulsoup4, lxml, Pillow (installati tramite
  `requirements.txt`)
- Playwright Chromium (scaricato automaticamente per lo scanning delle
  pagine carriera)

---

## 🤖 Provider AI (opzionale)

Configura in **Strumenti → Impostazioni AI**:

- Google AI Studio (piano gratuito)
- NVIDIA NIM (crediti gratuiti)
- OpenAI
- Qualsiasi endpoint compatibile OpenAI (vLLM, Ollama, LM Studio)

Oppure salta completamente l'API e usa il flusso integrato di chat AI nel
browser con il tuo normale account ChatGPT / Gemini / Claude.

---

## 📄 Licenza

MIT — vedi [LICENSE](LICENSE).