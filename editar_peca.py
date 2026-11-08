"""Edicao simples de pecas (STL): furo, corte, formas somadas/subtraidas e texto (relevo ou gravado).
Todas as funcoes recebem um trimesh.Trimesh e devolvem OUTRO (o original nunca e alterado). Coordenadas em mm, no sistema da propria malha
(X/Y centrados na peca, Z=0 na base). Usa manifold3d para cortar/juntar formas (so funciona em malhas FECHADAS: sem buracos)."""
import os
import numpy as np
import trimesh
from trimesh.transformations import rotation_matrix, translation_matrix

FACES = ('cima', 'frente', 'tras', 'esquerda', 'direita')
EIXOS = ('x', 'y', 'z')
FONTES_BOAS = ['Arial', 'Arial Black', 'Segoe UI', 'Consolas', 'Courier New', 'Times New Roman', 'Impact', 'Verdana', 'Comic Sans MS', 'Georgia']


class ErroEdicao(Exception):
    pass


def carregar(caminho):
    m = trimesh.load(caminho, force='mesh')
    if isinstance(m, trimesh.Scene): m = m.dump(concatenate=True)
    return m


def preparar(m):
    """Copia, junta vertices, tira faces degeneradas, fecha furinhos e confere se e 'fechada' (necessario para cortar/juntar)."""
    m = m.copy(); m.merge_vertices(); m.update_faces(m.nondegenerate_faces()); m.remove_unreferenced_vertices()
    if not m.is_watertight:
        try: trimesh.repair.fill_holes(m); trimesh.repair.fix_normals(m)
        except Exception: pass
    if not m.is_watertight:
        raise ErroEdicao('Esta peca tem buracos na malha (nao e "fechada"), entao nao da para cortar/juntar formas nela. Conserte o STL (por exemplo no Windows 3D Builder, "Reparar") e abra de novo.')
    return m


def _bool(a, b, modo):
    a = preparar(a)
    try:
        r = trimesh.boolean.union([a, b], engine='manifold') if modo == 'soma' else trimesh.boolean.difference([a, b], engine='manifold')
    except Exception as e:
        raise ErroEdicao('Nao consegui %s: %s' % ('juntar' if modo == 'soma' else 'cortar', str(e)[:120]))
    if r is None or len(r.faces) == 0:
        raise ErroEdicao('O resultado ficou vazio (a forma cobriu a peca inteira?).')
    return r


def _diag(m):
    return float(np.linalg.norm(m.bounds[1] - m.bounds[0]))


def info(m):
    b = m.bounds; t = b[1] - b[0]
    return dict(min=[round(float(v), 2) for v in b[0]], max=[round(float(v), 2) for v in b[1]], tamanho=[round(float(v), 2) for v in t], faces=int(len(m.faces)), fechada=bool(m.is_watertight))


# ---------------- ferramentas (formas) ----------------
def forma_cilindro(diametro, comprimento, eixo='z', centro=(0, 0, 0)):
    c = trimesh.creation.cylinder(radius=max(0.05, diametro / 2.0), height=max(0.05, comprimento), sections=64)
    if eixo == 'x': c.apply_transform(rotation_matrix(np.pi / 2, [0, 1, 0]))
    elif eixo == 'y': c.apply_transform(rotation_matrix(np.pi / 2, [1, 0, 0]))
    c.apply_translation(centro); return c


def forma_caixa(largura, profundidade, altura, centro=(0, 0, 0)):
    c = trimesh.creation.box(extents=(max(0.05, largura), max(0.05, profundidade), max(0.05, altura))); c.apply_translation(centro); return c


def forma_esfera(diametro, centro=(0, 0, 0)):
    c = trimesh.creation.icosphere(subdivisions=3, radius=max(0.05, diametro / 2.0)); c.apply_translation(centro); return c


# ---------------- operacoes ----------------
def furo(m, x, y, z, diametro, comprimento=0, eixo='z'):
    """Cilindro subtraido, centrado em (x,y,z). comprimento 0 = atravessa a peca inteira."""
    if eixo not in EIXOS: raise ErroEdicao('eixo deve ser x, y ou z')
    if diametro <= 0: raise ErroEdicao('o diametro precisa ser maior que zero')
    L = comprimento if comprimento and comprimento > 0 else _diag(m) * 3
    return _bool(m, forma_cilindro(diametro, L, eixo, (x, y, z)), 'sub')


def cortar_plano(m, eixo, posicao, manter='menor'):
    """Corta a peca num plano e joga fora um dos lados. manter='menor' fica com a parte de coordenada menor (ex.: eixo z: a parte de baixo)."""
    if eixo not in EIXOS: raise ErroEdicao('eixo deve ser x, y ou z')
    if manter not in ('menor', 'maior'): raise ErroEdicao("manter deve ser 'menor' ou 'maior'")
    g = _diag(m) * 3; i = EIXOS.index(eixo); ext = [g * 2] * 3; ext[i] = g
    c = [0.0, 0.0, 0.0]; c[i] = posicao + (g / 2 if manter == 'menor' else -g / 2)
    b = m.bounds
    if not (b[0][i] < posicao < b[1][i]): raise ErroEdicao('o plano de corte (%s=%.1f) esta fora da peca (de %.1f a %.1f)' % (eixo, posicao, b[0][i], b[1][i]))
    for k in range(3):
        if k != i: c[k] = float((b[0][k] + b[1][k]) / 2)
    return _bool(m, trimesh.creation.box(extents=ext, transform=translation_matrix(c)), 'sub')


def forma(m, tipo, modo, x, y, z, a, b=None, c=None, eixo='z'):
    """Soma ou subtrai uma forma. caixa: a=largura(X) b=profundidade(Y) c=altura(Z); cilindro: a=diametro b=comprimento; esfera: a=diametro."""
    if modo not in ('somar', 'subtrair'): raise ErroEdicao("modo deve ser 'somar' ou 'subtrair'")
    if tipo == 'caixa': f = forma_caixa(a, b or a, c or a, (x, y, z))
    elif tipo == 'cilindro': f = forma_cilindro(a, b or a, eixo, (x, y, z))
    elif tipo == 'esfera': f = forma_esfera(a, (x, y, z))
    else: raise ErroEdicao("tipo deve ser 'caixa', 'cilindro' ou 'esfera'")
    return _bool(m, f, 'soma' if modo == 'somar' else 'sub')


def fontes_disponiveis():
    try:
        from matplotlib import font_manager as fm
        nomes = {f.name for f in fm.fontManager.ttflist}
        bons = [n for n in FONTES_BOAS if n in nomes]
        return bons or ['DejaVu Sans']
    except Exception:
        return ['DejaVu Sans']


def _poligono_texto(txt, altura_letra, fonte):
    from matplotlib.textpath import TextPath
    from matplotlib.font_manager import FontProperties
    from shapely.geometry import Polygon
    from shapely import affinity
    if not txt.strip(): raise ErroEdicao('escreva o texto')
    tp = TextPath((0, 0), txt, size=altura_letra, prop=FontProperties(family=fonte))
    poly = None
    for anel in tp.to_polygons():
        if len(anel) < 3: continue
        p = Polygon(anel).buffer(0)
        if p.is_empty: continue
        poly = p if poly is None else poly.symmetric_difference(p)      # par-impar: miolo de letras como 'o', 'a', 'e' fica vazado
    if poly is None or poly.is_empty: raise ErroEdicao('nao consegui desenhar esse texto com essa fonte')
    x0, y0, x1, y1 = poly.bounds
    return affinity.translate(poly, -(x0 + x1) / 2, -(y0 + y1) / 2)


def malha_texto(txt, altura_letra, profundidade, fonte='Arial'):
    """Texto centrado na origem, no plano XY, extrudado de z=0 ate z=profundidade."""
    poly = _poligono_texto(txt, altura_letra, fonte)
    geos = list(poly.geoms) if hasattr(poly, 'geoms') else [poly]
    ms = [trimesh.creation.extrude_polygon(g, profundidade) for g in geos if g.area > 1e-6]
    if not ms: raise ErroEdicao('texto pequeno demais')
    return trimesh.util.concatenate(ms)


_ROT = {'cima': np.eye(4), 'frente': rotation_matrix(np.pi / 2, [1, 0, 0]),
        'tras': rotation_matrix(np.pi, [0, 0, 1]) @ rotation_matrix(np.pi / 2, [1, 0, 0]),
        'direita': rotation_matrix(np.pi / 2, [0, 0, 1]) @ rotation_matrix(np.pi / 2, [1, 0, 0]),
        'esquerda': rotation_matrix(-np.pi / 2, [0, 0, 1]) @ rotation_matrix(np.pi / 2, [1, 0, 0])}


def texto_malha_posicionada(m, txt, altura_letra, profundidade, modo, face, u, v, giro, fonte):
    """A malha do texto ja no lugar certo na face. Relevo: sai da face (entra 0.4 mm dentro para colar). Gravado: entra na peca."""
    if face not in FACES: raise ErroEdicao('face deve ser uma de: ' + ', '.join(FACES))
    if modo not in ('relevo', 'gravado'): raise ErroEdicao("modo deve ser 'relevo' ou 'gravado'")
    if profundidade <= 0: raise ErroEdicao('a altura/profundidade do texto precisa ser maior que zero')
    emb = 0.4
    t = malha_texto(txt, altura_letra, profundidade + emb, fonte)          # z de 0 a profundidade+emb
    if giro: t.apply_transform(rotation_matrix(np.radians(giro), [0, 0, 1]))
    # relevo: a base do texto fica emb DENTRO da peca (z=-emb); gravado: a base fica 'profundidade' dentro (z=-profundidade), ponta passa 'emb' para fora
    t.apply_translation([0, 0, -emb if modo == 'relevo' else -profundidade])
    t.apply_translation([u, v, 0]); t.apply_transform(_ROT[face])
    b = m.bounds; c = (b[0] + b[1]) / 2
    ancora = {'cima': [c[0], c[1], b[1][2]], 'frente': [c[0], b[0][1], c[2]], 'tras': [c[0], b[1][1], c[2]],
              'direita': [b[1][0], c[1], c[2]], 'esquerda': [b[0][0], c[1], c[2]]}[face]
    t.apply_translation(ancora)
    return t


def texto(m, txt, altura_letra, profundidade, modo='relevo', face='cima', u=0.0, v=0.0, giro=0.0, fonte='Arial'):
    t = texto_malha_posicionada(m, txt, altura_letra, profundidade, modo, face, u, v, giro, fonte)
    r = _bool(m, t, 'soma' if modo == 'relevo' else 'sub')
    if modo == 'gravado' and len(r.faces) == len(m.faces) and abs(float(r.volume) - float(m.volume)) < 1e-6:
        raise ErroEdicao('o texto nao tocou na peca (a face nao esta onde o programa esperava). Tente outra face ou posicao.')
    return r


def recentralizar(m):
    """X/Y centrados na origem e a base em z=0 (como o programa guarda as pecas)."""
    m = m.copy(); b = m.bounds
    m.apply_translation([-(b[0][0] + b[1][0]) / 2, -(b[0][1] + b[1][1]) / 2, -b[0][2]])
    return m


def salvar(m, pasta, nome_base):
    os.makedirs(pasta, exist_ok=True)
    base = os.path.splitext(os.path.basename(nome_base))[0]; n = 1
    while os.path.exists(os.path.join(pasta, '%s_editada_%d.stl' % (base, n))): n += 1
    caminho = os.path.join(pasta, '%s_editada_%d.stl' % (base, n))
    recentralizar(m).export(caminho)
    return caminho
