"""Teste da aba Modelar pelo caminho que a IA usa: MCP (funcoes de mcp_ender/server.py) -> API do programa -> aba Modelar.
O programa (imprimir_ender.py) precisa estar ABERTO. Nao manda nada para a impressora. Rodar: python tests/modelar/t_api.py [pasta_das_imagens]"""
import sys, os, time, base64, traceback
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, os.path.join(RAIZ, 'mcp_ender'))
import server as S

FOTOS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAIZ, 'tests', 'modelar', 'saida'); os.makedirs(FOTOS, exist_ok=True)
OK = FALHA = 0


def t(nome, fn):
    global OK, FALHA
    try:
        r = fn(); OK += 1; print('  ok  ', nome, '' if r is None else '-> %s' % (str(r)[:150],))
    except Exception as e:
        FALHA += 1; print('FALHA ', nome, '->', type(e).__name__, str(e)[:400])
        if '-v' in sys.argv: traceback.print_exc()


def ok(r):
    assert r.get('ok'), r.get('erro', r); return r


def img(nome, im):
    open(os.path.join(FOTOS, nome + '.png'), 'wb').write(im.data); return '%d KB' % (len(im.data) // 1024)


NOME = 'Teste API %s' % time.strftime('%H%M%S')


def f_ajuda():
    a = ok(S.ender_modelar_ajuda()); assert len(a['ferramentas']) >= 25 and 'perfil' in a; f = ok(S.ender_modelar_ajuda('furo')); assert f['parametros'][0]['nome'] == 'diametro'; return len(a['ferramentas'])


def f_novo():
    r = ok(S.ender_modelar_projetos('novo', NOME)); assert any(p['nome'] == NOME and p['ativo'] for p in r['projetos']); return [p['nome'] for p in r['projetos']]


def f_suporte():
    """Suporte de celular: base + encosto inclinado (desenho de lado) + rasgo para o cabo + furos + arredondar."""
    r = ok(S.ender_modelar_passos([
        dict(op='extrudar', plano='yz', posicao=-35, altura=70, perfil=[dict(t='poli', pts=[[0, 0], [70, 0], [70, 8], [62, 8], [62, 14], [56, 14], [56, 5], [22, 5], [8, 90], [0, 90]])]),
        dict(op='extrudar', plano='xy', posicao=-1, altura=20, modo='subtrair', perfil=[dict(t='rasgo', c=30, l=12, x=0, y=59, g=90)]),
        dict(op='furo', diametro=5, x=-22, y=40, tipo='escareado', diametro2=9, repetir=dict(tipo='linear', n=2, dx=44)),
        dict(op='chanfrar', tamanho=1, arestas=['esquerda', 'direita'])]))
    assert r['aplicados'] == 4 and r['tamanho'] == [70.0, 70.0, 90.0], r; return r['tamanho'], r['volume_cm3']


def f_ver(): return img('api_1_suporte', S.ender_modelar_ver('3d'))
def f_ver4(): return img('api_2_quatro_vistas', S.ender_modelar_ver_4vistas('arestas'))


def f_estado():
    e = ok(S.ender_modelar_estado(True)); assert e['tipo'] == 'cad' and len(e['passos']) == 4 and e['n_arestas'] > 20, e.keys(); return e['n_faces'], e['n_arestas'], e['passos'][0]['descricao']


def f_editar():
    r = ok(S.ender_modelar_editar_passo(1, dict(altura=90))); assert r['tamanho'][0] == 90.0, r['tamanho']
    r = ok(S.ender_modelar_editar_passo(1, dict(posicao=-45))); return r['min'], r['max']


def f_erro():
    r = S.ender_modelar_passo('arredondar', dict(raio=60)); assert not r['ok'] and 'nao coube' in r['erro'], r
    r2 = S.ender_modelar_passo('caixa', dict(largurra=3)); assert not r2['ok'] and 'desconhecido' in r2['erro'], r2
    r3 = S.ender_modelar_passo('codigo', dict(codigo='resultado = Box(1,1,1)')); assert not r3['ok'], r3
    e = ok(S.ender_modelar_estado(False)); assert len(e['passos']) == 4; return r['erro'][:90]


def f_variavel():
    ok(S.ender_modelar_variavel('folga', '0.3')); r = ok(S.ender_modelar_editar_passo(3, dict(diametro='5 + folga*2'))); assert r['variaveis'] == {'folga': 0.3}; return r['passos'][2]['descricao']


def f_texto():
    r = ok(S.ender_modelar_passo('texto', dict(txt='VICTOR', tam=9, prof=0.8, tipo='gravado', face='frente', v=-38))); return r['passos'][-1]['descricao']


def f_historico():
    ok(S.ender_modelar_historico('desfazer')); e = ok(S.ender_modelar_estado(False)); assert len(e['passos']) == 4
    ok(S.ender_modelar_historico('refazer')); e = ok(S.ender_modelar_estado(False)); assert len(e['passos']) == 5
    ok(S.ender_modelar_historico('alternar', 5)); ok(S.ender_modelar_historico('alternar', 5)); return 'desfazer/refazer/alternar'


def f_foto_final(): return img('api_3_final', S.ender_modelar_ver(az=-125, el=22))


def f_exportar():
    r = ok(S.ender_modelar_exportar('step')); assert os.path.getsize(r['arquivo']) > 2000; s = ok(S.ender_modelar_exportar('stl'))
    import trimesh; m = trimesh.load(s['arquivo']); assert m.is_watertight, 'STL aberto'; return os.path.basename(r['arquivo']), os.path.basename(s['arquivo']), len(m.faces)


def f_mesa():
    antes = len(S.ender_mesa_ver().get('pecas', [])); r = ok(S.ender_modelar_para_mesa()); time.sleep(1.5); m = S.ender_mesa_ver(); ps = m.get('pecas', [])
    assert len(ps) == antes + 1, (antes, len(ps)); n = len(ps); img('api_4_mesa', S.ender_mesa_imagem('3d'))
    ok(S.ender_mesa_remover(n)); return 'entrou na Mesa 3D como peca %d (cabe: %s) e foi retirada de novo' % (n, ps[-1].get('cabe', ps[-1].get('ok', '?')))


def f_abrir_stl():
    s = ok(S.ender_modelar_exportar('stl')); r = ok(S.ender_modelar_abrir(s['arquivo'])); assert r['tipo'] == 'malha', r['tipo']
    f = ok(S.ender_modelar_passo('furo', dict(diametro=8, x=0, y=10))); e = S.ender_modelar_passo('arredondar', dict(raio=1)); assert not e['ok'] and 'STL' in e['erro']
    img('api_5_stl_editado', S.ender_modelar_ver()); ok(S.ender_modelar_projetos('fechar')); return f['passos'][-1]['descricao']


def f_fechar():
    r = ok(S.ender_modelar_projetos('fechar', projeto=NOME)); assert not any(p['nome'] == NOME for p in r['projetos']); return [p['nome'] for p in r['projetos']]


for nome, fn in (('ajuda (lista de ferramentas)', f_ajuda), ('nova peca', f_novo), ('suporte de celular em 4 passos', f_suporte), ('imagem 3D', f_ver), ('imagem 4 vistas com numeros das arestas', f_ver4),
                 ('estado com faces e arestas', f_estado), ('editar passo antigo (peca se refaz)', f_editar), ('erros claros e peca intacta (raio grande, parametro errado, codigo desligado)', f_erro),
                 ('variavel + conta', f_variavel), ('texto gravado', f_texto), ('desfazer / refazer / desligar passo', f_historico), ('imagem em angulo livre', f_foto_final),
                 ('exportar STEP e STL (fechado)', f_exportar), ('mandar para a Mesa 3D', f_mesa), ('abrir STL e editar (malha)', f_abrir_stl), ('fechar a peca de teste', f_fechar)):
    t(nome, fn)
print('\n%d ok, %d falhas' % (OK, FALHA)); sys.exit(1 if FALHA else 0)
