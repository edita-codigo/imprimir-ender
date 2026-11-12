"""Teste da TELA da aba Modelar fora do programa: abre a janela, usa as ferramentas como o usuario usaria (formulario, desenho, clique na peca),
confere o resultado e tira fotos da janela. Rodar: python tests/modelar/t_tela.py [pasta_das_fotos]"""
import sys, os, time, types, shutil, traceback
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, RAIZ)
import tkinter as tk
from PIL import ImageGrab
import modelar as md, modelar_ui as mu, modelar_tema as T

FOTOS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAIZ, 'tests', 'modelar', 'saida')
TRAB = os.path.join(FOTOS, '_trabalho'); shutil.rmtree(TRAB, ignore_errors=True); os.makedirs(TRAB, exist_ok=True)
OK = FALHA = 0


def t(nome, fn):
    global OK, FALHA
    try:
        r = fn(); OK += 1; print('  ok  ', nome, '' if r is None else '-> %s' % (r,))
    except Exception as e:
        FALHA += 1; print('FALHA ', nome, '->', type(e).__name__, str(e)[:300]); traceback.print_exc()


raiz = tk.Tk(); raiz.title('Modelar (teste)'); raiz.configure(bg=T.BG); raiz.geometry('1180x690+20+10')
mesa_falsa = types.SimpleNamespace(pecas=[], sel=None, add_arquivo=lambda c, **k: mesa_falsa.pecas.append(c))
app = types.SimpleNamespace(pasta=TRAB, painel_mesa=mesa_falsa, aba=lambda n: None)
P = mu.PainelModelar(raiz, app); P.pack(fill='both', expand=True)


def rodar(seg=0.3):
    fim = time.time() + seg
    while time.time() < fim: raiz.update(); time.sleep(0.01)


def foto(nome):
    raiz.lift(); raiz.attributes('-topmost', True); rodar(0.5)
    import ctypes
    k = ImageGrab.grab().size[0] / float(ctypes.windll.user32.GetSystemMetrics(0))       # tela com zoom do Windows (125%): a foto usa pixels de verdade
    x, y, w, h = [int(v * k) for v in (raiz.winfo_rootx(), raiz.winfo_rooty(), raiz.winfo_width(), raiz.winfo_height())]
    ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(os.path.join(FOTOS, nome + '.png')); raiz.attributes('-topmost', False)


t0 = time.time()
while not P._pronto and time.time() - t0 < 60: rodar(0.2)
print('motor pronto em %.1fs' % (time.time() - t0)); assert P._pronto
foto('tela_1_vazia')


def campo(nome, valor): P.form['v'][nome].set(valor)


def f_caixa():
    P.ferramenta('caixa'); rodar(); assert P.form and P.form['op'] == 'caixa'
    campo('largura', '80'); campo('profundidade', '50'); campo('altura', '24'); campo('raio', '8'); rodar(0.5)
    assert P.vista.fantasma is not None, 'sem previa'; foto('tela_2_form_caixa'); P._aplicar(); rodar()
    assert P.form is None and len(P.proj.passos) == 1, P.l_erro.cget('text') if P.form else ''; return P.proj.descricao(0)


def f_casca():
    P.ferramenta('casca'); rodar(); campo('espessura', '2,4'); P._aplicar(); rodar(); assert len(P.proj.passos) == 2; return round(md.volume(P.proj.est) / 1000, 1)


def f_furo_clique():
    """Clica numa face da frente da peca na tela e abre o Furo: a posicao e a direcao vem do clique."""
    P.vista.vista('frente'); rodar(0.6); W, H = P.vista.winfo_width(), P.vista.winfo_height()
    h, info = P.vista.pick(W // 2 - 60, H // 2); assert h and h[0] == 'f' and info is not None, h
    P.vista.event_generate('<ButtonPress-1>', x=W // 2 - 60, y=H // 2); P.vista.event_generate('<ButtonRelease-1>', x=W // 2 - 60, y=H // 2); rodar(0.4)
    assert P.vista.sel_faces, 'clique nao selecionou a face'
    P.ferramenta('furo'); rodar(); d = P._ler_form(); assert d['direcao'] == '+y' and d['y'] == '', d
    campo('diametro', '6'); campo('z', '12'); P.form['v']['_rep_tipo'].set('Em fila / grade'); P._rep_campos(); P.form['x']['_rep_vars']['n'].set('3'); P.form['x']['_rep_vars']['dx'].set('20'); campo('x', '-20'); rodar(0.6)
    P.vista.vista('3d'); foto('tela_3_form_furo'); v0 = md.volume(P.proj.est); P._aplicar(); rodar(); assert P.form is None, 'erro: ' + (P.l_erro.cget('text') if P.form else '')
    assert md.volume(P.proj.est) < v0; return P.proj.descricao(2)


def f_arredondar_clique():
    """Passa o mouse e clica numa aresta de cima; arredonda 'as que eu cliquei'."""
    P.vista.vista('3d'); rodar(0.6); b = P.vista._buf; A2, B2, vis = b['seg']; c = P.vista.cena; dv = c.dv
    alvo = next(a for a in dv['info_arestas'] if a['tipo'] == 'reta' and abs(a['meio'][2] - 24) < 0.01 and a['comprimento'] > 50 and vis[c.SE == a['id']].all())
    k = [i for i in range(len(c.SE)) if c.SE[i] == alvo['id']]; j = k[len(k) // 2]; x, y = ((A2[j] + B2[j]) / 2).astype(int)
    h, _ = P.vista.pick(x, y); assert h == ('a', alvo['id']), (h, alvo['id'])
    P.vista.event_generate('<ButtonPress-1>', x=x, y=y); P.vista.event_generate('<ButtonRelease-1>', x=x, y=y); rodar(0.4); assert P.vista.sel_arestas == {alvo['id']}
    foto('tela_4_aresta_escolhida'); P.ferramenta('arredondar'); rodar(); assert P.form['v']['arestas'].get() == mu.NOME_ARESTAS['selecionadas']
    campo('raio', '1'); v0 = md.volume(P.proj.est); P._aplicar(); rodar(); assert P.form is None, P.l_erro.cget('text') if P.form else ''
    assert 0 < v0 - md.volume(P.proj.est) < 60 and isinstance(P.proj.passos[-1]['arestas'][0], dict); return P.proj.passos[-1]['arestas']


def f_desenho():
    """Extrudar: abre o editor de desenho, desenha um retangulo ARRASTANDO o mouse e um circulo-furo, conclui e aplica."""
    P.ferramenta('extrudar'); rodar(); P._desenhar('perfil'); rodar(0.5); E = P.editor; assert E is not None
    E.ferramenta('ret'); x0, y0 = E.tela(-15, -10); x1, y1 = E.tela(15, 10)
    E.c.event_generate('<ButtonPress-1>', x=int(x0), y=int(y0)); E.c.event_generate('<B1-Motion>', x=int(x1), y=int(y1)); E.c.event_generate('<ButtonRelease-1>', x=int(x1), y=int(y1)); rodar(0.3)
    assert len(E.figs) == 1 and E.figs[0]['t'] == 'ret' and abs(E.figs[0]['l'] - 30) < 1.01 and abs(E.figs[0]['a'] - 20) < 1.01, E.figs
    E.vars_campo['l'].set('30'); E.vars_campo['a'].set('20'); E.vars_campo['r'].set('3'); E.vars_campo['x'].set('0'); E.vars_campo['y'].set('0')
    E.ferramenta('circ'); cx, cy = E.tela(0, 0); bx, by = E.tela(5, 0)
    E.c.event_generate('<ButtonPress-1>', x=int(cx), y=int(cy)); E.c.event_generate('<B1-Motion>', x=int(bx), y=int(by)); E.c.event_generate('<ButtonRelease-1>', x=int(bx), y=int(by)); rodar(0.3)
    assert len(E.figs) == 2 and E.figs[1]['t'] == 'circ', E.figs; E.vars_campo['d'].set('10'); E._furo(True); rodar(0.3); foto('tela_5_desenho')
    E.concluir(); rodar(0.4); assert P.editor is None and len(P.form['x']['perfil']) == 2
    campo('altura', '6'); rodar(0.6); foto('tela_6_extrudar_previa'); n = len(P.proj.passos); P._aplicar(); rodar(); assert len(P.proj.passos) == n + 1, P.l_erro.cget('text') if P.form else ''
    return P.proj.descricao(n)


def f_editar_passo():
    P.editar_passo(0); rodar(); assert P.form['indice'] == 0 and P.form['v']['largura'].get() == '80'
    campo('largura', '100'); P._aplicar(); rodar(); assert P.form is None, P.l_erro.cget('text') if P.form else ''
    lim = P.proj.est.limites(); assert abs((lim[1] - lim[0])[0] - 100) < 0.01, lim; return 'largura 80 -> 100, peca refeita'


def f_variavel():
    P.definir_variavel('folga', '0,3'); assert P.proj.vars['folga'] == 0.3
    P.editar_passo(2); rodar(); campo('diametro', '6 + folga*2'); P._aplicar(); rodar(); assert P.form is None, P.l_erro.cget('text') if P.form else ''; return P.proj.passos[2]['diametro']


def f_desfazer():
    n = len(P.proj.passos); P.remover_passo(n - 1); rodar(); assert len(P.proj.passos) == n - 1; P.desfazer(); rodar(); assert len(P.proj.passos) == n; return n


def f_erro_amigavel():
    P.ferramenta('arredondar'); rodar(); P.form['v']['arestas'].set(mu.NOME_ARESTAS['todas']); campo('raio', '40'); P._aplicar(); rodar()
    assert P.form is not None and 'nao coube' in P.l_erro.cget('text'), P.l_erro.cget('text'); foto('tela_7_erro'); P._fechar_form(); rodar(); return 'mensagem mostrada, peca intacta'


def f_dois_projetos():
    P.novo_projeto(); rodar(); assert len(P.projs) == 2 and P.at == 1 and P.proj.est.vazio
    r = P.api(dict(acao='passos', lista=[dict(op='revolucao', perfil=[dict(t='poli', pts=[[0, 0], [22, 0], [26, 30], [18, 55], [14, 55], [22, 30], [18, 4], [0, 4]])]), dict(op='arredondar', raio=1.2, arestas='cima')]))
    assert r['ok'], r; P.renomear(1, 'Vaso'); rodar(0.5); foto('tela_8_segunda_peca'); P.ativar(0); rodar(0.4); assert len(P.proj.passos) >= 5; return [p.nome for p in P.projs]


def f_mesa():
    c = P.para_mesa(mostrar=False); assert c and os.path.isfile(c) and mesa_falsa.pecas == [c]
    import trimesh; m = trimesh.load(c); assert m.is_watertight and abs(m.bounds[0][2]) < 1e-6; return os.path.basename(c), len(m.faces)


def f_salvou():
    P._salvar_tudo(); arqs = sorted(os.listdir(os.path.join(TRAB, 'projetos_modelar'))); assert 'sessao.json' in arqs and sum(a.endswith('.modelo.json') for a in arqs) == 2, arqs; return arqs


def f_abrir_stl():
    stl = mesa_falsa.pecas[0]; p = P.abrir_arquivo(stl); rodar(0.4); assert p.est.tipo == 'malha' and len(P.projs) == 3
    P.ferramenta('arredondar'); rodar(); assert P.form is None and 'STL' in P.l_status.cget('text')
    P.ferramenta('furo'); rodar(); campo('diametro', '12'); campo('x', '30'); campo('y', '0'); P._aplicar(); rodar(); assert P.form is None, P.l_erro.cget('text') if P.form else ''
    foto('tela_9_stl_editado'); return P.proj.descricao(1)


for nome, fn in (('caixa pelo formulario (com previa)', f_caixa), ('casca', f_casca), ('furo: clique na face marca posicao e direcao + repetir 3x', f_furo_clique),
                 ('arredondar a aresta clicada', f_arredondar_clique), ('desenho com o mouse -> extrudar', f_desenho), ('mudar medida de passo antigo', f_editar_passo),
                 ('variavel em medida', f_variavel), ('apagar passo e desfazer', f_desfazer), ('erro amigavel (raio grande demais)', f_erro_amigavel),
                 ('segunda peca ao mesmo tempo (pela API)', f_dois_projetos), ('mandar para a Mesa 3D (STL fechado)', f_mesa), ('salvou sozinho os projetos', f_salvou),
                 ('abrir STL e editar (modo malha)', f_abrir_stl)):
    t(nome, fn)
P.ativar(0); rodar(0.5); P.vista.vista('3d'); foto('tela_10_final')
print('\n%d ok, %d falhas' % (OK, FALHA)); raiz.destroy(); sys.exit(1 if FALHA else 0)
