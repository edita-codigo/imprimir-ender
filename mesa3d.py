"""Mesa 3D da Ender-3 V3 SE: vista 3D girável + mesa vista de cima (arrastar peças), várias peças/cópias na mesma impressão.
- Mesa 220 x 220 x 250 mm. Respeita margem e espaço entre peças (por causa do brim do ABS).
- Exporta tudo num STL só (mesa_atual.stl, coordenadas relativas ao centro da mesa) e o programa fatia como uma impressão só.
"""
import os, math, tempfile, json, threading, re, time
import numpy as np
import tkinter as tk
from tkinter import ttk,  filedialog, messagebox, simpledialog
import trimesh
from scipy.spatial import ConvexHull
import vista3d
import importar_3mf

import perfil as _perfil
_m = _perfil.carregar()['mesa']; BED_X, BED_Y, BED_Z = float(_m['x']), float(_m['y']), float(_m['z'])      # tamanho da mesa: perfil_impressora.json
BG, CARD, TXT, DIM, VERDE, LARANJA, AZUL, VERM, AMARELO = '#0D1117', '#151B24', '#EAF0F8', '#93A0B5', '#38D39F', '#FF8A3D', '#5AB0FF', '#FF6B6B', '#F7C948'
CORES = ['#5AB0FF', '#38D39F', '#FF8A3D', '#B794F6', '#F7C948', '#3DD6E8', '#FF6B9D', '#9BDEAC']
SUPORTES = ['Sem suporte', 'Suporte só apoiado na mesa', 'Suporte em tudo (também sobre a peça)']
ADESOES = ['Brim (borda larga - padrão ABS)', 'Só uma linha de contorno (skirt)', 'Raft (base inteira embaixo)']
COR_TIPO = {'WALL-OUTER': '#ff7043', 'WALL-INNER': '#66bb6a', 'SKIN': '#ffd54f', 'FILL': '#8d6e63', 'SUPPORT': '#26c6da', 'SUPPORT-INTERFACE': '#80deea',
            'SKIRT': '#b0bec5', 'PRIME-TOWER': '#ab47bc'}
ESC = 1.8      # pixels por mm na vista de cima
PAD = 14


def _rot(graus):
    a = math.radians(graus); c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s], [s, c]])


def _hull(xy):
    try:
        h = ConvexHull(xy); return xy[h.vertices]
    except Exception:
        x0, y0 = xy.min(0); x1, y1 = xy.max(0)
        return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])


def _separadas(A, B, gap):
    """Poligonos convexos A e B (Nx2): True se ha pelo menos 'gap' mm entre eles (teste de eixo separador, conservador)."""
    for ax in (np.array([1.0, 0.0]), np.array([0.0, 1.0])):          # tambem os eixos X e Y (o 'organizar' separa pelas caixas, nao pelas arestas)
        a_ = A @ ax; b_ = B @ ax
        if max(b_.min() - a_.max(), a_.min() - b_.max()) >= gap - 1e-4: return True
    for P in (A, B):
        n = len(P)
        for i in range(n):
            e = P[(i + 1) % n] - P[i]
            L = math.hypot(*e)
            if L < 1e-9: continue
            ax = np.array([-e[1], e[0]]) / L
            a = A @ ax; b = B @ ax
            if max(b.min() - a.max(), a.min() - b.max()) >= gap - 1e-4: return True      # tolerancia: 'organizar' encosta no espaco exato e o arredondamento dava 13.99999 < 14
    return False


class Peca:
    def __init__(self, caminho, mesh_prev, hull0, altura0, cor, rot=0.0, esc=100.0):
        self.caminho = caminho; self.nome = os.path.basename(caminho)
        self.prev = mesh_prev       # malha leve (centrada, base em z=0) so para desenhar
        self.hull0 = hull0          # contorno (cima) da malha cheia centrada
        self.h0 = altura0
        self.cor = cor; self.rot = rot; self.esc = esc
        self.x = BED_X / 2; self.y = BED_Y / 2
        self.ok = True; self.motivo = ''

    # contorno atual (coordenadas da mesa 0..220), com o centro do retangulo envolvente em (x, y)
    def contorno(self, rot=None):
        r = self.rot if rot is None else rot
        p = (self.hull0 * (self.esc / 100.0)) @ _rot(r).T
        mn, mx = p.min(0), p.max(0)
        return p - (mn + mx) / 2 + np.array([self.x, self.y])

    def tamanho(self, rot=None):
        p = self.contorno(rot); mn, mx = p.min(0), p.max(0)
        return float(mx[0] - mn[0]), float(mx[1] - mn[1])

    @property
    def altura(self): return self.h0 * self.esc / 100.0

    @property
    def grupo(self):
        """Pecas vindas do MESMO 3MF (pasta importados/<nome>/) formam um conjunto montado: podem ficar sobrepostas e mostram a cor real."""
        d = os.path.dirname(self.caminho).replace('\\', '/')
        return d if 'importados' in d.split('/') else None

    def vertices_mesa(self, V):
        """V = vertices da malha centrada (z>=0). Devolve em coordenadas da mesa (x,y 0..220)."""
        f = self.esc / 100.0
        xy = (V[:, :2] * f) @ _rot(self.rot).T
        base = (self.hull0 * f) @ _rot(self.rot).T
        c = (base.min(0) + base.max(0)) / 2
        xy = xy - c + np.array([self.x, self.y])
        return np.column_stack([xy, V[:, 2] * f])


def carregar_malha(caminho):
    m = trimesh.load(caminho, force='mesh')
    if isinstance(m, trimesh.Scene): m = m.dump(concatenate=True)
    b = m.bounds
    m.apply_translation([-(b[0][0] + b[1][0]) / 2, -(b[0][1] + b[1][1]) / 2, -b[0][2]])
    hull0 = _hull(np.asarray(m.vertices)[:, :2])
    altura = float(m.bounds[1][2])
    prev = m
    if len(m.faces) > 9000:
        try: prev = m.simplify_quadric_decimation(face_count=9000)
        except Exception:
            try: prev = m.simplify_quadric_decimation(percent=1 - 9000 / len(m.faces))
            except Exception:
                V, Fc = vista3d.simplificar(m, 9000)       # sem 'fast_simplification': agrupa vertices (a peca continua inteira, sem buracos)
                prev = trimesh.Trimesh(vertices=V, faces=Fc, process=False)
    return prev, hull0, altura


class Mesa(tk.Frame):
    """Aba 'Mesa 3D' dentro do programa (nao e outra janela)."""
    def __init__(self, pai, app):
        super().__init__(pai, bg=BG)
        self.app = app; self.p = app.preset_atual()
        self.pecas = []; self.sel = None; self.arrasto = None; self.ncor = 0; self.estoque = []; self._rot_cor = {}
        self._pode_salvar = False      # so grava a mesa depois que a aba abriu e restaurou a mesa guardada (antes, o programa gravava a mesa VAZIA ao abrir)
        self.modo = 'modelo'; self.camadas = None; self.layout_json = os.path.join(app.pasta, 'mesa_layout.json')
        self._xbtn = None; self._calc_id = None; self._calc_rodando = False; self._calc_sujo = False; self._res = None
        self.gcode_prev = os.path.join(app.pasta, 'mesa_prev_abs.gcode'); self.tempo_total = None; self.tempo_valido = False
        brim = self.p.get('brim', 0)
        self.var_gap = tk.DoubleVar(value=round(2 * brim * 0.4 + 2, 1) if brim else 5.0)
        self.var_mar = tk.DoubleVar(value=round(brim * 0.4 + 2, 1) if brim else 3.0)
        self._montar()
        self.winfo_toplevel().bind('<Delete>', self._tecla_del, add='+'); self.winfo_toplevel().bind('<BackSpace>', self._tecla_del, add='+')
        self.redesenhar(so2d=True)      # so2d: NAO salva (antes gravava a mesa vazia por cima da mesa guardada ao abrir o programa)
        self.after(400, self._poll); self.after(1500, self._restaurar_ao_abrir)

    def _restaurar_ao_abrir(self):
        """Recupera a mesa guardada logo que o programa abre (antes so recuperava quando alguem abria a aba Mesa 3D; a API/celular/IA via mesa vazia)."""
        try:
            if not self.pecas and not self._pode_salvar:
                brim = self.app.preset_atual().get('brim', 0)
                self.var_gap.set(round(2 * brim * 0.4 + 2, 1) if brim else 5.0); self.var_mar.set(round(brim * 0.4 + 2, 1) if brim else 3.0)
                self.restaurar()
            self._pode_salvar = True; self.redesenhar(so2d=True)
        except Exception: pass

    def mostrar(self):
        """Chamado toda vez que a aba aparece: se a mesa esta vazia, traz o STL que ja estava carregado."""
        brim = self.app.preset_atual().get('brim', 0)
        ini = getattr(self.app, 'arq_origem', '') or ''
        stl_escolhido = ini.lower().endswith('.stl') and os.path.isfile(ini) and not os.path.basename(ini).startswith('mesa_')
        if stl_escolhido and ini != getattr(self, '_origem_vista', None):
            # o arquivo escolhido na aba Imprimir e o que aparece aqui (sem precisar adicionar de novo)
            self._origem_vista = ini
            self.var_gap.set(round(2 * brim * 0.4 + 2, 1) if brim else 5.0); self.var_mar.set(round(brim * 0.4 + 2, 1) if brim else 3.0)
            self.pecas.clear(); self.sel = None; self.add_arquivo(ini)
        elif not self.pecas:
            self.var_gap.set(round(2 * brim * 0.4 + 2, 1) if brim else 5.0); self.var_mar.set(round(brim * 0.4 + 2, 1) if brim else 3.0)
            self.restaurar()
        self._pode_salvar = True
        self.redesenhar()
        if not self.pecas and ini.lower().endswith(('.gcode', '.gco')):
            self.lstatus.config(text='O arquivo escolhido é um G-code pronto (%s): a Mesa 3D mostra só STL. Escolha o STL na aba Imprimir.' % os.path.basename(ini), fg=AMARELO)

    # ---------- guardar / restaurar a mesa (cada peca separada) ----------
    def salvar_layout(self):
        if not self._pode_salvar: return
        try:
            d = [dict(caminho=p.caminho, x=p.x, y=p.y, rot=p.rot, esc=p.esc, cor=getattr(p, 'cor_fixa', None), nome=p.nome) for p in self.pecas]
            e = [dict(caminho=p.caminho, x=p.x, y=p.y, rot=p.rot, esc=p.esc, cor=getattr(p, 'cor_fixa', None), nome=p.nome) for p in self.estoque]
            json.dump(dict(pecas=d, estoque=e, gap=self.var_gap.get(), mar=self.var_mar.get()), open(self.layout_json, 'w', encoding='utf-8'))
        except Exception: pass

    def restaurar(self):
        try: d = json.load(open(self.layout_json, encoding='utf-8'))
        except Exception: return False
        cache = {}; n = 0

        def refazer(it):
            c = it.get('caminho', '')
            if not os.path.isfile(c) or os.path.basename(c).startswith('mesa_'): return None
            try:
                if c not in cache: cache[c] = carregar_malha(c)
                prev, hull0, alt = cache[c]
            except Exception: return None
            cf = it.get('cor')
            pc = Peca(c, prev, hull0, alt, cf or CORES[self.ncor % len(CORES)], rot=it.get('rot', 0), esc=it.get('esc', 100)); self.ncor += 1
            if cf: pc.cor_fixa = cf
            if it.get('nome'): pc.nome = it['nome']
            pc.x, pc.y = it.get('x', 110), it.get('y', 110); return pc
        for it in d.get('pecas', []):
            pc = refazer(it)
            if pc: self.pecas.append(pc); n += 1
        for it in d.get('estoque', []):
            pc = refazer(it)
            if pc: self.estoque.append(pc)
        if n:
            self.sel = self.pecas[0]
            try: self.var_gap.set(d.get('gap', self.var_gap.get())); self.var_mar.set(d.get('mar', self.var_mar.get()))
            except Exception: pass
        return n > 0

    # ---------- interface ----------
    def botao(self, pai, texto, cmd, cor, **kw):
        return tk.Button(pai, text=texto, command=cmd, bg=cor, fg=TXT if cor in ('#263041', '#33405A') else '#0D1117', activebackground=cor, relief='flat', bd=0, cursor='hand2', font=('Segoe UI', 10, 'bold'), padx=10, pady=5, **kw)

    def _montar(self):
        topo = tk.Frame(self, bg=BG); topo.pack(fill='x', padx=12, pady=(8, 2))
        self.botao(topo, '+ Adicionar STL...', self.add_dialogo, AZUL).pack(side='left')
        self.botao(topo, 'Importar 3MF (com cores)...', self.importar_3mf_dialogo, '#B794F6').pack(side='left', padx=(10, 0))
        self.botao(topo, 'COPIAR PEÇA', self.copiar_uma, VERDE).pack(side='left', padx=(10, 4))
        self.botao(topo, 'Fazer N cópias...', self.copias, '#263041').pack(side='left', padx=4)
        self.botao(topo, 'ENCHER A MESA', self.encher, LARANJA).pack(side='left', padx=4)
        self.botao(topo, 'FATIAR E VOLTAR PARA IMPRIMIR  →', self.usar, VERDE).pack(side='right')
        topo2 = tk.Frame(self, bg=BG); topo2.pack(fill='x', padx=12, pady=(2, 0))
        self.botao(topo2, 'Girar 90°', lambda: self.girar(90), '#263041').pack(side='left')
        self.botao(topo2, 'Organizar tudo', self.organizar, AMARELO).pack(side='left', padx=4)
        self.botao(topo2, 'APAGAR PEÇA SELECIONADA', self.remover, VERM).pack(side='left', padx=4)
        self.botao(topo2, 'Limpar mesa', self.limpar, '#263041').pack(side='left', padx=4)
        cfg = tk.Frame(self, bg=BG); cfg.pack(fill='x', padx=12)
        for txt, var in (('Espaço entre peças (mm):', self.var_gap), ('Margem da borda (mm):', self.var_mar)):
            tk.Label(cfg, text=txt, bg=BG, fg=DIM, font=('Segoe UI', 9)).pack(side='left')
            tk.Spinbox(cfg, from_=0, to=50, increment=0.5, width=5, textvariable=var, command=self.redesenhar, bg='#263041', fg=TXT, buttonbackground='#263041', relief='flat').pack(side='left', padx=(4, 14))
        self.var_gap.trace_add('write', lambda *a: self.after(50, self.redesenhar)); self.var_mar.trace_add('write', lambda *a: self.after(50, self.redesenhar))
        cfg2 = tk.Frame(self, bg=BG); cfg2.pack(fill='x', padx=12, pady=(4, 0))
        app = self.app
        tk.Label(cfg2, text='Suporte (base para partes no ar):', bg=BG, fg=DIM, font=('Segoe UI', 9)).pack(side='left')
        om = tk.OptionMenu(cfg2, app.v_sup, *SUPORTES); om.config(bg='#263041', fg=TXT, activebackground='#33405A', highlightthickness=0, bd=0, font=('Segoe UI', 9)); om.pack(side='left', padx=(4, 6))
        tk.Label(cfg2, text='ângulo:', bg=BG, fg=DIM, font=('Segoe UI', 9)).pack(side='left')
        tk.Spinbox(cfg2, from_=20, to=80, increment=5, width=4, textvariable=app.v_ang, bg='#263041', fg=TXT, buttonbackground='#263041', relief='flat').pack(side='left', padx=(4, 14))
        tk.Button(cfg2, text='Ajustes do suporte...', command=lambda: __import__('suporte').abrir(app), bg='#263041', fg=TXT, relief='flat', bd=0, cursor='hand2', font=('Segoe UI', 9), padx=8, pady=2).pack(side='left', padx=(0, 14))
        tk.Label(cfg2, text='Aderência à mesa:', bg=BG, fg=DIM, font=('Segoe UI', 9)).pack(side='left')
        om2 = tk.OptionMenu(cfg2, app.v_ades, *ADESOES); om2.config(bg='#263041', fg=TXT, activebackground='#33405A', highlightthickness=0, bd=0, font=('Segoe UI', 9)); om2.pack(side='left', padx=4)
        self.bcam = self.botao(cfg2, 'VER CAMADAS (como vai imprimir)', self.alternar_camadas, AZUL); self.bcam.pack(side='right')
        cfg3 = tk.Frame(self, bg=BG); cfg3.pack(fill='x', padx=12, pady=(4, 0))
        tk.Label(cfg3, text='Imprimir só uma cor:', bg=BG, fg=DIM, font=('Segoe UI', 9)).pack(side='left')
        self.v_cor_sel = tk.StringVar(value='Todas')
        self.cb_cor = ttk.Combobox(cfg3, textvariable=self.v_cor_sel, values=['Todas'], state='readonly', width=22); self.cb_cor.pack(side='left', padx=6)
        self.cb_cor.bind('<<ComboboxSelected>>', lambda e: self.escolher_cor())
        self.l_cor = tk.Label(cfg3, text='', bg=BG, fg=DIM, font=('Segoe UI', 9)); self.l_cor.pack(side='left', padx=6)
        self.ltempo = tk.Label(self, text='', bg=BG, fg=AMARELO, font=('Segoe UI', 12, 'bold'), anchor='w'); self.ltempo.pack(fill='x', padx=14, pady=(4, 0))
        self.fcam = tk.Frame(self, bg=BG)       # barra de camadas (so aparece no modo camadas)
        tk.Label(self.fcam, text='Camada:', bg=BG, fg=TXT, font=('Segoe UI', 10, 'bold')).pack(side='left')
        self.v_cam = tk.IntVar(value=1)
        self.esc_cam = tk.Scale(self.fcam, from_=1, to=2, orient='horizontal', variable=self.v_cam, command=lambda v: self.desenhar_camadas(), bg=BG, fg=TXT, troughcolor='#263041', highlightthickness=0, length=500)
        self.esc_cam.pack(side='left', padx=8)
        self.lcam = tk.Label(self.fcam, text='', bg=BG, fg=DIM, font=('Segoe UI', 9)); self.lcam.pack(side='left')
        self.lleg = tk.Label(self.fcam, text='  laranja=parede de fora  verde=parede de dentro  amarelo=topo/base  marrom=enchimento  AZUL-CLARO=SUPORTE', bg=BG, fg=DIM, font=('Segoe UI', 8)); self.lleg.pack(side='left', padx=10)
        self.lstatus = tk.Label(self, text='', bg=BG, fg=VERDE, font=('Segoe UI', 11, 'bold'), anchor='w', justify='left', wraplength=1200); self.lstatus.pack(fill='x', padx=14, pady=(6, 2))
        corpo = tk.Frame(self, bg=BG); corpo.pack(fill='both', expand=True, padx=12, pady=4)
        # esquerda: lista + campos da peca
        esq = tk.Frame(corpo, bg=CARD, width=260); esq.pack(side='left', fill='y'); esq.pack_propagate(False)
        tk.Label(esq, text='PEÇAS NA MESA', bg=CARD, fg=DIM, font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=10, pady=(8, 2))
        self.lista = tk.Listbox(esq, bg='#0D1117', fg=TXT, selectbackground='#2f6fb5', activestyle='none', bd=0, highlightthickness=0, font=('Segoe UI', 10), height=6, exportselection=False)
        self.lista.pack(fill='x', padx=8); self.lista.bind('<<ListboxSelect>>', self._lista_sel)
        self.campos = tk.Frame(esq, bg=CARD); self.campos.pack(fill='x', padx=8, pady=8)
        self.v_x, self.v_y, self.v_rot, self.v_esc = tk.StringVar(), tk.StringVar(), tk.StringVar(), tk.StringVar()
        for r, (t, v) in enumerate((('X (mm)', self.v_x), ('Y (mm)', self.v_y), ('Girar (°)', self.v_rot), ('Escala (%)', self.v_esc))):
            tk.Label(self.campos, text=t, bg=CARD, fg=DIM, font=('Segoe UI', 9)).grid(row=r, column=0, sticky='w', pady=2)
            e = tk.Entry(self.campos, textvariable=v, width=8, bg='#263041', fg=TXT, insertbackground=TXT, relief='flat'); e.grid(row=r, column=1, padx=6)
            e.bind('<Return>', self._aplicar_campos); e.bind('<FocusOut>', self._aplicar_campos)
        self.linfo = tk.Label(esq, text='', bg=CARD, fg=TXT, font=('Segoe UI', 9), justify='left', anchor='w', wraplength=240); self.linfo.pack(fill='x', padx=10)
        tk.Label(esq, text='COMO MEXER (na vista 3D)\n• Clique na peça e arraste = mover.\n• Ctrl + arrastar a peça = girar.\n• Arraste no vazio = girar a câmera.\n• Botão direito arrastando = deslocar; roda = zoom.\n• Botão direito (clique) = menu.\n• ✕ vermelho ou Delete = apaga.\n• Ctrl+D = copia; Q/E = gira 15°; setas = 1 mm.\n• Duplo clique no vazio = leva a peça.\nVermelho = não cabe ou está colada.', bg=CARD, fg=DIM, font=('Segoe UI', 8), justify='left', wraplength=240).pack(side='bottom', anchor='w', padx=10, pady=8)
        # direita: a vista 3D de verdade (clicar na peca, arrastar, girar a camera, zoom)
        dir_ = tk.Frame(corpo, bg=CARD); dir_.pack(side='left', fill='both', expand=True, padx=(8, 0))
        bar = tk.Frame(dir_, bg=CARD); bar.pack(fill='x', padx=8, pady=(6, 2))
        tk.Label(bar, text='MESA 3D', bg=CARD, fg=DIM, font=('Segoe UI', 10, 'bold')).pack(side='left')
        for t, v in (('De cima (1)', 'topo'), ('Frente (2)', 'frente'), ('Lado (3)', 'lado'), ('3D (4)', '3d')):
            tk.Button(bar, text=t, command=lambda v=v: self.vista.vista(v), bg='#263041', fg=TXT, relief='flat', bd=0, cursor='hand2', font=('Segoe UI', 9), padx=8, pady=2).pack(side='left', padx=(8 if v == 'topo' else 3, 0))
        self.vista = vista3d.Vista3D(dir_, self, bed=(BED_X, BED_Y), width=760, height=620)
        self.vista.pack(fill='both', expand=True, padx=6, pady=(0, 6))

    # ---------- pecas ----------
    def add_dialogo(self):
        for a in filedialog.askopenfilenames(parent=self, initialdir=self.app.pasta, filetypes=[('Modelo 3D', '*.stl *.3mf'), ('Todos', '*.*')]):
            if a.lower().endswith('.3mf'): self.importar_3mf(a)
            else: self.add_arquivo(a)

    # ---------- 3MF com cores ----------
    def importar_3mf_dialogo(self):
        a = filedialog.askopenfilename(parent=self, title='Escolha o arquivo 3MF', filetypes=[('3MF', '*.3mf'), ('Todos', '*.*')])
        if a: self.importar_3mf(a)

    def importar_3mf(self, caminho, organizar=True):
        """Le o 3MF, grava cada parte como STL em importados/<nome>/ e poe todas na mesa, cada uma com a cor do arquivo."""
        self.lstatus.config(text='Lendo o 3MF %s ...' % os.path.basename(caminho), fg=AMARELO); self.update_idletasks()
        try:
            partes, resumo = importar_3mf.ler(caminho)
            pasta = os.path.join(self.app.pasta, 'importados', re.sub(r'[^\w\-]+', '_', os.path.splitext(os.path.basename(caminho))[0])[:40])
            itens = importar_3mf.exportar_partes(partes, pasta, caminho)
        except Exception as e:
            messagebox.showerror('3MF', 'Não consegui ler esse 3MF:\n%s' % e, parent=self); return None
        n = 0; pares = []
        for k, it in enumerate(itens):
            p = self.add_arquivo(it['stl'], cor=it['cor'], nome=it['nome'], autoajustar=False)
            if p is not None: n += 1; pares.append((p, partes[k].malha.bounds))
        # as peças do 3MF ficam MONTADAS como no arquivo (posição original) e o conjunto todo é reduzido por igual se for maior que a mesa
        aviso = ''
        if pares:
            mn = np.min([b[0] for _, b in pares], axis=0); mx = np.max([b[1] for _, b in pares], axis=0); C = (mn + mx) / 2
            esc = self._escala_que_cabe(mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]); f = esc / 100.0
            for p, b in pares:
                c = (b[0] + b[1]) / 2
                p.rot = 0.0; p.esc = esc; p.x = BED_X / 2 + f * (c[0] - C[0]); p.y = BED_Y / 2 + f * (c[1] - C[1])
            if esc < 100.0: aviso = ' Era maior que a mesa: reduzi tudo para %.1f%% (mesma proporção em todas as peças).' % esc
        elif organizar: self.organizar(silencioso=True)
        self.redesenhar()
        self.lstatus.config(text='3MF lido: %s.%s Use "Imprimir só uma cor" para imprimir uma cor de cada vez.' % (resumo, aviso), fg=VERDE)
        return dict(ok=True, resumo=resumo, partes=[dict(nome=i['nome'], cor=i['cor_nome'], hex=i['cor']) for i in itens], adicionadas=n)

    def cor_de(self, p):
        return importar_3mf._nome_cor(p.cor_fixa) if getattr(p, 'cor_fixa', None) else 'sem cor'

    def cores_presentes(self):
        cont = {}
        for p in list(self.pecas) + list(self.estoque):
            if getattr(p, 'cor_fixa', None): c = self.cor_de(p); cont[c] = cont.get(c, 0) + 1
        return cont

    def atualizar_cores(self):
        cont = self.cores_presentes()
        self.cb_cor.config(values=['Todas'] + ['%s (%d)' % (c, n) for c, n in cont.items()])
        if self.estoque: self.l_cor.config(text='%d peça(s) de outras cores guardadas' % len(self.estoque), fg=AMARELO)
        else: self.l_cor.config(text='', fg=DIM)
        if not self.estoque: self.v_cor_sel.set('Todas')

    def escolher_cor(self):
        v = self.v_cor_sel.get()
        self.so_cor(None if v.startswith('Todas') else v.rsplit(' (', 1)[0])

    def so_cor(self, nome_cor):
        """Deixa na mesa só as peças dessa cor (as outras ficam guardadas); None = traz tudo de volta."""
        todas = list(self.pecas) + list(self.estoque)
        if nome_cor is None: manter, guardar = todas, []
        else:
            manter = [p for p in todas if self.cor_de(p) == nome_cor]
            guardar = [p for p in todas if self.cor_de(p) != nome_cor]
            if not manter: return False
        self.pecas = manter; self.estoque = guardar; self.sel = self.pecas[0] if self.pecas else None
        self.organizar(silencioso=True); self.redesenhar(); return True

    def _escala_que_cabe(self, larg, prof, alt):
        """Escala (%) maxima <= 100 para um objeto larg x prof x alt (mm) caber na mesa (com a margem) e na altura. So diminui, nunca aumenta."""
        mar = self.var_mar.get()
        s = min(1.0, (BED_X - 2 * mar) / max(larg, 1e-6), (BED_Y - 2 * mar) / max(prof, 1e-6), BED_Z / max(alt, 1e-6))
        return 100.0 if s >= 1.0 else math.floor(s * 0.995 * 1000) / 10.0       # arredonda p/ baixo (0,5% de folga) p/ nunca passar da borda

    def add_arquivo(self, caminho, copia_de=None, so_se_couber=False, cor=None, nome=None, autoajustar=True):
        if os.path.basename(caminho).startswith('mesa_'):
            messagebox.showinfo('Mesa 3D', 'Esse arquivo (%s) é a mesa JÁ MONTADA pelo programa, com todas as peças juntas.\nAdicione o STL original da peça.' % os.path.basename(caminho), parent=self); return None
        try:
            if copia_de is not None:
                prev, hull0, alt = copia_de.prev, copia_de.hull0, copia_de.h0
            else:
                self.lstatus.config(text='Lendo %s ...' % os.path.basename(caminho), fg=AMARELO); self.update_idletasks()
                prev, hull0, alt = carregar_malha(caminho)
        except Exception as e:
            messagebox.showerror('Mesa 3D', 'Não consegui abrir %s:\n%s' % (os.path.basename(caminho), e), parent=self); return None
        pc = Peca(caminho, prev, hull0, alt, cor or CORES[self.ncor % len(CORES)])
        if cor: pc.cor_fixa = cor
        if nome: pc.nome = nome
        if copia_de is not None: pc.rot, pc.esc = copia_de.rot, copia_de.esc; pc.cor_fixa = getattr(copia_de, 'cor_fixa', None); pc.cor = copia_de.cor if pc.cor_fixa else pc.cor
        self.ncor += 1
        aviso = None
        if copia_de is None and autoajustar:       # arquivo maior que a mesa: so diminui a porcentagem (o arquivo nao e alterado)
            w, h = pc.tamanho(); e = self._escala_que_cabe(w, h, pc.altura)
            if e < 100.0: pc.esc = e; aviso = 'Arquivo maior que a mesa: reduzi para %.1f%% para caber (o arquivo original não foi alterado).' % e
        self.pecas.append(pc)
        if not self._lugar_livre(pc) and so_se_couber:
            self.pecas.remove(pc); return None
        self.sel = pc
        self.redesenhar()
        if aviso: self.lstatus.config(text=aviso, fg=AMARELO)
        return pc

    def _lugar_livre(self, pc):
        """Primeiro lugar livre (varre a mesa); se nao achar, tenta girado 90°; se nao cabe deixa no centro (ficara vermelho)."""
        gap, mar = self.var_gap.get(), self.var_mar.get()
        outras = [o for o in self.pecas if o is not pc]
        for rot in (pc.rot, pc.rot + 90):
            w, h = pc.tamanho(rot)
            x = mar + w / 2
            while x <= BED_X - mar - w / 2 + 1e-6:
                y = mar + h / 2
                while y <= BED_Y - mar - h / 2 + 1e-6:
                    pc.x, pc.y, pc.rot = x, y, rot
                    if all(_separadas(pc.contorno(), o.contorno(), gap) for o in outras): return True
                    y += 4
                x += 4
        pc.x, pc.y = BED_X / 2, BED_Y / 2
        return False

    def copiar_uma(self):
        if not self.sel:
            if self.pecas: self.sel = self.pecas[-1]
            else: messagebox.showinfo('Copiar', 'Adicione uma peça primeiro (botão + Adicionar STL).', parent=self); return
        base = self.sel
        novo = self.add_arquivo(base.caminho, copia_de=base, so_se_couber=True)
        if novo is None: messagebox.showinfo('Copiar', 'Não cabe mais uma cópia nessa mesa (com o espaço entre peças atual).\nTente girar as peças, diminuir o espaço entre elas ou usar "Organizar tudo".', parent=self)
        else: self.lstatus.config(text='Cópia criada (peça %d). Arraste para o lugar que quiser.' % len(self.pecas), fg=VERDE)

    def encher(self):
        if not self.sel: messagebox.showinfo('Encher a mesa', 'Selecione (ou adicione) uma peça primeiro.', parent=self); return
        base = self.sel; n = 0
        while n < 60:
            if self.add_arquivo(base.caminho, copia_de=base, so_se_couber=True) is not None: n += 1; continue
            # sem lugar livre pelo metodo simples: tenta reorganizar tudo em fileiras (as vezes cabe mais uma)
            novo = self.add_arquivo(base.caminho, copia_de=base)
            if novo is not None and self.organizar(silencioso=True): n += 1; continue
            if novo in self.pecas: self.pecas.remove(novo)
            break
        self.sel = base; self.redesenhar()
        self.lstatus.config(text='Pronto: %d cópia(s) adicionada(s); agora são %d peças na mesa.' % (n, len(self.pecas)), fg=VERDE)

    def _peca_em(self, x, y):
        """Peca debaixo do ponto (x, y) da mesa (de cima)."""
        from matplotlib.path import Path as MPath
        for p in reversed(self.pecas):
            if MPath(p.contorno()).contains_point((x, y)): return p
        return None

    def _tecla_del(self, e=None):
        if not self.winfo_ismapped() or self.modo != 'modelo': return
        if isinstance(self.focus_get(), (tk.Entry, tk.Spinbox)): return
        self.remover()

    def menu_direito(self, ev):
        """Clique direito na vista 3D (ev = evento de soltar o botao)."""
        if self.modo != 'modelo': return
        alvo = self.vista.pick(ev.x, ev.y)
        m = tk.Menu(self, tearoff=0, bg='#263041', fg=TXT, activebackground='#2f6fb5', font=('Segoe UI', 10))
        if alvo:
            self.selecionar(alvo)
            m.add_command(label='❌ Apagar esta peça', command=self.remover)
            m.add_command(label='Copiar esta peça (em lugar livre)', command=self.copiar_uma)
            m.add_command(label='Girar 90°', command=lambda: self.girar(90))
        else:
            m.add_command(label='Copiar a peça selecionada para cá', command=lambda: self._copiar_aqui(ev))
        try: m.tk_popup(ev.x_root, ev.y_root)
        finally: m.grab_release()

    def _copiar_aqui(self, ev):
        """Cria uma copia da peca selecionada exatamente onde clicou (no plano da mesa)."""
        h = self.vista.bed_xy(ev.x, ev.y)
        if not self.pecas or not h: return
        base = self.sel or self.pecas[-1]
        pc = Peca(base.caminho, base.prev, base.hull0, base.h0, getattr(base, 'cor_fixa', None) or CORES[self.ncor % len(CORES)], rot=base.rot, esc=base.esc); pc.nome = base.nome
        if getattr(base, 'cor_fixa', None): pc.cor_fixa = base.cor_fixa
        self.ncor += 1; pc.x, pc.y = h; self.pecas.append(pc); self.sel = pc; self.redesenhar()

    def copias(self):
        if not self.sel: messagebox.showinfo('Cópias', 'Selecione uma peça primeiro.', parent=self); return
        n = simpledialog.askinteger('Cópias', 'Quantas peças IGUAIS no total (incluindo esta)?', parent=self, initialvalue=2, minvalue=1, maxvalue=60)
        if not n: return
        base = self.sel; ja = [p for p in self.pecas if p.caminho == base.caminho and p.esc == base.esc]
        for _ in range(max(0, n - len(ja))): self.add_arquivo(base.caminho, copia_de=base)
        self.sel = base; self.redesenhar()

    def girar(self, g):
        if self.sel: self.sel.rot = (self.sel.rot + g) % 360; self.redesenhar()

    def remover(self):
        if self.sel in self.pecas:
            i = self.pecas.index(self.sel); self.pecas.remove(self.sel)
            self.sel = self.pecas[min(i, len(self.pecas) - 1)] if self.pecas else None
            self.redesenhar()

    def limpar(self):
        if self.pecas and messagebox.askyesno('Limpar', 'Tirar todas as peças da mesa?', parent=self):
            self.pecas.clear(); self.sel = None; self.redesenhar()

    def organizar(self, silencioso=False):
        """Arruma em fileiras. Tenta ate achar um arranjo que cabe (girando 90° quando ajuda)."""
        if not self.pecas: return False
        gap, mar = self.var_gap.get(), self.var_mar.get()
        W, H = BED_X - 2 * mar, BED_Y - 2 * mar
        melhor = None
        for modo in ('paisagem', 'retrato', 'como_esta'):
            rots = []
            for p in self.pecas:
                cand = [p.rot, p.rot + 90]
                if modo == 'como_esta': r = p.rot
                else:
                    r = max(cand, key=lambda g: (p.tamanho(g)[0] - p.tamanho(g)[1]) * (1 if modo == 'paisagem' else -1))
                rots.append(r)
            ordem = sorted(range(len(self.pecas)), key=lambda i: -self.pecas[i].tamanho(rots[i])[1])
            pos = {}; x = y = 0.0; lh = 0.0; cabe = True
            for i in ordem:
                w, h = self.pecas[i].tamanho(rots[i])
                if x + w > W + 1e-6: x = 0.0; y += lh + gap; lh = 0.0
                if y + h > H + 1e-6 or w > W + 1e-6: cabe = False; break
                pos[i] = (x + w / 2, y + h / 2); x += w + gap; lh = max(lh, h)
            if cabe: melhor = (rots, pos); break
        if melhor is None:
            if not silencioso: messagebox.showwarning('Organizar', 'Não consegui colocar todas as peças na mesa com esse espaço entre elas.\nTire uma peça, diminua o espaço entre peças ou a escala.', parent=self)
            return False
        rots, pos = melhor
        xs = [pos[i][0] - self.pecas[i].tamanho(rots[i])[0] / 2 for i in pos]; xe = [pos[i][0] + self.pecas[i].tamanho(rots[i])[0] / 2 for i in pos]
        ys = [pos[i][1] - self.pecas[i].tamanho(rots[i])[1] / 2 for i in pos]; ye = [pos[i][1] + self.pecas[i].tamanho(rots[i])[1] / 2 for i in pos]
        dx = (W - (max(xe) - min(xs))) / 2 + mar - min(xs); dy = (H - (max(ye) - min(ys))) / 2 + mar - min(ys)   # centraliza o grupo na mesa
        for i, p in enumerate(self.pecas): p.rot = rots[i] % 360; p.x = pos[i][0] + dx; p.y = pos[i][1] + dy
        self.redesenhar()
        return True

    # ---------- validacao ----------
    def validar(self):
        gap, mar = self.var_gap.get(), self.var_mar.get()
        for p in self.pecas: p.ok, p.motivo = True, ''
        for i, p in enumerate(self.pecas):
            c = p.contorno(); mn, mx = c.min(0), c.max(0)
            if mn[0] < mar - 0.01 or mn[1] < mar - 0.01 or mx[0] > BED_X - mar + 0.01 or mx[1] > BED_Y - mar + 0.01:
                p.ok, p.motivo = False, 'fora da mesa (ou na margem da borda)'
            if p.altura > BED_Z:
                p.ok, p.motivo = False, 'alta demais (%.0f mm, limite %.0f)' % (p.altura, BED_Z)
            for o in self.pecas[i + 1:]:
                if p.grupo and p.grupo == o.grupo: continue      # camadas/cores do mesmo 3MF ficam sobrepostas de proposito (conjunto montado)
                if not _separadas(c, o.contorno(), gap):
                    for q in (p, o):
                        if q.ok: q.ok, q.motivo = False, 'muito perto de outra peça (menos de %.1f mm)' % gap
        return all(p.ok for p in self.pecas)

    # ---------- desenho ----------
    def redesenhar(self, so2d=False):
        if self.modo == 'camadas': self.sair_camadas(redesenhar=False)
        tudo_ok = self.validar()
        self.vista.redesenhar(baixa=so2d)
        try: self.atualizar_cores()
        except Exception: pass
        # lista
        if not so2d or self.lista.size() != len(self.pecas):
            self.lista.delete(0, 'end')
            for i, p in enumerate(self.pecas):
                w, h = p.tamanho(); self.lista.insert('end', '%s%d. %s  (%.0f x %.0f x %.0f)' % ('' if p.ok else '! ', i + 1, p.nome[:24], w, h, p.altura))
        self.lista.selection_clear(0, 'end')
        if self.sel in self.pecas: self.lista.selection_set(self.pecas.index(self.sel))
        self._campos()
        # status
        if not self.pecas: self.lstatus.config(text='Mesa vazia. Clique em "+ Adicionar STL..." (pode escolher vários de uma vez).', fg=AMARELO)
        elif tudo_ok: self.lstatus.config(text='%d peça(s) na mesa - tudo cabe. Pode fatiar.' % len(self.pecas), fg=VERDE)
        else:
            erros = [('%d (%s)' % (i + 1, p.motivo)) for i, p in enumerate(self.pecas) if not p.ok]
            self.lstatus.config(text='Atenção - peça(s) com problema: ' + '; '.join(erros[:4]) + ('...' if len(erros) > 4 else ''), fg=VERM)
        if not so2d:
            self.salvar_layout(); self.agendar_calculo()

    def _campos(self):
        p = self.sel
        if not p: self.v_x.set(''); self.v_y.set(''); self.v_rot.set(''); self.v_esc.set(''); self.linfo.config(text=''); return
        self.v_x.set('%.1f' % p.x); self.v_y.set('%.1f' % p.y); self.v_rot.set('%.0f' % p.rot); self.v_esc.set('%.0f' % p.esc)
        w, h = p.tamanho(); self.linfo.config(text='%s\n%.1f x %.1f x %.1f mm%s' % (p.nome, w, h, p.altura, ('\n' + p.motivo) if not p.ok else ''), fg=TXT if p.ok else VERM)

    def _aplicar_campos(self, e=None):
        p = self.sel
        if not p: return
        try:
            p.x, p.y, p.rot, p.esc = float(self.v_x.get().replace(',', '.')), float(self.v_y.get().replace(',', '.')), float(self.v_rot.get().replace(',', '.')) % 360, max(5.0, float(self.v_esc.get().replace(',', '.')))
        except ValueError: pass
        self.redesenhar()

    # ---------- ligacao com a vista 3D ----------
    def selecionar(self, p):
        self.sel = p; self.redesenhar(so2d=True)

    def mover_peca(self, p, x, y):
        p.x, p.y = x, y; self.redesenhar(so2d=True)

    def girar_peca(self, p, rot):
        p.rot = rot % 360; self.redesenhar(so2d=True)

    def terminou_mexer(self):
        self.redesenhar()          # agora sim: salva a mesa e recalcula o tempo

    def mover_sel(self, dx, dy):
        if isinstance(self.focus_get(), (tk.Entry, tk.Spinbox)): return
        if self.sel: self.sel.x += dx; self.sel.y += dy; self.redesenhar()

    # ---------- mouse ----------
    def _lista_sel(self, e):
        s = self.lista.curselection()
        if s and s[0] < len(self.pecas): self.sel = self.pecas[s[0]]; self.redesenhar(so2d=True)

    # ---------- tempo estimado (fatia em segundo plano) ----------
    def agendar_calculo(self):
        self.tempo_valido = False
        if self._calc_id: self.after_cancel(self._calc_id)
        if not self.pecas or not all(p.ok for p in self.pecas): self.ltempo.config(text='' if not self.pecas else 'Arrume as peças em vermelho para calcular o tempo.', fg=DIM); self._calc_id = None; return
        self.ltempo.config(text='Tempo de impressão: calculando...', fg=AMARELO)
        self._calc_id = self.after(1200, self._iniciar_calculo)

    def _opcoes(self):
        p = dict(self.app.preset_atual()); p.update(self.app.opcoes_fatiar()); return p

    def _iniciar_calculo(self):
        self._calc_id = None
        if self._calc_rodando: self._calc_sujo = True; return
        if not self.pecas or not all(p.ok for p in self.pecas) or self.app.imprimindo: return
        stl = os.path.join(self.app.pasta, 'mesa_prev.stl')
        try: self.exportar(stl)
        except Exception as e: self.ltempo.config(text='Erro ao montar: %s' % e, fg=VERM); return
        self._calc_rodando = True; self._calc_sujo = False; n = len(self.pecas); opc = self._opcoes()
        def run():
            from base_ender import fatiar
            try:
                ok = fatiar(stl, self.gcode_prev, opc); tt = None
                if ok:
                    # o ';TIME:' do cabecalho e um valor fixo (6666) do CuraEngine: o tempo real e o ultimo ';TIME_ELAPSED:'
                    for l in open(self.gcode_prev, encoding='utf-8', errors='ignore'):
                        if l.startswith(';TIME_ELAPSED:'):
                            try: tt = int(float(l.split(':')[1]))
                            except ValueError: pass
                self._res = ('ok' if ok and tt else 'erro', tt, n)
            except Exception as e: self._res = ('erro', str(e), n)
        threading.Thread(target=run, daemon=True).start()

    def _poll(self):
        r = self._res
        if r is not None:
            self._res = None; self._calc_rodando = False
            if r[0] == 'ok' and not self._calc_sujo:
                self.tempo_total = r[1]; self.tempo_valido = True
                s = r[1]; txt = '%dh %02dmin' % (s // 3600, (s % 3600) // 60) if s >= 3600 else '%d min' % (s // 60)
                self.ltempo.config(text='Tempo estimado de impressão: %s  (%d peça(s), +~6 min para esquentar)' % (txt, r[2]), fg=VERDE)
            elif r[0] == 'erro' and not self._calc_sujo: self.ltempo.config(text='Não consegui calcular o tempo (%s).' % (r[1] or 'erro ao fatiar'), fg=VERM)
            if self._calc_sujo: self._calc_sujo = False; self.agendar_calculo()
        self.after(400, self._poll)

    # ---------- ver as camadas (o que a impressora vai fazer) ----------
    def alternar_camadas(self):
        if self.modo == 'camadas': self.sair_camadas(); return
        if not self.pecas: messagebox.showinfo('Camadas', 'Adicione uma peça primeiro.', parent=self); return
        if not self.tempo_valido or not os.path.isfile(self.gcode_prev):
            messagebox.showinfo('Camadas', 'Ainda estou fatiando (veja o aviso "calculando..."). Tente de novo em alguns segundos.', parent=self); return
        self.ltempo.config(text='Lendo as camadas...', fg=AMARELO); self.update_idletasks()
        res = {}
        def run():
            try: res['c'] = ler_camadas(self.gcode_prev)
            except Exception as e: res['e'] = str(e)
        t = threading.Thread(target=run, daemon=True); t.start()
        def espera():
            if t.is_alive(): self.after(150, espera); return
            if 'c' not in res or not res['c']: self.ltempo.config(text='Não consegui ler as camadas.', fg=VERM); return
            self.camadas = res['c']; self.modo = 'camadas'
            self.esc_cam.config(to=len(self.camadas)); self.v_cam.set(len(self.camadas)); self.bcam.config(text='VOLTAR AO MODELO (editar a mesa)', bg=LARANJA)
            self.fcam.pack(fill='x', padx=14, pady=(2, 0), before=self.lstatus)
            s = self.tempo_total; self.ltempo.config(text='Vendo o fatiamento. Tempo estimado: %dh %02dmin' % (s // 3600, (s % 3600) // 60), fg=VERDE)
            self.desenhar_camadas()
        espera()

    def sair_camadas(self, redesenhar=True):
        self.modo = 'modelo'; self.fcam.pack_forget(); self.bcam.config(text='VER CAMADAS (como vai imprimir)', bg=AZUL); self.vista.sair_camadas()
        if redesenhar: self.redesenhar()

    def desenhar_camadas(self):
        if self.modo != 'camadas' or not self.camadas: return
        n = int(self.v_cam.get()); n = max(1, min(n, len(self.camadas))); cam = self.camadas[n - 1]
        self.lcam.config(text='%d de %d  (altura %.1f mm)' % (n, len(self.camadas), cam['z']))
        self.vista.mostrar_camadas(self.camadas, n)

    # ---------- API (MCP / celular): roda na thread da tela, sem janelas de aviso ----------
    def api_estado(self):
        self.validar()
        pecas = []
        for i, p in enumerate(self.pecas):
            w, h = p.tamanho()
            pecas.append(dict(id=i + 1, nome=p.nome, x=round(p.x, 1), y=round(p.y, 1), rot=round(p.rot, 1), escala=round(p.esc, 1), largura=round(w, 1), profundidade=round(h, 1),
                              altura=round(p.altura, 1), ok=p.ok, motivo=p.motivo, selecionada=(p is self.sel), cor=self.cor_de(p)))
        return dict(ok=True, mesa=dict(x=BED_X, y=BED_Y, z=BED_Z), espaco_entre_pecas=float(self.var_gap.get()), margem=float(self.var_mar.get()), pecas=pecas,
                    tudo_cabe=all(p.ok for p in self.pecas), tempo_estimado_s=self.tempo_total if self.tempo_valido else None, guardadas_outras_cores=len(self.estoque), cores=self.cores_presentes())

    def _peca_id(self, d):
        try: i = int(d.get('id')) - 1
        except (TypeError, ValueError): raise ValueError('informe o id da peca (numero na lista)')
        if not (0 <= i < len(self.pecas)): raise ValueError('nao existe a peca %s (ha %d)' % (d.get('id'), len(self.pecas)))
        return self.pecas[i]

    def api_acao(self, acao, d):
        if self.app.imprimindo: return dict(ok=False, erro='a impressora esta imprimindo agora')
        try:
            if acao == 'imagem':
                import io as _io, base64 as _b64
                nome = str(d.get('vista', '3d')); az, el = {'frente': (-90.0, 9.0), 'topo': (-90.0, 89.0), 'lado': (0.0, 9.0), 'baixo': (-90.0, -80.0), '3d': (-62.0, 30.0)}.get(nome, (-62.0, 30.0))
                img = self.vista.render(int(d.get('largura', 1000)), int(d.get('altura', 760)), az, el, 430.0 if nome != 'topo' else 400.0, (BED_X / 2, BED_Y / 2, 20.0), esc=1.5)
                b = _io.BytesIO(); img.save(b, 'PNG'); return dict(ok=True, png_base64=_b64.b64encode(b.getvalue()).decode())
            if acao == 'importar3mf':
                c = str(d.get('caminho', ''))
                if not (os.path.isfile(c) and c.lower().endswith('.3mf')): return dict(ok=False, erro='caminho precisa ser um arquivo .3mf que existe')
                r = self.importar_3mf(c)
                return r if r else dict(ok=False, erro='nao consegui ler o 3mf')
            if acao == 'so_cor':
                nome = d.get('cor'); ok = self.so_cor(None if not nome or str(nome).lower() in ('todas', 'tudo') else str(nome).strip().capitalize())
                return dict(ok=ok, erro=None if ok else 'nenhuma peca dessa cor (cores: %s)' % ', '.join(self.cores_presentes()), cores=self.cores_presentes(), na_mesa=len(self.pecas), guardadas=len(self.estoque))
            if acao == 'adicionar':
                c = str(d.get('caminho', ''))
                if not (os.path.isfile(c) and c.lower().endswith('.stl')): return dict(ok=False, erro='caminho precisa ser um arquivo .stl que existe')
                p = self.add_arquivo(c)
                if p is None: return dict(ok=False, erro='nao consegui abrir o STL')
                if not p.ok: self.lstatus.config(text='Peca adicionada, mas nao cabe/esta colada (veja em vermelho).', fg=VERM)
            elif acao == 'copiar':
                base = self._peca_id(d); n = max(1, min(60, int(d.get('n', 1)))); feitas = 0
                for _ in range(n):
                    if self.add_arquivo(base.caminho, copia_de=base, so_se_couber=True) is None: break
                    feitas += 1
                self.sel = base; self.redesenhar()
                return dict(self.api_estado(), copias_feitas=feitas, aviso=('so couberam %d de %d copias' % (feitas, n)) if feitas < n else '')
            elif acao == 'editar':
                p = self._peca_id(d)
                if 'x' in d: p.x = float(d['x'])
                if 'y' in d: p.y = float(d['y'])
                if 'rot' in d: p.rot = float(d['rot']) % 360
                if 'escala' in d: p.esc = max(5.0, float(d['escala']))
                self.sel = p; self.redesenhar()
            elif acao == 'remover':
                self.sel = self._peca_id(d); self.remover()
            elif acao == 'limpar':
                self.pecas.clear(); self.sel = None; self.redesenhar()
            elif acao == 'encher':
                self.sel = self._peca_id(d); self.encher()
            elif acao == 'organizar':
                if not self.organizar(silencioso=True): return dict(ok=False, erro='nao consegui colocar todas na mesa com esse espaco entre pecas', **{k: v for k, v in self.api_estado().items() if k != 'ok'})
            elif acao == 'fatiar':
                if not self.pecas: return dict(ok=False, erro='mesa vazia')
                if not self.validar(): return dict(ok=False, erro='ha peca fora da mesa ou colada em outra', **{k: v for k, v in self.api_estado().items() if k != 'ok'})
                self.usar()
                return dict(ok=True, msg='montando e fatiando; acompanhe pelo status (arquivo pronto)')
            else: return dict(ok=False, erro='acao desconhecida: %s' % acao)
        except ValueError as e: return dict(ok=False, erro=str(e))
        return self.api_estado()

    # ---------- fatiar ----------
    def exportar(self, destino):
        partes = []
        for p in self.pecas:
            m = trimesh.load(p.caminho, force='mesh')
            if isinstance(m, trimesh.Scene): m = m.dump(concatenate=True)
            b = m.bounds
            m.apply_translation([-(b[0][0] + b[1][0]) / 2, -(b[0][1] + b[1][1]) / 2, -b[0][2]])
            V = p.vertices_mesa(np.asarray(m.vertices))
            V[:, 0] -= BED_X / 2; V[:, 1] -= BED_Y / 2       # relativo ao centro da mesa (o fatiador poe o centro 0,0 no meio)
            partes.append(trimesh.Trimesh(vertices=V, faces=np.asarray(m.faces), process=False))
        todo = trimesh.util.concatenate(partes)
        todo.export(destino)
        return todo

    def usar(self):
        if not self.pecas: messagebox.showinfo('Mesa 3D', 'Adicione pelo menos uma peça.', parent=self); return
        if not self.validar():
            self.redesenhar(); messagebox.showwarning('Mesa 3D', 'Tem peça fora da mesa ou colada em outra (em vermelho). Arrume antes de fatiar.', parent=self); return
        if self.app.imprimindo: messagebox.showwarning('Mesa 3D', 'A impressora está imprimindo agora.', parent=self); return
        destino = os.path.join(self.app.pasta, 'mesa_atual.stl')
        try: self.exportar(destino)
        except Exception as e: messagebox.showerror('Mesa 3D', 'Erro ao montar a mesa: %s' % e, parent=self); return
        self.salvar_layout(); self.app.usar_mesa(destino, len(self.pecas))


def ler_camadas(caminho):
    """Le o G-code do Cura e devolve [{'z':..., 'segs':{tipo: array Nx4 (x0,y0,x1,y1)}}, ...] so com movimentos que extrudam."""
    camadas = []; atual = None; tipo = 'WALL-OUTER'; x = y = 0.0; z = 0.0; e = 0.0; viu = False
    rx = re.compile(r'([XYZEF])(-?[\d.]+)')
    for l in open(caminho, encoding='utf-8', errors='ignore'):
        if l[0] == ';':
            if l.startswith(';LAYER:'):
                viu = True; atual = {'z': z, 'segs': {}}; camadas.append(atual)
            elif l.startswith(';TYPE:'): tipo = l[6:].strip()
            continue
        if not viu: continue
        if l.startswith('G92'):
            m = re.search(r'E(-?[\d.]+)', l)
            if m: e = float(m.group(1))
            continue
        if l.startswith(('G0', 'G1')):
            v = dict(rx.findall(l.split(';')[0]))
            nx = float(v['X']) if 'X' in v else x; ny = float(v['Y']) if 'Y' in v else y
            if 'Z' in v:
                z = float(v['Z'])
                if atual is not None and not atual['segs']: atual['z'] = z
            ne = float(v['E']) if 'E' in v else e
            if atual is not None and ('X' in v or 'Y' in v) and ne > e + 1e-6 and l.startswith('G1'):
                atual['segs'].setdefault(tipo, []).append((x, y, nx, ny))
            x, y, e = nx, ny, ne
    for c in camadas: c['segs'] = {t: np.array(s, dtype=float) for t, s in c['segs'].items() if s}
    return [c for c in camadas if c['segs']]


def _hex(h):
    h = h.lstrip('#'); return [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
