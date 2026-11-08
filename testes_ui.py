"""Aba 'Testar impressora': testa as pecas da Ender (bico, mesa, motores, ventoinha, display, sensores...) uma a uma."""
import tkinter as tk
import testes_hw as th

BG, CARD, TXT, DIM, VERDE, LARANJA, AZUL, VERM, AMARELO = '#0D1117', '#151B24', '#EAF0F8', '#93A0B5', '#38D39F', '#FF8A3D', '#5AB0FF', '#FF6B6B', '#F7C948'
LINHA = '#263041'
COR = {'ok': VERDE, 'falha': VERM, 'aviso': AMARELO, 'observar': AZUL, 'pulado': DIM, 'rodando': LARANJA, '': DIM}
CATROT = {'leitura': 'só lê', 'aquece': 'AQUECE', 'mexe': 'MEXE os eixos', 'extrusor': 'AQUECE + empurra filamento'}


class PainelTestes(tk.Frame):
    def __init__(self, pai, app):
        super().__init__(pai, bg=BG)
        self.app = app; self.sel = {t['id']: tk.BooleanVar(value=(t['cat'] == 'leitura')) for t in th.TESTES}; self.lin = {}
        self.v_aq = tk.BooleanVar(value=False); self.v_mv = tk.BooleanVar(value=False); self.v_ex = tk.BooleanVar(value=False)
        self._montar()

    def _montar(self):
        a = self.app
        corpo = a.card(self); corpo.pack(fill='both', expand=True, padx=18, pady=8)
        a.rotulo(corpo, 'TESTAR AS PEÇAS DA IMPRESSORA').pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(corpo, text='Testa cada parte da impressora separadamente e diz o que está certo ou errado. A impressora precisa estar parada e ligada por USB. No fim, bico, mesa e ventoinha são sempre desligados. Uma IA também pode pedir este diagnóstico pelo MCP.', bg=CARD, fg=DIM, font=('Segoe UI', 9), wraplength=1000, justify='left').pack(anchor='w', padx=16)
        r = tk.Frame(corpo, bg=CARD); r.pack(fill='x', padx=16, pady=(8, 2))
        for txt, var in (('Permitir AQUECER o bico e a mesa', self.v_aq), ('Permitir MEXER os motores (tire a peça da mesa!)', self.v_mv), ('Permitir empurrar filamento (precisa de filamento carregado)', self.v_ex)):
            tk.Checkbutton(r, text=txt, variable=var, bg=CARD, fg=AMARELO, selectcolor=LINHA, activebackground=CARD, activeforeground=AMARELO, bd=0, highlightthickness=0, font=('Segoe UI', 9, 'bold')).pack(side='left', padx=(0, 14))
        lista = tk.Frame(corpo, bg=CARD); lista.pack(fill='both', expand=True, padx=16, pady=6)
        for t in th.TESTES:
            f = tk.Frame(lista, bg=CARD); f.pack(fill='x', pady=3)
            tk.Checkbutton(f, variable=self.sel[t['id']], bg=CARD, activebackground=CARD, selectcolor=LINHA, bd=0, highlightthickness=0).pack(side='left')
            est = tk.Label(f, text=' ', width=2, bg=CARD, fg=DIM, font=('Segoe UI', 14, 'bold')); est.pack(side='left')
            blk = tk.Frame(f, bg=CARD); blk.pack(side='left', fill='x', expand=True)
            tk.Label(blk, text='%s   [%s]' % (t['nome'], CATROT[t['cat']]), bg=CARD, fg=TXT, font=('Segoe UI', 10, 'bold'), anchor='w').pack(fill='x')
            det = tk.Label(blk, text=t['desc'], bg=CARD, fg=DIM, font=('Segoe UI', 9), anchor='w', justify='left', wraplength=900); det.pack(fill='x')
            self.lin[t['id']] = (est, det, t['desc'])
        r = tk.Frame(corpo, bg=CARD); r.pack(fill='x', padx=16, pady=(4, 6))
        self.bgo = a.botao(r, 'RODAR OS MARCADOS', self.rodar, VERDE); self.bgo.pack(side='left')
        a.botao(r, 'Marcar só os que apenas leem', self.marcar_seguros, LINHA).pack(side='left', padx=6); a.botao(r, 'Marcar todos', self.marcar_todos, LINHA).pack(side='left')
        a.botao(r, 'PARAR', lambda: a.parar_tudo(), VERM).pack(side='left', padx=6)
        self.lmsg = tk.Label(corpo, text='', bg=CARD, fg=AMARELO, font=('Segoe UI', 10, 'bold'), anchor='w', justify='left', wraplength=1000); self.lmsg.pack(fill='x', padx=16, pady=(0, 12))

    def marcar_seguros(self):
        for t in th.TESTES: self.sel[t['id']].set(t['cat'] == 'leitura')

    def marcar_todos(self):
        for t in th.TESTES: self.sel[t['id']].set(True)

    def rodar(self):
        ids = [i for i, v in self.sel.items() if v.get()]
        if not ids: self.lmsg.config(text='Marque pelo menos um teste.', fg=VERM); return
        r = self.app.diag_iniciar(ids, self.v_aq.get(), self.v_mv.get(), self.v_ex.get(), 'tela')
        if not r.get('ok'): self.lmsg.config(text=r.get('erro', 'não deu'), fg=VERM)
        elif r.get('pulados'): self.lmsg.config(text='Não rodei (falta a permissão acima): %s' % ', '.join(r['pulados']), fg=AMARELO)

    def atualizar(self):
        d = self.app.diag; res = {x['id']: x for x in d.get('resultados', [])}
        for i, (est, det, desc) in self.lin.items():
            if i in res: e = res[i]['estado']; est.config(text=th.ESTADOS.get(e, ' '), fg=COR[e]); det.config(text=res[i]['detalhe'], fg=TXT if e != 'falha' else VERM)
            elif d.get('estado') == 'rodando' and d.get('atual') == i: est.config(text='…', fg=LARANJA); det.config(text='Rodando…', fg=LARANJA)
            else: est.config(text=' '); det.config(text=desc, fg=DIM)
        rod = d.get('estado') == 'rodando'
        self.bgo.config(state='disabled' if rod else 'normal')
        if rod: self.lmsg.config(text=d.get('msg') or 'Rodando os testes…', fg=LARANJA)
        elif d.get('estado') == 'pronto':
            n = {k: sum(1 for x in d['resultados'] if x['estado'] == k) for k in ('ok', 'falha', 'aviso', 'observar', 'pulado')}
            self.lmsg.config(text='Pronto: %d ok · %d com problema · %d aviso(s)' % (n['ok'], n['falha'], n['aviso']), fg=VERDE if not n['falha'] else VERM)
        elif d.get('estado') == 'erro': self.lmsg.config(text=d.get('msg', 'Erro'), fg=VERM)
