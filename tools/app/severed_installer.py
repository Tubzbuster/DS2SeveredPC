"""DS2SeveredPC installer: a classic setup wizard around the converter
(tools/test/make_severed_test.py), so nobody needs the command line.

Pages: Welcome (install or remove), Locations (the Severed add-on, the
Dead Space 2 folder; ffmpeg only when it is not bundled), Ready, Installing
(progress and the converter's log in a terminal box), Finish. Temporary
files go to severed_work next to the program and are deleted at the end
(kept when setup stops, so a new run picks up where it left off). The app
also installs and removes the hook dinput8.dll it carries, so nothing is
copied by hand; another mod's dinput8.dll is set aside and put back.

    py -3 severed_installer.py              the wizard
    py -3 severed_installer.py --selftest   checks a built app carries all its parts
    py -3 severed_installer.py --game ...   the converter's own command line
Built into a Windows app with PyInstaller (build_app.bat, or the GitHub
Actions workflow), carrying its own Python and ffmpeg, so users need
nothing installed.
"""
import io
import os
import queue
import shutil
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = getattr(sys, 'frozen', False)
APP_DIR = os.path.dirname(sys.executable) if FROZEN else HERE
if not FROZEN:                                   # the built app carries the converter inside
    sys.path.insert(0, os.path.join(HERE, '..', 'test'))
sys.path.insert(0, HERE)
import gamefind  # noqa: E402

TITLE = 'Dead Space 2: Severed for PC'
VERSION = '1.2.5'
WORK_GB, GAME_GB = 10, 3.5
WIN = sys.platform == 'win32'
FONT = 'Segoe UI' if WIN else 'DejaVu Sans'
MONO = 'Consolas' if WIN else 'DejaVu Sans Mono'
BANNER_BG, BANNER_FG, ACCENT = '#14171a', '#d8dde2', '#b3261e'
ICON_BY, ICON_URL = 'youngpotart', 'https://www.steamgriddb.com/profile/76561198110359023'
HOOK = 'dinput8.dll'
HOOK_BACKUP = 'dinput8.dll.other'               # another mod's dinput8.dll, put back on removal
HOOK_TAGS = (b'severed_probe.log',)             # text only our hook carries


def bundled_ffmpeg():
    for p in (os.path.join(APP_DIR, 'ffmpeg', 'ffmpeg.exe'), os.path.join(APP_DIR, 'ffmpeg', 'ffmpeg')):
        if os.path.isfile(p):
            return p
    return shutil.which('ffmpeg')


def bundled_hook():
    base = getattr(sys, '_MEIPASS', None)
    p = (os.path.join(base, 'hook', HOOK) if base
         else os.path.join(HERE, '..', 'probe', 'bin', HOOK))
    return p if os.path.isfile(p) else None


def is_our_hook(p):
    try:
        with open(p, 'rb') as f:
            data = f.read()
    except OSError:
        return False
    return any(t in data for t in HOOK_TAGS)


def install_hook(game, log):
    """copies the hook next to deadspace2.exe, setting another mod's aside"""
    src = bundled_hook()
    if not src:
        raise SystemExit('The app is missing its %s: download it again.' % HOOK)
    dst, bak = os.path.join(game, HOOK), os.path.join(game, HOOK_BACKUP)
    if os.path.exists(dst) and not is_our_hook(dst):
        if os.path.exists(bak):
            raise SystemExit('%s belongs to another mod and %s is already taken: move one of them '
                             'out of the game folder and run the app again.' % (dst, bak))
        os.replace(dst, bak)
        log('Another mod\'s %s set aside as %s (put back when Severed is removed)' % (HOOK, bak))
    shutil.copyfile(src, dst)
    log('Installed', dst)


def remove_hook(game, log):
    dst, bak = os.path.join(game, HOOK), os.path.join(game, HOOK_BACKUP)
    if os.path.exists(dst) and is_our_hook(dst):
        os.remove(dst)
        log('Removed', dst)
    if os.path.exists(bak) and not os.path.exists(dst):
        os.replace(bak, dst)
        log('Put the other mod\'s %s back' % HOOK)


def free_gb(path):
    p = os.path.abspath(path or '.')
    while p and not os.path.exists(p):
        q = os.path.dirname(p)
        if q == p:
            return None
        p = q
    try:
        return shutil.disk_usage(p).free / 1e9
    except OSError:
        return None


def is_package(p):
    try:
        with open(p, 'rb') as f:
            return f.read(4) in (b'CON ', b'LIVE', b'PIRS')
    except OSError:
        return False


def addon_root(p):
    """the add-on the user picked: the package file itself, or for a file
    inside an unpacked add-on, the folder holding weller1.lvl (or the
    pdlc1_ch01_mng folder) above it"""
    if os.path.isdir(p) or is_package(p):
        return p
    for test in (lambda d: os.path.isfile(os.path.join(d, 'weller1.lvl')),
                 lambda d: os.path.isdir(os.path.join(d, 'pdlc1_ch01_mng', 'pdlc1_ch01_mng'))):
        d = os.path.dirname(p)
        while True:
            if test(d):
                return d
            up = os.path.dirname(d)
            if up == d:
                break
            d = up
    return os.path.dirname(p)


def addon_kind(p):
    if p and os.path.isfile(p):
        return 'package' if is_package(p) else None
    if p and os.path.isdir(p):
        for d, _, fs in os.walk(p):
            if 'weller1.lvl' in fs:
                return 'folder'
            if d.count(os.sep) - p.count(os.sep) >= 2:
                break
    return None


class Pipe(io.TextIOBase):
    """stdout replacement: the converter's lines go to the window"""
    def __init__(self, q):
        self.q = q

    def write(self, s):
        self.q.put(s)
        return len(s)


class Wizard:
    PAGES = ('welcome', 'locations', 'ready', 'installing', 'finish')

    def __init__(self, root):
        self.root = root
        root.title('%s Setup' % TITLE)
        res = getattr(sys, '_MEIPASS', HERE)            # icon by youngpotart (SteamGridDB)
        icon = os.path.join(res, 'icon.ico')
        if WIN and os.path.isfile(icon):
            root.iconbitmap(default=icon)
        try:
            self.logo = tk.PhotoImage(file=os.path.join(res, 'icon.png')).subsample(2)   # 128 px
        except tk.TclError:
            self.logo = None
        root.geometry('720x520')
        root.minsize(640, 480)
        style = ttk.Style(root)
        if 'vista' in style.theme_names():
            style.theme_use('vista')
        elif 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('Head.TLabel', font=(FONT, 10, 'bold'), background='white')
        style.configure('Sub.TLabel', font=(FONT, 9), background='white')
        style.configure('White.TFrame', background='white')
        style.configure('Big.TLabel', font=(FONT, 15, 'bold'), background='white')
        style.configure('Body.TLabel', font=(FONT, 9), background='white')
        style.configure('White.TRadiobutton', background='white', font=(FONT, 9))
        style.configure('Warn.TLabel', foreground='#a4262c')
        self.q = queue.Queue()
        self.mode = tk.StringVar(value='install')
        self.addon = tk.StringVar()
        found = gamefind.find()
        self.games = found
        self.game = tk.StringVar(value=found[0] if found else '')
        self.work = os.path.join(APP_DIR, 'severed_work')
        self.cleanup = tk.BooleanVar(value=True)
        self.ffmpeg = tk.StringVar(value=bundled_ffmpeg() or '')
        self.ffmpeg_bundled = bool(self.ffmpeg.get())
        self.ok = None

        self.body = ttk.Frame(root)
        self.body.pack(fill='both', expand=True)
        ttk.Separator(root).pack(fill='x')
        bar = ttk.Frame(root, padding=(10, 8))
        bar.pack(fill='x')
        ttk.Label(bar, text='DS2SeveredPC %s' % VERSION, foreground='#888').pack(side='left')
        self.cancel = ttk.Button(bar, text='Cancel', command=self.on_cancel)
        self.cancel.pack(side='right')
        self.next = ttk.Button(bar, text='Next >', command=self.on_next)
        self.next.pack(side='right', padx=(0, 10))
        self.back = ttk.Button(bar, text='< Back', command=self.on_back)
        self.back.pack(side='right')
        root.protocol('WM_DELETE_WINDOW', self.on_cancel)
        self.page = 0
        self.show()
        root.after(100, self.drain)

    # ---- page frames ---------------------------------------------------------

    def side_page(self, credit=False):
        """Welcome / Finish: the dark banner on the left, white text area"""
        f = tk.Frame(self.body, bg='white')
        f.pack(fill='both', expand=True)
        banner = tk.Canvas(f, width=190, bg=BANNER_BG, highlightthickness=0)
        banner.pack(side='left', fill='y')
        banner.create_rectangle(0, 0, 6, 2000, fill=ACCENT, width=0)
        banner.create_text(24, 40, anchor='nw', text='DEAD SPACE 2', fill=BANNER_FG, font=(FONT, 13, 'bold'))
        banner.create_text(24, 72, anchor='nw', text='SEVERED', fill=ACCENT, font=(FONT, 19, 'bold'))
        banner.create_text(24, 112, anchor='nw', text='for PC', fill='#8a939b', font=(FONT, 10))
        if self.logo:
            banner.create_image(98, 280, image=self.logo)
        if credit:       # the icon's maker, linked, under the icon
            banner.create_text(24, 362, anchor='nw', text='App icon by', fill='#8a939b', font=(FONT, 8))
            link = banner.create_text(24, 378, anchor='nw', text=ICON_BY, fill='#b9c0c6',
                                      font=(FONT, 8, 'underline'))
            banner.create_text(24, 394, anchor='nw', text='(SteamGridDB)', fill='#8a939b', font=(FONT, 8))
            banner.tag_bind(link, '<Button-1>', lambda e: webbrowser.open(ICON_URL))
            banner.tag_bind(link, '<Enter>', lambda e: banner.config(cursor='hand2'))
            banner.tag_bind(link, '<Leave>', lambda e: banner.config(cursor=''))
        banner.create_text(24, 460, anchor='sw', text='Converted from your own\nXbox 360 add-on',
                           fill='#6b747c', font=(FONT, 8))
        inner = ttk.Frame(f, style='White.TFrame', padding=(24, 24))
        inner.pack(side='left', fill='both', expand=True)
        return inner

    def head_page(self, title, sub):
        """inner pages: the white header band with title and subtitle"""
        head = ttk.Frame(self.body, style='White.TFrame', padding=(16, 10))
        head.pack(fill='x')
        ttk.Label(head, text=title, style='Head.TLabel').pack(anchor='w')
        ttk.Label(head, text=sub, style='Sub.TLabel').pack(anchor='w', padx=(12, 0), pady=(2, 0))
        ttk.Separator(self.body).pack(fill='x')
        inner = ttk.Frame(self.body, padding=(24, 16))
        inner.pack(fill='both', expand=True)
        return inner

    def show(self):
        for w in self.body.winfo_children():
            w.destroy()
        name = self.PAGES[self.page]
        getattr(self, 'page_' + name)()
        self.back.config(state='normal' if name in ('locations', 'ready') else 'disabled')
        self.next.config(text={'ready': 'Install' if self.mode.get() == 'install' else 'Remove',
                               'finish': 'Finish'}.get(name, 'Next >'))
        self.next.config(state='disabled' if name == 'installing' else 'normal')
        self.cancel.config(state='disabled' if name == 'finish' else 'normal')
        self.refresh()

    def page_welcome(self):
        f = self.side_page(credit=True)
        ttk.Label(f, text='Welcome to the %s Setup Wizard' % TITLE, style='Big.TLabel',
                  justify='left', wraplength=440).pack(anchor='w')
        ttk.Label(f, style='Body.TLabel', wraplength=440, justify='left', text=(
            '\nThis wizard converts your own copy of the Xbox 360 add-on "Dead Space 2: '
            'Severed" for the PC version of Dead Space 2. Severed is then started from '
            'Single Player > New Game > Episode Select.\n\n'
            'Converting takes 15 minutes or more. It can be stopped and started again: it '
            'picks up where it left off.\n\n'
            'DS2SeveredPC contains no game files. It adds one archive (DS2DAT2.DAT) and the '
            'hook that puts Severed in the menu (dinput8.dll) to the game folder. A free fan project, not made or endorsed by Electronic Arts.\n\n'
            'What would you like to do?')).pack(anchor='w')
        for v, t in (('install', 'Install Severed'), ('remove', 'Remove Severed from the game')):
            ttk.Radiobutton(f, text=t, value=v, variable=self.mode, style='White.TRadiobutton').pack(
                anchor='w', padx=8, pady=2)

    def path_row(self, f, label, var, buttons, combo=None, note=None):
        ttk.Label(f, text=label).pack(anchor='w', pady=(10, 2))
        row = ttk.Frame(f)
        row.pack(fill='x')
        if combo:
            e = ttk.Combobox(row, textvariable=var, values=combo)
        else:
            e = ttk.Entry(row, textvariable=var)
        e.pack(side='left', fill='x', expand=True)
        for text, cmd in buttons:
            ttk.Button(row, text=text, command=cmd).pack(side='left', padx=(6, 0))
        if note:
            ttk.Label(f, text=note, foreground='#8a8a8a', font=(FONT, 8)).pack(anchor='w', pady=(2, 0))
        var.trace_add('write', lambda *a: self.refresh())

    def page_locations(self):
        install = self.mode.get() == 'install'
        f = self.head_page('Choose locations', 'Point the wizard at your files.' if install
                           else 'Choose the game folder to remove Severed from.')
        if install:
            self.path_row(f, 'Location of the Xbox 360 Severed DLC Addon File or Extracted Addon File Folder:',
                          self.addon, (('Browse...', self.pick_addon),),
                          note='The package file 29E2FCC0..., or any file in a folder it was unpacked to.')
        self.path_row(f, 'Dead Space 2 folder (holds deadspace2.exe)%s:' % (
            ', found automatically' if self.games else ''), self.game,
            (('Browse...', self.pick_game),), combo=self.games or None)
        if install:
            if not self.ffmpeg_bundled:
                self.path_row(f, 'ffmpeg.exe (decodes the Xbox audio):', self.ffmpeg,
                              (('Browse...', self.pick_ffmpeg),))
        self.space = ttk.Label(f, text='', justify='left')
        self.space.pack(anchor='w', pady=(14, 0))

    def page_ready(self):
        install = self.mode.get() == 'install'
        f = self.head_page('Ready to %s' % ('install' if install else 'remove'),
                           'The wizard is ready. Click %s to start.' % ('Install' if install else 'Remove'))
        lines = ['Dead Space 2 folder:\n    %s' % self.game.get()]
        if install:
            lines = ['Severed add-on:\n    %s' % self.addon.get()] + lines + [
                'Temporary files (about %d GB, deleted at the end):\n    %s' % (WORK_GB, self.work),
                'ffmpeg:\n    %s' % ('included' if self.ffmpeg_bundled else self.ffmpeg.get())]
        box = tk.Text(f, height=12, wrap='word', font=(FONT, 9), relief='solid', borderwidth=1, padx=8, pady=6)
        box.insert('end', '\n\n'.join(lines))
        box.config(state='disabled')
        box.pack(fill='both', expand=True)

    def page_installing(self):
        install = self.mode.get() == 'install'
        f = self.head_page('Installing' if install else 'Removing',
                           'Please wait while Severed is converted. This takes 15 minutes or more.' if install
                           else 'Please wait.')
        self.status = ttk.Label(f, text='Starting...')
        self.status.pack(anchor='w')
        self.bar = ttk.Progressbar(f, mode='indeterminate')
        self.bar.pack(fill='x', pady=(6, 10))
        self.bar.start(15)
        frame = tk.Frame(f, bg='#0c0c0c', bd=1, relief='sunken')
        frame.pack(fill='both', expand=True)
        self.term = tk.Text(frame, height=10, bg='#0c0c0c', fg='#cccccc', insertbackground='#cccccc', font=(MONO, 9),
                            wrap='none', relief='flat', padx=6, pady=4, state='disabled')
        sb = ttk.Scrollbar(frame, command=self.term.yview)
        self.term.config(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.term.pack(fill='both', expand=True)
        args = ['--game', self.game.get().strip()]
        if install:
            args = ['--severed', self.addon.get().strip()] + args + [
                '--work', self.work, '--ffmpeg', self.ffmpeg.get().strip()]
        else:
            args.append('--remove')
        threading.Thread(target=self.work_thread, args=(args,), daemon=True).start()

    def page_finish(self):
        f = self.side_page()
        install = self.mode.get() == 'install'
        if self.ok:
            title = 'Severed is installed' if install else 'Severed is removed'
            text = ('Start Dead Space 2 and choose Single Player > New Game > Episode Select > Dead Space 2: Severed.'
                    if install else 'Dead Space 2 is back to normal.')
        else:
            title = 'Setup did not finish'
            text = ('%s\n\nThe log is saved as make_severed_test.log next to this program. '
                    'Running the wizard again picks up where it stopped.' % (self.fail_msg or ''))
        ttk.Label(f, text=title, style='Big.TLabel').pack(anchor='w')
        ttk.Label(f, text='\n' + text, style='Body.TLabel', wraplength=440, justify='left').pack(anchor='w')
        if self.ok and install and os.path.isdir(self.work):
            ttk.Checkbutton(f, text='Delete the temporary files (severed_work)', variable=self.cleanup).pack(
                anchor='w', pady=(16, 0))

    # ---- input checks ----------------------------------------------------------

    def problem(self):
        name = self.PAGES[self.page]
        if name != 'locations':
            return None
        if not os.path.isfile(os.path.join(self.game.get().strip(), gamefind.EXE)):
            return 'The Dead Space 2 folder must hold deadspace2.exe.'
        if self.mode.get() != 'install':
            return None
        if not addon_kind(self.addon.get().strip()):
            return 'Choose the Severed add-on: the package file, or a file in the folder it was unpacked to.'
        if not os.path.isfile(self.ffmpeg.get().strip()):
            return 'Choose ffmpeg.exe.'
        return None

    def refresh(self):
        bad = self.problem()
        if self.PAGES[self.page] == 'locations':
            self.next.config(state='disabled' if bad is not None else 'normal')
        if self.PAGES[self.page] == 'locations' and getattr(self, 'space', None):
            lines = [bad] if bad else []
            if self.mode.get() == 'install':
                for label, path, need in (('temporary files (next to this program)', self.work, WORK_GB),
                                          ('game folder', self.game.get(), GAME_GB)):
                    g = free_gb(path.strip()) if path.strip() else None
                    if g is not None:
                        lines.append('Free space for the %s: %.1f GB (needs about %s GB)%s'
                                     % (label, g, need, '' if g >= need else '  - not enough'))
            try:
                self.space.config(text='\n'.join(lines), style='Warn.TLabel' if bad else 'TLabel')
            except tk.TclError:
                pass

    # ---- buttons ---------------------------------------------------------------

    def on_next(self):
        name = self.PAGES[self.page]
        if name == 'finish':
            if self.ok and self.mode.get() == 'install' and self.cleanup.get() and os.path.isdir(self.work):
                self.root.config(cursor='watch')
                self.root.update()
                shutil.rmtree(self.work, ignore_errors=True)
            self.root.destroy()
            return
        if self.problem():
            return
        self.page += 1
        self.show()

    def on_back(self):
        if self.page > 0:
            self.page -= 1
            self.show()

    def on_cancel(self):
        if self.PAGES[self.page] == 'installing':
            if messagebox.askyesno('Cancel', 'Stop the conversion? Running the wizard again picks up '
                                   'where it stopped.', icon='warning'):
                os._exit(1)
            return
        if self.PAGES[self.page] == 'finish' or messagebox.askyesno('Cancel', 'Exit the setup wizard?'):
            self.root.destroy()

    def pick_addon(self):
        p = filedialog.askopenfilename(title='The Severed add-on file (29E2FCC0...), or any file in its unpacked folder')
        if p:
            self.addon.set(addon_root(os.path.normpath(p)))

    def pick_game(self):
        p = filedialog.askdirectory(title='The Dead Space 2 folder (holds deadspace2.exe)')
        if p:
            self.game.set(os.path.normpath(p))

    def pick_ffmpeg(self):
        p = filedialog.askopenfilename(title='ffmpeg.exe', filetypes=[('ffmpeg', 'ffmpeg.exe'), ('All files', '*.*')])
        if p:
            self.ffmpeg.set(os.path.normpath(p))

    # ---- the conversion ----------------------------------------------------------

    def work_thread(self, args):
        """runs the converter on this thread, its printed log sent to the window"""
        old = sys.stdout, sys.argv
        sys.stdout, sys.argv = Pipe(self.q), ['make_severed_test.py'] + args
        ok, msg = True, ''
        try:
            import make_severed_test
            make_severed_test.main()
            game = args[args.index('--game') + 1]
            if '--remove' in args:
                remove_hook(game, make_severed_test.log)
            else:
                make_severed_test.log('Installing the hook that adds Severed to the episode select')
                install_hook(game, make_severed_test.log)
        except SystemExit as e:
            if e.code not in (None, 0):
                ok, msg = False, str(e.code)
        except Exception as e:                      # shown, not lost: the user sends the log
            import traceback
            traceback.print_exc(file=sys.stdout)
            ok, msg = False, 'Stopped by an error: %s' % e
        finally:
            sys.stdout, sys.argv = old
        self.q.put(('end', ok, msg))

    def drain(self):
        try:
            while True:
                item = self.q.get_nowait()
                if isinstance(item, tuple):
                    self.ok, self.fail_msg = item[1], item[2]
                    self.page = self.PAGES.index('finish')
                    self.show()
                    continue
                if self.PAGES[self.page] != 'installing':
                    continue
                self.term.config(state='normal')
                self.term.insert('end', item)
                self.term.see('end')
                self.term.config(state='disabled')
                for line in item.splitlines():
                    s = line[9:] if line[:2].isdigit() and line[2:3] == ':' else line
                    if s and not s.startswith(' '):          # a step headline, not a detail line
                        self.status.config(text=s[:110])
        except queue.Empty:
            pass
        self.root.after(100, self.drain)


def selftest():
    """--selftest: loads every converter data file, the native library and
    ffmpeg, to check a built app carries all its parts. Also written to
    selftest.txt next to the app (a windowed app has no console)."""
    import json
    import pickle
    import subprocess
    import make_severed_test  # noqa: F401  (imports the converters)
    from ds2 import addoncheck, build, eaaudio
    here = os.path.dirname(build.__file__)
    names = sorted(f for f in os.listdir(here) if f.endswith(('.pkl', '.json')))
    for f in names:
        with open(os.path.join(here, f), 'rb') as fh:
            (pickle.load if f.endswith('.pkl') else json.load)(fh)
    eaaudio._lib()
    ff = bundled_ffmpeg()
    ffv = 'not found'
    if ff:
        r = subprocess.run([ff, '-hide_banner', '-decoders'], capture_output=True, text=True,
                           creationflags=subprocess.CREATE_NO_WINDOW if WIN else 0)
        ffv = 'xma2 decoder ' + ('present' if ' xma2 ' in r.stdout else 'MISSING')
    hook = bundled_hook()
    hv = 'present' if hook and is_our_hook(hook) else 'MISSING'
    msg = ('selftest ok: %d data files, %d expected add-on files, native library loaded, ffmpeg %s, hook %s'
           % (len(names), len(addoncheck.expected()), ffv, hv))
    with open(os.path.join(APP_DIR, 'selftest.txt'), 'w') as f:
        f.write(msg + '\n')
    if sys.stdout:
        print(msg)
    if 'MISSING' in msg or (FROZEN and not ff):
        raise SystemExit(1)


def main():
    if len(sys.argv) > 1:                        # command line: the converter's own options
        if sys.argv[1] == '--selftest':
            return selftest()
        import make_severed_test
        return make_severed_test.main()
    root = tk.Tk()
    Wizard(root)
    root.mainloop()


if __name__ == '__main__':
    main()
