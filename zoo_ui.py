"""Aba "Criar peça": descreve a peca em texto, a Zoo desenha, vira STL e entra na Mesa 3D."""
import os, shutil, threading, time
import tkinter as tk
from tkinter import filedialog, messagebox
import zoo_cad as zc

BG, CARD, TXT, DIM, VERDE, LARANJA, AZUL, VERM, AMARELO = '#0D1117', '#151B24', '#EAF0F8', '#93A0B5', '#38D39F', '#FF8A3D', '#5AB0FF', '#FF6B6B', '#F7C948'
LINHA = '#263041'


class PainelZoo(tk.Frame):
    def __init__(self, pai, app):
        super().__init__(pai, bg=BG)
        self.app = app; self.cfg = zc.carregar_cfg(); self.chaves = zc.carregar_chaves(); self._tratado = None; self._msg_cli = ''; self._lista_n = -1
        self._montar(); self.recarregar_lista()

    def _montar(self):
        a = self.app
        corpo = tk.Frame(self, bg=BG); corpo.pack(fill='both', expand=True, padx=18, pady=8)
        corpo.columnconfigure(0, weight=3, uniform='z'); corpo.columnconfigure(1, weight=2, uniform='z')
        esq = a.card(corpo); esq.grid(row=0, column=0, sticky='nsew', padx=(0, 7)); dir_ = a.card(corpo); dir_.grid(row=0, column=1, sticky='nsew', padx=(7, 0))
        a.rotulo(esq, 'DESCREVA A PEÇA (a Zoo desenha em CAD e vira STL)').pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(esq, text='Seja específico com as medidas. Ex.: "suporte de parede em L, 60 x 20 x 5 mm, com dois furos de 4 mm" ou "caixa com tampa de encaixe, 80 x 50 x 30 mm, parede de 2 mm".', bg=CARD, fg=DIM, font=('Segoe UI', 9), wraplength=560, justify='left').pack(anchor='w', padx=16)
        self.txt = tk.Text(esq, height=5, bg=BG, fg=TXT, insertbackground=TXT, relief='flat', font=('Segoe UI', 11), wrap='word'); self.txt.pack(fill='x', padx=16, pady=6)
        r = tk.Frame(esq, bg=CARD); r.pack(fill='x', padx=16)
        self.bcriar = a.botao(r, 'CRIAR A PEÇA', self.criar, VERDE); self.bcriar.pack(side='left')
        self.v_mesa = tk.BooleanVar(value=True)
        tk.Checkbutton(r, text='pôr na Mesa 3D quando ficar pronta', variable=self.v_mesa, bg=CARD, fg=TXT, selectcolor=LINHA, activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0, font=('Segoe UI', 10)).pack(side='left', padx=14)
        self.lst = tk.Label(esq, text='', bg=CARD, fg=AMARELO, font=('Segoe UI', 11, 'bold'), wraplength=580, justify='left', anchor='w'); self.lst.pack(fill='x', padx=16, pady=(10, 4))
        a.rotulo(esq, 'PEÇAS JÁ CRIADAS').pack(fill='x', padx=16, pady=(8, 2))
        self.lista = tk.Listbox(esq, bg=BG, fg=TXT, selectbackground='#2f6fb5', activestyle='none', bd=0, highlightthickness=0, font=('Segoe UI', 10), height=8, exportselection=False); self.lista.pack(fill='x', padx=16)
        self.lista.bind('<Double-Button-1>', lambda e: self.por_na_mesa())
        r = tk.Frame(esq, bg=CARD); r.pack(fill='x', padx=16, pady=(6, 12))
        a.botao(r, 'Pôr na Mesa 3D', self.por_na_mesa, AZUL).pack(side='left'); a.botao(r, 'Abrir a pasta', self.abrir_pasta, LINHA).pack(side='left', padx=6); a.botao(r, 'Apagar', self.apagar, LINHA).pack(side='left')
        # ---- direita ----
        a.rotulo(dir_, 'CHAVES DA ZOO (uma por linha, sem limite)').pack(fill='x', padx=16, pady=(12, 2))
        self.lch = tk.Label(dir_, text='', bg=CARD, fg=TXT, font=('Segoe UI', 9, 'bold'), anchor='w'); self.lch.pack(fill='x', padx=16)
        rt = tk.Frame(dir_, bg=CARD); rt.pack(fill='x', padx=16)
        self.tch = tk.Text(rt, height=4, bg=BG, fg=TXT, insertbackground=TXT, relief='flat', font=('Consolas', 9), wrap='none'); self.tch.pack(side='left', fill='x', expand=True)
        sb = tk.Scrollbar(rt, command=self.tch.yview); sb.pack(side='left', fill='y'); self.tch.config(yscrollcommand=sb.set); self.tch.insert('1.0', '\n'.join(self.chaves))
        self.tch.bind('<KeyRelease>', lambda e: self.chaves_editou()); self.tch.bind('<<Paste>>', lambda e: self.after(50, self.chaves_editou))
        self.v_alea = tk.BooleanVar(value=self.cfg['aleatorio']); self.v_api = tk.BooleanVar(value=self.cfg['permitir_mcp'])
        for t, v in (('usar as chaves em ordem aleatória', self.v_alea), ('permitir que a IA/celular (API e MCP) crie peças com as minhas chaves', self.v_api)):
            tk.Checkbutton(dir_, text=t, variable=v, command=self.salvar, bg=CARD, fg=TXT, selectcolor=LINHA, activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 9), wraplength=330, justify='left').pack(fill='x', padx=14)
        tk.Label(dir_, text='As chaves ficam só no arquivo _PRIVADO_zoo.json. Se uma esgotar o crédito ou for recusada, o programa usa a próxima. Cada peça gasta tempo da sua conta Zoo (confira o plano grátis e o preço na sua conta).', bg=CARD, fg=DIM, font=('Segoe UI', 8), wraplength=340, justify='left').pack(anchor='w', padx=16, pady=(4, 0))
        a.rotulo(dir_, 'PROGRAMA DA ZOO (zoo.exe) — converte o desenho em STL').pack(fill='x', padx=16, pady=(12, 2))
        self.lcli = tk.Label(dir_, text='', bg=CARD, fg=TXT, font=('Segoe UI', 9), wraplength=340, justify='left', anchor='w'); self.lcli.pack(fill='x', padx=16)
        r = tk.Frame(dir_, bg=CARD); r.pack(fill='x', padx=16, pady=4)
        a.botao(r, 'Baixar o oficial (confere SHA-256)', self.baixar, AMARELO).pack(side='left'); a.botao(r, 'Escolher…', self.escolher_cli, LINHA).pack(side='left', padx=6)
        tk.Label(dir_, text='O download vem do GitHub oficial da Zoo (KittyCAD/cli, ~120 MB) e só é guardado se o SHA-256 bater.', bg=CARD, fg=DIM, font=('Segoe UI', 8), wraplength=340, justify='left').pack(anchor='w', padx=16, pady=(0, 12))
        self.atualizar_rotulos()

    # ---------- configuracao ----------
    def chaves_editou(self):
        self.chaves = zc.lista_chaves(self.tch.get('1.0', 'end')); zc.salvar_chaves(self.chaves); self.atualizar_rotulos()

    def salvar(self):
        self.cfg['aleatorio'] = bool(self.v_alea.get()); self.cfg['permitir_mcp'] = bool(self.v_api.get()); zc.salvar_cfg(self.cfg)

    def atualizar_rotulos(self):
        st = zc.status_chaves(self.chaves)
        self.lch.config(text='Chaves: %d%s' % (st['total'], (' (%d de molho: recusadas ou sem crédito)' % st['de_molho']) if st['de_molho'] else ''))
        cli = zc.achar_cli(self.cfg)
        self.lcli.config(text=(self._msg_cli or (('Encontrado: ' + cli) if cli else 'Ainda não encontrei o zoo.exe. Baixe o oficial ou escolha onde ele está.')), fg=VERDE if cli else AMARELO)

    def baixar(self):
        if self._msg_cli.startswith('Baixando'): return
        self._msg_cli = 'Baixando...'
        def run():
            try:
                dest, tag = zc.baixar_cli(progresso=lambda t: setattr(self, '_msg_cli', t))
                self.cfg['cli'] = dest; zc.salvar_cfg(self.cfg); self._msg_cli = 'zoo.exe %s baixado e conferido (SHA-256 ok).' % tag
            except Exception as e: self._msg_cli = 'Não deu para baixar: %s' % e
        threading.Thread(target=run, daemon=True).start()

    def escolher_cli(self):
        a = filedialog.askopenfilename(title='Onde está o zoo.exe?', filetypes=[('Programa', '*.exe'), ('Todos', '*.*')])
        if a: self.cfg['cli'] = a; zc.salvar_cfg(self.cfg); self._msg_cli = ''; self.atualizar_rotulos()

    # ---------- criar ----------
    def criar(self):
        if self.app.zoo.estado == 'rodando': return
        prompt = self.txt.get('1.0', 'end').strip()
        if not self.chaves: messagebox.showinfo('Criar peça', 'Cole pelo menos uma chave da Zoo (caixa da direita).', parent=self); return
        self._tratado = None; self.app.zoo.origem = 'tela'
        self.app.zoo.iniciar(prompt, self.cfg, self.chaves)
        self.atualizar()

    def atualizar(self):
        t = self.app.zoo; st = t.status()
        self.bcriar.config(state='disabled' if st['estado'] == 'rodando' else 'normal', text='CRIANDO…' if st['estado'] == 'rodando' else 'CRIAR A PEÇA', bg='#1C3B30' if st['estado'] == 'rodando' else VERDE)
        txt = st['msg']
        if st['estado'] == 'rodando' and st['segundos'] is not None: txt += '  (%d s)' % st['segundos']
        self.lst.config(text=txt, fg=VERM if st['estado'] == 'erro' else (VERDE if st['estado'] == 'pronto' else AMARELO))
        if st['estado'] == 'pronto' and self._tratado != st['stl']:
            self._tratado = st['stl']; self.recarregar_lista()
            if (t.auto_mesa if t.origem == 'api' else self.v_mesa.get()): self.por_arquivo(st['stl'])
        self.atualizar_rotulos()

    # ---------- lista ----------
    def pastas(self):
        out = []
        if os.path.isdir(zc.PECAS):
            for d in sorted(os.listdir(zc.PECAS), reverse=True):
                s = os.path.join(zc.PECAS, d, 'saida')
                if os.path.isdir(s):
                    stls = [f for f in os.listdir(s) if f.lower().endswith('.stl')]
                    if stls: out.append((d, os.path.join(s, stls[0])))
        return out

    def recarregar_lista(self):
        self._itens = self.pastas(); self.lista.delete(0, 'end')
        for d, stl in self._itens: self.lista.insert('end', d)

    def _sel(self):
        s = self.lista.curselection()
        return self._itens[s[0]] if s and s[0] < len(self._itens) else None

    def por_arquivo(self, stl):
        try:
            self.app.painel_mesa.add_arquivo(stl); self.app.aba('Mesa 3D'); self.app.say('Peça da Zoo posta na Mesa 3D: ' + os.path.basename(os.path.dirname(os.path.dirname(stl))))
        except Exception as e: self.app.say('Não consegui pôr na mesa: %s' % e)

    def por_na_mesa(self):
        it = self._sel()
        if it: self.por_arquivo(it[1])

    def abrir_pasta(self):
        it = self._sel()
        if it:
            try: os.startfile(os.path.dirname(os.path.dirname(it[1])))
            except Exception: pass

    def apagar(self):
        it = self._sel()
        if it and messagebox.askyesno('Apagar', 'Apagar a peça %s (STL e desenho)?' % it[0], parent=self):
            shutil.rmtree(os.path.join(zc.PECAS, it[0]), ignore_errors=True); self.recarregar_lista()
