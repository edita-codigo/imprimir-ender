"""Visualizador 3D de verdade para a Mesa 3D (sem placa de video, so numpy + PIL): camera em perspectiva que gira, afasta e aproxima,
clique NA PECA em 3D para selecionar, arrastar a peca pela mesa, e modo "camadas" (mostra o fatiamento, inclusive o SUPORTE, em 3D).

Mouse:  esquerdo na peca = selecionar e ARRASTAR  |  esquerdo no vazio = girar a camera  |  Ctrl + esquerdo na peca = GIRAR a peca
        direito ou do meio (arrastando) = deslocar a camera  |  roda = zoom  |  direito (so clicar) = menu
Teclas: setas = mover 1 mm, Q/E = girar a peca 15 graus, Ctrl+D = copiar a peca, Delete = apagar, 1/2/3/4 = vistas.
"""
import math
import numpy as np
import tkinter as tk
from PIL import Image, ImageDraw, ImageTk

BG = '#0D1117'
COR_TIPO = {'WALL-OUTER': '#ff7043', 'WALL-INNER': '#66bb6a', 'SKIN': '#ffd54f', 'FILL': '#8d6e63', 'SUPPORT': '#26c6da', 'SUPPORT-INTERFACE': '#80deea',
            'SKIRT': '#b0bec5', 'PRIME-TOWER': '#ab47bc'}
LUZ = np.array([-0.35, -0.55, 0.78]); LUZ = LUZ / np.linalg.norm(LUZ)
VERM = (255, 107, 107)
ORCAMENTO = 14000        # triangulos desenhados por quadro (acima disso, as pecas nao selecionadas ficam mais grossas)


def _rgb(h):
    h = h.lstrip('#'); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def simplificar(m, alvo):
    """Reduz a malha para ~alvo triangulos agrupando vertices numa grade (rapido, sem biblioteca extra). Devolve (vertices, faces)."""
    V = np.asarray(m.vertices, dtype=float); F = np.asarray(m.faces, dtype=int)
    cell = math.sqrt(max(float(m.area), 1e-6) / max(alvo, 1)) * 1.3
    melhor = (V, F)
    for _ in range(7):
        q = np.floor(V / cell).astype(np.int64); chaves, inv = np.unique(q, axis=0, return_inverse=True); inv = inv.ravel()
        nv = np.zeros((len(chaves), 3)); np.add.at(nv, inv, V); nv /= np.bincount(inv, minlength=len(chaves))[:, None]
        f = inv[F]; f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
        melhor = (nv, f)
        if len(f) > alvo * 1.4: cell *= 1.3
        elif len(f) < alvo * 0.35 and len(f) > 0: cell /= 1.3
        else: break
    return melhor


class Vista3D(tk.Canvas):
    def __init__(self, pai, mesa, bed=(220.0, 220.0), **kw):
        super().__init__(pai, bg=BG, highlightthickness=0, **kw)
        self.mesa = mesa; self.bed = bed
        self.az, self.el, self.dist = -62.0, 30.0, 430.0
        self.alvo = np.array([bed[0] / 2, bed[1] / 2, 20.0]); self.fov = 36.0
        self.modo = 'modelo'; self.camadas = None; self.ncam = 0
        self._img = None; self._item = None; self._agendado = False; self._arrastando = False; self._baixa = False
        self._acao = None; self._ult = (0, 0); self._mexeu = False; self._xbtn = None
        self._lod = {}
        self.bind('<Configure>', lambda e: self.redesenhar())
        self.bind('<ButtonPress-1>', self._b1); self.bind('<B1-Motion>', self._b1_mov); self.bind('<ButtonRelease-1>', self._b1_solta)
        for b in (2, 3):
            self.bind('<ButtonPress-%d>' % b, self._bp); self.bind('<B%d-Motion>' % b, self._bp_mov); self.bind('<ButtonRelease-%d>' % b, lambda e, b=b: self._bp_solta(e, b))
        self.bind('<MouseWheel>', self._roda); self.bind('<Enter>', lambda e: self.focus_set())
        self.bind('<Double-Button-1>', self._duplo)
        for k, dx, dy in (('<Left>', -1, 0), ('<Right>', 1, 0), ('<Up>', 0, 1), ('<Down>', 0, -1)):
            self.bind(k, lambda e, dx=dx, dy=dy: self.mesa.mover_sel(dx, dy))
        self.bind('<KeyPress-q>', lambda e: self.mesa.girar(-15)); self.bind('<KeyPress-e>', lambda e: self.mesa.girar(15))
        self.bind('<Control-d>', lambda e: self.mesa.copiar_uma()); self.bind('<Control-D>', lambda e: self.mesa.copiar_uma())
        for k, v in (('1', 'topo'), ('2', 'frente'), ('3', 'lado'), ('4', '3d')): self.bind('<KeyPress-%s>' % k, lambda e, v=v: self.vista(v))

    # ---------------- camera ----------------
    def _cam(self):
        W, H = getattr(self, '_wh', None) or (max(self.winfo_width(), 200), max(self.winfo_height(), 200))
        a, e = math.radians(self.az), math.radians(self.el)
        eye = self.alvo + self.dist * np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
        f = self.alvo - eye; f = f / np.linalg.norm(f)
        r = np.cross(f, [0, 0, 1.0]); r = r / np.linalg.norm(r); u = np.cross(r, f)
        s = (H / 2.0) / math.tan(math.radians(self.fov) / 2)
        return W, H, eye, r, u, f, s

    def _proj(self, P, cam=None, escala=1.0):
        """P (n,3) mundo -> (n,2) tela, profundidade (n,)"""
        W, H, eye, r, u, f, s = cam or self._cam()
        d = P - eye; x = d @ r; y = d @ u; z = d @ f
        z = np.where(z < 1.0, 1.0, z)
        return np.column_stack([(W / 2 + s * x / z) * escala, (H / 2 - s * y / z) * escala]), z

    def bed_xy(self, px, py, z0=0.0):
        """Ponto da mesa (x, y em mm) debaixo do pixel (raio da camera ate o plano z=z0). None se aponta para o ceu."""
        W, H, eye, r, u, f, s = self._cam()
        dr = f + r * ((px - W / 2) / s) + u * ((H / 2 - py) / s)
        if abs(dr[2]) < 1e-6: return None
        t = (z0 - eye[2]) / dr[2]
        if t <= 0: return None
        p = eye + t * dr; return float(p[0]), float(p[1])

    def vista(self, nome):
        if nome == 'topo': self.az, self.el = -90.0, 89.0
        elif nome == 'frente': self.az, self.el = -90.0, 9.0
        elif nome == 'lado': self.az, self.el = 0.0, 9.0
        else: self.az, self.el = -62.0, 30.0
        self.dist = 430.0 if nome != 'topo' else 400.0; self.alvo = np.array([self.bed[0] / 2, self.bed[1] / 2, 20.0]); self.redesenhar()

    # ---------------- geometria das pecas ----------------
    def _malha(self, p, alvo=None):
        """(vertices, faces) para desenhar. alvo = no maximo ~alvo triangulos (agrupa vertices proximos; a forma geral fica)."""
        nf = len(p.prev.faces)
        if alvo and nf > alvo:
            b = 250
            while b < alvo: b *= 2
            alvo = b
            k = (id(p.prev), alvo)
            if k not in self._lod: self._lod[k] = (*simplificar(p.prev, alvo), p.prev)         # guarda p.prev: o id nao e reaproveitado
        else:
            k = (id(p.prev), 0)
            if k not in self._lod: self._lod[k] = (np.asarray(p.prev.vertices, dtype=float), np.asarray(p.prev.faces, dtype=int), p.prev)
        return self._lod[k][0], self._lod[k][1]

    def _triangulos(self, pecas, sel, cam, escala, ids=False):
        """Todos os triangulos da cena: (pontos_tela (n,3,2), profundidade (n,), cor (n,3)). ids=True: cor = numero da peca."""
        total = sum(len(p.prev.faces) for p in pecas); lod = total > ORCAMENTO; alvo = max(250, ORCAMENTO // max(1, len(pecas)))
        P2, Z, C = [], [], []
        for n, p in enumerate(pecas):
            V0, F = self._malha(p, alvo=alvo if (lod and p is not sel) else None)
            V = p.vertices_mesa(V0); tri = V[F]
            S, z = self._proj(V, cam, escala); S = S[F]; zt = z[F].mean(1)
            if ids: cor = np.tile(np.array([(n + 1) & 255, ((n + 1) >> 8) & 255, 0]), (len(F), 1))
            else:
                nn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]); ln = np.linalg.norm(nn, axis=1); ln[ln == 0] = 1; nn = nn / ln[:, None]
                sh = 0.30 + 0.70 * np.abs(nn @ LUZ)
                base = np.array(VERM if not p.ok else _rgb(p.cor), dtype=float)
                if p is sel: base = np.clip(base * 0.8 + 70, 0, 255)
                cor = np.clip(base[None, :] * sh[:, None], 0, 255).astype(int)
            P2.append(S); Z.append(zt); C.append(cor)
        if not P2: return None
        return np.concatenate(P2), np.concatenate(Z), np.concatenate(C)

    def _pintar(self, draw, tris):
        P, Z, C = tris; ordem = np.argsort(-Z)
        pts = P[ordem].tolist(); cols = [tuple(c) for c in C[ordem].tolist()]
        poly = draw.polygon
        for t, c in zip(pts, cols): poly([tuple(t[0]), tuple(t[1]), tuple(t[2])], fill=c)

    # ---------------- desenho ----------------
    def redesenhar(self, baixa=False):
        self._baixa = self._baixa or baixa
        if self._agendado: return
        self._agendado = True; self.after(12, self._quadro)

    def _quadro(self):
        self._agendado = False
        W, H = self.winfo_width(), self.winfo_height()
        if W < 50 or H < 50: return
        esc = 1.0 if self._baixa or self._arrastando else 2.0; self._baixa = False
        cam = self._cam()
        img = Image.new('RGB', (int(W * esc), int(H * esc)), _rgb(BG)); d = ImageDraw.Draw(img)
        self._desenhar_mesa(d, cam, esc)
        pecas = list(self.mesa.pecas); sel = self.mesa.sel
        if self.modo == 'camadas' and self.camadas: self._desenhar_camadas(d, cam, esc)
        elif pecas:
            for p in pecas: self._sombra(d, p, cam, esc, p is sel)
            t = self._triangulos(pecas, sel, cam, esc)
            if t is not None: self._pintar(d, t)
            if sel in pecas: self._contorno_sel(d, sel, cam, esc)
        if esc != 1.0: img = img.resize((W, H), Image.LANCZOS)
        self.ultima_imagem = img
        self._img = ImageTk.PhotoImage(img)
        if self._item is None: self._item = self.create_image(0, 0, anchor='nw', image=self._img)
        else: self.itemconfig(self._item, image=self._img)
        self.coords(self._item, 0, 0); self._overlay(cam, pecas, sel)

    def render(self, W=900, H=700, az=None, el=None, dist=None, alvo=None, esc=1.0):
        """Desenha a cena num PIL.Image (sem mexer na tela). Serve para a IA/MCP VER a mesa ou a peca em edicao."""
        old = (self.az, self.el, self.dist, self.alvo, getattr(self, '_wh', None))
        try:
            if az is not None: self.az = float(az)
            if el is not None: self.el = float(el)
            if dist is not None: self.dist = float(dist)
            if alvo is not None: self.alvo = np.array(alvo, dtype=float)
            self._wh = (int(W), int(H)); cam = self._cam()
            img = Image.new('RGB', (int(W * esc), int(H * esc)), _rgb(BG)); d = ImageDraw.Draw(img)
            self._desenhar_mesa(d, cam, esc)
            pecas = list(self.mesa.pecas); sel = self.mesa.sel
            if pecas:
                for p in pecas: self._sombra(d, p, cam, esc, p is sel)
                t = self._triangulos(pecas, sel, cam, esc)
                if t is not None: self._pintar(d, t)
            return img.resize((int(W), int(H)), Image.LANCZOS) if esc != 1.0 else img
        finally:
            self.az, self.el, self.dist, self.alvo, self._wh = old

    def _linha3d(self, d, a, b, cam, esc, cor, larg=1):
        S, _ = self._proj(np.array([a, b], dtype=float), cam, esc)
        d.line([tuple(S[0]), tuple(S[1])], fill=cor, width=max(1, int(larg * esc / 1.5)))

    def _desenhar_mesa(self, d, cam, esc):
        bx, by = self.bed
        c = np.array([[0, 0, 0], [bx, 0, 0], [bx, by, 0], [0, by, 0]], dtype=float); S, _ = self._proj(c, cam, esc)
        d.polygon([tuple(q) for q in S], fill=(18, 25, 35), outline=(70, 84, 110))
        for g in range(0, int(bx) + 1, 10):
            self._linha3d(d, (g, 0, 0), (g, by, 0), cam, esc, (52, 60, 74) if g % 50 == 0 else (35, 43, 55))
        for g in range(0, int(by) + 1, 10):
            self._linha3d(d, (0, g, 0), (bx, g, 0), cam, esc, (52, 60, 74) if g % 50 == 0 else (35, 43, 55))
        self._linha3d(d, (0, 0, 0), (bx, 0, 0), cam, esc, (255, 138, 61), 3)           # borda da FRENTE em laranja
        for a, b in (((bx, 0, 0), (bx, by, 0)), ((bx, by, 0), (0, by, 0)), ((0, by, 0), (0, 0, 0))): self._linha3d(d, a, b, cam, esc, (110, 125, 150), 2)
        try: mar = float(self.mesa.var_mar.get())
        except Exception: mar = 3.0
        if mar > 0:
            pts = [(mar, mar), (bx - mar, mar), (bx - mar, by - mar), (mar, by - mar), (mar, mar)]
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                L = math.hypot(x1 - x0, y1 - y0); n = max(2, int(L / 8))
                for i in range(0, n, 2):
                    a = (x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n, 0); b = (x0 + (x1 - x0) * min(i + 1, n) / n, y0 + (y1 - y0) * min(i + 1, n) / n, 0)
                    self._linha3d(d, a, b, cam, esc, (75, 88, 110))

    def _sombra(self, d, p, cam, esc, sel):
        c = p.contorno(); P = np.column_stack([c, np.zeros(len(c))]); S, _ = self._proj(P, cam, esc)
        d.polygon([tuple(q) for q in S], fill=(60, 30, 30) if not p.ok else (8, 12, 18))

    def _contorno_sel(self, d, p, cam, esc):
        c = p.contorno(); n = len(c)
        for z in (0.0, p.altura):
            P = np.column_stack([c, np.full(n, z)]); S, _ = self._proj(P, cam, esc); pts = [tuple(q) for q in S] + [tuple(S[0])]
            d.line(pts, fill=(255, 255, 255), width=max(1, int(2 * esc / 1.5)))

    def _desenhar_camadas(self, d, cam, esc):
        n = self.ncam; cs = self.camadas[:n]
        total = sum(len(v) for c in cs for v in c['segs'].values()); k = max(1, int(math.ceil(total / 30000.0)))
        for i, c in enumerate(cs):
            atual = (i == n - 1)
            if not atual and (n - 1 - i) % k: continue
            for tipo, segs in c['segs'].items():
                cor = _rgb(COR_TIPO.get(tipo, '#cfd8dc'))
                if not atual: cor = tuple(int(v * 0.72) for v in cor)
                a = np.column_stack([segs[:, 0], segs[:, 1], np.full(len(segs), c['z'])]); b = np.column_stack([segs[:, 2], segs[:, 3], np.full(len(segs), c['z'])])
                Sa, _ = self._proj(a, cam, esc); Sb, _ = self._proj(b, cam, esc); w = max(1, int((2 if atual else 1) * esc / 1.5))
                for p, q in zip(Sa.tolist(), Sb.tolist()): d.line([tuple(p), tuple(q)], fill=cor, width=w)

    def _overlay(self, cam, pecas, sel):
        self.delete('ov'); self._xbtn = None
        S, _ = self._proj(np.array([[self.bed[0] / 2, -12.0, 0.0]]), cam)
        self.create_text(S[0][0], S[0][1], text='FRENTE', fill='#FF8A3D', font=('Segoe UI', 8, 'bold'), tags='ov')
        W, H = cam[0], cam[1]
        o = np.array([[0, 0, 0], [30, 0, 0], [0, 30, 0], [0, 0, 30]], dtype=float) + np.array([-18.0, -18.0, 0.0])
        if self.modo == 'modelo':
            for n, p in enumerate(pecas):
                top = np.array([[p.x, p.y, p.altura]]); Sx, _ = self._proj(top, cam)
                self.create_text(Sx[0][0], Sx[0][1] - 10, text=str(n + 1), fill='white', font=('Segoe UI', 10, 'bold'), tags='ov')
            if sel in pecas:
                c = sel.contorno(); q = max(c, key=lambda t: t[0] + t[1]); Sx, _ = self._proj(np.array([[q[0], q[1], sel.altura]]), cam)
                bx, by, r = Sx[0][0] + 10, Sx[0][1] - 10, 10
                self.create_oval(bx - r, by - r, bx + r, by + r, fill='#FF6B6B', outline='white', width=2, tags='ov'); self.create_text(bx, by, text='✕', fill='white', font=('Segoe UI', 9, 'bold'), tags='ov')
                self._xbtn = (bx, by, r)
        self.create_text(8, H - 8, anchor='sw', fill='#6C788C', font=('Segoe UI', 8), tags='ov',
                         text='arraste a peça = mover · Ctrl+arrastar = girar a peça · arraste no vazio = girar a câmera · botão direito arrastando = deslocar · roda = zoom')

    # ---------------- mouse ----------------
    def pick(self, px, py):
        """Peca (ou None) debaixo do pixel, lida de um desenho por 'cor de identidade' (acerta mesmo peca atras de outra)."""
        pecas = list(self.mesa.pecas)
        if not pecas: return None
        W, H = self.winfo_width(), self.winfo_height(); cam = self._cam()
        img = Image.new('RGB', (W, H), (0, 0, 0)); d = ImageDraw.Draw(img)
        t = self._triangulos(pecas, self.mesa.sel, cam, 1.0, ids=True)
        if t is None: return None
        self._pintar(d, t)
        if not (0 <= px < W and 0 <= py < H): return None
        r, g, b = img.getpixel((int(px), int(py))); n = r + (g << 8)
        return pecas[n - 1] if 1 <= n <= len(pecas) else None

    def _b1(self, ev):
        self.focus_set(); self._mexeu = False; self._ult = (ev.x, ev.y)
        if self.modo != 'modelo': self._acao = ('orbita',); return
        if self._xbtn and (ev.x - self._xbtn[0]) ** 2 + (ev.y - self._xbtn[1]) ** 2 <= (self._xbtn[2] + 3) ** 2:
            self._acao = None; self.mesa.remover(); return
        p = self.pick(ev.x, ev.y)
        if p is not None:
            self.mesa.selecionar(p)
            if ev.state & 0x0004: self._acao = ('gira', p, ev.x, p.rot)                         # Ctrl + arrastar = girar a peca
            else:
                h = self.bed_xy(ev.x, ev.y); self._acao = ('move', p, (p.x - h[0], p.y - h[1]) if h else (0, 0))
        else:
            self.mesa.selecionar(None); self._acao = ('orbita',)

    def _b1_mov(self, ev):
        a = self._acao
        if not a: return
        self._mexeu = True; self._arrastando = True
        if a[0] == 'orbita':
            dx, dy = ev.x - self._ult[0], ev.y - self._ult[1]; self._ult = (ev.x, ev.y)
            if ev.state & 0x0001: self._deslocar(dx, dy)
            else: self.az -= dx * 0.4; self.el = max(3.0, min(89.5, self.el + dy * 0.4))
            self.redesenhar(baixa=True)
        elif a[0] == 'move':
            h = self.bed_xy(ev.x, ev.y)
            if h: self.mesa.mover_peca(a[1], h[0] + a[2][0], h[1] + a[2][1])
        elif a[0] == 'gira':
            self.mesa.girar_peca(a[1], (a[3] + (ev.x - a[2]) * 0.6) % 360)

    def _b1_solta(self, ev):
        self._arrastando = False
        if self._acao and self._acao[0] in ('move', 'gira') and self._mexeu: self.mesa.terminou_mexer()
        self._acao = None; self.redesenhar()

    def _duplo(self, ev):
        if self.modo != 'modelo' or self.pick(ev.x, ev.y) is not None: return
        h = self.bed_xy(ev.x, ev.y)
        if h and self.mesa.sel: self.mesa.mover_peca(self.mesa.sel, h[0], h[1]); self.mesa.terminou_mexer()

    def _deslocar(self, dx, dy):
        W, H, eye, r, u, f, s = self._cam(); k = self.dist / s
        self.alvo = self.alvo - r * dx * k + u * dy * k

    def _bp(self, ev): self._ult = (ev.x, ev.y); self._mexeu = False

    def _bp_mov(self, ev):
        dx, dy = ev.x - self._ult[0], ev.y - self._ult[1]
        if abs(dx) + abs(dy) > 2: self._mexeu = True
        self._ult = (ev.x, ev.y); self._deslocar(dx, dy); self.redesenhar(baixa=True)

    def _bp_solta(self, ev, b):
        if b == 3 and not self._mexeu: self.mesa.menu_direito(ev)
        self.redesenhar()

    def _roda(self, ev):
        self.dist = max(110.0, min(1300.0, self.dist * (0.9 ** (ev.delta / 120.0)))); self.redesenhar(baixa=True); self.after(180, self.redesenhar)

    # ---------------- modo camadas ----------------
    def mostrar_camadas(self, camadas, n):
        self.modo = 'camadas'; self.camadas = camadas; self.ncam = n; self.redesenhar()

    def sair_camadas(self):
        self.modo = 'modelo'; self.camadas = None; self.redesenhar()
