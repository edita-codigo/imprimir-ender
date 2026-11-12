"""VALIDACAO COMPLETA da tela da aba Modelar (fora do programa): todas as 25 ferramentas pelo FORMULARIO (como o usuario usa), reabrir e salvar cada passo,
todas as ferramentas do desenho 2D com o mouse, solido valido + STL fechado depois de cada passo, sessao que volta ao reabrir, peca pesada de STL.
Rodar: python tests/modelar/t_validar.py [pasta] [--en]     (--en = programa em ingles, para ver se a traducao automatica nao quebra nada)"""
import sys, os, time, types, shutil, traceback, json
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, RAIZ)
import tkinter as tk
if '--en' in sys.argv:
    import i18n; i18n.carregar('en'); i18n.instalar()
import numpy as np, trimesh
import modelar as md, modelar_ui as mu, modelar_tema as T

args = [a for a in sys.argv[1:] if not a.startswith('--')]
FOTOS = args[0] if args else os.path.join(RAIZ, 'tests', 'modelar', 'saida')
TRAB = os.path.join(FOTOS, '_validar'); shutil.rmtree(TRAB, ignore_errors=True); os.makedirs(TRAB, exist_ok=True)
OK = FALHA = 0; FALHAS = []


def t(nome, fn):
    global OK, FALHA
    try:
        r = fn(); OK += 1; print('  ok  ', nome, '' if r is None else '-> %s' % (str(r)[:110],))
    except Exception as e:
        FALHA += 1; FALHAS.append(nome); print('FALHA ', nome, '->', type(e).__name__, str(e)[:300])
        if '-v' in sys.argv: traceback.print_exc()
        try: P._fechar_form()
        except Exception: pass


raiz = tk.Tk(); raiz.title('Modelar (validacao)'); raiz.configure(bg=T.BG); raiz.geometry('1180x690+20+10')
mesa_falsa = types.SimpleNamespace(pecas=[], sel=None, add_arquivo=lambda c, **k: mesa_falsa.pecas.append(c))
app = types.SimpleNamespace(pasta=TRAB, painel_mesa=mesa_falsa, aba=lambda n: None)
P = mu.PainelModelar(raiz, app); P.pack(fill='both', expand=True)


def rodar(seg=0.25):
    fim = time.time() + seg
    while time.time() < fim: raiz.update(); time.sleep(0.01)


t0 = time.time()
while not P._pronto and time.time() - t0 < 90: rodar(0.2)
assert P._pronto


def por(nome, valor):
    """Poe um valor num campo do formulario aberto (escolhas pelo nome interno, ex.: modo='subtrair')."""
    v = P.form['v'][nome]
    if isinstance(v, tk.BooleanVar): v.set(bool(valor)); return
    mapa = P.form['x'].get('_op_' + nome)
    if mapa:
        inv = {b: a for a, b in mapa.items()}; assert valor in inv, (nome, valor, list(inv)); v.set(inv[valor])
    else: v.set(str(valor))


def conferir(rotulo=''):
    """A peca atual tem de ser um solido valido e virar STL fechado."""
    e = P.proj.est; assert not e.vazio, 'peca vazia'
    if e.sol is not None: assert e.sol.is_valid, 'solido invalido ' + rotulo
    m = md.malha_final(e); assert m.is_watertight, 'STL aberto ' + rotulo; assert m.volume > 0
    return round(md.volume(e) / 1000, 2)


def usar(op, campos=None, antes=None, espera_previa=True):
    """Clica na ferramenta, preenche, confere a previa vermelha, aplica; devolve volume em cm3."""
    n = len(P.proj.passos); P.ferramenta(op); rodar(0.15)
    if op == 'assentar': assert len(P.proj.passos) == n + 1, P.l_status.cget('text'); return conferir(op)
    assert P.form and P.form['op'] == op, 'formulario nao abriu: ' + P.l_status.cget('text')
    if antes: antes()
    for k, v in (campos or {}).items(): por(k, v)
    rodar(0.45)
    if espera_previa: assert P.vista.fantasma is not None, 'sem previa vermelha (%s)' % P.l_erro.cget('text')
    P._aplicar(); rodar(0.15)
    assert P.form is None, 'nao aplicou: ' + P.l_erro.cget('text')
    assert len(P.proj.passos) == n + 1; return conferir(op)


def nova(nome):
    P.novo_projeto(nome); rodar(0.1); assert P.proj.est.vazio


def rep(tipo, **kw):
    def f():
        P.form['v']['_rep_tipo'].set({'linear': 'Em fila / grade', 'circular': 'Em círculo'}[tipo]); P._rep_campos()
        for k, v in kw.items(): P.form['x']['_rep_vars'][k].set(str(v))
    return f


def perfil(figs, chave='perfil'):
    def f(): P.form['x'][chave] = figs; P._resumo_perfil(chave)
    return f


# ======================= 1. todas as ferramentas pelo formulario =======================
def g_criar():
    nova('Formas'); out = {}
    out['caixa'] = usar('caixa', dict(largura=60, profundidade=40, altura=12, raio=4))
    out['cilindro'] = usar('cilindro', dict(diametro=16, altura=20, x=-18, y=0, z=12))
    out['tubo'] = usar('tubo', dict(diametro=18, parede=2, altura=14, x=18, y=0, z=12))
    out['cone'] = usar('cone', dict(diametro=14, diametro_topo=4, altura=12, x=-18, y=0, z=32))
    out['esfera'] = usar('esfera', dict(diametro=10, x=0, y=0, z=14))
    out['prisma'] = usar('prisma', dict(lados=6, diametro=12, altura=6, x=0, y=-12, z=12))
    out['toro'] = usar('toro', dict(diametro=14, diametro_fio=3, x=0, y=12, z=13))
    out['cunha'] = usar('cunha', dict(largura=14, profundidade=8, altura=8, topo=0, x=22, y=-14, z=12))
    out['texto relevo'] = usar('texto', dict(txt='OK', tam=6, prof=0.8, tipo='relevo', face='frente'))
    out['texto gravado'] = usar('texto', dict(txt='AB', tam=5, prof=0.6, tipo='gravado', face='baixo'))
    assert len(P.proj.passos) == 10; return out


def g_modos():
    nova('Modos'); a = usar('caixa', dict(largura=40, profundidade=40, altura=20)); b = usar('cilindro', dict(diametro=20, altura=30, z=-5, modo='subtrair')); assert b < a
    c = usar('esfera', dict(diametro=30, z=20, modo='somar')); assert c > b; d = usar('caixa', dict(largura=30, profundidade=30, altura=60, z=-10, modo='intersectar')); assert d < c
    e = usar('cilindro', dict(diametro=10, altura=10, modo='novo')); assert abs(e - 0.785) < 0.01, e; return a, b, c, d, e


def g_desenho():
    nova('Desenhos'); out = {}
    out['extrudar xy'] = usar('extrudar', dict(altura=6), perfil([dict(t='ret', l=50, a=30, r=4), dict(t='circ', d=8, furo=True), dict(t='rasgo', c=16, l=5, x=-16, furo=True)]))
    out['extrudar xz simetrico conico'] = usar('extrudar', dict(plano='xz', posicao=0, altura=8, simetrico=True, conicidade=5), perfil([dict(t='reg', n=6, d=14, x=16, y=14)]))
    out['extrudar yz tirar'] = usar('extrudar', dict(plano='yz', posicao=-30, altura=60, modo='subtrair'), perfil([dict(t='elipse', l=10, a=4, x=7, y=3)]))
    out['extrudar texto'] = usar('extrudar', dict(altura=1, posicao=6), perfil([dict(t='texto', txt='Z', tam=8, x=-16, y=8)]))
    nova('Revolucao'); out['revolucao'] = usar('revolucao', dict(angulo=360), perfil([dict(t='poli', pts=[[0, 0], [20, 0], [24, 30], [20, 30], [17, 3], [0, 3]])]))
    out['revolucao 180 eixo x'] = usar('revolucao', dict(angulo=180, eixo='x', x=40, modo='somar'), perfil([dict(t='caminho', ini=[0, 0], seg=[['l', 8, 0], ['a', 12, 6, 8, 12], ['l', 0, 12]])]))
    nova('Transicao'); P.ferramenta('loft'); rodar(0.4); assert P.form and len(P.form['x']['secoes']) == 2 and P.vista.fantasma is not None
    P._aplicar(); rodar(0.15); assert P.form is None, P.l_erro.cget('text') if P.form else ''; out['loft padrao'] = conferir()
    nova('Varrer'); out['varrer cantos'] = usar('varrer', dict(curva='cantos'), perfil([dict(t='circ', d=5)]))
    out['varrer arredondado'] = usar('varrer', dict(curva='arredondado', raio=6, modo='novo'), perfil([dict(t='ret', l=4, a=4)]))
    return out


def g_modificar():
    nova('Modificar'); out = {}
    usar('caixa', dict(largura=60, profundidade=40, altura=24))
    out['arredondar verticais'] = usar('arredondar', dict(raio=5, arestas='verticais'), espera_previa=False)
    out['casca cima'] = usar('casca', dict(espessura=2, abrir='cima'), espera_previa=False)
    out['chanfrar baixo'] = usar('chanfrar', dict(tamanho=0.8, arestas='baixo'), espera_previa=False)
    out['furo simples grade'] = usar('furo', dict(diametro=3, x=-20, y=-10, z='', direcao='-z'), rep('linear', n=3, dx=20, n2=2, dy2=20))
    out['furo rebaixado lado'] = usar('furo', dict(diametro=3, x='', y=0, z=12, direcao='-x', tipo='rebaixado', diametro2=6, profundidade2=1, profundidade=0))
    out['furo escareado circulo'] = usar('furo', dict(diametro=2.5, x=0, y='', z=12, direcao='+y', profundidade=3, tipo='escareado', diametro2=5))
    out['cortar'] = usar('cortar', dict(eixo='z', posicao=20, manter='menor'))
    out['arredondar ultimo'] = usar('arredondar', dict(raio=0.5, arestas='cima'), espera_previa=False)
    return out


def g_mover():
    nova('Mover'); out = {}; usar('caixa', dict(largura=30, profundidade=20, altura=10, x=20)); usar('cilindro', dict(diametro=8, altura=20, x=25))
    out['mover'] = usar('mover', dict(dx=5, dy=-3, dz=4), espera_previa=False); out['girar'] = usar('girar', dict(eixo='y', angulo=30), espera_previa=False)
    out['escalar'] = usar('escalar', dict(x=120, y=100, z=80), espera_previa=False); out['espelhar'] = usar('espelhar', dict(plano='yz', posicao=0, juntar=True), espera_previa=False)
    out['assentar'] = usar('assentar'); lim = P.proj.est.limites(); assert abs(lim[0][2]) < 1e-6 and abs(lim[0][0] + lim[1][0]) < 1e-6, lim; return out


def g_importar():
    P.ativar([p.nome for p in P.projs].index('Modificar')); stl = P.para_mesa(mostrar=False); stp = os.path.join(TRAB, 'm.step'); P.proj.exportar(stp)
    nova('Importar'); a = usar('importar', dict(caminho=stp), espera_previa=False); assert P.proj.est.tipo == 'cad'
    b = usar('importar', dict(caminho=stl, x=70, modo='somar'), espera_previa=False); assert P.proj.est.tipo == 'malha' and b > a
    c = usar('furo', dict(diametro=6, x=70, y=0)); d = usar('texto', dict(txt='M', tam=6, tipo='relevo', face='cima', u=-35))
    P.ferramenta('casca'); rodar(0.1); assert P.form is None and 'STL' in P.l_status.cget('text'); return a, b, c, d


def g_mais_menu():
    """Os botoes 'Mais' existem e as ferramentas escondidas tem botao/entrada."""
    todos = {op for _, ops, mais in mu.FAIXA for op in ops + mais}; falta = set(md.OPS) - todos - {'importar', 'codigo'}; assert not falta, falta; return len(todos)


# ======================= 2. reabrir e salvar cada passo (ida e volta do formulario) =======================
def g_ida_volta():
    out = []
    for i, p in enumerate(P.projs):
        if p.est.vazio: continue
        P.ativar(i); rodar(0.05); v0 = md.volume(P.proj.est)
        for k, ps in enumerate(list(P.proj.passos)):
            if ps['op'] == 'assentar': continue
            antes = json.dumps(P.proj.passos[k], sort_keys=True, default=str)
            P.editar_passo(k); rodar(0.05); assert P.form and P.form['indice'] == k, (p.nome, k)
            lido = P._ler_form(); P._aplicar(); rodar(0.05); assert P.form is None, '%s passo %d (%s): %s' % (p.nome, k + 1, ps['op'], P.l_erro.cget('text') if P.form else '')
            assert abs(md.volume(P.proj.est) - v0) < 1e-3 * max(v0, 1), '%s passo %d (%s) mudou a peca ao salvar sem mexer: %.3f -> %.3f' % (p.nome, k + 1, ps['op'], v0, md.volume(P.proj.est))
        out.append((p.nome, len(p.passos)))
    return out


# ======================= 3. desenho 2D com o mouse =======================
def arrasta(E, a, b):
    x0, y0 = E.tela(*a); x1, y1 = E.tela(*b)
    E.c.event_generate('<ButtonPress-1>', x=int(x0), y=int(y0)); E.c.event_generate('<B1-Motion>', x=int((x0 + x1) / 2), y=int((y0 + y1) / 2)); E.c.event_generate('<B1-Motion>', x=int(x1), y=int(y1)); E.c.event_generate('<ButtonRelease-1>', x=int(x1), y=int(y1)); rodar(0.08)


def clica(E, a, duplo=False):
    x, y = E.tela(*a); E.c.event_generate('<ButtonPress-1>', x=int(x), y=int(y)); E.c.event_generate('<ButtonRelease-1>', x=int(x), y=int(y))
    rodar(0.08)


def g_esboco():
    nova('Esboco'); P.ferramenta('extrudar'); rodar(0.2); P._desenhar('perfil'); rodar(0.4); E = P.editor; assert E is not None; out = {}
    E.zoom = 5.0; E.ox = E.c.winfo_width() / 2; E.oy = E.c.winfo_height() / 2; E.desenhar()
    E.ferramenta('ret'); arrasta(E, (-40, -20), (-10, 0)); f = E.figs[-1]; assert f['t'] == 'ret' and (f['l'], f['a'], f['x'], f['y']) == (30, 20, -25, -10), f; out['ret'] = (f['l'], f['a'])
    E.ferramenta('circ'); arrasta(E, (20, 20), (28, 20)); f = E.figs[-1]; assert f['t'] == 'circ' and f['d'] == 16 and (f['x'], f['y']) == (20, 20), f; out['circ'] = f['d']
    E.ferramenta('elipse'); arrasta(E, (0, -30), (20, -20)); f = E.figs[-1]; assert f['t'] == 'elipse' and (f['l'], f['a']) == (20, 10), f; out['elipse'] = (f['l'], f['a'])
    E.ferramenta('reg'); arrasta(E, (-20, 25), (-10, 25)); f = E.figs[-1]; assert f['t'] == 'reg' and f['d'] == 20 and f['n'] == 6, f; out['reg'] = f['d']
    E.ferramenta('rasgo'); arrasta(E, (30, -10), (50, -10)); f = E.figs[-1]; assert f['t'] == 'rasgo' and abs(f['c'] - 27) < 0.01 and f['g'] == 0, f; out['rasgo'] = f['c']
    E.ferramenta('poli'); [clica(E, p) for p in ((40, 0), (55, 0), (55, 12))]; clica(E, (42, 12)); E._duplo(None); rodar(0.05); f = E.figs[-1]; assert f['t'] == 'poli' and len(f['pts']) == 4, f; out['poli'] = len(f['pts'])
    n = len(E.figs); assert n == 6, n
    E.ferramenta('sel'); arrasta(E, (-25, -10), (-20, -5)); assert E.sel == 0 and (E.figs[0]['x'], E.figs[0]['y']) == (-20, -5), (E.sel, E.figs[0]); out['mover'] = 'ok'
    E.vars_campo['l'].set('32'); E.vars_campo['r'].set('3'); rodar(0.05); assert E.figs[0]['l'] == 32 and E.figs[0]['r'] == 3; out['medida digitada'] = 'ok'
    clica(E, (20, 20)); assert E.sel == 1; E._furo(True); assert E.figs[1].get('furo')
    clica(E, (50, 4)); assert E.sel == 5; arrasta(E, (55, 12), (60, 15)); assert E.figs[5]['pts'][2] == [60, 15], E.figs[5]['pts']; out['arrastar ponto'] = 'ok'
    E.apagar(); assert len(E.figs) == 5; E.desfazer(); assert len(E.figs) == 6; out['apagar/desfazer'] = 'ok'
    E.figs[1].pop('furo'); E.figs = [E.figs[0], dict(t='circ', d=6, x=-20, y=-5, furo=True)] + E.figs[2:]            # desenho final: retangulo com furo + as outras figuras
    E.concluir(); rodar(0.3); assert P.editor is None and len(P.form['x']['perfil']) == 6
    por('altura', 4); rodar(0.5); assert P.vista.fantasma is not None, P.l_erro.cget('text'); P._aplicar(); rodar(0.1); assert P.form is None, P.l_erro.cget('text') if P.form else ''
    out['extrudado cm3'] = conferir(); return out


def g_esboco_cancelar():
    P.ferramenta('extrudar'); rodar(0.2); P._desenhar('perfil'); rodar(0.3); E = P.editor; E.ferramenta('ret'); arrasta(E, (0, 0), (10, 10)); E.cancelar(); rodar(0.2)
    assert P.editor is None and P.form['x']['perfil'] == [] and P.f_vista.winfo_ismapped(); P._aplicar(); rodar(0.1)
    assert P.form is not None and 'vazio' in P.l_erro.cget('text'), P.l_erro.cget('text'); P._fechar_form(); return 'cancelar nao muda o desenho; aplicar sem desenho avisa'


# ======================= 4. clique na peca, vistas, selecao multipla =======================
def g_clique():
    P.ativar([p.nome for p in P.projs].index('Modos')); P.proj.limpar(); P._atualizar(True); usar('caixa', dict(largura=40, profundidade=30, altura=20)); out = {}
    for vs in ('3d', 'frente', 'direita', 'cima', 'tras', 'esquerda', 'baixo'):
        P.vista.vista(vs); rodar(0.35); W, H = P.vista.winfo_width(), P.vista.winfo_height(); h, info = P.vista.pick(W // 2, H // 2)
        assert h and h[0] in ('f', 'a') and info is not None, (vs, h); out[vs] = h
    assert out['cima'][0] == 'f' and out['frente'][0] == 'f' and out['cima'][1] != out['frente'][1] != out['direita'][1]
    P.vista.vista('3d'); rodar(0.4); b = P.vista._buf; A2, B2, vis = b['seg']; c = P.vista.cena; ids = [a['id'] for a in c.dv['info_arestas'] if abs(a['meio'][2] - 20) < 0.01 and vis[c.SE == a['id']].all()][:3]; assert len(ids) >= 2
    for n, i in enumerate(ids):
        k = np.nonzero(c.SE == i)[0]; x, y = ((A2[k[len(k) // 2]] + B2[k[len(k) // 2]]) / 2).astype(int)
        P.vista.event_generate('<ButtonPress-1>', x=x, y=y); P.vista.event_generate('<ButtonRelease-1>', x=x, y=y, state=0x0001 if n else 0); rodar(0.25)
    assert P.vista.sel_arestas == set(ids), (P.vista.sel_arestas, ids); v0 = md.volume(P.proj.est)
    usar('chanfrar', dict(tamanho=2), espera_previa=False); assert len(P.proj.passos[-1]['arestas'][0]['perto']) == len(ids); out['chanfro em %d arestas clicadas (Shift)' % len(ids)] = round(v0 - md.volume(P.proj.est), 1)
    return out


# ======================= 5. sessao, arquivo pesado, limites =======================
def g_sessao():
    global P
    P._salvar_tudo(); antes = [(p.nome, len(p.passos), round(md.volume(p.est), 2)) for p in P.projs if p.passos]; at = P.proj.nome
    P.destroy(); P = mu.PainelModelar(raiz, app); P.pack(fill='both', expand=True); t1 = time.time()
    while (not P._pronto or P._pend_sessao is not None) and time.time() - t1 < 60: rodar(0.2)
    depois = [(p.nome, len(p.passos), round(md.volume(p.est), 2)) for p in P.projs]; assert depois == antes, [(a, b) for a, b in zip(antes, depois) if a != b] + [len(antes), len(depois)]; assert P.proj.nome == at; return '%d pecas voltaram iguais' % len(depois)


def g_pesado():
    stl = os.path.join(RAIZ, '..', '..', 'lampada_batman', 'lampada_batman_agy.stl')
    cand = [stl] + [os.path.join(RAIZ, 'importados', f) for f in (os.listdir(os.path.join(RAIZ, 'importados')) if os.path.isdir(os.path.join(RAIZ, 'importados')) else []) if f.lower().endswith('.stl')]
    cand = sorted([c for c in cand if os.path.isfile(c)], key=os.path.getsize, reverse=True)
    if not cand: return 'sem STL grande no PC para testar'
    c = cand[0]; t1 = time.time(); p = P.abrir_arquivo(c); rodar(0.3); ta = time.time() - t1; n = len(p.est.malha.faces)
    t1 = time.time(); P.vista._pintar(900, 600, P.vista._cam(900, 600), 1.0); tq = time.time() - t1
    t1 = time.time(); usar('caixa', dict(largura=20, profundidade=20, altura=10, x=0, y=0, z=0)); tb = time.time() - t1
    assert tq < 1.5, 'quadro lento: %.2fs' % tq; return '%s: %d triangulos, abrir %.1fs, quadro %.2fs, somar caixa %.1fs' % (os.path.basename(c), n, ta, tq, tb)


def g_limites():
    nova('Limites'); out = []
    for op in ('arredondar', 'furo', 'cortar', 'texto', 'mover', 'casca'):
        P.ferramenta(op); rodar(0.05); assert P.form is None and 'precisa de uma peça' in P.l_status.cget('text'), op
    out.append('ferramentas que precisam de peca avisam')
    P.ferramenta('caixa'); rodar(0.1); por('largura', 'abc'); P._aplicar(); rodar(0.05); assert P.form is not None and P.l_erro.cget('text'), 'aceitou texto na medida'; out.append('medida errada: ' + P.l_erro.cget('text')[:40])
    por('largura', '-5'); P._aplicar(); rodar(0.05); assert P.form is not None; por('largura', '2*10 + 5'); P._aplicar(); rodar(0.1); assert P.form is None and P.proj.est.limites()[1][0] == 12.5; out.append('conta na medida')
    P.desfazer(); rodar(0.05); assert P.proj.est.vazio; P.refazer(); rodar(0.05); assert not P.proj.est.vazio
    for _ in range(3): P.desfazer()
    assert 'desfazer' in P.l_status.cget('text').lower(); out.append('desfazer alem do inicio avisa')
    n = len(P.projs); P.fechar_projeto(P.at, perguntar=False); assert len(P.projs) == n - 1; return out


for nome, fn in (('CRIAR: 9 formas + texto relevo/gravado', g_criar), ('MODOS: somar / tirar / cruzar / novo', g_modos), ('DESENHO: extrudar (3 planos), revolucao, transicao, varrer', g_desenho),
                 ('MODIFICAR: arredondar, casca, chanfrar, 3 tipos de furo, repetir, cortar', g_modificar), ('MOVER: mover, girar, escalar, espelhar, assentar', g_mover),
                 ('IMPORTAR: STEP (solido) e STL (malha) + editar a malha', g_importar), ('todas as ferramentas tem botao na faixa', g_mais_menu),
                 ('reabrir e salvar TODOS os passos sem mexer nao muda a peca', g_ida_volta), ('desenho 2D: 6 ferramentas com o mouse, mover, medida, ponto, apagar, desfazer', g_esboco),
                 ('desenho 2D: cancelar e aplicar sem desenho', g_esboco_cancelar), ('clique na peca nas 7 vistas + varias arestas com Shift', g_clique),
                 ('fechar e reabrir: as pecas voltam iguais', g_sessao), ('STL pesado', g_pesado), ('limites e erros de digitacao', g_limites)):
    t(nome, fn)
print('\n%d ok, %d falhas%s' % (OK, FALHA, (' -> ' + '; '.join(FALHAS)) if FALHAS else '')); raiz.destroy(); sys.exit(1 if FALHA else 0)
