"""Leitor de 3MF com CORES. Devolve as PARTES do arquivo (cada uma com nome, cor e malha), para a Mesa 3D.
De onde a cor vem (nesta ordem de confianca):
  1. NOME da parte com uma cor (ex.: 'Branco (2)', 'Vermelho', 'Black body', 'Azul')   <- o arquivo da luminaria so tem isto
  2. Cor do EXTRUSOR/FILAMENTO escolhido para a parte (PrusaSlicer: Slic3r_PE_model.config; Bambu/Orca: model_settings.config)
  3. Cor padrao 3MF (basematerials, colorgroup, cor por triangulo)
Sem nenhuma cor: a parte vem sem cor (None).
PrusaSlicer, Bambu/Orca e 3MF padrao. Bambu/Orca sao 'melhor esforco' (sem arquivo de exemplo para testar)."""
import os, re, json, zipfile, unicodedata
import xml.etree.ElementTree as ET
import numpy as np
import trimesh

PALAVRAS_COR = {
    'branco': '#F2F2F2', 'white': '#F2F2F2', 'blanco': '#F2F2F2', 'белый': '#F2F2F2',
    'preto': '#1A1A1A', 'black': '#1A1A1A', 'negro': '#1A1A1A', 'черный': '#1A1A1A', 'чёрный': '#1A1A1A',
    'vermelho': '#D62828', 'red': '#D62828', 'rojo': '#D62828', 'красный': '#D62828',
    'azul': '#1E6FD9', 'blue': '#1E6FD9', 'синий': '#1E6FD9',
    'verde': '#2EAD4B', 'green': '#2EAD4B', 'зеленый': '#2EAD4B',
    'amarelo': '#F7D117', 'yellow': '#F7D117', 'amarillo': '#F7D117', 'желтый': '#F7D117',
    'laranja': '#FF8A1F', 'orange': '#FF8A1F', 'naranja': '#FF8A1F', 'оранжевый': '#FF8A1F',
    'roxo': '#7B3FC4', 'purple': '#7B3FC4', 'violeta': '#7B3FC4', 'morado': '#7B3FC4', 'violet': '#7B3FC4',
    'rosa': '#FF7FB0', 'pink': '#FF7FB0',
    'cinza': '#8C8C8C', 'gray': '#8C8C8C', 'grey': '#8C8C8C', 'gris': '#8C8C8C', 'серый': '#8C8C8C',
    'marrom': '#7A4B2A', 'brown': '#7A4B2A', 'castanho': '#7A4B2A',
    'dourado': '#D4AF37', 'gold': '#D4AF37', 'dorado': '#D4AF37', 'ouro': '#D4AF37',
    'prata': '#C0C0C0', 'silver': '#C0C0C0', 'plata': '#C0C0C0',
    'ciano': '#19C3D6', 'cyan': '#19C3D6', 'turquesa': '#19C3D6', 'bege': '#E8D8B8', 'beige': '#E8D8B8', 'natural': '#EAE2CF',
}
NOMES_HEX = {}


def _sem_acento(t):
    return ''.join(c for c in unicodedata.normalize('NFD', t.lower()) if unicodedata.category(c) != 'Mn')


def cor_do_nome(nome):
    """'Vermelho (3)' -> '#D62828'. None se o nome nao tem cor."""
    for tok in re.split(r'[^\w]+', nome.lower()):
        if tok in PALAVRAS_COR: return PALAVRAS_COR[tok]
        t2 = _sem_acento(tok)
        if t2 in PALAVRAS_COR: return PALAVRAS_COR[t2]
    return None


def _hex(c):
    c = (c or '').strip()
    m = re.match(r'#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?$', c)
    return ('#' + m.group(1).upper()) if m else None


def _nome_cor(hexcor):
    """Nome simples em portugues para mostrar na tela (a cor mais proxima da tabela)."""
    if not hexcor: return 'sem cor'
    r, g, b = [int(hexcor[i:i + 2], 16) for i in (1, 3, 5)]
    melhor, dm = None, 1e9
    for n, h in (('Branco', '#F2F2F2'), ('Preto', '#1A1A1A'), ('Vermelho', '#D62828'), ('Azul', '#1E6FD9'), ('Verde', '#2EAD4B'), ('Amarelo', '#F7D117'),
                 ('Laranja', '#FF8A1F'), ('Roxo', '#7B3FC4'), ('Rosa', '#FF7FB0'), ('Cinza', '#8C8C8C'), ('Marrom', '#7A4B2A'), ('Dourado', '#D4AF37'),
                 ('Prata', '#C0C0C0'), ('Ciano', '#19C3D6'), ('Bege', '#E8D8B8')):
        rr, gg, bb = [int(h[i:i + 2], 16) for i in (1, 3, 5)]
        d = (r - rr) ** 2 + (g - gg) ** 2 + (b - bb) ** 2
        if d < dm: melhor, dm = n, d
    return melhor


def _tag(e):
    return e.tag.split('}')[-1]


def _matriz(txt):
    if not txt: return np.eye(4)
    v = [float(x) for x in txt.split()]
    if len(v) != 12: return np.eye(4)
    M = np.eye(4)
    M[:3, :3] = np.array(v[:9]).reshape(3, 3).T
    M[:3, 3] = v[9:12]
    return M


def _escala_unidade(u):
    return {'micron': 0.001, 'millimeter': 1.0, 'centimeter': 10.0, 'inch': 25.4, 'foot': 304.8, 'meter': 1000.0}.get((u or 'millimeter').lower(), 1.0)


class Importado:
    def __init__(self, nome, cor, malha, origem):
        self.nome = nome; self.cor = cor; self.malha = malha; self.origem = origem

    def __repr__(self): return '<%s %s %d tri (%s)>' % (self.nome, self.cor, len(self.malha.faces), self.origem)


def _ler_modelo(xml_bytes):
    """-> (unidade, objetos{id: dict(nome, verts, tris(n,3), tri_pid(n)|None, tri_p1(n)|None, pid, pindex, comps[(id, M, path)])}, itens[(id, M)], cores{(pid,idx): hex})."""
    raiz = ET.fromstring(xml_bytes)
    unidade = raiz.get('unit', 'millimeter')
    objs, itens, cores = {}, [], {}
    for e in raiz.iter():
        t = _tag(e)
        if t in ('colorgroup', 'basematerials'):
            pid = e.get('id')
            for i, c in enumerate([x for x in e if _tag(x) in ('color', 'base')]):
                cores[(pid, i)] = _hex(c.get('color') or c.get('displaycolor'))
        elif t == 'object':
            o = dict(nome=e.get('name') or ('objeto ' + e.get('id', '?')), verts=None, tris=None, tri_pid=None, tri_p1=None, pid=e.get('pid'), pindex=e.get('pindex'), comps=[])
            mesh = next((x for x in e if _tag(x) == 'mesh'), None)
            if mesh is not None:
                vs = next(x for x in mesh if _tag(x) == 'vertices'); ts = next(x for x in mesh if _tag(x) == 'triangles')
                o['verts'] = np.array([[float(v.get('x')), float(v.get('y')), float(v.get('z'))] for v in vs], dtype=float)
                tr = list(ts)
                o['tris'] = np.array([[int(t_.get('v1')), int(t_.get('v2')), int(t_.get('v3'))] for t_ in tr], dtype=int)
                if any(t_.get('pid') or t_.get('p1') for t_ in tr):
                    o['tri_pid'] = [t_.get('pid') or e.get('pid') for t_ in tr]; o['tri_p1'] = [t_.get('p1') for t_ in tr]
            comps = next((x for x in e if _tag(x) == 'components'), None)
            if comps is not None:
                for c in comps:
                    o['comps'].append((c.get('objectid'), _matriz(c.get('transform')), c.get('{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}path') or c.get('path')))
            objs[e.get('id')] = o
        elif t == 'item':
            itens.append((e.get('objectid'), _matriz(e.get('transform'))))
    return unidade, objs, itens, cores


def _malha(verts, tris, M, esc):
    v = (np.c_[verts, np.ones(len(verts))] @ M.T)[:, :3] * esc
    return trimesh.Trimesh(vertices=v, faces=tris, process=False)


def _expandir(id_, M, objs, esc, nivel=0):
    """Gera (objeto_id, objeto_dict, matriz_final) das folhas com malha (resolve componentes)."""
    o = objs.get(id_)
    if o is None or nivel > 8: return
    if o['verts'] is not None: yield id_, o, M
    for cid, CM, _p in o['comps']: yield from _expandir(cid, M @ CM, objs, esc, nivel + 1)


def _config_prusa(z):
    """{object_id: [(firstid, lastid, nome, extruder)]} e lista de cores de filamento/extrusor."""
    vols = {}
    if 'Metadata/Slic3r_PE_model.config' in z.namelist():
        raiz = ET.fromstring(z.read('Metadata/Slic3r_PE_model.config'))
        for ob in raiz.iter('object'):
            lst = []
            for v in ob.iter('volume'):
                meta = {m.get('key'): m.get('value') for m in v.iter('metadata')}
                if meta.get('volume_type', 'ModelPart') != 'ModelPart': continue
                lst.append((int(v.get('firstid')), int(v.get('lastid')), meta.get('name', ''), int(meta.get('extruder') or 0) or None))
            vols[ob.get('id')] = (next((m.get('value') for m in ob.iter('metadata') if m.get('key') == 'name'), ''), int(ob.get('instances_count', 1) or 1), lst)
    cores = []
    if 'Metadata/Slic3r_PE.config' in z.namelist():
        txt = z.read('Metadata/Slic3r_PE.config').decode('utf-8', 'ignore'); ext, fil = [], []
        for l in txt.splitlines():
            if l.startswith('; extruder_colour ='): ext = [_hex(x) for x in l.split('=', 1)[1].strip().strip('"').split(';')]
            if l.startswith('; filament_colour ='): fil = [_hex(x) for x in l.split('=', 1)[1].strip().strip('"').split(';')]
        n = max(len(ext), len(fil)); cores = [(ext[i] if i < len(ext) and ext[i] else (fil[i] if i < len(fil) else None)) for i in range(n)]
    return vols, cores


def _config_bambu(z):
    """{object_id: {'nome','extruder', 'partes': {part_id: (nome, extruder)}}} e cores do projeto."""
    objs = {}
    if 'Metadata/model_settings.config' in z.namelist():
        raiz = ET.fromstring(z.read('Metadata/model_settings.config'))
        for ob in raiz.iter('object'):
            meta = {m.get('key'): m.get('value') for m in ob.findall('metadata')}
            partes = {}
            for p in ob.findall('part'):
                pm = {m.get('key'): m.get('value') for m in p.findall('metadata')}
                partes[p.get('id')] = (pm.get('name', ''), int(pm.get('extruder') or 0) or None)
            objs[ob.get('id')] = dict(nome=meta.get('name', ''), extruder=int(meta.get('extruder') or 0) or None, partes=partes)
    cores = []
    if 'Metadata/project_settings.config' in z.namelist():
        try: cores = [_hex(c) for c in json.loads(z.read('Metadata/project_settings.config').decode('utf-8', 'ignore')).get('filament_colour', [])]
        except Exception: pass
    return objs, cores


def ler(caminho):
    """-> (lista de Importado, resumo texto). Cada Importado.malha ja esta na posicao MONTADA (como no arquivo), em mm."""
    z = zipfile.ZipFile(caminho)
    nomes = z.namelist()
    principal = next((n for n in nomes if n.lower() == '3d/3dmodel.model'), None) or next((n for n in nomes if n.lower().endswith('.model')), None)
    if not principal: raise ValueError('Isso nao parece um 3MF (nao achei 3D/3dmodel.model).')
    unidade, objs, itens, cores_std = _ler_modelo(z.read(principal)); esc = _escala_unidade(unidade)
    # objetos que ficam em outros .model (Bambu/Orca: 3D/Objects/*.model)
    for n in nomes:
        if n.lower().endswith('.model') and n != principal:
            try:
                _u, o2, _i, c2 = _ler_modelo(z.read(n))
                for k, v in o2.items(): objs.setdefault(k, v)
                cores_std.update(c2)
            except Exception: pass
    vols_prusa, cores_ext = _config_prusa(z)
    obj_bambu, cores_bambu = _config_bambu(z)
    if cores_bambu: cores_ext = cores_bambu
    if not itens: itens = [(k, np.eye(4)) for k, o in objs.items() if o['verts'] is not None or o['comps']]
    partes = []
    for id_item, M in itens:
        for oid, o, MM in _expandir(id_item, M, objs, esc):
            V, T = o['verts'], o['tris']
            grupos = []          # (nome, cor_por_nome_ou_none, extruder, indices de triangulos, origem)
            if oid in vols_prusa and vols_prusa[oid][2]:
                for a, b, nm, ex in vols_prusa[oid][2]:
                    idx = np.arange(a, min(b, len(T) - 1) + 1)
                    if len(idx): grupos.append((nm, cor_do_nome(nm), ex, idx, 'PrusaSlicer'))
            elif id_item in obj_bambu or oid in obj_bambu:
                ob = obj_bambu.get(id_item) or obj_bambu.get(oid)
                if oid in ob['partes'] and len(ob['partes']) > 1: nm, ex = ob['partes'][oid]; grupos.append((nm or o['nome'], cor_do_nome(nm or o['nome']), ex or ob['extruder'], np.arange(len(T)), 'Bambu/Orca'))
                else: grupos.append((o['nome'] or ob['nome'], cor_do_nome(o['nome'] or ob['nome']), ob['extruder'], np.arange(len(T)), 'Bambu/Orca'))
            if not grupos:
                if o['tri_pid'] is not None:         # cor por triangulo (3MF padrao)
                    chave = [(o['tri_pid'][i], o['tri_p1'][i]) for i in range(len(T))]
                    for k in dict.fromkeys(chave):
                        idx = np.array([i for i, c in enumerate(chave) if c == k]); cor = cores_std.get((k[0], int(k[1]))) if k[1] is not None and k[0] is not None else None
                        grupos.append((o['nome'] + ('' if len(set(chave)) == 1 else ' (%s)' % _nome_cor(cor)), cor_do_nome(o['nome']), ('hex', cor), idx, '3MF padrao'))
                else:
                    cor = cores_std.get((o['pid'], int(o['pindex']))) if o['pid'] is not None and o['pindex'] is not None else None
                    grupos.append((o['nome'], cor_do_nome(o['nome']), ('hex', cor), np.arange(len(T)), '3MF padrao'))
            for nm, cor_nome, ex, idx, orig in grupos:
                cor = cor_nome
                if cor is None:
                    if isinstance(ex, tuple): cor = ex[1]
                    elif ex and ex - 1 < len(cores_ext): cor = cores_ext[ex - 1]
                m = _malha(V, T[idx], MM, esc)
                m.remove_unreferenced_vertices()
                if len(m.faces) < 4: continue
                partes.append(Importado(nm or o['nome'], cor, m, orig))
    # cor padrao cinza (#A0A0A0) so e 'sem cor': nao e uma escolha do usuario
    for p in partes:
        if p.cor == '#A0A0A0': p.cor = None
    if not partes: raise ValueError('Nao achei nenhuma peca dentro desse 3MF.')
    corcont = {}
    for p in partes: k = _nome_cor(p.cor) if p.cor else None; corcont[k] = corcont.get(k, 0) + 1
    resumo = '%d parte(s): ' % len(partes) + ', '.join('%s x%d' % (c or 'sem cor', n) for c, n in corcont.items())
    return partes, resumo


def exportar_partes(partes, pasta, nome_base):
    """Grava cada parte como STL (individual) e devolve [{nome, cor, stl, cor_nome}]. Nomes de arquivo seguros e unicos."""
    os.makedirs(pasta, exist_ok=True); out = []
    base = re.sub(r'[^\w\-]+', '_', os.path.splitext(os.path.basename(nome_base))[0])[:40]
    for i, p in enumerate(partes, 1):
        seg = re.sub(r'[^\w\-]+', '_', p.nome)[:40].strip('_') or 'parte'
        arq = os.path.join(pasta, '%s_%02d_%s.stl' % (base, i, seg))
        p.malha.export(arq)
        out.append(dict(nome=p.nome, cor=p.cor, cor_nome=_nome_cor(p.cor), stl=arq, origem=p.origem, triangulos=int(len(p.malha.faces))))
    return out
