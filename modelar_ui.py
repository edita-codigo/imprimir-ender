"""Aba MODELAR: criar pecas do zero e editar pecas prontas, com ferramentas de CAD (formas, desenho + extrusao, revolucao, arredondar, chanfrar,
casca, furos, repetir, espelhar...). Varios projetos abertos ao mesmo tempo, receita de passos editavel (muda um numero antigo e a peca se refaz),
variaveis, exportar STL/STEP e mandar para a Mesa 3D. Tudo que a tela faz, a IA tambem faz pela API (/api/modelar) e pelo MCP (ender_modelar_*).

Rodar sozinho (sem o programa da impressora), para testar:  python modelar_ui.py
"""
import os, io, json, base64, copy, time, re
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
import numpy as np
import modelar as md
import modelar_tema as T
import modelar_icones as ic
import modelar_vista as mv
import modelar_esboco as me

FAIXA = [('Criar', ['caixa', 'cilindro', 'esfera', 'cone', 'tubo', 'texto'], ['prisma', 'toro', 'cunha']),
         ('Desenho', ['extrudar', 'revolucao'], ['loft', 'varrer']),
         ('Modificar', ['arredondar', 'chanfrar', 'casca', 'furo', 'cortar'], []),
         ('Mover', ['mover', 'girar', 'espelhar'], ['escalar', 'assentar'])]
ICONE = {k: k for k in md.OPS}
DICAS_OP = {'caixa': 'Bloco retangular (com cantos arredondados, se quiser).', 'cilindro': 'Cilindro, pino, eixo.', 'esfera': 'Bola.', 'cone': 'Cone ou tronco de cone.', 'tubo': 'Tubo, anel, bucha.',
            'texto': 'Texto em relevo ou gravado numa face da peça.', 'prisma': 'Prisma de N lados (sextavado, triângulo...).', 'toro': 'Rosquinha (anel de seção redonda).', 'cunha': 'Rampa / cunha.',
            'extrudar': 'Desenhe uma figura 2D e dê espessura a ela.', 'revolucao': 'Desenhe meio perfil e gire (vaso, copo, botão, polia).', 'loft': 'Liga desenhos em alturas diferentes (quadrado virando círculo).',
            'varrer': 'Um desenho percorre um caminho (cano, alça).', 'arredondar': 'Arredonda as arestas. Clique nas arestas da peça ou escolha "todas".', 'chanfrar': 'Corta as arestas em ângulo.',
            'casca': 'Deixa a peça oca com parede fina (caixa, pote).', 'furo': 'Furo redondo. Clique na peça para marcar onde.', 'cortar': 'Corta a peça num plano e fica com um lado.',
            'mover': 'Desloca a peça.', 'girar': 'Gira a peça.', 'espelhar': 'Espelha a peça (faz peça simétrica).', 'escalar': 'Aumenta ou diminui.', 'assentar': 'Centraliza e apoia a peça na mesa.'}
NOME_ARESTAS = {'todas': 'Todas', 'cima': 'As de cima', 'baixo': 'As de baixo', 'verticais': 'As verticais (em pé)', 'horizontais': 'As horizontais (deitadas)', 'circulares': 'As redondas (furos)',
                'ultimo': 'As do último passo', 'frente': 'As da frente', 'tras': 'As de trás', 'esquerda': 'As da esquerda', 'direita': 'As da direita', 'selecionadas': 'As que eu cliquei na peça'}
NOME_FACES = {'cima': 'Em cima', 'baixo': 'Em baixo', 'frente': 'Frente', 'tras': 'Trás', 'esquerda': 'Esquerda', 'direita': 'Direita', 'nenhuma': 'Nenhuma (oca fechada)', 'selecionadas': 'As que eu cliquei na peça'}
NOME_OPCAO = {'somar': 'Somar à peça', 'subtrair': 'Tirar da peça', 'intersectar': 'Só onde cruza', 'novo': 'Começar de novo',
              'xy': 'No chão (XY) → sobe', 'xz': 'De frente (XZ) → vai ao fundo', 'yz': 'De lado (YZ) → vai à direita',
              'cantos': 'Cantos vivos', 'arredondado': 'Cantos arredondados', 'suave': 'Curva suave', 'menor': 'Menor (ex.: de baixo)', 'maior': 'Maior (ex.: de cima)',
              '-z': 'De cima para baixo', '+z': 'De baixo para cima', '+y': 'Da frente para o fundo', '-y': 'Do fundo para a frente', '+x': 'Da esquerda para a direita', '-x': 'Da direita para a esquerda'}


ARRASTA_POS = ('caixa', 'cunha', 'cilindro', 'tubo', 'prisma', 'cone', 'esfera', 'toro', 'revolucao')       # formas que o mouse arrasta pelo corpo (campos x, y, z)


class _Malha:
    """So vertices e faces (o que a vista precisa para desenhar a forma em vermelho)."""
    def __init__(self, V, F): self.vertices = V; self.faces = F


def _txt(v):
    if isinstance(v, bool): return v
    if isinstance(v, float): return '%g' % v
    return '' if v is None else str(v)


class PainelModelar(tk.Frame):
    def __init__(self, pai, app):
        super().__init__(pai, bg=T.BG)
        self.app = app; self.pasta = os.path.join(getattr(app, 'pasta', os.path.dirname(os.path.abspath(__file__))), 'projetos_modelar'); self.pasta_stl = os.path.join(os.path.dirname(self.pasta), 'pecas_modeladas')
        self.projs = [md.Projeto('Peça 1')]; self.at = 0; self.form = None; self.editor = None; self.bt_op = {}; self._previa_job = None; self._salvar_job = None; self._pronto = False; self._pend_sessao = None
        self.cfg = self._ler_cfg()
        self._montar()
        self._carregar_sessao()
        md.aquecer(); self.after(400, self._esperar_motor)

    # ============================ configuracao / sessao ============================
    def _ler_cfg(self):
        try: return json.load(open(os.path.join(self.pasta, 'config.json'), encoding='utf-8'))
        except Exception: return {'permitir_codigo': False}

    def _gravar_cfg(self):
        try:
            os.makedirs(self.pasta, exist_ok=True); json.dump(self.cfg, open(os.path.join(self.pasta, 'config.json'), 'w', encoding='utf-8'))
        except Exception: pass

    def _carregar_sessao(self):
        try: s = json.load(open(os.path.join(self.pasta, 'sessao.json'), encoding='utf-8'))
        except Exception: s = {}
        self._pend_sessao = [c for c in s.get('abertos', []) if os.path.isfile(c)]; self._at_sessao = s.get('ativo_arquivo') or ''
        self._abas(); self._atualizar()

    def _esperar_motor(self):
        if not md.motor_pronto():
            if md._bd_erro: self._status('Motor de modelagem não instalado: no terminal, rode  pip install build123d', T.VERM); self.l_motor.config(text='● motor não instalado', fg=T.VERM); return
            self.l_motor.config(text='● carregando o motor…', fg=T.AMARELO); self.after(400, self._esperar_motor); return
        self._pronto = True; self.l_motor.config(text='● pronto', fg=T.VERDE)
        if self._pend_sessao:
            ps = []
            for c in self._pend_sessao:
                try: ps.append(md.Projeto.abrir(c, self.cfg.get('permitir_codigo', False)))
                except Exception: pass
            if ps: self.projs = ps; self.at = next((i for i, q in enumerate(ps) if q.arquivo == self._at_sessao), 0)        # a peca ativa volta pelo ARQUIVO (a posicao muda se havia peca vazia)
        self._pend_sessao = None; self._abas(); self._atualizar(True); self._status('Pronto. Escolha uma ferramenta na faixa de cima para começar a peça.')

    def _motor_ok(self):
        if self._pronto: return True
        self._status('O motor de modelagem ainda está carregando (alguns segundos)…', T.AMARELO); return False

    @property
    def proj(self): return self.projs[self.at]

    def _nome_arquivo(self, p):
        base = re.sub(r'[^\w\- ]', '_', p.nome).strip() or 'peca'; c = os.path.join(self.pasta, base + '.modelo.json'); n = 2
        usados = {q.arquivo for q in self.projs if q is not p and q.arquivo}
        while c in usados: c = os.path.join(self.pasta, '%s_%d.modelo.json' % (base, n)); n += 1
        return c

    def _salvar_logo(self):
        if self._salvar_job: self.after_cancel(self._salvar_job)
        self._salvar_job = self.after(900, self._salvar_tudo)

    def _salvar_tudo(self):
        self._salvar_job = None
        try:
            for p in self.projs:
                if not p.passos and not p.arquivo: continue
                if not p.arquivo: p.arquivo = self._nome_arquivo(p)
                if p.alterado or not os.path.isfile(p.arquivo): p.salvar()
            os.makedirs(self.pasta, exist_ok=True)
            json.dump(dict(abertos=[p.arquivo for p in self.projs if p.arquivo], ativo_arquivo=self.proj.arquivo or ''), open(os.path.join(self.pasta, 'sessao.json'), 'w', encoding='utf-8'))
        except Exception as e: self._status('Não consegui salvar o projeto: %s' % e, T.VERM)

    # ============================ montagem da tela ============================
    def _montar(self):
        # ---- barra dos projetos ----
        b = tk.Frame(self, bg=T.BG); b.pack(fill='x', padx=10, pady=(4, 0))
        self.f_abas = tk.Frame(b, bg=T.BG); self.f_abas.pack(side='left')
        dr = tk.Frame(b, bg=T.BG); dr.pack(side='right')
        T.botao(dr, 'MANDAR PARA A MESA 3D', self.para_mesa, 'primario', 'mesa').pack(side='right', padx=(6, 0))
        T.botao(dr, 'Exportar…', self.exportar_dialogo, 'normal', 'exportar').pack(side='right', padx=(6, 0))
        self.bt_abrir = T.botao(dr, 'Abrir…', self._menu_abrir, 'normal', 'abrir'); self.bt_abrir.pack(side='right', padx=(6, 0))
        T.botao(dr, 'Usar IA', self.janela_ia, 'normal', 'ia').pack(side='right', padx=(6, 0))
        self.l_motor = tk.Label(dr, text='● carregando o motor…', bg=T.BG, fg=T.AMARELO, font=(T.F, 8, 'bold')); self.l_motor.pack(side='right', padx=10)
        # ---- faixa de ferramentas ----
        fx = tk.Frame(self, bg=T.FAIXA, highlightthickness=1, highlightbackground=T.BORDA); fx.pack(fill='x', padx=10, pady=(4, 6))
        for nome, ops, mais in FAIXA:
            g = tk.Frame(fx, bg=T.FAIXA); g.pack(side='left', padx=(2, 0), pady=(2, 0))
            l = tk.Frame(g, bg=T.FAIXA); l.pack()
            for op in ops:
                bt = T.BotaoFerramenta(l, ICONE[op], md.OPS[op]['t'], lambda op=op: self.ferramenta(op), DICAS_OP.get(op, md.OPS[op]['d'])); bt.pack(side='left'); self.bt_op[op] = bt
            if mais:
                bm = T.BotaoFerramenta(l, 'mais', 'Mais', lambda: None, 'Mais ferramentas deste grupo.', larg=40); bm.pack(side='left'); bm.cmd = lambda bm=bm, mais=mais: self._menu_mais(bm, mais)
            tk.Label(g, text=nome.upper(), bg=T.FAIXA, fg=T.FRACO, font=(T.F, 7, 'bold')).pack(pady=(0, 2))
            T.linha(fx, True).pack(side='left', fill='y', padx=(2, 0), pady=8)
        g = tk.Frame(fx, bg=T.FAIXA); g.pack(side='right', padx=4, pady=(2, 0)); l = tk.Frame(g, bg=T.FAIXA); l.pack()
        self.bt_desf = T.BotaoFerramenta(l, 'desfazer', 'Desfazer', self.desfazer, 'Desfaz a última mudança (Ctrl+Z).'); self.bt_desf.pack(side='left')
        self.bt_ref = T.BotaoFerramenta(l, 'refazer', 'Refazer', self.refazer, 'Refaz o que foi desfeito (Ctrl+Y).'); self.bt_ref.pack(side='left')
        tk.Label(g, text='HISTÓRICO', bg=T.FAIXA, fg=T.FRACO, font=(T.F, 7, 'bold')).pack(pady=(0, 2))
        # ---- rodape ----
        rd = tk.Frame(self, bg=T.BG); rd.pack(side='bottom', fill='x', padx=10, pady=(6, 2))
        self.l_status = tk.Label(rd, text='', bg=T.BG, fg=T.DIM, font=(T.F, 9), anchor='w'); self.l_status.pack(side='left', fill='x', expand=True)
        tk.Label(rd, text='clique = escolher (Shift = várias) · arrastar no vazio = girar · arrastar a forma vermelha = mover · botão direito = deslocar · roda = zoom · duplo clique = enquadrar', bg=T.BG, fg=T.FRACO, font=(T.F, 8)).pack(side='right')
        # ---- corpo ----
        corpo = tk.Frame(self, bg=T.BG); corpo.pack(fill='both', expand=True, padx=10)
        esq = T.painel(corpo, width=244); esq.pack(side='left', fill='y'); esq.pack_propagate(False)
        T.titulo(esq, 'Passos da peça').pack(fill='x', padx=12, pady=(12, 4))
        T.rotulo(esq, 'Clique num passo para mudar as medidas.', T.FRACO, 8).pack(fill='x', padx=12)
        self.lista = T.Rolavel(esq); self.lista.pack(fill='both', expand=True, padx=6, pady=6)
        T.linha(esq).pack(fill='x')
        cab = tk.Frame(esq, bg=T.PAINEL); cab.pack(fill='x', padx=12, pady=(8, 2)); T.titulo(cab, 'Variáveis').pack(side='left')
        bv = T.botao(cab, '+', self.nova_variavel, 'liso', None, 12); bv.config(padx=6, pady=0); bv.pack(side='right'); T.Dica(bv, 'Criar uma variável (ex.: folga = 0,2). Depois use o nome dela em qualquer medida.')
        self.f_vars = tk.Frame(esq, bg=T.PAINEL); self.f_vars.pack(fill='x', padx=8, pady=(0, 10))
        self.dir = T.painel(corpo, width=304); self.dir.pack(side='right', fill='y'); self.dir.pack_propagate(False)
        self.meio = tk.Frame(corpo, bg=T.BG); self.meio.pack(side='left', fill='both', expand=True, padx=8)
        self.f_vista = tk.Frame(self.meio, bg=T.BG); self.f_vista.pack(fill='both', expand=True)
        bv = tk.Frame(self.f_vista, bg=T.PAINEL, highlightthickness=1, highlightbackground=T.BORDA); bv.pack(fill='x', pady=(0, 6))
        for nome, ch in (('3D', '3d'), ('Frente', 'frente'), ('Direita', 'direita'), ('Cima', 'cima'), ('Trás', 'tras'), ('Esquerda', 'esquerda'), ('Baixo', 'baixo')):
            x = T.botao(bv, nome, lambda c=ch: self.vista.vista(c), 'liso', None, 9); x.config(padx=9, pady=5); x.pack(side='left')
        x = T.botao(bv, '', lambda: self.vista.enquadrar(), 'liso', 'enquadrar', 9); x.config(pady=3, padx=6); x.pack(side='left', padx=(6, 0)); T.Dica(x, 'Enquadrar: mostra a peça inteira (ou duplo clique na vista).')
        self.v_med = tk.BooleanVar(value=True); self.v_ar = tk.BooleanVar(value=True)
        T.marca(bv, 'Arestas', self.v_ar, self._opcoes_vista).pack(side='right', padx=(0, 8)); T.marca(bv, 'Medidas', self.v_med, self._opcoes_vista).pack(side='right')
        self.vista = mv.VistaCAD(self.f_vista, ao_escolher=self._escolheu, ao_passar=self._passou, width=420, height=220); self.vista.ao_arrastar = self._arrastou; self.vista.pack(fill='both', expand=True)      # tamanho pedido pequeno: em tela baixa quem encolhe e a vista, nao o rodape
        self.bind_all('<Control-z>', self._atalho_desfazer, add='+'); self.bind_all('<Control-y>', self._atalho_refazer, add='+')
        self._painel_info()

    def _atalho_desfazer(self, e):
        if self.winfo_ismapped() and self.editor is None and not isinstance(e.widget, (tk.Entry, tk.Text)): self.desfazer()

    def _atalho_refazer(self, e):
        if self.winfo_ismapped() and self.editor is None and not isinstance(e.widget, (tk.Entry, tk.Text)): self.refazer()

    def _menu_mais(self, bt, ops):
        m = tk.Menu(self, tearoff=0, bg=T.PAINEL2, fg=T.TXT, activebackground=T.ACENTO, activeforeground='#14100C', font=(T.F, 10), bd=0)
        for op in ops: m.add_command(label='  ' + md.OPS[op]['t'], image=ic.icone(ICONE[op], 22), compound='left', command=lambda op=op: self.ferramenta(op))
        m.tk_popup(bt.winfo_rootx(), bt.winfo_rooty() + bt.winfo_height())

    def _menu_abrir(self):
        m = tk.Menu(self, tearoff=0, bg=T.PAINEL2, fg=T.TXT, activebackground=T.ACENTO, activeforeground='#14100C', font=(T.F, 10), bd=0)
        m.add_command(label='  Arquivo do computador (STL, STEP, 3MF, projeto)…', image=ic.icone('abrir', 20), compound='left', command=self.abrir_dialogo)
        m.add_command(label='  A peça selecionada na Mesa 3D', image=ic.icone('mesa', 20), compound='left', command=self._abrir_da_mesa)
        m.tk_popup(self.bt_abrir.winfo_rootx(), self.bt_abrir.winfo_rooty() + self.bt_abrir.winfo_height())

    def _abrir_da_mesa(self):
        try: self.pegar_da_mesa()
        except Exception as e: self._status(str(e), T.VERM)

    def _opcoes_vista(self):
        self.vista.mostrar_medidas = self.v_med.get(); self.vista.mostrar_arestas = self.v_ar.get(); self.vista.redesenhar()

    def _status(self, t, cor=None): self.l_status.config(text=t, fg=cor or T.DIM)

    # ============================ projetos (abas) ============================
    def _abas(self):
        for w in self.f_abas.winfo_children(): w.destroy()
        for i, p in enumerate(self.projs):
            s = i == self.at; bg = T.PAINEL if s else T.BG
            f = tk.Frame(self.f_abas, bg=bg, highlightthickness=1, highlightbackground=T.ACENTO if s else T.BORDA, cursor='hand2'); f.pack(side='left', padx=(0, 4))
            l = tk.Label(f, text=p.nome, bg=bg, fg=T.TXT if s else T.DIM, font=(T.F, 10, 'bold' if s else 'normal'), padx=10, pady=5); l.pack(side='left')
            l.bind('<Button-1>', lambda e, i=i: self.ativar(i)); l.bind('<Double-Button-1>', lambda e, i=i: self.renomear(i))
            x = tk.Label(f, text='×', bg=bg, fg=T.FRACO, font=(T.F, 11, 'bold'), padx=6, cursor='hand2'); x.pack(side='left'); x.bind('<Button-1>', lambda e, i=i: self.fechar_projeto(i))
            x.bind('<Enter>', lambda e, x=x: x.config(fg=T.VERM)); x.bind('<Leave>', lambda e, x=x: x.config(fg=T.FRACO))
        n = T.botao(self.f_abas, '+ Nova peça', self.novo_projeto, 'liso', None, 10); n.config(padx=10, pady=4); n.pack(side='left')
        T.Dica(n, 'Abre outra peça ao lado (dá para trabalhar em várias ao mesmo tempo). Duplo clique no nome = renomear.')

    def _nome_livre(self, base='Peça'):
        nomes = {p.nome for p in self.projs}; n = 1
        while '%s %d' % (base, n) in nomes: n += 1
        return '%s %d' % (base, n)

    def novo_projeto(self, nome=None):
        self._fechar_form(); p = md.Projeto(nome or self._nome_livre()); p.permitir_codigo = self.cfg.get('permitir_codigo', False)
        self.projs.append(p); self.at = len(self.projs) - 1; self._abas(); self._atualizar(True); self._salvar_logo(); return p

    def ativar(self, i):
        if not (0 <= i < len(self.projs)) or i == self.at: return
        self._fechar_form(); self.at = i; self._abas(); self._atualizar(True); self._salvar_logo()

    def renomear(self, i, nome=None):
        p = self.projs[i]; n = nome or simpledialog.askstring('Nome da peça', 'Nome desta peça:', initialvalue=p.nome, parent=self)
        if n and n.strip(): p.nome = n.strip()[:40]; p.alterado = True; self._abas(); self._salvar_logo()

    def fechar_projeto(self, i, perguntar=True):
        p = self.projs[i]
        if perguntar and p.passos and not messagebox.askyesno('Fechar peça', 'Fechar "%s"?\n\nEla continua salva na pasta projetos_modelar (botão Abrir… traz de volta).' % p.nome, parent=self): return
        self._salvar_tudo(); self._fechar_form(); self.projs.pop(i)
        if not self.projs: self.projs = [md.Projeto('Peça 1')]
        self.at = max(0, min(self.at if i > self.at else self.at - 1 if i < self.at else i, len(self.projs) - 1)); self._abas(); self._atualizar(True); self._salvar_logo()

    # ============================ atualizar a tela ============================
    def _atualizar(self, enquadrar=False):
        p = self.proj
        try: dv = p.dados() if self._pronto else md.dados_vista(md.Est())
        except Exception as e: dv = md.dados_vista(md.Est()); self._status('Erro ao desenhar: %s' % e, T.VERM)
        self.vista.definir(dv, enquadrar); self._passos(); self._variaveis()
        self.bt_desf.lt.config(fg='#C8D2E2' if p._desf else T.FRACO); self.bt_ref.lt.config(fg='#C8D2E2' if p._ref else T.FRACO)
        if self.form is None: self._painel_info()

    def _passos(self):
        self.lista.limpar(); p = self.proj; d = self.lista.dentro
        if not p.passos:
            T.rotulo(d, 'A peça está vazia.\n\nComece por uma forma em CRIAR\n(Caixa, Cilindro…) ou por um\ndesenho em DESENHO (Extrudar).', T.FRACO, 9, justify='left').pack(anchor='w', padx=8, pady=10); return
        ed = self.form['indice'] if self.form else None
        for i, ps in enumerate(p.passos):
            err = p.erro and p.erro[0] == i; depois = p.erro and i > p.erro[0]; off = ps.get('desligado'); s = i == ed
            bg = '#33241A' if s else ('#3A1F24' if err else T.PAINEL)
            l = tk.Frame(d, bg=bg, cursor='hand2'); l.pack(fill='x', pady=1)
            tk.Label(l, text='%d' % (i + 1), bg=bg, fg=T.FRACO, font=(T.F, 8), width=2).pack(side='left', padx=(2, 0))
            a = tk.Label(l, image=ic.icone(ICONE.get(ps['op'], 'caixa'), 20), bg=bg); a.pack(side='left', padx=(2, 6), pady=5)
            cor = T.VERM if err else (T.FRACO if (off or depois) else (T.ACENTO if s else T.TXT))
            t = tk.Label(l, text=p.descricao(i), bg=bg, fg=cor, font=(T.F, 9, 'bold' if s else ('overstrike' if off else 'normal')), anchor='w'); t.pack(side='left', fill='x', expand=True)
            x = tk.Label(l, image=ic.icone('lixo', 14), bg=bg, cursor='hand2'); x.pack(side='right', padx=(2, 6)); x.bind('<Button-1>', lambda e, i=i: self.remover_passo(i)); T.Dica(x, 'Apagar este passo.')
            o = tk.Label(l, image=ic.icone('olho_off' if off else 'olho', 15), bg=bg, cursor='hand2'); o.pack(side='right', padx=2); o.bind('<Button-1>', lambda e, i=i: self.alternar_passo(i)); T.Dica(o, 'Desligar/ligar este passo (a peça é refeita sem ele).')
            for w in (l, a, t): w.bind('<Button-1>', lambda e, i=i: self.editar_passo(i))
            if err: T.rotulo(d, '  ' + p.erro[1], T.VERM, 8, wraplength=210, justify='left').pack(fill='x', padx=6)

    def _variaveis(self):
        for w in self.f_vars.winfo_children(): w.destroy()
        p = self.proj
        if not p.vars: T.rotulo(self.f_vars, 'Nenhuma. Ex.: folga = 0,2', T.FRACO, 8).pack(anchor='w', padx=4); return
        for nome, val in p.vars.items():
            l = tk.Frame(self.f_vars, bg=T.PAINEL); l.pack(fill='x', pady=1)
            T.rotulo(l, nome, T.AZUL, 9, True).pack(side='left', padx=(4, 4)); T.rotulo(l, '=').pack(side='left')
            x = tk.Label(l, text='×', bg=T.PAINEL, fg=T.FRACO, font=(T.F, 10, 'bold'), cursor='hand2'); x.pack(side='right', padx=4); x.bind('<Button-1>', lambda e, n=nome: self.definir_variavel(n, ''))
            var = tk.StringVar(value='%g' % val); c = T.campo(l, var, 8); c.pack(side='right')
            c.entry.bind('<Return>', lambda e, n=nome, var=var: self.definir_variavel(n, var.get())); c.entry.bind('<FocusOut>', lambda e, n=nome, var=var, v0=val: var.get().strip() != '%g' % v0 and self.definir_variavel(n, var.get()))

    def _painel_info(self):
        for w in self.dir.winfo_children(): w.destroy()
        d = self.dir; p = self.proj; e = p.est
        T.titulo(d, 'Peça').pack(fill='x', padx=14, pady=(14, 6))
        if e.vazio:
            T.rotulo(d, 'Ainda não há peça.', T.TXT, 11, True).pack(anchor='w', padx=14)
            T.rotulo(d, 'Como começar:\n\n1. Clique numa forma em CRIAR (por exemplo,\n   Caixa) e digite as medidas.\n\n2. Ou clique em Extrudar, desenhe a figura\n   com o mouse e dê a espessura.\n\n3. Depois use MODIFICAR: furo, arredondar,\n   casca, chanfro…\n\n4. Pronto? MANDAR PARA A MESA 3D.\n\nJá tem um STL? Use Abrir… para editar ele aqui.', T.DIM, 9, justify='left').pack(anchor='w', padx=14, pady=8)
        else:
            lim = e.limites(); t = lim[1] - lim[0]; vol = md.volume(e)
            for rot, val in (('Largura (X)', '%.2f mm' % t[0]), ('Profundidade (Y)', '%.2f mm' % t[1]), ('Altura (Z)', '%.2f mm' % t[2]), ('Volume', '%.2f cm³' % (vol / 1000)),
                             ('Peso maciço', 'PLA %.0f g · ABS %.0f g' % (vol / 1000 * 1.24, vol / 1000 * 1.04)), ('Tipo', 'sólido exato (CAD)' if e.tipo == 'cad' else 'malha (veio de STL)')):
                l = tk.Frame(d, bg=T.PAINEL); l.pack(fill='x', padx=14, pady=2); T.rotulo(l, rot).pack(side='left'); T.rotulo(l, val, T.TXT, 10, True).pack(side='right')
            if e.tipo == 'malha':
                T.rotulo(d, 'Peça em malha: dá para somar formas, furar, cortar, escrever, mover e espelhar. Arredondar, chanfrar e casca só em peça criada aqui ou vinda de STEP.', T.AMARELO, 8, wraplength=270, justify='left').pack(fill='x', padx=14, pady=8)
            if e.sol is not None and len(e.sol.solids()) > 1:
                T.rotulo(d, 'Atenção: a peça está em %d pedaços soltos (um corte/furo dividiu a peça, ou uma forma somada não encosta nela).' % len(e.sol.solids()), T.AMARELO, 9, wraplength=270, justify='left').pack(fill='x', padx=14, pady=8)
            if p.erro: T.rotulo(d, 'O passo %d está com erro (em vermelho na lista): a peça mostrada vai só até o passo anterior.' % (p.erro[0] + 1), T.VERM, 9, wraplength=270, justify='left').pack(fill='x', padx=14, pady=8)
        T.linha(d).pack(fill='x', pady=10)
        T.titulo(d, 'Escolhido na peça').pack(fill='x', padx=14, pady=(0, 6))
        self.l_sel = T.rotulo(d, '', T.DIM, 9, wraplength=270, justify='left'); self.l_sel.pack(fill='x', padx=14); self._texto_sel()
        self.f_acoes = tk.Frame(d, bg=T.PAINEL); self.f_acoes.pack(fill='x', padx=12, pady=8); self._acoes_sel()

    def _texto_sel(self):
        if not getattr(self, 'l_sel', None) or not self.l_sel.winfo_exists(): return
        v = self.vista; dv = v.cena.dv; t = []
        for i in sorted(v.sel_arestas):
            a = dv['info_arestas'][i] if i < len(dv.get('info_arestas', [])) else None
            if a: t.append('Aresta %d: %s, %.2f mm' % (i, a['tipo'], a['comprimento']))
        for i in sorted(v.sel_faces):
            f = dv['faces'][i] if i < len(dv.get('faces', [])) else None
            if f: t.append('Face %d: %s, %.1f mm²' % (i, f['tipo'], f['area']))
        self.l_sel.config(text='\n'.join(t[:8]) + ('\n…' if len(t) > 8 else '') if t else 'Nada escolhido. Clique numa aresta ou face da peça (Shift = várias).')

    def _acoes_sel(self):
        if not getattr(self, 'f_acoes', None) or not self.f_acoes.winfo_exists(): return
        for w in self.f_acoes.winfo_children(): w.destroy()
        v = self.vista
        if v.sel_arestas:
            T.botao(self.f_acoes, 'Arredondar', lambda: self.ferramenta('arredondar'), 'normal', 'arredondar', 9).pack(side='left', padx=2); T.botao(self.f_acoes, 'Chanfrar', lambda: self.ferramenta('chanfrar'), 'normal', 'chanfrar', 9).pack(side='left', padx=2)
        elif v.sel_faces:
            T.botao(self.f_acoes, 'Furo aqui', lambda: self.ferramenta('furo'), 'normal', 'furo', 9).pack(side='left', padx=2); T.botao(self.f_acoes, 'Casca abrindo aqui', lambda: self.ferramenta('casca'), 'normal', 'casca', 9).pack(side='left', padx=2)

    # ============================ escolher na peca ============================
    def _passou(self, h):
        dv = self.vista.cena.dv
        if h and h[0] == 'a' and h[1] < len(dv.get('info_arestas', [])): a = dv['info_arestas'][h[1]]; self._status('Aresta %d · %s · %.2f mm' % (h[1], a['tipo'], a['comprimento']))
        elif h and h[0] == 'f' and h[1] < len(dv.get('faces', [])): f = dv['faces'][h[1]]; self._status('Face %d · %s · %.1f mm²' % (h[1], f['tipo'], f['area']))

    def _escolheu(self, h, info):
        self._ult_ponto = info
        if self.form:
            op = self.form['op']; fv = self.form['v']
            if 'arestas' in fv and self.vista.sel_arestas: fv['arestas'].set(NOME_ARESTAS['selecionadas']); self._previa_logo()
            if 'abrir' in fv and self.vista.sel_faces: fv['abrir'].set(NOME_FACES['selecionadas'])
            if info is not None and h and h[0] in ('f', 'p', 'a'):
                pt = [round(float(c) * 2) / 2 for c in info['ponto']]; n = info['normal']
                if op == 'furo':
                    k = int(np.argmax(np.abs(n))); d = ('-' if n[k] > 0 else '+') + 'xyz'[k]
                    fv['direcao'].set(NOME_OPCAO[d])
                    for j, c in enumerate('xyz'): fv[c].set('' if j == k else '%g' % pt[j])
                    self._status('Furo marcado em (%g, %g, %g), %s.' % (pt[0], pt[1], pt[2], NOME_OPCAO[d].lower()), T.VERDE)
                elif op in ('caixa', 'cilindro', 'tubo', 'cone', 'prisma', 'cunha', 'esfera', 'toro') and all(c in fv for c in 'xyz'):
                    for j, c in enumerate('xyz'): fv[c].set('%g' % pt[j])
                    self._status('Posição marcada em (%g, %g, %g).' % tuple(pt), T.VERDE)
        else: self._texto_sel(); self._acoes_sel()

    # ============================ formulario de uma ferramenta ============================
    def ferramenta(self, op):
        if not self._motor_ok() or self.editor is not None: return
        if op in md.PRECISA_PECA and self.proj.est.vazio: self._status('"%s" precisa de uma peça. Comece por uma forma (Caixa, Cilindro…) ou por Extrudar.' % md.OPS[op]['t'], T.AMARELO); return
        if op in md.SO_CAD and self.proj.est.tipo == 'malha': self._status('"%s" só funciona em peça criada aqui ou vinda de STEP (esta veio de STL).' % md.OPS[op]['t'], T.AMARELO); return
        if op == 'assentar': self._executar(lambda: self.proj.adicionar(dict(op='assentar')), 'Peça centralizada e apoiada na mesa.'); return
        self._abrir_form(op, None, None)

    def editar_passo(self, i):
        if not self._motor_ok() or self.editor is not None: return
        ps = self.proj.passos[i]
        if ps['op'] == 'assentar': self._status('Esse passo não tem medidas para mudar.'); return
        self._abrir_form(ps['op'], copy.deepcopy(ps), i)

    def _abrir_form(self, op, passo, indice):
        self._fechar_form(False); o = md.OPS[op]; vals = md.padrao(op)
        if passo: vals.update({k: v for k, v in passo.items() if k not in ('op',)})
        elif op in ('arredondar', 'chanfrar') and self.vista.sel_arestas: vals['arestas'] = 'selecionadas'
        elif op == 'casca' and self.vista.sel_faces: vals['abrir'] = 'selecionadas'
        elif op == 'furo' and getattr(self, '_ult_ponto', None) and self.vista.sel_faces:
            pt = [round(float(c) * 2) / 2 for c in self._ult_ponto['ponto']]; n = self._ult_ponto['normal']; k = int(np.argmax(np.abs(n)))
            vals.update(x=pt[0], y=pt[1], z=pt[2], direcao=('-' if n[k] > 0 else '+') + 'xyz'[k]); vals['xyz'[k]] = ''
        elif op == 'cortar' and not self.proj.est.vazio:
            lim = self.proj.est.limites(); vals['posicao'] = round(float(lim[0][2] + lim[1][2]) / 2, 2)
        elif op in ('caixa', 'cilindro', 'tubo', 'cone', 'prisma', 'cunha', 'extrudar', 'revolucao') and not self.proj.est.vazio and 'z' in vals:
            vals['z'] = round(float(self.proj.est.limites()[1][2]), 2)                       # forma nova nasce em cima da peca
        self.form = dict(op=op, indice=indice, v={}, x={}, sel_arestas=sorted(self.vista.sel_arestas), sel_faces=sorted(self.vista.sel_faces))
        for w in self.dir.winfo_children(): w.destroy()
        d = self.dir
        cab = tk.Frame(d, bg=T.PAINEL); cab.pack(fill='x', padx=12, pady=(12, 2))
        tk.Label(cab, image=ic.icone(ICONE[op], 28), bg=T.PAINEL).pack(side='left', padx=(0, 8))
        T.rotulo(cab, ('Mudar: ' if indice is not None else '') + o['t'], T.TXT, 13, True).pack(side='left')
        T.rotulo(d, DICAS_OP.get(op, o['d']), T.DIM, 8, wraplength=276, justify='left').pack(fill='x', padx=14, pady=(0, 6))
        rod = tk.Frame(d, bg=T.PAINEL); rod.pack(side='bottom', fill='x', padx=12, pady=10)
        T.botao(rod, 'SALVAR MUDANÇA' if indice is not None else 'APLICAR', self._aplicar, 'ok', 'ok', 11).pack(side='left', fill='x', expand=True); T.botao(rod, 'Cancelar', self._fechar_form, 'normal', None, 10).pack(side='left', padx=(6, 0))
        self.l_erro = T.rotulo(d, '', T.VERM, 9, wraplength=276, justify='left'); self.l_erro.pack(side='bottom', fill='x', padx=14)
        rol = T.Rolavel(d); rol.pack(fill='both', expand=True, padx=6); f = rol.dentro
        for prm in o['p']:
            nome, tipo, pad, rot = prm[:4]; ops = prm[4].split('|') if len(prm) > 4 else None; v = vals.get(nome, pad)
            if tipo in ('n', 'i', 's'):
                l = tk.Frame(f, bg=T.PAINEL); l.pack(fill='x', padx=8, pady=3); T.rotulo(l, rot, T.TXT, 9).pack(side='left')
                var = tk.StringVar(value=_txt(v)); T.campo(l, var, 14 if tipo == 's' else 9).pack(side='right'); self.form['v'][nome] = var; var.trace_add('write', lambda *a: self._previa_logo())
            elif tipo == 'e':
                l = tk.Frame(f, bg=T.PAINEL); l.pack(fill='x', padx=8, pady=3); T.rotulo(l, rot, T.TXT, 9).pack(side='left')
                var = tk.StringVar(value=NOME_OPCAO.get(v, v)); T.escolha(l, var, [NOME_OPCAO.get(x, x) for x in ops], 20 if max(len(NOME_OPCAO.get(x, x)) for x in ops) > 9 else 9, lambda *a: self._previa_logo()).pack(side='right')
                self.form['v'][nome] = var; self.form['x']['_op_' + nome] = {NOME_OPCAO.get(x, x): x for x in ops}
            elif tipo == 'b':
                var = tk.BooleanVar(value=bool(v)); T.marca(f, rot, var, self._previa_logo).pack(anchor='w', padx=6, pady=3); self.form['v'][nome] = var
            elif tipo in ('arestas', 'faces'):
                nomes = NOME_ARESTAS if tipo == 'arestas' else NOME_FACES
                l = tk.Frame(f, bg=T.PAINEL); l.pack(fill='x', padx=8, pady=3); T.rotulo(l, rot, T.TXT, 9).pack(anchor='w')
                if isinstance(v, str) and v in nomes: ini = nomes[v]
                else: ini = 'As já gravadas neste passo'; self.form['x']['_sel_' + nome] = v
                var = tk.StringVar(value=ini); lst = list(nomes.values()) + (['As já gravadas neste passo'] if ini not in nomes.values() else [])
                T.escolha(l, var, lst, 26, lambda *a: self._previa_logo()).pack(anchor='w', pady=(2, 0)); self.form['v'][nome] = var; self.form['x']['_op_' + nome] = {b: a for a, b in nomes.items()}
                T.rotulo(l, 'Para escolher na mão: clique nas %s da peça (Shift = várias).' % ('arestas' if tipo == 'arestas' else 'faces'), T.FRACO, 8, wraplength=260, justify='left').pack(anchor='w')
            elif tipo == 'perfil':
                self.form['x'][nome] = copy.deepcopy(v) if v else []; l = tk.Frame(f, bg=T.PAINEL2, highlightthickness=1, highlightbackground=T.BORDA); l.pack(fill='x', padx=8, pady=6)
                lb = T.rotulo(l, '', T.TXT, 9, wraplength=250, justify='left'); lb.pack(fill='x', padx=8, pady=(8, 4)); self.form['x']['_lb_' + nome] = lb
                T.botao(l, 'DESENHAR…', lambda n=nome: self._desenhar(n), 'azul', 'lapis', 10).pack(fill='x', padx=8, pady=(0, 8)); self._resumo_perfil(nome)
            elif tipo == 'secoes':
                self.form['x'][nome] = copy.deepcopy(v) if v else [dict(z=0, perfil=[dict(t='ret', l=30, a=30)]), dict(z=30, perfil=[dict(t='circ', d=15)])]
                self.form['x']['_f_sec'] = tk.Frame(f, bg=T.PAINEL); self.form['x']['_f_sec'].pack(fill='x', padx=8, pady=4); self._secoes()
            elif tipo == 'pts':
                T.rotulo(f, rot + '  (um ponto por linha: x, y, z)', T.TXT, 9).pack(anchor='w', padx=8, pady=(6, 2))
                tx = tk.Text(f, height=6, width=30, bg=T.CAMPO, fg=T.TXT, insertbackground=T.TXT, relief='flat', font=('Consolas', 10), highlightthickness=1, highlightbackground=T.BORDA); tx.pack(fill='x', padx=8)
                tx.insert('1.0', '\n'.join(', '.join(_txt(c) for c in q) for q in (v or [[0, 0, 0], [0, 0, 20], [20, 0, 30], [40, 0, 30]]))); tx.bind('<KeyRelease>', lambda e: self._previa_logo()); self.form['x']['_tx_' + nome] = tx
            elif tipo == 'rep': self._form_repetir(f, v)
            elif tipo == 'cod':
                tx = tk.Text(f, height=14, width=30, bg=T.CAMPO, fg=T.TXT, insertbackground=T.TXT, relief='flat', font=('Consolas', 9), highlightthickness=1, highlightbackground=T.BORDA); tx.pack(fill='x', padx=8, pady=4)
                tx.insert('1.0', _txt(v)); self.form['x']['_tx_' + nome] = tx
            elif tipo == 'arq':
                l = tk.Frame(f, bg=T.PAINEL); l.pack(fill='x', padx=8, pady=3); var = tk.StringVar(value=_txt(v)); T.campo(l, var, 22).pack(side='left'); self.form['v'][nome] = var
                T.botao(l, '…', lambda var=var: var.set(filedialog.askopenfilename(parent=self, filetypes=[('Modelo 3D', '*.stl *.3mf *.obj *.step *.stp')]) or var.get()), 'normal', None, 9).pack(side='left', padx=4)
        if op in ('mover', 'escalar'):
            T.rotulo(f, 'Com o mouse: arraste a peça para mudar o lugar (bolinha azul = subir/descer).' if op == 'mover' else 'Com o mouse: puxe o quadradinho amarelo do canto para aumentar ou diminuir.', T.FRACO, 8, wraplength=260, justify='left').pack(anchor='w', padx=8, pady=(8, 2))
        if op in ('furo', 'caixa', 'cilindro', 'tubo', 'cone', 'prisma', 'cunha', 'esfera', 'toro'):
            T.rotulo(f, 'Com o mouse: arraste a forma vermelha para mudar o lugar; puxe os quadradinhos amarelos para mudar o tamanho; a bolinha azul sobe e desce. Ou clique num ponto da peça para marcar a posição.', T.FRACO, 8, wraplength=260, justify='left').pack(anchor='w', padx=8, pady=(8, 2))
        T.rotulo(f, 'Em qualquer medida vale conta e variável (ex.: 40/2, largura - 2*folga).', T.FRACO, 8, wraplength=260, justify='left').pack(anchor='w', padx=8, pady=(2, 8))
        for b_op, bt in self.bt_op.items(): bt.marcar(b_op == op)
        self._passos(); self._previa_logo(); self._status('Ajuste as medidas à direita (em vermelho na peça: o que vai ser feito) e clique APLICAR.')

    def _form_repetir(self, f, v):
        v = v if isinstance(v, dict) else {}; x = self.form['x']
        cx = tk.Frame(f, bg=T.PAINEL2, highlightthickness=1, highlightbackground=T.BORDA); cx.pack(fill='x', padx=8, pady=8)
        l = tk.Frame(cx, bg=T.PAINEL2); l.pack(fill='x', padx=8, pady=6); T.rotulo(l, 'Repetir', T.TXT, 9, True).pack(side='left')
        nomes = {'nao': 'Não repetir', 'linear': 'Em fila / grade', 'circular': 'Em círculo'}; x['_rep_nomes'] = {b: a for a, b in nomes.items()}
        tv = tk.StringVar(value=nomes.get(v.get('tipo'), nomes['nao'])); self.form['v']['_rep_tipo'] = tv
        T.escolha(l, tv, list(nomes.values()), 14, lambda *a: (self._rep_campos(), self._previa_logo())).pack(side='right')
        x['_rep_f'] = tk.Frame(cx, bg=T.PAINEL2); x['_rep_f'].pack(fill='x'); x['_rep_v'] = dict(v); self._rep_campos()

    def _rep_campos(self):
        x = self.form['x']; f = x['_rep_f']; v0 = x['_rep_v']
        for w in f.winfo_children(): w.destroy()
        tipo = x['_rep_nomes'][self.form['v']['_rep_tipo'].get()]; x['_rep_vars'] = {}
        campos = {'linear': [('n', 'Quantas', 3), ('dx', 'Passo em X', 10), ('dy', 'Passo em Y', 0), ('dz', 'Passo em Z', 0), ('n2', 'Fileiras', 1), ('dx2', 'Passo da fileira X', 0), ('dy2', 'Passo da fileira Y', 10)],
                  'circular': [('n', 'Quantas', 6), ('cx', 'Centro X', 0), ('cy', 'Centro Y', 0), ('cz', 'Centro Z', 0), ('angulo', 'Ângulo total', 360)]}.get(tipo, [])
        for k, rot, pad in campos:
            l = tk.Frame(f, bg=T.PAINEL2); l.pack(fill='x', padx=8, pady=2); T.rotulo(l, rot, T.DIM, 9).pack(side='left')
            var = tk.StringVar(value=_txt(v0.get(k, pad))); T.campo(l, var, 8).pack(side='right'); x['_rep_vars'][k] = var; var.trace_add('write', lambda *a: self._previa_logo())
        if tipo == 'circular':
            l = tk.Frame(f, bg=T.PAINEL2); l.pack(fill='x', padx=8, pady=2); T.rotulo(l, 'Em volta do eixo', T.DIM, 9).pack(side='left')
            var = tk.StringVar(value=v0.get('eixo', 'z')); T.escolha(l, var, ['z', 'x', 'y'], 4, lambda *a: self._previa_logo()).pack(side='right'); x['_rep_vars']['eixo'] = var
        if campos: tk.Frame(f, bg=T.PAINEL2, height=6).pack()

    def _resumo_perfil(self, nome):
        figs = self.form['x'][nome]; lb = self.form['x']['_lb_' + nome]
        if not figs: lb.config(text='Nenhum desenho ainda. Clique em DESENHAR para fazer a figura com o mouse.', fg=T.AMARELO)
        else: lb.config(text='Desenho: ' + '; '.join(me.descrever(f, self.proj.vars) for f in figs[:4]) + ('…' if len(figs) > 4 else ''), fg=T.TXT)

    def _secoes(self):
        x = self.form['x']; f = x['_f_sec']; sec = x['secoes']
        for w in f.winfo_children(): w.destroy()
        T.rotulo(f, 'Seções (de baixo para cima)', T.TXT, 9, True).pack(anchor='w')
        for i, s in enumerate(sec):
            l = tk.Frame(f, bg=T.PAINEL2, highlightthickness=1, highlightbackground=T.BORDA); l.pack(fill='x', pady=3)
            a = tk.Frame(l, bg=T.PAINEL2); a.pack(fill='x', padx=6, pady=(6, 2)); T.rotulo(a, 'Altura Z', T.DIM, 9).pack(side='left')
            var = tk.StringVar(value=_txt(s.get('z', 0))); T.campo(a, var, 7).pack(side='left', padx=6); var.trace_add('write', lambda *q, i=i, var=var: (sec[i].__setitem__('z', var.get()), self._previa_logo()))
            if len(sec) > 2:
                b = T.botao(a, '×', lambda i=i: (sec.pop(i), self._secoes(), self._previa_logo()), 'liso', None, 11); b.config(padx=4, pady=0); b.pack(side='right')
            T.rotulo(l, '; '.join(me.descrever(g, self.proj.vars) for g in s.get('perfil', [])[:3]) or 'sem desenho', T.TXT if s.get('perfil') else T.AMARELO, 8, wraplength=240, justify='left').pack(fill='x', padx=6)
            T.botao(l, 'Desenhar…', lambda i=i: self._desenhar('secoes', i), 'azul', 'lapis', 9).pack(anchor='w', padx=6, pady=6)
        T.botao(f, '+ Outra seção', lambda: (sec.append(dict(z=md.num(sec[-1].get('z'), self.proj.vars) + 20, perfil=copy.deepcopy(sec[-1].get('perfil', [])))), self._secoes(), self._previa_logo()), 'normal', None, 9).pack(anchor='w', pady=4)

    def _ler_form(self):
        """Formulario -> dicionario do passo."""
        fm = self.form; op = fm['op']; d = {'op': op}; x = fm['x']
        for prm in md.OPS[op]['p']:
            nome, tipo = prm[0], prm[1]
            if tipo in ('n', 'i'):
                s = fm['v'][nome].get().strip().replace(',', '.')
                if s == '':
                    d[nome] = '' if (op == 'furo' and nome in 'xyz') else prm[2]; continue
                try: d[nome] = int(float(s)) if tipo == 'i' else float(s)
                except ValueError: d[nome] = s
            elif tipo == 's': d[nome] = fm['v'][nome].get()
            elif tipo == 'e': d[nome] = x['_op_' + nome].get(fm['v'][nome].get(), fm['v'][nome].get())
            elif tipo == 'b': d[nome] = bool(fm['v'][nome].get())
            elif tipo in ('arestas', 'faces'):
                esc = x['_op_' + nome].get(fm['v'][nome].get())
                if esc is None: d[nome] = x.get('_sel_' + nome, 'todas')
                elif esc == 'selecionadas':
                    ids = sorted(self.vista.sel_arestas if tipo == 'arestas' else self.vista.sel_faces) or (fm['sel_arestas'] if tipo == 'arestas' else fm['sel_faces'])
                    if not ids: raise md.ErroModelo('Clique nas %s da peça primeiro (Shift = várias), ou escolha outra opção na lista.' % ('arestas' if tipo == 'arestas' else 'faces'))
                    d[nome] = self._ids_para_pontos(tipo, ids)
                else: d[nome] = esc
            elif tipo == 'perfil': d[nome] = copy.deepcopy(x[nome])
            elif tipo == 'secoes': d[nome] = copy.deepcopy(x['secoes'])
            elif tipo == 'pts':
                pts = []
                for ln in x['_tx_' + nome].get('1.0', 'end').splitlines():
                    q = [c for c in ln.replace(';', ',').replace(' ', ',').split(',') if c != '']
                    if len(q) >= 3: pts.append([float(c) if re.fullmatch(r'-?\d+(\.\d+)?', c) else c for c in q[:3]])
                d[nome] = pts
            elif tipo == 'cod': d[nome] = x['_tx_' + nome].get('1.0', 'end').rstrip()
            elif tipo == 'arq': d[nome] = fm['v'][nome].get().strip()
            elif tipo == 'rep':
                t = x['_rep_nomes'][fm['v']['_rep_tipo'].get()]
                if t != 'nao':
                    r = {'tipo': t}
                    for k, var in x['_rep_vars'].items():
                        s = var.get().strip().replace(',', '.')
                        if k == 'eixo': r[k] = s; continue
                        try: r[k] = float(s) if s else 0.0
                        except ValueError: r[k] = s
                    d[nome] = r
        return d

    def _ids_para_pontos(self, tipo, ids):
        """A escolha feita na tela e gravada como PONTOS (assim continua valendo se a peca mudar)."""
        dv = self.vista.cena.dv; out = []
        for i in ids:
            if tipo == 'arestas' and i < len(dv['info_arestas']): out.append(dv['info_arestas'][i]['meio'])
            elif tipo == 'faces' and i < len(dv['faces']): out.append(dv['faces'][i]['centro'])
        return [{'perto': out}]

    def _previa_logo(self):
        if self._previa_job: self.after_cancel(self._previa_job)
        self._previa_job = self.after(260, self._previa)

    def _previa(self):
        self._previa_job = None
        if not self.form or self.editor is not None: return
        d = None
        try:
            d = self._ler_form(); i = self.form['indice']; est = self.proj._estado_antes(i) if i is not None else self.proj.est
            if d['op'] in ('mover', 'escalar') and not est.vazio: fant = self._fantasma_peca(d, est)
            else: fant = md.malha_previa(d['op'], d, self.proj.vars, est)
            self.vista.definir_fantasma(fant); self.l_erro.config(text='')
        except md.ErroModelo as e: self.vista.definir_fantasma(None); self.l_erro.config(text=str(e))
        except Exception as e: self.vista.definir_fantasma(None); self.l_erro.config(text='%s: %s' % (type(e).__name__, str(e)[:120]))
        self._alcas(d)

    # ============================ arrastar com o mouse (posicao e tamanho) ============================
    def _fantasma_peca(self, d, est):
        """Mover / Escalar: a peca inteira aparece em vermelho no lugar/tamanho novo, para arrastar com o mouse."""
        x = self.form['x']
        if x.get('_mb_id') != id(est):
            m = md.malha_final(est, fino=False); V = np.asarray(m.vertices, dtype=float); F = np.asarray(m.faces, dtype=int)
            if len(F) > 9000: V, F = mv._simplificar(V, F, 6000)
            x['_mb_id'] = id(est); x['_mb'] = (V, F); x['_mb_lim'] = est.limites()
        V, F = x['_mb']; lim = x['_mb_lim']; vs = self.proj.vars; N = lambda k, p=0.0: float(md.num(d.get(k), vs, p))
        if d['op'] == 'mover': V2 = V + np.array([N('dx'), N('dy'), N('dz')])
        else:
            c = (lim[0] + lim[1]) / 2; f = np.array([N('x', 100), N('y', 100), N('z', 100)]) / 100.0
            if f.min() <= 0: raise md.ErroModelo('escala precisa ser maior que zero')
            V2 = c + (V - c) * f
        return _Malha(V2, F)

    def _alcas(self, d=None):
        """Monta os pontos de puxar da ferramenta aberta (quadradinho amarelo = tamanho, bolinha azul = subir/descer) e diz se o corpo vermelho pode ser arrastado."""
        v = self.vista; v.corpo_arrastavel = False; v.peca_arrastavel = False; v.plano_fixo = None; A = []
        if self.form and self.editor is None and d is not None and v.fantasma is not None:
            try:
                op = d['op']; vs = self.proj.vars; N = lambda k, p=0.0: float(md.num(d.get(k), vs, p))
                X, Y, Z = np.eye(3); EV = {'x': X, 'y': Y, 'z': Z}; RAD = {'x': Y, 'y': X, 'z': X}; AM = (255, 196, 70); AZ = (104, 164, 250)
                fmn, fmx = v.fantasma[0].min(0), v.fantasma[0].max(0)

                def tam(campo, base, eixo, fator):
                    A.append(dict(id='t:' + campo, campo=campo, p=base + eixo * (N(campo) / fator), eixo=eixo, base=base, fator=fator, cor=AM, forma='q'))

                def sobe(o):
                    folga = max(6.0, float(fmx[2] - fmn[2]) * 0.3); p = np.array([o[0], o[1], fmx[2] + folga]); A.append(dict(id='z', p=p, eixo=Z, base=p - Z * folga, cor=AZ, forma='c'))

                if op in ARRASTA_POS:
                    o = np.array([N('x'), N('y'), N('z')]); v.corpo_arrastavel = True
                    if op in ('caixa', 'cunha'):
                        g = np.radians(N('giro')); ax = np.array([np.cos(g), np.sin(g), 0.0]); ay = np.array([-np.sin(g), np.cos(g), 0.0]); m = o + Z * (N('altura') / 2)
                        tam('largura', m, ax, 2); tam('profundidade', m, ay, 2); tam('altura', o, Z, 1)
                    elif op in ('cilindro', 'tubo', 'prisma', 'cone'):
                        e = EV[d.get('eixo', 'z')]; r = RAD[d.get('eixo', 'z')]
                        tam('diametro', o if op == 'cone' else o + e * (N('altura') / 2), r, 2); tam('altura', o, e, 1)
                    elif op == 'esfera': tam('diametro', o, X, 2)
                    elif op == 'toro': tam('diametro', o, RAD[d.get('eixo', 'z')], 2)
                    sobe(o)
                elif op == 'furo':
                    k = 'xyz'.index(d.get('direcao', '-z')[1]); v.corpo_arrastavel = True; v.plano_fixo = k           # o furo desliza na face em que ele entra
                    if all(d.get(c) != '' for c in 'xyz'): tam('diametro', np.array([N('x'), N('y'), N('z')]), np.eye(3)[(k + 1) % 3], 2)
                elif op == 'mover':
                    v.corpo_arrastavel = True; v.peca_arrastavel = True; sobe((fmn + fmx) / 2)
                elif op == 'escalar':
                    lim = self.form['x']['_mb_lim']; c = (lim[0] + lim[1]) / 2; canto = np.array([fmx[0], fmx[1], fmx[2]]); r = float(np.linalg.norm(canto - c))
                    if r > 1e-6: A.append(dict(id='esc', p=canto, eixo=(canto - c) / r, base=c, r=r, cor=AM, forma='q'))
            except Exception: A = []
        v.definir_alcas(A)

    def _arrastou(self, fase, alvo, p, p0, estado=0):
        """A vista avisa que o usuario esta arrastando a forma ou uma alca: as medidas do formulario acompanham o mouse."""
        if not self.form or self.editor is not None: return
        fv = self.form['v']; op = self.form['op']
        if fase == 'ini':
            self._arr = None
            try: d = self._ler_form()
            except Exception: return
            v0 = {}
            for prm in md.OPS[op]['p']:
                if prm[1] == 'n' and d.get(prm[0]) != '':
                    try: v0[prm[0]] = float(md.num(d.get(prm[0]), self.proj.vars, 0.0))
                    except Exception: pass
            a = next((dict(q) for q in self.vista.alcas if q['id'] == alvo), None); self._arr = dict(v0=v0, a=a, t=0.0); return
        g = getattr(self, '_arr', None)
        if g is None: return
        if fase == 'fim':
            self._arr = None; self._previa()
            self._status('Pronto. Confira as medidas à direita e clique %s.' % ('SALVAR MUDANÇA' if self.form['indice'] is not None else 'APLICAR'), T.VERDE); return
        v0 = g['v0']; a = g['a']; passo = 0.1 if estado & 0x0004 else 0.5; grade = lambda x: round(round(float(x) / passo) * passo, 3)

        def por(campo, valor):
            if campo in fv and campo in v0:
                s = '%g' % valor
                if fv[campo].get() != s: fv[campo].set(s)

        dl = np.asarray(p, dtype=float) - np.asarray(p0, dtype=float)
        if alvo == 'corpo':
            for j, c in enumerate(('dx', 'dy', 'dz') if op == 'mover' else 'xyz'):
                if abs(dl[j]) > 1e-9: por(c, grade(v0.get(c, 0.0) + dl[j]))
        elif alvo == 'z': c = 'dz' if op == 'mover' else 'z'; por(c, grade(v0.get(c, 0.0) + dl[2]))
        elif alvo == 'esc' and a:
            k = max(0.05, float((np.asarray(p, dtype=float) - a['base']) @ a['eixo']) / a['r'])
            for c in 'xyz': por(c, round(v0.get(c, 100.0) * k, 1))
        elif alvo.startswith('t:') and a: por(a['campo'], max(passo, grade(a['fator'] * float((np.asarray(p, dtype=float) - a['base']) @ a['eixo']))))
        self._status('  '.join('%s %s' % (md.OPS[op]['p'][i][3], fv[md.OPS[op]['p'][i][0]].get()) for i in range(len(md.OPS[op]['p'])) if md.OPS[op]['p'][i][0] in v0 and md.OPS[op]['p'][i][1] == 'n')[:150] + '   (Ctrl = passo fino)')
        if self._previa_job: self.after_cancel(self._previa_job); self._previa_job = None
        if time.time() - g['t'] >= 0.05:
            self._previa(); g['t'] = time.time()                              # a forma vermelha acompanha o mouse
        else: self._previa_job = self.after(60, self._previa)

    def _aplicar(self):
        if not self.form: return
        try: d = self._ler_form()
        except md.ErroModelo as e: self.l_erro.config(text=str(e)); return
        except Exception as e: self.l_erro.config(text='Confira os números: %s' % str(e)[:100]); return
        if self._previa_job: self.after_cancel(self._previa_job); self._previa_job = None          # senao a previa atrasada apagaria a mensagem de erro
        i = self.form['indice']; self._cursor('watch')
        try:
            if i is None: self.proj.adicionar(d)
            else:
                d.pop('op'); self.proj.editar(i, d)
        except md.ErroModelo as e: self.l_erro.config(text=str(e)); return
        except Exception as e: self.l_erro.config(text='%s: %s' % (type(e).__name__, str(e)[:160])); return
        finally: self._cursor('')
        era_vazio = len(self.proj.passos) == 1 and i is None
        self._fechar_form(False); self._atualizar(era_vazio); self._salvar_logo(); self._status('Feito em %.1f s. Não gostou? Desfazer (Ctrl+Z) ou clique no passo para mudar as medidas.' % self.proj.tempo, T.VERDE)

    def _fechar_form(self, atualizar=True):
        if self._previa_job: self.after_cancel(self._previa_job); self._previa_job = None
        if self.editor is not None: self._fechar_editor()
        tinha = self.form is not None; self.form = None; self.vista.definir_fantasma(None); self._arr = None; self._alcas(None)
        if self.vista.cget('cursor'): self.vista.config(cursor='')
        for bt in self.bt_op.values(): bt.marcar(False)
        if tinha and atualizar: self._passos(); self._painel_info()

    def _cursor(self, c):
        try: self.winfo_toplevel().config(cursor=c); self.update_idletasks()
        except Exception: pass

    # ---- desenho 2D ----
    def _desenhar(self, nome, sec=None):
        fm = self.form; op = fm['op']; lim = self.proj.est.limites() if not self.proj.est.vazio else None; ref = None; eixos = ('→', '↑'); eixo = False
        if op == 'extrudar':
            pl = fm['x']['_op_plano'].get(fm['v']['plano'].get(), 'xy'); a, b = {'xy': (0, 1), 'xz': (0, 2), 'yz': (1, 2)}[pl]; eixos = ('XYZ'[a], 'XYZ'[b])
            if lim is not None: ref = (lim[0][a], lim[0][b], lim[1][a], lim[1][b])
            tit = 'Desenho para extrudar — plano %s' % NOME_OPCAO[pl].split(' → ')[0].lower()
        elif op == 'revolucao': eixos = ('distância do eixo', 'altura'); eixo = True; tit = 'Desenho de MEIO perfil (só do lado direito do eixo laranja)'
        elif op == 'loft':
            eixos = ('X', 'Y'); tit = 'Desenho da seção %d' % (sec + 1)
            if lim is not None: ref = (lim[0][0], lim[0][1], lim[1][0], lim[1][1])
        else: tit = 'Desenho da seção que vai percorrer o caminho (centro = o caminho)'
        perfil = fm['x']['secoes'][sec].get('perfil', []) if sec is not None else fm['x'][nome]
        self.f_vista.pack_forget(); self.vista.definir_fantasma(None)
        def ok(figs):
            if sec is not None: fm['x']['secoes'][sec]['perfil'] = figs; self._fechar_editor(); self._secoes()
            else: fm['x'][nome] = figs; self._fechar_editor(); self._resumo_perfil(nome)
            self._previa_logo()
        self.editor = me.EditorEsboco(self.meio, perfil, self.proj.vars, ok, self._fechar_editor, tit, ref, eixo, eixos); self.editor.pack(fill='both', expand=True)

    def _fechar_editor(self):
        if self.editor is not None: self.editor.destroy(); self.editor = None
        self.f_vista.pack(fill='both', expand=True)

    # ============================ acoes na receita ============================
    def _executar(self, fn, msg=''):
        """Roda uma acao do projeto mostrando erro amigavel; atualiza e salva."""
        if not self._motor_ok(): return False
        self._cursor('watch')
        try: fn()
        except md.ErroModelo as e: self._status(str(e), T.VERM); return False
        except Exception as e: self._status('%s: %s' % (type(e).__name__, str(e)[:160]), T.VERM); return False
        finally: self._cursor('')
        self._fechar_form(False); self._atualizar(); self._salvar_logo()
        if msg: self._status(msg, T.VERDE)
        return True

    def desfazer(self): self._executar(self.proj.desfazer, 'Desfeito.')
    def refazer(self): self._executar(self.proj.refazer, 'Refeito.')
    def remover_passo(self, i): self._executar(lambda: self.proj.remover(i), 'Passo apagado (Desfazer traz de volta).')
    def alternar_passo(self, i): self._executar(lambda: self.proj.alternar(i), 'Passo ligado/desligado.')

    def nova_variavel(self):
        n = simpledialog.askstring('Nova variável', 'Nome da variável (sem espaços, ex.: folga, largura):', parent=self)
        if not n: return
        v = simpledialog.askstring('Nova variável', 'Valor de "%s" (mm):' % n.strip(), initialvalue='10', parent=self)
        if v is not None: self.definir_variavel(n.strip(), v)

    def definir_variavel(self, nome, valor): self._executar(lambda: self.proj.definir_var(nome, valor), 'Variável %s.' % ('apagada' if valor in ('', None) else 'atualizada: a peça foi refeita'))

    # ============================ arquivos ============================
    def abrir_dialogo(self):
        c = filedialog.askopenfilename(parent=self, initialdir=self.pasta if os.path.isdir(self.pasta) else None, title='Abrir peça ou projeto',
                                       filetypes=[('Projetos e modelos 3D', '*.modelo.json *.stl *.3mf *.obj *.step *.stp'), ('Todos', '*.*')])
        if c: self.abrir_arquivo(c)

    def abrir_arquivo(self, c):
        """Projeto (.modelo.json) abre como estava; STL/3MF/OBJ/STEP vira uma peca nova que comeca importando o arquivo."""
        if not self._motor_ok(): raise md.ErroModelo('o motor de modelagem ainda esta carregando; tente de novo em alguns segundos')
        if not os.path.isfile(c): raise md.ErroModelo('arquivo nao encontrado: %s' % c)
        self._fechar_form(); self._cursor('watch')
        try:
            if c.lower().endswith('.json'):
                for i, q in enumerate(self.projs):
                    if q.arquivo and os.path.abspath(q.arquivo) == os.path.abspath(c): self.ativar(i); return q
                p = md.Projeto.abrir(c, self.cfg.get('permitir_codigo', False))
            else:
                p = md.Projeto(os.path.splitext(os.path.basename(c))[0][:40]); p.permitir_codigo = self.cfg.get('permitir_codigo', False); p.adicionar(dict(op='importar', caminho=c)); p._desf = []
        finally: self._cursor('')
        if len(self.projs) == 1 and not self.projs[0].passos and not self.projs[0].arquivo: self.projs = [p]; self.at = 0
        else: self.projs.append(p); self.at = len(self.projs) - 1
        self._abas(); self._atualizar(True); self._salvar_logo(); self._status('Aberto: %s' % p.nome, T.VERDE); return p

    def pegar_da_mesa(self, idx=None):
        mesa = getattr(self.app, 'painel_mesa', None)
        if mesa is None: raise md.ErroModelo('a Mesa 3D nao esta disponivel')
        pc = mesa.sel if idx is None else mesa.pecas[idx]
        if pc is None: raise md.ErroModelo('selecione uma peca na Mesa 3D primeiro')
        p = self.abrir_arquivo(pc.caminho)
        if abs(getattr(pc, 'esc', 100.0) - 100.0) > 0.01: p.editar(0, dict(escala=pc.esc)); p._desf = []; self._atualizar(True)
        return p

    def exportar_dialogo(self):
        if self.proj.est.vazio: self._status('Ainda não há peça para exportar.', T.AMARELO); return
        c = filedialog.asksaveasfilename(parent=self, title='Exportar peça', initialfile=re.sub(r'[^\w\- ]', '_', self.proj.nome), defaultextension='.stl',
                                         filetypes=[('STL (para imprimir)', '*.stl'), ('STEP (sólido exato, abre no Fusion/FreeCAD)', '*.step'), ('3MF', '*.3mf'), ('OBJ', '*.obj')])
        if not c: return
        try: self.proj.exportar(c); self._status('Exportado: %s' % c, T.VERDE)
        except Exception as e: self._status(str(e), T.VERM)

    def _stl_novo(self):
        os.makedirs(self.pasta_stl, exist_ok=True); base = re.sub(r'[^\w\-]', '_', self.proj.nome).strip('_') or 'peca'; n = 1
        while os.path.exists(os.path.join(self.pasta_stl, '%s_%d.stl' % (base, n))): n += 1
        return os.path.join(self.pasta_stl, '%s_%d.stl' % (base, n))

    def para_mesa(self, mostrar=True):
        """Grava o STL da peca e poe na Mesa 3D (pronta para fatiar e imprimir)."""
        if self.proj.est.vazio: self._status('Ainda não há peça. Crie uma forma primeiro.', T.AMARELO); return None
        try:
            self._cursor('watch'); c = self.proj.exportar(self._stl_novo())
        except Exception as e: self._status(str(e), T.VERM); return None
        finally: self._cursor('')
        mesa = getattr(self.app, 'painel_mesa', None)
        if mesa is not None:
            mesa.add_arquivo(c)
            if mostrar: self.app.aba('Mesa 3D')
        self._status('Peça gravada em %s%s' % (c, ' e colocada na Mesa 3D.' if mesa is not None else '.'), T.VERDE); return c

    # ============================ IA ============================
    def janela_ia(self):
        w = tk.Toplevel(self); w.title('Modelar com IA'); w.configure(bg=T.PAINEL); w.geometry('560x470'); w.transient(self.winfo_toplevel())
        T.rotulo(w, 'Modelar com a IA (MCP)', T.TXT, 14, True).pack(anchor='w', padx=18, pady=(16, 4))
        T.rotulo(w, 'Tudo o que você faz nesta aba, a IA também consegue fazer pelo MCP "ender-impressora" (ferramentas ender_modelar_*). '
                    'Ela cria os passos, pede uma imagem da peça para conferir e corrige.\n\n'
                    'Como usar:\n1. Deixe este programa aberto.\n2. Abra o seu cliente de IA com MCP (uma conversa nova, para ele enxergar as ferramentas).\n'
                    '3. Peça, por exemplo:\n   "Modele um suporte de celular de 80 mm de largura, com base de 60 mm e encosto inclinado."\n'
                    '   "Olhe esta foto (caminho do arquivo) e modele essa peça; ela tem 5 cm de altura."\n'
                    '4. A peça aparece aqui, passo a passo. Você pode mudar qualquer medida depois.\n\n'
                    'A configuração do MCP (token, comando) fica na aba IA / MCP.', T.DIM, 10, wraplength=520, justify='left').pack(anchor='w', padx=18)
        v = tk.BooleanVar(value=bool(self.cfg.get('permitir_codigo')))
        def troca():
            self.cfg['permitir_codigo'] = bool(v.get()); self._gravar_cfg()
            for p in self.projs: p.permitir_codigo = self.cfg['permitir_codigo']
        T.marca(w, 'Permitir que a IA use CÓDIGO livre (formas que os botões não fazem)', v, troca).pack(anchor='w', padx=14, pady=(14, 2))
        T.rotulo(w, 'Desligado por padrão: código roda no seu computador. Ligue só se quem está usando o MCP é você/sua IA.', T.AMARELO, 8, wraplength=520, justify='left').pack(anchor='w', padx=18)
        T.botao(w, 'Fechar', w.destroy, 'normal').pack(anchor='e', padx=18, pady=14)

    # ============================ API / MCP ============================
    def _achar_proj(self, ref):
        if ref in (None, ''): return self.at
        if isinstance(ref, (int, float)) or (isinstance(ref, str) and ref.isdigit()):
            i = int(ref) - 1
            if 0 <= i < len(self.projs): return i
            raise md.ErroModelo('nao existe o projeto %s (ha %d)' % (ref, len(self.projs)))
        for i, p in enumerate(self.projs):
            if p.nome.lower() == str(ref).lower(): return i
        raise md.ErroModelo('nao existe projeto chamado "%s". Abertos: %s' % (ref, ', '.join(p.nome for p in self.projs)))

    def _lista_proj(self):
        return [dict(n=i + 1, nome=p.nome, ativo=i == self.at, passos=len(p.passos), vazio=p.est.vazio, tamanho=None if p.est.vazio else [round(float(x), 2) for x in (p.est.limites()[1] - p.est.limites()[0])]) for i, p in enumerate(self.projs)]

    def imagem_png(self, vista='3d', largura=900, altura=700, az=None, el=None, numeros=None, medidas=True):
        b = io.BytesIO(); self.vista.render(largura, altura, vista, az, el, numeros, medidas).save(b, 'PNG'); return b.getvalue()

    def imagem_4vistas(self, largura=1200, altura=900, numeros=None):
        from PIL import Image
        w, h = largura // 2, altura // 2; g = Image.new('RGB', (w * 2, h * 2))
        for k, vs in enumerate(('3d', 'frente', 'direita', 'cima')): g.paste(self.vista.render(w, h, vs, None, None, numeros if k == 0 else None, True), ((k % 2) * w, (k // 2) * h))
        b = io.BytesIO(); g.save(b, 'PNG'); return b.getvalue()

    def api(self, d):
        """Porta unica da API (/api/modelar). d = {'acao': ..., ...}. Ver MANUAL_MCP.md."""
        ac = str(d.get('acao', 'estado'))
        try:
            if ac == 'ajuda': return dict(ok=True, **(md.ajuda(d.get('op')) if d.get('op') else md.ajuda()))
            if not self._pronto:
                md.motor()
                self._esperar_motor()
            if ac == 'projetos': return dict(ok=True, projetos=self._lista_proj())
            if ac == 'mostrar':
                self.app.aba('Modelar'); return dict(ok=True, projetos=self._lista_proj())
            if ac == 'novo':
                self.novo_projeto(str(d['nome'])[:40] if d.get('nome') else None); return dict(ok=True, projetos=self._lista_proj())
            if ac == 'abrir_arquivo':
                p = self.abrir_arquivo(str(d.get('caminho', ''))); return dict(ok=True, projetos=self._lista_proj(), **p.estado(False))
            if ac == 'pegar_da_mesa':
                p = self.pegar_da_mesa(int(d['id']) - 1 if d.get('id') else None); return dict(ok=True, projetos=self._lista_proj(), **p.estado(False))
            i = self._achar_proj(d.get('projeto'))
            if i != self.at: self.ativar(i)
            p = self.proj; det = bool(d.get('detalhe', False))
            if ac == 'ativar': return dict(ok=True, projetos=self._lista_proj())
            if ac == 'fechar': self.fechar_projeto(i, perguntar=False); return dict(ok=True, projetos=self._lista_proj())
            if ac == 'renomear': self.renomear(i, str(d.get('nome', ''))); return dict(ok=True, projetos=self._lista_proj())
            if ac == 'estado': return dict(ok=True, **p.estado(d.get('detalhe', True)))
            if ac in ('imagem', 'imagens'):
                self._fechar_form()
                if ac == 'imagens': png = self.imagem_4vistas(int(d.get('largura', 1200)), int(d.get('altura', 900)), d.get('numeros'))
                else: png = self.imagem_png(str(d.get('vista', '3d')), int(d.get('largura', 900)), int(d.get('altura', 700)), d.get('az'), d.get('el'), d.get('numeros'), bool(d.get('medidas', True)))
                return dict(ok=True, png_base64=base64.b64encode(png).decode(), projeto=p.nome)
            if ac == 'exportar':
                c = d.get('caminho')
                if not c:
                    fmt = str(d.get('formato', 'stl')).lower().strip('.'); c = os.path.splitext(self._stl_novo())[0] + '.' + fmt
                p.exportar(str(c), bool(d.get('assentar', True))); return dict(ok=True, arquivo=str(c))
            if ac == 'para_mesa':
                c = self.para_mesa(mostrar=bool(d.get('mostrar', False)))
                if not c: return dict(ok=False, erro=self.l_status.cget('text'))
                return dict(ok=True, arquivo=c, dica='A peca esta na Mesa 3D. Use ender_mesa_ver / ender_mesa_fatiar para continuar.')
            self._fechar_form()
            feitos = None
            if ac == 'passo': p.adicionar({k: v for k, v in d.items() if k not in ('acao', 'projeto', 'posicao', 'detalhe')}, d.get('posicao'))
            elif ac == 'passos':
                feitos = 0
                for n, ps in enumerate(d.get('lista') or []):
                    try: p.adicionar(ps); feitos += 1
                    except md.ErroModelo as e:
                        self._atualizar(); self._salvar_logo()
                        return dict(ok=False, erro='passo %d da lista (%s): %s' % (n + 1, ps.get('op') if isinstance(ps, dict) else '?', e), aplicados=feitos, **p.estado(False))
            elif ac == 'editar': p.editar(int(d['n']) - 1, d.get('mudancas') or {})
            elif ac == 'remover': p.remover(int(d['n']) - 1)
            elif ac == 'alternar': p.alternar(int(d['n']) - 1)
            elif ac == 'limpar': p.limpar()
            elif ac == 'variavel': p.definir_var(d.get('nome', ''), d.get('valor'))
            elif ac == 'desfazer': p.desfazer()
            elif ac == 'refazer': p.refazer()
            else: return dict(ok=False, erro='acao desconhecida: %s' % ac)
            self._atualizar(len(p.passos) <= 1); self._salvar_logo()
            return dict(ok=True, **({'aplicados': feitos} if feitos is not None else {}), **p.estado(det))
        except md.ErroModelo as e: return dict(ok=False, erro=str(e))
        except KeyError as e: return dict(ok=False, erro='falta o parametro %s' % e)
        except Exception as e: return dict(ok=False, erro='%s: %s' % (type(e).__name__, str(e)[:200]))


if __name__ == '__main__':
    import types
    raiz = tk.Tk(); raiz.title('Modelar (teste fora do programa)'); raiz.configure(bg=T.BG); raiz.geometry('1280x860')
    app = types.SimpleNamespace(pasta=os.path.dirname(os.path.abspath(__file__)), painel_mesa=None, aba=lambda n: None)
    PainelModelar(raiz, app).pack(fill='both', expand=True); raiz.mainloop()
