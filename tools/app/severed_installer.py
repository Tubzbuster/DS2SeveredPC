"""DS2SeveredPC installer: a classic setup wizard around the converter
(tools/test/make_severed_test.py), so nobody needs the command line.

Pages: Welcome (install or remove), Before you start, Locations (the
Severed add-on, the Dead Space 2 folder, a working folder; ffmpeg when it is
not bundled), Ready, Installing (progress and the converter's log in a
terminal box), Finish.

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
VERSION = '0.4.0'
WORK_GB, GAME_GB = 10, 3.5
WIN = sys.platform == 'win32'
FONT = 'Segoe UI' if WIN else 'DejaVu Sans'
MONO = 'Consolas' if WIN else 'DejaVu Sans Mono'
BANNER_BG, BANNER_FG, ACCENT = '#14171a', '#d8dde2', '#b3261e'


def bundled_ffmpeg():
    for p in (os.path.join(APP_DIR, 'ffmpeg', 'ffmpeg.exe'), os.path.join(APP_DIR, 'ffmpeg', 'ffmpeg')):
        if os.path.isfile(p):
            return p
    return shutil.which('ffmpeg')


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


class Pipe(io.TextIOBase):
    """stdout replacement: the converter's lines go to the window"""
    def __init__(self, q):
        self.q = q

    def write(self, s):
        self.q.put(s)
        return len(s)


class Wizard:
    PAGES = ('welcome', 'notice', 'locations', 'ready', 'installing', 'finish')

    def __init__(self, root):
        self.root = root
        root.title('%s Setup' % TITLE)
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
        self.agree = tk.BooleanVar(value=False)
        self.addon = tk.StringVar()
        found = gamefind.find()
        self.games = found
        self.game = tk.StringVar(value=found[0] if found else '')
        self.work = tk.StringVar()
        self.ffmpeg = tk.StringVar(value=bundled_ffmpeg() or '')
        self.ffmpeg_bundled = bool(self.ffmpeg.get())
        self.ok = None
        self.addon.trace_add('write', self._default_work)

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

    def side_page(self):
        """Welcome / Finish: the dark banner on the left, white text area"""
        f = tk.Frame(self.body, bg='white')
        f.pack(fill='both', expand=True)
        banner = tk.Canvas(f, width=190, bg=BANNER_BG, highlightthickness=0)
        banner.pack(side='left', fill='y')
        banner.create_rectangle(0, 0, 6, 2000, fill=ACCENT, width=0)
        banner.create_text(24, 40, anchor='nw', text='DEAD SPACE 2', fill=BANNER_FG, font=(FONT, 13, 'bold'))
        banner.create_text(24, 72, anchor='nw', text='SEVERED', fill=ACCENT, font=(FONT, 19, 'bold'))
        banner.create_text(24, 112, anchor='nw', text='for PC', fill='#8a939b', font=(FONT, 10))
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
        self.back.config(state='normal' if name in ('notice', 'locations', 'ready') else 'disabled')
        self.next.config(text={'ready': 'Install' if self.mode.get() == 'install' else 'Remove',
                               'finish': 'Finish'}.get(name, 'Next >'))
        self.next.config(state='disabled' if name == 'installing' else 'normal')
        self.cancel.config(state='disabled' if name == 'finish' else 'normal')
        self.refresh()

    def page_welcome(self):
        f = self.side_page()
        ttk.Label(f, text='Welcome to the %s Setup Wizard' % TITLE, style='Big.TLabel',
                  justify='left', wraplength=440).pack(anchor='w')
        ttk.Label(f, style='Body.TLabel', wraplength=440, justify='left', text=(
            '\nThis wizard converts your own copy of the Xbox 360 add-on "Dead Space 2: '
            'Severed" for the PC version of Dead Space 2. Severed is then started from '
            'Single Player > Episode Select.\n\n'
            'Converting takes about an hour. It can be stopped and started again: it '
            'picks up where it left off.\n\nWhat would you like to do?')).pack(anchor='w')
        for v, t in (('install', 'Install Severed'), ('remove', 'Remove Severed from the game')):
            ttk.Radiobutton(f, text=t, value=v, variable=self.mode, style='White.TRadiobutton').pack(
                anchor='w', padx=8, pady=2)

    def page_notice(self):
        f = self.head_page('Before you start', 'Please read the following.')
        box = tk.Text(f, height=11, wrap='word', font=(FONT, 9), relief='solid', borderwidth=1, padx=8, pady=6)
        box.insert('end', (
            'DS2SeveredPC contains no game files. It converts files you supply from your own '
            'legitimate copy of the Severed add-on, for use with your own legitimate copy of '
            'Dead Space 2 for PC (Steam or retail).\n\n'
            'It adds one archive, DS2DAT2.DAT, to the game folder and changes nothing else in '
            'it. Remove Severed (in this wizard) takes that archive out again.\n\n'
            'This is a fan project, free and non-commercial, not made or endorsed by Electronic '
            'Arts. It is provided as is, without warranty of any kind. Back up your saves.\n\n'
            'Dead Space, Dead Space 2 and Dead Space 2: Severed are trademarks of Electronic Arts '
            'Inc. ffmpeg (included, LGPL) decodes the Xbox audio; its licence is in the ffmpeg '
            'folder next to this program.'))
        box.config(state='disabled')
        box.pack(fill='both', expand=True)
        ttk.Checkbutton(f, text='I own both the Severed add-on and Dead Space 2 for PC',
                        variable=self.agree, command=self.refresh).pack(anchor='w', pady=(10, 0))

    def path_row(self, f, label, var, buttons, combo=None):
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
        var.trace_add('write', lambda *a: self.refresh())

    def page_locations(self):
        install = self.mode.get() == 'install'
        f = self.head_page('Choose locations', 'Point the wizard at your files.' if install
                           else 'Choose the game folder to remove Severed from.')
        if install:
            self.path_row(f, 'Severed add-on (the package file 29E2FCC0..., or a folder it was unpacked to):',
                          self.addon, (('File...', self.pick_addon_file), ('Folder...', self.pick_addon_dir)))
        self.path_row(f, 'Dead Space 2 folder (holds deadspace2.exe)%s:' % (
            ', found automatically' if self.games else ''), self.game,
            (('Browse...', self.pick_game),), combo=self.games or None)
        if install:
            self.path_row(f, 'Working folder (temporary files, about %d GB):' % WORK_GB, self.work,
                          (('Browse...', self.pick_work),))
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
                'Working folder:\n    %s' % self.work.get(),
                'ffmpeg:\n    %s' % ('included' if self.ffmpeg_bundled else self.ffmpeg.get())]
        box = tk.Text(f, height=12, wrap='word', font=(FONT, 9), relief='solid', borderwidth=1, padx=8, pady=6)
        box.insert('end', '\n\n'.join(lines))
        box.config(state='disabled')
        box.pack(fill='both', expand=True)

    def page_installing(self):
        install = self.mode.get() == 'install'
        f = self.head_page('Installing' if install else 'Removing',
                           'Please wait while Severed is converted. This takes about an hour.' if install
                           else 'Please wait.')
        self.status = ttk.Label(f, text='Starting...')
        self.status.pack(anchor='w')
        self.bar = ttk.Progressbar(f, mode='indeterminate')
        self.bar.pack(fill='x', pady=(6, 10))
        self.bar.start(15)
        frame = tk.Frame(f, bg='#0c0c0c', bd=1, relief='sunken')
        frame.pack(fill='both', expand=True)
        self.term = tk.Text(frame, bg='#0c0c0c', fg='#cccccc', insertbackground='#cccccc', font=(MONO, 9),
                            wrap='none', relief='flat', padx=6, pady=4, state='disabled')
        sb = ttk.Scrollbar(frame, command=self.term.yview)
        self.term.config(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.term.pack(fill='both', expand=True)
        args = ['--game', self.game.get().strip()]
        if install:
            args = ['--severed', self.addon.get().strip()] + args + [
                '--work', self.work.get().strip(), '--ffmpeg', self.ffmpeg.get().strip()]
        else:
            args.append('--remove')
        threading.Thread(target=self.work_thread, args=(args,), daemon=True).start()

    def page_finish(self):
        f = self.side_page()
        install = self.mode.get() == 'install'
        if self.ok:
            title = 'Severed is installed' if install else 'Severed is removed'
            text = ('Start Dead Space 2 and choose Single Player > Episode Select > Dead Space 2: Severed.'
                    if install else 'Dead Space 2 is back to normal.')
        else:
            title = 'Setup did not finish'
            text = ('%s\n\nThe log is saved as make_severed_test.log next to this program. '
                    'Running the wizard again picks up where it stopped.' % (self.fail_msg or ''))
        ttk.Label(f, text=title, style='Big.TLabel').pack(anchor='w')
        ttk.Label(f, text='\n' + text, style='Body.TLabel', wraplength=440, justify='left').pack(anchor='w')

    # ---- input checks ----------------------------------------------------------

    def _default_work(self, *a):
        """the converter's own default: severed_work next to the add-on"""
        p = self.addon.get().strip()
        if p and (not self.work.get().strip() or self.work.get() == getattr(self, '_auto_work', None)):
            self._auto_work = os.path.join(os.path.dirname(os.path.normpath(p)), 'severed_work')
            self.work.set(self._auto_work)

    def problem(self):
        name = self.PAGES[self.page]
        if name == 'notice' and not self.agree.get():
            return ''
        if name != 'locations':
            return None
        if not os.path.isfile(os.path.join(self.game.get().strip(), gamefind.EXE)):
            return 'The Dead Space 2 folder must hold deadspace2.exe.'
        if self.mode.get() != 'install':
            return None
        if not os.path.exists(self.addon.get().strip()):
            return 'Choose the Severed add-on file or its folder.'
        if not self.work.get().strip():
            return 'Choose a working folder.'
        if not os.path.isfile(self.ffmpeg.get().strip()):
            return 'Choose ffmpeg.exe.'
        return None

    def refresh(self):
        bad = self.problem()
        if self.PAGES[self.page] in ('notice', 'locations'):
            self.next.config(state='disabled' if bad is not None else 'normal')
        if self.PAGES[self.page] == 'locations' and getattr(self, 'space', None):
            lines = [bad] if bad else []
            if self.mode.get() == 'install':
                for label, path, need in (('working folder', self.work.get(), WORK_GB),
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

    def pick_addon_file(self):
        p = filedialog.askopenfilename(title='The Severed add-on file (29E2FCC0...)')
        if p:
            self.addon.set(os.path.normpath(p))

    def pick_addon_dir(self):
        p = filedialog.askdirectory(title='The folder the Severed add-on was unpacked to')
        if p:
            self.addon.set(os.path.normpath(p))

    def pick_game(self):
        p = filedialog.askdirectory(title='The Dead Space 2 folder (holds deadspace2.exe)')
        if p:
            self.game.set(os.path.normpath(p))

    def pick_work(self):
        p = filedialog.askdirectory(title='Working folder (about %d GB of temporary files)' % WORK_GB)
        if p:
            self.work.set(os.path.normpath(p))

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
        r = subprocess.run([ff, '-hide_banner', '-decoders'], capture_output=True, text=True)
        ffv = 'xma2 decoder ' + ('present' if ' xma2 ' in r.stdout else 'MISSING')
    msg = ('selftest ok: %d data files, %d expected add-on files, native library loaded, ffmpeg %s'
           % (len(names), len(addoncheck.expected()), ffv))
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
