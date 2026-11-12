"""Editor de DESENHO 2D da aba Modelar: desenhar com o mouse (retangulo, circulo, elipse, poligono, sextavado, rasgo, texto), com grade que
"gruda" de 1 em 1 mm e medidas digitadas. O desenho vira o 'perfil' usado por Extrudar, Revolucao, Transicao e Varrer.

Mouse: ferramenta escolhida + clicar e arrastar = desenhar · Selecionar: clicar = escolher, arrastar = mover · roda = zoom ·
botao direito arrastando = deslocar · Delete = apagar · Ctrl+Z = desfazer · Alt = sem grudar na grade.
"""
import math, copy
import numpy as np
import tkinter as tk
from tkinter import simpledialog
import modelar as md
import modelar_tema as T
import modelar_icones as ic

NOMES = {'ret': 'Retângulo', 'circ': 'Círculo', 'elipse': 'Elipse', 'reg': 'Polígono regular', 'rasgo': 'Rasgo', 'poli': 'Polígono livre', 'caminho': 'Caminho (linhas e arcos)', 'texto': 'Texto'}
CAMPOS = {'ret': [('l', 'Largura'), ('a', 'Altura'), ('r', 'Raio dos cantos'), ('x', 'Centro →'), ('y', 'Centro ↑'), ('g', 'Girar (graus)')],
          'circ': [('d', 'Diâmetro'), ('x', 'Centro →'), ('y', 'Centro ↑')],
          'elipse': [('l', 'Largura'), ('a', 'Altura'), ('x', 'Centro →'), ('y', 'Centro ↑'), ('g', 'Girar (graus)')],
          'reg': [('n', 'Número de lados'), ('d', 'Diâmetro (pontas)'), ('x', 'Centro →'), ('y', 'Centro ↑'), ('g', 'Girar (graus)')],
          'rasgo': [('c', 'Comprimento total'), ('l', 'Largura'), ('x', 'Centro →'), ('y', 'Centro ↑'), ('g', 'Girar (graus)')],
          'poli': [('x', 'Mover →'), ('y', 'Mover ↑'), ('g', 'Girar (graus)')],
          'caminho': [('x', 'Mover →'), ('y', 'Mover ↑'), ('g', 'Girar (graus)')],
          'texto': [('txt', 'Texto'), ('tam', 'Altura da letra'), ('fonte', 'Fonte'), ('x', 'Centro →'), ('y', 'Centro ↑'), ('g', 'Girar (graus)')]}
PADRAO = {'ret': dict(l=20, a=10, r=0, x=0, y=0, g=0), 'circ': dict(d=10, x=0, y=0), 'elipse': dict(l=20, a=10, x=0, y=0, g=0), 'reg': dict(n=6, d=20, x=0, y=0, g=0),
          'rasgo': dict(c=30, l=8, x=0, y=0, g=0), 'poli': dict(pts=[], x=0, y=0, g=0), 'texto': dict(txt='Texto', tam=10, fonte='Arial', x=0, y=0, g=0)}


def _n(v, vs, p=0.0):
    try: return md.num(v, vs, p)
    except Exception: return p


def contorno(f, vs):
    """Pontos (n,2) do contorno de uma figura, ja girada e no lugar (para desenhar e para saber onde clicou)."""
    t = f.get('t'); P = None
    if t == 'ret':
        l, a = max(_n(f.get('l'), vs, 10), 0.01) / 2, max(_n(f.get('a'), vs, 10), 0.01) / 2; r = min(max(_n(f.get('r'), vs), 0), min(l, a) - 0.005)
        if r > 0.02:
            P = []
            for cx, cy, a0 in ((l - r, a - r, 0), (-l + r, a - r, 90), (-l + r, -a + r, 180), (l - r, -a + r, 270)):
                for k in range(9): ang = math.radians(a0 + k * 11.25); P.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        else: P = [(-l, -a), (l, -a), (l, a), (-l, a)]
    elif t == 'circ':
        r = max(_n(f.get('d'), vs, 10), 0.01) / 2; P = [(r * math.cos(k * math.pi / 32), r * math.sin(k * math.pi / 32)) for k in range(64)]
    elif t == 'elipse':
        l, a = _n(f.get('l'), vs, 20) / 2, _n(f.get('a'), vs, 10) / 2; P = [(l * math.cos(k * math.pi / 32), a * math.sin(k * math.pi / 32)) for k in range(64)]
    elif t == 'reg':
        n = int(max(3, min(200, _n(f.get('n'), vs, 6)))); r = _n(f.get('d'), vs, 20) / 2; P = [(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)) for k in range(n)]
    elif t == 'rasgo':
        c, l = _n(f.get('c'), vs, 30), _n(f.get('l'), vs, 8); r = l / 2; m = max(c / 2 - r, 0.0)
        P = [(m + r * math.cos(math.radians(-90 + k * 11.25)), r * math.sin(math.radians(-90 + k * 11.25))) for k in range(17)] + [(-m + r * math.cos(math.radians(90 + k * 11.25)), r * math.sin(math.radians(90 + k * 11.25))) for k in range(17)]
    elif t == 'poli': P = [(_n(p[0], vs), _n(p[1], vs)) for p in f.get('pts', [])]
    elif t == 'caminho':
        try:
            p0 = (_n(f['ini'][0], vs), _n(f['ini'][1], vs)); P = [p0]
            for sg in f.get('seg', []):
                if sg[0] == 'l': p1 = (_n(sg[1], vs), _n(sg[2], vs)); P.append(p1)
                else:
                    pm = (_n(sg[1], vs), _n(sg[2], vs)); p1 = (_n(sg[3], vs), _n(sg[4], vs)); P += _arco3(p0, pm, p1)
                p0 = p1
        except Exception: P = [(0, 0)]
    elif t == 'texto':
        tam = _n(f.get('tam'), vs, 10); w = max(len(str(f.get('txt', ''))), 1) * tam * 0.62 / 2; P = [(-w, -tam / 2), (w, -tam / 2), (w, tam / 2), (-w, tam / 2)]
    if not P: return np.zeros((0, 2))
    P = np.array(P, dtype=float); g = math.radians(_n(f.get('g'), vs))
    if g: c, s = math.cos(g), math.sin(g); P = P @ np.array([[c, s], [-s, c]])
    return P + np.array([_n(f.get('x'), vs), _n(f.get('y'), vs)])


def _arco3(p0, pm, p1, n=14):
    """Pontos de um arco que passa por 3 pontos."""
    ax, ay = p0; bx, by = pm; cx, cy = p1; d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9: return [p1]
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    r = math.hypot(ax - ux, ay - uy); a0 = math.atan2(ay - uy, ax - ux); am = math.atan2(by - uy, bx - ux); a1 = math.atan2(cy - uy, cx - ux)
    def nrm(a): return a % (2 * math.pi)
    anti = nrm(am - a0) < nrm(a1 - a0); tot = nrm(a1 - a0) if anti else -nrm(a0 - a1)
    return [(ux + r * math.cos(a0 + tot * k / n), uy + r * math.sin(a0 + tot * k / n)) for k in range(1, n + 1)]


def _dentro(P, x, y):
    if len(P) < 3: return False
    xs, ys = P[:, 0], P[:, 1]; x2, y2 = np.roll(xs, -1), np.roll(ys, -1)
    c = ((ys > y) != (y2 > y)) & (x < (x2 - xs) * (y - ys) / np.where(y2 == ys, 1e-12, y2 - ys) + xs)
    return bool(c.sum() % 2)


def descrever(f, vs):
    t = f.get('t'); g = lambda k, p=0: '%g' % round(_n(f.get(k), vs, p), 2)
    s = {'ret': lambda: 'Retângulo %s × %s' % (g('l'), g('a')), 'circ': lambda: 'Círculo ø%s' % g('d'), 'elipse': lambda: 'Elipse %s × %s' % (g('l'), g('a')),
         'reg': lambda: 'Polígono %s lados ø%s' % (g('n', 6), g('d')), 'rasgo': lambda: 'Rasgo %s × %s' % (g('c'), g('l')), 'poli': lambda: 'Polígono livre (%d pontos)' % len(f.get('pts', [])),
         'caminho': lambda: 'Caminho (%d trechos)' % len(f.get('seg', [])), 'texto': lambda: 'Texto "%s"' % str(f.get('txt', ''))[:12]}.get(t, lambda: str(t))()
    return s + ('  — furo' if f.get('furo') else '')


class EditorEsboco(tk.Frame):
    def __init__(self, pai, perfil, variaveis, ao_concluir, ao_cancelar, titulo='Desenho', ref=None, eixo=False, eixos=('→', '↑')):
        super().__init__(pai, bg=T.BG)
        self.figs = copy.deepcopy(perfil or []); self.vs = variaveis or {}; self.ao_concluir = ao_concluir; self.ao_cancelar = ao_cancelar; self.ref = ref; self.eixo = eixo; self.eixos = eixos
        self.sel = None; self.ferr = 'sel'; self.zoom = 4.0; self.ox = 0.0; self.oy = 0.0; self._centrado = False
        self.arr = None; self.temp = None; self.pts = []; self.cursor = (0.0, 0.0); self.hist = []; self.bt = {}; self.vars_campo = {}; self._trava = False
        # ---- topo ----
        topo = tk.Frame(self, bg=T.FAIXA, highlightthickness=1, highlightbackground=T.BORDA); topo.pack(fill='x')
        tk.Label(topo, image=ic.icone('lapis', 20), bg=T.FAIXA).pack(side='left', padx=(12, 6), pady=8)
        tk.Label(topo, text=titulo, bg=T.FAIXA, fg=T.TXT, font=(T.F, 11, 'bold')).pack(side='left')
        T.botao(topo, 'CONCLUIR DESENHO', self.concluir, 'ok', 'ok').pack(side='right', padx=(6, 12), pady=6); T.botao(topo, 'Cancelar', self.cancelar, 'normal').pack(side='right', pady=6)
        self.dica = ''
        corpo = tk.Frame(self, bg=T.BG); corpo.pack(fill='both', expand=True)
        # ---- ferramentas (esquerda) ----
        esq = tk.Frame(corpo, bg=T.FAIXA, highlightthickness=1, highlightbackground=T.BORDA); esq.pack(side='left', fill='y')
        for k, nome, dica in (('sel', 'Selecionar', 'Clicar numa figura para escolher; arrastar para mover. Delete apaga.'), ('ret', 'Retângulo', 'Clique num canto e arraste até o canto oposto.'),
                              ('circ', 'Círculo', 'Clique no centro e arraste até a borda.'), ('elipse', 'Elipse', 'Clique num canto e arraste.'), ('reg', 'Sextavado', 'Polígono regular: clique no centro e arraste até uma ponta. O número de lados muda no painel.'),
                              ('rasgo', 'Rasgo', 'Furo oblongo: clique numa ponta e arraste até a outra.'), ('poli', 'Polígono', 'Clique ponto por ponto; duplo clique (ou clique no primeiro ponto) fecha a figura.'),
                              ('texto', 'Texto', 'Clique onde o texto vai ficar.')):
            b = T.BotaoFerramenta(esq, {'sel': 'selecionar', 'texto': 'texto'}.get(k, k), nome, lambda k=k: self.ferramenta(k), dica, larg=72); b.pack(pady=1); self.bt[k] = b
        # ---- painel (direita) ----
        dr = tk.Frame(corpo, bg=T.PAINEL, width=268, highlightthickness=1, highlightbackground=T.BORDA); dr.pack(side='right', fill='y'); dr.pack_propagate(False)
        T.titulo(dr, 'Figuras do desenho').pack(fill='x', padx=12, pady=(12, 6))
        self.lista = T.Rolavel(dr, T.PAINEL, height=170); self.lista.pack(fill='x', padx=8); self.lista.pack_propagate(False)
        T.linha(dr).pack(fill='x', pady=8)
        T.titulo(dr, 'Medidas da figura').pack(fill='x', padx=12, pady=(0, 6))
        self.props = T.Rolavel(dr, T.PAINEL); self.props.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        # ---- desenho ----
        self.c = tk.Canvas(corpo, bg='#0A0D13', highlightthickness=0, cursor='crosshair'); self.c.pack(side='left', fill='both', expand=True)
        self.c.bind('<Configure>', self._tamanho); self.c.bind('<ButtonPress-1>', self._b1); self.c.bind('<B1-Motion>', self._b1m); self.c.bind('<ButtonRelease-1>', self._b1s)
        self.c.bind('<Double-Button-1>', self._duplo); self.c.bind('<Motion>', self._mov); self.c.bind('<MouseWheel>', self._roda)
        for b in (2, 3): self.c.bind('<ButtonPress-%d>' % b, self._pan0); self.c.bind('<B%d-Motion>' % b, self._pan)
        self.c.bind('<Enter>', lambda e: self.c.focus_set())
        for k, fn in (('<Delete>', self.apagar), ('<Escape>', self._esc), ('<Return>', lambda e=None: self._fechar_poli()), ('<Control-z>', self.desfazer), ('<Control-Z>', self.desfazer)): self.c.bind(k, lambda e, fn=fn: fn())
        self.ferramenta('ret' if not self.figs else 'sel'); self._listar(); self._props()

    # ---------------- coordenadas ----------------
    def _tamanho(self, e):
        if not self._centrado and e.width > 50:
            self._centrado = True; self.enquadrar()
        self.desenhar()

    def enquadrar(self):
        W, H = max(self.c.winfo_width(), 100), max(self.c.winfo_height(), 100); cs = [contorno(f, self.vs) for f in self.figs]; cs = [c for c in cs if len(c)]
        if self.ref: cs.append(np.array([[self.ref[0], self.ref[1]], [self.ref[2], self.ref[3]]]))
        if cs:
            P = np.concatenate(cs); mn, mx = P.min(0), P.max(0); t = np.maximum(mx - mn, 20.0)
            self.zoom = float(min(W / (t[0] * 1.6), H / (t[1] * 1.6), 14.0)); c = (mn + mx) / 2
        else: self.zoom = min(W, H) / 110.0; c = np.array([25.0, 15.0]) if self.eixo else np.zeros(2)
        self.ox = W / 2 - c[0] * self.zoom; self.oy = H / 2 + c[1] * self.zoom

    def tela(self, u, v): return self.ox + u * self.zoom, self.oy - v * self.zoom

    def mundo(self, x, y): return (x - self.ox) / self.zoom, (self.oy - y) / self.zoom

    def _grude(self, u, v, ev=None):
        if ev is not None and ev.state & 0x20000: return round(u, 2), round(v, 2)          # Alt = livre
        p = 1.0 if self.zoom >= 2.2 else (5.0 if self.zoom >= 0.6 else 10.0)
        return round(u / p) * p, round(v / p) * p

    # ---------------- historico ----------------
    def _guardar(self): self.hist.append(copy.deepcopy(self.figs)); self.hist = self.hist[-60:]

    def desfazer(self):
        if self.hist: self.figs = self.hist.pop(); self.sel = None; self._listar(); self._props(); self.desenhar()

    # ---------------- ferramentas ----------------
    def ferramenta(self, k):
        self.ferr = k; self.pts = []; self.temp = None
        for n, b in self.bt.items(): b.marcar(n == k)
        self.dica = ({'sel': 'Clique numa figura para escolher · arraste para mover', 'ret': 'Clique e arraste: canto a canto', 'circ': 'Clique no centro e arraste até a borda', 'elipse': 'Clique e arraste',
                                 'reg': 'Clique no centro e arraste até uma ponta', 'rasgo': 'Clique numa ponta e arraste até a outra', 'poli': 'Clique ponto por ponto · duplo clique fecha', 'texto': 'Clique onde o texto vai ficar'}[k])
        self.c.config(cursor='arrow' if k == 'sel' else 'crosshair'); self.desenhar()

    def _esc(self):
        if self.pts or self.temp: self.pts = []; self.temp = None
        elif self.ferr != 'sel': self.ferramenta('sel')
        else: self.sel = None; self._listar(); self._props()
        self.desenhar()

    def _acertar(self, u, v):
        for i in range(len(self.figs) - 1, -1, -1):
            if _dentro(contorno(self.figs[i], self.vs), u, v): return i
        return None

    def _b1(self, ev):
        self.c.focus_set(); u, v = self.mundo(ev.x, ev.y); gu, gv = self._grude(u, v, ev)
        if self.ferr == 'sel':
            if self.sel is not None and self.figs[self.sel].get('t') == 'poli':              # arrastar um ponto do poligono
                P = contorno(self.figs[self.sel], self.vs)
                for k, p in enumerate(P):
                    sx, sy = self.tela(*p)
                    if abs(sx - ev.x) < 8 and abs(sy - ev.y) < 8 and not _n(self.figs[self.sel].get('g'), self.vs): self._guardar(); self.arr = ('pt', k); return
            i = self._acertar(u, v); self.sel = i; self._listar(); self._props()
            if i is not None:
                f = self.figs[i]; self.arr = ('mover', (gu, gv), (_n(f.get('x'), self.vs), _n(f.get('y'), self.vs)), False)
            self.desenhar(); return
        if self.ferr == 'poli':
            if len(self.pts) >= 3:
                sx, sy = self.tela(*self.pts[0])
                if abs(sx - ev.x) < 9 and abs(sy - ev.y) < 9: self._fechar_poli(); return
            if not self.pts or (gu, gv) != self.pts[-1]: self.pts.append((gu, gv))
            self.desenhar(); return
        if self.ferr == 'texto':
            t = simpledialog.askstring('Texto', 'Escreva o texto:', parent=self)
            if t and t.strip():
                self._guardar(); self.figs.append(dict(t='texto', txt=t.strip(), tam=10, fonte='Arial', x=gu, y=gv, g=0)); self.sel = len(self.figs) - 1; self.ferramenta('sel'); self._listar(); self._props()
            return
        self.arr = ('novo', (gu, gv)); self.temp = None

    def _b1m(self, ev):
        if not self.arr: return
        u, v = self.mundo(ev.x, ev.y); gu, gv = self._grude(u, v, ev); self.cursor = (gu, gv)
        if self.arr[0] == 'mover':
            _, p0, xy0, mexeu = self.arr; f = self.figs[self.sel]
            if not mexeu and (gu, gv) != p0: self._guardar(); self.arr = ('mover', p0, xy0, True)
            if (gu, gv) != p0 or mexeu: f['x'] = round(xy0[0] + gu - p0[0], 3); f['y'] = round(xy0[1] + gv - p0[1], 3)
            self._props(so_valores=True)
        elif self.arr[0] == 'pt':
            f = self.figs[self.sel]; f['pts'][self.arr[1]] = [round(gu - _n(f.get('x'), self.vs), 3), round(gv - _n(f.get('y'), self.vs), 3)]
        elif self.arr[0] == 'novo':
            (u0, v0) = self.arr[1]; t = self.ferr; du, dv = gu - u0, gv - v0; f = None
            if t in ('ret', 'elipse') and abs(du) > 0.01 and abs(dv) > 0.01: f = dict(PADRAO[t], t=t, l=round(abs(du), 3), a=round(abs(dv), 3), x=round(u0 + du / 2, 3), y=round(v0 + dv / 2, 3))
            elif t == 'circ' and math.hypot(du, dv) > 0.01: f = dict(t='circ', d=round(2 * math.hypot(du, dv), 2), x=u0, y=v0)
            elif t == 'reg' and math.hypot(du, dv) > 0.01: f = dict(t='reg', n=6, d=round(2 * math.hypot(du, dv), 2), x=u0, y=v0, g=round(math.degrees(math.atan2(dv, du)) / 15) * 15)
            elif t == 'rasgo' and math.hypot(du, dv) > 0.01:
                L = math.hypot(du, dv); lg = min(8.0, max(2.0, round(L / 3))); f = dict(t='rasgo', c=round(L + lg, 2), l=lg, x=round(u0 + du / 2, 3), y=round(v0 + dv / 2, 3), g=round(math.degrees(math.atan2(dv, du)), 1))
            self.temp = f
        self.desenhar()

    def _b1s(self, ev):
        a = self.arr; self.arr = None
        if a and a[0] == 'novo' and self.temp:
            self._guardar(); self.figs.append(self.temp); self.sel = len(self.figs) - 1; self.temp = None; self._listar(); self._props()
        elif a and a[0] in ('mover', 'pt'): self._listar(); self._props()
        self.temp = None; self.desenhar()

    def _duplo(self, ev):
        if self.ferr == 'poli': self._fechar_poli()

    def _fechar_poli(self):
        if self.ferr != 'poli': return
        pts = []
        for p in self.pts:
            if not pts or p != pts[-1]: pts.append(p)
        if len(pts) >= 3:
            self._guardar(); self.figs.append(dict(t='poli', pts=[[round(p[0], 3), round(p[1], 3)] for p in pts], x=0, y=0, g=0)); self.sel = len(self.figs) - 1
        self.pts = []; self._listar(); self._props(); self.desenhar()

    def _mov(self, ev):
        u, v = self.mundo(ev.x, ev.y); self.cursor = self._grude(u, v, ev)
        if self.ferr != 'sel' or self.pts: self.desenhar()
        else: self._rodape()

    def _roda(self, ev):
        u, v = self.mundo(ev.x, ev.y); self.zoom = max(0.25, min(60.0, self.zoom * (1.15 ** (ev.delta / 120.0)))); self.ox = ev.x - u * self.zoom; self.oy = ev.y + v * self.zoom; self.desenhar()

    def _pan0(self, ev): self._p = (ev.x, ev.y)

    def _pan(self, ev):
        self.ox += ev.x - self._p[0]; self.oy += ev.y - self._p[1]; self._p = (ev.x, ev.y); self.desenhar()

    def apagar(self):
        if self.sel is not None and 0 <= self.sel < len(self.figs):
            self._guardar(); self.figs.pop(self.sel); self.sel = None; self._listar(); self._props(); self.desenhar()

    # ---------------- desenhar ----------------
    def desenhar(self):
        c = self.c; c.delete('all'); W, H = c.winfo_width(), c.winfo_height()
        if W < 20: return
        u0, v1 = self.mundo(0, 0); u1, v0 = self.mundo(W, H)
        p = 1.0 if self.zoom >= 6 else (5.0 if self.zoom >= 1.3 else (10.0 if self.zoom >= 0.55 else 50.0))
        for k in range(int(math.floor(u0 / p)), int(math.ceil(u1 / p)) + 1):
            x = self.ox + k * p * self.zoom; forte = (k * p) % (p * 5 if p < 10 else 50) == 0
            c.create_line(x, 0, x, H, fill='#1C2433' if forte else '#121823')
            if forte and self.zoom * p * 5 > 34: c.create_text(x + 3, H - 3, text='%g' % (k * p), anchor='sw', fill='#4C5A72', font=(T.F, 7))
        for k in range(int(math.floor(v0 / p)), int(math.ceil(v1 / p)) + 1):
            y = self.oy - k * p * self.zoom; forte = (k * p) % (p * 5 if p < 10 else 50) == 0
            c.create_line(0, y, W, y, fill='#1C2433' if forte else '#121823')
            if forte and self.zoom * p * 5 > 34: c.create_text(3, y - 2, text='%g' % (k * p), anchor='sw', fill='#4C5A72', font=(T.F, 7))
        if self.eixo:
            c.create_rectangle(0, 0, self.ox, H, fill='#1A1014', outline=''); c.create_text(max(8, self.ox - 8), 26, text='não desenhar deste lado', anchor='ne', fill='#7A4A52', font=(T.F, 9))
        c.create_line(0, self.oy, W, self.oy, fill='#7A3A3A', width=1); c.create_line(self.ox, 0, self.ox, H, fill=T.ACENTO if self.eixo else '#2F6B3C', width=3 if self.eixo else 1)
        c.create_text(W - 8, self.oy - 4, text=self.eixos[0], anchor='se', fill='#C06060', font=(T.F, 10, 'bold')); c.create_text(self.ox + 6, 6, text=self.eixos[1] + ('  (eixo de giro)' if self.eixo else ''), anchor='nw', fill=T.ACENTO if self.eixo else '#58B070', font=(T.F, 10, 'bold'))
        if self.ref:
            x0, y0 = self.tela(self.ref[0], self.ref[3]); x1, y1 = self.tela(self.ref[2], self.ref[1])
            c.create_rectangle(x0, y0, x1, y1, outline='#3E6FA8', dash=(5, 4)); c.create_text(x0 + 4, y0 - 3, text='peça atual', anchor='sw', fill='#3E6FA8', font=(T.F, 8))
        ordem = [i for i, f in enumerate(self.figs) if not f.get('furo')] + [i for i, f in enumerate(self.figs) if f.get('furo')]
        for i in ordem:
            f = self.figs[i]; P = contorno(f, self.vs)
            if len(P) < 2: continue
            pts = [q for p in P for q in self.tela(*p)]; s = i == self.sel; furo = bool(f.get('furo'))
            c.create_polygon(pts, fill='#0A0D13' if furo else '#1E3654', outline=(T.ACENTO if s else ('#FF8080' if furo else '#6FB4FF')), width=3 if s else 2, dash=(4, 3) if furo else None)
            if f.get('t') == 'texto':
                x, y = self.tela(_n(f.get('x'), self.vs), _n(f.get('y'), self.vs)); c.create_text(x, y, text=str(f.get('txt', '')), fill='#CFE2FF', font=(T.F, max(7, int(_n(f.get('tam'), self.vs, 10) * self.zoom * 0.62)), 'bold'), angle=_n(f.get('g'), self.vs))
            if s and f.get('t') == 'poli' and not _n(f.get('g'), self.vs):
                for p in P:
                    x, y = self.tela(*p); c.create_rectangle(x - 4, y - 4, x + 4, y + 4, fill=T.ACENTO, outline='#0A0D13')
        if self.temp is not None:
            P = contorno(self.temp, self.vs)
            if len(P) > 1: c.create_polygon([q for p in P for q in self.tela(*p)], fill='', outline=T.AMARELO, width=2, dash=(6, 3))
            x, y = self.tela(*self.cursor); c.create_text(x + 14, y + 16, text=descrever(self.temp, self.vs), anchor='nw', fill=T.AMARELO, font=(T.F, 10, 'bold'))
        if self.pts:
            pts = [q for p in self.pts + [self.cursor] for q in self.tela(*p)]; c.create_line(pts, fill=T.AMARELO, width=2)
            for k, p in enumerate(self.pts):
                x, y = self.tela(*p); r = 6 if k == 0 else 4; c.create_oval(x - r, y - r, x + r, y + r, fill=T.VERDE if k == 0 else T.AMARELO, outline='#0A0D13')
        if self.ferr != 'sel':
            x, y = self.tela(*self.cursor); c.create_line(x - 9, y, x + 9, y, fill='#FFFFFF'); c.create_line(x, y - 9, x, y + 9, fill='#FFFFFF')
        self._rodape()

    def _rodape(self):
        self.c.delete('rod'); W, H = self.c.winfo_width(), self.c.winfo_height()
        self.c.create_text(10, H - 13, anchor='w', tags='rod', fill='#8C99AE', font=(T.F, 9), text=self.dica + '   ·   roda = zoom · botão direito = deslocar · Alt = sem grudar na grade')
        self.c.create_rectangle(W - 190, H - 26, W, H, fill='#101621', outline='#27303F', tags='rod')
        self.c.create_text(W - 10, H - 13, anchor='e', tags='rod', fill='#C8D2E2', font=('Consolas', 10), text='%s %8.2f   %s %8.2f mm' % (self.eixos[0], self.cursor[0], self.eixos[1], self.cursor[1]))

    # ---------------- painel ----------------
    def _listar(self):
        self.lista.limpar()
        if not self.figs: T.rotulo(self.lista.dentro, 'Nenhuma figura ainda.\nEscolha uma ferramenta à esquerda\ne desenhe na grade.', T.FRACO, justify='left').pack(anchor='w', padx=6, pady=8)
        for i, f in enumerate(self.figs):
            s = i == self.sel; bg = '#33241A' if s else T.PAINEL
            l = tk.Frame(self.lista.dentro, bg=bg, cursor='hand2'); l.pack(fill='x', pady=1)
            a = tk.Label(l, image=ic.icone({'texto': 'texto', 'caminho': 'poli'}.get(f.get('t'), f.get('t')), 16), bg=bg); a.pack(side='left', padx=(6, 6), pady=4)
            b = tk.Label(l, text=descrever(f, self.vs), bg=bg, fg=T.ACENTO if s else T.TXT, font=(T.F, 9, 'bold' if s else 'normal'), anchor='w'); b.pack(side='left', fill='x', expand=True)
            for w in (l, a, b): w.bind('<Button-1>', lambda e, i=i: self._escolher(i))

    def _escolher(self, i):
        self.sel = i; self.ferramenta('sel'); self._listar(); self._props()

    def _props(self, so_valores=False):
        f = self.figs[self.sel] if self.sel is not None and self.sel < len(self.figs) else None
        if so_valores and f is not None:
            self._trava = True
            for k, v in self.vars_campo.items():
                if k in ('x', 'y'): v.set('%g' % f.get(k, 0) if isinstance(f.get(k, 0), (int, float)) else str(f.get(k)))
            self._trava = False; return
        self.props.limpar(); self.vars_campo = {}; d = self.props.dentro
        if f is None:
            T.rotulo(d, 'Clique numa figura para ver\ne mudar as medidas dela.', T.FRACO, justify='left').pack(anchor='w', padx=6, pady=6); return
        T.rotulo(d, NOMES.get(f.get('t'), ''), T.TXT, 10, True).pack(anchor='w', padx=6, pady=(0, 6))
        for k, rot in CAMPOS.get(f.get('t'), []):
            l = tk.Frame(d, bg=T.PAINEL); l.pack(fill='x', padx=6, pady=2); T.rotulo(l, rot).pack(side='left')
            v = f.get(k, PADRAO.get(f.get('t'), {}).get(k, 0)); var = tk.StringVar(value=('%g' % v) if isinstance(v, (int, float)) else str(v)); self.vars_campo[k] = var
            cp = T.campo(l, var, 12 if k in ('txt', 'fonte') else 8); cp.pack(side='right')
            var.trace_add('write', lambda *a, k=k, var=var: self._mudou(k, var))
        if f.get('t') == 'poli':
            T.rotulo(d, 'Pontos (um por linha: →, ↑)').pack(anchor='w', padx=6, pady=(8, 2))
            tx = tk.Text(d, height=7, width=24, bg=T.CAMPO, fg=T.TXT, insertbackground=T.TXT, relief='flat', font=('Consolas', 9), highlightthickness=1, highlightbackground=T.BORDA); tx.pack(fill='x', padx=6)
            tx.insert('1.0', '\n'.join('%g, %g' % (_n(p[0], self.vs), _n(p[1], self.vs)) for p in f.get('pts', [])))
            tx.bind('<KeyRelease>', lambda e: self._pontos(tx))
        vf = tk.BooleanVar(value=bool(f.get('furo')))
        T.marca(d, 'É um furo (tirar do desenho)', vf, lambda: self._furo(vf.get())).pack(anchor='w', padx=4, pady=(10, 4))
        T.botao(d, 'Apagar figura', self.apagar, 'perigo', 'lixo', 9).pack(anchor='w', padx=6, pady=(4, 8))
        T.rotulo(d, 'Dica: nos campos vale conta e variável\n(ex.: largura/2).', T.FRACO, 8, justify='left').pack(anchor='w', padx=6)

    def _mudou(self, k, var):
        if self._trava or self.sel is None: return
        f = self.figs[self.sel]; s = var.get().strip()
        if k in ('txt', 'fonte'): f[k] = s
        else:
            if s == '' or s in ('-', '.'): return
            try: f[k] = float(s.replace(',', '.'))
            except ValueError:
                try: md.num(s, self.vs); f[k] = s                 # conta / variavel: guarda o texto
                except Exception: return
        self.desenhar()
        if k not in ('x', 'y', 'g'): self._atualizar_nome()

    def _atualizar_nome(self):
        try:
            l = self.lista.dentro.winfo_children()[self.sel]; l.winfo_children()[1].config(text=descrever(self.figs[self.sel], self.vs))
        except Exception: pass

    def _pontos(self, tx):
        pts = []
        for ln in tx.get('1.0', 'end').splitlines():
            p = [x for x in ln.replace(';', ',').replace(' ', ',').split(',') if x != '']
            if len(p) >= 2:
                try: pts.append([float(p[0]), float(p[1])])
                except ValueError: pass
        if len(pts) >= 3 and self.sel is not None: self.figs[self.sel]['pts'] = pts; self.desenhar(); self._atualizar_nome()

    def _furo(self, sim):
        if self.sel is None: return
        self._guardar()
        if sim: self.figs[self.sel]['furo'] = True
        else: self.figs[self.sel].pop('furo', None)
        self._listar(); self.desenhar()

    # ---------------- fim ----------------
    def concluir(self):
        if self.ferr == 'poli' and len(self.pts) >= 3: self._fechar_poli()
        self.ao_concluir(copy.deepcopy(self.figs))

    def cancelar(self): self.ao_cancelar()
