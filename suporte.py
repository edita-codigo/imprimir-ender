"""Ajustes do SUPORTE (o que sustenta partes no ar). Tela "Ajustes do suporte..." + valores guardados em suporte.json.

O tipo (sem / so na mesa / em tudo) e o angulo ficam nos menus principais; aqui ficam os detalhes:
  estrutura  normal (colunas e paredes) ou ARVORE (galhos finos: gasta menos e sai facil; bom para pecas curvas e organicas)
  padrao     como o suporte e preenchido por dentro (zigue-zague, linhas, grade...)
  densidade  quanto de material (menos = mais facil de tirar; mais = apoia melhor)
  distancias folga entre suporte e peca: em cima (Z) e dos lados (XY). Folga maior = sai mais facil, acabamento pior.
  teto       camada fina e cheia embaixo da peca: acabamento melhor onde o suporte encosta."""
import os, json
import tkinter as tk

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(PASTA, 'suporte.json')
BG, CARD, TXT, DIM, VERDE, LARANJA, AZUL, VERM, AMARELO = '#0D1117', '#151B24', '#EAF0F8', '#93A0B5', '#38D39F', '#FF8A3D', '#5AB0FF', '#FF6B6B', '#F7C948'
LINHA = '#263041'
ESTRUTURAS = {'normal': 'Normal (colunas e paredes)', 'arvore': 'Árvore (galhos finos — peças curvas)'}
PADROES = {'zigzag': 'Zigue-zague', 'lines': 'Linhas', 'grid': 'Grade', 'triangles': 'Triângulos', 'cross': 'Cruz', 'gyroid': 'Gyroid'}
PADRAO = dict(estrutura='normal', padrao='zigzag', dens=15, z=0.2, xy=0.8, teto=True)
PRESETS = {
    'Peça normal': dict(estrutura='normal', padrao='zigzag', dens=15, z=0.2, xy=0.8, teto=True),
    'Peça curva / orgânica (árvore)': dict(estrutura='arvore', padrao='zigzag', dens=15, z=0.2, xy=0.8, teto=True),
    'Econômico (sai fácil)': dict(estrutura='arvore', padrao='lines', dens=8, z=0.3, xy=1.0, teto=False),
    'Firme (apoia melhor)': dict(estrutura='normal', padrao='grid', dens=30, z=0.15, xy=0.6, teto=True),
}


def carregar():
    c = dict(PADRAO)
    try:
        d = json.load(open(ARQ, encoding='utf-8'))
        if d.get('estrutura') in ESTRUTURAS: c['estrutura'] = d['estrutura']
        if d.get('padrao') in PADROES: c['padrao'] = d['padrao']
        for k, lo, hi in (('dens', 3, 80), ('z', 0.05, 1.0), ('xy', 0.2, 3.0)):
            try: c[k] = max(lo, min(hi, float(d[k]) if k != 'dens' else int(d[k])))
            except (KeyError, ValueError, TypeError): pass
        c['teto'] = bool(d.get('teto', c['teto']))
    except Exception: pass
    return c


def salvar(c):
    try: json.dump(c, open(ARQ, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    except Exception: pass


def abrir(app):
    """Janela com todos os ajustes do suporte (usa as variaveis do app; cada mudanca refaz o fatiamento sozinha)."""
    if getattr(app, '_jan_sup', None) and app._jan_sup.winfo_exists(): app._jan_sup.lift(); app._jan_sup.focus_force(); return
    j = tk.Toplevel(app); app._jan_sup = j; j.title('Ajustes do suporte'); j.configure(bg=BG); j.geometry('600x830+20+0'); j.transient(app)
    def rot(t, pad=(7, 1)): tk.Label(j, text=t, bg=BG, fg=DIM, font=('Segoe UI', 9, 'bold'), anchor='w').pack(fill='x', padx=18, pady=pad)
    def dica(t): tk.Label(j, text=t, bg=BG, fg=DIM, font=('Segoe UI', 8), anchor='w', justify='left', wraplength=520).pack(fill='x', padx=18)
    tk.Button(j, text='Fechar', command=j.destroy, bg=VERDE, fg='#0D1117', relief='flat', bd=0, cursor='hand2', font=('Segoe UI', 10, 'bold'), padx=18, pady=6).pack(side='bottom', pady=10)
    tk.Label(j, text='SUPORTE', bg=BG, fg=TXT, font=('Segoe UI', 14, 'bold')).pack(anchor='w', padx=18, pady=(14, 0))
    dica('Mudou, vale na hora (refatia sozinho). Veja em "VER CAMADAS": o suporte aparece em azul-claro.')
    rot('JÁ PRONTO PARA…')
    f = tk.Frame(j, bg=BG); f.pack(fill='x', padx=18)
    for i, (nome, vals) in enumerate(PRESETS.items()):
        tk.Button(f, text=nome, command=lambda v=vals: app.sup_aplicar(v), bg=LINHA, fg=TXT, relief='flat', bd=0, cursor='hand2', font=('Segoe UI', 9), padx=8, pady=4).grid(row=i // 2, column=i % 2, sticky='ew', padx=3, pady=3)
    f.columnconfigure(0, weight=1); f.columnconfigure(1, weight=1)
    rot('ONDE PÕE SUPORTE')
    om = tk.OptionMenu(j, app.v_sup, *app.SUPORTES_TXT); om.config(bg=LINHA, fg=TXT, relief='flat', bd=0, highlightthickness=0, activebackground='#33405A', font=('Segoe UI', 10)); om['menu'].config(bg=LINHA, fg=TXT); om.pack(fill='x', padx=18)
    rot('ESTRUTURA')
    for k, t in ESTRUTURAS.items():
        tk.Radiobutton(j, text=t, variable=app.v_sup_estr, value=k, bg=BG, fg=TXT, selectcolor=LINHA, activebackground=BG, activeforeground=TXT, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 10)).pack(fill='x', padx=18)
    dica('Árvore: galhos finos, gasta menos e sai fácil. Melhor para peças curvas e cheias de detalhes.')
    rot('PREENCHIMENTO DO SUPORTE')
    om2 = tk.OptionMenu(j, app.v_sup_pad_txt, *PADROES.values()); om2.config(bg=LINHA, fg=TXT, relief='flat', bd=0, highlightthickness=0, activebackground='#33405A', font=('Segoe UI', 10)); om2['menu'].config(bg=LINHA, fg=TXT); om2.pack(fill='x', padx=18)
    def barra(titulo, var, de, ate, passo, un, dica_t):
        rot(titulo); r = tk.Frame(j, bg=BG); r.pack(fill='x', padx=18)
        tk.Scale(r, from_=de, to=ate, resolution=passo, orient='horizontal', variable=var, bg=BG, fg=TXT, troughcolor=LINHA, highlightthickness=0, length=420).pack(side='left')
        tk.Label(r, text=un, bg=BG, fg=DIM).pack(side='left', padx=6); dica(dica_t)
    barra('ÂNGULO (acima de quantos graus de inclinação precisa de suporte)', app.v_ang, 20, 80, 5, '°', 'Menor = mais suporte. Maior = só os balanços grandes.')
    barra('DENSIDADE', app.v_sup_dens, 3, 80, 1, '%', 'Menos = sai fácil. Mais = apoia melhor, mas gruda e gasta mais.')
    barra('FOLGA EM CIMA (entre o suporte e a peça)', app.v_sup_z, 0.05, 0.6, 0.05, 'mm', 'Menor = acabamento melhor, mas gruda. Maior = solta fácil.')
    barra('FOLGA DOS LADOS', app.v_sup_xy, 0.2, 2.5, 0.1, 'mm', 'Distância do suporte até as paredes da peça.')
    tk.Checkbutton(j, text='Camada de "teto" cheia embaixo da peça (acabamento melhor onde apoia)', variable=app.v_sup_teto, bg=BG, fg=TXT, selectcolor=LINHA, activebackground=BG, activeforeground=TXT, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 10)).pack(fill='x', padx=16, pady=(10, 0))
