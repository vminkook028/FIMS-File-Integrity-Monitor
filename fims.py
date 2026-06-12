import os
import hashlib
import json
import csv
import shutil
import smtplib
import threading
import subprocess
import sys
import time
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog

HASH_FILE  = "baseline.json"
REPORT_FILE= "report.json"
QUARANTINE = "quarantine"
IGNORE     = [".log", ".tmp", "__pycache__", ".pyc"]

THEMES = {
    "light": {
        "BG_MAIN":"#F5F6FA","BG_SIDE":"#FFFFFF","BG_TOP":"#FFFFFF",
        "BG_OUTPUT":"#FAFBFC","BG_CARD":"#FFFFFF",
        "BG_BTN":"#F0F2F7","BG_BTN_HOV":"#E4E7F0",
        "BG_PRIMARY":"#0F9E75","BG_PRI_HOV":"#0C8562",
        "FG_TEXT":"#1A2035","FG_MUTED":"#6B7490",
        "FG_ACCENT":"#0F9E75","FG_WHITE":"#FFFFFF",
        "CLR_NEW":"#C47A15","CLR_MOD":"#B03030",
        "CLR_SAFE":"#3B7A0F","CLR_INIT":"#1A6FD4","CLR_BORDER":"#E2E6ED",
    },
    "dark": {
        "BG_MAIN":"#12131A","BG_SIDE":"#1A1C26","BG_TOP":"#1A1C26",
        "BG_OUTPUT":"#0E0F16","BG_CARD":"#1E2030",
        "BG_BTN":"#262840","BG_BTN_HOV":"#32354F",
        "BG_PRIMARY":"#0F9E75","BG_PRI_HOV":"#0C8562",
        "FG_TEXT":"#E2E6F0","FG_MUTED":"#7B82A0",
        "FG_ACCENT":"#0F9E75","FG_WHITE":"#FFFFFF",
        "CLR_NEW":"#D4922A","CLR_MOD":"#C94040",
        "CLR_SAFE":"#4A9A18","CLR_INIT":"#2A84E8","CLR_BORDER":"#2A2D42",
    },
}
current_theme = "light"
def T(k): return THEMES[current_theme][k]

stats         = {"safe":0,"modified":0,"new":0,"init":0}
tracked_files = {"safe":[],"modified":[],"new":[],"init":[]}
watch_active  = False
watch_thread  = None
auto_active   = False
auto_thread   = None
EMAIL_CFG     = {"host":"","port":"587","user":"","password":"","to":""}
TELEGRAM_CFG  = {"token":"","chat_id":""}
SETTINGS_FILE = "fims_settings.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE,"r") as f:
                data=json.load(f)
                TELEGRAM_CFG.update(data.get("telegram",{}))
                EMAIL_CFG.update(data.get("email",{}))
        except: pass

def save_settings():
    with open(SETTINGS_FILE,"w") as f:
        json.dump({"telegram":TELEGRAM_CFG,"email":EMAIL_CFG},f,indent=4)

# ── Core ──────────────────────────────────────────────────
def calculate_hash(fp):
    try:
        with open(fp,"rb") as f: return hashlib.sha256(f.read()).hexdigest()
    except: return None

def load_baseline():
    if os.path.exists(HASH_FILE):
        with open(HASH_FILE,"r") as f: return json.load(f)
    return {}

def save_baseline(data):
    with open(HASH_FILE,"w") as f: json.dump(data,f,indent=4)

def write_report(entry):
    data=[]
    if os.path.exists(REPORT_FILE):
        try:
            with open(REPORT_FILE,"r") as f: data=json.load(f)
        except: data=[]
    data.append(entry)
    with open(REPORT_FILE,"w") as f: json.dump(data,f,indent=4)

def reset_stats():
    for k in stats: stats[k]=0
    for k in tracked_files: tracked_files[k]=[]

def update_metric_cards():
    try:
        lbl_safe.config(text=str(stats["safe"]))
        lbl_mod.config(text=str(stats["modified"]))
        lbl_new.config(text=str(stats["new"]))
        lbl_init.config(text=str(stats["init"]))
    except: pass

# ── Log ───────────────────────────────────────────────────
def log(msg, color="normal"):
    colors={"safe":T("CLR_SAFE"),"modified":T("CLR_MOD"),"new":T("CLR_NEW"),
            "init":T("CLR_INIT"),"normal":T("FG_TEXT"),"muted":T("FG_MUTED"),"watch":T("BG_PRIMARY")}
    ts=datetime.now().strftime("%H:%M:%S")
    try:
        output.config(state=tk.NORMAL)
        output.insert(tk.END,f"  {ts}  ","muted")
        output.insert(tk.END,msg+"\n",color)
        for tag,fg in colors.items(): output.tag_config(tag,foreground=fg)
        output.tag_config("muted",foreground=T("FG_MUTED"),font=("Consolas",9))
        output.config(state=tk.DISABLED)
        output.see(tk.END)
        apply_search_highlight()
    except: pass

def log_sep():
    try:
        output.config(state=tk.NORMAL)
        output.insert(tk.END,"  "+"─"*70+"\n","muted")
        output.config(state=tk.DISABLED)
    except: pass

def clear_log_ui():
    output.config(state=tk.NORMAL)
    output.delete(1.0,tk.END)
    output.config(state=tk.DISABLED)

# ── Search ────────────────────────────────────────────────
def apply_search_highlight(*args):
    try:
        output.tag_remove("highlight","1.0",tk.END)
        q=search_var.get().strip().lower()
        if not q: return
        start="1.0"
        output.config(state=tk.NORMAL)
        while True:
            pos=output.search(q,start,nocase=True,stopindex=tk.END)
            if not pos: break
            end=f"{pos}+{len(q)}c"
            output.tag_add("highlight",pos,end)
            output.tag_config("highlight",background="#FFD966",foreground="#000000")
            start=end
        output.config(state=tk.DISABLED)
    except: pass

# ── Email ─────────────────────────────────────────────────
def send_email_alert(files):
    if not EMAIL_CFG["host"] or not EMAIL_CFG["user"] or not EMAIL_CFG["to"]: return
    try:
        body="FIMS ALERT — Modified files:\n\n"+"".join(f"  • {f}\n" for f in files)+f"\nTime: {datetime.now()}"
        msg=MIMEMultipart()
        msg["From"]=EMAIL_CFG["user"]; msg["To"]=EMAIL_CFG["to"]
        msg["Subject"]=f"[FIMS] {len(files)} file(s) modified!"
        msg.attach(MIMEText(body,"plain"))
        s=smtplib.SMTP(EMAIL_CFG["host"],int(EMAIL_CFG["port"]))
        s.starttls(); s.login(EMAIL_CFG["user"],EMAIL_CFG["password"]); s.send_message(msg); s.quit()
        root.after(0,lambda: log("  ✉  Email alert sent!","init"))
    except Exception as e:
        root.after(0,lambda: log(f"  ✉  Email failed: {e}","modified"))

def open_email_settings():
    win=tk.Toplevel(root); win.title("Email Alert Settings")
    win.configure(bg=T("BG_MAIN")); win.geometry("420x330")
    win.resizable(False,False); win.transient(root); win.grab_set()
    fields=[("SMTP Host","host"),("SMTP Port","port"),("Your Email","user"),("Password","password"),("Recipient","to")]
    entries={}
    for i,(label,key) in enumerate(fields):
        tk.Label(win,text=label,bg=T("BG_MAIN"),fg=T("FG_TEXT"),font=("Segoe UI",10)).grid(row=i,column=0,padx=20,pady=8,sticky="w")
        e=tk.Entry(win,font=("Consolas",10),width=28,bg=T("BG_CARD"),fg=T("FG_TEXT"),
                   show="*" if key=="password" else "",relief=tk.FLAT,bd=1,
                   highlightbackground=T("CLR_BORDER"),highlightthickness=1)
        e.insert(0,EMAIL_CFG.get(key,""))
        e.grid(row=i,column=1,padx=10,pady=8)
        entries[key]=e
    def save():
        for key,entry in entries.items(): EMAIL_CFG[key]=entry.get()
        messagebox.showinfo("Saved","Email settings saved!"); win.destroy()
    tk.Button(win,text="  Save Settings  ",command=save,bg=T("BG_PRIMARY"),fg=T("FG_WHITE"),
              font=("Segoe UI",10,"bold"),relief=tk.FLAT,bd=0,cursor="hand2",padx=6,pady=8
              ).grid(row=len(fields),column=0,columnspan=2,pady=16)

# ── Telegram ──────────────────────────────────────────────
def send_telegram_alert(files):
    if not TELEGRAM_CFG["token"] or not TELEGRAM_CFG["chat_id"]: return
    try:
        import urllib.request, urllib.parse
        file_list = ""
        for f in files:
            fname = os.path.basename(f)
            fpath = os.path.dirname(f)
            file_list += f"📄 {fname}\n📁 {fpath}\n\n"
        msg = (
            "🚨 FIMS SECURITY ALERT 🚨\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️  File Modification Detected!\n\n"
            f"📊 Total Modified: {len(files)} file(s)\n"
            f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📂 MODIFIED FILES:\n\n"
            f"{file_list}"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🛡 FIMS v3.0 — File Integrity Monitor\n"
            "⚡ Immediate action recommended!"
        )
        url = f"https://api.telegram.org/bot{TELEGRAM_CFG['token']}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": TELEGRAM_CFG["chat_id"], "text": msg}).encode()
        urllib.request.urlopen(url, data=data, timeout=10)
        root.after(0, lambda: log("  ✈  Telegram alert sent!", "init"))
    except Exception as e:
        root.after(0, lambda: log(f"  ✈  Telegram failed: {e}", "modified"))

def open_telegram_settings():
    win = tk.Toplevel(root); win.title("Telegram Alert Settings")
    win.configure(bg=T("BG_MAIN")); win.geometry("460x220")
    win.resizable(False, False); win.transient(root); win.grab_set()

    tk.Frame(win, bg="#2CA5E0", height=4).pack(fill=tk.X)

    tk.Label(win, text="  🤖  Telegram Bot Settings", bg=T("BG_MAIN"), fg=T("FG_TEXT"),
             font=("Segoe UI", 12, "bold"), pady=10).pack(anchor="w", padx=16)

    fields = [("Bot Token", "token"), ("Chat ID", "chat_id")]
    entries = {}
    for label, key in fields:
        row = tk.Frame(win, bg=T("BG_MAIN")); row.pack(fill=tk.X, padx=16, pady=6)
        tk.Label(row, text=label, bg=T("BG_MAIN"), fg=T("FG_TEXT"),
                 font=("Segoe UI", 10), width=12, anchor="w").pack(side=tk.LEFT)
        e = tk.Entry(row, font=("Consolas", 10), bg=T("BG_CARD"), fg=T("FG_TEXT"),
                     relief=tk.FLAT, bd=1, highlightbackground=T("CLR_BORDER"),
                     highlightthickness=1, width=36)
        e.insert(0, TELEGRAM_CFG.get(key, ""))
        e.pack(side=tk.LEFT, padx=6)
        entries[key] = e

    def save():
        for key, entry in entries.items(): TELEGRAM_CFG[key] = entry.get()
        save_settings()
        log("  ✈  Telegram settings saved!", "init")
        messagebox.showinfo("Saved", "Telegram settings saved!\nAlerts will be sent on file modification.")
        win.destroy()

    def test():
        for key, entry in entries.items(): TELEGRAM_CFG[key] = entry.get()
        def _test():
            try:
                import urllib.request, urllib.parse
                msg = (
                    "✅ FIMS Test Alert\n\n"
                    "🛡 File Integrity Monitor v3.0\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "✔ Telegram connected successfully!\n"
                    f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "You will receive alerts here when files are modified!"
                )
                url = f"https://api.telegram.org/bot{TELEGRAM_CFG['token']}/sendMessage"
                data = urllib.parse.urlencode({"chat_id": TELEGRAM_CFG["chat_id"], "text": msg}).encode()
                urllib.request.urlopen(url, data=data, timeout=10)
                root.after(0, lambda: messagebox.showinfo("Success!", "✅ Test alert sent!\nCheck your Telegram!"))
                root.after(0, lambda: log("  ✈  Telegram test alert sent successfully!", "init"))
            except Exception as e:
                root.after(0, lambda: messagebox.showerror("Failed!", f"❌ Telegram error:\n{e}"))
                root.after(0, lambda: log(f"  ✈  Telegram test failed: {e}", "modified"))
        threading.Thread(target=_test, daemon=True).start()

    btn_row = tk.Frame(win, bg=T("BG_MAIN")); btn_row.pack(pady=14)
    tk.Button(btn_row, text="  Test Alert  ", command=test,
              bg=T("BG_BTN"), fg=T("FG_TEXT"), font=("Segoe UI", 10, "bold"),
              relief=tk.FLAT, bd=0, cursor="hand2", padx=6, pady=8).pack(side=tk.LEFT, padx=6)
    tk.Button(btn_row, text="  Save Settings  ", command=save,
              bg="#2CA5E0", fg=T("FG_WHITE"), font=("Segoe UI", 10, "bold"),
              relief=tk.FLAT, bd=0, cursor="hand2", padx=6, pady=8).pack(side=tk.LEFT, padx=6)


def export_csv():
    if not os.path.exists(REPORT_FILE):
        messagebox.showwarning("No Report","No report.json found."); return
    path=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")],initialfile="fims_report.csv")
    if not path: return
    with open(REPORT_FILE,"r") as f: data=json.load(f)
    with open(path,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["file","status","time"]); w.writeheader(); w.writerows(data)
    log(f"  ✓  CSV exported → {path}","safe")
    messagebox.showinfo("Exported",f"Saved:\n{path}")

def export_txt():
    if not os.path.exists(REPORT_FILE):
        messagebox.showwarning("No Report","No report.json found."); return
    path=filedialog.asksaveasfilename(defaultextension=".txt",filetypes=[("Text","*.txt")],initialfile="fims_report.txt")
    if not path: return
    with open(REPORT_FILE,"r") as f: data=json.load(f)
    with open(path,"w") as f:
        f.write(f"FIMS Report\nGenerated: {datetime.now()}\n"+"="*60+"\n\n")
        for e in data: f.write(f"[{e['status']}]  {e['file']}\n         Time: {e['time']}\n\n")
    log(f"  ✓  TXT exported → {path}","safe")
    messagebox.showinfo("Exported",f"Saved:\n{path}")

# ── Report Viewer ─────────────────────────────────────────
def open_report_viewer():
    if not os.path.exists(REPORT_FILE):
        messagebox.showwarning("No Report","No report.json found."); return
    with open(REPORT_FILE,"r") as f: data=json.load(f)
    win=tk.Toplevel(root); win.title("FIMS · Report Viewer")
    win.configure(bg=T("BG_MAIN")); win.geometry("860x500"); win.transient(root); win.grab_set()
    tk.Frame(win,bg=T("BG_PRIMARY"),height=4).pack(fill=tk.X)
    hdr=tk.Frame(win,bg=T("BG_CARD"),highlightbackground=T("CLR_BORDER"),highlightthickness=1)
    hdr.pack(fill=tk.X)
    tk.Label(hdr,text="  Report Viewer",bg=T("BG_CARD"),fg=T("FG_TEXT"),font=("Segoe UI",13,"bold"),pady=10).pack(side=tk.LEFT)
    tk.Label(hdr,text=f"  {len(data)} entries  ",bg=T("BG_CARD"),fg=T("FG_MUTED"),font=("Segoe UI",9)).pack(side=tk.RIGHT)
    tf=tk.Frame(win,bg=T("BG_MAIN")); tf.pack(fill=tk.BOTH,expand=True,padx=12,pady=10)
    cols=("Status","File","Time")
    tree=ttk.Treeview(tf,columns=cols,show="headings",height=18)
    tree.heading("Status",text="Status"); tree.heading("File",text="File"); tree.heading("Time",text="Time")
    tree.column("Status",width=100,anchor="center"); tree.column("File",width=520); tree.column("Time",width=180)
    vsb=ttk.Scrollbar(tf,orient=tk.VERTICAL,command=tree.yview); tree.configure(yscrollcommand=vsb.set)
    tree.pack(side=tk.LEFT,fill=tk.BOTH,expand=True); vsb.pack(side=tk.RIGHT,fill=tk.Y)
    tree.tag_configure("MODIFIED",foreground=T("CLR_MOD"))
    tree.tag_configure("NEW",foreground=T("CLR_NEW"))
    tree.tag_configure("SAFE",foreground=T("CLR_SAFE"))
    for e in reversed(data):
        s=e.get("status",""); tree.insert("",tk.END,values=(s,e.get("file",""),e.get("time","")),tags=(s,))
    br=tk.Frame(win,bg=T("BG_MAIN")); br.pack(fill=tk.X,padx=12,pady=(0,12))
    tk.Button(br,text="  Export CSV  ",command=export_csv,bg=T("BG_BTN"),fg=T("FG_TEXT"),
              font=("Segoe UI",10,"bold"),relief=tk.FLAT,bd=0,cursor="hand2",padx=6,pady=7).pack(side=tk.LEFT,padx=4)
    tk.Button(br,text="  Export TXT  ",command=export_txt,bg=T("BG_BTN"),fg=T("FG_TEXT"),
              font=("Segoe UI",10,"bold"),relief=tk.FLAT,bd=0,cursor="hand2",padx=6,pady=7).pack(side=tk.LEFT,padx=4)
    tk.Button(br,text="  Close  ",command=win.destroy,bg=T("BG_PRIMARY"),fg=T("FG_WHITE"),
              font=("Segoe UI",10,"bold"),relief=tk.FLAT,bd=0,cursor="hand2",padx=6,pady=7).pack(side=tk.RIGHT,padx=4)

# ── Quarantine ────────────────────────────────────────────
def quarantine_file(fp):
    if not os.path.exists(fp): messagebox.showerror("Not Found",f"File not found:\n{fp}"); return
    os.makedirs(QUARANTINE,exist_ok=True)
    dest=os.path.join(QUARANTINE,os.path.basename(fp)+"_"+datetime.now().strftime("%Y%m%d_%H%M%S"))
    shutil.move(fp,dest)
    log(f"  ⚠  Quarantined → {dest}","modified")
    messagebox.showinfo("Quarantined",f"File moved to quarantine:\n{dest}")

def open_quarantine_manager():
    os.makedirs(QUARANTINE,exist_ok=True)
    files=os.listdir(QUARANTINE)
    win=tk.Toplevel(root); win.title("FIMS · Quarantine Manager")
    win.configure(bg=T("BG_MAIN")); win.geometry("700x420"); win.transient(root); win.grab_set()
    tk.Frame(win,bg=T("CLR_MOD"),height=4).pack(fill=tk.X)
    hdr=tk.Frame(win,bg=T("BG_CARD"),highlightbackground=T("CLR_BORDER"),highlightthickness=1)
    hdr.pack(fill=tk.X)
    tk.Label(hdr,text="  Quarantine Manager",bg=T("BG_CARD"),fg=T("CLR_MOD"),font=("Segoe UI",13,"bold"),pady=10).pack(side=tk.LEFT)
    tk.Label(hdr,text=f"  {len(files)} file(s)  ",bg=T("BG_CARD"),fg=T("FG_MUTED"),font=("Segoe UI",9)).pack(side=tk.RIGHT)
    lf=tk.Frame(win,bg=T("BG_OUTPUT"),highlightbackground=T("CLR_BORDER"),highlightthickness=1)
    lf.pack(fill=tk.BOTH,expand=True,padx=12,pady=8)
    lf.rowconfigure(0,weight=1); lf.columnconfigure(0,weight=1)
    listbox=tk.Listbox(lf,bg=T("BG_OUTPUT"),fg=T("CLR_MOD"),font=("Consolas",10),
                       selectbackground=T("CLR_MOD"),selectforeground=T("FG_WHITE"),
                       relief=tk.FLAT,bd=0,highlightthickness=0)
    vsb=ttk.Scrollbar(lf,command=listbox.yview); listbox.config(yscrollcommand=vsb.set)
    listbox.grid(row=0,column=0,sticky="nsew"); vsb.grid(row=0,column=1,sticky="ns")
    for f in files: listbox.insert(tk.END,f"  {f}")
    def restore_sel():
        sel=listbox.curselection()
        if not sel: messagebox.showinfo("Select","Select a file first."); return
        fname=files[sel[0]]; src=os.path.join(QUARANTINE,fname)
        dest=filedialog.askdirectory(title="Restore to?")
        if not dest: return
        orig="__".join(fname.split("_")[:-2]) if "_" in fname else fname
        shutil.move(src,os.path.join(dest,orig))
        log(f"  ✓  Restored → {os.path.join(dest,orig)}","safe")
        win.destroy(); open_quarantine_manager()
    def delete_sel():
        sel=listbox.curselection()
        if not sel: return
        fname=files[sel[0]]
        if messagebox.askyesno("Delete",f"Permanently delete?\n{fname}"):
            os.remove(os.path.join(QUARANTINE,fname))
            log(f"  ✗  Deleted: {fname}","modified"); win.destroy(); open_quarantine_manager()
    br=tk.Frame(win,bg=T("BG_MAIN")); br.pack(fill=tk.X,padx=12,pady=(0,12))
    tk.Button(br,text="  ↩ Restore  ",command=restore_sel,bg=T("CLR_SAFE"),fg=T("FG_WHITE"),
              font=("Segoe UI",10,"bold"),relief=tk.FLAT,bd=0,cursor="hand2",padx=6,pady=7).pack(side=tk.LEFT,padx=4)
    tk.Button(br,text="  ✕ Delete  ",command=delete_sel,bg=T("CLR_MOD"),fg=T("FG_WHITE"),
              font=("Segoe UI",10,"bold"),relief=tk.FLAT,bd=0,cursor="hand2",padx=6,pady=7).pack(side=tk.LEFT,padx=4)
    tk.Button(br,text="  Close  ",command=win.destroy,bg=T("BG_BTN"),fg=T("FG_TEXT"),
              font=("Segoe UI",10,"bold"),relief=tk.FLAT,bd=0,cursor="hand2",padx=6,pady=7).pack(side=tk.RIGHT,padx=4)

def restore_from_baseline():
    fp=filedialog.askopenfilename(title="Select file to check baseline hash")
    if not fp: return
    baseline=load_baseline()
    if fp not in baseline:
        messagebox.showwarning("Not in Baseline",f"File not tracked:\n{fp}"); return
    messagebox.showinfo("Baseline Hash",f"File: {os.path.basename(fp)}\n\nSHA-256:\n{baseline[fp]}\n\nNote: FIMS stores hashes only, not file copies.\nUse Quarantine Manager to restore moved files.")

# ── File List Popup ───────────────────────────────────────
def show_file_list(category):
    files=list(tracked_files[category])
    if not files: messagebox.showinfo("No Files",f"No {category.upper()} files.\nRun a scan first."); return
    cmap={"safe":T("CLR_SAFE"),"modified":T("CLR_MOD"),"new":T("CLR_NEW"),"init":T("CLR_INIT")}
    lmap={"safe":"SAFE FILES","modified":"MODIFIED FILES","new":"NEW FILES","init":"INDEXED FILES"}
    accent=cmap[category]; title=lmap[category]
    popup=tk.Toplevel(root); popup.title(f"FIMS · {title}")
    popup.configure(bg=T("BG_MAIN")); popup.resizable(True,True); popup.transient(root)
    popup.columnconfigure(0,weight=1); popup.rowconfigure(2,weight=1)
    tk.Frame(popup,bg=accent,height=5).grid(row=0,column=0,sticky="ew")
    hdr=tk.Frame(popup,bg=T("BG_CARD"),highlightbackground=T("CLR_BORDER"),highlightthickness=1)
    hdr.grid(row=1,column=0,sticky="ew")
    tk.Label(hdr,text=f"  {title}",bg=T("BG_CARD"),fg=accent,font=("Segoe UI",13,"bold"),pady=10).pack(side=tk.LEFT)
    tk.Label(hdr,text=f"  {len(files)} file(s)  ",bg=T("BG_CARD"),fg=T("FG_MUTED"),font=("Segoe UI",9)).pack(side=tk.RIGHT)
    lf=tk.Frame(popup,bg=T("BG_OUTPUT"),highlightbackground=T("CLR_BORDER"),highlightthickness=1)
    lf.grid(row=2,column=0,sticky="nsew",padx=12,pady=8)
    lf.rowconfigure(0,weight=1); lf.columnconfigure(0,weight=1)
    listbox=tk.Listbox(lf,bg=T("BG_OUTPUT"),fg=accent,font=("Consolas",10),
                       selectbackground=accent,selectforeground=T("FG_WHITE"),
                       relief=tk.FLAT,bd=0,highlightthickness=0,activestyle="none")
    vsb=ttk.Scrollbar(lf,orient=tk.VERTICAL,command=listbox.yview)
    hsb=ttk.Scrollbar(lf,orient=tk.HORIZONTAL,command=listbox.xview)
    listbox.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
    listbox.grid(row=0,column=0,sticky="nsew"); vsb.grid(row=0,column=1,sticky="ns"); hsb.grid(row=1,column=0,sticky="ew")
    for fp in files: listbox.insert(tk.END,f"  {fp}")
    pv=tk.StringVar(value="  Select a file to see its full path")
    pb=tk.Frame(popup,bg=T("BG_CARD"),highlightbackground=T("CLR_BORDER"),highlightthickness=1)
    pb.grid(row=3,column=0,sticky="ew",padx=12,pady=(0,4))
    tk.Label(pb,textvariable=pv,bg=T("BG_CARD"),fg=T("FG_MUTED"),font=("Consolas",8),anchor="w",pady=5,padx=8).pack(fill=tk.X)
    br=tk.Frame(popup,bg=T("BG_MAIN")); br.grid(row=4,column=0,sticky="ew",padx=12,pady=(0,12))
    def open_path(path):
        if not os.path.exists(path): messagebox.showerror("Not Found",f"Not found:\n{path}"); return
        try:
            if sys.platform=="win32": os.startfile(path)
            elif sys.platform=="darwin": subprocess.Popen(["open",path])
            else: subprocess.Popen(["xdg-open",path])
        except Exception as ex: messagebox.showerror("Error",str(ex))
    def on_sel(e):
        sel=listbox.curselection()
        if sel: pv.set(f"  {files[sel[0]]}")
    def on_dbl(e):
        sel=listbox.curselection()
        if sel: open_path(files[sel[0]])
    def open_folder():
        sel=listbox.curselection()
        if not sel: messagebox.showinfo("Select","Click a file first."); return
        open_path(os.path.dirname(files[sel[0]]))
    def do_quarantine():
        sel=listbox.curselection()
        if not sel: messagebox.showinfo("Select","Click a file first."); return
        quarantine_file(files[sel[0]])
    listbox.bind("<<ListboxSelect>>",on_sel); listbox.bind("<Double-Button-1>",on_dbl)
    tk.Button(br,text="  📁 Open Folder  ",command=open_folder,bg=T("BG_BTN"),fg=T("FG_TEXT"),
              font=("Segoe UI",10,"bold"),relief=tk.FLAT,bd=0,cursor="hand2",padx=6,pady=7).pack(side=tk.LEFT,padx=2)
    if category=="modified":
        tk.Button(br,text="  ⚠ Quarantine  ",command=do_quarantine,bg=T("CLR_MOD"),fg=T("FG_WHITE"),
                  font=("Segoe UI",10,"bold"),relief=tk.FLAT,bd=0,cursor="hand2",padx=6,pady=7).pack(side=tk.LEFT,padx=2)
    tk.Button(br,text="  ✕ Close  ",command=popup.destroy,bg=accent,fg=T("FG_WHITE"),
              font=("Segoe UI",10,"bold"),relief=tk.FLAT,bd=0,cursor="hand2",padx=6,pady=7).pack(side=tk.RIGHT)
    popup.update_idletasks(); popup.geometry("780x480")
    x=root.winfo_x()+(root.winfo_width()//2)-390; y=root.winfo_y()+(root.winfo_height()//2)-240
    popup.geometry(f"780x480+{x}+{y}"); popup.grab_set()

# ── Scan ──────────────────────────────────────────────────
def check_file(fp, baseline):
    if any(x in fp for x in IGNORE): return
    fh=calculate_hash(fp)
    if fh is None: return
    oh=baseline.get(fp)
    if oh is None:
        stats["new"]+=1; tracked_files["new"].append(fp); log(f"[NEW]      {fp}","new")
    elif oh!=fh:
        stats["modified"]+=1; tracked_files["modified"].append(fp)
        log(f"[MODIFIED] {fp}","modified")
        write_report({"file":fp,"status":"MODIFIED","time":str(datetime.now())})
    else:
        stats["safe"]+=1; tracked_files["safe"].append(fp); log(f"[SAFE]     {fp}","safe")
    update_metric_cards()

def scan_folder(path, baseline, mode="VERIFY"):
    for rd,dirs,files in os.walk(path):
        for file in files:
            fp=os.path.join(rd,file)
            if mode=="INIT":
                fh=calculate_hash(fp)
                if fh:
                    baseline[fp]=fh; stats["init"]+=1; tracked_files["init"].append(fp)
                    log(f"[INIT]     {fp}","init"); update_metric_cards()
            else:
                check_file(fp,baseline)

def init_baseline():
    path=filedialog.askdirectory(title="Select folder to baseline")
    if not path: return
    reset_stats(); update_metric_cards(); clear_log_ui()
    status_var.set("Creating baseline..."); path_var.set(path)
    log_sep(); log(f"  INIT BASELINE  →  {path}","init"); log_sep()
    baseline={}; scan_folder(path,baseline,"INIT"); save_baseline(baseline)
    log_sep(); log(f"  Saved → {HASH_FILE}  ({stats['init']} files hashed)","init"); log_sep()
    status_var.set(f"Baseline created  ·  {stats['init']} files")
    messagebox.showinfo("Done",f"Baseline created!\n{stats['init']} files indexed.")

def scan_files():
    path=filedialog.askdirectory(title="Select folder to scan")
    if not path: return
    reset_stats(); update_metric_cards(); clear_log_ui()
    status_var.set("Scanning..."); path_var.set(path)
    log_sep(); log(f"  SCAN FOLDER  →  {path}","normal"); log_sep()
    baseline=load_baseline(); scan_folder(path,baseline)
    log_sep(); log(f"  Done  ·  Safe:{stats['safe']}  Modified:{stats['modified']}  New:{stats['new']}","normal"); log_sep()
    status_var.set(f"Scan done  ·  S:{stats['safe']} M:{stats['modified']} N:{stats['new']}")
    if stats["modified"]>0:
        threading.Thread(target=send_email_alert,args=(list(tracked_files["modified"]),),daemon=True).start()
        threading.Thread(target=send_telegram_alert,args=(list(tracked_files["modified"]),),daemon=True).start()
    fp=filedialog.askopenfilename(title="Select file to check")
    if not fp: return
    reset_stats(); update_metric_cards(); clear_log_ui()
    status_var.set("Checking..."); path_var.set(fp)
    log_sep(); log(f"  CHECK FILE  →  {fp}","normal"); log_sep()
    check_file(fp,load_baseline()); log_sep(); status_var.set("File check complete")

def check_single_file():
    fp=filedialog.askopenfilename(title="Select file to check")
    if not fp: return
    reset_stats(); update_metric_cards(); clear_log_ui()
    status_var.set("Checking..."); path_var.set(fp)
    log_sep(); log(f"  CHECK FILE  →  {fp}","normal"); log_sep()
    check_file(fp,load_baseline()); log_sep(); status_var.set("File check complete")

def clear_output():
    reset_stats(); update_metric_cards(); clear_log_ui()
    status_var.set("Ready"); path_var.set("No folder selected")

# ── Auto-Scan ─────────────────────────────────────────────
def toggle_auto_scan():
    global auto_active,auto_thread
    if auto_active:
        auto_active=False; auto_btn.config(text="  ⏱  Auto-Scan OFF  ",bg=T("BG_BTN"),fg=T("FG_TEXT"))
        log("  ⏱  Auto-scan stopped.","muted"); status_var.set("Auto-scan stopped"); return
    path=filedialog.askdirectory(title="Folder to auto-scan")
    if not path: return
    iv=simpledialog.askstring("Auto-Scan","Scan every how many seconds?\n(e.g. 60)",initialvalue="60")
    try: interval=int(iv)
    except: messagebox.showerror("Invalid","Enter a valid number."); return
    auto_active=True; auto_btn.config(text=f"  ⏱  Auto:{interval}s  ",bg=T("BG_PRIMARY"),fg=T("FG_WHITE"))
    log(f"  ⏱  Auto-scan ON  ·  {path}  ·  Every {interval}s","init")
    def loop():
        while auto_active:
            time.sleep(interval)
            if not auto_active: break
            root.after(0,lambda: _auto_run(path))
    auto_thread=threading.Thread(target=loop,daemon=True); auto_thread.start()

def _auto_run(path):
    log_sep(); log(f"  ⏱  AUTO SCAN  →  {path}","init"); log_sep()
    baseline=load_baseline(); reset_stats(); update_metric_cards(); scan_folder(path,baseline)
    log(f"  Auto done  ·  S:{stats['safe']} M:{stats['modified']} N:{stats['new']}","normal"); log_sep()
    status_var.set(f"Auto-scan  ·  {datetime.now().strftime('%H:%M:%S')}")
    if stats["modified"]>0:
        threading.Thread(target=send_email_alert,args=(list(tracked_files["modified"]),),daemon=True).start()
        threading.Thread(target=send_telegram_alert,args=(list(tracked_files["modified"]),),daemon=True).start()

# ── Watch Mode ────────────────────────────────────────────
def toggle_watch():
    global watch_active,watch_thread
    if watch_active:
        watch_active=False; watch_btn.config(text="  👁  Watch OFF  ",bg=T("BG_BTN"),fg=T("FG_TEXT"))
        log("  👁  Watch stopped.","muted"); status_var.set("Watch stopped"); return
    path=filedialog.askdirectory(title="Folder to watch")
    if not path: return
    watch_active=True; watch_btn.config(text="  👁  Watching...  ",bg=T("CLR_MOD"),fg=T("FG_WHITE"))
    log(f"  👁  Watch ON  →  {path}","watch"); status_var.set(f"Watching: {path}")
    def loop():
        snap={}
        for rd,dirs,files in os.walk(path):
            for file in files:
                fp=os.path.join(rd,file)
                if not any(x in fp for x in IGNORE):
                    h=calculate_hash(fp)
                    if h: snap[fp]=h
        while watch_active:
            time.sleep(3)
            for rd,dirs,files in os.walk(path):
                for file in files:
                    fp=os.path.join(rd,file)
                    if any(x in fp for x in IGNORE): continue
                    h=calculate_hash(fp)
                    if h is None: continue
                    old=snap.get(fp)
                    if old is None:
                        snap[fp]=h; root.after(0,lambda f=fp: log(f"  👁  NEW: {f}","new"))
                    elif old!=h:
                        snap[fp]=h; root.after(0,lambda f=fp: log(f"  👁  CHANGED: {f}","modified"))
                        write_report({"file":fp,"status":"MODIFIED(watch)","time":str(datetime.now())})
                        threading.Thread(target=send_email_alert,args=([fp],),daemon=True).start()
                        threading.Thread(target=send_telegram_alert,args=([fp],),daemon=True).start()
    watch_thread=threading.Thread(target=loop,daemon=True); watch_thread.start()

# ── Theme Toggle ──────────────────────────────────────────
def toggle_theme():
    global current_theme
    current_theme="dark" if current_theme=="light" else "light"
    theme_btn.config(text="  ☀ Light  " if current_theme=="dark" else "  🌙 Dark  ")
    messagebox.showinfo("Theme",f"Switched to {current_theme.upper()} mode.\nRestart FIMS to apply fully.")

# ── Ignore Editor ─────────────────────────────────────────
def open_ignore_editor():
    win=tk.Toplevel(root); win.title("FIMS · Ignore List")
    win.configure(bg=T("BG_MAIN")); win.geometry("380x300")
    win.resizable(False,False); win.transient(root); win.grab_set()
    tk.Label(win,text="  Ignored patterns (one per line):",bg=T("BG_MAIN"),fg=T("FG_TEXT"),
             font=("Segoe UI",10,"bold")).pack(anchor="w",padx=16,pady=(14,4))
    txt=tk.Text(win,bg=T("BG_OUTPUT"),fg=T("FG_TEXT"),font=("Consolas",11),
                relief=tk.FLAT,bd=1,highlightbackground=T("CLR_BORDER"),highlightthickness=1,
                padx=8,pady=8,height=8)
    txt.pack(fill=tk.BOTH,expand=True,padx=16,pady=4)
    txt.insert(tk.END,"\n".join(IGNORE))
    def save():
        global IGNORE
        IGNORE[:]=[ l.strip() for l in txt.get("1.0",tk.END).splitlines() if l.strip() ]
        log(f"  ✓  Ignore list: {IGNORE}","init"); win.destroy()
    tk.Button(win,text="  Save  ",command=save,bg=T("BG_PRIMARY"),fg=T("FG_WHITE"),
              font=("Segoe UI",10,"bold"),relief=tk.FLAT,bd=0,cursor="hand2",padx=6,pady=8).pack(pady=10)

# ── Make Button ───────────────────────────────────────────
def make_btn(parent,text,cmd,primary=False,icon=""):
    bg=T("BG_PRIMARY") if primary else T("BG_BTN")
    fg=T("FG_WHITE") if primary else T("FG_TEXT")
    b=tk.Button(parent,text=f"  {icon}  {text}  " if icon else f"  {text}  ",
                command=cmd,bg=bg,fg=fg,font=("Segoe UI",10,"bold"),
                relief=tk.FLAT,bd=0,cursor="hand2",
                activebackground=T("BG_PRI_HOV") if primary else T("BG_BTN_HOV"),
                activeforeground=fg,padx=6,pady=8)
    b.bind("<Enter>",lambda e:b.config(bg=T("BG_PRI_HOV") if primary else T("BG_BTN_HOV")))
    b.bind("<Leave>",lambda e:b.config(bg=T("BG_PRIMARY") if primary else T("BG_BTN")))
    return b

# ── ROOT ──────────────────────────────────────────────────
root=tk.Tk()
root.title("FIMS  ·  File Integrity Monitor  ·  v3.0")
root.geometry("1120x700"); root.minsize(900,540)
root.configure(bg=T("BG_MAIN")); root.resizable(True,True)

# ── SIDEBAR ───────────────────────────────────────────────
sidebar=tk.Frame(root,bg=T("BG_SIDE"),width=240)
sidebar.pack(side=tk.LEFT,fill=tk.Y); sidebar.pack_propagate(False)

lf=tk.Frame(sidebar,bg=T("BG_SIDE"),pady=20); lf.pack(fill=tk.X,padx=20)
lic=tk.Canvas(lf,width=36,height=36,bg=T("BG_PRIMARY"),highlightthickness=0); lic.pack(side=tk.LEFT)
lic.create_text(18,18,text="⬡",fill=T("FG_WHITE"),font=("Segoe UI",18))
ltf=tk.Frame(lf,bg=T("BG_SIDE")); ltf.pack(side=tk.LEFT,padx=(10,0))
tk.Label(ltf,text="FIMS",bg=T("BG_SIDE"),fg=T("FG_TEXT"),font=("Segoe UI",16,"bold")).pack(anchor="w")
tk.Label(ltf,text="Integrity Monitor",bg=T("BG_SIDE"),fg=T("FG_MUTED"),font=("Segoe UI",9)).pack(anchor="w")
tk.Frame(sidebar,bg=T("CLR_BORDER"),height=1).pack(fill=tk.X)

def nav_label(t):
    tk.Label(sidebar,text=t,bg=T("BG_SIDE"),fg=T("FG_MUTED"),
             font=("Segoe UI",8,"bold")).pack(anchor="w",padx=20,pady=(14,4))

nav_label("CORE ACTIONS")
make_btn(sidebar,"Init Baseline", init_baseline,       icon="◈").pack(fill=tk.X,padx=12,pady=2)
make_btn(sidebar,"Scan Folder",   scan_files,primary=True,icon="⌕").pack(fill=tk.X,padx=12,pady=2)
make_btn(sidebar,"Check File",    check_single_file,   icon="◎").pack(fill=tk.X,padx=12,pady=2)
make_btn(sidebar,"Clear Logs",    clear_output,        icon="⊘").pack(fill=tk.X,padx=12,pady=2)

nav_label("LIVE MONITOR")
watch_btn=tk.Button(sidebar,text="  👁  Watch OFF  ",command=toggle_watch,
                    bg=T("BG_BTN"),fg=T("FG_TEXT"),font=("Segoe UI",10,"bold"),
                    relief=tk.FLAT,bd=0,cursor="hand2",padx=6,pady=8)
watch_btn.pack(fill=tk.X,padx=12,pady=2)
auto_btn=tk.Button(sidebar,text="  ⏱  Auto-Scan OFF  ",command=toggle_auto_scan,
                   bg=T("BG_BTN"),fg=T("FG_TEXT"),font=("Segoe UI",10,"bold"),
                   relief=tk.FLAT,bd=0,cursor="hand2",padx=6,pady=8)
auto_btn.pack(fill=tk.X,padx=12,pady=2)

nav_label("TOOLS")
make_btn(sidebar,"Report Viewer",   open_report_viewer,    icon="📋").pack(fill=tk.X,padx=12,pady=2)
make_btn(sidebar,"Quarantine Mgr",  open_quarantine_manager,icon="⚠").pack(fill=tk.X,padx=12,pady=2)
make_btn(sidebar,"Restore Info",    restore_from_baseline, icon="↩").pack(fill=tk.X,padx=12,pady=2)

make_btn(sidebar,"Telegram Alert",  open_telegram_settings,icon="✈").pack(fill=tk.X,padx=12,pady=2)
make_btn(sidebar,"Ignore List",     open_ignore_editor,    icon="⚙").pack(fill=tk.X,padx=12,pady=2)

nav_label("EXPORT")
make_btn(sidebar,"Export CSV",export_csv,icon="⬇").pack(fill=tk.X,padx=12,pady=2)
make_btn(sidebar,"Export TXT",export_txt,icon="⬇").pack(fill=tk.X,padx=12,pady=2)

tk.Frame(sidebar,bg=T("BG_SIDE")).pack(fill=tk.BOTH,expand=True)
tk.Frame(sidebar,bg=T("CLR_BORDER"),height=1).pack(fill=tk.X)
foot=tk.Frame(sidebar,bg=T("BG_SIDE"),pady=12); foot.pack(fill=tk.X,padx=14)
theme_btn=tk.Button(foot,text="  🌙 Dark  ",command=toggle_theme,
                    bg=T("BG_BTN"),fg=T("FG_TEXT"),font=("Segoe UI",9,"bold"),
                    relief=tk.FLAT,bd=0,cursor="hand2",padx=4,pady=5)
theme_btn.pack(fill=tk.X,pady=(0,8))
tk.Label(foot,text="● ENGINE ACTIVE",bg=T("BG_SIDE"),fg=T("FG_ACCENT"),font=("Segoe UI",9,"bold")).pack(anchor="w")
tk.Label(foot,text="SHA-256  ·  v3.0",bg=T("BG_SIDE"),fg=T("FG_MUTED"),font=("Segoe UI",8)).pack(anchor="w",pady=(2,0))

# ── MAIN ──────────────────────────────────────────────────
main=tk.Frame(root,bg=T("BG_MAIN")); main.pack(side=tk.RIGHT,fill=tk.BOTH,expand=True)

topbar=tk.Frame(main,bg=T("BG_TOP"),height=52); topbar.pack(fill=tk.X); topbar.pack_propagate(False)
tk.Frame(topbar,bg=T("CLR_BORDER"),width=1).pack(side=tk.LEFT,fill=tk.Y)
tk.Label(topbar,text="Overview",bg=T("BG_TOP"),fg=T("FG_TEXT"),font=("Segoe UI",12,"bold")).pack(side=tk.LEFT,padx=20)
path_var=tk.StringVar(value="No folder selected")
tk.Label(topbar,textvariable=path_var,bg=T("BG_BTN"),fg=T("FG_MUTED"),
         font=("Consolas",9),padx=10,pady=4,relief=tk.FLAT).pack(side=tk.LEFT,padx=8)
search_var=tk.StringVar(); search_var.trace("w",apply_search_highlight)
sf=tk.Frame(topbar,bg=T("BG_BTN"),highlightbackground=T("CLR_BORDER"),highlightthickness=1)
sf.pack(side=tk.RIGHT,padx=14)
tk.Label(sf,text=" 🔍 ",bg=T("BG_BTN"),fg=T("FG_MUTED"),font=("Segoe UI",10)).pack(side=tk.LEFT)
tk.Entry(sf,textvariable=search_var,bg=T("BG_BTN"),fg=T("FG_TEXT"),font=("Consolas",9),
         relief=tk.FLAT,bd=0,width=22,insertbackground=T("FG_TEXT")).pack(side=tk.LEFT,pady=6)
tk.Frame(topbar,bg=T("CLR_BORDER"),height=1).pack(side=tk.BOTTOM,fill=tk.X)

# Cards
cf=tk.Frame(main,bg=T("BG_MAIN"),pady=14,padx=14); cf.pack(fill=tk.X)
def metric_card(parent,label,accent,category):
    card=tk.Frame(parent,bg=T("BG_CARD"),relief=tk.FLAT,
                  highlightbackground=T("CLR_BORDER"),highlightthickness=1,cursor="hand2")
    card.pack(side=tk.LEFT,fill=tk.BOTH,expand=True,padx=5)
    stripe=tk.Frame(card,bg=T("CLR_BORDER"),height=3); stripe.pack(fill=tk.X)
    lt=tk.Label(card,text=label,bg=T("BG_CARD"),fg=T("FG_MUTED"),font=("Segoe UI",8,"bold"))
    lt.pack(anchor="w",padx=14,pady=(10,0))
    lv=tk.Label(card,text="0",bg=T("BG_CARD"),fg=accent,font=("Segoe UI",22,"bold"))
    lv.pack(anchor="w",padx=14)
    lh=tk.Label(card,text="click to view ↗",bg=T("BG_CARD"),fg=T("FG_MUTED"),font=("Segoe UI",7),cursor="hand2")
    lh.pack(anchor="w",padx=14,pady=(0,10))
    def hov(e):  stripe.config(bg=accent); card.config(highlightbackground=accent)
    def lev(e):  stripe.config(bg=T("CLR_BORDER")); card.config(highlightbackground=T("CLR_BORDER"))
    def clk(e):  show_file_list(category)
    for w in [card,stripe,lt,lv,lh]:
        w.bind("<Enter>",hov); w.bind("<Leave>",lev); w.bind("<Button-1>",clk)
    return lv

lbl_safe=metric_card(cf,"SAFE",    T("CLR_SAFE"),"safe")
lbl_mod =metric_card(cf,"MODIFIED",T("CLR_MOD"), "modified")
lbl_new =metric_card(cf,"NEW",     T("CLR_NEW"), "new")
lbl_init=metric_card(cf,"INDEXED", T("CLR_INIT"),"init")

# Log Panel
lframe=tk.Frame(main,bg=T("BG_MAIN"),padx=14,pady=0); lframe.pack(fill=tk.BOTH,expand=True)
lhdr=tk.Frame(lframe,bg=T("BG_CARD"),highlightbackground=T("CLR_BORDER"),highlightthickness=1)
lhdr.pack(fill=tk.X)
tk.Label(lhdr,text="  Activity Log",bg=T("BG_CARD"),fg=T("FG_TEXT"),font=("Segoe UI",9,"bold"),pady=8).pack(side=tk.LEFT)
tk.Label(lhdr,text="SHA-256 · Real-time  ",bg=T("BG_CARD"),fg=T("FG_MUTED"),font=("Segoe UI",9)).pack(side=tk.RIGHT)
lbody=tk.Frame(lframe,bg=T("BG_OUTPUT"),highlightbackground=T("CLR_BORDER"),highlightthickness=1)
lbody.pack(fill=tk.BOTH,expand=True)
scrollbar=ttk.Scrollbar(lbody); scrollbar.pack(side=tk.RIGHT,fill=tk.Y)
output=tk.Text(lbody,bg=T("BG_OUTPUT"),fg=T("FG_TEXT"),font=("Consolas",10),
               insertbackground=T("FG_TEXT"),yscrollcommand=scrollbar.set,
               relief=tk.FLAT,bd=0,padx=8,pady=8,state=tk.DISABLED,
               selectbackground="#D0E8FF",wrap=tk.NONE,spacing1=2,spacing3=2)
output.pack(fill=tk.BOTH,expand=True); scrollbar.config(command=output.yview)

# Status Bar
sb=tk.Frame(root,bg=T("BG_SIDE"),height=28,highlightbackground=T("CLR_BORDER"),highlightthickness=1)
sb.pack(side=tk.BOTTOM,fill=tk.X); sb.pack_propagate(False)
status_var=tk.StringVar(value="Ready")
tk.Label(sb,textvariable=status_var,bg=T("BG_SIDE"),fg=T("FG_MUTED"),
         font=("Segoe UI",9),anchor="w",padx=16).pack(side=tk.LEFT,fill=tk.Y)
tk.Label(sb,text=f"FIMS v3.0  ·  {datetime.now().strftime('%Y-%m-%d')}",
         bg=T("BG_SIDE"),fg=T("FG_MUTED"),font=("Segoe UI",9),padx=16).pack(side=tk.RIGHT)

# Startup
load_settings()
log_sep()
log("  FIMS v3.0  ·  File Integrity Monitor  ·  Ready","normal")
log("  💡 Click metric cards (SAFE / MODIFIED / NEW) after scanning to view those files","muted")
log("  💡 Use 🔍 search bar to filter activity log in real-time","muted")
log_sep()

root.mainloop()