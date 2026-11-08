"""Aba "Avançado": tela dos ajustes de avancado.py (ver la o que cada coisa faz)."""
import os, json, subprocess
import tkinter as tk
from tkinter import messagebox
import avancado as av
import perfil

BG, CARD, TXT, DIM, VERDE, LARANJA, AZUL, VERM, AMARELO = '#0D1117', '#151B24', '#EAF0F8', '#93A0B5', '#38D39F', '#FF8A3D', '#5AB0FF', '#FF6B6B', '#F7C948'
LINHA = '#263041'


class PainelAvancado(tk.Frame):
    def __init__(self, pai, app):
        super().__init__(pai, bg=BG)
        self.app = app; self._ocupado = False; self._id = None
        self.v = {}
        self._montar(); self.recarregar()

    # ---------- montagem ----------
    def _montar(self):
        a = self.app
        corpo = tk.Frame(self, bg=BG); corpo.pack(fill='both', expand=True, padx=18, pady=8)
        corpo.columnconfigure(0, weight=1, uniform='c'); corpo.columnconfigure(1, weight=1, uniform='c')
        esq = a.card(corpo); esq.grid(row=0, column=0, sticky='nsew', padx=(0, 7)); dir_ = a.card(corpo); dir_.grid(row=0, column=1, sticky='nsew', padx=(7, 0))
        self.v['ativo'] = tk.BooleanVar()
        tk.Checkbutton(esq, text='USAR OS AJUSTES AVANÇADOS desta aba', variable=self.v['ativo'], command=self.mudou, bg=CARD, fg=VERDE, selectcolor=LINHA, activebackground=CARD, activeforeground=VERDE, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 11, 'bold')).pack(fill='x', padx=14, pady=(12, 0))
        tk.Label(esq, text='Desligado = a impressora faz tudo do jeito de sempre. Ligado = vale o que está marcado aqui (o arquivo é preparado de novo na hora).', bg=CARD, fg=DIM, font=('Segoe UI', 8), wraplength=470, justify='left').pack(anchor='w', padx=16, pady=(0, 4))
        def sec(t): a.rotulo(esq, t).pack(fill='x', padx=16, pady=(8, 2))
        def chk(sec_, chave, texto, aviso=''):
            var = tk.BooleanVar(); self.v[(sec_, chave)] = var
            tk.Checkbutton(esq, text=texto, variable=var, command=self.mudou, bg=CARD, fg=TXT, selectcolor=LINHA, activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 10)).pack(fill='x', padx=14)
            if aviso: tk.Label(esq, text=aviso, bg=CARD, fg=AMARELO, font=('Segoe UI', 8)).pack(anchor='w', padx=36)
        sec('NO COMEÇO')
        chk('inicio', 'home', 'Fazer HOME (zerar os eixos com o sensor)', 'Desmarcar só se a impressora JÁ está com Home feito, senão ela recusa mover.')
        chk('inicio', 'mapa', 'Carregar o mapa de nivelamento salvo')
        chk('inicio', 'linha', 'Fazer a linha de limpeza do bico')
        sec('NO FINAL (cada passo pode ser pulado)')
        for chave, texto, _ in av.FIM_PASSOS: chk('fim', chave, texto)
        sec('VENTOINHA DA PEÇA')
        self.v['vmodo'] = tk.StringVar()
        for k, t in av.MODOS_VENT.items():
            tk.Radiobutton(esq, text=t, variable=self.v['vmodo'], value=k, command=self.mudou, bg=CARD, fg=TXT, selectcolor=LINHA, activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 10)).pack(fill='x', padx=14)
        r = tk.Frame(esq, bg=CARD); r.pack(fill='x', padx=36, pady=2)
        self.v['vpct'] = tk.StringVar(); self.v['vcam'] = tk.StringVar()
        tk.Label(r, text='força', bg=CARD, fg=DIM).pack(side='left'); self._entrada(r, self.v['vpct'], 4).pack(side='left', padx=(4, 2)); tk.Label(r, text='%   a partir da camada', bg=CARD, fg=DIM).pack(side='left')
        self._entrada(r, self.v['vcam'], 5).pack(side='left', padx=4)
        r = tk.Frame(esq, bg=CARD); r.pack(fill='x', padx=16, pady=(8, 12))
        self.v['vel'] = tk.StringVar(); self.v['flu'] = tk.StringVar()
        tk.Label(r, text='Velocidade', bg=CARD, fg=TXT).pack(side='left'); self._entrada(r, self.v['vel'], 4).pack(side='left', padx=(4, 2)); tk.Label(r, text='%', bg=CARD, fg=DIM).pack(side='left')
        tk.Label(r, text='   Fluxo', bg=CARD, fg=TXT).pack(side='left'); self._entrada(r, self.v['flu'], 4).pack(side='left', padx=(4, 2)); tk.Label(r, text='%', bg=CARD, fg=DIM).pack(side='left')
        # ---- direita: textos livres ----
        def texto(t, dica, chave, alt):
            a.rotulo(dir_, t).pack(fill='x', padx=16, pady=(10, 0))
            tk.Label(dir_, text=dica, bg=CARD, fg=DIM, font=('Segoe UI', 8), wraplength=470, justify='left').pack(anchor='w', padx=16)
            tx = tk.Text(dir_, height=alt, bg=BG, fg=TXT, insertbackground=TXT, relief='flat', font=('Consolas', 9), wrap='none'); tx.pack(fill='x', padx=16, pady=(2, 0))
            tx.bind('<KeyRelease>', lambda e: self.mudou()); self.v[chave] = tx
        texto('G-CODE EXTRA ANTES DE COMEÇAR A PEÇA', 'Uma linha por comando. Ex.: M300 S440 P200 (bip)', 'gcode_antes', 3)
        texto('G-CODE EXTRA DEPOIS DE TERMINAR', 'Roda no fim de tudo.', 'gcode_depois', 3)
        texto('COMANDOS EM CAMADAS ESPECÍFICAS', 'Formato  camada: comando   Ex.:  5: M106 S128   (ventoinha a 50% na camada 5)', 'por_camada', 4)
        texto('AJUSTES EXTRAS DO FATIADOR (CuraEngine)', 'Um por linha:  chave=valor   Ex.:  wall_line_count=3   ou   infill_pattern=gyroid.  Vale para qualquer ajuste do CuraEngine.', 'fatiador_extra', 4)
        a.rotulo(dir_, 'COMO VAI SAIR (início e fim)').pack(fill='x', padx=16, pady=(10, 0))
        self.prev = tk.Text(dir_, height=12, bg='#0A0D12', fg='#9FB0C8', relief='flat', font=('Consolas', 8), wrap='none', state='disabled'); self.prev.pack(fill='x', padx=16, pady=(2, 4))
        r = tk.Frame(dir_, bg=CARD); r.pack(fill='x', padx=16, pady=(2, 12))
        a.botao(r, 'Restaurar o padrão', self.restaurar, LINHA).pack(side='left'); a.botao(r, 'Abrir o perfil da impressora…', self.abrir_perfil, LINHA).pack(side='left', padx=8)

    def _entrada(self, pai, var, w):
        e = tk.Entry(pai, textvariable=var, width=w, bg=BG, fg=TXT, insertbackground=TXT, relief='flat', font=('Segoe UI', 10)); var.trace_add('write', lambda *x: self.mudou()); return e

    # ---------- dados <-> tela ----------
    def recarregar(self):
        """Poe na tela os valores de app.av (usado ao abrir e quando a API muda algo)."""
        c = self.app.av; self._ocupado = True
        try:
            self.v['ativo'].set(c['ativo'])
            for sec_ in ('inicio', 'fim'):
                for k, val in c[sec_].items():
                    if (sec_, k) in self.v: self.v[(sec_, k)].set(val)
            self.v['vmodo'].set(c['ventoinha']['modo']); self.v['vpct'].set(str(c['ventoinha']['pct'])); self.v['vcam'].set(str(c['ventoinha']['camada']))
            self.v['vel'].set(str(c['velocidade'])); self.v['flu'].set(str(c['fluxo']))
            for k in ('gcode_antes', 'gcode_depois', 'por_camada', 'fatiador_extra'):
                self.v[k].delete('1.0', 'end'); self.v[k].insert('1.0', c[k])
        finally:
            self._ocupado = False
        self._previa()

    def _ler(self):
        c = self.app.av
        c['ativo'] = bool(self.v['ativo'].get())
        for sec_ in ('inicio', 'fim'):
            for k in c[sec_]:
                if (sec_, k) in self.v: c[sec_][k] = bool(self.v[(sec_, k)].get())
        c['ventoinha']['modo'] = self.v['vmodo'].get() or 'preset'
        for chave, var, lo, hi in (('pct', self.v['vpct'], 0, 100), ('camada', self.v['vcam'], 1, 5000)):
            try: c['ventoinha'][chave] = int(max(lo, min(hi, float(var.get().replace(',', '.')))))
            except ValueError: pass
        for chave, var in (('velocidade', self.v['vel']), ('fluxo', self.v['flu'])):
            try: c[chave] = int(max(20, min(300, float(var.get().replace(',', '.')))))
            except ValueError: pass
        for k in ('gcode_antes', 'gcode_depois', 'por_camada', 'fatiador_extra'): c[k] = self.v[k].get('1.0', 'end').strip()

    def mudou(self):
        if self._ocupado: return
        self._ler(); av.salvar(self.app.av); self._previa()
        if self._id:
            try: self.after_cancel(self._id)
            except Exception: pass
        self._id = self.after(900, self.app.agendar_refatiar)

    def _previa(self):
        a = self.app
        try:
            ini, il = av.inicio(a.av, a.bico, a.mesa, a.bico <= 220); fim = av.fim(a.av)
            txt = 'INÍCIO\n' + '\n'.join('  ' + c for c in ini) + '\n\nFIM\n' + '\n'.join('  ' + c for c in fim)
        except Exception as e: txt = 'Não deu para montar a prévia: %s' % e
        self.prev.config(state='normal'); self.prev.delete('1.0', 'end'); self.prev.insert('1.0', txt); self.prev.config(state='disabled')

    def restaurar(self):
        if not messagebox.askyesno('Avançado', 'Voltar todos os ajustes avançados ao padrão (e desligar)?', parent=self): return
        self.app.av.clear(); self.app.av.update(json.loads(json.dumps(av.PADRAO))); av.salvar(self.app.av); self.recarregar(); self.app.agendar_refatiar()

    def abrir_perfil(self):
        p = perfil.ARQ
        if not os.path.isfile(p): perfil.salvar(perfil.carregar())
        try: os.startfile(p)
        except Exception as e: messagebox.showinfo('Perfil', 'Arquivo: %s\n(%s)' % (p, e), parent=self)
