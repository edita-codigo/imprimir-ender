"""Aba Manual: mover eixos, home, pre-aquecer, empurrar/puxar filamento, trocar filamento, desligar motores, parada de emergencia.
Usa uma conexao propria com a impressora SO quando nao esta imprimindo (ao mandar imprimir, a conexao manual e fechada sozinha)."""
import time, threading, queue
import tkinter as tk
from tkinter import messagebox
from base_ender import achar_porta

BG, CARD, TXT, DIM, VERDE, LARANJA, AZUL, VERM, AMARELO = '#0D1117', '#151B24', '#EAF0F8', '#93A0B5', '#38D39F', '#FF8A3D', '#5AB0FF', '#FF6B6B', '#F7C948'
LINHA = '#263041'
PRE = {'ABS (245 / 100)': (245, 100), 'PLA (205 / 60)': (205, 60), 'PETG (235 / 80)': (235, 80), 'Só a mesa morna (0 / 60)': (0, 60), 'ESFRIAR tudo (0 / 0)': (0, 0)}
MIN_EXTRUSAO = 175     # bico frio nao empurra filamento (a impressora tambem recusa: "cold extrusion")


class Manual(tk.Frame):
    def __init__(self, pai, app):
        super().__init__(pai, bg=BG)
        self.app = app; self.L = None; self.conectado = False; self.q = queue.Queue(); self.thread = None
        self.msg = ''; self.ult_resp = ''; self.passo = tk.DoubleVar(value=1.0); self.v_bico = tk.IntVar(value=245); self.v_mesa = tk.IntVar(value=100)
        self.v_mm = tk.IntVar(value=50); self.v_vel = tk.IntVar(value=300); self.ocupado_cmd = False
        self._montar()

    # ---------- interface ----------
    def _montar(self):
        a = self.app
        topo = tk.Frame(self, bg=BG); topo.pack(fill='x', padx=18, pady=(0, 8))
        self.bcon = a.botao(topo, 'CONECTAR NA IMPRESSORA', self.alternar, AZUL); self.bcon.pack(side='left')
        self.lest = tk.Label(topo, text='Desconectado. Conecte para mover a impressora com a mão.', bg=BG, fg=DIM, font=('Segoe UI', 10), anchor='w'); self.lest.pack(side='left', padx=14, fill='x', expand=True)
        a.botao(topo, 'PARADA DE EMERGÊNCIA', self.emergencia, VERM).pack(side='right')
        corpo = tk.Frame(self, bg=BG); corpo.pack(fill='both', expand=True, padx=18)
        corpo.columnconfigure(0, weight=1, uniform='x'); corpo.columnconfigure(1, weight=1, uniform='x'); corpo.columnconfigure(2, weight=1, uniform='x')
        # ---- eixos ----
        c1 = a.card(corpo); c1.grid(row=0, column=0, sticky='nsew', padx=(0, 7))
        a.rotulo(c1, 'MOVER OS EIXOS').pack(fill='x', padx=16, pady=(12, 4))
        g = tk.Frame(c1, bg=CARD); g.pack(padx=16, pady=4)
        def bt(t, cmd, r, c, cor=LINHA, w=6):
            b = tk.Button(g, text=t, command=cmd, bg=cor, fg=TXT if cor == LINHA else '#0D1117', activebackground=cor, relief='flat', bd=0, cursor='hand2', font=('Segoe UI', 12, 'bold'), width=w, pady=8)
            b.grid(row=r, column=c, padx=3, pady=3); return b
        bt('Y +', lambda: self.mover('Y', 1), 0, 1); bt('X −', lambda: self.mover('X', -1), 1, 0); bt('⌂ XY', lambda: self.home('X Y'), 1, 1, AMARELO); bt('X +', lambda: self.mover('X', 1), 1, 2); bt('Y −', lambda: self.mover('Y', -1), 2, 1)
        bt('Z +', lambda: self.mover('Z', 1), 0, 3, AZUL); bt('⌂ Z', lambda: self.home('Z'), 1, 3, AMARELO); bt('Z −', lambda: self.mover('Z', -1), 2, 3, AZUL)
        p = tk.Frame(c1, bg=CARD); p.pack(fill='x', padx=16, pady=(6, 2))
        tk.Label(p, text='Passo:', bg=CARD, fg=DIM).pack(side='left')
        for v in (0.1, 1.0, 10.0, 50.0):
            tk.Radiobutton(p, text=('%g mm' % v), variable=self.passo, value=v, bg=CARD, fg=TXT, selectcolor=LINHA, activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0, font=('Segoe UI', 10)).pack(side='left', padx=4)
        r = tk.Frame(c1, bg=CARD); r.pack(fill='x', padx=16, pady=(4, 12))
        a.botao(r, 'Home de tudo', lambda: self.home(''), AMARELO).pack(side='left', fill='x', expand=True); a.botao(r, 'Soltar motores', lambda: self.enviar('M84'), LINHA).pack(side='left', fill='x', expand=True, padx=(8, 0))
        tk.Label(c1, text='Cuidado com o Z −: o bico pode bater na mesa. Faça Home antes de mover.', bg=CARD, fg=DIM, font=('Segoe UI', 8), wraplength=360, justify='left').pack(anchor='w', padx=16, pady=(0, 10))
        # ---- temperatura ----
        c2 = a.card(corpo); c2.grid(row=0, column=1, sticky='nsew', padx=7)
        a.rotulo(c2, 'PRÉ-AQUECER').pack(fill='x', padx=16, pady=(12, 4))
        for nome, (b, m) in PRE.items():
            a.botao(c2, nome, lambda b=b, m=m: self.aquecer(b, m), LARANJA if b else (AZUL if m else LINHA)).pack(fill='x', padx=16, pady=3)
        r = tk.Frame(c2, bg=CARD); r.pack(fill='x', padx=16, pady=(8, 2))
        tk.Label(r, text='Bico', bg=CARD, fg=DIM).pack(side='left'); tk.Spinbox(r, from_=0, to=280, increment=5, width=5, textvariable=self.v_bico, bg=BG, fg=TXT, buttonbackground=LINHA, relief='flat', font=('Segoe UI', 11, 'bold')).pack(side='left', padx=(4, 12))
        tk.Label(r, text='Mesa', bg=CARD, fg=DIM).pack(side='left'); tk.Spinbox(r, from_=0, to=110, increment=5, width=5, textvariable=self.v_mesa, bg=BG, fg=TXT, buttonbackground=LINHA, relief='flat', font=('Segoe UI', 11, 'bold')).pack(side='left', padx=(4, 12))
        a.botao(r, 'Aplicar', self.aquecer_manual, VERDE).pack(side='left')
        self.ltemp = tk.Label(c2, text='', bg=CARD, fg=TXT, font=('Segoe UI', 12, 'bold'), anchor='w'); self.ltemp.pack(fill='x', padx=16, pady=(10, 12))
        # ---- filamento ----
        c3 = a.card(corpo); c3.grid(row=0, column=2, sticky='nsew', padx=(7, 0))
        a.rotulo(c3, 'FILAMENTO (bico quente, ≥ %d °C)' % MIN_EXTRUSAO).pack(fill='x', padx=16, pady=(12, 4))
        r = tk.Frame(c3, bg=CARD); r.pack(fill='x', padx=16, pady=2)
        tk.Label(r, text='Quantidade', bg=CARD, fg=DIM).pack(side='left'); tk.Spinbox(r, from_=1, to=200, increment=5, width=4, textvariable=self.v_mm, bg=BG, fg=TXT, buttonbackground=LINHA, relief='flat', font=('Segoe UI', 11, 'bold')).pack(side='left', padx=(4, 2))
        tk.Label(r, text='mm a', bg=CARD, fg=DIM).pack(side='left'); tk.Spinbox(r, from_=60, to=1500, increment=60, width=4, textvariable=self.v_vel, bg=BG, fg=TXT, buttonbackground=LINHA, relief='flat', font=('Segoe UI', 11, 'bold')).pack(side='left', padx=(4, 2))
        tk.Label(r, text='mm/min', bg=CARD, fg=DIM).pack(side='left')
        r = tk.Frame(c3, bg=CARD); r.pack(fill='x', padx=16, pady=6)
        a.botao(r, '▼ Empurrar', lambda: self.extrudar(1), VERDE).pack(side='left', fill='x', expand=True); a.botao(r, '▲ Puxar', lambda: self.extrudar(-1), LINHA).pack(side='left', fill='x', expand=True, padx=(6, 0))
        tk.Frame(c3, bg=LINHA, height=1).pack(fill='x', padx=16, pady=6)
        a.rotulo(c3, 'TROCAR O FILAMENTO').pack(fill='x', padx=16, pady=(2, 4))
        a.botao(c3, '1. DESCARREGAR o filamento velho', self.descarregar, AMARELO).pack(fill='x', padx=16, pady=3)
        a.botao(c3, '2. CARREGAR o filamento novo', self.carregar_fil, VERDE).pack(fill='x', padx=16, pady=3)
        tk.Label(c3, text='Descarregar: aquece ao preset escolhido ao lado, empurra 5 mm e puxa 80 mm rápido. Carregar: empurra 90 mm devagar; repita até a cor nova sair limpa.', bg=CARD, fg=DIM, font=('Segoe UI', 8), wraplength=360, justify='left').pack(anchor='w', padx=16, pady=(4, 10))
        self.lresp = tk.Label(self, text='', bg=BG, fg=DIM, font=('Consolas', 9), anchor='w'); self.lresp.pack(fill='x', padx=18, pady=(8, 0))

    # ---------- conexao ----------
    def alternar(self):
        if self.conectado: self.desconectar()
        else: self.conectar()

    def conectar(self):
        if self.app.ocupado: messagebox.showinfo('Manual', 'A impressora está ocupada (imprimindo, nivelando ou testando o sensor).'); return False
        porta = achar_porta()
        if not porta: messagebox.showerror('Manual', 'Não achei a impressora. Confira o cabo USB e se ela está ligada.'); return False
        self.app.ocupado = True; self.conectado = True; self.msg = 'Conectando...'
        self.thread = threading.Thread(target=self._worker, args=(porta,), daemon=True); self.thread.start(); return True

    def desconectar(self, esperar=True):
        self.conectado = False; self.q.put(None)
        if esperar and self.thread and self.thread.is_alive() and threading.current_thread() is not self.thread: self.thread.join(timeout=15)

    def _worker(self, porta):
        L = None
        try:
            L = self.app.abrir(porta); self.L = L; self.msg = 'Conectado em %s' % porta; self.app.porta_txt = 'Porta ' + porta; self.app.say('Manual: conectado em %s' % porta)
            L.tx('M155 S0'); self.app.aguardar(L, 3)
            ult = 0
            while self.conectado:
                try: item = self.q.get(timeout=0.5)
                except queue.Empty: item = 'tick'
                if item is None: break
                if item == 'tick':
                    if time.time() - ult >= 3: ult = time.time(); L.tx('M105'); self.app.aguardar(L, 5)
                    continue
                cmds, rotulo = item; self.ocupado_cmd = True; self.msg = rotulo + '...'
                for c in cmds:
                    L.tx(c); r = self.app.aguardar(L, 600)
                    self.ult_resp = '%s -> %s' % (c, 'ok' if r is True else r)
                    if r is not True: self.msg = 'A impressora respondeu: %s' % r; break
                else: self.msg = rotulo + ': feito.'
                self.ocupado_cmd = False
        except SystemExit: pass
        except Exception as e: self.msg = 'Erro: %s' % e; self.app.say('Manual: erro %s' % e)
        finally:
            if L: L.fechar()
            self.L = None; self.conectado = False; self.ocupado_cmd = False; self.app.ocupado = False
            if not self.msg.startswith('Erro'): self.msg = 'Desconectado.'

    def enviar(self, *cmds, rotulo=None):
        if not self.conectado: messagebox.showinfo('Manual', 'Conecte na impressora primeiro (botão azul).'); return False
        self.q.put((list(cmds), rotulo or cmds[0])); return True

    # ---------- acoes ----------
    def mover(self, eixo, sinal):
        try: d = float(self.passo.get()) * sinal
        except Exception: d = sinal
        self.enviar('G91', 'G1 %s%.2f F%d' % (eixo, d, 600 if eixo == 'Z' else 3000), 'G90', rotulo='Mover %s %+.1f mm' % (eixo, d))

    def home(self, eixos):
        self.enviar(('G28 ' + eixos).strip(), rotulo='Home ' + (eixos or 'de tudo'))

    def aquecer(self, bico, mesa):
        self.v_bico.set(bico); self.v_mesa.set(mesa)
        self.enviar('M104 S%d' % bico, 'M140 S%d' % mesa, rotulo='Aquecer bico %d / mesa %d' % (bico, mesa))

    def aquecer_manual(self):
        try: self.aquecer(int(self.v_bico.get()), int(self.v_mesa.get()))
        except Exception: pass

    def _bico_quente(self):
        if self.app.st.get('bico', 0) < MIN_EXTRUSAO:
            messagebox.showinfo('Filamento', 'O bico está em %.0f °C. Esquente até pelo menos %d °C antes de mexer no filamento.' % (self.app.st.get('bico', 0), MIN_EXTRUSAO)); return False
        return True

    def extrudar(self, sinal):
        if not self._bico_quente(): return
        try: mm = max(1, int(self.v_mm.get())) * sinal; vel = max(60, int(self.v_vel.get()))
        except Exception: mm = 50 * sinal; vel = 300
        self.enviar('M83', 'G1 E%d F%d' % (mm, vel), 'M82', rotulo=('Empurrar' if sinal > 0 else 'Puxar') + ' %d mm' % abs(mm))

    def descarregar(self):
        try: bico = max(MIN_EXTRUSAO + 5, int(self.v_bico.get()))
        except Exception: bico = 240
        if not messagebox.askyesno('Descarregar', 'Vai esquentar o bico a %d °C (espera), empurrar 5 mm e puxar 80 mm rápido para soltar o filamento velho.\nDepois puxe o resto com a mão. Continuar?' % bico): return
        self.enviar('M104 S%d' % bico, 'M109 S%d' % bico, 'M83', 'G1 E5 F200', 'G1 E-80 F1500', 'M82', rotulo='Descarregar filamento')

    def carregar_fil(self):
        if not self._bico_quente(): return
        self.enviar('M83', 'G1 E60 F600', 'G1 E30 F200', 'M82', rotulo='Carregar filamento')

    def emergencia(self):
        if not messagebox.askyesno('PARADA DE EMERGÊNCIA', 'Isso manda M112: a impressora TRAVA na hora (motores, bico e mesa) e precisa ser DESLIGADA E LIGADA depois.\n\nUse só se algo estiver dando muito errado. Confirmar?'): return
        try:
            self.app.parar = True
            L = self.L
            if L is None:
                from imprimir_ender import Linha
                porta = achar_porta()
                if not porta: messagebox.showerror('Emergência', 'Não achei a impressora.'); return
                L = Linha(porta); time.sleep(0.5)
            L.tx('M112'); self.app.say('PARADA DE EMERGÊNCIA (M112) enviada')
            self.msg = 'M112 enviado: a impressora travou. Desligue e ligue de novo.'
        except Exception as e: messagebox.showerror('Emergência', 'Não consegui mandar: %s' % e)

    # ---------- tela ----------
    def atualizar(self):
        st = self.app.st
        self.bcon.config(text='DESCONECTAR' if self.conectado else 'CONECTAR NA IMPRESSORA', bg=LINHA if self.conectado else AZUL, fg=TXT if self.conectado else '#0D1117')
        if self.conectado: self.lest.config(text=self.msg or 'Conectado.', fg=VERDE if not self.msg.startswith(('Erro', 'A impressora')) else VERM)
        else: self.lest.config(text=(self.msg + '  ·  ' if self.msg and self.msg != 'Desconectado.' else '') + 'Desconectado. Conecte para mover a impressora com a mão.' if not self.app.imprimindo else 'Imprimindo: a aba Manual fica bloqueada.', fg=DIM)
        self.ltemp.config(text='Bico %.0f°C (alvo %.0f)   ·   Mesa %.0f°C (alvo %.0f)' % (st['bico'], st['bico_alvo'], st['mesa'], st['mesa_alvo']))
        self.lresp.config(text=self.ult_resp)
