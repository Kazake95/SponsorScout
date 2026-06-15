from __future__ import annotations

import threading
import logging
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from sponsorscout.i18n import _, set_locale, get_locale, load_saved_locale, get_available_locales, get_locale_name

logger = logging.getLogger(__name__)

from sponsorscout.db.database import (
    initialize, search_jobs, get_dashboard_stats,
    get_dashboard_top_companies, get_dashboard_country_counts,
    get_dashboard_ats_health, upsert_application, list_applications,
    delete_application, get_connection, DB_PATH,
)
from sponsorscout.services.country_config import ordered_countries
from sponsorscout.services.objectives import available_search_objective_labels, normalize_objective
from sponsorscout.core.dedup import dedup_jobs_in_db, dedup_companies_in_db
from sponsorscout.services.scan_coordinator import ScanCoordinator
from sponsorscout.services.ai_rating import (
    load_prompt, save_prompt,
    DEFAULT_AI_PROMPT,
    load_cv_prompt, save_cv_prompt, load_cl_prompt, save_cl_prompt,
    DEFAULT_CV_PROMPT, DEFAULT_CL_PROMPT,
    load_cv, save_cv,
    load_base_cover_letter, save_base_cover_letter,
    fetch_jd_from_url,
    build_rating_prompt, build_cv_prompt, build_cover_letter_prompt,
    parse_rating_result, parse_text_result,
)
from sponsorscout.services.ai_webview import AIWebviewLauncher, AI_SITES, DEFAULT_SITE

EXPERIENCE_OPTIONS = [
    "All",
    "Any (incl. unknown)",
    "Unknown / Not classified",
    "Intern",
    "Entry",
    "Mid",
    "Senior",
    "Lead",
    "Exec",
]
SORT_OPTIONS = ["Best match", "Latest", "Sponsored Only"]
REMOTE_OPTIONS = ["All", "Remote EU", "Remote EMEA", "Remote Global", "Remote Only", "Hybrid"]
OBJECTIVE_OPTIONS = available_search_objective_labels()


class SponsorScoutApp(tk.Tk):

    def __init__(self):
        super().__init__()
        load_saved_locale()
        self.title("SponsorScout v0.1.1")
        self.geometry("1380x840")
        self._selected_job = None
        # BUG-FIX: initialise caches before _build_ui / load_results so
        # load_results() never hits AttributeError on self._ai_cache
        self._ai_cache: dict[str, dict] = {}
        self._tailor_jd_text: str = ""      # active JD for tailoring panel
        self._tailor_job_title: str = ""
        self._tailor_job_company: str = ""
        self._load_icon()
        self._ai_webview = AIWebviewLauncher()
        self._scanner = ScanCoordinator(
            db_path=DB_PATH,
            on_progress=lambda m: self.status_var.set(m),
            on_complete=lambda _: self.after(0, self._on_scan_complete),
        )
        self._build_ui()
        self._scanner.set_on_progress(self._on_scan_progress)
        self.load_results()
        self.load_dashboard()
        self.load_applications()
        self.load_health()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(500, self._check_first_run)

    # ── Icon ──────────────────────────────────────────────────────────────────

    def _load_icon(self):
        self._logo_image = None
        icon_dir = Path(__file__).resolve().parent.parent / "data" / "icons"
        try:
            from PIL import Image, ImageTk
            p256 = icon_dir / "sponsorscout_256.png"
            p48  = icon_dir / "sponsorscout_48.png"
            if p256.exists():
                ph = ImageTk.PhotoImage(Image.open(str(p48)).resize((40, 40)))
                self.iconphoto(True, ph)
                self._icon_photo = ph
                self._logo_image = ImageTk.PhotoImage(
                    Image.open(str(p256)).resize((28, 28)))
        except Exception as exc:
            logger.exception("Failed to load PNG icon, falling back to Tk PhotoImage")
            try:
                p = icon_dir / "sponsorscout_48.png"
                if p.exists():
                    ph = tk.PhotoImage(file=str(p))
                    self.iconphoto(True, ph)
                    self._icon_photo = ph
                    self._logo_image = ph
            except Exception as exc2:
                logger.exception("Failed to load icon fallback")
                pass

    def _on_close(self):
        self._scanner.stop()
        self._ai_webview.close()
        try:
            self.quit()
        finally:
            self.destroy()

    def _on_scan_progress(self, msg: str):
        self._append_scan_log(msg)
        self.status_var.set(msg)
        try:
            self.update_idletasks()
        except Exception:
            pass

    def _on_scan_complete(self):
        self.load_dashboard()
        self.load_results()
        self.load_health()
        self.scan_status.set("idle")
        self.status_var.set("Scan complete.")

    def _check_first_run(self):
        try:
            if get_dashboard_stats(DB_PATH)["companies"] == 0:
                if messagebox.askyesno(
                    "Welcome to SponsorScout",
                    "No data yet.\n\n"
                    "Run the first scan now? Fetches jobs from each company's\n"
                    "official career page first, then ATS fallback connectors (1–3 min)."
                ):
                    self.tabs.select(self.tools_tab)
                    self._run_scan_now()
        except Exception as exc:
            logger.exception("Failed to determine whether this is the first run")
            # Don't block startup if the dashboard is unavailable, but log the cause.

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ───────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg="#1d2d44", pady=7, padx=12)
        hdr.pack(fill="x")
        if self._logo_image:
            tk.Label(hdr, image=self._logo_image,
                     bg="#1d2d44").pack(side="left", padx=(0, 8))
        tk.Label(hdr, text="SponsorScout",
                 font=("Helvetica", 13, "bold"),
                 fg="white", bg="#1d2d44").pack(side="left")
        tk.Label(hdr,
                 text=f"  ·  {_('Verified sponsorship-focused jobs from official career pages and ATS boards')}",
                 font=("Helvetica", 9), fg="#8fa8c8",
                 bg="#1d2d44").pack(side="left")
        # Language toggle
        self._lang_var = tk.StringVar(value=get_locale())
        lang_combo = ttk.Combobox(
            hdr, textvariable=self._lang_var,
            values=get_available_locales(),
            width=5, state="readonly")
        lang_combo.pack(side="right", padx=(0, 8))
        lang_combo.bind("<<ComboboxSelected>>", self._on_language_change)

        self.status_var = tk.StringVar(value=_("Ready"))
        tk.Label(hdr, textvariable=self.status_var,
                 font=("Helvetica", 9), fg="#8fa8c8",
                 bg="#1d2d44").pack(side="right")

        # ── Tabs ─────────────────────────────────────────────────────────────
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook",      background="#f0f2f5", borderwidth=0)
        style.configure("TNotebook.Tab",  background="#e2e6ea", foreground="#444",
                        padding=[16, 6], font=("Helvetica", 10))
        style.map("TNotebook.Tab",
                  background=[("selected", "#ffffff")],
                  foreground=[("selected", "#1d2d44")])
        style.configure("Treeview",
                        background="#ffffff", fieldbackground="#ffffff",
                        foreground="#222", rowheight=26,
                        font=("Helvetica", 9))
        style.configure("Treeview.Heading",
                        background="#f0f2f5", foreground="#444",
                        font=("Helvetica", 9, "bold"))
        # BUGFIX: previous style used a default 1-pixel Treeview border
        # and 1px-high separator rules between heading and body, which
        # showed up as a phantom horizontal line above the section
        # headers in the dashboard and on every tab that contained a
        # Treeview. We now zero-out the border widths and remove the
        # heading underline so the layout reads as a continuous canvas
        # with cards on top and tables below.
        style.configure("Treeview.Heading",
                        borderwidth=0, relief="flat",
                        background="#f0f2f5", foreground="#444",
                        font=("Helvetica", 9, "bold"))
        style.configure("Treeview",
                        background="#ffffff", fieldbackground="#ffffff",
                        foreground="#222", rowheight=26,
                        borderwidth=0, relief="flat",
                        font=("Helvetica", 9))
        style.layout("Treeview", [
            ("Treeview.treearea", {"sticky": "nswe"})
        ])
        style.map("Treeview",
                  background=[("selected", "#3a7bd5")],
                  foreground=[("selected", "white")])
        style.configure("TButton",   font=("Helvetica", 9), padding=[8, 4])
        style.configure("TCombobox", font=("Helvetica", 9))
        style.configure("TEntry",    font=("Helvetica", 9))
        # Use ttk's vertical/horizontal scrollbar themes that look uniform
        # across Tk versions and don't have the "chunky" ttk default.
        style.configure("Vertical.TScrollbar", arrowsize=14)
        style.configure("Horizontal.TScrollbar", arrowsize=14)

        self.tabs = ttk.Notebook(self)
        self.search_tab       = ttk.Frame(self.tabs)
        self.dashboard_tab    = ttk.Frame(self.tabs)
        self.applications_tab = ttk.Frame(self.tabs)
        self.health_tab       = ttk.Frame(self.tabs)
        self.tools_tab        = ttk.Frame(self.tabs)
        self.tailor_tab       = ttk.Frame(self.tabs)
        self.ai_assistant_tab = ttk.Frame(self.tabs)

        self.tabs.add(self.search_tab,       text=_("Search"))
        self.tabs.add(self.dashboard_tab,    text=_("Dashboard"))
        self.tabs.add(self.applications_tab, text=_("Applications"))
        self.tabs.add(self.health_tab,       text=_("ATS Health"))
        self.tabs.add(self.tailor_tab,       text=_("✨ AI Tailor"))
        self.tabs.add(self.ai_assistant_tab, text=_("🤖 AI Assistant"))
        self.tabs.add(self.tools_tab,        text=_("Tools"))
        self.tabs.pack(fill="both", expand=True)

        self._build_search_tab()
        self._build_dashboard_tab()
        self._build_applications_tab()
        self._build_health_tab()
        self._build_tailor_tab()
        self._build_ai_assistant_tab()
        self._build_tools_tab()

    # ── Search tab ────────────────────────────────────────────────────────────

    def _build_search_tab(self):
        bar = tk.Frame(self.search_tab, bg="#ffffff", padx=10, pady=8)
        bar.pack(fill="x")

        self.title_var      = tk.StringVar()
        self.company_var    = tk.StringVar()
        self.country_var    = tk.StringVar(value=_("All"))
        self.spons_var      = tk.StringVar(value=_("All"))
        self.remote_var     = tk.StringVar(value=_("All"))
        self.experience_var = tk.StringVar(value=_("All"))
        self.objective_var  = tk.StringVar(value="Balanced")
        self.sort_var       = tk.StringVar(value=_("Best match"))
        self.eu_bc_var      = tk.BooleanVar()
        self.reloc_var      = tk.BooleanVar()

        def lbl(parent, t):
            return tk.Label(parent, text=t, font=("Helvetica", 9),
                            fg="#666", bg="#ffffff")
        def ent(v, w=20): return ttk.Entry(bar, textvariable=v, width=w)
        def cmb(v, vals, w=15):
            return ttk.Combobox(bar, textvariable=v,
                                values=vals, width=w, state="readonly")

        r1 = tk.Frame(bar, bg="#ffffff")
        r1.pack(fill="x", pady=(0, 5))
        lbl(r1, _("Title:")).pack(side="left")
        ent(self.title_var, 24).pack(side="left", padx=(3, 10))
        lbl(r1, _("Company:")).pack(side="left")
        ent(self.company_var, 20).pack(side="left", padx=(3, 10))
        lbl(r1, _("Country:")).pack(side="left")
        cmb(self.country_var, ["All"] + ordered_countries(), 18
            ).pack(side="left", padx=(3, 10))
        ttk.Button(r1, text=_("Search"),
                   command=self.load_results).pack(side="left", padx=4)
        ttk.Button(r1, text=_("Clear"),
                   command=self._clear_search).pack(side="left")
        self.count_var = tk.StringVar(value="")
        tk.Label(r1, textvariable=self.count_var,
                 font=("Helvetica", 9), fg="#888",
                 bg="#ffffff").pack(side="right", padx=8)

        r2 = tk.Frame(bar, bg="#ffffff")
        r2.pack(fill="x")
        lbl(r2, _("Sponsorship:")).pack(side="left")
        cmb(self.spons_var, [_("All"), _("Sponsored Only")], 13
            ).pack(side="left", padx=(3, 10))
        lbl(r2, _("Remote:")).pack(side="left")
        cmb(self.remote_var, [_("All"), _("Remote EU"), _("Remote EMEA"),
                              _("Remote Global"), _("Remote Only"),
                              _("Hybrid")], 13
            ).pack(side="left", padx=(3, 10))
        lbl(r2, _("Experience:")).pack(side="left")
        cmb(self.experience_var, [
            _("All"), _("Any (incl. unknown)"),
            _("Unknown / Not classified"), _("Intern"), _("Entry"),
            _("Mid"), _("Senior"), _("Lead"), _("Exec")
        ], 18).pack(side="left", padx=(3, 10))

        r3 = tk.Frame(bar, bg="#ffffff")
        r3.pack(fill="x", pady=(5, 0))
        lbl(r3, _("Sort:")).pack(side="left")
        cmb(self.sort_var, [_("Best match"), _("Latest"), _("Sponsored Only")], 12
            ).pack(side="left", padx=(3, 10))
        lbl(r3, _("Objective:")).pack(side="left")
        cmb(self.objective_var, OBJECTIVE_OPTIONS, 16
            ).pack(side="left", padx=(3, 10))
        tk.Checkbutton(r3, text=_("EU Blue Card"), variable=self.eu_bc_var,
                       bg="#ffffff", font=("Helvetica", 9),
                       fg="#444").pack(side="left", padx=(6, 4))
        tk.Checkbutton(r3, text=_("Relocation"), variable=self.reloc_var,
                       bg="#ffffff", font=("Helvetica", 9),
                       fg="#444").pack(side="left")

        ttk.Separator(self.search_tab, orient="horizontal").pack(fill="x")

        cols = ("Title", "Company", "Country", "Location",
                "Remote", "Sponsor", "BluCard", "Reloc", "AI ★", "URL")
        widths = {
            "Title": 210, "Company": 140, "Country": 110,
            "Location": 130, "Remote": 80, "Sponsor": 55,
            "BluCard": 52, "Reloc": 45, "AI ★": 45, "URL": 0,
        }

        # BUGFIX: previous version packed the tree and the AI panel in
        # the SAME `self.search_tab` frame and let the AI panel
        # `side="bottom"` push the tree up, making the panel effectively
        # non-resizable (the user had to drag-resize the whole window to
        # see the long AI verdict). We now wrap the tree + AI panel in a
        # `ttk.PanedWindow` (vertical sash) so the user can drag the
        # divider to allocate more or less space to either pane. We
        # also use plain ttk.Scrollbar (not ScrolledText) so the scroll
        # widget uses the themed style we configured in `_build_ui`,
        # giving smooth macOS/Windows rendering instead of the chunky
        # legacy look from the previous version.
        self._search_pane = ttk.PanedWindow(
            self.search_tab, orient="vertical")
        self._search_pane.pack(fill="both", expand=True, pady=(2, 0))

        # Top pane: the Treeview with its own vertical + horizontal
        # ttk scrollbars.
        tree_frame = tk.Frame(self._search_pane)
        self._search_pane.add(tree_frame, weight=1)

        self.tree = ttk.Treeview(
            tree_frame, columns=cols,
            show="headings", selectmode="browse")
        for c in cols:
            self.tree.heading(c, text=c,
                              command=lambda col=c: self._sort_tree(col))
            self.tree.column(c, width=widths.get(c, 100),
                             anchor="w", stretch=(c == "URL"))
        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal",
                            command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self._open_url)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Bottom pane: the AI rating panel. Wrapped in a ttk.LabelFrame
        # for the section heading, with the result text inside.
        self._ai_panel = ttk.LabelFrame(
            self._search_pane, text=f" ✨ {_('AI Job Rating & Eligibility')} ")
        self._search_pane.add(self._ai_panel, weight=0)
        # BUGFIX: previous version packed the AI panel with a hard-coded
        # natural height (no fill="both", no expand) so users with a
        # long AI verdict could not see the full result without
        # maximizing the window. The PanedWindow above fixes that.
        ai_inner = tk.Frame(self._ai_panel, bg="#f8f9fa")
        ai_inner.pack(fill="both", expand=True, padx=4, pady=4)
        ai_hdr = tk.Frame(ai_inner, bg="#f8f9fa")
        ai_hdr.pack(fill="x", pady=(0, 4))
        self._ai_copy_btn = ttk.Button(
            ai_hdr, text=f"📋 {_('Copy Rating Prompt')}",
            command=self._copy_rating_prompt)
        self._ai_copy_btn.pack(side="left", padx=(0, 4))
        self._ai_paste_btn = ttk.Button(
            ai_hdr, text=f"📥 {_('Paste AI Result')}",
            command=self._paste_rating_result)
        self._ai_paste_btn.pack(side="left", padx=4)
        self._ai_tailor_btn = ttk.Button(
            ai_hdr, text=f"📄 {_('Tailor CV & Letter')}",
            command=self._open_tailor_for_selected)
        self._ai_tailor_btn.pack(side="left", padx=4)
        self._ai_result_var = tk.StringVar(value=_("Select a job, click 'Copy Rating Prompt', paste it into the AI Assistant tab, then click 'Paste AI Result'."))
        self._ai_cv_hint_var = tk.StringVar(value="")
        tk.Label(ai_hdr, textvariable=self._ai_cv_hint_var,
                 font=("Helvetica", 8, "italic"), fg="#3a7bd5",
                 bg="#f8f9fa").pack(side="left", padx=(8, 0))
        self._ai_result_lbl = tk.Label(
            ai_inner, textvariable=self._ai_result_var,
            font=("Helvetica", 9), fg="#444", bg="#f8f9fa",
            wraplength=1300, justify="left", padx=4, pady=4,
            anchor="w",
        )
        self._ai_result_lbl.pack(fill="both", expand=True)

        ctx = tk.Menu(self.tree, tearoff=0)
        ctx.add_command(label=_("Open in browser"), command=self._open_url)
        ctx.add_command(label=_("Save to Applications"), command=self._save_to_apps)
        ctx.add_command(label=_("Copy Rating Prompt"), command=self._copy_rating_prompt)
        ctx.add_command(label=_("Tailor CV & Cover Letter"), command=self._open_tailor_for_selected)
        self._ctx_menu = ctx

        def _show_context_menu(event):
            try:
                current = self.tabs.select()
                if current != str(self.search_tab):
                    return
            except Exception as exc:
                logger.debug("Context menu event ignored because tab state could not be read", exc_info=exc)
                return
            try:
                ctx.tk_popup(event.x_root, event.y_root)
            finally:
                ctx.grab_release()

        self.tree.bind("<Button-3>", _show_context_menu)

        def _dismiss_menu_on_tab_change(_event=None):
            try:
                self._ctx_menu.unpost()
            except Exception as exc:
                logger.debug("Failed to dismiss context menu", exc_info=exc)

        self.tabs.bind("<<NotebookTabChanged>>", _dismiss_menu_on_tab_change)
        self._sort_col = None
        self._sort_asc = True

    def _copy_rating_prompt(self):
        if not self._selected_job:
            self._ai_result_var.set(_("No job selected."))
            return
        v = self._selected_job
        url = str(v[-1])

        title   = str(v[0])
        company = str(v[1])
        country = str(v[2])
        spons   = int(v[5]) if str(v[5]).lstrip("-").isdigit() else 0
        remote  = str(v[4])
        bluecard = v[6] == "✓"
        reloc    = v[7] == "✓"

        # Show CV status
        cv_text = load_cv()
        if cv_text:
            self._ai_cv_hint_var.set(_("Rating against your saved CV profile"))
        else:
            self._ai_cv_hint_var.set(_("No CV on file — paste yours in AI Assistant tab for personalised results"))

        # Fetch description from DB
        try:
            conn = get_connection(DB_PATH)
            row = conn.execute("SELECT description FROM jobs WHERE url=?", (url,)).fetchone()
            description = row["description"] if row else ""
            conn.close()
        except Exception as exc:
            logger.exception("Failed to load job description for AI rating")
            description = ""

        prompt = build_rating_prompt(
            title=title, company=company, country=country,
            description=description, sponsorship_score=spons,
            remote_type=remote, eu_blue_card=bluecard,
            has_relocation=reloc,
            objective=self.objective_var.get(),
        )
        self.clipboard_clear()
        self.clipboard_append(prompt)
        self._tailor_job_title   = title
        self._tailor_job_company = company
        self._ai_pending_url = url
        self._ai_result_var.set(
            _("✓ Prompt copied! Paste it into the AI Assistant tab, "
              "copy the reply, then click 'Paste AI Result' here."))

    def _paste_rating_result(self):
        if not self._selected_job:
            self._ai_result_var.set(_("No job selected."))
            return
        v = self._selected_job
        url = str(v[-1])
        try:
            pasted = self.clipboard_get()
        except Exception:
            pasted = ""
        result = parse_rating_result(pasted)
        if not result.get("error"):
            self._ai_cache[url] = result
            rating = result.get("rating")
            sel = self.tree.selection()
            if sel and isinstance(rating, int):
                self._update_ai_rating_in_tree(rating, sel)
        self._show_ai_result(result)

    def _update_ai_rating_in_tree(self, rating: int, sel: tuple):
        """Update the AI rating column in the treeview (must run on main thread)."""
        try:
            rating_str = f"{rating}/10"
            item_id = sel[0]
            values = list(self.tree.item(item_id)["values"])
            values[8] = rating_str  # AI ★ column index 8
            self.tree.item(item_id, values=values)
        except Exception as exc:
            logger.exception("Failed to update AI rating in tree: %s", exc)

    def _show_ai_result(self, result: dict):
        if result.get("error"):
            self._ai_result_var.set(f"❌ {result['error']}")
            return
        rating  = result.get("rating", "?")
        verdict = result.get("verdict", "")
        pros    = result.get("pros", [])
        cons    = result.get("cons", [])
        stars   = "★" * int(rating) + "☆" * (10 - int(rating)) if isinstance(rating, int) else ""
        pros_str = "  ✓ " + "  ✓ ".join(pros) if pros else ""
        cons_str = "  ✗ " + "  ✗ ".join(cons) if cons else ""
        text = f"Rating: {rating}/10 {stars}   |   {verdict}"
        if pros_str:
            text += f"\n{pros_str}"
        if cons_str:
            text += f"\n{cons_str}"
        self._ai_result_var.set(text)

    def _sort_tree(self, col):
        def sort_key(value):
            value = str(value or "").strip()
            if col in ("Sponsor", "AI ★"):
                if "/" in value:
                    value = value.split("/", 1)[0].strip()
                try:
                    return float(value)
                except ValueError:
                    return -1
            if col in ("BluCard", "Reloc"):
                return 1 if value == "✓" else 0
            return value.lower()

        rows = [(sort_key(self.tree.set(k, col)), k)
                for k in self.tree.get_children("")]
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_asc = True
            self._sort_col = col
        rows.sort(reverse=not self._sort_asc)
        for i, (_, k) in enumerate(rows):
            self.tree.move(k, "", i)

    def _on_language_change(self, _event=None):
        """Handle language change from the header dropdown."""
        new_locale = self._lang_var.get()
        set_locale(new_locale)
        messagebox.showinfo(
            _("Language"),
            f"{_('Language')} → {get_locale_name(new_locale)}\n\n"
            "Please restart SponsorScout to apply\nthe new language.")

    def _clear_search(self):
        self.title_var.set("")
        self.company_var.set("")
        self.country_var.set(_("All"))
        self.spons_var.set(_("All"))
        self.remote_var.set(_("All"))
        self.experience_var.set(_("All"))
        self.objective_var.set("Balanced")
        self.sort_var.set(_("Best match"))
        self.eu_bc_var.set(False)
        self.reloc_var.set(False)
        self.load_results()

    def _on_select(self, _=None):
        sel = self.tree.selection()
        self._selected_job = (self.tree.item(sel[0])["values"]
                              if sel else None)
        if self._selected_job:
            url = str(self._selected_job[-1])
            cv_text = load_cv()
            if cv_text:
                self._ai_cv_hint_var.set(_("Rating will use your saved CV profile"))
            else:
                self._ai_cv_hint_var.set(_("No CV on file — paste yours in AI Assistant tab for personalised results"))
            if url in self._ai_cache:
                self._show_ai_result(self._ai_cache[url])
            else:
                self._ai_result_var.set(_("Select a job, then click 'Copy Rating Prompt'."))
        else:
            self._ai_cv_hint_var.set("")
            self._ai_result_var.set(_("Select a job, then click 'Copy Rating Prompt'."))

    def _open_url(self, _=None):
        sel = self.tree.selection()
        if sel:
            webbrowser.open(str(self.tree.item(sel[0])["values"][-1]))

    def _save_to_apps(self):
        if not self._selected_job:
            return
        v = self._selected_job
        upsert_application(DB_PATH,
                           job_url=str(v[-1]),
                           company=str(v[1]),
                           title=str(v[0]),
                           status="saved")
        self.load_applications()
        self.status_var.set(f"Saved: {v[0]} @ {v[1]}")

    def _open_tailor_for_selected(self):
        """Switch to AI Tailor tab and pre-load the selected job's info."""
        if not self._selected_job:
            messagebox.showinfo("No job selected",
                                "Select a job in the Search tab first.")
            return
        v = self._selected_job
        url     = str(v[-1])
        title   = str(v[0])
        company = str(v[1])
        # Try to get description from DB
        try:
            from sponsorscout.db.database import get_connection, DB_PATH
            conn = get_connection(DB_PATH)
            row  = conn.execute("SELECT description FROM jobs WHERE url=?",
                                (url,)).fetchone()
            description = (row["description"] or "").strip() if row else ""
            conn.close()
        except Exception as exc:
            logger.exception("Failed to load job description for the tailor tab")
            description = ""

        # Pre-populate the tailor tab
        self._tailor_job_title   = title
        self._tailor_job_company = company
        self._tailor_url_var.set(url)
        self._tailor_job_label_var.set(f"Job: {title}  @  {company}")

        # If we already have a description, paste it into the JD box
        if description:
            self._tailor_jd_text = description
            self._update_jd_preview(description)
        else:
            self._tailor_jd_text = ""
            self._update_jd_preview("")

        self.tabs.select(self.tailor_tab)

    def _update_jd_preview(self, text: str):
        # BUGFIX: previous version called `config(state="normal")` both
        # before AND after the insert, which actually kept the widget
        # editable when the intent was to render the fetched JD as a
        # read-only preview. The textbox was effectively always editable,
        # so users could accidentally edit the fetched JD and then
        # click "Use this JD" with a half-edited version that had no
        # warning. Now we keep the box editable (so the user CAN paste
        # their own JD), and rely on the explicit "Use this JD" button
        # to commit the contents.
        self._jd_text_box.config(state="normal")
        self._jd_text_box.delete("1.0", "end")
        self._jd_text_box.insert("1.0", text or "")
        # NOTE: do NOT re-disable the box here — we want the user to be
        # able to paste, edit, or augment the JD inline. The button row
        # below provides the explicit "Use this JD" commit step.

    # ── AI Tailor tab ─────────────────────────────────────────────────────────

    def _build_tailor_tab(self):
        outer = tk.Frame(self.tailor_tab, bg="#f0f2f5", padx=14, pady=10)
        outer.pack(fill="both", expand=True)

        # ── Header ────────────────────────────────────────────────────────
        hdr = tk.Frame(outer, bg="#f0f2f5")
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(hdr, text="✨  AI CV & Cover Letter Tailor",
                 font=("Helvetica", 13, "bold"),
                 fg="#1d2d44", bg="#f0f2f5").pack(side="left")
        tk.Label(hdr,
                 text="  ·  Select a job in Search → 'Tailor CV & Letter', or load a JD manually below",
                 font=("Helvetica", 9), fg="#8fa8c8",
                 bg="#f0f2f5").pack(side="left")
        help_btn = ttk.Button(hdr, text="📖 How to use",
                              command=self._show_tailor_help)
        help_btn.pack(side="right")

        # Active job label
        self._tailor_job_label_var = tk.StringVar(value="No job selected — use Search tab or paste a JD below")
        tk.Label(outer, textvariable=self._tailor_job_label_var,
                 font=("Helvetica", 9, "italic"), fg="#3a7bd5",
                 bg="#f0f2f5").pack(anchor="w", pady=(0, 6))

        # ── Two-column layout ─────────────────────────────────────────────
        cols = tk.Frame(outer, bg="#f0f2f5")
        cols.pack(fill="both", expand=True)

        left  = tk.Frame(cols, bg="#f0f2f5")
        right = tk.Frame(cols, bg="#f0f2f5")
        left.pack(side="left",  fill="both", expand=True, padx=(0, 6))
        right.pack(side="left", fill="both", expand=True)

        # ── LEFT: JD input ────────────────────────────────────────────────
        jd_header = tk.Frame(left, bg="#ffffff")
        jd_header.pack(fill="x", padx=10, pady=(10, 2))
        tk.Label(jd_header, text="Job Description",
                 font=("Helvetica", 9, "bold"),
                 fg="#1d2d44", bg="#ffffff").pack(side="left")
        jd_info = tk.Label(jd_header, text="ⓘ",
                           font=("Helvetica", 10, "bold"),
                           fg="#3a7bd5", bg="#ffffff", cursor="hand2")
        jd_info.pack(side="left", padx=(4, 0))
        jd_info.bind("<Button-1>", lambda e: messagebox.showinfo(
            "Job Description",
            "Paste a job description to tailor your CV/cover letter.\n\n"
            "Two ways:\n"
            "1. Enter a job URL → click '⬇ Fetch JD'\n"
            "2. Paste the full text → click 'Use this JD'\n\n"
            "The AI uses this to match keywords, skills, and\n"
            "requirements when rewriting your CV.\n\n"
            "TIP: From the Search tab, right-click a job →\n"
            "'Tailor CV & Letter' to auto-fill this panel."))
        jd_frame = tk.Frame(left, bg="#ffffff", padx=10, pady=4)
        jd_frame.pack(fill="both", expand=True)

        url_row = tk.Frame(jd_frame, bg="#ffffff"); url_row.pack(fill="x", pady=(0, 6))
        tk.Label(url_row, text="Job URL:", font=("Helvetica", 9),
                 bg="#ffffff").pack(side="left")
        self._tailor_url_var = tk.StringVar()
        ttk.Entry(url_row, textvariable=self._tailor_url_var,
                  width=46).pack(side="left", padx=(4, 6))
        self._fetch_btn = ttk.Button(url_row, text="⬇ Fetch JD",
                                      command=self._fetch_jd_from_url)
        self._fetch_btn.pack(side="left")

        tk.Label(jd_frame, text="— or paste full JD below —",
                 font=("Helvetica", 8), fg="#aaa", bg="#ffffff").pack(anchor="w")

        from tkinter import scrolledtext as _st
        self._jd_text_box = _st.ScrolledText(
            jd_frame, height=14, wrap="word",
            font=("Helvetica", 9), relief="solid", bd=1)
        self._jd_text_box.pack(fill="both", expand=True, pady=(4, 0))
        self._jd_text_box.bind("<<Modified>>", self._on_jd_changed)

        jd_btn_row = tk.Frame(jd_frame, bg="#ffffff"); jd_btn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(jd_btn_row, text="Use this JD",
                   command=self._confirm_jd).pack(side="left")
        ttk.Button(jd_btn_row, text="Clear",
                   command=lambda: (self._jd_text_box.delete("1.0", "end"),
                                    setattr(self, "_tailor_jd_text", ""),
                                    self._tailor_jd_status_var.set("")
                                    )).pack(side="left", padx=6)
        self._tailor_jd_status_var = tk.StringVar(value="")
        tk.Label(jd_frame, textvariable=self._tailor_jd_status_var,
                 font=("Helvetica", 8), fg="#3a7bd5", bg="#ffffff").pack(anchor="w")

        # ── RIGHT: scrollable canvas for all right-column sections ───────
        right_canvas = tk.Canvas(right, bg="#f0f2f5", highlightthickness=0)
        right_vsb = ttk.Scrollbar(right, orient="vertical",
                                   command=right_canvas.yview)
        right_canvas.configure(yscrollcommand=right_vsb.set)
        right_vsb.pack(side="right", fill="y")
        right_canvas.pack(side="left", fill="both", expand=True)
        right_inner = tk.Frame(right_canvas, bg="#f0f2f5")
        right_canvas_win = right_canvas.create_window(
            (0, 0), window=right_inner, anchor="nw")
        def _on_right_configure(_e=None):
            right_canvas.configure(scrollregion=right_canvas.bbox("all"))
        def _on_right_canvas_configure(e):
            right_canvas.itemconfig(right_canvas_win, width=e.width)
        right_inner.bind("<Configure>", _on_right_configure)
        right_canvas.bind("<Configure>", _on_right_canvas_configure)
        # Mousewheel scroll — only active when mouse is over this canvas
        def _on_right_mousewheel(e):
            right_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        right_canvas.bind("<Enter>", lambda e: right_canvas.bind_all(
            "<MouseWheel>", _on_right_mousewheel))
        right_canvas.bind("<Leave>", lambda e: right_canvas.unbind_all(
            "<MouseWheel>"))

        # ── My CV section ───────────────────────────────────────────────
        cv_header = tk.Frame(right_inner, bg="#ffffff")
        cv_header.pack(fill="x", padx=10, pady=(10, 2))
        tk.Label(cv_header, text="My CV (stored locally)",
                 font=("Helvetica", 9, "bold"),
                 fg="#1d2d44", bg="#ffffff").pack(side="left")
        cv_info = tk.Label(cv_header, text="ⓘ",
                            font=("Helvetica", 10, "bold"),
                            fg="#3a7bd5", bg="#ffffff", cursor="hand2")
        cv_info.pack(side="left", padx=(4, 0))
        cv_info.bind("<Button-1>", lambda e: messagebox.showinfo(
            "My CV",
            "Paste your full CV once. It is saved locally and\n"
            "used by the AI for ALL future tailoring sessions.\n\n"
            "The AI uses this to personalise:\n"
            "• Job ratings (eligibility assessment)\n"
            "• CV tailoring (rewrites your CV for each role)\n"
            "• Cover letters (uses your experience as basis)\n\n"
            "File: ~/.sponsorscout/my_cv.txt"))
        cv_frame = tk.Frame(right_inner, bg="#ffffff", padx=10, pady=4)
        cv_frame.pack(fill="both", expand=True)

        tk.Label(cv_frame,
                 text="Paste your current CV once — it's saved for all future tailoring sessions.",
                 font=("Helvetica", 8), fg="#888", bg="#ffffff",
                 wraplength=480, justify="left").pack(anchor="w", pady=(0, 4))

        self._cv_text_box = _st.ScrolledText(
            cv_frame, height=10, wrap="word",
            font=("Helvetica", 9), relief="solid", bd=1)
        self._cv_text_box.pack(fill="both", expand=True)
        saved_cv = load_cv()
        if saved_cv:
            self._cv_text_box.insert("1.0", saved_cv)

        cv_btn_row = tk.Frame(cv_frame, bg="#ffffff"); cv_btn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(cv_btn_row, text="💾 Save CV",
                   command=self._save_cv_text).pack(side="left")
        self._cv_status_var = tk.StringVar(value="✓ CV saved" if saved_cv else "")
        tk.Label(cv_frame, textvariable=self._cv_status_var,
                 font=("Helvetica", 8), fg="#2a9d2a", bg="#ffffff").pack(anchor="w", pady=(2, 0))

        # ── Base Cover Letter template ──────────────────────────────────────
        cl_header = tk.Frame(right_inner, bg="#ffffff")
        cl_header.pack(fill="x", padx=10, pady=(10, 2))
        tk.Label(cl_header, text="Base Cover Letter (template for AI)",
                 font=("Helvetica", 9, "bold"),
                 fg="#1d2d44", bg="#ffffff").pack(side="left")
        cl_info = tk.Label(cl_header, text="ⓘ",
                           font=("Helvetica", 10, "bold"),
                           fg="#3a7bd5", bg="#ffffff", cursor="hand2")
        cl_info.pack(side="left", padx=(4, 0))
        cl_info.bind("<Button-1>", lambda e: messagebox.showinfo(
            "Base Cover Letter Template",
            "Optional: paste an example cover letter you like.\n\n"
            "The AI will use it as a STYLE/STRUCTURE reference\n"
            "when generating new cover letters for each role.\n\n"
            "This ensures every generated letter matches your\n"
            "preferred tone, formatting, and writing style.\n\n"
            "File: ~/.sponsorscout/my_cover_letter.txt"))
        cl_frame = tk.Frame(right_inner, bg="#ffffff", padx=10, pady=4)
        cl_frame.pack(fill="x", pady=(0, 4))

        tk.Label(cl_frame,
                 text="Paste an example cover letter you like. The AI will match "
                      "its style/tone when generating new letters.",
                 font=("Helvetica", 8), fg="#888", bg="#ffffff",
                 wraplength=480, justify="left").pack(anchor="w", pady=(0, 4))

        self._cl_template_box = _st.ScrolledText(
            cl_frame, height=7, wrap="word",
            font=("Helvetica", 9), relief="solid", bd=1)
        self._cl_template_box.pack(fill="x")
        saved_cl = load_base_cover_letter()
        if saved_cl:
            self._cl_template_box.insert("1.0", saved_cl)

        cl_templ_btn_row = tk.Frame(cl_frame, bg="#ffffff"); cl_templ_btn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(cl_templ_btn_row, text="💾 Save Template",
                   command=self._save_base_cover_letter).pack(side="left")
        ttk.Button(cl_templ_btn_row, text="🗑 Clear",
                   command=lambda: (self._cl_template_box.delete("1.0", "end"),
                                    save_base_cover_letter(""),
                                    self._cl_template_status_var.set(""))).pack(side="left", padx=6)
        self._cl_template_status_var = tk.StringVar(value="✓ Template saved" if saved_cl else "")
        tk.Label(cl_frame, textvariable=self._cl_template_status_var,
                 font=("Helvetica", 8), fg="#2a9d2a", bg="#ffffff").pack(anchor="w", pady=(2, 0))

        # ── Generate buttons ───────────────────────────────────────────────
        act_header = tk.Frame(right_inner, bg="#ffffff")
        act_header.pack(fill="x", padx=10, pady=(10, 2))
        tk.Label(act_header, text="Generate",
                 font=("Helvetica", 9, "bold"),
                 fg="#1d2d44", bg="#ffffff").pack(side="left")
        act_info = tk.Label(act_header, text="ⓘ",
                            font=("Helvetica", 10, "bold"),
                            fg="#3a7bd5", bg="#ffffff", cursor="hand2")
        act_info.pack(side="left", padx=(4, 0))
        act_info.bind("<Button-1>", lambda e: messagebox.showinfo(
            "Generate Buttons",
            "• 'Copy CV Prompt' → copies a ready-to-paste prompt that\n"
            "  asks an AI to rewrite your CV for this role\n\n"
            "• 'Copy Cover Letter Prompt' → copies a prompt that asks\n"
            "  an AI to write a personalised cover letter\n\n"
            "Paste the copied prompt into the 🤖 AI Assistant tab,\n"
            "send it, then copy the AI's reply and paste it into the\n"
            "Result box below using 'Paste CV' / 'Paste Cover Letter'.\n\n"
            "Requires: CV saved + JD confirmed"))
        act_frame = tk.Frame(right_inner, bg="#ffffff", padx=10, pady=4)
        act_frame.pack(fill="x", pady=(0, 4))

        act_row = tk.Frame(act_frame, bg="#ffffff"); act_row.pack(fill="x")
        self._copy_cv_prompt_btn = ttk.Button(
            act_row, text="📋 Copy CV Prompt",
            command=lambda: self._copy_tailor_prompt("cv"))
        self._copy_cv_prompt_btn.pack(side="left", padx=(0, 6))
        self._copy_cl_prompt_btn = ttk.Button(
            act_row, text="📋 Copy Cover Letter Prompt",
            command=lambda: self._copy_tailor_prompt("cl"))
        self._copy_cl_prompt_btn.pack(side="left", padx=(0, 6))
        self._open_ai_btn = ttk.Button(
            act_row, text="🤖 Open AI Assistant",
            command=lambda: self.tabs.select(self.ai_assistant_tab))
        self._open_ai_btn.pack(side="left")

        self._tailor_progress_var = tk.StringVar(value="")
        tk.Label(act_frame, textvariable=self._tailor_progress_var,
                 font=("Helvetica", 9, "italic"), fg="#e07b00",
                 bg="#ffffff").pack(anchor="w", pady=(4, 0))

        # ── Result area ────────────────────────────────────────────────────
        res_header = tk.Frame(right_inner, bg="#ffffff")
        res_header.pack(fill="x", padx=10, pady=(10, 2))
        tk.Label(res_header, text="Result",
                 font=("Helvetica", 9, "bold"),
                 fg="#1d2d44", bg="#ffffff").pack(side="left")
        res_info = tk.Label(res_header, text="ⓘ",
                            font=("Helvetica", 10, "bold"),
                            fg="#3a7bd5", bg="#ffffff", cursor="hand2")
        res_info.pack(side="left", padx=(4, 0))
        res_info.bind("<Button-1>", lambda e: messagebox.showinfo(
            "Result Area",
            "1. Get the AI's reply in the 🤖 AI Assistant tab and\n"
            "   copy it (select all, Ctrl+C).\n\n"
            "2. Switch between CV / Cover Letter tabs above, then\n"
            "   click '📥 Paste CV' or '📥 Paste Cover Letter' to\n"
            "   bring the reply in from your clipboard.\n\n"
            "3. Click '📋 Copy' to put the result back on your\n"
            "   clipboard for your job application.\n\n"
            "TIP: You can edit the result and re-copy as needed."))
        res_frame = tk.Frame(right_inner, bg="#ffffff", padx=10, pady=4)
        res_frame.pack(fill="both", expand=True, pady=(0, 10))

        res_toolbar = tk.Frame(res_frame, bg="#ffffff"); res_toolbar.pack(fill="x", pady=(0, 4))
        self._result_tab_var = tk.StringVar(value="cv")
        ttk.Radiobutton(res_toolbar, text="CV", variable=self._result_tab_var,
                        value="cv", command=self._switch_result_view).pack(side="left")
        ttk.Radiobutton(res_toolbar, text="Cover Letter", variable=self._result_tab_var,
                        value="cl", command=self._switch_result_view).pack(side="left", padx=8)
        ttk.Button(res_toolbar, text="📥 Paste",
                   command=self._paste_tailor_result).pack(side="right", padx=(4, 0))
        ttk.Button(res_toolbar, text="📋 Copy",
                   command=self._copy_result).pack(side="right")

        self._result_box = _st.ScrolledText(
            res_frame, height=10, wrap="word",
            font=("Courier", 9), relief="solid", bd=1)
        self._result_box.pack(fill="both", expand=True)

        # Internal result storage
        self._tailor_cv_result = ""
        self._tailor_cl_result = ""

    # ── Tailor helpers ─────────────────────────────────────────────────────────


    def _on_jd_changed(self, _=None):
        self._jd_text_box.edit_modified(False)

    def _confirm_jd(self):
        text = self._jd_text_box.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Empty JD", "Paste a job description first.")
            return
        self._tailor_jd_text = text
        words = len(text.split())
        self._tailor_jd_status_var.set(f"✓ JD ready ({words} words)")

    def _fetch_jd_from_url(self):
        url = self._tailor_url_var.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Enter a job post URL first.")
            return
        self._fetch_btn.config(state="disabled")
        self._tailor_jd_status_var.set("⏳ Fetching…")

        def _worker():
            result = fetch_jd_from_url(url)
            def _done():
                self._fetch_btn.config(state="normal")
                if result["error"]:
                    self._tailor_jd_status_var.set(f"❌ {result['error']}")
                else:
                    text = result["text"]
                    self._tailor_jd_text = text
                    self._update_jd_preview(text)
                    words = len(text.split())
                    self._tailor_jd_status_var.set(f"✓ Fetched ({words} words) — click 'Use this JD' to confirm")
            self.after(0, _done)

        import threading as _t
        _t.Thread(target=_worker, daemon=True).start()

    def _save_cv_text(self):
        text = self._cv_text_box.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Empty CV", "Paste your CV first.")
            return
        save_cv(text)
        self._cv_status_var.set("✓ CV saved")

    def _save_base_cover_letter(self):
        text = self._cl_template_box.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Empty", "Paste a cover letter template first.")
            return
        save_base_cover_letter(text)
        self._cl_template_status_var.set("✓ Template saved")

    def _show_tailor_help(self):
        """Show a full workflow guide for the AI Tailor tab."""
        messagebox.showinfo(
            "AI Tailor — How to Use",
            "STEPS (left → right):\n\n"
            "1. JOB DESCRIPTION (left column)\n"
            "   • Enter a job URL and click 'Fetch JD', OR\n"
            "   • Paste the full JD text below and click 'Use this JD'\n\n"
            "2. MY CV (right column)\n"
            "   • Paste your current CV here once — it's saved for all\n"
            "     future tailoring sessions (stored locally).\n\n"
            "3. BASE COVER LETTER (right column — optional)\n"
            "   • Paste an example cover letter you like as a template.\n"
            "     AI will match its style/tone when generating new ones.\n\n"
            "4. COPY A PROMPT (right column)\n"
            "   • 'Copy CV Prompt' or 'Copy Cover Letter Prompt' copies a\n"
            "     ready-to-use prompt to your clipboard.\n\n"
            "5. AI ASSISTANT TAB\n"
            "   • Click '🤖 Open AI Assistant', paste the prompt into the\n"
            "     chat, send it, and copy the AI's reply.\n\n"
            "6. RESULT (below)\n"
            "   • Switch between CV / Cover Letter, click '📥 Paste' to\n"
            "     bring in the AI's reply, edit if needed, then '📋 Copy'\n"
            "     to use it in your application.\n\n"
            "TIP: Paste your CV once → select jobs from Search tab →\n"
            "     click '📄 Tailor CV & Letter' to auto-fill the JD."
        )

    def _make_section_header(self, parent, title, tooltip_text="", bg="#ffffff"):
        """Create a section header row with an optional ⓘ help button."""
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", pady=(0, 2))
        tk.Label(row, text=title,
                 font=("Helvetica", 9, "bold"),
                 fg="#1d2d44", bg=bg).pack(side="left")
        if tooltip_text:
            info = tk.Label(row, text="ⓘ",
                            font=("Helvetica", 10, "bold"),
                            fg="#3a7bd5", bg=bg, cursor="hand2")
            info.pack(side="left", padx=(4, 0))
            info.bind("<Button-1>", lambda e, t=tooltip_text:
                      messagebox.showinfo(title, t))
        return row

    def _copy_tailor_prompt(self, mode: str):
        """mode: 'cv' or 'cl'. Builds the prompt and copies it to clipboard."""
        jd = self._tailor_jd_text.strip()
        if not jd:
            # Try reading from the text box directly
            jd = self._jd_text_box.get("1.0", "end").strip()
            self._tailor_jd_text = jd

        if not jd:
            messagebox.showwarning(
                "No Job Description",
                "Fetch or paste a job description first, then click 'Use this JD'.")
            return

        cv_text = self._cv_text_box.get("1.0", "end").strip()
        if not cv_text:
            messagebox.showwarning(
                "No CV",
                "Paste your CV in the 'My CV' box and save it first.")
            return

        if mode == "cv":
            prompt = build_cv_prompt(cv_text, jd)
            label = "CV"
        else:
            prompt = build_cover_letter_prompt(
                cv_text, jd,
                base_letter=self._cl_template_box.get("1.0", "end").strip(),
            )
            label = "Cover Letter"

        self.clipboard_clear()
        self.clipboard_append(prompt)
        self._result_tab_var.set(mode)
        self._tailor_progress_var.set(
            f"✓ {label} prompt copied! Open the AI Assistant tab, paste, "
            f"send, copy the reply, then click '📥 Paste' below.")

    def _paste_tailor_result(self):
        """Paste the AI's reply (from clipboard) into the active result box."""
        try:
            pasted = self.clipboard_get()
        except Exception:
            pasted = ""
        parsed = parse_text_result(pasted)
        if parsed.get("error"):
            self._tailor_progress_var.set(f"❌ {parsed['error']}")
            return
        text = parsed["text"]
        mode = self._result_tab_var.get()
        if mode == "cv":
            self._tailor_cv_result = text
        else:
            self._tailor_cl_result = text
        self._switch_result_view()
        label = "CV" if mode == "cv" else "Cover Letter"
        self._tailor_progress_var.set(f"✓ {label} pasted — edit if needed, then '📋 Copy'")

    def _switch_result_view(self):
        mode = self._result_tab_var.get()
        text = self._tailor_cv_result if mode == "cv" else self._tailor_cl_result
        self._result_box.delete("1.0", "end")
        self._result_box.insert("1.0", text or "(nothing pasted yet)")

    def _copy_result(self):
        mode = self._result_tab_var.get()
        # Use whatever is currently in the box (the user may have edited it).
        text = self._result_box.get("1.0", "end").strip()
        if mode == "cv":
            self._tailor_cv_result = text
        else:
            self._tailor_cl_result = text
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self._tailor_progress_var.set("✓ Copied to clipboard!")

    # ── AI Assistant tab ──────────────────────────────────────────────────────

    def _build_ai_assistant_tab(self):
        outer = tk.Frame(self.ai_assistant_tab, bg="#f0f2f5", padx=14, pady=10)
        outer.pack(fill="both", expand=True)

        hdr = tk.Frame(outer, bg="#f0f2f5")
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(hdr, text=f"🤖  {_('AI Assistant')}",
                 font=("Helvetica", 13, "bold"),
                 fg="#1d2d44", bg="#f0f2f5").pack(side="left")
        tk.Label(hdr,
                 text=f"  ·  {_('Chat with a free web AI — no API key needed')}",
                 font=("Helvetica", 9), fg="#8fa8c8",
                 bg="#f0f2f5").pack(side="left")
        help_btn = ttk.Button(hdr, text=f"📖 {_('How to use')}",
                              command=self._show_ai_assistant_help)
        help_btn.pack(side="right")

        # ── Open AI chat ──────────────────────────────────────────────────
        chat_frame = tk.Frame(outer, bg="#ffffff", padx=10, pady=8)
        chat_frame.pack(fill="x", pady=(0, 8))
        tk.Label(chat_frame, text=_("Open AI Chat"),
                 font=("Helvetica", 9, "bold"),
                 fg="#1d2d44", bg="#ffffff").pack(anchor="w")
        tk.Label(chat_frame,
                 text=_("Opens the AI chat in your normal web browser — uses "
                        "whatever account you're already signed into there. "
                        "Paste a prompt from the AI Tailor tab or Search tab, "
                        "send it, then copy the reply back."),
                 font=("Helvetica", 8), fg="#888", bg="#ffffff",
                 wraplength=900, justify="left").pack(anchor="w", pady=(2, 6))

        site_row = tk.Frame(chat_frame, bg="#ffffff")
        site_row.pack(fill="x")
        tk.Label(site_row, text=_("Site:"), font=("Helvetica", 9),
                 bg="#ffffff").pack(side="left")
        self._ai_site_var = tk.StringVar(value=DEFAULT_SITE)
        ttk.Combobox(site_row, textvariable=self._ai_site_var,
                     values=list(AI_SITES.keys()), width=14,
                     state="readonly").pack(side="left", padx=(6, 8))
        ttk.Button(site_row, text=f"🌐 {_('Open AI Chat')}",
                   command=self._open_ai_webview).pack(side="left")
        self._ai_webview_status_var = tk.StringVar(value="")
        tk.Label(site_row, textvariable=self._ai_webview_status_var,
                 font=("Helvetica", 8, "italic"), fg="#3a7bd5",
                 bg="#ffffff").pack(side="left", padx=(10, 0))

        # ── Eligibility Rating ────────────────────────────────────────────
        elig_frame = tk.Frame(outer, bg="#ffffff", padx=10, pady=8)
        elig_frame.pack(fill="x", pady=(0, 8))
        tk.Label(elig_frame, text=_("Eligibility Rating"),
                 font=("Helvetica", 9, "bold"),
                 fg="#1d2d44", bg="#ffffff").pack(anchor="w")
        tk.Label(elig_frame,
                 text=_("From the Search tab: select a job, click '📋 Copy Rating Prompt', "
                        "paste it into the AI chat above, then come back, copy the "
                        "reply and click '📥 Paste AI Result' in the Search tab."),
                 font=("Helvetica", 8), fg="#888", bg="#ffffff",
                 wraplength=900, justify="left").pack(anchor="w", pady=(2, 0))
        ttk.Button(elig_frame, text=_("Go to Search tab"),
                   command=lambda: self.tabs.select(self.search_tab)
                   ).pack(anchor="w", pady=(6, 0))

        # ── CV Tailoring & Cover Letter ──────────────────────────────────
        cvcl_frame = tk.Frame(outer, bg="#ffffff", padx=10, pady=8)
        cvcl_frame.pack(fill="x", pady=(0, 8))
        tk.Label(cvcl_frame, text=_("CV Tailoring & Cover Letter"),
                 font=("Helvetica", 9, "bold"),
                 fg="#1d2d44", bg="#ffffff").pack(anchor="w")
        tk.Label(cvcl_frame,
                 text=_("From the ✨ AI Tailor tab: confirm a job description, then click "
                        "'📋 Copy CV Prompt' or '📋 Copy Cover Letter Prompt'. Paste it into "
                        "the AI chat above, then copy the reply back into the Result box "
                        "with '📥 Paste'."),
                 font=("Helvetica", 8), fg="#888", bg="#ffffff",
                 wraplength=900, justify="left").pack(anchor="w", pady=(2, 0))
        ttk.Button(cvcl_frame, text=_("Go to AI Tailor tab"),
                   command=lambda: self.tabs.select(self.tailor_tab)
                   ).pack(anchor="w", pady=(6, 0))

    def _open_ai_webview(self):
        site = self._ai_site_var.get().strip() or DEFAULT_SITE
        self._ai_webview_status_var.set(_("⏳ Opening {site}…").format(site=site))
        self.update_idletasks()
        try:
            self._ai_webview.open(site)
            self._ai_webview_status_var.set(
                _("✓ Opened {site} in your browser — sign in there if needed.")
                .format(site=site))
        except Exception as exc:
            logger.exception("Failed to open AI chat in browser")
            self._ai_webview_status_var.set(f"❌ {exc}")
            messagebox.showerror(
                _("Could not open AI chat"),
                _("Failed to open {site} in your browser:\n\n{error}\n\n"
                  "Make sure a default web browser is set up on this "
                  "computer.").format(site=site, error=exc))

    def _show_ai_assistant_help(self):
        messagebox.showinfo(
            _("AI Assistant — How to Use"),
            _("This tab opens a normal web AI chat (ChatGPT, Gemini, Claude, "
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
              "web chat, just like using it in a browser tab.")
        )

    # ── Dashboard tab ─────────────────────────────────────────────────────────

    def _build_dashboard_tab(self):
        outer = tk.Frame(self.dashboard_tab, bg="#f0f2f5",
                         padx=14, pady=12)
        outer.pack(fill="both", expand=True)

        # BUGFIX (2024-Q4): previous version packed the cards row with
        # `expand=True, fill="x"` and then a `Refresh` button with anchor="w"
        # but no fill. That left a thin horizontal empty strip between the
        # cards and the section headers because the rows of cards had
        # growable expand children that pushed the section below them
        # down by exactly the height of an empty row. We now:
        #   1. Restrict the cards row to its natural height (no fill on x,
        #      so it sizes to the cards inside it).
        #   2. Place the Refresh button in the SAME row, anchored right,
        #      so there's no orphan button row creating a phantom line.
        #   3. Make the headers + trees section explicitly fill="both" and
        #      expand=True, so the section below the cards takes all the
        #      remaining vertical space.
        cards_row = tk.Frame(outer, bg="#f0f2f5", highlightthickness=0, bd=0)
        cards_row.pack(fill="x", pady=(0, 8), anchor="n")
        self._stat_labels = {}
        # left half of the row: the stat cards
        cards_left = tk.Frame(cards_row, bg="#f0f2f5", highlightthickness=0, bd=0)
        cards_left.pack(side="left", fill="both", expand=True)
        for key, title in [
            ("companies",         "Companies"),
            ("verified_jobs",     "Verified Jobs"),
            ("sponsored_jobs",    "Sponsored"),
            ("remote_jobs",       "Remote"),
            ("eu_blue_card_jobs", "EU Blue Card"),
            ("recent_jobs",       "New this week"),
        ]:
            card = tk.Frame(cards_left, bg="#ffffff",
                            padx=16, pady=10, relief="flat",
                            highlightthickness=0, bd=0)
            card.pack(side="left", expand=True, fill="x", padx=(0, 8))
            num = tk.Label(card, text="—",
                           font=("Helvetica", 22, "bold"),
                           fg="#3a7bd5", bg="#ffffff")
            num.pack()
            tk.Label(card, text=title,
                     font=("Helvetica", 8), fg="#888",
                     bg="#ffffff").pack()
            self._stat_labels[key] = num
        # right half of the row: the Refresh button, vertically centered
        ttk.Button(cards_row, text="↻  Refresh",
                   command=self.load_dashboard).pack(side="right", padx=0, pady=0)

        # Section: tables take all remaining vertical space
        cols_frame = tk.Frame(outer, bg="#f0f2f5",
                              highlightthickness=0, bd=0)
        cols_frame.pack(fill="both", expand=True, pady=(4, 0))
        left  = tk.Frame(cols_frame, bg="#f0f2f5",
                         highlightthickness=0, bd=0)
        right = tk.Frame(cols_frame, bg="#f0f2f5",
                         highlightthickness=0, bd=0)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right.pack(side="left", fill="both", expand=True)

        # BUG-3 fix: every nested widget gets highlightthickness=0 + bd=0
        # and the section header label uses pady=(0, 4) (no top padding)
        # so the prior phantom horizontal line / gap is gone.
        hdr_left = tk.Frame(left, bg="#f0f2f5",
                            highlightthickness=0, bd=0)
        hdr_left.pack(fill="x", pady=(0, 4))
        tk.Label(hdr_left, text="Top companies by sponsorship score",
                 font=("Helvetica", 10, "bold"),
                 fg="#1d2d44", bg="#f0f2f5",
                 highlightthickness=0, bd=0).pack(side="left")
        co_cols = ("Company", "Country", "Jobs", "Sponsor")
        self.co_tree = ttk.Treeview(left, columns=co_cols,
                                    show="headings", height=12)
        for c in co_cols:
            self.co_tree.heading(c, text=c)
            self.co_tree.column(c, width=150, anchor="w")
        cosb = ttk.Scrollbar(left, orient="vertical",
                             command=self.co_tree.yview)
        self.co_tree.configure(yscroll=cosb.set)
        self.co_tree.pack(side="left", fill="both",
                          expand=True, pady=(4, 0))
        cosb.pack(side="right", fill="y", pady=(4, 0))

        hdr_right = tk.Frame(right, bg="#f0f2f5",
                             highlightthickness=0, bd=0)
        hdr_right.pack(fill="x", pady=(0, 4))
        tk.Label(hdr_right, text="Jobs by country",
                 font=("Helvetica", 10, "bold"),
                 fg="#1d2d44", bg="#f0f2f5",
                 highlightthickness=0, bd=0).pack(side="left")
        ct_cols = ("Country", "Jobs")
        self.ct_tree = ttk.Treeview(right, columns=ct_cols,
                                    show="headings", height=12)
        for c in ct_cols:
            self.ct_tree.heading(c, text=c)
            self.ct_tree.column(c,
                width=200 if c == "Country" else 80, anchor="w")
        ctsb = ttk.Scrollbar(right, orient="vertical",
                             command=self.ct_tree.yview)
        self.ct_tree.configure(yscroll=ctsb.set)
        self.ct_tree.pack(side="left", fill="both",
                          expand=True, pady=(4, 0))
        ctsb.pack(side="right", fill="y", pady=(4, 0))

    # ── Applications tab ──────────────────────────────────────────────────────

    def _build_applications_tab(self):
        outer = tk.Frame(self.applications_tab, bg="#f0f2f5",
                         padx=14, pady=12)
        outer.pack(fill="both", expand=True)

        # FIX-2: removed the blue info-box that appeared above "Saved applications"
        # header and created an extra divider line in the layout. The right-click
        # hint is redundant now that the context menu is properly scoped.

        tb = tk.Frame(outer, bg="#f0f2f5")
        tb.pack(fill="x", pady=(0, 6))
        tk.Label(tb, text="Saved applications",
                 font=("Helvetica", 11, "bold"),
                 fg="#1d2d44", bg="#f0f2f5").pack(side="left")
        ttk.Button(tb, text="↻ Refresh",
                   command=self.load_applications).pack(side="right")
        ttk.Button(tb, text="Remove Selected",
                   command=self._remove_application).pack(side="right",
                                                          padx=6)

        app_cols = ("Company", "Title", "Status", "Saved on", "URL")
        app_w = {"Company": 170, "Title": 240,
                 "Status": 90, "Saved on": 130, "URL": 0}
        list_frame = tk.Frame(outer)
        list_frame.pack(fill="both", expand=True)

        self.app_tree = ttk.Treeview(list_frame, columns=app_cols,
                                     show="headings", height=16,
                                     selectmode="browse")
        for c in app_cols:
            self.app_tree.heading(c, text=c)
            self.app_tree.column(c, width=app_w.get(c, 120),
                                 anchor="w", stretch=(c == "URL"))
        asb = ttk.Scrollbar(list_frame, orient="vertical",
                            command=self.app_tree.yview)
        self.app_tree.configure(yscroll=asb.set)
        self.app_tree.pack(side="left", fill="both", expand=True)
        asb.pack(side="right", fill="y")
        self.app_tree.bind("<<TreeviewSelect>>",
                           self._on_app_select)

        self._form_frame = tk.LabelFrame(
            outer, text=" Edit selected ",
            bg="#ffffff", font=("Helvetica", 9),
            fg="#888", padx=10, pady=8)

        self.app_status  = tk.StringVar(value="saved")
        self.app_notes   = tk.StringVar()
        self._editing_url = None

        form_row = tk.Frame(self._form_frame, bg="#ffffff")
        form_row.pack(fill="x")
        tk.Label(form_row, text="Status:", font=("Helvetica", 9),
                 bg="#ffffff").pack(side="left")
        ttk.Combobox(form_row, textvariable=self.app_status,
                     values=["saved", "applied", "interview",
                             "offer", "rejected"],
                     state="readonly",
                     width=14).pack(side="left", padx=(4, 16))
        tk.Label(form_row, text="Notes:", font=("Helvetica", 9),
                 bg="#ffffff").pack(side="left")
        ttk.Entry(form_row, textvariable=self.app_notes,
                  width=36).pack(side="left", padx=4)
        ttk.Button(form_row, text="Save",
                   command=self._update_application).pack(side="left",
                                                          padx=8)
        ttk.Button(form_row, text="Cancel",
                   command=self._hide_form).pack(side="left")

    def _on_app_select(self, _=None):
        sel = self.app_tree.selection()
        if not sel:
            return
        v = self.app_tree.item(sel[0])["values"]
        self._editing_url = str(v[-1])
        self.app_status.set(str(v[2]))
        self.app_notes.set("")
        self._form_frame.pack(fill="x", pady=(8, 0))

    def _hide_form(self):
        self._form_frame.pack_forget()
        self._editing_url = None

    def _update_application(self):
        if not self._editing_url:
            return
        sel = self.app_tree.selection()
        if not sel:
            return
        v = self.app_tree.item(sel[0])["values"]
        upsert_application(
            DB_PATH,
            job_url=self._editing_url,
            company=str(v[0]),
            title=str(v[1]),
            status=self.app_status.get(),
            notes=self.app_notes.get().strip(),
        )
        self.load_applications()
        self._hide_form()

    def _remove_application(self):
        sel = self.app_tree.selection()
        if not sel:
            messagebox.showinfo("Select a row",
                                "Click a row first, then click Remove.")
            return
        v = self.app_tree.item(sel[0])["values"]
        if messagebox.askyesno(
            "Remove",
            f"Remove  {v[1]}  at  {v[0]}?"
        ):
            delete_application(DB_PATH, str(v[-1]))
            self._hide_form()
            self.load_applications()

    # ── ATS Health tab ────────────────────────────────────────────────────────

    def _build_health_tab(self):
        outer = tk.Frame(self.health_tab, bg="#f0f2f5",
                         padx=14, pady=12)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="ATS Connector Health",
                 font=("Helvetica", 11, "bold"),
                 fg="#1d2d44", bg="#f0f2f5").pack(anchor="w")
        tk.Label(outer,
                 text="Success/failure rates per connector after each scan.",
                 font=("Helvetica", 9), fg="#888",
                 bg="#f0f2f5").pack(anchor="w", pady=(0, 4))

        # FIX-4: add explanation that data is populated by running a scan
        self._health_note_var = tk.StringVar(value="")
        tk.Label(outer, textvariable=self._health_note_var,
                 font=("Helvetica", 8, "italic"), fg="#e07b00",
                 bg="#f0f2f5").pack(anchor="w", pady=(0, 4))

        ttk.Button(outer, text="↻ Refresh",
                   command=self.load_health).pack(anchor="w",
                                                  pady=(0, 8))
        h_cols = ("ATS", "Success", "Failure", "Rate %",
                  "Avg ms", "Last success", "Last failure")
        h_widths = {"ATS": 140, "Success": 70, "Failure": 70,
                    "Rate %": 70, "Avg ms": 70,
                    "Last success": 160, "Last failure": 160}
        hf = tk.Frame(outer)
        hf.pack(fill="both", expand=True)
        self.h_tree = ttk.Treeview(hf, columns=h_cols, show="headings")
        for c in h_cols:
            self.h_tree.heading(c, text=c)
            self.h_tree.column(c, width=h_widths.get(c, 120), anchor="w")
        hsb = ttk.Scrollbar(hf, orient="vertical",
                            command=self.h_tree.yview)
        self.h_tree.configure(yscroll=hsb.set)
        self.h_tree.pack(side="left", fill="both", expand=True)
        hsb.pack(side="right", fill="y")

    # ── Tools tab ─────────────────────────────────────────────────────────────

    def _build_tools_tab(self):
        # Tools tab is content-heavy (3 prompt editors) — use a canvas+scrollbar
        canvas = tk.Canvas(self.tools_tab, bg="#f0f2f5", highlightthickness=0)
        vsb = ttk.Scrollbar(self.tools_tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        outer = tk.Frame(canvas, bg="#f0f2f5", padx=14, pady=12)
        win_id = canvas.create_window((0, 0), window=outer, anchor="nw")

        def _on_frame_configure(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def _on_canvas_configure(e):
            canvas.itemconfig(win_id, width=e.width)
        outer.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def section(title, desc=""):
            f = tk.LabelFrame(outer, text=f"  {title}  ",
                               bg="#ffffff", pady=10, padx=12,
                               font=("Helvetica", 10, "bold"), fg="#1d2d44",
                               relief="groove", bd=1)
            f.pack(fill="x", pady=(0, 10))
            if desc:
                tk.Label(f, text=desc, font=("Helvetica", 8),
                         fg="#888", bg="#ffffff",
                         wraplength=900, justify="left"
                         ).pack(anchor="w", pady=(0, 6))
            return f

        # ── Scanner ───────────────────────────────────────────────────────
        sc = section("Scanner",
                     "Manual scan only. SponsorScout does not run periodic background scans.")
        sr = tk.Frame(sc, bg="#ffffff"); sr.pack(fill="x")
        self.scan_status = tk.StringVar(value="idle")
        tk.Label(sr, text="Status:", font=("Helvetica", 9),
                 fg="#888", bg="#ffffff").pack(side="left")
        tk.Label(sr, textvariable=self.scan_status,
                 font=("Helvetica", 9, "bold"),
                 fg="#3a7bd5", bg="#ffffff").pack(side="left", padx=6)
        ttk.Button(sr, text="▶  Scan Now",
                   command=self._run_scan_now).pack(side="left", padx=(20, 4))

        # Live progress log — shows per-company results streaming in
        log_hdr = tk.Frame(sc, bg="#ffffff"); log_hdr.pack(fill="x", pady=(8, 0))
        tk.Label(log_hdr, text="Scan Log:", font=("Helvetica", 8, "bold"),
                 fg="#555", bg="#ffffff").pack(side="left")
        ttk.Button(log_hdr, text="Clear",
                   command=self._clear_scan_log).pack(side="right")
        self._scan_log = tk.Text(sc, height=7, wrap="word",
                                  font=("Courier", 8), state="disabled",
                                  relief="solid", bd=1, bg="#f8f9fa")
        self._scan_log.pack(fill="x", pady=(2, 0))

        # ── Data Quality ──────────────────────────────────────────────────
        dq = section("Data Quality",
                     "Remove duplicate jobs and companies from the database.")
        ttk.Button(dq, text="Run Dedup",
                   command=self._run_dedup).pack(anchor="w")

        # ── AI Prompts ────────────────────────────────────────────────────
        ai = section("AI Prompts",
                     "Prompts used by the 🤖 AI Assistant tab for job rating, "
                     "eligibility (uses your CV from AI Tailor tab), and document generation.")

        tk.Label(ai, text="Job Rating & Eligibility Prompt  (AI uses this + your CV to score each job):",
                 font=("Helvetica", 9), bg="#ffffff",
                 fg="#555").pack(anchor="w", pady=(4, 2))
        self._prompt_text = scrolledtext.ScrolledText(
            ai, height=8, wrap="word", font=("Courier", 8),
            relief="solid", bd=1)
        self._prompt_text.pack(fill="x")
        self._prompt_text.insert("1.0", load_prompt())

        pbtn_row = tk.Frame(ai, bg="#ffffff"); pbtn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(pbtn_row, text="Save Prompt",
                   command=self._save_prompt).pack(side="left")
        ttk.Button(pbtn_row, text="Reset to Default",
                   command=self._reset_prompt).pack(side="left", padx=8)

        # ── CV Tailoring Prompt ───────────────────────────────────────────
        tk.Label(ai, text="CV Tailoring Prompt  (how AI rewrites your CV to match a JD):",
                 font=("Helvetica", 9), bg="#ffffff",
                 fg="#555").pack(anchor="w", pady=(10, 2))
        self._cv_prompt_text = scrolledtext.ScrolledText(
            ai, height=6, wrap="word", font=("Courier", 8),
            relief="solid", bd=1)
        self._cv_prompt_text.pack(fill="x")
        self._cv_prompt_text.insert("1.0", load_cv_prompt())
        cv_pbtn_row = tk.Frame(ai, bg="#ffffff"); cv_pbtn_row.pack(fill="x", pady=(4, 0))
        ttk.Button(cv_pbtn_row, text="Save CV Prompt",
                   command=self._save_cv_prompt_settings).pack(side="left")
        ttk.Button(cv_pbtn_row, text="Reset",
                   command=self._reset_cv_prompt).pack(side="left", padx=8)

        # ── Cover Letter Prompt ───────────────────────────────────────────
        tk.Label(ai, text="Cover / Motivation Letter Prompt  (for EU-based roles — personalised from your CV + JD):",
                 font=("Helvetica", 9), bg="#ffffff",
                 fg="#555").pack(anchor="w", pady=(10, 2))
        self._cl_prompt_text = scrolledtext.ScrolledText(
            ai, height=6, wrap="word", font=("Courier", 8),
            relief="solid", bd=1)
        self._cl_prompt_text.pack(fill="x")
        self._cl_prompt_text.insert("1.0", load_cl_prompt())
        cl_pbtn_row = tk.Frame(ai, bg="#ffffff"); cl_pbtn_row.pack(fill="x", pady=(4, 0))
        ttk.Button(cl_pbtn_row, text="Save Letter Prompt",
                   command=self._save_cl_prompt_settings).pack(side="left")
        ttk.Button(cl_pbtn_row, text="Reset",
                   command=self._reset_cl_prompt).pack(side="left", padx=8)

        # ── Company Discovery ─────────────────────────────────────────────
        cd = section("Company Discovery",
                     "Probes official career pages first, then ATS boards for matching companies. "
                     "Use role keywords: 'analyst', 'engineer', 'backend', 'data'.")
        dr = tk.Frame(cd, bg="#ffffff"); dr.pack(fill="x", pady=(0, 6))
        self.disc_q = tk.StringVar(value="software engineer")
        self.disc_c = tk.StringVar(value="Germany")
        tk.Label(dr, text="Query:", font=("Helvetica", 9),
                 bg="#ffffff").pack(side="left")
        ttk.Entry(dr, textvariable=self.disc_q,
                  width=28).pack(side="left", padx=(4, 10))
        tk.Label(dr, text="Country:", font=("Helvetica", 9),
                 bg="#ffffff").pack(side="left")
        ttk.Entry(dr, textvariable=self.disc_c,
                  width=14).pack(side="left", padx=(4, 10))
        ttk.Button(dr, text="Discover",
                   command=self._run_discovery).pack(side="left")
        self.disc_log = tk.Text(cd, height=5, wrap="word",
                                font=("Helvetica", 9),
                                state="disabled", relief="flat",
                                bg="#f8f9fa")
        self.disc_log.pack(fill="x")

        # ── Freshness ─────────────────────────────────────────────────────
        fv = section("Freshness Check",
                     "Verify jobs still exist online — auto-expires dead links.")
        fr = tk.Frame(fv, bg="#ffffff"); fr.pack(fill="x")
        self.verify_n = tk.IntVar(value=50)
        tk.Label(fr, text="Max jobs:", font=("Helvetica", 9),
                 bg="#ffffff").pack(side="left")
        ttk.Spinbox(fr, from_=5, to=200, increment=5,
                    textvariable=self.verify_n,
                    width=6).pack(side="left", padx=(4, 10))
        ttk.Button(fr, text="Run",
                   command=self._run_freshness).pack(side="left")
        self.fresh_status = tk.StringVar(value="")
        tk.Label(fv, textvariable=self.fresh_status,
                 font=("Helvetica", 9), fg="#888",
                 bg="#ffffff").pack(anchor="w", pady=(4, 0))

    # ── AI prompt actions ──────────────────────────────────────────────────────

    def _save_prompt(self):
        text = self._prompt_text.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Empty", "Prompt cannot be empty.")
            return
        save_prompt(text)
        messagebox.showinfo("Saved", "Custom prompt saved.")

    def _reset_prompt(self):
        if messagebox.askyesno("Reset", "Reset prompt to default?"):
            self._prompt_text.delete("1.0", "end")
            self._prompt_text.insert("1.0", DEFAULT_AI_PROMPT)
            save_prompt(DEFAULT_AI_PROMPT)

    def _save_cv_prompt_settings(self):
        text = self._cv_prompt_text.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Empty", "Prompt cannot be empty.")
            return
        save_cv_prompt(text)
        messagebox.showinfo("Saved", "CV tailoring prompt saved.")

    def _reset_cv_prompt(self):
        if messagebox.askyesno("Reset", "Reset CV tailoring prompt to default?"):
            self._cv_prompt_text.delete("1.0", "end")
            self._cv_prompt_text.insert("1.0", DEFAULT_CV_PROMPT)
            save_cv_prompt(DEFAULT_CV_PROMPT)

    def _save_cl_prompt_settings(self):
        text = self._cl_prompt_text.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Empty", "Prompt cannot be empty.")
            return
        save_cl_prompt(text)
        messagebox.showinfo("Saved", "Cover letter prompt saved.")

    def _reset_cl_prompt(self):
        if messagebox.askyesno("Reset", "Reset cover letter prompt to default?"):
            self._cl_prompt_text.delete("1.0", "end")
            self._cl_prompt_text.insert("1.0", DEFAULT_CL_PROMPT)
            save_cl_prompt(DEFAULT_CL_PROMPT)

    # ── Data loaders ──────────────────────────────────────────────────────────

    def load_results(self):
        try:
            experience_filter = self.experience_var.get()
            sort_by_map = {
                "Best match": "best",
                "Latest": "latest",
                "Sponsored Only": "sponsorship",
            }
            sort_by = sort_by_map.get(self.sort_var.get(), "best")
            rows = search_jobs(
                DB_PATH,
                title=self.title_var.get().strip(),
                company=self.company_var.get().strip(),
                country=self.country_var.get(),
                verified_only=True,
                sponsorship_only=(self.spons_var.get() == "Sponsored Only"),
                active_only=True,
                remote_filter=self.remote_var.get(),
                eu_blue_card_only=self.eu_bc_var.get(),
                relocation_only=self.reloc_var.get(),
                experience_filter=experience_filter,
                sort_by=sort_by,
                objective=normalize_objective(self.objective_var.get()),
            )
        except Exception as exc:
            messagebox.showerror("Search error", str(exc))
            return
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            url = r["url"]
            ai_rating = self._ai_cache.get(url, {}).get("rating", "")
            rating_str = f"{ai_rating}/10" if ai_rating else ""
            self.tree.insert("", "end", values=(
                r["title"], r["company"], r["country"],
                r["location"], r["remote_type"] or "onsite",
                r["sponsorship_score"],
                "✓" if r["eu_blue_card"] else "",
                "✓" if r["has_relocation"] else "",
                rating_str,
                url,
            ))
        n = len(rows)
        self.count_var.set(f"{n} job{'s' if n != 1 else ''} found")

    def load_dashboard(self):
        try:
            stats = get_dashboard_stats(DB_PATH)
            cos   = get_dashboard_top_companies(DB_PATH)
            cts   = get_dashboard_country_counts(DB_PATH)
        except Exception as exc:
            logger.exception("Failed to load dashboard stats")
            self.status_var.set("Dashboard data could not be loaded.")
            return
        for key, lbl in self._stat_labels.items():
            lbl.config(text=str(stats.get(key, 0)))
        self.co_tree.delete(*self.co_tree.get_children())
        for r in cos:
            self.co_tree.insert("", "end", values=(
                r["company"], r["country"],
                r["job_count"], r["max_sponsor"]))
        self.ct_tree.delete(*self.ct_tree.get_children())
        for r in cts:
            self.ct_tree.insert("", "end",
                values=(r["country"], r["count"]))

    def load_applications(self):
        try:
            rows = list_applications(DB_PATH)
        except Exception as exc:
            logger.exception("Failed to load applications")
            return
        self.app_tree.delete(*self.app_tree.get_children())
        for r in rows:
            self.app_tree.insert("", "end", values=(
                r["company"], r["title"], r["status"],
                r["applied_at"] or "", r["job_url"]))

    def load_health(self):
        """Reload the ATS Health table.

        BUG-4 fix: this function used to silently swallow all exceptions with
        a bare `except Exception: pass`, which made the Refresh button appear
        to do nothing if the DB was missing a table or the connector import
        failed. We now:

        1. Surface any error in the health-note label (and the status bar)
           so the user can see why nothing updated.
        2. Pre-populate the ats_health table with every connector defined in
           `sponsorscout.connectors.CONNECTORS` (zero-count rows), so the
           table shows ALL connectors -- not just those seen in past scans.
        3. Show a count in the advisory line (e.g. "10 of 18 connectors
           have been exercised") so the user knows the table is complete.
        4. BUGFIX: previously, if a connector had been DELETED from the
           registry (e.g. it was renamed or removed in a code update), the
           stale row would silently stay in ats_health. We now also
           purge rows whose ats_name is no longer in CONNECTORS, and
           we add a row for any NEW connectors that haven't been seen yet.
        5. BUGFIX: previously, the Refresh button sometimes did not seem
           to update the table because get_dashboard_ats_health used the
           same sqlite3 connection the populate step had already closed.
           We now re-fetch after a fresh open and commit the populate
           changes BEFORE the read.
        """
        last_error: str = ""
        try:
            from sponsorscout.connectors import get_connector_names
            conn = get_connection(DB_PATH)
            # Purge rows for connectors that no longer exist in the registry.
            existing_rows = conn.execute(
                "SELECT ats_name FROM ats_health"
            ).fetchall()
            existing = {r["ats_name"] for r in existing_rows}
            wanted = set(get_connector_names())
            for stale in existing - wanted:
                conn.execute(
                    "DELETE FROM ats_health WHERE ats_name = ?",
                    (stale,),
                )
            # Add rows for any connector that's missing a row.
            for ats_name in wanted:
                if ats_name not in existing:
                    conn.execute(
                        "INSERT INTO ats_health (ats_name) VALUES (?)",
                        (ats_name,),
                    )
            conn.commit()
            conn.close()
        except Exception as exc:
            last_error = f"populate error: {exc}"

        try:
            rows = get_dashboard_ats_health(DB_PATH)
        except Exception as exc:
            self._health_note_var.set(
                f"ERROR  Could not read ats_health: {exc}. "
                "Try restarting the app or running a scan first."
            )
            return

        self.h_tree.delete(*self.h_tree.get_children())
        for r in rows:
            self.h_tree.insert("", "end", values=(
                r["ats_name"], r["success_count"], r["failure_count"],
                f"{r['success_rate']:.0f}%",
                f"{r['avg_response_ms']:.0f}",
                r["last_success"] or "",
                r["last_failure"] or ""))

        # Advisory line — distinguish "no data yet" from "partial data".
        total = len(rows)
        exercised = sum(
            1 for r in rows
            if r["success_count"] > 0 or r["failure_count"] > 0
        )
        if total == 0:
            self._health_note_var.set(
                "⚠ No connectors registered — check the "
                "sponsorscout.connectors import in Tools → log."
            )
        elif exercised == 0:
            self._health_note_var.set(
                f"⚠ No scan data yet — run a scan in the Tools tab to "
                f"populate health metrics for all {total} connectors."
            )
        elif exercised < total:
            self._health_note_var.set(
                f"ℹ {exercised} of {total} connectors have been "
                f"exercised by scans. Run another scan to populate the rest."
            )
        else:
            self._health_note_var.set("")

        if last_error:
            # Don't overwrite the more useful "no data yet" message, but
            # surface the error in the status bar so it's visible.
            self.status_var.set(f"ATS Health refresh warning: {last_error}")
        else:
            self.status_var.set(f"ATS Health refreshed ({exercised}/{total} exercised).")

    # ── Tool actions ──────────────────────────────────────────────────────────

    def _append_scan_log(self, msg: str):
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._scan_log.config(state="normal")
        self._scan_log.insert("end", f"[{ts}]  {msg}\n")
        self._scan_log.see("end")
        self._scan_log.config(state="disabled")

    def _clear_scan_log(self):
        self._scan_log.config(state="normal")
        self._scan_log.delete("1.0", "end")
        self._scan_log.config(state="disabled")

    def _run_scan_now(self):
        self.scan_status.set("running…")
        self.status_var.set("Scanning…")
        self._scanner.run_now()

    def _run_dedup(self):
        try:
            conn = get_connection(DB_PATH)
            jd   = dedup_jobs_in_db(conn)
            cd   = dedup_companies_in_db(conn)
            conn.close()
            messagebox.showinfo(
                "Dedup complete",
                f"Removed {jd} duplicate job(s) and "
                f"{cd} duplicate company entry(ies).")
            self.load_dashboard()
            self.load_results()
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def _log(self, msg: str):
        self.disc_log.config(state="normal")
        self.disc_log.insert("end", msg + "\n")
        self.disc_log.see("end")
        self.disc_log.config(state="disabled")

    def _run_discovery(self):
        q = self.disc_q.get().strip()
        c = self.disc_c.get().strip()
        if not q:
            messagebox.showwarning("Missing", "Enter a search query.")
            return
        self.disc_log.config(state="normal")
        self.disc_log.delete("1.0", "end")
        self.disc_log.config(state="disabled")
        self.status_var.set("Running discovery…")

        def _worker():
            try:
                from sponsorscout.core.discovery_engine import (
                    discover_companies_from_search,
                    auto_register_companies)
                def log(msg):
                    self.after(0, lambda m=msg: self._log(m))
                log(f"Probing ATS boards for '{q}' [{c or 'any'}]…")
                candidates = discover_companies_from_search(q, c, limit=20)
                log(f"Found {len(candidates)} candidate(s).")
                if candidates:
                    conn = get_connection(DB_PATH)
                    reg  = auto_register_companies(conn, candidates, c)
                    conn.close()
                    log(f"Registered {len(reg)} new company(ies):")
                    for co in reg:
                        log(f"  • {co['name']} ({co['ats_type']})")
                else:
                    log("No new companies found.")
                    log("Try: 'analyst', 'backend', 'data engineer'")
                self.after(0, lambda: self.status_var.set("Discovery done."))
                self.after(0, self.load_dashboard)
            except Exception as exc:
                self.after(0, lambda e=exc: self._log(f"Error: {e}"))
                self.after(0, lambda: self.status_var.set("Discovery failed."))

        threading.Thread(target=_worker, daemon=True).start()

    def _run_freshness(self):
        n = self.verify_n.get()
        self.status_var.set(f"Verifying up to {n} jobs…")
        self.fresh_status.set("Running…")

        def _worker():
            try:
                from sponsorscout.core.verification_service import verify_job
                from sponsorscout.core.persistence import upsert_job
                conn = get_connection(DB_PATH)
                try:
                    rows = conn.execute("""
                        SELECT url FROM jobs
                        WHERE verified_active=1 AND is_expired=0
                        AND (last_verified_at IS NULL OR
                             last_verified_at < datetime('now','-7 days'))
                        ORDER BY last_verified_at ASC LIMIT ?""",
                        (n,)).fetchall()
                    expired = checked = 0
                    for row in rows:
                        jr = conn.execute(
                            "SELECT * FROM jobs WHERE url=?",
                            (row["url"],),
                        ).fetchone()
                        if not jr:
                            continue
                        result = verify_job(dict(jr))
                        upsert_job(conn, result)
                        if result.get("is_expired"):
                            expired += 1
                        checked += 1
                finally:
                    conn.close()
                msg = f"Checked {checked} — expired {expired}."
                self.after(0, lambda: self.fresh_status.set(msg))
                self.after(0, lambda: self.status_var.set(
                    "Freshness check done."))
                self.after(0, self.load_results)
            except Exception as exc:
                self.after(0, lambda e=exc:
                           self.fresh_status.set(f"Error: {e}"))
                self.after(0, lambda: self.status_var.set("Failed."))

        threading.Thread(target=_worker, daemon=True).start()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("SponsorScout starting up")
    initialize()
    app = SponsorScoutApp()
    app.mainloop()


if __name__ == "__main__":
    main()
