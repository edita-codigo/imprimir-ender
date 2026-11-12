"""Teste do ARRASTAR COM O MOUSE na aba Modelar: mover a forma vermelha pelo corpo, puxar os quadradinhos de tamanho, bolinha de subir/descer,
Mover e Escalar a peca pronta, e conferir que arrastar no vazio continua girando a vista. Rodar: python tests/modelar/t_arrastar.py [pasta_das_fotos]"""
import sys, os, time, types, shutil, traceback
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, RAIZ)
import tkinter as tk
import numpy as np
from PIL import ImageGrab
import modelar as md, modelar_ui as mu, modelar_tema as T

FOTOS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAIZ, 'tests', 'modelar', 'saida')
TRAB = os.path.join(FOTOS, '_trabalho_arrastar'); shutil.rmtree(TRAB, ignore_errors=True); os.makedirs(TRAB, exist_ok=True)
OK = FALHA = 0


def t(nome, fn):
    global OK, FALHA
    try:
        r = fn(); OK += 1; print('  ok  ', nome, '' if r is None else '-> %s' % (r,))
    except Exception as e:
        FALHA += 1; print('FALHA ', nome, '->', type(e).__name__, str(e)[:300]); traceback.print_exc()


raiz = tk.Tk(); raiz.title('Modelar (teste arrastar)'); raiz.configure(bg=T.BG); raiz.geometry('1180x690+20+10')
mesa_falsa = types.SimpleNamespace(pecas=[], sel=None, add_arquivo=lambda c, **k: mesa_falsa.pecas.append(c))
app = types.SimpleNamespace(pasta=TRAB, painel_mesa=mesa_falsa, aba=lambda n: None)
P = mu.PainelModelar(raiz, app); P.pack(fill='both', expand=True); V = P.vista


def rodar(seg=0.3):
    fim = time.time() + seg
    while time.time() < fim: raiz.update(); time.sleep(0.01)


def foto(nome):
    raiz.lift(); raiz.attributes('-topmost', True); rodar(0.5)
    import ctypes
    k = ImageGrab.grab().size[0] / float(ctypes.windll.user32.GetSystemMetrics(0))
    x, y, w, h = [int(v * k) for v in (raiz.winfo_rootx(), raiz.winfo_rooty(), raiz.winfo_width(), raiz.winfo_height())]
    ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(os.path.join(FOTOS, nome + '.png')); raiz.attributes('-topmost', False)


t0 = time.time()
while not P._pronto and time.time() - t0 < 60: rodar(0.2)
assert P._pronto


def abrir(op):
    P.ferramenta(op); t1 = time.time()
    while V.fantasma is None and time.time() - t1 < 8: rodar(0.2)
    rodar(0.5)


def val(nome): return float(P.form['v'][nome].get().replace(',', '.'))


def tela(p):
    S, _ = V._proj(np.array([p], dtype=float), V._cam()); return int(round(S[0, 0])), int(round(S[0, 1]))


def arrastar(x0, y0, x1, y1, passos=6):
    V.event_generate('<ButtonPress-1>', x=x0, y=y0); rodar(0.05)
    for i in range(1, passos + 1):
        V.event_generate('<B1-Motion>', x=int(x0 + (x1 - x0) * i / passos), y=int(y0 + (y1 - y0) * i / passos)); rodar(0.05)
    V.event_generate('<ButtonRelease-1>', x=x1, y=y1); rodar(0.5)


def alca(i):
    a = next(q for q in V.alcas if q['id'] == i); return tela(a['p'])


def f_esfera_mover():
    abrir('esfera'); assert V.fantasma is not None and V.corpo_arrastavel, 'sem previa/arrasto'
    assert {q['id'] for q in V.alcas} == {'t:diametro', 'z'}, [q['id'] for q in V.alcas]
    x, y = tela((0, 0, 10)); foto('arr_1_esfera_alcas'); arrastar(x, y, x + 90, y + 30)
    nx, ny, nz = val('x'), val('y'), val('z'); assert abs(nx) + abs(ny) > 5 and nz == 10, (nx, ny, nz)
    c = (V.fantasma[0].min(0) + V.fantasma[0].max(0)) / 2; assert abs(c[0] - nx) < 0.3 and abs(c[1] - ny) < 0.3, (c, nx, ny)      # a forma vermelha foi junto
    return 'x %g  y %g' % (nx, ny)


def f_esfera_tamanho():
    d0 = val('diametro'); x, y = alca('t:diametro'); cx, cy = tela((val('x'), val('y'), val('z')))
    arrastar(x, y, x + (x - cx) * 1, y + (y - cy) * 1); d1 = val('diametro'); assert d1 > d0 * 1.5, (d0, d1)
    x, y = alca('t:diametro'); cx, cy = tela((val('x'), val('y'), val('z'))); arrastar(x, y, int(x - (x - cx) * 0.5), int(y - (y - cy) * 0.5)); d2 = val('diametro'); assert d2 < d1 * 0.75, (d1, d2)
    return 'diametro %g -> %g -> %g' % (d0, d1, d2)


def f_esfera_subir():
    z0 = val('z'); x, y = alca('z'); arrastar(x, y, x, y - 60); z1 = val('z'); assert z1 > z0 + 3 and val('diametro') > 0, (z0, z1)
    foto('arr_2_esfera_arrastada'); x0, y0 = val('x'), val('y'); P._aplicar(); rodar(0.6); assert P.form is None and len(P.proj.passos) == 1, P.l_erro.cget('text') if P.form else ''
    lim = P.proj.est.limites(); c = (lim[0] + lim[1]) / 2; assert abs(c[0] - x0) < 0.01 and abs(c[1] - y0) < 0.01 and abs(c[2] - z1) < 0.01, (c, x0, y0, z1)
    assert not V.alcas and not V.corpo_arrastavel; return 'z %g -> %g; aplicada no lugar arrastado' % (z0, z1)


def f_caixa_alcas():
    abrir('caixa'); ids = {q['id'] for q in V.alcas}; assert ids == {'t:largura', 't:profundidade', 't:altura', 'z'}, ids
    l0 = val('largura'); x, y = alca('t:largura'); cx, cy = tela((val('x'), val('y'), val('z') + val('altura') / 2)); arrastar(x, y, x + (x - cx), y + (y - cy)); l1 = val('largura'); assert l1 > l0 * 1.6, (l0, l1)
    h0 = val('altura'); x, y = alca('t:altura'); arrastar(x, y, x, y - 50); h1 = val('altura'); assert h1 > h0 + 3, (h0, h1)
    foto('arr_3_caixa'); P._fechar_form(); rodar(0.3); return 'largura %g -> %g, altura %g -> %g' % (l0, l1, h0, h1)


def f_vazio_gira():
    az = V.az; arrastar(30, 40, 130, 60); assert abs(V.az - az) > 10, (az, V.az); P.vista.vista('3d'); rodar(0.4); return 'arrastar no vazio girou %.0f graus' % abs(V.az - az)


def f_mover_peca():
    lim0 = P.proj.est.limites(); abrir('mover'); assert V.fantasma is not None and V.peca_arrastavel
    c = (lim0[0] + lim0[1]) / 2; x, y = tela(c); arrastar(x, y, x - 80, y + 20); dx, dy = val('dx'), val('dy'); assert abs(dx) + abs(dy) > 5, (dx, dy)
    x, y = alca('z'); arrastar(x, y, x, y - 40); dz = val('dz'); assert dz > 2, dz
    foto('arr_4_mover'); P._aplicar(); rodar(0.6); assert P.form is None, P.l_erro.cget('text') if P.form else ''
    lim1 = P.proj.est.limites(); assert np.allclose(lim1[0] - lim0[0], [dx, dy, dz], atol=0.01), (lim1[0] - lim0[0], dx, dy, dz); return 'peca andou (%g, %g, %g)' % (dx, dy, dz)


def f_escalar_peca():
    lim0 = P.proj.est.limites(); abrir('escalar'); assert [q['id'] for q in V.alcas] == ['esc']
    c = (lim0[0] + lim0[1]) / 2; x, y = alca('esc'); cx, cy = tela(c); arrastar(x, y, x + (x - cx), y + (y - cy)); k = val('x'); assert k > 150 and val('y') == k and val('z') == k, (k, val('y'), val('z'))
    foto('arr_5_escalar'); P._aplicar(); rodar(0.6); assert P.form is None, P.l_erro.cget('text') if P.form else ''
    lim1 = P.proj.est.limites(); r = (lim1[1] - lim1[0])[0] / (lim0[1] - lim0[0])[0]; assert abs(r - k / 100) < 0.01, (r, k); return 'escala %g%%' % k


def f_editar_passo_arrastando():
    P.editar_passo(0); rodar(1.5); assert P.form['indice'] == 0 and V.corpo_arrastavel
    x0 = val('x'); x, y = tela((val('x'), val('y'), val('z'))); arrastar(x, y, x + 60, y); assert val('x') != x0; P._aplicar(); rodar(0.6); assert P.form is None, P.l_erro.cget('text') if P.form else ''
    return 'passo antigo refeito com x %g -> %s' % (x0, P.proj.passos[0]['x'])


def f_furo_arrasta():
    P.novo_projeto(); rodar(0.3); r = P.api(dict(acao='passos', lista=[dict(op='caixa', largura=60, profundidade=40, altura=10)])); assert r['ok'], r; rodar(0.5); P.vista.vista('3d'); rodar(0.5)
    abrir('furo'); assert V.fantasma is not None and V.plano_fixo == 2
    x, y = tela((0, 0, 10)); arrastar(x, y, x + 50, y + 10); assert abs(val('x')) + abs(val('y')) > 3, (val('x'), val('y')); foto('arr_6_furo')
    v0 = md.volume(P.proj.est); P._aplicar(); rodar(0.6); assert P.form is None and md.volume(P.proj.est) < v0; return 'furo em (%g, %g)' % (P.proj.passos[-1]['x'], P.proj.passos[-1]['y'])


for nome, fn in (('esfera: arrastar o corpo muda X/Y', f_esfera_mover), ('esfera: quadradinho aumenta e diminui', f_esfera_tamanho), ('esfera: bolinha sobe + aplicar', f_esfera_subir),
                 ('caixa: alcas de largura e altura', f_caixa_alcas), ('arrastar no vazio continua girando', f_vazio_gira), ('Mover: arrastar a peca pronta', f_mover_peca),
                 ('Escalar: puxar o canto', f_escalar_peca), ('mudar passo antigo arrastando', f_editar_passo_arrastando), ('furo desliza na face', f_furo_arrasta)):
    t(nome, fn)
print('\n%d ok, %d falhas' % (OK, FALHA)); raiz.destroy(); sys.exit(1 if FALHA else 0)
