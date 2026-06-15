"""Internationalization (i18n) for SponsorScout.

Provides English (default) and Italian translations.
Usage:  from sponsorscout.i18n import _, set_locale, get_locale
        text = _("Search")
"""
from __future__ import annotations

import json
from pathlib import Path

from sponsorscout.paths import USER_DATA_DIR

# ── current locale (runtime, persisted separately) ──────────────────────────

_locale: str = "en"

# Config file for persisting language preference
_I18N_CONFIG = USER_DATA_DIR / "locale.json"


def set_locale(locale: str) -> None:
    """Set the active locale at runtime."""
    global _locale
    _locale = locale
    # Persist to disk
    try:
        _I18N_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        _I18N_CONFIG.write_text(json.dumps({"locale": locale}))
    except Exception:
        pass


def get_locale() -> str:
    """Return the current locale code ('en' or 'it')."""
    return _locale


def load_saved_locale() -> str:
    """Load persisted locale from disk. Returns 'en' if not found."""
    global _locale
    try:
        if _I18N_CONFIG.exists():
            data = json.loads(_I18N_CONFIG.read_text())
            _locale = data.get("locale", "en")
    except Exception:
        _locale = "en"
    return _locale


def get_available_locales() -> list[str]:
    """Return list of available locale codes."""
    return ["en", "it"]


def get_locale_name(locale: str) -> str:
    """Return human-readable locale name."""
    names = {"en": "English", "it": "Italiano"}
    return names.get(locale, locale)


# ── Translation dictionary ─────────────────────────────────────────────────
# Each key is the English string. English is the identity (key == value).
# Italian provides precise translations.

LANGUAGES: dict[str, dict[str, str]] = {
    "en": {
        # ── Header ─────────────────────────────────────────────────────
        "Verified sponsorship-focused jobs from official ATS boards":
            "Verified sponsorship-focused jobs from official ATS boards",
        "Ready": "Ready",
        "Scan complete.": "Scan complete.",

        # ── Tab names ──────────────────────────────────────────────────
        "Search": "Search",
        "Dashboard": "Dashboard",
        "Applications": "Applications",
        "ATS Health": "ATS Health",
        "AI Tailor": "AI Tailor",
        "Tools": "Tools",

        # ── Search tab ─────────────────────────────────────────────────
        "Title:": "Title:",
        "Company:": "Company:",
        "Country:": "Country:",
        "Search": "Search",
        "Clear": "Clear",
        "Sponsorship:": "Sponsorship:",
        "Remote:": "Remote:",
        "Experience:": "Experience:",
        "Sort:": "Sort:",
        "Objective:": "Objective:",
        "Balanced": "Balanced",
        "Strict quality": "Strict quality",
        "Visa sponsor": "Visa sponsor",
        "Local EU": "Local EU",
        "Remote EMEA": "Remote EMEA",
        "Blue Card focus": "Blue Card focus",
        "EU Blue Card": "EU Blue Card",
        "Relocation": "Relocation",
        "All": "All",
        "Any (incl. unknown)": "Any (incl. unknown)",
        "Unknown / Not classified": "Unknown / Not classified",
        "Intern": "Intern",
        "Entry": "Entry",
        "Mid": "Mid",
        "Senior": "Senior",
        "Lead": "Lead",
        "Exec": "Exec",
        "Best match": "Best match",
        "Latest": "Latest",
        "Sponsored Only": "Sponsored Only",
        "Remote EU": "Remote EU",
        "Remote EMEA": "Remote EMEA",
        "Remote Global": "Remote Global",
        "Remote Only": "Remote Only",
        "Hybrid": "Hybrid",
        "jobs found": "jobs found",
        "job found": "job found",

        # ── AI Rating panel ────────────────────────────────────────────
        "AI Job Rating & Eligibility": "AI Job Rating & Eligibility",
        "Rate this job": "Rate this job",
        "Tailor CV & Letter": "Tailor CV & Letter",
        "Select a job, then click 'Rate this job'.":
            "Select a job, then click 'Rate this job'.",
        "No job selected.": "No job selected.",
        "Rating against your saved CV profile":
            "Rating against your saved CV profile",
        "No CV on file — paste yours in AI Tailor tab for personalised results":
            "No CV on file — paste yours in AI Tailor tab for personalised results",
        "Rating will use your saved CV profile":
            "Rating will use your saved CV profile",
        "Contacting Gemini API...": "Contacting Gemini API...",
        "Contacting custom AI endpoint...": "Contacting custom AI endpoint...",
        "Contacting {provider} OpenAI-compatible API...":
            "Contacting {provider} OpenAI-compatible API...",

        # ── Search: right-click context menu ───────────────────────────
        "Open in browser": "Open in browser",
        "Save to Applications": "Save to Applications",
        "Rate with AI": "Rate with AI",
        "Tailor CV & Cover Letter": "Tailor CV & Cover Letter",

        # ── Dashboard ──────────────────────────────────────────────────
        "Companies": "Companies",
        "Verified Jobs": "Verified Jobs",
        "Sponsored": "Sponsored",
        "Remote": "Remote",
        "EU Blue Card": "EU Blue Card",
        "New this week": "New this week",
        "Top companies by sponsorship score":
            "Top companies by sponsorship score",
        "Jobs by country": "Jobs by country",

        # ── Applications tab ───────────────────────────────────────────
        "Saved applications": "Saved applications",
        "Refresh": "Refresh",
        "Remove Selected": "Remove Selected",
        "Edit selected": "Edit selected",
        "Status:": "Status:",
        "Notes:": "Notes:",
        "saved": "saved",
        "applied": "applied",
        "interview": "interview",
        "offer": "offer",
        "rejected": "rejected",

        # ── ATS Health tab ─────────────────────────────────────────────
        "ATS Connector Health": "ATS Connector Health",
        "Success/failure rates per connector after each scan.":
            "Success/failure rates per connector after each scan.",

        # ── Tools tab ──────────────────────────────────────────────────
        "Scanner": "Scanner",
        "Scan all 111 companies via their official ATS APIs.":
            "Scan all 111 companies via their official ATS APIs.",
        "Status:": "Status:",
        "idle": "idle",
        "Scan Now": "Scan Now",
        "Auto (1 h)": "Auto (1 h)",
        "Stop": "Stop",
        "Scan Log:": "Scan Log:",
        "Data Quality": "Data Quality",
        "Remove duplicate jobs and companies from the database.":
            "Remove duplicate jobs and companies from the database.",
        "Run Dedup": "Run Dedup",
        "AI Settings": "AI Settings",
        "AI provider API key + prompts for job rating, eligibility (uses your CV from AI Tailor tab), and document generation.":
            "AI provider API key + prompts for job rating, eligibility (uses your CV from AI Tailor tab), and document generation.",
        "AI API Key / Token:": "AI API Key / Token:",
        "Save Key": "Save Key",
        "Provider:": "Provider:",
        "Model:": "Model:",
        "(type any model name; chips are provider-specific)":
            "(type any model name; chips are provider-specific)",
        "Base URL:": "Base URL:",
        "(auto-filled for built-in providers; required for custom)":
            "(auto-filled for built-in providers; required for custom)",
        "type the exact model ID from your provider":
            "type the exact model ID from your provider",
        "Job Rating & Eligibility Prompt  (AI uses this + your CV to score each job):":
            "Job Rating & Eligibility Prompt  (AI uses this + your CV to score each job):",
        "Save Prompt": "Save Prompt",
        "Reset to Default": "Reset to Default",
        "CV Tailoring Prompt  (how AI rewrites your CV to match a JD):":
            "CV Tailoring Prompt  (how AI rewrites your CV to match a JD):",
        "Save CV Prompt": "Save CV Prompt",
        "Reset": "Reset",
        "Cover / Motivation Letter Prompt  (for EU-based roles — personalised from your CV + JD):":
            "Cover / Motivation Letter Prompt  (for EU-based roles — personalised from your CV + JD):",
        "Save Letter Prompt": "Save Letter Prompt",
        "Company Discovery": "Company Discovery",
        "Probes 210 curated ATS boards.  Use role keywords: 'analyst', 'engineer', 'backend', 'data'.":
            "Probes 210 curated ATS boards.  Use role keywords: 'analyst', 'engineer', 'backend', 'data'.",
        "Query:": "Query:",
        "Discover": "Discover",
        "Freshness Check": "Freshness Check",
        "Verify jobs still exist online — auto-expires dead links.":
            "Verify jobs still exist online — auto-expires dead links.",
        "Max jobs:": "Max jobs:",
        "Run": "Run",

        # ── AI Tailor tab ──────────────────────────────────────────────
        "AI CV & Cover Letter Tailor": "AI CV & Cover Letter Tailor",
        "Select a job in Search → 'Tailor CV & Letter', or load a JD manually below":
            "Select a job in Search → 'Tailor CV & Letter', or load a JD manually below",
        "How to use": "How to use",
        "No job selected — use Search tab or paste a JD below":
            "No job selected — use Search tab or paste a JD below",
        "Job Description": "Job Description",
        "Job URL:": "Job URL:",
        "Fetch JD": "Fetch JD",
        "— or paste full JD below —": "— or paste full JD below —",
        "Use this JD": "Use this JD",
        "My CV (stored locally)": "My CV (stored locally)",
        "Paste your current CV once — it's saved for all future tailoring sessions.":
            "Paste your current CV once — it's saved for all future tailoring sessions.",
        "Save CV": "Save CV",
        "CV saved": "CV saved",
        "Base Cover Letter (template for AI)":
            "Base Cover Letter (template for AI)",
        "Paste an example cover letter you like. The AI will match its style/tone when generating new letters.":
            "Paste an example cover letter you like. The AI will match its style/tone when generating new letters.",
        "Save Template": "Save Template",
        "Template saved": "Template saved",
        "Generate": "Generate",
        "Tailor My CV": "Tailor My CV",
        "Write Cover Letter": "Write Cover Letter",
        "Both": "Both",
        "Result": "Result",
        "CV": "CV",
        "Cover Letter": "Cover Letter",
        "Copy": "Copy",
        "Fetching…": "Fetching…",

        # ── Messages: tailor tab ───────────────────────────────────────
        "Empty JD": "Empty JD",
        "Paste a job description first.": "Paste a job description first.",
        "No URL": "No URL",
        "Enter a job post URL first.": "Enter a job post URL first.",
        "Empty CV": "Empty CV",
        "Paste your CV first.": "Paste your CV first.",
        "No Job Description": "No Job Description",
        "Fetch or paste a job description first, then click 'Use this JD'.":
            "Fetch or paste a job description first, then click 'Use this JD'.",
        "No CV": "No CV",
        "Paste your CV in the 'My CV' box and save it first.":
            "Paste your CV in the 'My CV' box and save it first.",
        "Copied to clipboard!": "Copied to clipboard!",
        "Select a row": "Select a row",
        "Click a row first, then click Remove.":
            "Click a row first, then click Remove.",
        "Remove": "Remove",
        "Search error": "Search error",
        "Error": "Error",
        "Missing": "Missing",
        "Enter a search query.": "Enter a search query.",

        # ── Messages: AI settings ──────────────────────────────────────
        "Saved": "Saved",
        "AI API key saved.": "AI API key saved.",
        "Empty": "Empty",
        "Prompt cannot be empty.": "Prompt cannot be empty.",
        "Custom prompt saved.": "Custom prompt saved.",
        "CV tailoring prompt saved.": "CV tailoring prompt saved.",
        "Cover letter prompt saved.": "Cover letter prompt saved.",
        "Reset prompt to default?": "Reset prompt to default?",
        "Reset CV tailoring prompt to default?":
            "Reset CV tailoring prompt to default?",
        "Reset cover letter prompt to default?":
            "Reset cover letter prompt to default?",
        "Unknown provider": "Unknown provider",
        "Missing model": "Missing model",
        "Type a model name first.": "Type a model name first.",
        "Missing base URL": "Missing base URL",

        # ── Messages: first run ────────────────────────────────────────
        "Welcome to SponsorScout": "Welcome to SponsorScout",

        # ── Messages: general ──────────────────────────────────────────
        "No job selected": "No job selected",
        "Select a job in the Search tab first.":
            "Select a job in the Search tab first.",
        "Dashboard data could not be loaded.":
            "Dashboard data could not be loaded.",
        "Dedup complete": "Dedup complete",
        "Probing ATS boards for": "Probing ATS boards for",
        "Found": "Found",
        "candidate(s).": "candidate(s).",
        "No new companies found.":
            "No new companies found.",
        "Try: 'analyst', 'backend', 'data engineer'":
            "Try: 'analyst', 'backend', 'data engineer'",
        "Discovery done.": "Discovery done.",
        "Discovery failed.": "Discovery failed.",
        "Running discovery…": "Running discovery…",
        "running…": "running…",
        "Scanning…": "Scanning…",
        "auto — every 1 h": "auto — every 1 h",
        "stopped": "stopped",
        "Failed.": "Failed.",
        "Verified": "Verified",

        # ── Tooltip: How to Use ────────────────────────────────────────
        "AI Tailor — How to Use": "AI Tailor — How to Use",

        # ── Tooltip: JD section ────────────────────────────────────────
        "Job Description": "Job Description",

        # ── Tooltip: CV section ────────────────────────────────────────
        "My CV": "My CV",

        # ── Tooltip: Cover Letter section ──────────────────────────────
        "Base Cover Letter Template": "Base Cover Letter Template",

        # ── Tooltip: Generate section ──────────────────────────────────
        "Generate Buttons": "Generate Buttons",

        # ── Tooltip: Result section ────────────────────────────────────
        "Result Area": "Result Area",

        # ── Language toggle ────────────────────────────────────────────
        "Language": "Language",
    },

    # ═══════════════════════════════════════════════════════════════════
    # ITALIAN TRANSLATIONS
    # ═══════════════════════════════════════════════════════════════════
    "it": {
        # ── Header ─────────────────────────────────────────────────────
        "Verified sponsorship-focused jobs from official ATS boards":
            "Lavori con sponsorizzazione verificati da bacheche ATS ufficiali",
        "Ready": "Pronto",
        "Scan complete.": "Scansione completata.",

        # ── Tab names ──────────────────────────────────────────────────
        "Search": "Cerca",
        "Dashboard": "Pannello",
        "Applications": "Candidature",
        "ATS Health": "Stato ATS",
        "AI Tailor": "AI Personalizza",
        "AI Assistant": "Assistente AI",
        "Tools": "Strumenti",

        # ── Search tab ─────────────────────────────────────────────────
        "Title:": "Posizione:",
        "Company:": "Azienda:",
        "Country:": "Paese:",
        "Clear": "Pulisci",
        "Sponsorship:": "Sponsorizzazione:",
        "Remote:": "Remoto:",
        "Experience:": "Esperienza:",
        "Sort:": "Ordina:",
        "Objective:": "Obiettivo:",
        "Balanced": "Bilanciato",
        "Strict quality": "Qualità rigorosa",
        "Visa sponsor": "Sponsor visto",
        "Local EU": "UE locale",
        "Remote EMEA": "Remoto EMEA",
        "Blue Card focus": "Focus Blue Card",
        "EU Blue Card": "Carta Blu UE",
        "Relocation": "Ricollocazione",
        "All": "Tutti",
        "Any (incl. unknown)": "Qualsiasi (incl. sconosciuto)",
        "Unknown / Not classified": "Sconosciuto / Non classificato",
        "Intern": "Stage",
        "Entry": "Junior",
        "Mid": "Intermedio",
        "Senior": "Senior",
        "Lead": "Capo",
        "Exec": "Dirigente",
        "Best match": "Miglior corrispondenza",
        "Latest": "Più recenti",
        "Sponsored Only": "Solo Sponsorizzati",
        "Remote EU": "Remoto UE",
        "Remote EMEA": "Remoto EMEA",
        "Remote Global": "Remoto Globale",
        "Remote Only": "Solo Remoto",
        "Hybrid": "Ibrido",
        "jobs found": "lavori trovati",
        "job found": "lavoro trovato",

        # ── AI Rating panel ────────────────────────────────────────────
        "AI Job Rating & Eligibility": "Valutazione AI ed Eleggibilità Lavoro",
        "Copy Rating Prompt": "Copia Prompt di Valutazione",
        "Paste AI Result": "Incolla Risultato AI",
        "Tailor CV & Letter": "Personalizza CV e Lettera",
        "Select a job, click 'Copy Rating Prompt', paste it into the AI Assistant tab, then click 'Paste AI Result'.":
            "Seleziona un lavoro, clicca 'Copia Prompt di Valutazione', incollalo nella scheda Assistente AI, poi clicca 'Incolla Risultato AI'.",
        "Select a job, then click 'Copy Rating Prompt'.":
            "Seleziona un lavoro, poi clicca 'Copia Prompt di Valutazione'.",
        "No job selected.": "Nessun lavoro selezionato.",
        "Rating against your saved CV profile":
            "Valutazione basata sul tuo CV salvato",
        "No CV on file — paste yours in AI Assistant tab for personalised results":
            "Nessun CV salvato — incolla il tuo nella scheda Assistente AI per risultati personalizzati",
        "Rating will use your saved CV profile":
            "La valutazione userà il tuo CV salvato",
        "✓ Prompt copied! Paste it into the AI Assistant tab, copy the reply, then click 'Paste AI Result' here.":
            "✓ Prompt copiato! Incollalo nella scheda Assistente AI, copia la risposta, poi clicca 'Incolla Risultato AI' qui.",

        # ── Search: right-click context menu ───────────────────────────
        "Open in browser": "Apri nel browser",
        "Save to Applications": "Salva nelle Candidature",
        "Copy Rating Prompt": "Copia Prompt di Valutazione",
        "Tailor CV & Cover Letter": "Personalizza CV e Lettera",

        # ── Dashboard ──────────────────────────────────────────────────
        "Companies": "Aziende",
        "Verified Jobs": "Lavori Verificati",
        "Sponsored": "Sponsorizzati",
        "Remote": "Remoti",
        "New this week": "Nuovi questa settimana",
        "Top companies by sponsorship score":
            "Migliori aziende per punteggio di sponsorizzazione",
        "Jobs by country": "Lavori per paese",

        # ── Applications tab ───────────────────────────────────────────
        "Saved applications": "Candidature salvate",
        "Refresh": "Aggiorna",
        "Remove Selected": "Rimuovi Selezionato",
        "Edit selected": "Modifica selezionato",
        "Status:": "Stato:",
        "Notes:": "Note:",
        "saved": "salvato",
        "applied": "candidatura inviata",
        "interview": "colloquio",
        "offer": "offerta",
        "rejected": "rifiutato",

        # ── ATS Health tab ─────────────────────────────────────────────
        "ATS Connector Health": "Stato Connettore ATS",
        "Success/failure rates per connector after each scan.":
            "Tasso di successo/errore per connettore dopo ogni scansione.",

        # ── Tools tab ──────────────────────────────────────────────────
        "Scanner": "Scansione",
        "Scan all 111 companies via their official ATS APIs.":
            "Scansiona tutte le 111 aziende tramite le loro API ATS ufficiali.",
        "idle": "inattivo",
        "Scan Now": "Scansiona Ora",
        "Auto (1 h)": "Automatico (1 h)",
        "Stop": "Ferma",
        "Scan Log:": "Registro Scansione:",
        "Data Quality": "Qualità Dati",
        "Remove duplicate jobs and companies from the database.":
            "Rimuovi lavori e aziende duplicati dal database.",
        "Run Dedup": "Esegui Deduplicazione",
        "AI Settings": "Impostazioni AI",
        "AI provider API key + prompts for job rating, eligibility (uses your CV from AI Tailor tab), and document generation.":
            "Chiave API del provider AI + prompt per valutazione lavori, eleggibilità (usa il CV dalla scheda AI Personalizza) e generazione documenti.",
        "AI API Key / Token:": "Chiave API / Token AI:",
        "Save Key": "Salva Chiave",
        "Provider:": "Provider:",
        "Model:": "Modello:",
        "(type any model name; chips are provider-specific)":
            "(inserisci qualsiasi nome modello; i suggerimenti sono specifici del provider)",
        "Base URL:": "URL Base:",
        "(auto-filled for built-in providers; required for custom)":
            "(compilato automaticamente per provider integrati; obbligatorio per personalizzato)",
        "type the exact model ID from your provider":
            "inserisci l'ID esatto del modello dal tuo provider",
        "Job Rating & Eligibility Prompt  (AI uses this + your CV to score each job):":
            "Prompt Valutazione ed Eleggibilità Lavoro  (l'AI usa questo + il tuo CV per valutare ogni lavoro):",
        "Save Prompt": "Salva Prompt",
        "Reset to Default": "Ripristina Predefinito",
        "CV Tailoring Prompt  (how AI rewrites your CV to match a JD):":
            "Prompt Personalizzazione CV  (come l'AI riscrive il tuo CV per corrispondere a un annuncio):",
        "Save CV Prompt": "Salva Prompt CV",
        "Reset": "Ripristina",
        "Cover / Motivation Letter Prompt  (for EU-based roles — personalised from your CV + JD):":
            "Prompt Lettera di Presentazione  (per ruoli nell'UE — personalizzata dal tuo CV + annuncio):",
        "Save Letter Prompt": "Salva Prompt Lettera",
        "Company Discovery": "Scoperta Aziende",
        "Probes 210 curated ATS boards.  Use role keywords: 'analyst', 'engineer', 'backend', 'data'.":
            "Indaga 210 bacheche ATS curate. Usa parole chiave: 'analista', 'ingegnere', 'backend', 'dati'.",
        "Query:": "Ricerca:",
        "Discover": "Scopri",
        "Freshness Check": "Verifica Aggiornamento",
        "Verify jobs still exist online — auto-expires dead links.":
            "Verifica che i lavori esistano ancora online — scadenza automatica dei link morti.",
        "Max jobs:": "Max lavori:",
        "Run": "Esegui",

        # ── AI Tailor tab ──────────────────────────────────────────────
        "AI CV & Cover Letter Tailor": "AI Personalizzazione CV e Lettera di Presentazione",
        "Select a job in Search → 'Tailor CV & Letter', or load a JD manually below":
            "Seleziona un lavoro in Cerca → 'Personalizza CV e Lettera', o carica un annuncio manualmente",
        "How to use": "Come usare",
        "No job selected — use Search tab or paste a JD below":
            "Nessun lavoro selezionato — usa la scheda Cerca o incolla un annuncio",
        "Job URL:": "URL Lavoro:",
        "Fetch JD": "Scarica Annuncio",
        "— or paste full JD below —": "— oppure incolla l'annuncio completo qui sotto —",
        "Use this JD": "Usa questo Annuncio",
        "My CV (stored locally)": "Il mio CV (salvato localmente)",
        "Paste your current CV once — it's saved for all future tailoring sessions.":
            "Incolla il tuo CV una volta — viene salvato per tutte le future sessioni di personalizzazione.",
        "Save CV": "Salva CV",
        "CV saved": "CV salvato",
        "Base Cover Letter (template for AI)":
            "Lettera di Presentazione Base (modello per l'AI)",
        "Paste an example cover letter you like. The AI will match its style/tone when generating new letters.":
            "Incolla una lettera di presentazione che ti piace. L'AI ne riprodurrà lo stile/tono quando genererà nuove lettere.",
        "Save Template": "Salva Modello",
        "Template saved": "Modello salvato",
        "Generate": "Genera",
        "Tailor My CV": "Personalizza il mio CV",
        "Write Cover Letter": "Scrivi Lettera di Presentazione",
        "Both": "Entrambi",
        "Result": "Risultato",
        "CV": "CV",
        "Cover Letter": "Lettera di Presentazione",
        "Copy": "Copia",
        "Fetching…": "Scaricamento…",

        # ── Messages: tailor tab ───────────────────────────────────────
        "Empty JD": "Annuncio vuoto",
        "Paste a job description first.":
            "Incolla prima una descrizione del lavoro.",
        "No URL": "Nessun URL",
        "Enter a job post URL first.":
            "Inserisci prima un URL dell'annuncio di lavoro.",
        "Empty CV": "CV vuoto",
        "Paste your CV first.":
            "Incolla prima il tuo CV.",
        "No Job Description": "Nessun Annuncio",
        "Fetch or paste a job description first, then click 'Use this JD'.":
            "Scarica o incolla prima un annuncio, poi clicca 'Usa questo Annuncio'.",
        "No CV": "Nessun CV",
        "Paste your CV in the 'My CV' box and save it first.":
            "Incolla il tuo CV nella sezione 'Il mio CV' e salvalo prima.",
        "Copied to clipboard!": "Copiato negli appunti!",
        "Select a row": "Seleziona una riga",
        "Click a row first, then click Remove.":
            "Clicca prima su una riga, poi su Rimuovi.",
        "Remove": "Rimuovi",
        "Search error": "Errore di ricerca",
        "Error": "Errore",
        "Missing": "Manca",
        "Enter a search query.":
            "Inserisci una ricerca.",

        # ── Messages: AI settings ──────────────────────────────────────
        "AI API key saved.": "Chiave API AI salvata.",
        "Empty": "Vuoto",
        "Prompt cannot be empty.": "Il prompt non può essere vuoto.",
        "Custom prompt saved.": "Prompt personalizzato salvato.",
        "CV tailoring prompt saved.": "Prompt personalizzazione CV salvato.",
        "Cover letter prompt saved.": "Prompt lettera di presentazione salvato.",
        "Reset prompt to default?":
            "Ripristinare il prompt predefinito?",
        "Reset CV tailoring prompt to default?":
            "Ripristinare il prompt di personalizzazione CV predefinito?",
        "Reset cover letter prompt to default?":
            "Ripristinare il prompt della lettera di presentazione predefinito?",
        "Unknown provider": "Provider sconosciuto",
        "Missing model": "Modello mancante",
        "Type a model name first.":
            "Inserisci prima il nome di un modello.",
        "Missing base URL": "URL base mancante",

        # ── Messages: first run ────────────────────────────────────────
        "Welcome to SponsorScout": "Benvenuto in SponsorScout",

        # ── Messages: general ──────────────────────────────────────────
        "No job selected": "Nessun lavoro selezionato",
        "Select a job in the Search tab first.":
            "Seleziona prima un lavoro nella scheda Cerca.",
        "Dashboard data could not be loaded.":
            "Impossibile caricare i dati del pannello.",
        "Dedup complete": "Deduplicazione completata",
        "Probing ATS boards for": "Indagine bacheche ATS per",
        "Found": "Trovati",
        "candidate(s).": "candidato/i.",
        "No new companies found.":
            "Nessuna nuova azienda trovata.",
        "Try: 'analyst', 'backend', 'data engineer'":
            "Prova: 'analista', 'backend', 'ingegnere dati'",
        "Discovery done.": "Scoperta completata.",
        "Discovery failed.": "Scoperta fallita.",
        "Running discovery…": "Scoperta in corso…",
        "running…": "in esecuzione…",
        "Scanning…": "Scansione in corso…",
        "auto — every 1 h": "automatico — ogni 1 h",
        "stopped": "fermato",
        "Failed.": "Fallito.",
        "Verified": "Verificato",

        # ── Tooltip: How to Use ────────────────────────────────────────
        "AI Tailor — How to Use": "AI Personalizza — Come Usare",

        # ── Tooltip: JD section ────────────────────────────────────────

        # ── Tooltip: CV section ────────────────────────────────────────
        "My CV": "Il mio CV",

        # ── Tooltip: Cover Letter section ──────────────────────────────
        "Base Cover Letter Template": "Modello Lettera di Presentazione Base",

        # ── Tooltip: Generate section ──────────────────────────────────
        "Generate Buttons": "Pulsanti di Generazione",

        # ── Tooltip: Result section ────────────────────────────────────
        "Result Area": "Area Risultati",

        # ── AI Assistant tab ────────────────────────────────────────────
        "Chat with a free web AI — no API key needed":
            "Chatta con un'AI gratuita sul web — nessuna chiave API necessaria",
        "How to use": "Come usare",
        "Open AI Chat": "Apri Chat AI",
        "Opens the AI chat in your normal web browser — uses "
        "whatever account you're already signed into there. "
        "Paste a prompt from the AI Tailor tab or Search tab, "
        "send it, then copy the reply back.":
            "Apre la chat AI nel tuo normale browser web — usa "
            "l'account in cui sei già connesso. Incolla un prompt "
            "dalla scheda AI Personalizza o Cerca, invialo, poi "
            "copia la risposta.",
        "Site:": "Sito:",
        "Eligibility Rating": "Valutazione di Eleggibilità",
        "From the Search tab: select a job, click '📋 Copy Rating Prompt', "
        "paste it into the AI chat above, then come back, copy the "
        "reply and click '📥 Paste AI Result' in the Search tab.":
            "Dalla scheda Cerca: seleziona un lavoro, clicca '📋 Copia Prompt di "
            "Valutazione', incollalo nella chat AI sopra, poi torna, copia la "
            "risposta e clicca '📥 Incolla Risultato AI' nella scheda Cerca.",
        "Go to Search tab": "Vai alla scheda Cerca",
        "CV Tailoring & Cover Letter": "Personalizzazione CV e Lettera",
        "From the ✨ AI Tailor tab: confirm a job description, then click "
        "'📋 Copy CV Prompt' or '📋 Copy Cover Letter Prompt'. Paste it into "
        "the AI chat above, then copy the reply back into the Result box "
        "with '📥 Paste'.":
            "Dalla scheda ✨ AI Personalizza: confema una descrizione del lavoro, "
            "poi clicca '📋 Copia Prompt CV' o '📋 Copia Prompt Lettera'. "
            "Incollalo nella chat AI sopra, poi copia la risposta nella "
            "casella Risultato con '📥 Incolla'.",
        "Go to AI Tailor tab": "Vai alla scheda AI Personalizza",
        "✓ Opened {site} in your browser — sign in there if needed.":
            "✓ {site} aperto nel tuo browser — accedi lì se necessario.",
        "⏳ Opening {site}…": "⏳ Apertura di {site}…",
        "Could not open AI chat": "Impossibile aprire la chat AI",
        "Failed to open {site} in your browser:\n\n{error}\n\n"
        "Make sure a default web browser is set up on this "
        "computer.":
            "Impossibile aprire {site} nel browser:\n\n{error}\n\n"
            "Assicurati che un browser predefinito sia configurato "
            "su questo computer.",
        "AI Assistant — How to Use": "Assistente AI — Come si usa",
        "This tab opens a normal web AI chat (ChatGPT, Gemini, Claude, "
        "Mistral, Perplexity) in your default web browser, using "
        "whichever account you're already signed into there.\n\n"
        "WORKFLOW:\n\n"
        "1. Pick a site and click '🌐 Open AI Chat'. Sign in if needed "
        "(your browser will remember it).\n\n"
        "2. In the Search tab or AI Tailor tab, click one of the "
        "'📋 Copy ... Prompt' buttons. This copies a ready-made prompt "
        "(including your CV/JD context) to your clipboard.\n\n"
        "3. Switch to the AI chat tab in your browser, paste the prompt "
        "(Ctrl+V), and send it.\n\n"
        "4. Select the AI's full reply, copy it (Ctrl+C).\n\n"
        "5. Back in SponsorScout, click '📥 Paste AI Result' (Search tab) or "
        "'📥 Paste' (AI Tailor tab) to bring the reply in.\n\n"
        "No API key required — everything runs through the AI's normal "
        "web chat, just like using it in a browser tab.":
            "Questa scheda apre una normale chat AI sul web (ChatGPT, Gemini, "
            "Claude, Mistral, Perplexity) nel tuo browser predefinito, "
            "usando l'account in cui sei già connesso.\n\n"
            "PROCEDURA:\n\n"
            "1. Scegli un sito e clicca '🌐 Apri Chat AI'. Accedi se necessario "
            "(il browser lo ricorderà).\n\n"
            "2. Nella scheda Cerca o AI Personalizza, clicca uno dei pulsanti "
            "'📋 Copia Prompt ...'. Questo copia un prompt pronto (con il "
            "contesto del tuo CV/annuncio) negli appunti.\n\n"
            "3. Vai alla scheda della chat AI nel browser, incolla il prompt "
            "(Ctrl+V) e invialo.\n\n"
            "4. Seleziona l'intera risposta dell'AI e copiala (Ctrl+C).\n\n"
            "5. Torna in SponsorScout e clicca '📥 Incolla Risultato AI' (scheda "
            "Cerca) o '📥 Incolla' (scheda AI Personalizza) per inserire la risposta.\n\n"
            "Nessuna chiave API richiesta — tutto avviene tramite la normale "
            "chat web dell'AI, come in una scheda del browser.",

        # ── Language toggle ────────────────────────────────────────────
        "Language": "Language",
    },

    # ═══════════════════════════════════════════════════════════════════
    # ITALIAN TRANSLATIONS
    # ═══════════════════════════════════════════════════════════════════
    "it": {
        # ── Header ─────────────────────────────────────────────────────
        "Verified sponsorship-focused jobs from official ATS boards":
            "Lavori con sponsorizzazione verificati da bacheche ATS ufficiali",
        "Ready": "Pronto",
        "Scan complete.": "Scansione completata.",

        # ── Tab names ──────────────────────────────────────────────────
        "Search": "Cerca",
        "Dashboard": "Pannello",
        "Applications": "Candidature",
        "ATS Health": "Stato ATS",
        "AI Tailor": "AI Personalizza",
        "AI Assistant": "Assistente AI",
        "Tools": "Strumenti",

        # ── Search tab ─────────────────────────────────────────────────
        "Title:": "Posizione:",
        "Company:": "Azienda:",
        "Country:": "Paese:",
        "Clear": "Pulisci",
        "Sponsorship:": "Sponsorizzazione:",
        "Remote:": "Remoto:",
        "Experience:": "Esperienza:",
        "Sort:": "Ordina:",
        "Objective:": "Obiettivo:",
        "Balanced": "Bilanciato",
        "Strict quality": "Qualità rigorosa",
        "Visa sponsor": "Sponsor visto",
        "Local EU": "UE locale",
        "Remote EMEA": "Remoto EMEA",
        "Blue Card focus": "Focus Blue Card",
        "EU Blue Card": "Carta Blu UE",
        "Relocation": "Ricollocazione",
        "All": "Tutti",
        "Any (incl. unknown)": "Qualsiasi (incl. sconosciuto)",
        "Unknown / Not classified": "Sconosciuto / Non classificato",
        "Intern": "Stage",
        "Entry": "Junior",
        "Mid": "Intermedio",
        "Senior": "Senior",
        "Lead": "Capo",
        "Exec": "Dirigente",
        "Best match": "Miglior corrispondenza",
        "Latest": "Più recenti",
        "Sponsored Only": "Solo Sponsorizzati",
        "Remote EU": "Remoto UE",
        "Remote EMEA": "Remoto EMEA",
        "Remote Global": "Remoto Globale",
        "Remote Only": "Solo Remoto",
        "Hybrid": "Ibrido",
        "jobs found": "lavori trovati",
        "job found": "lavoro trovato",

        # ── AI Rating panel ────────────────────────────────────────────
        "AI Job Rating & Eligibility": "Valutazione AI ed Eleggibilità Lavoro",
        "Copy Rating Prompt": "Copia Prompt di Valutazione",
        "Paste AI Result": "Incolla Risultato AI",
        "Tailor CV & Letter": "Personalizza CV e Lettera",
        "Select a job, click 'Copy Rating Prompt', paste it into the AI Assistant tab, then click 'Paste AI Result'.":
            "Seleziona un lavoro, clicca 'Copia Prompt di Valutazione', incollalo nella scheda Assistente AI, poi clicca 'Incolla Risultato AI'.",
        "Select a job, then click 'Copy Rating Prompt'.":
            "Seleziona un lavoro, poi clicca 'Copia Prompt di Valutazione'.",
        "No job selected.": "Nessun lavoro selezionato.",
        "Rating against your saved CV profile":
            "Valutazione basata sul tuo CV salvato",
        "No CV on file — paste yours in AI Assistant tab for personalised results":
            "Nessun CV salvato — incolla il tuo nella scheda Assistente AI per risultati personalizzati",
        "Rating will use your saved CV profile":
            "La valutazione userà il tuo CV salvato",
        "✓ Prompt copied! Paste it into the AI Assistant tab, copy the reply, then click 'Paste AI Result' here.":
            "✓ Prompt copiato! Incollalo nella scheda Assistente AI, copia la risposta, poi clicca 'Incolla Risultato AI' qui.",

        # ── Search: right-click context menu ───────────────────────────
        "Open in browser": "Apri nel browser",
        "Save to Applications": "Salva nelle Candidature",
        "Copy Rating Prompt": "Copia Prompt di Valutazione",
        "Tailor CV & Cover Letter": "Personalizza CV e Lettera",

        # ── Dashboard ──────────────────────────────────────────────────
        "Companies": "Aziende",
        "Verified Jobs": "Lavori Verificati",
        "Sponsored": "Sponsorizzati",
        "Remote": "Remoti",
        "New this week": "Nuovi questa settimana",
        "Top companies by sponsorship score":
            "Migliori aziende per punteggio di sponsorizzazione",
        "Jobs by country": "Lavori per paese",

        # ── Applications tab ───────────────────────────────────────────
        "Saved applications": "Candidature salvate",
        "Refresh": "Aggiorna",
        "Remove Selected": "Rimuovi Selezionato",
        "Edit selected": "Modifica selezionato",
        "Status:": "Stato:",
        "Notes:": "Note:",
        "saved": "salvato",
        "applied": "candidatura inviata",
        "interview": "colloquio",
        "offer": "offerta",
        "rejected": "rifiutato",

        # ── ATS Health tab ─────────────────────────────────────────────
        "ATS Connector Health": "Stato Connettore ATS",
        "Success/failure rates per connector after each scan.":
            "Tasso di successo/errore per connettore dopo ogni scansione.",

        # ── Tools tab ──────────────────────────────────────────────────
        "Scanner": "Scansione",
        "Scan all 111 companies via their official ATS APIs.":
            "Scansiona tutte le 111 aziende tramite le loro API ATS ufficiali.",
        "idle": "inattivo",
        "Scan Now": "Scansiona Ora",
        "Auto (1 h)": "Automatico (1 h)",
        "Stop": "Ferma",
        "Scan Log:": "Registro Scansione:",
        "Data Quality": "Qualità Dati",
        "Remove duplicate jobs and companies from the database.":
            "Rimuovi lavori e aziende duplicati dal database.",
        "Run Dedup": "Esegui Deduplicazione",
        "AI Settings": "Impostazioni AI",
        "AI provider API key + prompts for job rating, eligibility (uses your CV from AI Tailor tab), and document generation.":
            "Chiave API del provider AI + prompt per valutazione lavori, eleggibilità (usa il CV dalla scheda AI Personalizza) e generazione documenti.",
        "AI API Key / Token:": "Chiave API / Token AI:",
        "Save Key": "Salva Chiave",
        "Provider:": "Provider:",
        "Model:": "Modello:",
        "(type any model name; chips are provider-specific)":
            "(inserisci qualsiasi nome modello; i suggerimenti sono specifici del provider)",
        "Base URL:": "URL Base:",
        "(auto-filled for built-in providers; required for custom)":
            "(compilato automaticamente per provider integrati; obbligatorio per personalizzato)",
        "type the exact model ID from your provider":
            "inserisci l'ID esatto del modello dal tuo provider",
        "Job Rating & Eligibility Prompt  (AI uses this + your CV to score each job):":
            "Prompt Valutazione ed Eleggibilità Lavoro  (l'AI usa questo + il tuo CV per valutare ogni lavoro):",
        "Save Prompt": "Salva Prompt",
        "Reset to Default": "Ripristina Predefinito",
        "CV Tailoring Prompt  (how AI rewrites your CV to match a JD):":
            "Prompt Personalizzazione CV  (come l'AI riscrive il tuo CV per corrispondere a un annuncio):",
        "Save CV Prompt": "Salva Prompt CV",
        "Reset": "Ripristina",
        "Cover / Motivation Letter Prompt  (for EU-based roles — personalised from your CV + JD):":
            "Prompt Lettera di Presentazione  (per ruoli nell'UE — personalizzata dal tuo CV + annuncio):",
        "Save Letter Prompt": "Salva Prompt Lettera",
        "Company Discovery": "Scoperta Aziende",
        "Probes 210 curated ATS boards.  Use role keywords: 'analyst', 'engineer', 'backend', 'data'.":
            "Indaga 210 bacheche ATS curate. Usa parole chiave: 'analista', 'ingegnere', 'backend', 'dati'.",
        "Query:": "Ricerca:",
        "Discover": "Scopri",
        "Freshness Check": "Verifica Aggiornamento",
        "Verify jobs still exist online — auto-expires dead links.":
            "Verifica che i lavori esistano ancora online — scadenza automatica dei link morti.",
        "Max jobs:": "Max lavori:",
        "Run": "Esegui",

        # ── AI Tailor tab ──────────────────────────────────────────────
        "AI CV & Cover Letter Tailor": "AI Personalizzazione CV e Lettera di Presentazione",
        "Select a job in Search → 'Tailor CV & Letter', or load a JD manually below":
            "Seleziona un lavoro in Cerca → 'Personalizza CV e Lettera', o carica un annuncio manualmente",
        "How to use": "Come usare",
        "No job selected — use Search tab or paste a JD below":
            "Nessun lavoro selezionato — usa la scheda Cerca o incolla un annuncio",
        "Job URL:": "URL Lavoro:",
        "Fetch JD": "Scarica Annuncio",
        "— or paste full JD below —": "— oppure incolla l'annuncio completo qui sotto —",
        "Use this JD": "Usa questo Annuncio",
        "My CV (stored locally)": "Il mio CV (salvato localmente)",
        "Paste your current CV once — it's saved for all future tailoring sessions.":
            "Incolla il tuo CV una volta — viene salvato per tutte le future sessioni di personalizzazione.",
        "Save CV": "Salva CV",
        "CV saved": "CV salvato",
        "Base Cover Letter (template for AI)":
            "Lettera di Presentazione Base (modello per l'AI)",
        "Paste an example cover letter you like. The AI will match its style/tone when generating new letters.":
            "Incolla una lettera di presentazione che ti piace. L'AI ne riprodurrà lo stile/tono quando genererà nuove lettere.",
        "Save Template": "Salva Modello",
        "Template saved": "Modello salvato",
        "Generate": "Genera",
        "Tailor My CV": "Personalizza il mio CV",
        "Write Cover Letter": "Scrivi Lettera di Presentazione",
        "Both": "Entrambi",
        "Result": "Risultato",
        "CV": "CV",
        "Cover Letter": "Lettera di Presentazione",
        "Copy": "Copia",
        "Fetching…": "Scaricamento…",

        # ── Messages: tailor tab ───────────────────────────────────────
        "Empty JD": "Annuncio vuoto",
        "Paste a job description first.":
            "Incolla prima una descrizione del lavoro.",
        "No URL": "Nessun URL",
        "Enter a job post URL first.":
            "Inserisci prima un URL dell'annuncio di lavoro.",
        "Empty CV": "CV vuoto",
        "Paste your CV first.":
            "Incolla prima il tuo CV.",
        "No Job Description": "Nessun Annuncio",
        "Fetch or paste a job description first, then click 'Use this JD'.":
            "Scarica o incolla prima un annuncio, poi clicca 'Usa questo Annuncio'.",
        "No CV": "Nessun CV",
        "Paste your CV in the 'My CV' box and save it first.":
            "Incolla il tuo CV nella sezione 'Il mio CV' e salvalo prima.",
        "Copied to clipboard!": "Copiato negli appunti!",
        "Select a row": "Seleziona una riga",
        "Click a row first, then click Remove.":
            "Clicca prima su una riga, poi su Rimuovi.",
        "Remove": "Rimuovi",
        "Search error": "Errore di ricerca",
        "Error": "Errore",
        "Missing": "Manca",
        "Enter a search query.":
            "Inserisci una ricerca.",

        # ── Messages: AI settings ──────────────────────────────────────
        "AI API key saved.": "Chiave API AI salvata.",
        "Empty": "Vuoto",
        "Prompt cannot be empty.": "Il prompt non può essere vuoto.",
        "Custom prompt saved.": "Prompt personalizzato salvato.",
        "CV tailoring prompt saved.": "Prompt personalizzazione CV salvato.",
        "Cover letter prompt saved.": "Prompt lettera di presentazione salvato.",
        "Reset prompt to default?":
            "Ripristinare il prompt predefinito?",
        "Reset CV tailoring prompt to default?":
            "Ripristinare il prompt di personalizzazione CV predefinito?",
        "Reset cover letter prompt to default?":
            "Ripristinare il prompt della lettera di presentazione predefinito?",
        "Unknown provider": "Provider sconosciuto",
        "Missing model": "Modello mancante",
        "Type a model name first.":
            "Inserisci prima il nome di un modello.",
        "Missing base URL": "URL base mancante",

        # ── Messages: first run ────────────────────────────────────────
        "Welcome to SponsorScout": "Benvenuto in SponsorScout",

        # ── Messages: general ──────────────────────────────────────────
        "No job selected": "Nessun lavoro selezionato",
        "Select a job in the Search tab first.":
            "Seleziona prima un lavoro nella scheda Cerca.",
        "Dashboard data could not be loaded.":
            "Impossibile caricare i dati del pannello.",
        "Dedup complete": "Deduplicazione completata",
        "Probing ATS boards for": "Indagine bacheche ATS per",
        "Found": "Trovati",
        "candidate(s).": "candidato/i.",
        "No new companies found.":
            "Nessuna nuova azienda trovata.",
        "Try: 'analyst', 'backend', 'data engineer'":
            "Prova: 'analista', 'backend', 'ingegnere dati'",
        "Discovery done.": "Scoperta completata.",
        "Discovery failed.": "Scoperta fallita.",
        "Running discovery…": "Scoperta in corso…",
        "running…": "in esecuzione…",
        "Scanning…": "Scansione in corso…",
        "auto — every 1 h": "automatico — ogni 1 h",
        "stopped": "fermato",
        "Failed.": "Fallito.",
        "Verified": "Verificato",

        # ── Tooltip: How to Use ────────────────────────────────────────
        "AI Tailor — How to Use": "AI Personalizza — Come Usare",

        # ── Tooltip: JD section ────────────────────────────────────────

        # ── Tooltip: CV section ────────────────────────────────────────
        "My CV": "Il mio CV",

        # ── Tooltip: Cover Letter section ──────────────────────────────
        "Base Cover Letter Template": "Modello Lettera di Presentazione Base",

        # ── Tooltip: Generate section ──────────────────────────────────
        "Generate Buttons": "Pulsanti di Generazione",

        # ── Tooltip: Result section ────────────────────────────────────
        "Result Area": "Area Risultati",

        # ── AI Assistant tab ────────────────────────────────────────────
        "Chat with a free web AI — no API key needed":
            "Chatta con un'AI gratuita sul web — nessuna chiave API necessaria",
        "How to use": "Come usare",
        "Open AI Chat": "Apri Chat AI",
        "Opens a browser window with your normal login (stays signed "
        "in between sessions). Paste a prompt from the AI Tailor tab "
        "or Search tab, send it, then copy the reply back.":
            "Apre una finestra del browser con il tuo accesso normale (resta "
            "connesso tra le sessioni). Incolla un prompt dalla scheda AI "
            "Personalizza o Cerca, invialo, poi copia la risposta.",
        "Site:": "Sito:",
        "Eligibility Rating": "Valutazione di Eleggibilità",
        "From the Search tab: select a job, click '📋 Copy Rating Prompt', "
        "paste it into the AI chat above, then come back, copy the "
        "reply and click '📥 Paste AI Result' in the Search tab.":
            "Dalla scheda Cerca: seleziona un lavoro, clicca '📋 Copia Prompt di "
            "Valutazione', incollalo nella chat AI sopra, poi torna, copia la "
            "risposta e clicca '📥 Incolla Risultato AI' nella scheda Cerca.",
        "Go to Search tab": "Vai alla scheda Cerca",
        "CV Tailoring & Cover Letter": "Personalizzazione CV e Lettera",
        "From the ✨ AI Tailor tab: confirm a job description, then click "
        "'📋 Copy CV Prompt' or '📋 Copy Cover Letter Prompt'. Paste it into "
        "the AI chat above, then copy the reply back into the Result box "
        "with '📥 Paste'.":
            "Dalla scheda ✨ AI Personalizza: confema una descrizione del lavoro, "
            "poi clicca '📋 Copia Prompt CV' o '📋 Copia Prompt Lettera'. "
            "Incollalo nella chat AI sopra, poi copia la risposta nella "
            "casella Risultato con '📥 Incolla'.",
        "Go to AI Tailor tab": "Vai alla scheda AI Personalizza",

        # ── Language toggle ────────────────────────────────────────────
        "Language": "Lingua",
    },
}


def _(text: str) -> str:
    """Translate a string to the current locale.

    Falls back to English (the key itself) if the string is not translated.
    """
    return LANGUAGES.get(_locale, {}).get(text, text)