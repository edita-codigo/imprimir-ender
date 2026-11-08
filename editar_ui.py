"""Aba 'Editar peça': abrir uma peca (da Mesa ou de um STL), fazer furo / corte / formas / texto / desenho, ver em 3D, desfazer e salvar como COPIA.
Tambem e a porta de entrada da API/MCP (api): a IA edita a peca e consegue VER o resultado (imagem)."""
import os, io, base64, types
import numpy as np
import trimesh
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from trimesh.transformations import rotation_matrix
import editar_peca as ep
import vista3d
import mesa3d

BG, CARD, TXT, DIM, VERDE, LARANJA, AZUL, VERM, AMARELO = '#0D1117', '#151B24', '#EAF0F8', '#93A0B5', '#38D39F', '#FF8A3D', '#5AB0FF', '#FF6B6B', '#F7C948'
LINHA = '#263041'
VISTAS = {'frente': (-90.0, 9.0), 'topo': (-90.0, 89.0), 'lado': (0.0, 9.0), '3d': (-62.0, 30.0), 'tras': (90.0, 9.0), 'baixo': (-90.0, -80.0)}


class PecaEd:
    """Peca para a Vista3D (sem recentralizar: assim a ferramenta fantasma e a peca ficam no mesmo referencial)."""
    def __init__(self, mesh, cor, centro, ok=True, nome='peca'):
        self.prev = mesh; self.cor = cor; self.rot = 0.0; self.esc = 100.0; self.ok = ok; self.motivo = ''; self.nome = nome; self.caminho = nome
        self.centro = np.array(centro[:2], dtype=float); self.x, self.y = float(centro[0]), float(centro[1])
        v = np.asarray(mesh.vertices)[:, :2]; self.hull0 = mesa3d._hull(v); self.h0 = float(max(mesh.bounds[1][2], 0.1))

    @property
    def altura(self): return self.h0

    def contorno(self, rot=None): return self.hull0 + self.centro

    def tamanho(self, rot=None):
        c = self.contorno(); mn, mx = c.min(0), c.max(0); return float(mx[0] - mn[0]), float(mx[1] - mn[1])

    def vertices_mesa(self, V): return np.column_stack([V[:, :2] + self.centro, V[:, 2]])


class MesaEd:
    """O que a Vista3D espera de uma 'mesa' (aqui nada se arrasta: so a camera mexe)."""
    def __init__(self): self.pecas = []; self.sel = None; self.var_mar = types.SimpleNamespace(get=lambda: 0.0)
    def mover_sel(self, *a): pass
    def girar(self, *a): pass
    def copiar_uma(self, *a): pass
    def selecionar(self, *a): pass
    def mover_peca(self, *a): pass
    def girar_peca(self, *a): pass
    def terminou_mexer(self, *a): pass
    def menu_direito(self, *a): pass
    def remover(self, *a): pass


class Sessao:
    def __init__(self):
        self.orig = None; self.mesh = None; self.hist = []; self.passos = []; self.nome = ''; self.caminho = ''; self.cor_fixa = None; self.fantasma = None

    def aberta(self):
        if self.mesh is None: raise ep.ErroEdicao('Nenhuma peca aberta. Abra uma peca primeiro (da Mesa 3D ou um STL).')
        return self.mesh

    def abrir(self, mesh, nome, caminho, cor_fixa=None):
        self.orig = ep.recentralizar(mesh); self.mesh = self.orig.copy(); self.hist = []; self.passos = []; self.nome = nome; self.caminho = caminho; self.cor_fixa = cor_fixa; self.fantasma = None

    def aplicar(self, fn, desc):
        novo = fn(self.aberta()); self.hist.append((self.mesh, self.passos[:])); self.mesh = novo; self.passos.append(desc); self.fantasma = None

    def desfazer(self):
        if not self.hist: raise ep.ErroEdicao('Nao ha o que desfazer.')
        self.mesh, self.passos = self.hist.pop(); self.fantasma = None

    def voltar_original(self):
        self.aberta(); self.mesh = self.orig.copy(); self.hist = []; self.passos = []; self.fantasma = None

    def estado(self):
        m = self.aberta(); i = ep.info(m)
        return dict(peca=self.nome, min=i['min'], max=i['max'], tamanho=i['tamanho'], centro=[round(float((a + b) / 2), 2) for a, b in zip(m.bounds[0], m.bounds[1])], faces=i['faces'], fechada=i['fechada'], passos=list(self.passos), pode_desfazer=bool(self.hist),
                    dica='Coordenadas em mm no sistema da peca: X/Y centrados, base em Z=0. As operacoes usam esse mesmo sistema (veja min/max).')

    # ---- poligono desenhado (esbocado) e extrudado ----
    def malha_poligono(self, pontos, plano, offset, altura):
        from shapely.geometry import Polygon
        pts = [(float(p[0]), float(p[1])) for p in pontos]
        if len(pts) < 3: raise ep.ErroEdicao('o desenho precisa de pelo menos 3 pontos [[u,v],...]')
        poly = Polygon(pts).buffer(0)
        if poly.is_empty or poly.area < 1e-6: raise ep.ErroEdicao('o desenho nao forma uma area (pontos em linha ou cruzados?)')
        geos = list(poly.geoms) if hasattr(poly, 'geoms') else [poly]
        h = max(0.05, float(altura)); t = trimesh.util.concatenate([trimesh.creation.extrude_polygon(g, h) for g in geos if g.area > 1e-6])
        if plano == 'xy': t.apply_translation([0, 0, offset])
        elif plano in ('xz', 'yz'):
            t.apply_transform(rotation_matrix(np.pi / 2, [1, 0, 0]))          # u->x, v->z, extrusao para -y
            if plano == 'xz': t.apply_translation([0, offset + h, 0])
            else: t.apply_transform(rotation_matrix(np.pi / 2, [0, 0, 1])); t.apply_translation([offset, 0, 0])      # u->y, extrusao para +x
        else: raise ep.ErroEdicao("plano deve ser 'xy' (extruda em Z), 'xz' (extruda em Y) ou 'yz' (extruda em X)")
        return t

    # ---- operacoes (aplicar) ----
    def furo(self, x, y, z, diametro, comprimento=0, eixo='z'):
        self.aplicar(lambda m: ep.furo(m, x, y, z, diametro, comprimento, eixo), 'furo ø%g em (%g, %g, %g) eixo %s' % (diametro, x, y, z, eixo))

    def cortar(self, eixo, posicao, manter='menor'):
        self.aplicar(lambda m: ep.cortar_plano(m, eixo, posicao, manter), 'corte em %s=%g (fica a parte %s)' % (eixo, posicao, manter))

    def forma(self, tipo, modo, x, y, z, a, b=None, c=None, eixo='z'):
        self.aplicar(lambda m: ep.forma(m, tipo, modo, x, y, z, a, b, c, eixo), '%s %s em (%g, %g, %g)' % (modo, tipo, x, y, z))

    def texto(self, txt, tam, prof, modo, face, u, v, giro, fonte):
        self.aplicar(lambda m: ep.texto(m, txt, tam, prof, modo, face, u, v, giro, fonte), 'texto "%s" %s na face %s' % (txt, modo, face))

    def poligono(self, pontos, plano, offset, altura, modo):
        if modo not in ('somar', 'subtrair'): raise ep.ErroEdicao("modo deve ser 'somar' ou 'subtrair'")
        def f(m):
            t = self.malha_poligono(pontos, plano, offset, altura)
            return ep._bool(m, t, 'soma' if modo == 'somar' else 'sub')
        self.aplicar(f, 'desenho de %d pontos (%s) no plano %s' % (len(pontos), modo, plano))

    # ---- fantasma (ferramenta mostrada em vermelho antes de aplicar) ----
    def ferramenta(self, op, p):
        m = self.aberta()
        if op == 'furo':
            L = p['comprimento'] if p.get('comprimento') else ep._diag(m) * 3
            return ep.forma_cilindro(p['diametro'], L, p['eixo'], (p['x'], p['y'], p['z']))
        if op == 'cortar':
            i = ep.EIXOS.index(p['eixo']); ext = [float((m.bounds[1][k] - m.bounds[0][k]) * 1.3 + 4) for k in range(3)]; ext[i] = 0.4
            c = [float((m.bounds[0][k] + m.bounds[1][k]) / 2) for k in range(3)]; c[i] = p['posicao']
            return ep.forma_caixa(ext[0], ext[1], ext[2], c)
        if op == 'forma':
            t = p['tipo']
            if t == 'caixa': return ep.forma_caixa(p['a'], p.get('b') or p['a'], p.get('c') or p['a'], (p['x'], p['y'], p['z']))
            if t == 'cilindro': return ep.forma_cilindro(p['a'], p.get('b') or p['a'], p['eixo'], (p['x'], p['y'], p['z']))
            return ep.forma_esfera(p['a'], (p['x'], p['y'], p['z']))
        if op == 'texto': return ep.texto_malha_posicionada(m, p['txt'], p['tam'], p['prof'], p['modo'], p['face'], p['u'], p['v'], p['giro'], p['fonte'])
        if op == 'poligono': return self.malha_poligono(p['pontos'], p['plano'], p['offset'], p['altura'])
        raise ep.ErroEdicao('ferramenta desconhecida')


class PainelEditar(tk.Frame):
    def __init__(self, pai, app):
        super().__init__(pai, bg=BG)
        self.app = app; self.s = Sessao(); self.mesa_ed = MesaEd(); self.v = {}
        self.pasta = os.path.join(app.pasta, 'pecas_editadas')
        self._montar(); self._atualizar()

    # ---------------- interface ----------------
    def _campo(self, pai, rotulo, padrao, larg=8, linha=None):
        var = tk.StringVar(value=str(padrao)); f = linha or tk.Frame(pai, bg=CARD)
        if linha is None: f.pack(fill='x', pady=1)
        tk.Label(f, text=rotulo, bg=CARD, fg=DIM, font=('Segoe UI', 9), width=0).pack(side='left', padx=(0, 4))
        tk.Entry(f, textvariable=var, width=larg, bg=BG, fg=TXT, insertbackground=TXT, relief='flat', font=('Segoe UI', 10)).pack(side='left', padx=(0, 10), ipady=2)
        return var

    def _opcao(self, pai, rotulo, var, valores, linha=None):
        f = linha or tk.Frame(pai, bg=CARD)
        if linha is None: f.pack(fill='x', pady=1)
        tk.Label(f, text=rotulo, bg=CARD, fg=DIM, font=('Segoe UI', 9)).pack(side='left', padx=(0, 4))
        om = tk.OptionMenu(f, var, *valores); om.config(bg=LINHA, fg=TXT, activebackground='#33405A', highlightthickness=0, bd=0, font=('Segoe UI', 9)); om.pack(side='left', padx=(0, 10))

    def _botoes(self, pai, op):
        f = tk.Frame(pai, bg=CARD); f.pack(fill='x', pady=(6, 2))
        self.app.botao(f, 'Mostrar onde', lambda: self.previa(op), LINHA).pack(side='left')
        self.app.botao(f, 'APLICAR', lambda: self.aplicar(op), VERDE).pack(side='left', padx=6)

    def _montar(self):
        a = self.app
        corpo = tk.Frame(self, bg=BG); corpo.pack(fill='both', expand=True, padx=12, pady=8)
        esq = a.card(corpo); esq.pack(side='left', fill='y', padx=(0, 8)); esq.config(width=420); esq.pack_propagate(False)
        a.rotulo(esq, 'EDITAR PEÇA').pack(fill='x', padx=12, pady=(10, 2))
        r = tk.Frame(esq, bg=CARD); r.pack(fill='x', padx=12)
        a.botao(r, 'Pegar a peça selecionada da Mesa', self.pegar_da_mesa, AZUL).pack(side='left'); a.botao(r, 'Abrir STL…', self.abrir_arquivo, LINHA).pack(side='left', padx=6)
        self.l_info = tk.Label(esq, text='', bg=CARD, fg=TXT, font=('Segoe UI', 9), justify='left', anchor='w', wraplength=390); self.l_info.pack(fill='x', padx=12, pady=(6, 4))
        nb = ttk.Notebook(esq); nb.pack(fill='x', padx=10, pady=4)
        self.nb = nb
        # --- furo
        t = tk.Frame(nb, bg=CARD, padx=8, pady=6); nb.add(t, text='Furo')
        tk.Label(t, text='Fura a peça. Posição = centro do furo (mm, X/Y centrados na peça, Z=0 na base).', bg=CARD, fg=DIM, font=('Segoe UI', 8), wraplength=380, justify='left').pack(anchor='w')
        f = tk.Frame(t, bg=CARD); f.pack(fill='x'); self.v['f_x'] = self._campo(t, 'X', 0, 6, f); self.v['f_y'] = self._campo(t, 'Y', 0, 6, f); self.v['f_z'] = self._campo(t, 'Z', 5, 6, f)
        f = tk.Frame(t, bg=CARD); f.pack(fill='x'); self.v['f_d'] = self._campo(t, 'Diâmetro', 4, 6, f); self.v['f_l'] = self._campo(t, 'Comprimento (0 = atravessa)', 0, 6, f)
        self.v['f_e'] = tk.StringVar(value='z'); self._opcao(t, 'Direção do furo (eixo):', self.v['f_e'], ep.EIXOS); self._botoes(t, 'furo')
        # --- cortar
        t = tk.Frame(nb, bg=CARD, padx=8, pady=6); nb.add(t, text='Cortar')
        tk.Label(t, text='Corta num plano e joga fora um lado (ex.: eixo Z em 10 e "menor" = fica só a parte de baixo, até 10 mm).', bg=CARD, fg=DIM, font=('Segoe UI', 8), wraplength=380, justify='left').pack(anchor='w')
        self.v['c_e'] = tk.StringVar(value='z'); self._opcao(t, 'Eixo:', self.v['c_e'], ep.EIXOS); self.v['c_p'] = self._campo(t, 'Posição (mm)', 10, 8)
        self.v['c_m'] = tk.StringVar(value='menor'); self._opcao(t, 'Ficar com a parte:', self.v['c_m'], ('menor', 'maior')); self._botoes(t, 'cortar')
        # --- forma
        t = tk.Frame(nb, bg=CARD, padx=8, pady=6); nb.add(t, text='Forma')
        tk.Label(t, text='Soma ou tira uma forma (caixa, cilindro, esfera). Para tirar um pedaço: forma "subtrair".', bg=CARD, fg=DIM, font=('Segoe UI', 8), wraplength=380, justify='left').pack(anchor='w')
        self.v['m_t'] = tk.StringVar(value='caixa'); self.v['m_m'] = tk.StringVar(value='subtrair')
        f = tk.Frame(t, bg=CARD); f.pack(fill='x'); self._opcao(t, 'Forma:', self.v['m_t'], ('caixa', 'cilindro', 'esfera'), f); self._opcao(t, 'Modo:', self.v['m_m'], ('somar', 'subtrair'), f)
        f = tk.Frame(t, bg=CARD); f.pack(fill='x'); self.v['m_x'] = self._campo(t, 'X', 0, 6, f); self.v['m_y'] = self._campo(t, 'Y', 0, 6, f); self.v['m_z'] = self._campo(t, 'Z', 5, 6, f)
        tk.Label(t, text='Tamanhos: caixa = largura X / prof. Y / altura Z · cilindro = diâmetro / comprimento · esfera = diâmetro', bg=CARD, fg=DIM, font=('Segoe UI', 8), wraplength=380, justify='left').pack(anchor='w')
        f = tk.Frame(t, bg=CARD); f.pack(fill='x'); self.v['m_a'] = self._campo(t, 'A', 10, 6, f); self.v['m_b'] = self._campo(t, 'B', 10, 6, f); self.v['m_c'] = self._campo(t, 'C', 10, 6, f)
        self.v['m_e'] = tk.StringVar(value='z'); self._opcao(t, 'Eixo do cilindro:', self.v['m_e'], ep.EIXOS); self._botoes(t, 'forma')
        # --- texto
        t = tk.Frame(nb, bg=CARD, padx=8, pady=6); nb.add(t, text='Texto')
        self.v['t_txt'] = self._campo(t, 'Texto', 'NOME', 24); f = tk.Frame(t, bg=CARD); f.pack(fill='x')
        self.v['t_tam'] = self._campo(t, 'Altura da letra', 8, 5, f); self.v['t_prof'] = self._campo(t, 'Relevo/fundo', 1, 5, f)
        self.v['t_modo'] = tk.StringVar(value='relevo'); self.v['t_face'] = tk.StringVar(value='cima'); self.v['t_fonte'] = tk.StringVar(value=ep.fontes_disponiveis()[0])
        f = tk.Frame(t, bg=CARD); f.pack(fill='x'); self._opcao(t, 'Modo:', self.v['t_modo'], ('relevo', 'gravado'), f); self._opcao(t, 'Face:', self.v['t_face'], ep.FACES, f)
        self._opcao(t, 'Fonte:', self.v['t_fonte'], ep.fontes_disponiveis())
        f = tk.Frame(t, bg=CARD); f.pack(fill='x'); self.v['t_u'] = self._campo(t, 'Desloc. →', 0, 5, f); self.v['t_v'] = self._campo(t, '↑', 0, 5, f); self.v['t_g'] = self._campo(t, 'Girar°', 0, 5, f)
        self._botoes(t, 'texto')
        # --- desenho
        t = tk.Frame(nb, bg=CARD, padx=8, pady=6); nb.add(t, text='Desenho')
        tk.Label(t, text='Desenhe uma figura com pontos (um por linha: u,v em mm) e dê espessura. Plano XY = em cima/embaixo; XZ = na frente; YZ = no lado.', bg=CARD, fg=DIM, font=('Segoe UI', 8), wraplength=380, justify='left').pack(anchor='w')
        self.txt_pts = tk.Text(t, height=5, width=36, bg=BG, fg=TXT, insertbackground=TXT, relief='flat', font=('Consolas', 9)); self.txt_pts.pack(fill='x', pady=3); self.txt_pts.insert('1.0', '-8,-8\n8,-8\n8,8\n-8,8')
        self.v['d_pl'] = tk.StringVar(value='xy'); self.v['d_m'] = tk.StringVar(value='somar'); f = tk.Frame(t, bg=CARD); f.pack(fill='x')
        self._opcao(t, 'Plano:', self.v['d_pl'], ('xy', 'xz', 'yz'), f); self._opcao(t, 'Modo:', self.v['d_m'], ('somar', 'subtrair'), f)
        f = tk.Frame(t, bg=CARD); f.pack(fill='x'); self.v['d_o'] = self._campo(t, 'Posição do plano', 0, 6, f); self.v['d_h'] = self._campo(t, 'Espessura', 2, 6, f)
        self._botoes(t, 'poligono')
        # --- rodape
        r = tk.Frame(esq, bg=CARD); r.pack(fill='x', padx=12, pady=(8, 2))
        a.botao(r, 'Desfazer', self.desfazer, AMARELO).pack(side='left'); a.botao(r, 'Voltar ao original', self.original, LINHA).pack(side='left', padx=6)
        a.botao(esq, 'SALVAR CÓPIA E PÔR NA MESA 3D', self.salvar, VERDE).pack(fill='x', padx=12, pady=6)
        self.l_msg = tk.Label(esq, text='Escolha uma peça para começar.', bg=CARD, fg=AMARELO, font=('Segoe UI', 9, 'bold'), wraplength=390, justify='left', anchor='w'); self.l_msg.pack(fill='x', padx=12, pady=(0, 8))
        # --- vista
        dir_ = a.card(corpo); dir_.pack(side='left', fill='both', expand=True)
        r = tk.Frame(dir_, bg=CARD); r.pack(fill='x', padx=8, pady=(8, 2))
        for nome, ch in (('De cima', 'topo'), ('Frente', 'frente'), ('Lado', 'lado'), ('3D', '3d')): a.botao(r, nome, lambda c=ch: self.vista_para(c), LINHA).pack(side='left', padx=2)
        tk.Label(r, text='arraste = girar · roda = zoom · botão direito arrastando = deslocar · vermelho = onde a ferramenta vai agir', bg=CARD, fg=DIM, font=('Segoe UI', 8)).pack(side='left', padx=10)
        self.vista = vista3d.Vista3D(dir_, self.mesa_ed, bed=(100.0, 100.0), width=700, height=600); self.vista.pack(fill='both', expand=True, padx=8, pady=8)

    # ---------------- estado ----------------
    def _msg(self, t, ok=True): self.l_msg.config(text=t, fg=VERDE if ok else VERM)

    def _atualizar(self):
        me = self.mesa_ed; me.pecas = []
        if self.s.mesh is not None:
            m = self.s.mesh; sz = m.bounds[1] - m.bounds[0]; B = float(max(60.0, np.ceil(max(sz[0], sz[1]) * 1.9 / 10) * 10))
            self.vista.bed = (B, B); c = (B / 2, B / 2)
            cor = self.s.cor_fixa or '#5AB0FF'; p = PecaEd(m, cor, c, True, self.s.nome); me.pecas.append(p)
            if self.s.fantasma is not None: me.pecas.append(PecaEd(self.s.fantasma, '#FF6B6B', c, False, 'ferramenta'))
            me.sel = p
            i = self.s.estado()
            self.l_info.config(text='%s\nTamanho %.1f × %.1f × %.1f mm · %d faces · %s\n%s' % (self.s.nome, *i['tamanho'], i['faces'], 'malha fechada' if i['fechada'] else 'COM BURACOS (não dá para cortar/juntar)', ('Passos: ' + ' → '.join(i['passos'])) if i['passos'] else 'Sem alterações ainda.'))
        else: self.l_info.config(text='Nenhuma peça aberta.')
        self.vista.redesenhar()

    def vista_para(self, nome):
        if self.s.mesh is None: return
        az, el = VISTAS[nome]; m = self.s.mesh; sz = m.bounds[1] - m.bounds[0]; B = self.vista.bed[0]; zc = float((m.bounds[0][2] + m.bounds[1][2]) / 2)
        self.vista.az, self.vista.el = az, el; self.vista.alvo = np.array([B / 2, B / 2, zc]); self.vista.dist = float(max(sz) * 2.6 + 40); self.vista.redesenhar()

    def _abrir_malha(self, mesh, nome, caminho, cor=None):
        self.s.abrir(mesh, nome, caminho, cor); i = self.s.estado()
        self.v['f_z'].set(round(i['centro'][2], 1)); self.v['m_z'].set(round(i['centro'][2], 1)); self.v['c_p'].set(round(i['centro'][2], 1))
        self._atualizar(); self.vista_para('3d')
        self._msg('Peça aberta. ' + ('' if i['fechada'] else 'ATENÇÃO: a malha tem buracos; para cortar/juntar formas ela precisa ser conserto antes.'), i['fechada'])

    # ---------------- abrir ----------------
    def pegar_da_mesa(self, idx=None):
        mesa = self.app.painel_mesa
        p = mesa.sel if idx is None else mesa.pecas[idx]
        if p is None: self._msg('Selecione uma peça na Mesa 3D primeiro.', False); return False
        m = ep.carregar(p.caminho); m.apply_scale(p.esc / 100.0)
        if p.rot: m.apply_transform(rotation_matrix(np.radians(p.rot), [0, 0, 1]))
        self._abrir_malha(m, p.nome, p.caminho, getattr(p, 'cor_fixa', None)); return True

    def abrir_arquivo(self, caminho=None):
        c = caminho or filedialog.askopenfilename(parent=self, filetypes=[('Modelo 3D', '*.stl *.3mf *.obj'), ('Todos', '*.*')])
        if not c: return False
        m = ep.carregar(c); self._abrir_malha(m, os.path.basename(c), c); return True

    # ---------------- parametros ----------------
    def _f(self, k): return float(self.v[k].get().replace(',', '.'))

    def _params(self, op):
        if op == 'furo': return dict(x=self._f('f_x'), y=self._f('f_y'), z=self._f('f_z'), diametro=self._f('f_d'), comprimento=self._f('f_l'), eixo=self.v['f_e'].get())
        if op == 'cortar': return dict(eixo=self.v['c_e'].get(), posicao=self._f('c_p'), manter=self.v['c_m'].get())
        if op == 'forma': return dict(tipo=self.v['m_t'].get(), modo=self.v['m_m'].get(), x=self._f('m_x'), y=self._f('m_y'), z=self._f('m_z'), a=self._f('m_a'), b=self._f('m_b'), c=self._f('m_c'), eixo=self.v['m_e'].get())
        if op == 'texto': return dict(txt=self.v['t_txt'].get(), tam=self._f('t_tam'), prof=self._f('t_prof'), modo=self.v['t_modo'].get(), face=self.v['t_face'].get(), u=self._f('t_u'), v=self._f('t_v'), giro=self._f('t_g'), fonte=self.v['t_fonte'].get())
        if op == 'poligono':
            pts = []
            for l in self.txt_pts.get('1.0', 'end').splitlines():
                l = l.strip().replace(';', ',')
                if l: a, b = [float(x) for x in l.replace(' ', ',').split(',') if x != ''][:2]; pts.append([a, b])
            return dict(pontos=pts, plano=self.v['d_pl'].get(), offset=self._f('d_o'), altura=self._f('d_h'), modo=self.v['d_m'].get())
        raise ValueError(op)

    def previa(self, op):
        try:
            self.s.aberta(); p = self._params(op); self.s.fantasma = self.s.ferramenta(op, p)
            self._atualizar(); self._msg('Em vermelho: onde a ferramenta vai agir. Ajuste os números e clique APLICAR.')
        except Exception as e: self._msg(str(e), False)

    def executar(self, op, p):
        s = self.s
        if op == 'furo': s.furo(p['x'], p['y'], p['z'], p['diametro'], p.get('comprimento', 0), p.get('eixo', 'z'))
        elif op == 'cortar': s.cortar(p['eixo'], p['posicao'], p.get('manter', 'menor'))
        elif op == 'forma': s.forma(p['tipo'], p['modo'], p['x'], p['y'], p['z'], p['a'], p.get('b'), p.get('c'), p.get('eixo', 'z'))
        elif op == 'texto': s.texto(p['txt'], p['tam'], p['prof'], p['modo'], p['face'], p.get('u', 0), p.get('v', 0), p.get('giro', 0), p.get('fonte', 'Arial'))
        elif op == 'poligono': s.poligono(p['pontos'], p['plano'], p.get('offset', 0), p['altura'], p['modo'])
        else: raise ep.ErroEdicao('operacao desconhecida: ' + op)

    def aplicar(self, op):
        try:
            self.s.aberta(); self._cursor('watch')
            self.executar(op, self._params(op)); self._atualizar(); self._msg('Feito. Use "Desfazer" se não gostou.')
        except Exception as e: self._msg(str(e), False)
        finally: self._cursor('')

    def _cursor(self, c):
        try: self.app.config(cursor=c); self.update_idletasks()
        except Exception: pass

    def desfazer(self):
        try: self.s.desfazer(); self._atualizar(); self._msg('Desfeito.')
        except Exception as e: self._msg(str(e), False)

    def original(self):
        try:
            self.s.voltar_original(); self._atualizar(); self._msg('Voltou ao original.')
        except Exception as e: self._msg(str(e), False)

    def salvar(self, adicionar=True):
        try:
            m = self.s.aberta()
            if not self.s.passos: raise ep.ErroEdicao('Ainda não há alterações para salvar.')
            c = ep.salvar(m, self.pasta, self.s.nome)
            if adicionar:
                pc = self.app.painel_mesa.add_arquivo(c, cor=self.s.cor_fixa); self.app.aba('Mesa 3D')
            self._msg('Salvo como cópia: %s (o original não foi mexido).' % c); return c
        except Exception as e: self._msg(str(e), False); return None

    # ---------------- API / MCP ----------------
    def imagem_png(self, vista='3d', largura=900, altura=700, az=None, el=None):
        m = self.s.aberta(); sz = m.bounds[1] - m.bounds[0]; B = self.vista.bed[0]; zc = float((m.bounds[0][2] + m.bounds[1][2]) / 2)
        a0, e0 = VISTAS.get(vista, VISTAS['3d'])
        img = self.vista.render(largura, altura, az if az is not None else a0, el if el is not None else e0, float(max(sz) * 2.6 + 40), (B / 2, B / 2, zc), esc=1.5)
        b = io.BytesIO(); img.save(b, 'PNG'); return b.getvalue()

    def api(self, d):
        """Entrada unica da API: {'acao': 'abrir'|'estado'|'furo'|'cortar'|'forma'|'texto'|'poligono'|'desfazer'|'original'|'salvar'|'imagem', ...parametros}"""
        ac = str(d.get('acao', 'estado')); s = self.s
        try:
            if ac == 'abrir':
                if d.get('id') is not None:
                    i = int(d['id']) - 1
                    if not (0 <= i < len(self.app.painel_mesa.pecas)): return dict(ok=False, erro='nao existe a peca %s na Mesa' % d['id'])
                    self.pegar_da_mesa(i)
                elif d.get('caminho'):
                    c = str(d['caminho'])
                    if not os.path.isfile(c): return dict(ok=False, erro='arquivo nao existe')
                    self.abrir_arquivo(c)
                else: return dict(ok=False, erro="informe 'id' (peca da Mesa) ou 'caminho' (STL)")
            elif ac == 'estado': pass
            elif ac in ('furo', 'cortar', 'forma', 'texto', 'poligono'):
                p = {k: v for k, v in d.items() if k not in ('acao',)}
                if ac == 'furo': need = ('x', 'y', 'z', 'diametro')
                elif ac == 'cortar': need = ('eixo', 'posicao')
                elif ac == 'forma': need = ('tipo', 'modo', 'x', 'y', 'z', 'a')
                elif ac == 'texto': need = ('txt', 'tam', 'prof', 'modo', 'face')
                else: need = ('pontos', 'plano', 'altura', 'modo')
                falta = [k for k in need if k not in p]
                if falta: return dict(ok=False, erro='faltam parametros: ' + ', '.join(falta))
                for k in p:
                    if k not in ('txt', 'modo', 'face', 'fonte', 'eixo', 'plano', 'tipo', 'manter', 'pontos'): p[k] = float(p[k])
                self.executar(ac, p)
            elif ac == 'desfazer': s.desfazer()
            elif ac == 'original': s.voltar_original()
            elif ac == 'salvar':
                c = self.salvar(bool(d.get('adicionar_na_mesa', True)))
                if not c: return dict(ok=False, erro=self.l_msg.cget('text'))
                return dict(ok=True, arquivo=c, **s.estado())
            elif ac == 'imagem':
                png = self.imagem_png(str(d.get('vista', '3d')), int(d.get('largura', 900)), int(d.get('altura', 700)), d.get('az'), d.get('el'))
                return dict(ok=True, png_base64=base64.b64encode(png).decode(), **s.estado())
            else: return dict(ok=False, erro='acao desconhecida: ' + ac)
            self._atualizar()
            if ac == 'abrir': self.vista_para('3d')
            return dict(ok=True, **s.estado())
        except ep.ErroEdicao as e: return dict(ok=False, erro=str(e))
        except Exception as e: return dict(ok=False, erro='%s: %s' % (type(e).__name__, e))
