"""Vista 3D da aba Modelar (aparencia de programa CAD, sem placa de video: numpy + PIL).

Mostra a peca com as ARESTAS desenhadas, deixa clicar em FACES e ARESTAS (para arredondar, furar, desenhar em cima), mostra a ferramenta
em vermelho transparente antes de aplicar, as medidas da peca e os eixos. Tambem gera imagens para a IA ver a peca (com os numeros das arestas/faces).

Com uma ferramenta aberta: arrastar a forma vermelha = mudar a posicao · puxar os quadradinhos = mudar o tamanho · bolinha azul = subir/descer.
Mouse: clique = escolher (Shift = varias) · arrastar no vazio = girar · botao direito ou do meio arrastando = deslocar · roda = zoom · duplo clique = enquadrar.
"""
import math
import numpy as np
import tkinter as tk
from PIL import Image, ImageDraw, ImageTk, ImageFont

FUNDO_A, FUNDO_B = (30, 37, 50), (12, 15, 21)
COR_PECA = (150, 172, 204); COR_SEL = (255, 148, 66); COR_HOVER = (196, 214, 240); COR_ARESTA = (18, 24, 33); COR_ARESTA_SEL = (255, 170, 60); COR_ARESTA_HOVER = (255, 226, 120)
COR_FANTASMA = (255, 96, 96); COR_GRADE = (44, 53, 68); COR_GRADE_F = (64, 76, 96); COR_MEDIDA = (120, 200, 255)
ORCAMENTO = 16000
VISTAS = {'3d': (-58.0, 28.0), 'frente': (-90.0, 0.0), 'tras': (90.0, 0.0), 'direita': (0.0, 0.0), 'esquerda': (180.0, 0.0), 'cima': (-90.0, 89.9), 'baixo': (-90.0, -89.9)}
NOMES_VISTA = {'3d': '3D', 'frente': 'Frente', 'tras': 'Trás', 'direita': 'Direita', 'esquerda': 'Esquerda', 'cima': 'Cima', 'baixo': 'Baixo'}
_fontes = {}


def fonte(tam, negrito=False):
    k = (int(tam), negrito)
    if k not in _fontes:
        try: _fontes[k] = ImageFont.truetype('segoeuib.ttf' if negrito else 'segoeui.ttf', int(tam))
        except Exception:
            try: _fontes[k] = ImageFont.truetype('arial.ttf', int(tam))
            except Exception: _fontes[k] = ImageFont.load_default()
    return _fontes[k]


def _simplificar(V, F, alvo):
    """Reduz a malha agrupando vertices numa grade (para pecas pesadas vindas de STL)."""
    area = float(np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1).sum() / 2)
    cell = math.sqrt(max(area, 1e-6) / max(alvo, 1)) * 1.3; melhor = (V, F)
    for _ in range(7):
        q = np.floor(V / cell).astype(np.int64); ch, inv = np.unique(q, axis=0, return_inverse=True); inv = inv.ravel()
        nv = np.zeros((len(ch), 3)); np.add.at(nv, inv, V); nv /= np.bincount(inv, minlength=len(ch))[:, None]
        f = inv[F]; f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]; melhor = (nv, f)
        if len(f) > alvo * 1.4: cell *= 1.3
        elif len(f) < alvo * 0.35 and len(f) > 0: cell /= 1.3
        else: break
    return melhor


class Cena:
    """Dados prontos para desenhar (calculados uma vez por peca)."""
    def __init__(self, dv):
        V = np.asarray(dv['V'], dtype=float); F = np.asarray(dv['F'], dtype=int); self.tipo = dv.get('tipo', 'vazio'); self.dv = dv
        fid = np.asarray(dv['fid'], dtype=int); ar = dv.get('arestas', []); adj = dv.get('adj', [])
        self.lod = False
        if len(F) > ORCAMENTO * 1.6 and self.tipo != 'cad':           # so malha pesada (STL) e simplificada; peca CAD nunca perde as arestas
            V, F = _simplificar(V, F, ORCAMENTO); fid = np.arange(len(F)); ar = []; adj = []; self.lod = True
        elif self.tipo == 'malha': fid = np.arange(len(F))
        VN = None
        if len(F) and not self.lod and self.tipo == 'cad':
            # normal de cada vertice = media dos triangulos da MESMA face (cada face tem seus proprios vertices): curva fica lisa, quina continua viva
            t = V[F]; n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]); VN = np.zeros((len(V), 3))
            for k in range(3): np.add.at(VN, F[:, k], n)
        if len(F) and not self.lod:
            # triangulos grandes enganam a ordem de desenho (o de tras aparece por cima): parte os compridos ao meio ate ficarem pequenos
            h = max(float(np.linalg.norm(V.max(0) - V.min(0))) / 16.0, 1.5)
            for _ in range(12):
                if len(F) > ORCAMENTO * 1.7: break
                t = V[F]; L = np.stack([np.linalg.norm(t[:, 1] - t[:, 0], axis=1), np.linalg.norm(t[:, 2] - t[:, 1], axis=1), np.linalg.norm(t[:, 0] - t[:, 2], axis=1)], axis=1)
                k = L.argmax(1); gr = L.max(1) > h
                if not gr.any(): break
                Fg = F[gr]; kg = k[gr]; i = np.arange(len(Fg)); a = Fg[i, kg]; b = Fg[i, (kg + 1) % 3]; c_ = Fg[i, (kg + 2) % 3]
                m = len(V) + i; V = np.concatenate([V, (V[a] + V[b]) / 2])
                if VN is not None:
                    na = VN[a] / np.maximum(np.linalg.norm(VN[a], axis=1), 1e-12)[:, None]; nb = VN[b] / np.maximum(np.linalg.norm(VN[b], axis=1), 1e-12)[:, None]; VN = np.concatenate([VN, na + nb])
                F = np.concatenate([F[~gr], np.column_stack([a, m, c_]), np.column_stack([m, b, c_])]); fid = np.concatenate([fid[~gr], fid[gr], fid[gr]])
        self.V, self.F, self.fid = V, F, fid
        if len(F):
            t = V[F]; n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]); ln = np.linalg.norm(n, axis=1); ln[ln == 0] = 1
            self.N = n / ln[:, None]; self.C = t.mean(1); self.min = V.min(0); self.max = V.max(0)
            if VN is not None:
                vn = VN / np.maximum(np.linalg.norm(VN, axis=1), 1e-12)[:, None]; s = vn[F].sum(1); ls = np.linalg.norm(s, axis=1)
                self.NS = np.where((ls > 1e-9)[:, None], s / np.maximum(ls, 1e-12)[:, None], self.N)          # normal 'de pintura' (lisa)
            else: self.NS = self.N
            if dv.get('lim') is not None: self.min, self.max = np.asarray(dv['lim'][0], dtype=float), np.asarray(dv['lim'][1], dtype=float)      # medidas exatas (nao as da malha)
        else:
            self.N = np.zeros((0, 3)); self.NS = self.N; self.C = np.zeros((0, 3)); self.min = np.array([-20.0, -20, 0]); self.max = np.array([20.0, 20, 20])
        # arestas -> segmentos curtos (para testar o que esta escondido atras da peca)
        A, B, E = [], [], []; self.n_arestas = len(ar)
        diag = float(np.linalg.norm(self.max - self.min)) or 1.0; passo = max(diag / 60.0, 0.4)
        for i, pts in enumerate(ar):
            pts = np.asarray(pts, dtype=float)
            if len(pts) == 2:
                k = int(max(1, min(40, np.linalg.norm(pts[1] - pts[0]) / passo))); s = np.linspace(0, 1, k + 1)[:, None]; pts = pts[0] + (pts[1] - pts[0]) * s
            A.append(pts[:-1]); B.append(pts[1:]); E.append(np.full(len(pts) - 1, i))
        self.SA = np.concatenate(A) if A else np.zeros((0, 3)); self.SB = np.concatenate(B) if B else np.zeros((0, 3)); self.SE = np.concatenate(E).astype(int) if E else np.zeros(0, dtype=int)
        self.adj = np.full((max(1, len(adj)), 2), -1, dtype=int); self.costura = np.zeros(max(1, len(adj)), dtype=bool)
        for i, a in enumerate(adj):
            a = list(a)[:2]
            for j, v in enumerate(a): self.adj[i, j] = v
            self.costura[i] = self.tipo == 'cad' and len(set(a)) < 2


class VistaCAD(tk.Canvas):
    def __init__(self, pai, ao_escolher=None, ao_passar=None, **kw):
        super().__init__(pai, bg='#0C0F15', highlightthickness=0, **kw)
        self.cena = Cena(dict(V=np.zeros((0, 3)), F=np.zeros((0, 3), dtype=int), fid=np.zeros(0, dtype=int)))
        self.az, self.el, self.dist, self.fov = -58.0, 28.0, 220.0, 30.0; self.alvo = np.array([0.0, 0.0, 10.0])
        self.fantasma = None; self.sel_faces = set(); self.sel_arestas = set(); self.hover = None
        self.ao_escolher = ao_escolher; self.ao_passar = ao_passar; self.mostrar_medidas = True; self.mostrar_arestas = True; self.mostrar_grade = True
        self._img = None; self._item = None; self._agendado = False; self._baixa = False; self._arrastando = False; self._ult = (0, 0); self._mexeu = False; self._botao = 0
        self._buf = None; self._wh = None; self._grad = {}; self._hover_job = None; self.ultima_imagem = None
        # arrastar com o mouse: alcas (quadradinhos de tamanho / bolinha de subir-descer) e o proprio corpo da forma em vermelho
        self.alcas = []; self.ao_arrastar = None; self.corpo_arrastavel = False; self.peca_arrastavel = False; self.plano_fixo = None; self._drag = None; self._alca_hover = None
        self.bind('<Configure>', lambda e: self.redesenhar())
        self.bind('<ButtonPress-1>', self._aperta); self.bind('<B1-Motion>', self._arrasta); self.bind('<ButtonRelease-1>', self._solta)
        for b in (2, 3):
            self.bind('<ButtonPress-%d>' % b, self._aperta); self.bind('<B%d-Motion>' % b, self._arrasta_pan); self.bind('<ButtonRelease-%d>' % b, self._solta_pan)
        self.bind('<MouseWheel>', self._roda); self.bind('<Double-Button-1>', lambda e: self.enquadrar()); self.bind('<Motion>', self._move); self.bind('<Leave>', lambda e: self._set_hover(None))

    # ---------------- dados ----------------
    def definir(self, dv, enquadrar=False):
        vazia = len(self.cena.F) == 0
        self.cena = Cena(dv); self.sel_faces = set(); self.sel_arestas = set(); self.hover = None; self._buf = None
        if enquadrar or vazia: self.enquadrar(redesenhar=False)
        self.redesenhar()

    def definir_fantasma(self, malha):
        self.fantasma = None if malha is None else (np.asarray(malha.vertices, dtype=float), np.asarray(malha.faces, dtype=int)); self.redesenhar()

    def definir_alcas(self, alcas):
        """alcas = [dict(id, p=(x,y,z), eixo=(x,y,z) ou None, cor, forma 'q'|'c', base=ponto ou None)]: pontos que o usuario puxa com o mouse."""
        self.alcas = list(alcas or [])
        if self._alca_hover is not None and not any(a['id'] == self._alca_hover for a in self.alcas): self._alca_hover = None
        self.redesenhar()

    def _alca_em(self, px, py, cam=None):
        if not self.alcas: return None
        S, _ = self._proj(np.array([a['p'] for a in self.alcas], dtype=float), cam or self._cam()); d = np.hypot(S[:, 0] - px, S[:, 1] - py); i = int(np.argmin(d))
        return self.alcas[i] if d[i] <= 13 else None

    def _fantasma_em(self, px, py, cam=None):
        """Ponto 3D da forma vermelha debaixo do mouse (None se o mouse nao esta em cima dela)."""
        if self.fantasma is None or not len(self.fantasma[1]): return None
        V, F = self.fantasma; o, dr = self._raio(px, py, cam or self._cam())
        v0, v1, v2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]; e1, e2 = v1 - v0, v2 - v0; h = np.cross(dr, e2); a = np.einsum('ij,ij->i', e1, h)
        ok = np.abs(a) > 1e-12; a = np.where(ok, a, 1.0); s = o - v0; uu = np.einsum('ij,ij->i', s, h) / a; q = np.cross(s, e1); vv = (q @ dr) / a; t = np.einsum('ij,ij->i', e2, q) / a
        m = ok & (uu >= -1e-6) & (vv >= -1e-6) & (uu + vv <= 1 + 1e-6) & (t > 0)
        return o + dr * float(t[m].min()) if m.any() else None

    def _desenhar_alcas(self, d, cam):
        for a in self.alcas:
            p = np.asarray(a['p'], dtype=float); S, _ = self._proj(np.array([p]), cam); x, y = float(S[0, 0]), float(S[0, 1]); cor = tuple(a.get('cor', (255, 196, 70)))
            if a.get('base') is not None:
                B, _ = self._proj(np.array([np.asarray(a['base'], dtype=float)]), cam); d.line([float(B[0, 0]), float(B[0, 1]), x, y], fill=cor, width=2)
            r = 9 if a['id'] == self._alca_hover or (self._drag and self._drag['alvo'] == a['id']) else 7
            caixa = [x - r, y - r, x + r, y + r]
            if a.get('forma') == 'c': d.ellipse(caixa, fill=cor, outline=(255, 255, 255), width=2)
            else: d.rectangle(caixa, fill=cor, outline=(255, 255, 255), width=2)

    def limpar_selecao(self):
        self.sel_faces = set(); self.sel_arestas = set(); self.redesenhar()

    def _limites(self):
        c = self.cena; mn, mx = c.min.copy(), c.max.copy()
        if self.fantasma is not None and len(self.fantasma[0]): mn = np.minimum(mn, self.fantasma[0].min(0)); mx = np.maximum(mx, self.fantasma[0].max(0))
        return mn, mx

    def enquadrar(self, redesenhar=True):
        mn, mx = self._limites(); r = float(np.linalg.norm(mx - mn)) / 2 or 20.0
        self.alvo = (mn + mx) / 2; self.dist = max(30.0, r / math.sin(math.radians(self.fov) / 2) * 1.12)
        if redesenhar: self.redesenhar()

    def vista(self, nome):
        self.az, self.el = VISTAS.get(nome, VISTAS['3d']); self.enquadrar()

    # ---------------- camera ----------------
    def _cam(self, W=None, H=None, az=None, el=None, dist=None, alvo=None):
        W = W or max(self.winfo_width(), 200); H = H or max(self.winfo_height(), 200)
        a, e = math.radians(self.az if az is None else az), math.radians(self.el if el is None else el)
        alvo = self.alvo if alvo is None else np.asarray(alvo, dtype=float); dist = self.dist if dist is None else dist
        eye = alvo + dist * np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
        f = alvo - eye; f = f / np.linalg.norm(f); r = np.cross(f, [0, 0, 1.0]); nr = np.linalg.norm(r)
        r = r / nr if nr > 1e-9 else np.array([1.0, 0, 0]); u = np.cross(r, f)
        return W, H, eye, r, u, f, (H / 2.0) / math.tan(math.radians(self.fov) / 2)

    @staticmethod
    def _proj(P, cam, esc=1.0):
        W, H, eye, r, u, f, s = cam; d = P - eye; z = d @ f; z = np.where(z < 0.5, 0.5, z)
        return np.column_stack([(W / 2 + s * (d @ r) / z) * esc, (H / 2 - s * (d @ u) / z) * esc]), z

    def _raio(self, px, py, cam):
        W, H, eye, r, u, f, s = cam; d = f + r * ((px - W / 2) / s) + u * ((H / 2 - py) / s)
        return eye, d / np.linalg.norm(d)

    # ---------------- desenho ----------------
    def _fundo(self, W, H):
        k = (W, H)
        if k not in self._grad:
            if len(self._grad) > 6: self._grad.clear()
            t = np.linspace(0, 1, H)[:, None, None]; g = (np.array(FUNDO_A) * (1 - t) + np.array(FUNDO_B) * t).astype(np.uint8)
            self._grad[k] = Image.fromarray(np.repeat(g, W, axis=1), 'RGB')
        return self._grad[k].copy()

    def _grade(self, d, cam, esc):
        mn, mx = self._limites(); m = max(abs(mn[0]), abs(mx[0]), abs(mn[1]), abs(mx[1]), 30.0); p = 10 if m <= 260 else 50
        L = math.ceil(m * 1.35 / p) * p; n = int(L / p)
        if self.mostrar_grade:
            for i in range(-n, n + 1):
                g = i * p; cor = COR_GRADE_F if i % 5 == 0 else COR_GRADE
                for a, b in (((g, -L, 0), (g, L, 0)), ((-L, g, 0), (L, g, 0))):
                    S, _ = self._proj(np.array([a, b], dtype=float), cam, esc); d.line([tuple(S[0]), tuple(S[1])], fill=cor, width=max(1, int(esc)))
        for a, b, cor in (((0, 0, 0), (L, 0, 0), (214, 84, 84)), ((0, 0, 0), (0, L, 0), (96, 190, 110)), ((0, 0, 0), (0, 0, L * 0.6), (90, 150, 240))):
            S, _ = self._proj(np.array([a, b], dtype=float), cam, esc); d.line([tuple(S[0]), tuple(S[1])], fill=cor, width=max(1, int(1.6 * esc)))

    def _pintar(self, W, H, cam, esc, destaque=True, numeros=None):
        """Desenha tudo num PIL.Image (W x H, ja reduzido). Guarda em self._buf o que o clique precisa."""
        c = self.cena; We, He = int(W * esc), int(H * esc)
        img = self._fundo(We, He); d = ImageDraw.Draw(img); self._grade(d, cam, esc)
        _, _, eye, r, u, f, s = cam
        buf = dict(cam=cam, W=W, H=H, ids=None, seg=None)
        if len(c.F):
            S, z = self._proj(c.V, cam, 1.0); T = S[c.F]; zt = z[c.F].mean(1)
            frente = np.einsum('ij,ij->i', c.N, eye - c.C) > 0
            luz = f * -0.62 + u * 0.62 + r * -0.48; luz = luz / np.linalg.norm(luz)
            sh = 0.34 + 0.66 * np.clip(c.NS @ luz, 0, 1) + 0.10 * np.clip(c.NS @ -f, 0, 1)
            base = np.tile(np.array(COR_PECA, dtype=float), (len(c.F), 1))
            for k, rgb in (c.dv.get('cores_fid') or {}).items(): base[c.fid == k] = rgb          # pecas de cores diferentes (ex.: 3MF colorido)
            if destaque:
                if self.sel_faces and c.tipo == 'cad': base[np.isin(c.fid, list(self.sel_faces))] = COR_SEL
                if self.hover and self.hover[0] == 'f' and c.tipo == 'cad': base[c.fid == self.hover[1]] = COR_HOVER
            cor = np.clip(base * sh[:, None], 0, 255).astype(int)
            idx = np.nonzero(frente)[0]; idx = idx[np.argsort(-zt[idx])]
            pol = d.polygon; Te = (T[idx] * esc).tolist(); Ce = [tuple(x) for x in cor[idx].tolist()]
            for t, k in zip(Te, Ce): pol([tuple(t[0]), tuple(t[1]), tuple(t[2])], fill=k, outline=k)
            # desenho de identidade: cada pixel sabe de qual face (ou triangulo) ele e
            idimg = Image.new('RGB', (W, H), (0, 0, 0)); di = ImageDraw.Draw(idimg); pid = di.polygon
            g = c.fid[idx] + 1; cores = np.column_stack([g & 255, (g >> 8) & 255, (g >> 16) & 255]).tolist()
            for t, k in zip(T[idx].tolist(), cores): pid([tuple(t[0]), tuple(t[1]), tuple(t[2])], fill=tuple(k))
            a = np.asarray(idimg).astype(np.int64); ids = a[:, :, 0] + (a[:, :, 1] << 8) + (a[:, :, 2] << 16); buf['ids'] = ids
            if len(c.SE) and self.mostrar_arestas:
                A2, _ = self._proj(c.SA, cam, 1.0); B2, _ = self._proj(c.SB, cam, 1.0); M = (A2 + B2) / 2
                vis = np.zeros(len(M), dtype=bool); adj = c.adj[c.SE] + 1
                mxi, myi = np.rint(M[:, 0]).astype(int), np.rint(M[:, 1]).astype(int)
                for dx in (-2, -1, 0, 1, 2):
                    for dy in (-2, -1, 0, 1, 2):
                        if abs(dx) + abs(dy) > 3: continue
                        x = mxi + dx; y = myi + dy; ok = (x >= 0) & (x < W) & (y >= 0) & (y < H)
                        v = np.zeros(len(M), dtype=np.int64); v[ok] = ids[y[ok], x[ok]]
                        vis |= ((v == adj[:, 0]) | (v == adj[:, 1])) & (v > 0)
                vis &= ~c.costura[c.SE]
                buf['seg'] = (A2, B2, vis)
                sel = np.isin(c.SE, list(self.sel_arestas)) if (destaque and self.sel_arestas) else np.zeros(len(M), dtype=bool)
                hov = (c.SE == self.hover[1]) if (destaque and self.hover and self.hover[0] == 'a') else np.zeros(len(M), dtype=bool)
                ln = d.line; w1 = max(1, int(round(1.25 * esc)))
                for i in np.nonzero(vis & ~sel & ~hov)[0].tolist(): ln([A2[i, 0] * esc, A2[i, 1] * esc, B2[i, 0] * esc, B2[i, 1] * esc], fill=COR_ARESTA, width=w1)
                for mask, k, w in ((hov, COR_ARESTA_HOVER, 3.2), (sel, COR_ARESTA_SEL, 3.6)):
                    for i in np.nonzero(mask & (vis | sel))[0].tolist(): ln([A2[i, 0] * esc, A2[i, 1] * esc, B2[i, 0] * esc, B2[i, 1] * esc], fill=k, width=max(2, int(round(w * esc))))
        if self.fantasma is not None and len(self.fantasma[1]):
            V, F = self.fantasma; S, z = self._proj(V, cam, esc); T = S[F]; zt = z[F].mean(1)
            t3 = V[F]; n = np.cross(t3[:, 1] - t3[:, 0], t3[:, 2] - t3[:, 0]); ln_ = np.linalg.norm(n, axis=1); ln_[ln_ == 0] = 1; n = n / ln_[:, None]
            sh = 0.55 + 0.45 * np.abs(n @ f); cam_fr = np.einsum('ij,ij->i', n, eye - t3.mean(1)) > 0
            cam_ = Image.new('RGBA', (We, He), (0, 0, 0, 0)); dc = ImageDraw.Draw(cam_)
            for i in np.argsort(-zt).tolist():
                k = tuple(int(v * sh[i]) for v in COR_FANTASMA) + ((120,) if cam_fr[i] else (46,))
                dc.polygon([tuple(T[i, 0]), tuple(T[i, 1]), tuple(T[i, 2])], fill=k)
            img = Image.alpha_composite(img.convert('RGBA'), cam_).convert('RGB'); d = ImageDraw.Draw(img)
        if esc != 1.0: img = img.resize((W, H), Image.LANCZOS)
        d = ImageDraw.Draw(img)
        if self.mostrar_medidas and len(c.F): self._medidas(d, cam)
        if numeros and c.tipo == 'cad': self._numeros(d, cam, numeros, buf)
        if destaque and self.alcas: self._desenhar_alcas(d, cam)
        self._eixinhos(d, cam, W, H)
        return img, buf

    def _medidas(self, d, cam):
        c = self.cena; mn, mx = c.min, c.max; t = mx - mn; fo = fonte(12, True); e = max(2.0, float(np.linalg.norm(t)) * 0.035)
        _, _, eye, r, u, f, s = cam
        ex = mn[1] - e if eye[1] < (mn[1] + mx[1]) / 2 else mx[1] + e            # a cota de X fica do lado da camera
        ey = mx[0] + e if eye[0] > (mn[0] + mx[0]) / 2 else mn[0] - e
        zx = mn[0] - e if eye[0] > (mn[0] + mx[0]) / 2 else mx[0] + e; zy = ex
        for a, b, txt in ((np.array([mn[0], ex, mn[2]]), np.array([mx[0], ex, mn[2]]), '%g' % round(t[0], 2)), (np.array([ey, mn[1], mn[2]]), np.array([ey, mx[1], mn[2]]), '%g' % round(t[1], 2)),
                          (np.array([zx, zy, mn[2]]), np.array([zx, zy, mx[2]]), '%g' % round(t[2], 2))):
            S, _ = self._proj(np.array([a, b]), cam)
            d.line([tuple(S[0]), tuple(S[1])], fill=COR_MEDIDA, width=1)
            for q in S: d.ellipse([q[0] - 2.5, q[1] - 2.5, q[0] + 2.5, q[1] + 2.5], fill=COR_MEDIDA)
            m = (S[0] + S[1]) / 2; w = d.textlength(txt, font=fo)
            d.rounded_rectangle([m[0] - w / 2 - 5, m[1] - 9, m[0] + w / 2 + 5, m[1] + 9], 4, fill=(16, 22, 32), outline=COR_MEDIDA)
            d.text((m[0] - w / 2, m[1] - 8), txt, fill=(225, 240, 255), font=fo)

    def _numeros(self, d, cam, quais, buf):
        """Numeros das arestas e/ou faces (para a IA dizer 'arredonde a aresta 7')."""
        c = self.cena; dv = c.dv; fo = fonte(11, True); ids = buf.get('ids')
        if quais in ('faces', 'tudo') and ids is not None:
            visiveis = set(np.unique(ids).tolist())
            for fc in dv.get('faces', []):
                if fc['id'] + 1 not in visiveis: continue
                ys, xs = np.nonzero(ids == fc['id'] + 1)
                if len(xs) < 30: continue
                x, y = float(np.median(xs)), float(np.median(ys)); t = 'F%d' % fc['id']; w = d.textlength(t, font=fo)
                d.rounded_rectangle([x - w / 2 - 3, y - 8, x + w / 2 + 3, y + 8], 3, fill=(30, 60, 110)); d.text((x - w / 2, y - 7), t, fill=(255, 255, 255), font=fo)
        if quais in ('arestas', 'tudo') and buf.get('seg') is not None:
            A2, B2, vis = buf['seg']
            for i in range(c.n_arestas):
                m = (c.SE == i) & vis
                if not m.any(): continue
                k = np.nonzero(m)[0]; j = k[len(k) // 2]; x, y = (A2[j] + B2[j]) / 2; t = str(i); w = d.textlength(t, font=fo)
                d.rounded_rectangle([x - w / 2 - 3, y - 8, x + w / 2 + 3, y + 8], 3, fill=(255, 196, 70)); d.text((x - w / 2, y - 7), t, fill=(20, 20, 20), font=fo)

    def _eixinhos(self, d, cam, W, H):
        _, _, eye, r, u, f, s = cam; o = np.array([46.0, H - 46.0]); fo = fonte(11, True)
        itens = []
        for v, nome, cor in (((1, 0, 0), 'X', (232, 96, 96)), ((0, 1, 0), 'Y', (106, 204, 122)), ((0, 0, 1), 'Z', (104, 164, 250))):
            v = np.array(v, dtype=float); itens.append((float(v @ f), o + np.array([v @ r, -(v @ u)]) * 30, nome, cor))
        d.ellipse([o[0] - 40, o[1] - 40, o[0] + 40, o[1] + 40], fill=(16, 21, 30), outline=(46, 58, 78))
        for _, p, nome, cor in sorted(itens, key=lambda t: -t[0]):
            d.line([tuple(o), tuple(p)], fill=cor, width=3); d.ellipse([p[0] - 8, p[1] - 8, p[0] + 8, p[1] + 8], fill=cor)
            d.text((p[0] - d.textlength(nome, font=fo) / 2, p[1] - 8), nome, fill=(12, 16, 22), font=fo)

    def redesenhar(self, baixa=False):
        self._baixa = self._baixa or baixa
        if self._agendado: return
        self._agendado = True; self.after(10, self._quadro)

    def _quadro(self):
        self._agendado = False; W, H = self.winfo_width(), self.winfo_height()
        if W < 60 or H < 60: return
        esc = 1.0 if (self._baixa or self._arrastando) else 2.0; self._baixa = False
        img, self._buf = self._pintar(W, H, self._cam(W, H), esc)
        self.ultima_imagem = img; self._img = ImageTk.PhotoImage(img)
        if self._item is None: self._item = self.create_image(0, 0, anchor='nw', image=self._img)
        else: self.itemconfig(self._item, image=self._img)

    def render(self, W=900, H=700, vista='3d', az=None, el=None, numeros=None, medidas=True):
        """Imagem da peca (PIL) sem mexer na tela. numeros: None | 'arestas' | 'faces' | 'tudo'."""
        a0, e0 = VISTAS.get(vista, VISTAS['3d']); az = a0 if az is None else float(az); el = e0 if el is None else float(el)
        mn, mx = self._limites(); rr = float(np.linalg.norm(mx - mn)) / 2 or 20.0
        alvo = (mn + mx) / 2; dist = max(30.0, rr / math.sin(math.radians(self.fov) / 2) * 1.2)
        old = self.mostrar_medidas; self.mostrar_medidas = medidas
        try:
            img, _ = self._pintar(int(W), int(H), self._cam(int(W), int(H), az, el, dist, alvo), 2.0, destaque=False, numeros=numeros)
        finally: self.mostrar_medidas = old
        d = ImageDraw.Draw(img); t = 'Vista: %s' % NOMES_VISTA.get(vista, vista) if az == a0 and el == e0 else 'az %.0f° el %.0f°' % (az, el)
        d.text((12, 10), t, fill=(200, 212, 230), font=fonte(13, True))
        return img

    # ---------------- escolher com o mouse ----------------
    def pick(self, px, py):
        """O que esta debaixo do mouse: ('a', aresta) | ('f', face) | None. Tambem devolve o ponto 3D e a normal (dict)."""
        b = self._buf; c = self.cena
        if not b or b['ids'] is None or not (0 <= px < b['W'] and 0 <= py < b['H']): return None, None
        g = int(b['ids'][int(py), int(px)]) - 1; info = None
        if g >= 0:
            tri = np.nonzero(c.fid == g)[0]; o, dr = self._raio(px, py, b['cam']); V = c.V; F = c.F[tri]
            v0, v1, v2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]; e1, e2 = v1 - v0, v2 - v0; h = np.cross(dr, e2); a = np.einsum('ij,ij->i', e1, h)
            ok = np.abs(a) > 1e-12; a = np.where(ok, a, 1.0); s = o - v0; uu = np.einsum('ij,ij->i', s, h) / a; q = np.cross(s, e1); vv = (q @ dr) / a; t = np.einsum('ij,ij->i', e2, q) / a
            m = ok & (uu >= -1e-6) & (vv >= -1e-6) & (uu + vv <= 1 + 1e-6) & (t > 0)
            if m.any():
                j = np.nonzero(m)[0][np.argmin(t[m])]; info = dict(ponto=o + dr * t[j], normal=c.N[tri[j]].copy())
        if b['seg'] is not None and c.tipo == 'cad':
            A2, B2, vis = b['seg']; p = np.array([px, py], dtype=float); ab = B2 - A2; L2 = np.einsum('ij,ij->i', ab, ab); L2[L2 == 0] = 1
            tt = np.clip(np.einsum('ij,ij->i', p - A2, ab) / L2, 0, 1); dist = np.linalg.norm(A2 + ab * tt[:, None] - p, axis=1); dist[~vis] = 1e9
            if len(dist) and dist.min() <= 6.5: return ('a', int(c.SE[int(np.argmin(dist))])), info
        if g >= 0 and c.tipo == 'cad': return ('f', g), info
        return (('p', 0), info) if g >= 0 else (None, None)

    def _set_hover(self, h):
        if h != self.hover:
            self.hover = h; self.redesenhar()
            if self.ao_passar: self.ao_passar(h)

    def _move(self, ev):
        if self._arrastando or ev.state & 0x0700: return
        if self._hover_job: self.after_cancel(self._hover_job)
        self._hover_job = self.after(25, lambda x=ev.x, y=ev.y: self._hover(x, y))

    def _hover(self, x, y):
        self._hover_job = None
        if self.ao_arrastar and (self.alcas or self.corpo_arrastavel or self.peca_arrastavel):
            a = self._alca_em(x, y); ah = a['id'] if a else None; cur = 'hand2' if a else ''
            if not a and ((self.corpo_arrastavel and self._fantasma_em(x, y) is not None) or (self.peca_arrastavel and self.pick(x, y)[1] is not None)): cur = 'fleur'
            if self.cget('cursor') != cur: self.config(cursor=cur)
            if ah != self._alca_hover: self._alca_hover = ah; self.redesenhar()
            if cur: self._set_hover(None); return
        elif self.cget('cursor'): self.config(cursor='')
        h, _ = self.pick(x, y)
        self._set_hover(h if h and h[0] in ('a', 'f') else None)

    def _aperta(self, ev):
        self.focus_set(); self._ult = (ev.x, ev.y); self._mexeu = False; self._drag = None
        if getattr(ev, 'num', 1) != 1 or not self.ao_arrastar: return
        cam = self._cam(); a = self._alca_em(ev.x, ev.y, cam)
        if a is not None:
            e = a.get('eixo'); self._drag = dict(alvo=a['id'], p0=np.asarray(a['p'], dtype=float).copy(), eixo=None if e is None else np.asarray(e, dtype=float) / np.linalg.norm(e), cam=cam); return
        p = self._fantasma_em(ev.x, ev.y, cam) if self.corpo_arrastavel else None
        if p is None and self.peca_arrastavel:
            info = self.pick(ev.x, ev.y)[1]; p = None if info is None else np.asarray(info['ponto'], dtype=float)
        if p is not None: self._drag = dict(alvo='corpo', p0=p, eixo=None, cam=cam)

    def _ponto_drag(self, px, py):
        """Onde o mouse esta em 3D durante o arrasto: em cima da reta da alca, ou no plano em que a forma desliza."""
        g = self._drag; cam = g['cam']; o, dr = self._raio(px, py, cam); p0 = g['p0']
        if g['eixo'] is not None:
            e = g['eixo']; w = p0 - o; b = float(e @ dr); den = 1.0 - b * b
            if den < 1e-5: return None
            return p0 + e * ((b * float(dr @ w) - float(e @ w)) / den)
        f = cam[5]; k = self.plano_fixo if self.plano_fixo is not None else (2 if abs(f[2]) >= 0.3 else int(np.argmax(np.abs(f))))      # normalmente desliza no chao; em vista de frente/lado, no plano da tela
        if abs(dr[k]) < 1e-6: return None
        t = (p0[k] - o[k]) / dr[k]
        return o + dr * t if t > 0 else None

    def _arrasta(self, ev):
        dx, dy = ev.x - self._ult[0], ev.y - self._ult[1]
        if not self._mexeu and abs(dx) + abs(dy) < 4: return
        if self._drag is not None:
            g = self._drag
            if not self._mexeu:
                self._mexeu = True; self._arrastando = True; self.ao_arrastar('ini', g['alvo'], g['p0'], g['p0'], ev.state)
            p = self._ponto_drag(ev.x, ev.y)
            if p is not None: self.ao_arrastar('mov', g['alvo'], p, g['p0'], ev.state)
            self.redesenhar(baixa=True); return
        self._mexeu = True; self._arrastando = True; self._ult = (ev.x, ev.y)
        if ev.state & 0x0001: self._deslocar(dx, dy)
        else: self.az -= dx * 0.45; self.el = max(-89.9, min(89.9, self.el + dy * 0.45))
        self.redesenhar(baixa=True)

    def _solta(self, ev):
        arr = self._arrastando; self._arrastando = False; g = self._drag; self._drag = None
        if g is not None and self._mexeu:
            self.ao_arrastar('fim', g['alvo'], g['p0'], g['p0'], ev.state); self.redesenhar(); return
        if arr or self._mexeu: self.redesenhar(); return
        h, info = self.pick(ev.x, ev.y); varios = bool(ev.state & 0x0001) or bool(ev.state & 0x0004)
        if h is None or h[0] == 'p':
            if not varios: self.sel_faces = set(); self.sel_arestas = set()
        else:
            alvo = self.sel_arestas if h[0] == 'a' else self.sel_faces
            if not varios:
                ja = h[1] in alvo and len(self.sel_arestas) + len(self.sel_faces) == 1
                self.sel_faces = set(); self.sel_arestas = set(); alvo = self.sel_arestas if h[0] == 'a' else self.sel_faces
                if not ja: alvo.add(h[1])
            elif h[1] in alvo: alvo.discard(h[1])
            else: alvo.add(h[1])
        self.redesenhar()
        if self.ao_escolher: self.ao_escolher(h, info)

    def _deslocar(self, dx, dy):
        W, H, eye, r, u, f, s = self._cam(); k = self.dist / s; self.alvo = self.alvo - r * dx * k + u * dy * k

    def _arrasta_pan(self, ev):
        dx, dy = ev.x - self._ult[0], ev.y - self._ult[1]; self._ult = (ev.x, ev.y); self._arrastando = True; self._deslocar(dx, dy); self.redesenhar(baixa=True)

    def _solta_pan(self, ev):
        self._arrastando = False; self.redesenhar()

    def _roda(self, ev):
        self.dist = max(8.0, min(6000.0, self.dist * (0.88 ** (ev.delta / 120.0)))); self.redesenhar(baixa=True)
        if getattr(self, '_zoom_job', None): self.after_cancel(self._zoom_job)
        self._zoom_job = self.after(160, self.redesenhar)
