"""Aparencia da aba Modelar: cores e pecas de tela (botoes, campos, dicas) com cara de programa profissional."""
import tkinter as tk
import modelar_icones as ic

BG = '#0B0E14'; PAINEL = '#131822'; PAINEL2 = '#1A2130'; FAIXA = '#161C28'; BORDA = '#27303F'; BORDA2 = '#34405A'
TXT = '#E6ECF5'; DIM = '#8C99AE'; FRACO = '#5F6C83'; CAMPO = '#0A0D13'
ACENTO = '#FF8A3D'; AZUL = '#4EA3FF'; VERDE = '#38D39F'; VERM = '#FF6B6B'; AMARELO = '#F7C948'
F = 'Segoe UI'


def _hover(w, normal, sobre):
    w.bind('<Enter>', lambda e: w.cget('state') != 'disabled' and w.config(bg=sobre), add='+'); w.bind('<Leave>', lambda e: w.config(bg=normal), add='+')


def botao(pai, texto, cmd, tipo='normal', icone=None, tam=10, larg=None):
    """tipo: normal (cinza) | primario (laranja) | ok (verde) | azul | perigo | liso (sem fundo)."""
    bg, fg, sobre = {'normal': (PAINEL2, TXT, BORDA2), 'primario': (ACENTO, '#14100C', '#FFA35F'), 'ok': (VERDE, '#07140F', '#5BE3B5'), 'azul': (AZUL, '#08131F', '#7BBBFF'),
                     'perigo': ('#3A1F24', '#FF9B9B', '#55262D'), 'liso': (pai.cget('bg'), DIM, PAINEL2)}[tipo]
    kw = dict(text=texto, command=cmd, bg=bg, fg=fg, activebackground=sobre, activeforeground=fg, relief='flat', bd=0, cursor='hand2', font=(F, tam, 'bold' if tipo != 'liso' else 'normal'),
              padx=12, pady=6, disabledforeground=FRACO, highlightthickness=0)
    if icone: kw.update(image=ic.icone(icone, 18), compound='left', padx=10)
    if larg: kw['width'] = larg
    b = tk.Button(pai, **kw); _hover(b, bg, sobre); return b


class BotaoFerramenta(tk.Frame):
    """Botao da faixa de ferramentas: icone em cima, nome em baixo."""
    def __init__(self, pai, icone, texto, cmd, dica='', larg=None):
        if larg is None:                                     # largura justa para o nome caber (a faixa tem muitos botoes)
            import tkinter.font as tkf
            larg = max(46, tkf.Font(family=F, size=8).measure(texto) + 12)
        super().__init__(pai, bg=FAIXA, cursor='hand2', width=larg, height=62); self.pack_propagate(False); self.cmd = cmd; self.ativo = False; self.ligado = True
        self.li = tk.Label(self, image=ic.icone(icone, 28), bg=FAIXA); self.li.pack(pady=(6, 0))
        self.lt = tk.Label(self, text=texto, bg=FAIXA, fg='#C8D2E2', font=(F, 8)); self.lt.pack()
        for w in (self, self.li, self.lt):
            w.bind('<Enter>', lambda e: self._cor(PAINEL2 if not self.ativo else '#3A2A1C')); w.bind('<Leave>', lambda e: self._cor(None)); w.bind('<Button-1>', lambda e: self.ligado and self.cmd())
        if dica: Dica(self, dica, (self.li, self.lt))

    def _cor(self, c):
        c = c or ('#33241A' if self.ativo else FAIXA)
        for w in (self, self.li, self.lt): w.config(bg=c)

    def marcar(self, sim):
        self.ativo = sim; self._cor(None); self.lt.config(fg=ACENTO if sim else '#C8D2E2')


def campo(pai, var, larg=9, mono=False):
    """Caixa de digitar com borda que acende quando esta em uso."""
    f = tk.Frame(pai, bg=BORDA, highlightthickness=0)
    e = tk.Entry(f, textvariable=var, width=larg, bg=CAMPO, fg=TXT, insertbackground=TXT, relief='flat', bd=0, font=('Consolas' if mono else F, 10), disabledbackground=PAINEL, disabledforeground=FRACO)
    e.pack(padx=1, pady=1, ipady=4, ipadx=4, fill='x', expand=True)
    e.bind('<FocusIn>', lambda ev: f.config(bg=ACENTO), add='+'); e.bind('<FocusOut>', lambda ev: f.config(bg=BORDA), add='+'); f.entry = e
    return f


def escolha(pai, var, valores, larg=12, cmd=None):
    om = tk.OptionMenu(pai, var, *valores, command=cmd)
    om.config(bg=CAMPO, fg=TXT, activebackground=PAINEL2, activeforeground=TXT, highlightthickness=1, highlightbackground=BORDA, bd=0, relief='flat', anchor='w', font=(F, 10), width=larg, padx=8, pady=4, indicatoron=True)
    om['menu'].config(bg=PAINEL2, fg=TXT, activebackground=ACENTO, activeforeground='#14100C', font=(F, 10), bd=0)
    return om


def marca(pai, texto, var, cmd=None):
    return tk.Checkbutton(pai, text=texto, variable=var, command=cmd, bg=pai.cget('bg'), fg=TXT, selectcolor=CAMPO, activebackground=pai.cget('bg'), activeforeground=TXT, font=(F, 10), bd=0, highlightthickness=0, cursor='hand2')


def rotulo(pai, texto, cor=DIM, tam=9, negrito=False, **kw):
    return tk.Label(pai, text=texto, bg=pai.cget('bg'), fg=cor, font=(F, tam, 'bold' if negrito else 'normal'), anchor='w', **kw)


def titulo(pai, texto):
    f = tk.Frame(pai, bg=pai.cget('bg')); tk.Frame(f, bg=ACENTO, width=3, height=14).pack(side='left', padx=(0, 7))
    tk.Label(f, text=texto.upper(), bg=pai.cget('bg'), fg='#C8D2E2', font=(F, 9, 'bold')).pack(side='left'); return f


def painel(pai, **kw):
    return tk.Frame(pai, bg=PAINEL, highlightthickness=1, highlightbackground=BORDA, **kw)


def linha(pai, vertical=False):
    return tk.Frame(pai, bg=BORDA, width=1 if vertical else 0, height=0 if vertical else 1)


class Dica:
    """Balaozinho de ajuda que aparece ao parar o mouse em cima."""
    def __init__(self, w, texto, extras=()):
        self.w = w; self.texto = texto; self.tip = None; self.job = None
        for x in (w,) + tuple(extras):
            x.bind('<Enter>', self._entra, add='+'); x.bind('<Leave>', self._sai, add='+'); x.bind('<Button-1>', self._sai, add='+')

    def _entra(self, e):
        self._cancela(); self.job = self.w.after(550, self._mostra)

    def _cancela(self):
        if self.job:
            try: self.w.after_cancel(self.job)
            except Exception: pass
            self.job = None

    def _sai(self, e=None):
        self._cancela()
        if self.tip:
            try: self.tip.destroy()
            except Exception: pass
            self.tip = None

    def _mostra(self):
        self.job = None
        if self.tip or not self.w.winfo_exists(): return
        t = tk.Toplevel(self.w); t.wm_overrideredirect(True); t.attributes('-topmost', True)
        t.geometry('+%d+%d' % (self.w.winfo_rootx() + 4, self.w.winfo_rooty() + self.w.winfo_height() + 6))
        tk.Label(t, text=self.texto, bg='#F4F6FA', fg='#10151D', font=(F, 9), justify='left', wraplength=300, padx=8, pady=5, bd=0).pack(); self.tip = t


class Rolavel(tk.Frame):
    """Area com rolagem (roda do mouse). O conteudo vai em .dentro"""
    def __init__(self, pai, bg=PAINEL, **kw):
        super().__init__(pai, bg=bg, **kw)
        self.c = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0); self.sb = tk.Scrollbar(self, orient='vertical', command=self.c.yview, width=10)
        self.dentro = tk.Frame(self.c, bg=bg); self.win = self.c.create_window((0, 0), window=self.dentro, anchor='nw')
        self.c.configure(yscrollcommand=self._rolou); self.c.pack(side='left', fill='both', expand=True)
        self.dentro.bind('<Configure>', lambda e: self.c.configure(scrollregion=self.c.bbox('all')))
        self.c.bind('<Configure>', lambda e: self.c.itemconfig(self.win, width=e.width))
        for w in (self.c, self.dentro): w.bind('<Enter>', lambda e: self.c.bind_all('<MouseWheel>', self._roda), add='+'); w.bind('<Leave>', lambda e: self.c.unbind_all('<MouseWheel>'), add='+')

    def _rolou(self, a, b):
        self.sb.set(a, b)
        if float(a) <= 0.0 and float(b) >= 1.0: self.sb.pack_forget()
        elif not self.sb.winfo_ismapped(): self.sb.pack(side='right', fill='y')

    def _roda(self, e):
        a, b = self.c.yview()
        if a <= 0.0 and b >= 1.0: return
        self.c.yview_scroll(int(-e.delta / 120) * 2, 'units')

    def limpar(self):
        for w in self.dentro.winfo_children(): w.destroy()
        self.c.yview_moveto(0)
