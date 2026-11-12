"""Icones da aba Modelar, desenhados por codigo (sem arquivos de imagem): icone(nome, tamanho) -> ImageTk.PhotoImage."""
import math
from PIL import Image, ImageDraw, ImageTk

CLARO = (226, 234, 246); AZUL = (96, 170, 255); LARANJA = (255, 148, 66); VERDE = (70, 214, 160); VERM = (255, 110, 110); CINZA = (128, 142, 164)
_cache = {}


class _D:
    """Desenha em coordenadas 0..100 (a imagem real e 4x maior e depois reduzida: fica lisinha)."""
    def __init__(self, n):
        self.k = n * 4 / 100.0; self.img = Image.new('RGBA', (n * 4, n * 4), (0, 0, 0, 0)); self.d = ImageDraw.Draw(self.img); self.w = max(2, int(round(7 * self.k)))

    def _p(self, pts): return [(x * self.k, y * self.k) for x, y in pts]

    def linha(self, pts, cor=CLARO, w=1.0, fechar=False):
        p = self._p(pts)
        if fechar: p.append(p[0])
        self.d.line(p, fill=cor, width=max(1, int(self.w * w)), joint='curve')
        r = self.w * w / 2
        for x, y in p: self.d.ellipse([x - r, y - r, x + r, y + r], fill=cor)

    def poli(self, pts, cor): self.d.polygon(self._p(pts), fill=cor)

    def elipse(self, x0, y0, x1, y1, cor=CLARO, w=1.0, fill=None):
        self.d.ellipse([x0 * self.k, y0 * self.k, x1 * self.k, y1 * self.k], outline=cor, width=max(1, int(self.w * w)), fill=fill)

    def arco(self, x0, y0, x1, y1, a0, a1, cor=CLARO, w=1.0):
        self.d.arc([x0 * self.k, y0 * self.k, x1 * self.k, y1 * self.k], a0, a1, fill=cor, width=max(1, int(self.w * w)))

    def seta(self, a, b, cor=CLARO, w=1.0, t=13):
        self.linha([a, b], cor, w); ang = math.atan2(b[1] - a[1], b[0] - a[0])
        self.poli([b, (b[0] - t * math.cos(ang - 0.5), b[1] - t * math.sin(ang - 0.5)), (b[0] - t * math.cos(ang + 0.5), b[1] - t * math.sin(ang + 0.5))], cor)
        e = t * 0.35; self.poli([(b[0] + e * math.cos(ang), b[1] + e * math.sin(ang)), (b[0] - t * math.cos(ang - 0.6), b[1] - t * math.sin(ang - 0.6)), (b[0] - t * math.cos(ang + 0.6), b[1] - t * math.sin(ang + 0.6))], cor)

    def fim(self, n): return self.img.resize((n, n), Image.LANCZOS)


def _cubo(d, cor=CLARO, topo=None):
    if topo: d.poli([(50, 14), (86, 32), (50, 50), (14, 32)], topo)
    d.linha([(50, 14), (86, 32), (86, 70), (50, 88), (14, 70), (14, 32)], cor, fechar=True); d.linha([(14, 32), (50, 50), (86, 32)], cor); d.linha([(50, 50), (50, 88)], cor)


def _desenhar(nome, d):
    if nome == 'caixa': _cubo(d, CLARO, AZUL + (150,))
    elif nome == 'cilindro':
        d.elipse(20, 12, 80, 40, CLARO, fill=AZUL + (150,)); d.linha([(20, 26), (20, 72)]); d.linha([(80, 26), (80, 72)]); d.arco(20, 58, 80, 86, 0, 180)
    elif nome == 'tubo':
        d.elipse(18, 12, 82, 42, CLARO); d.elipse(34, 19, 66, 35, AZUL, 0.9); d.linha([(18, 27), (18, 72)]); d.linha([(82, 27), (82, 72)]); d.arco(18, 57, 82, 87, 0, 180)
    elif nome == 'esfera':
        d.elipse(14, 14, 86, 86, CLARO, fill=AZUL + (110,)); d.arco(14, 36, 86, 64, 0, 180, CLARO, 0.8)
    elif nome == 'cone':
        d.poli([(50, 12), (82, 74), (18, 74)], AZUL + (120,)); d.linha([(18, 74), (50, 12), (82, 74)]); d.arco(18, 60, 82, 88, 0, 180)
    elif nome == 'toro':
        d.elipse(10, 26, 90, 74, CLARO, fill=AZUL + (120,)); d.elipse(34, 42, 66, 58, CLARO, 0.9, fill=(0, 0, 0, 0)); d.d.ellipse([34 * d.k, 42 * d.k, 66 * d.k, 58 * d.k], fill=(20, 26, 36, 255), outline=CLARO, width=int(d.w * 0.9))
    elif nome == 'prisma':
        p = [(50 + 36 * math.cos(math.radians(a)), 34 + 18 * math.sin(math.radians(a))) for a in range(0, 360, 60)]
        d.poli(p, AZUL + (150,)); d.linha(p, CLARO, fechar=True)
        for q in (p[0], p[1], p[2], p[3]): d.linha([q, (q[0], q[1] + 36)])
        d.linha([(p[0][0], p[0][1] + 36), (p[1][0], p[1][1] + 36), (p[2][0], p[2][1] + 36), (p[3][0], p[3][1] + 36)])
    elif nome == 'cunha':
        d.poli([(14, 78), (70, 78), (14, 30)], AZUL + (140,)); d.linha([(14, 78), (70, 78), (14, 30)], fechar=True); d.linha([(70, 78), (90, 62), (34, 14), (14, 30)]); d.linha([(34, 14), (34, 30)], CINZA, 0.6)
    elif nome == 'texto':
        d.linha([(22, 82), (50, 16), (78, 82)], CLARO, 1.25); d.linha([(34, 58), (66, 58)], AZUL, 1.25)
    elif nome == 'extrudar':
        d.poli([(18, 70), (56, 82), (84, 66), (46, 54)], AZUL + (170,)); d.linha([(18, 70), (56, 82), (84, 66), (46, 54)], CLARO, 0.9, True); d.seta((52, 60), (52, 14), LARANJA, 1.2, 16)
    elif nome == 'revolucao':
        d.linha([(50, 10), (50, 90)], CINZA, 0.7); d.poli([(50, 24), (74, 24), (66, 50), (80, 76), (50, 76)], AZUL + (160,)); d.linha([(50, 24), (74, 24), (66, 50), (80, 76), (50, 76)]); d.arco(16, 66, 84, 96, 20, 160, LARANJA, 1.1); d.poli([(16, 84), (30, 78), (26, 94)], LARANJA)
    elif nome == 'loft':
        d.linha([(18, 78), (82, 78), (82, 92), (18, 92)], CLARO, 0.9, True); d.elipse(34, 8, 66, 26, CLARO, 0.9, fill=AZUL + (150,)); d.linha([(18, 78), (34, 17)], AZUL); d.linha([(82, 78), (66, 17)], AZUL)
    elif nome == 'varrer':
        d.arco(18, 18, 118, 118, 180, 270, AZUL, 2.6); d.arco(18, 18, 118, 118, 180, 270, (20, 26, 36), 1.2); d.elipse(8, 58, 30, 80, CLARO, fill=AZUL + (160,)); d.seta((56, 18), (84, 18), LARANJA, 1.0, 13)
    elif nome == 'arredondar':
        d.linha([(16, 84), (16, 46)]); d.arco(16, 16, 76, 76, 180, 270, LARANJA, 1.4); d.linha([(46, 16), (84, 16)]); d.linha([(16, 84), (84, 84), (84, 16)], CINZA, 0.6)
    elif nome == 'chanfrar':
        d.linha([(16, 84), (16, 50)]); d.linha([(16, 50), (50, 16)], LARANJA, 1.4); d.linha([(50, 16), (84, 16)]); d.linha([(16, 84), (84, 84), (84, 16)], CINZA, 0.6)
    elif nome == 'casca':
        d.linha([(14, 22), (14, 84), (86, 84), (86, 22)], CLARO, 1.2); d.linha([(30, 22), (30, 68), (70, 68), (70, 22)], AZUL, 1.0); d.linha([(14, 22), (30, 22)]); d.linha([(70, 22), (86, 22)])
    elif nome == 'furo':
        d.poli([(12, 56), (50, 38), (88, 56), (50, 74)], AZUL + (110,)); d.linha([(12, 56), (50, 38), (88, 56), (50, 74)], CLARO, 0.9, True); d.elipse(36, 48, 64, 64, CLARO, 0.9, fill=(16, 20, 28, 255)); d.seta((50, 8), (50, 44), LARANJA, 1.1, 14)
    elif nome == 'cortar':
        _cubo(d, CINZA); d.poli([(6, 52), (50, 74), (94, 52), (50, 30)], LARANJA + (150,)); d.linha([(6, 52), (50, 74), (94, 52), (50, 30)], LARANJA, 0.9, True)
    elif nome == 'mover':
        for a, b in (((50, 50), (50, 10)), ((50, 50), (50, 90)), ((50, 50), (10, 50)), ((50, 50), (90, 50))): d.seta(a, b, CLARO, 1.0, 14)
    elif nome == 'girar':
        d.arco(16, 16, 84, 84, 40, 320, CLARO, 1.2); d.poli([(84, 22), (82, 48), (60, 38)], CLARO); d.elipse(42, 42, 58, 58, AZUL, fill=AZUL)
    elif nome == 'escalar':
        d.linha([(14, 50), (14, 86), (50, 86), (50, 50)], AZUL, 1.0, True); d.linha([(14, 14), (86, 14), (86, 86)], CINZA, 0.7); d.seta((40, 60), (80, 20), LARANJA, 1.1, 15)
    elif nome == 'espelhar':
        d.linha([(50, 8), (50, 92)], CINZA, 0.6); d.poli([(40, 22), (40, 78), (10, 78)], AZUL + (190,)); d.linha([(40, 22), (40, 78), (10, 78)], CLARO, 0.9, True); d.linha([(60, 22), (60, 78), (90, 78)], CLARO, 0.9, True)
    elif nome == 'assentar':
        d.linha([(8, 84), (92, 84)], VERDE, 1.3); d.linha([(28, 32), (72, 32), (72, 72), (28, 72)], CLARO, 1.0, True); d.seta((50, 6), (50, 26), LARANJA, 1.0, 12)
    elif nome == 'importar':
        d.linha([(16, 60), (16, 86), (84, 86), (84, 60)], CLARO, 1.2); d.seta((50, 10), (50, 66), AZUL, 1.3, 18)
    elif nome == 'exportar':
        d.linha([(16, 60), (16, 86), (84, 86), (84, 60)], CLARO, 1.2); d.seta((50, 68), (50, 12), VERDE, 1.3, 18)
    elif nome == 'codigo':
        d.linha([(34, 24), (10, 50), (34, 76)], CLARO, 1.2); d.linha([(66, 24), (90, 50), (66, 76)], CLARO, 1.2); d.linha([(58, 14), (42, 86)], AZUL, 1.2)
    elif nome == 'desfazer':
        d.arco(22, 28, 86, 92, 180, 20, CLARO, 1.3); d.poli([(6, 50), (40, 44), (26, 76)], CLARO)
    elif nome == 'refazer':
        d.arco(14, 28, 78, 92, 160, 0, CLARO, 1.3); d.poli([(94, 50), (60, 44), (74, 76)], CLARO)
    elif nome == 'mesa':
        d.poli([(8, 66), (50, 86), (92, 66), (50, 46)], VERDE + (120,)); d.linha([(8, 66), (50, 86), (92, 66), (50, 46)], VERDE, 0.9, True); d.linha([(34, 30), (66, 30), (66, 58), (34, 58)], CLARO, 1.0, True); d.linha([(34, 30), (44, 18), (76, 18), (66, 30)], CLARO, 0.9); d.linha([(76, 18), (76, 46), (66, 58)], CLARO, 0.9)
    elif nome == 'novo':
        d.linha([(22, 10), (60, 10), (80, 30), (80, 90), (22, 90)], CLARO, 1.0, True); d.linha([(60, 10), (60, 30), (80, 30)], CLARO, 0.8); d.linha([(51, 44), (51, 76)], VERDE, 1.3); d.linha([(35, 60), (67, 60)], VERDE, 1.3)
    elif nome == 'abrir':
        d.linha([(8, 84), (8, 22), (36, 22), (44, 32), (84, 32), (84, 46)], CLARO, 1.0); d.poli([(8, 84), (24, 46), (96, 46), (80, 84)], AZUL + (150,)); d.linha([(8, 84), (24, 46), (96, 46), (80, 84)], CLARO, 1.0, True)
    elif nome == 'salvar':
        d.linha([(12, 12), (72, 12), (88, 28), (88, 88), (12, 88)], CLARO, 1.0, True); d.linha([(30, 12), (30, 36), (66, 36), (66, 12)], CLARO, 0.9); d.linha([(28, 88), (28, 58), (72, 58), (72, 88)], AZUL, 1.0)
    elif nome == 'olho':
        d.arco(8, 22, 92, 92, 200, 340, CLARO, 1.1); d.arco(8, 8, 92, 78, 20, 160, CLARO, 1.1); d.elipse(38, 38, 62, 62, AZUL, fill=AZUL)
    elif nome == 'olho_off':
        d.arco(8, 22, 92, 92, 200, 340, CINZA, 1.1); d.arco(8, 8, 92, 78, 20, 160, CINZA, 1.1); d.linha([(18, 84), (82, 16)], VERM, 1.2)
    elif nome == 'lixo':
        d.linha([(14, 26), (86, 26)], VERM, 1.2); d.linha([(38, 26), (38, 12), (62, 12), (62, 26)], VERM, 1.0); d.linha([(24, 26), (30, 90), (70, 90), (76, 26)], VERM, 1.1); d.linha([(42, 42), (43, 76)], VERM, 0.8); d.linha([(58, 42), (57, 76)], VERM, 0.8)
    elif nome == 'variaveis':
        d.linha([(12, 26), (34, 78)], CLARO, 1.3); d.linha([(48, 26), (34, 78)], CLARO, 1.3); d.linha([(62, 44), (90, 44)], AZUL, 1.3); d.linha([(62, 64), (90, 64)], AZUL, 1.3)
    elif nome == 'enquadrar':
        for a, b, c in (((10, 34), (10, 10), (34, 10)), ((66, 10), (90, 10), (90, 34)), ((90, 66), (90, 90), (66, 90)), ((34, 90), (10, 90), (10, 66))): d.linha([a, b, c], CLARO, 1.2)
        d.linha([(36, 36), (64, 36), (64, 64), (36, 64)], AZUL, 1.0, True)
    elif nome == 'selecionar':
        d.poli([(22, 8), (22, 78), (40, 62), (54, 92), (66, 86), (52, 58), (76, 56)], CLARO)
    elif nome == 'ret': d.linha([(12, 24), (88, 24), (88, 76), (12, 76)], CLARO, 1.2, True)
    elif nome == 'circ': d.elipse(14, 14, 86, 86, CLARO, 1.2)
    elif nome == 'elipse': d.elipse(8, 26, 92, 74, CLARO, 1.2)
    elif nome == 'poli': d.linha([(14, 80), (30, 20), (62, 34), (88, 16), (78, 84)], CLARO, 1.2, True)
    elif nome == 'reg': d.linha([(50 + 40 * math.cos(math.radians(a)), 50 + 40 * math.sin(math.radians(a))) for a in range(0, 360, 60)], CLARO, 1.2, True)
    elif nome == 'rasgo':
        d.linha([(30, 30), (70, 30)], CLARO, 1.2); d.linha([(30, 70), (70, 70)], CLARO, 1.2); d.arco(10, 30, 50, 70, 90, 270, CLARO, 1.2); d.arco(50, 30, 90, 70, 270, 90, CLARO, 1.2)
    elif nome == 'mais': d.linha([(50, 14), (50, 86)], CLARO, 1.5); d.linha([(14, 50), (86, 50)], CLARO, 1.5)
    elif nome == 'fechar': d.linha([(22, 22), (78, 78)], CLARO, 1.3); d.linha([(78, 22), (22, 78)], CLARO, 1.3)
    elif nome == 'ok': d.linha([(14, 54), (40, 80), (88, 22)], VERDE, 1.6)
    elif nome == 'lapis': d.linha([(16, 84), (22, 62), (70, 14), (86, 30), (38, 78)], CLARO, 1.1, True); d.linha([(60, 24), (76, 40)], AZUL, 1.0)
    elif nome == 'ia':
        d.linha([(50, 8), (58, 40), (92, 50), (58, 60), (50, 92), (42, 60), (8, 50), (42, 40)], LARANJA, 1.0, True); d.poli([(50, 8), (58, 40), (92, 50), (58, 60), (50, 92), (42, 60), (8, 50), (42, 40)], LARANJA + (130,))
    else: d.elipse(30, 30, 70, 70, CINZA)


def imagem(nome, n=28):
    d = _D(n); _desenhar(nome, d); return d.fim(n)


def icone(nome, n=28):
    k = (nome, n)
    if k not in _cache: _cache[k] = ImageTk.PhotoImage(imagem(nome, n))
    return _cache[k]
