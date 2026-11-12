"""Teste do motor da aba Modelar (sem tela). Rodar: python tests/modelar/t_motor.py   (-v mostra o erro completo)"""
import sys, os, time, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
import modelar as md

OK = FALHA = 0
PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saida')
PI = 3.14159265


def t(nome, fn):
    global OK, FALHA
    try:
        r = fn(); OK += 1; print('  ok  ', nome, '' if r is None else '-> %s' % (r,))
    except Exception as e:
        FALHA += 1; print('FALHA ', nome, '->', type(e).__name__, str(e)[:300])
        if '-v' in sys.argv: traceback.print_exc()


def erro(nome, fn, trecho=''):
    global OK, FALHA
    try:
        fn(); FALHA += 1; print('FALHA ', nome, '-> devia dar erro e nao deu')
    except md.ErroModelo as e:
        if trecho and trecho not in str(e): FALHA += 1; print('FALHA ', nome, '-> erro diferente:', str(e)[:200])
        else: OK += 1; print('  ok  ', nome, '(erro esperado: %s)' % str(e)[:70])
    except Exception as e:
        FALHA += 1; print('FALHA ', nome, '-> erro cru', type(e).__name__, str(e)[:200])
        if '-v' in sys.argv: traceback.print_exc()


def vol(p): return round(md.volume(p.est), 1)


def tam(p):
    l = p.est.limites(); return [round(float(x), 2) for x in (l[1] - l[0])]


def base():
    p = md.Projeto(); p.adicionar(dict(op='caixa', largura=40, profundidade=30, altura=20)); return p


t0 = time.time(); md.motor(); print('motor em %.1fs' % (time.time() - t0))
P = md.Projeto


# ---------------- numeros ----------------
def f_conta(): assert md.num('largura/2 + folga', {'largura': 40, 'folga': 0.2}) == 20.2
def f_virgula(): assert md.num('12,5') == 12.5
t('conta com variaveis', f_conta); t('virgula decimal', f_virgula)
erro('conta perigosa', lambda: md.num('__import__("os")'))
erro('variavel inexistente', lambda: md.num('abc*2'), 'nao existe')


# ---------------- formas ----------------
def f_caixa():
    p = P(); p.adicionar(dict(op='caixa', largura=40, profundidade=30, altura=10)); assert vol(p) == 12000.0, vol(p); assert tam(p) == [40, 30, 10]
    assert abs(p.est.limites()[0][2]) < 1e-6; return vol(p)


def f_caixa_raio():
    p = P(); p.adicionar(dict(op='caixa', largura=40, profundidade=30, altura=10, raio=5)); assert 11700 < vol(p) < 11900, vol(p); return vol(p)


t('caixa', f_caixa); t('caixa de cantos redondos', f_caixa_raio)
for op, extra, esperado in (('cilindro', dict(diametro=20, altura=10), 3141.6), ('tubo', dict(diametro=20, parede=2, altura=10), 1131.0), ('esfera', dict(diametro=20), 4188.8),
                            ('cone', dict(diametro=20, diametro_topo=0, altura=30), 3141.6), ('toro', dict(diametro=30, diametro_fio=6), 2664.8), ('prisma', dict(lados=6, diametro=20, altura=10), 2598.1),
                            ('cunha', dict(largura=30, profundidade=20, altura=15, topo=0), 4500.0), ('cunha', dict(largura=30, profundidade=20, altura=15, topo=10), 6000.0)):
    def f(op=op, extra=extra, esperado=esperado):
        p = P(); p.adicionar(dict(op=op, **extra)); v = vol(p); assert abs(v - esperado) / esperado < 0.01, (v, esperado); return v
    t(op + (' topo %s' % extra['topo'] if 'topo' in extra else ''), f)


def f_eixos():
    out = []
    for e in 'xyz':
        p = P(); p.adicionar(dict(op='cilindro', diametro=10, altura=40, eixo=e, x=1, y=2, z=3)); l = p.est.limites(); i = 'xyz'.index(e)
        assert abs((l[1] - l[0])[i] - 40) < 1e-6 and abs(l[0][i] - [1, 2, 3][i]) < 1e-6, (e, l); out.append(e)
    return out


t('cilindro nos 3 eixos (comeca no ponto e vai no +)', f_eixos)


# ---------------- somar / subtrair ----------------
def f_bool():
    p = P(); p.adicionar(dict(op='caixa', largura=40, profundidade=30, altura=10)); p.adicionar(dict(op='cilindro', diametro=10, altura=30, z=-5, modo='subtrair'))
    assert abs(vol(p) - (12000 - 785.4)) < 1, vol(p)
    p.adicionar(dict(op='esfera', diametro=20, z=10, modo='somar')); v1 = vol(p); assert v1 > 11300
    p.adicionar(dict(op='caixa', largura=20, profundidade=20, altura=40, modo='intersectar')); assert vol(p) < v1; return vol(p)


def f_apaga_tudo():
    p = P(); p.adicionar(dict(op='caixa', largura=10, profundidade=10, altura=10)); p.adicionar(dict(op='caixa', largura=50, profundidade=50, altura=50, z=-5, modo='subtrair'))


t('somar / subtrair / intersectar', f_bool)
erro('subtrair sem peca', lambda: P().adicionar(dict(op='cilindro', modo='subtrair')), 'ainda nao ha peca')
erro('subtrair a peca inteira', f_apaga_tudo, 'vazio')
erro('medida zero', lambda: P().adicionar(dict(op='caixa', largura=0)), 'maior que zero')
erro('parametro desconhecido', lambda: P().adicionar(dict(op='caixa', largurra=3)), 'desconhecido')


# ---------------- desenho ----------------
def f_ext():
    p = P(); p.adicionar(dict(op='extrudar', perfil=[dict(t='ret', l=40, a=20, r=3), dict(t='circ', d=8, furo=True)], altura=10)); v = vol(p)
    assert abs(v - (40 * 20 - (4 - PI) * 9 - PI * 16) * 10) < 5, v; return v


def f_ext_planos():
    out = {}
    for pl, i in (('xy', 2), ('xz', 1), ('yz', 0)):
        p = P(); p.adicionar(dict(op='extrudar', perfil=[dict(t='ret', l=30, a=10, x=5, y=7)], plano=pl, posicao=4, altura=6)); l = p.est.limites()
        assert abs(l[0][i] - 4) < 1e-6 and abs(l[1][i] - 10) < 1e-6, (pl, l)       # vai de 'posicao' ate posicao+altura, no sentido +
        u, v = {'xy': (0, 1), 'xz': (0, 2), 'yz': (1, 2)}[pl]
        assert abs((l[0][u] + l[1][u]) / 2 - 5) < 1e-6 and abs((l[0][v] + l[1][v]) / 2 - 7) < 1e-6, (pl, l); out[pl] = 'ok'
    return out


def f_ext_sim():
    p = P(); p.adicionar(dict(op='extrudar', perfil=[dict(t='circ', d=10)], altura=10, simetrico=True)); l = p.est.limites(); assert abs(l[0][2] + 5) < 1e-6 and abs(l[1][2] - 5) < 1e-6, l
    q = P(); q.adicionar(dict(op='extrudar', perfil=[dict(t='ret', l=20, a=20)], altura=10, conicidade=10)); assert vol(q) < 4000; return vol(q)


def f_figs():
    out = {}
    for fig in (dict(t='elipse', l=20, a=10), dict(t='reg', n=5, d=20), dict(t='rasgo', c=30, l=8), dict(t='poli', pts=[[0, 0], [20, 0], [10, 15]]),
                dict(t='caminho', ini=[0, 0], seg=[['l', 20, 0], ['a', 25, 5, 20, 10], ['l', 0, 10]]), dict(t='texto', txt='Oi', tam=12), dict(t='ret', l=10, a=10, g=45, x=3)):
        p = P(); p.adicionar(dict(op='extrudar', perfil=[fig], altura=2)); out[fig['t']] = vol(p)
    assert abs(out['poli'] - 300) < 0.5, out; return out


def f_rev():
    p = P(); p.adicionar(dict(op='revolucao', perfil=[dict(t='ret', l=5, a=10, x=12.5, y=5)], eixo='z')); v = vol(p); assert abs(v - PI * (15 ** 2 - 10 ** 2) * 10) < 5, v
    l = p.est.limites(); assert abs(l[0][2]) < 1e-6 and abs(l[1][2] - 10) < 1e-6, l
    for e in 'xy':
        q = P(); q.adicionar(dict(op='revolucao', perfil=[dict(t='ret', l=5, a=10, x=12.5, y=5)], eixo=e)); lq = q.est.limites(); i = 'xyz'.index(e)
        assert abs((lq[1] - lq[0])[i] - 10) < 1e-6 and abs(lq[0][i]) < 1e-6, (e, lq)
    h = P(); h.adicionar(dict(op='revolucao', perfil=[dict(t='ret', l=5, a=10, x=12.5, y=5)], angulo=180)); assert abs(vol(h) - v / 2) < 3; return v


def f_loft():
    p = P(); p.adicionar(dict(op='loft', secoes=[dict(z=0, perfil=[dict(t='ret', l=30, a=30)]), dict(z=30, perfil=[dict(t='circ', d=15)])])); assert abs(p.est.limites()[1][2] - 30) < 1e-6; return vol(p)


def f_varrer():
    out = []
    for cv in ('cantos', 'arredondado', 'suave'):
        p = P(); p.adicionar(dict(op='varrer', perfil=[dict(t='circ', d=4)], caminho=[[0, 0, 0], [0, 0, 20], [20, 0, 30], [40, 0, 30]], curva=cv, raio=6)); out.append((cv, vol(p)))
    return out


t('extrudar no chao, com furo', f_ext); t('extrudar: planos xy/xz/yz e sentido', f_ext_planos); t('extrudar simetrico e conico', f_ext_sim); t('todas as figuras do desenho', f_figs)
erro('poligono cruzado', lambda: P().adicionar(dict(op='extrudar', perfil=[dict(t='poli', pts=[[0, 0], [10, 10], [10, 0], [0, 10]])], altura=2)), 'cruza')
erro('desenho vazio', lambda: P().adicionar(dict(op='extrudar', perfil=[], altura=2)), 'vazio')
t('revolucao (3 eixos, meia volta)', f_rev)
erro('revolucao cruzando o eixo', lambda: P().adicionar(dict(op='revolucao', perfil=[dict(t='ret', l=10, a=10)])), 'lado negativo')
t('transicao quadrado -> circulo', f_loft); t('varrer (cantos, arredondado, suave)', f_varrer)


# ---------------- modificar ----------------
def f_arr():
    out = {}
    for sel in ('todas', 'cima', 'baixo', 'verticais', 'horizontais', 'frente', 'direita'):
        p = base(); p.adicionar(dict(op='arredondar', raio=2, arestas=sel)); out[sel] = vol(p); assert vol(p) < 24000
    assert out['verticais'] > out['todas'] and abs(out['cima'] - out['baixo']) < 0.5, out; return out


def f_arr_ids():
    p = base(); e = p.estado(); ar = [a for a in e['arestas'] if a['tipo'] == 'reta' and abs(a['meio'][2] - 20) < 0.01]; assert len(ar) == 4, len(ar)
    p.adicionar(dict(op='arredondar', raio=3, arestas=[ar[0]['id'], ar[1]['id']])); assert isinstance(p.passos[-1]['arestas'][0], dict), p.passos[-1]     # numero virou ponto
    v1 = vol(p); assert v1 < 24000
    p.editar(0, dict(altura=20.5)); assert vol(p) > v1        # mexeu pouco: o ponto ainda acha a mesma aresta
    return v1, vol(p)


def f_arr_longe():
    p = base(); e = p.estado(); ar = [a for a in e['arestas'] if abs(a['meio'][2] - 20) < 0.01]
    p.adicionar(dict(op='arredondar', raio=3, arestas=[ar[0]['id']])); p.editar(0, dict(altura=60))


def f_arr_nome():
    p = base(); p.adicionar(dict(op='arredondar', raio=3, arestas='verticais')); p.editar(0, dict(largura=60)); return vol(p)


def f_ultimo():
    p = base(); p.adicionar(dict(op='cilindro', diametro=10, altura=30, z=-5, modo='subtrair')); n0 = vol(p); p.adicionar(dict(op='chanfrar', tamanho=1, arestas='ultimo'))
    assert 0 < n0 - vol(p) < 80, (n0, vol(p)); return round(n0 - vol(p), 1)


def f_casca():
    p = base(); p.adicionar(dict(op='casca', espessura=2)); v = vol(p); assert abs(v - (24000 - 36 * 26 * 18)) < 1, v
    q = base(); q.adicionar(dict(op='casca', espessura=2, abrir='nenhuma')); assert abs(vol(q) - (24000 - 36 * 26 * 16)) < 1, vol(q)
    r = base(); r.adicionar(dict(op='casca', espessura=2, abrir=['cima', 'frente'])); assert vol(r) < v; return v, vol(q), vol(r)


def f_furo():
    p = base(); p.adicionar(dict(op='furo', diametro=6)); assert abs(24000 - vol(p) - PI * 9 * 20) < 1, vol(p)                       # atravessa, z vazio
    q = base(); q.adicionar(dict(op='furo', diametro=6, profundidade=5)); assert abs(24000 - vol(q) - PI * 9 * 5) < 1, vol(q)        # cego, a partir de cima
    r = base(); r.adicionar(dict(op='furo', diametro=4, tipo='rebaixado', diametro2=8, profundidade2=3)); assert abs(24000 - vol(r) - (PI * 4 * 20 + PI * (16 - 4) * 3)) < 1, vol(r)
    s = base(); s.adicionar(dict(op='furo', diametro=4, tipo='escareado', diametro2=8)); assert vol(s) < 24000 - PI * 4 * 20
    u = base(); u.adicionar(dict(op='furo', diametro=5, direcao='+y', profundidade=4, x=0, y='', z=10)); assert abs(24000 - vol(u) - PI * 6.25 * 4) < 1, vol(u)   # entra pela frente
    return 'ok'


def f_rep():
    p = base(); p.adicionar(dict(op='furo', diametro=3, x=-15, y=-10, repetir=dict(tipo='linear', n=4, dx=10, n2=3, dy2=10))); assert abs(24000 - vol(p) - 12 * PI * 2.25 * 20) < 2, vol(p)
    q = P(); q.adicionar(dict(op='cilindro', diametro=60, altura=5)); q.adicionar(dict(op='furo', diametro=4, x=22, repetir=dict(tipo='circular', n=6)))
    assert abs(PI * 900 * 5 - vol(q) - 6 * PI * 4 * 5) < 2, vol(q); return vol(p), vol(q)


def f_cortar():
    p = base(); p.adicionar(dict(op='cortar', eixo='z', posicao=5, manter='menor')); assert abs(vol(p) - 6000) < 1 and tam(p)[2] == 5
    q = base(); q.adicionar(dict(op='cortar', eixo='x', posicao=10, manter='maior')); assert tam(q)[0] == 10, tam(q); return 'ok'


def f_texto():
    out = {}
    for face in ('cima', 'frente', 'tras', 'esquerda', 'direita', 'baixo'):
        p = base(); p.adicionar(dict(op='texto', txt='AB', tam=8, prof=1, tipo='relevo', face=face)); assert vol(p) > 24000, face
        q = base(); q.adicionar(dict(op='texto', txt='AB', tam=8, prof=1, tipo='gravado', face=face)); assert vol(q) < 24000, face
        out[face] = (round(vol(p) - 24000, 1), round(24000 - vol(q), 1)); assert abs(out[face][0] - out[face][1]) < 1.5, out
    return out


def f_mover():
    p = base(); p.adicionar(dict(op='mover', dx=5, dz=3)); l = p.est.limites(); assert abs(l[0][2] - 3) < 1e-6 and abs(l[0][0] + 15) < 1e-6
    p.adicionar(dict(op='girar', eixo='z', angulo=90)); assert tam(p) == [30, 40, 20], tam(p)
    p.adicionar(dict(op='escalar', x=50, y=100, z=200)); assert tam(p) == [15, 40, 40], tam(p)
    p.adicionar(dict(op='assentar')); l = p.est.limites(); assert abs(l[0][2]) < 1e-6 and abs(l[0][0] + l[1][0]) < 1e-6
    q = P(); q.adicionar(dict(op='caixa', largura=10, profundidade=10, altura=10, x=10)); q.adicionar(dict(op='espelhar', plano='yz', posicao=0)); assert tam(q)[0] == 30 and abs(vol(q) - 2000) < 1, (tam(q), vol(q)); return 'ok'


t('arredondar por nome', f_arr); t('arredondar por numero (vira ponto) + mexer pouco na medida', f_arr_ids)
erro('arredondar por numero + mexer muito (erro claro)', f_arr_longe, 'nao achei aresta')
t('arredondar por nome sobrevive a mudar medida', f_arr_nome); t("chanfrar 'ultimo' (so as bordas do furo)", f_ultimo)
erro('raio grande demais', lambda: base().adicionar(dict(op='arredondar', raio=50)), 'nao coube')
t('casca (aberta em cima, fechada, 2 faces)', f_casca); t('furo (passante, cego, rebaixado, escareado, pela frente)', f_furo); t('repetir (grade 4x3 e 6 em circulo)', f_rep); t('cortar', f_cortar)
erro('cortar fora da peca', lambda: base().adicionar(dict(op='cortar', eixo='z', posicao=50)), 'fora da peca')
t('texto relevo/gravado nas 6 faces', f_texto); t('mover, girar, escalar, assentar, espelhar', f_mover)


# ---------------- receita ----------------
def f_receita():
    p = P('Suporte'); p.definir_var('larg', 40); p.definir_var('folga', 0.2)
    p.adicionar(dict(op='caixa', largura='larg', profundidade=30, altura=10)); p.adicionar(dict(op='furo', diametro='5 + folga*2'))
    v1 = vol(p); p.definir_var('larg', 60); assert vol(p) > v1 and tam(p)[0] == 60
    p.editar(0, dict(altura=20)); assert tam(p)[2] == 20
    p.desfazer(); assert tam(p)[2] == 10; p.refazer(); assert tam(p)[2] == 20
    p.alternar(1); assert abs(vol(p) - 60 * 30 * 20) < 1; p.alternar(1)
    p.remover(1); assert len(p.passos) == 1
    c = os.path.join(PASTA, 'teste.modelo.json'); p.salvar(c); q = P.abrir(c); assert vol(q) == vol(p) and q.vars['larg'] == 60; return vol(q)


def f_depende():
    p = base(); p.adicionar(dict(op='furo', diametro=4)); p.remover(0)


def f_estado():
    p = base(); e = p.estado(); assert e['n_faces'] == 6 and e['n_arestas'] == 12 and e['tamanho'] == [40, 30, 20] and e['volume_cm3'] == 24.0, e
    assert e['passos'][0]['descricao'].startswith('Caixa 40'), e['passos']; return e['passos'][0]['descricao']


def f_dados():
    import trimesh
    p = base(); p.adicionar(dict(op='furo', diametro=8)); d = p.dados()
    m = trimesh.Trimesh(d['V'], d['F'], process=True); assert m.volume > 0, 'normais invertidas'; assert abs(m.volume - vol(p)) < 20, (m.volume, vol(p))
    assert len(d['arestas']) == len(d['info_arestas']) == len(d['adj']) and all(len(a) in (1, 2) for a in d['adj']), [len(a) for a in d['adj']]
    assert sum(1 for a in d['info_arestas'] if a.get('costura')) == 1          # so a costura do cilindro do furo
    return len(d['F']), len(d['arestas'])


def f_exp():
    import trimesh
    p = base(); p.adicionar(dict(op='arredondar', raio=2)); out = []
    for ext in ('stl', 'step', '3mf'):
        c = p.exportar(os.path.join(PASTA, 't.' + ext)); assert os.path.getsize(c) > 500; out.append(ext)
    m = trimesh.load(os.path.join(PASTA, 't.stl')); assert m.is_watertight and abs(m.volume - vol(p)) < 5, (m.is_watertight, m.volume, vol(p)); return out


t('variaveis, editar, desfazer/refazer, desligar, remover, salvar/abrir', f_receita)
erro('apagar passo de que outro depende', f_depende, 'depende')
t('estado (faces, arestas, descricao)', f_estado); t('dados para a tela (normais para fora, 2 faces por aresta)', f_dados); t('exportar STL (fechado), STEP, 3MF', f_exp)


# ---------------- malha (peca vinda de STL) ----------------
def f_malha():
    p = P(); p.adicionar(dict(op='importar', caminho=os.path.join(PASTA, 't.stl'))); assert p.est.tipo == 'malha'; v0 = vol(p)
    p.adicionar(dict(op='furo', diametro=6)); assert vol(p) < v0
    p.adicionar(dict(op='texto', txt='A', tam=6, tipo='gravado', u=10)); p.adicionar(dict(op='caixa', largura=10, profundidade=10, altura=30, x=-12))
    p.adicionar(dict(op='cortar', eixo='z', posicao=15)); p.adicionar(dict(op='girar', eixo='z', angulo=45)); p.adicionar(dict(op='espelhar', plano='yz', posicao=30))
    d = p.dados(); assert d['tipo'] == 'malha' and len(d['F']) > 100
    assert md.malha_final(p.est).is_watertight; return round(v0), vol(p)


def f_malha_arr():
    p = P(); p.adicionar(dict(op='importar', caminho=os.path.join(PASTA, 't.stl'))); p.adicionar(dict(op='arredondar', raio=1))


def f_step():
    p = P(); p.adicionar(dict(op='importar', caminho=os.path.join(PASTA, 't.step'))); assert p.est.tipo == 'cad'
    p.adicionar(dict(op='casca', espessura=1.5)); return vol(p)


t('modo malha: importar STL, furo, somar, texto, cortar, girar, espelhar', f_malha)
erro('arredondar em malha', f_malha_arr, 'veio de um STL')
t('importar STEP continua CAD (casca funciona)', f_step)


# ---------------- codigo / previa / ajuda ----------------
def f_cod():
    p = P(); p.permitir_codigo = True; p.adicionar(dict(op='codigo', codigo='resultado = Box(10,10,10) + Pos(0,0,10)*Sphere(4)')); return vol(p)


def f_previa():
    p = base(); m = md.malha_previa('furo', dict(md.padrao('furo'), diametro=5), {}, p.est); assert m is not None and len(m.faces) > 10
    assert md.malha_previa('arredondar', md.padrao('arredondar'), {}, p.est) is None; return len(m.faces)


erro('codigo desligado por padrao', lambda: P().adicionar(dict(op='codigo', codigo='resultado = Box(1,1,1)')), 'desligado')
t('codigo livre (ligado)', f_cod); t('previa da ferramenta', f_previa)
t('ajuda', lambda: (len(md.ajuda()['ferramentas']), md.ajuda('furo')['parametros'][0]['nome']))
print('\n%d ok, %d falhas, %.1fs' % (OK, FALHA, time.time() - t0)); sys.exit(1 if FALHA else 0)
