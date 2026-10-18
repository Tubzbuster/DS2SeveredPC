"""DS2SeveredPC installer: a window around the converter
(tools/test/make_severed_test.py), so nobody needs the command line.

It asks for the Severed add-on (the package file, or a folder it was
unpacked to), the Dead Space 2 folder and ffmpeg.exe, then runs the same
conversion as Make-SeveredTest.bat, showing its log. Remove takes the
Severed archive out of the game folder again.

    py -3 severed_installer.py
Built into a Windows app with PyInstaller (build_app.bat), carrying its own
Python, so users need nothing installed.
"""
import io
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

HERE = os.path.dirname(os.path.abspath(__file__))
if not getattr(sys, 'frozen', False):            # the built app carries the converter inside
    sys.path.insert(0, os.path.join(HERE, '..', 'test'))

STEAM_GUESSES = (r'C:\Program Files (x86)\Steam\steamapps\common\Dead Space 2',
                 r'C:\Program Files\Steam\steamapps\common\Dead Space 2',
                 r'C:\Program Files (x86)\Origin Games\Dead Space 2',
                 r'C:\Program Files (x86)\EA Games\Dead Space 2')


def guess_game():
    for p in STEAM_GUESSES:
        if os.path.exists(os.path.join(p, 'deadspace2.exe')):
            return p
    return ''


class Pipe(io.TextIOBase):
    """stdout replacement: the converter's lines go to the window"""
    def __init__(self, q):
        self.q = q

    def write(self, s):
        self.q.put(s)
        return len(s)


class App:
    def __init__(self, root):
        self.root = root
        root.title('DS2SeveredPC')
        root.minsize(640, 420)
        self.q = queue.Queue()
        self.busy = False
        self.addon = tk.StringVar()
        self.game = tk.StringVar(value=guess_game())
        self.ffmpeg = tk.StringVar()
        form = tk.Frame(root, padx=10, pady=10)
        form.pack(fill='x')
        form.columnconfigure(1, weight=1)
        self.row(form, 0, 'A) Severed add-on (file or unpacked folder)', self.addon, self.pick_addon)
        self.row(form, 1, 'B) Dead Space 2 folder (retail or Steam)', self.game, self.pick_game)
        self.row(form, 2, 'ffmpeg.exe (decodes the Xbox audio)', self.ffmpeg, self.pick_ffmpeg)
        bar = tk.Frame(root, padx=10)
        bar.pack(fill='x')
        self.install = tk.Button(bar, text='Install Severed', width=16, command=self.run_install)
        self.install.pack(side='left')
        self.remove = tk.Button(bar, text='Remove', width=10, command=self.run_remove)
        self.remove.pack(side='left', padx=8)
        tk.Label(bar, text='Needs about 10 GB free next to the add-on and 3.5 GB in the game folder.',
                 fg='#555').pack(side='left', padx=8)
        self.log = scrolledtext.ScrolledText(root, height=16, state='disabled', font=('Consolas', 9))
        self.log.pack(fill='both', expand=True, padx=10, pady=10)
        root.after(100, self.drain)

    def row(self, parent, r, label, var, browse):
        tk.Label(parent, text=label, anchor='w').grid(row=r, column=0, sticky='w', pady=3)
        tk.Entry(parent, textvariable=var).grid(row=r, column=1, sticky='ew', padx=6)
        tk.Button(parent, text='Browse...', command=browse).grid(row=r, column=2)

    def pick_addon(self):
        p = filedialog.askopenfilename(title='The Severed add-on file (29E2FCC0...)')
        if not p:
            p = filedialog.askdirectory(title='Or: the folder the add-on was unpacked to')
        if p:
            self.addon.set(os.path.normpath(p))

    def pick_game(self):
        p = filedialog.askdirectory(title='The Dead Space 2 folder (holds deadspace2.exe)')
        if p:
            self.game.set(os.path.normpath(p))

    def pick_ffmpeg(self):
        p = filedialog.askopenfilename(title='ffmpeg.exe', filetypes=[('ffmpeg', 'ffmpeg.exe'), ('All files', '*.*')])
        if p:
            self.ffmpeg.set(os.path.normpath(p))

    def problems(self, install):
        game = self.game.get().strip()
        if not os.path.exists(os.path.join(game, 'deadspace2.exe')):
            return 'B) has no deadspace2.exe: pick the Dead Space 2 folder.'
        if install:
            if not os.path.exists(self.addon.get().strip()):
                return 'A) does not exist: pick the Severed add-on file or its unpacked folder.'
            if not os.path.isfile(self.ffmpeg.get().strip()):
                return 'Pick ffmpeg.exe.'
        return None

    def run_install(self):
        self.start(True, ['--severed', self.addon.get().strip(), '--game', self.game.get().strip(),
                          '--ffmpeg', self.ffmpeg.get().strip()])

    def run_remove(self):
        self.start(False, ['--game', self.game.get().strip(), '--remove'])

    def start(self, install, args):
        if self.busy:
            return
        bad = self.problems(install)
        if bad:
            messagebox.showwarning('DS2SeveredPC', bad)
            return
        self.busy = True
        self.install.config(state='disabled')
        self.remove.config(state='disabled')
        threading.Thread(target=self.work, args=(args,), daemon=True).start()

    def work(self, args):
        """runs the converter on this thread, its printed log sent to the window"""
        old = sys.stdout, sys.argv
        sys.stdout, sys.argv = Pipe(self.q), ['make_severed_test.py'] + args
        ok, msg = True, 'Done.'
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
                    self.finish(*item[1:])
                    continue
                self.log.config(state='normal')
                self.log.insert('end', item)
                self.log.see('end')
                self.log.config(state='disabled')
        except queue.Empty:
            pass
        self.root.after(100, self.drain)

    def finish(self, ok, msg):
        self.busy = False
        self.install.config(state='normal')
        self.remove.config(state='normal')
        (messagebox.showinfo if ok else messagebox.showerror)('DS2SeveredPC', msg)


def selftest():
    """--selftest: loads every converter data file and the native library,
    to check a built app carries all its parts"""
    import json
    import pickle
    import make_severed_test  # noqa: F401  (imports the converters)
    from ds2 import addoncheck, build, eaaudio
    here = os.path.dirname(build.__file__)
    names = sorted(f for f in os.listdir(here) if f.endswith(('.pkl', '.json')))
    for f in names:
        with open(os.path.join(here, f), 'rb') as fh:
            (pickle.load if f.endswith('.pkl') else json.load)(fh)
    eaaudio._lib()
    print('selftest ok: %d data files, %d expected add-on files, native library loaded'
          % (len(names), len(addoncheck.expected())))


def main():
    if len(sys.argv) > 1:                        # command line: the converter's own options
        if sys.argv[1] == '--selftest':
            return selftest()
        import make_severed_test
        return make_severed_test.main()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
