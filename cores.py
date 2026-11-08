"""Impressao COLORIDA com uma Ender comum (um bico so): a troca de filamento e feita A MAO, mas o programa cuida de tudo em volta.

Como funciona (cor por altura ou por camada):
  1. Voce diz em que altura (ou camada) entra cada cor nova.
  2. Quando a impressao chega la, o programa: sobe, vai ao canto, PUXA o filamento velho e toca o alarme (tela + celular).
  3. Voce tira o filamento velho, poe o novo e toca CONTINUAR.
  4. O programa carrega o novo, CUSPE filamento no canto (tira a cor antiga do bico) e espera voce ver a cor limpa:
     "purgar mais" quantas vezes precisar, depois CONTINUAR. Ai ele volta para a peca e segue.
So serve para o MESMO material (ex.: so ABS). Onde cuspir e quantos mm: perfil_impressora.json (aba Cores).
"""
import os, re, json, time
import tkinter as tk
from tkinter import colorchooser, messagebox
import perfil
import base_ender

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(PASTA, 'cores.json')
BG, CARD, TXT, DIM, VERDE, LARANJA, AZUL, VERM, AMARELO = '#0D1117', '#151B24', '#EAF0F8', '#93A0B5', '#38D39F', '#FF8A3D', '#5AB0FF', '#FF6B6B', '#F7C948'
LINHA = '#263041'
PADRAO = dict(ativo=False, inicial=dict(nome='Branco', hex='#FFFFFF'), trocas=[])
MODOS = {'altura': 'na altura (mm)', 'camada': 'na camada'}
PALETA = ['#E5322D', '#F7C948', '#2E7DE1', '#38A857', '#111111', '#FF8A3D', '#8E44AD', '#FFFFFF']


def carregar_cfg():
    c = json.loads(json.dumps(PADRAO))
    try:
        d = json.load(open(ARQ, encoding='utf-8'))
        c['ativo'] = bool(d.get('ativo', False))
        if isinstance(d.get('inicial'), dict): c['inicial'].update({k: str(v) for k, v in d['inicial'].items() if k in ('nome', 'hex')})
        c['trocas'] = [dict(modo=t.get('modo', 'altura') if t.get('modo') in MODOS else 'altura', valor=float(t.get('valor', 0)),
                            nome=str(t.get('nome', '')), hex=str(t.get('hex', '#888888'))) for t in d.get('trocas', []) if isinstance(t, dict)]
    except Exception:
        pass
    return c


def salvar_cfg(c):
    json.dump(c, open(ARQ, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def z_por_camada(cmds, cams, ini):
    """Altura (Z mais alto) de cada camada, lida dos comandos. Devolve {numero_da_camada: z}."""
    z = {}; rel = False; cur = 0.0
    for i in range(ini, max(ini, len(cmds) - base_ender.INFO['fim_n'])):
        c = cmds[i]
        if c.startswith('G90'): rel = False
        elif c.startswith('G91'): rel = True
        elif c.startswith(('G0', 'G1')):
            m = re.search(r'Z(-?[\d.]+)', c)
            if m: cur = cur + float(m.group(1)) if rel else float(m.group(1))
        k = cams[i]
        if cur > z.get(k, 0): z[k] = cur
    return z


def resolver(trocas, z):
    """Converte cada troca (altura em mm ou numero da camada) na camada onde ela acontece. Levanta ValueError com texto claro."""
    if not z: raise ValueError('Carregue uma peca primeiro.')
    ultima = max(z); out = []
    for n, t in enumerate(trocas, 1):
        if t['modo'] == 'camada':
            cam = int(round(t['valor']))
        else:
            cam = next((c for c in sorted(z) if z[c] > t['valor'] + 0.001), None)
            if cam is None: raise ValueError('Troca %d: a altura %.1f mm esta acima da peca (que tem %.1f mm).' % (n, t['valor'], z[ultima]))
        if cam < 2: raise ValueError('Troca %d: tem que ser a partir da camada 2 (a 1a camada e a cor inicial).' % n)
        if cam > ultima: raise ValueError('Troca %d: a camada %d nao existe (a peca tem %d).' % (n, cam, ultima))
        out.append(dict(t, camada=cam, z=z.get(cam, 0), idx=n - 1))
    out.sort(key=lambda t: t['camada'])
    for a, b in zip(out, out[1:]):
        if a['camada'] == b['camada']: raise ValueError('Duas trocas caem na mesma camada (%d). Separe mais.' % a['camada'])
    return out


class Cores:
    """Estado e rotina da troca de cor durante a impressao."""
    def __init__(self, app):
        self.app = app; self.cfg = carregar_cfg(); self.zmap = {}
        self.fila = []; self.feitas = 0; self.total = 0; self.cor_atual = self.cfg['inicial']['nome']; self.fase = 'parado'; self.msg = ''

    # ---- chamado ao carregar um arquivo ----
    def arquivo_novo(self):
        a = self.app
        try: self.zmap = z_por_camada(a.cmds, a.cams, a.ini_peca)
        except Exception: self.zmap = {}

    def resolvidas(self):
        """(lista, erro) das trocas ja convertidas em camada, para a tela."""
        try: return resolver(self.cfg['trocas'], self.zmap), ''
        except ValueError as e: return [], str(e)

    # ---- chamado ao comecar a impressao ----
    def preparar_impressao(self):
        self.fila = []; self.feitas = 0; self.fase = 'imprimindo' if self.cfg['ativo'] else 'parado'; self.msg = ''
        self.cor_atual = self.cfg['inicial']['nome'] or 'cor inicial'
        if not self.cfg['ativo'] or not self.cfg['trocas']: self.total = 0; return
        self.arquivo_novo()
        self.fila = resolver(self.cfg['trocas'], self.zmap); self.total = len(self.fila)
        self.app.say('Impressao colorida: %d troca(s) de filamento' % self.total)

    def deve_trocar(self, cam):
        return bool(self.fila) and cam >= self.fila[0]['camada']

    def status(self):
        prox = self.fila[0] if self.fila else None
        return dict(ativo=self.cfg['ativo'], fase=self.fase, cor_atual=self.cor_atual, trocas_total=self.total, trocas_feitas=self.feitas,
                    proxima=dict(camada=prox['camada'], nome=prox['nome'], hex=prox['hex']) if prox else None, msg=self.msg)

    # ---- a troca ----
    def trocar(self, L):
        """Estaciona no canto, puxa o filamento velho, espera a troca, carrega, cuspe ate limpar e volta para a peca."""
        app = self.app; st = app.st; pf = perfil.cuspir(); p = dict(app._pos)
        t = self.fila.pop(0); de = self.cor_atual; para = t['nome'] or 'proxima cor'; n = self.feitas + 1; tot = self.total
        app.pausado = True; app.pausa_pedida = False; app.continuar_evt.clear(); app.purga_q = []
        def tx(c, lim=60): L.tx(c); return app.aguardar(L, lim, True)
        try:
            # 1) estaciona e puxa o filamento velho
            self.fase = 'descarregando'; self.msg = st['msg'] = 'Troca de cor %d/%d: estacionando e puxando o filamento %s...' % (n, tot, de)
            app.say(self.msg)
            for c in ('M83', 'G1 E-4 F1800', 'M82', 'G91', 'G1 Z10 F600', 'G90', 'G1 X%.1f Y%.1f F4000' % (pf['x'], pf['y'])): tx(c)
            if pf['z'] > p['Z'] + 10: tx('G1 Z%.1f F600' % pf['z'])
            if st['bico'] < app.bico - 5: tx('M109 S%d' % app.bico, 900)
            for c in ('M83', 'G1 E5 F200', 'G1 E-%d F1500' % pf['descarregar_mm'], 'M82'): tx(c, 180)
            # 2) espera voce trocar o filamento
            self.fase = 'aguardando_troca'
            self.msg = st['msg'] = 'TROCA DE COR %d/%d: tire o filamento %s, coloque %s e toque em CONTINUAR.' % (n, tot, de, para)
            app.say(self.msg); app.avisar(self.msg, 'pausa', prioridade=1); app.tocar_alarme('TROCAR O FILAMENTO', 'Troca %d/%d: tire %s, coloque %s e toque em CONTINUAR.' % (n, tot, de, para))
            self._esperar(L, pf, aceita_purga=False)
            app.silenciar_alarme()
            # 3) carrega o novo e cuspe para limpar a cor antiga
            self.fase = 'carregando'; self.msg = st['msg'] = 'Carregando %s e cuspindo %d mm para limpar o bico...' % (para, pf['purga_mm'])
            for c in ('M83', 'G1 E%d F600' % pf['carregar_mm'], 'G1 E%d F200' % pf['purga_mm'], 'M82'): tx(c, 240)
            self.fase = 'aguardando_limpeza'
            self.msg = st['msg'] = 'Olhe o filamento saindo: a cor %s esta limpa? Se nao, toque em PURGAR MAIS. Quando estiver limpa, toque em CONTINUAR.' % para
            app.say(self.msg); app.avisar('Troca %d/%d: veja se a cor %s saiu limpa. Toque em PURGAR MAIS ou em CONTINUAR.' % (n, tot, para), 'pausa', prioridade=0)
            self._esperar(L, pf, aceita_purga=True)
            # 4) limpa o fio, volta para a peca
            self.fase = 'voltando'; self.msg = st['msg'] = 'Voltando para a peca...'
            for c in ('M83', 'G1 E-4 F1800', 'M82', 'G1 X%.1f Y%.1f F2500' % (pf['x'] + 12, pf['y'])): tx(c)
            if st['bico'] < app.bico - 5: tx('M109 S%d' % app.bico, 900)
            for c in ('G90', 'G1 X%.3f Y%.3f F4000' % (p['X'], p['Y']), 'G1 Z%.3f F600' % p['Z'], 'M83', 'G1 E4 F1800', 'M82', 'G92 E%.5f' % p['E'], 'G1 F%d' % int(p.get('F') or 1500)): tx(c)
            if p['rel']: tx('G91', 10)
            self.feitas = n; self.cor_atual = para; self.fase = 'imprimindo'; self.msg = ''
            st['msg'] = 'Imprimindo a peca (cor %s)' % para; app.say('Troca de cor %d/%d concluida: agora %s' % (n, tot, para))
        finally:
            app.pausado = False; app.silenciar_alarme()

    def _esperar(self, L, pf, aceita_purga):
        app = self.app; st = app.st; ult = time.time(); t0 = time.time(); frio = False; lim = pf['espera_max_min'] * 60
        while not app.continuar_evt.is_set():
            if app.parar: raise SystemExit
            if app.purga_q:
                mm = app.purga_q.pop(0)
                if aceita_purga and st['bico'] >= 175:
                    st['msg'] = 'Cuspindo mais %d mm...' % mm
                    for c in ('M83', 'G1 E%d F200' % mm, 'M82'): L.tx(c); app.aguardar(L, 180, True)
                    st['msg'] = self.msg
                else: app.say('Purgar so vale depois de trocar o filamento (e com o bico quente).')
            if lim and not frio and time.time() - t0 > lim:
                frio = True; L.tx('M104 S%d' % int(pf['temp_espera'])); app.aguardar(L, 5, True)
                app.say('Espera longa: bico baixado para %d C para nao queimar o filamento. Ao continuar, ele esquenta de novo.' % pf['temp_espera'])
                app.avisar('A troca de cor esta demorando: baixei o bico para %d C. Ao tocar CONTINUAR ele esquenta de novo.' % pf['temp_espera'], 'pausa', prioridade=0)
            if time.time() - ult > 4: ult = time.time(); L.tx('M105'); app.aguardar(L, 5, True)
            time.sleep(0.2)
        app.continuar_evt.clear()
        if frio or st['bico'] < app.bico - 5:
            L.tx('M109 S%d' % app.bico); app.aguardar(L, 900, True)

    # ---- API ----
    def definir(self, dados):
        """Usado pela API/MCP: {'ativo': bool, 'inicial': {'nome','hex'}, 'trocas': [{'modo','valor','nome','hex'}]}"""
        if self.app.imprimindo: return {'ok': False, 'erro': 'esta imprimindo agora'}
        c = json.loads(json.dumps(self.cfg))
        if 'ativo' in dados: c['ativo'] = bool(dados['ativo'])
        if isinstance(dados.get('inicial'), dict): c['inicial'].update({k: str(v) for k, v in dados['inicial'].items() if k in ('nome', 'hex')})
        if isinstance(dados.get('trocas'), list):
            c['trocas'] = [dict(modo=t.get('modo') if t.get('modo') in MODOS else 'altura', valor=float(t.get('valor', 0)), nome=str(t.get('nome', '')), hex=str(t.get('hex', '#888888'))) for t in dados['trocas']]
        if self.zmap:
            try: resolver(c['trocas'], self.zmap)
            except ValueError as e: return {'ok': False, 'erro': str(e)}
        self.cfg = c; salvar_cfg(c)
        try: self.app.after(0, self.app.painel_cores.recarregar)
        except Exception: pass
        res, erro = self.resolvidas()
        return {'ok': True, 'cfg': c, 'camadas': [t['camada'] for t in res]}


# ===================== aba Cores =====================
class PainelCores(tk.Frame):
    def __init__(self, pai, app):
        super().__init__(pai, bg=BG)
        self.app = app; self.c = app.cores; self.linhas = []
        self.v_ativo = tk.BooleanVar(value=self.c.cfg['ativo']); self.v_ini_nome = tk.StringVar(value=self.c.cfg['inicial']['nome']); self.v_ini_hex = self.c.cfg['inicial']['hex']
        self.v_perf = {k: tk.StringVar() for k in ('x', 'y', 'z', 'purga_mm', 'purga_extra_mm', 'descarregar_mm', 'carregar_mm', 'espera_max_min')}
        self._montar(); self.recarregar()

    def _montar(self):
        a = self.app
        corpo = tk.Frame(self, bg=BG); corpo.pack(fill='both', expand=True, padx=18, pady=8)
        corpo.columnconfigure(0, weight=3); corpo.columnconfigure(1, weight=2)
        esq = a.card(corpo); esq.grid(row=0, column=0, sticky='nsew', padx=(0, 7))
        tk.Checkbutton(esq, text='IMPRESSÃO COLORIDA (troca o filamento a mão em certas alturas)', variable=self.v_ativo, command=self.salvar, bg=CARD, fg=VERDE, selectcolor=LINHA, activebackground=CARD, activeforeground=VERDE, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 11, 'bold')).pack(fill='x', padx=14, pady=(12, 2))
        tk.Label(esq, text='A cor muda numa altura da peça. Nessa altura o bico vai ao canto, puxa o filamento velho e toca o alarme. Você troca, o bico cospe até a cor sair limpa e a peça continua. Só funciona com o MESMO material (ex.: só ABS).', bg=CARD, fg=DIM, font=('Segoe UI', 9), wraplength=620, justify='left').pack(anchor='w', padx=16, pady=(0, 6))
        r = tk.Frame(esq, bg=CARD); r.pack(fill='x', padx=16, pady=4)
        tk.Label(r, text='Cor inicial (1ª camada):', bg=CARD, fg=TXT, font=('Segoe UI', 10, 'bold')).pack(side='left')
        self.b_ini = tk.Button(r, width=3, relief='flat', bd=0, cursor='hand2', command=lambda: self._escolher_cor(None)); self.b_ini.pack(side='left', padx=8)
        e = tk.Entry(r, textvariable=self.v_ini_nome, width=14, bg=BG, fg=TXT, insertbackground=TXT, relief='flat', font=('Segoe UI', 10)); e.pack(side='left', ipady=3)
        self.v_ini_nome.trace_add('write', lambda *x: self.salvar())
        tk.Frame(esq, bg=LINHA, height=1).pack(fill='x', padx=16, pady=8)
        self.fl = tk.Frame(esq, bg=CARD); self.fl.pack(fill='x', padx=16)
        a.botao(esq, '+ ADICIONAR TROCA DE COR', self.adicionar, AZUL).pack(anchor='w', padx=16, pady=(8, 4))
        self.lres = tk.Label(esq, text='', bg=CARD, fg=TXT, font=('Segoe UI', 10), wraplength=640, justify='left', anchor='w'); self.lres.pack(fill='x', padx=16, pady=(4, 2))
        self.barra = tk.Canvas(esq, height=34, bg=CARD, highlightthickness=0); self.barra.pack(fill='x', padx=16, pady=(2, 12))
        self.barra.bind('<Configure>', lambda e: self._preview())
        self.lfase = tk.Label(esq, text='', bg=CARD, fg=AMARELO, font=('Segoe UI', 11, 'bold'), wraplength=640, justify='left', anchor='w'); self.lfase.pack(fill='x', padx=16, pady=(0, 12))
        dir_ = a.card(corpo); dir_.grid(row=0, column=1, sticky='nsew', padx=(7, 0))
        a.rotulo(dir_, 'ONDE CUSPIR O FILAMENTO').pack(fill='x', padx=16, pady=(12, 4))
        tk.Label(dir_, text='Canto da frente, à esquerda (a tela fica na frente, à direita). Coloque uma lixeirinha embaixo. Perfil: %s' % perfil.carregar()['nome'], bg=CARD, fg=DIM, font=('Segoe UI', 9), wraplength=330, justify='left').pack(anchor='w', padx=16)
        def campo(rot, chave, un):
            rr = tk.Frame(dir_, bg=CARD); rr.pack(fill='x', padx=16, pady=2)
            tk.Label(rr, text=rot, bg=CARD, fg=TXT, width=22, anchor='w').pack(side='left')
            en = tk.Entry(rr, textvariable=self.v_perf[chave], width=7, bg=BG, fg=TXT, insertbackground=TXT, relief='flat', font=('Segoe UI', 10)); en.pack(side='left', ipady=2)
            tk.Label(rr, text=un, bg=CARD, fg=DIM).pack(side='left', padx=4); self.v_perf[chave].trace_add('write', lambda *x: self.salvar_perfil())
        campo('Posição X', 'x', 'mm'); campo('Posição Y', 'y', 'mm'); campo('Altura de segurança Z', 'z', 'mm')
        campo('Cuspir depois de carregar', 'purga_mm', 'mm'); campo('"Purgar mais" cada toque', 'purga_extra_mm', 'mm')
        campo('Puxar o filamento velho', 'descarregar_mm', 'mm'); campo('Empurrar o novo até o bico', 'carregar_mm', 'mm'); campo('Esfriar o bico se demorar', 'espera_max_min', 'min')
        a.botao(dir_, 'TESTAR POSIÇÃO (vai no ar, sem filamento)', self.testar_posicao, AMARELO).pack(fill='x', padx=16, pady=(10, 4))
        tk.Label(dir_, text='O teste faz Home e leva o bico até o ponto escolhido, sem soltar filamento. Conecte antes na aba Manual. Confira onde o filamento vai cair antes de colocar a lixeira.', bg=CARD, fg=DIM, font=('Segoe UI', 8), wraplength=330, justify='left').pack(anchor='w', padx=16, pady=(0, 12))

    # ---- dados <-> tela ----
    def recarregar(self):
        c = self.c.cfg; self.v_ativo.set(c['ativo']); self.v_ini_nome.set(c['inicial']['nome']); self.v_ini_hex = c['inicial']['hex']
        pf = perfil.carregar()['cuspir']
        for k, v in self.v_perf.items(): v.set('%g' % pf[k])
        self.b_ini.config(bg=self.v_ini_hex, activebackground=self.v_ini_hex); self._linhas_desenhar(); self._preview()

    def _linhas_desenhar(self):
        for w in self.fl.winfo_children(): w.destroy()
        self.linhas = []
        for n, t in enumerate(self.c.cfg['trocas'], 1):
            r = tk.Frame(self.fl, bg=CARD); r.pack(fill='x', pady=2)
            tk.Label(r, text='Troca %d:' % n, bg=CARD, fg=TXT, font=('Segoe UI', 10, 'bold'), width=8, anchor='w').pack(side='left')
            vm = tk.StringVar(value=MODOS[t['modo']]); om = tk.OptionMenu(r, vm, *MODOS.values(), command=lambda *_: self._ler_linhas()); om.config(bg=BG, fg=TXT, relief='flat', bd=0, highlightthickness=0, activebackground=LINHA, font=('Segoe UI', 9)); om['menu'].config(bg=BG, fg=TXT); om.pack(side='left')
            vv = tk.StringVar(value='%g' % t['valor']); tk.Entry(r, textvariable=vv, width=6, bg=BG, fg=TXT, insertbackground=TXT, relief='flat', font=('Segoe UI', 10, 'bold')).pack(side='left', padx=6, ipady=3)
            lc = tk.Label(r, text='', bg=CARD, fg=DIM, font=('Segoe UI', 9), width=12, anchor='w'); lc.pack(side='left')
            bc = tk.Button(r, width=3, bg=t['hex'], activebackground=t['hex'], relief='flat', bd=0, cursor='hand2', command=lambda i=n - 1: self._escolher_cor(i)); bc.pack(side='left', padx=6)
            vn = tk.StringVar(value=t['nome']); tk.Entry(r, textvariable=vn, width=14, bg=BG, fg=TXT, insertbackground=TXT, relief='flat', font=('Segoe UI', 10)).pack(side='left', ipady=3)
            tk.Button(r, text='✕', command=lambda i=n - 1: self.remover(i), bg=LINHA, fg=TXT, relief='flat', bd=0, cursor='hand2', padx=8).pack(side='left', padx=8)
            for v in (vm, vv, vn): v.trace_add('write', lambda *x: self._ler_linhas())
            self.linhas.append(dict(modo=vm, valor=vv, nome=vn, cam=lc, cor=bc))

    def _ler_linhas(self):
        inv = {v: k for k, v in MODOS.items()}
        for t, l in zip(self.c.cfg['trocas'], self.linhas):
            t['modo'] = inv.get(l['modo'].get(), 'altura'); t['nome'] = l['nome'].get().strip()
            try: t['valor'] = float(l['valor'].get().replace(',', '.'))
            except ValueError: pass
        self.salvar(); self._preview()

    def salvar(self):
        c = self.c.cfg; c['ativo'] = bool(self.v_ativo.get()); c['inicial']['nome'] = self.v_ini_nome.get().strip(); c['inicial']['hex'] = self.v_ini_hex
        try: salvar_cfg(c)
        except Exception as e: self.app.say('Cores: nao salvou (%s)' % e)

    def salvar_perfil(self):
        try:
            p = perfil.carregar()
            for k, v in self.v_perf.items(): p['cuspir'][k] = float(v.get().replace(',', '.'))
            perfil.salvar(p)
        except ValueError: pass
        except Exception as e: self.app.say('Perfil: nao salvou (%s)' % e)

    def adicionar(self):
        t = self.c.cfg['trocas']; n = len(t)
        alt = (max(self.c.zmap.values()) / (n + 2)) if self.c.zmap else 5.0
        ultimo = t[-1]['valor'] if t and t[-1]['modo'] == 'altura' else 0
        t.append(dict(modo='altura', valor=round(max(alt, ultimo + 2), 1), nome='Cor %d' % (n + 2), hex=PALETA[n % len(PALETA)]))
        self.salvar(); self._linhas_desenhar(); self._preview()

    def remover(self, i):
        del self.c.cfg['trocas'][i]; self.salvar(); self._linhas_desenhar(); self._preview()

    def _escolher_cor(self, i):
        atual = self.v_ini_hex if i is None else self.c.cfg['trocas'][i]['hex']
        r = colorchooser.askcolor(color=atual, title='Escolha a cor')
        if not r or not r[1]: return
        if i is None: self.v_ini_hex = r[1]; self.b_ini.config(bg=r[1], activebackground=r[1])
        else: self.c.cfg['trocas'][i]['hex'] = r[1]; self.linhas[i]['cor'].config(bg=r[1], activebackground=r[1])
        self.salvar(); self._preview()

    def _preview(self):
        """Mostra a camada de cada troca e uma barra com as cores empilhadas (base -> topo = esquerda -> direita)."""
        c = self.c; res, erro = c.resolvidas() if c.zmap else ([], 'Carregue uma peça (aba Imprimir) para ver em que camada cada troca cai.')
        cam_de = {t['idx']: t['camada'] for t in res}
        for n, l in enumerate(self.linhas): l['cam'].config(text=('= camada %d' % cam_de[n]) if n in cam_de else '')
        self.lres.config(text=erro if erro else '%d troca(s) de filamento nesta peça. Cada uma pausa a impressão.' % len(res), fg=VERM if erro else VERDE)
        self.barra.delete('all'); W = max(self.barra.winfo_width(), 400)
        if c.zmap and not erro:
            topo = max(c.zmap.values()); x0 = 0; cor = c.cfg['inicial']['hex']
            for t in res:
                x1 = W * c.zmap.get(t['camada'] - 1, t['z']) / topo
                self.barra.create_rectangle(x0, 2, x1, 30, fill=cor, outline='#5A6578'); x0 = x1; cor = t['hex']
            self.barra.create_rectangle(x0, 2, W, 30, fill=cor, outline='#5A6578')
            self.barra.create_text(6, 17, anchor='w', text='base', fill='#888', font=('Segoe UI', 8)); self.barra.create_text(W - 6, 17, anchor='e', text='topo  %.1f mm' % topo, fill='#888', font=('Segoe UI', 8))

    def testar_posicao(self):
        m = self.app.painel_manual
        if not m.conectado: messagebox.showinfo('Testar posição', 'Conecte na impressora primeiro (aba Manual, botão azul).'); return
        pf = perfil.cuspir()
        if not messagebox.askyesno('Testar posição', 'A impressora vai fazer HOME (G28) e levar o bico até X %g, Y %g, a %g mm de altura, SEM soltar filamento.\nTire peças da mesa e confira o caminho. Continuar?' % (pf['x'], pf['y'], pf['z'])): return
        m.enviar('G90', 'G28', 'G1 Z%.1f F600' % pf['z'], 'G1 X%.1f Y%.1f F3000' % (pf['x'], pf['y']), rotulo='Testar posição de cuspir')

    def atualizar(self):
        c = self.c
        txt = {'descarregando': 'Puxando o filamento velho...', 'aguardando_troca': 'TROQUE O FILAMENTO e toque em CONTINUAR (aba Imprimir ou celular).',
               'carregando': 'Carregando o novo e cuspindo...', 'aguardando_limpeza': 'Veja se a cor saiu limpa: PURGAR MAIS ou CONTINUAR.', 'voltando': 'Voltando para a peça...'}.get(c.fase, '')
        if self.app.imprimindo and c.cfg['ativo'] and c.total:
            txt = ('Troca %d de %d · cor atual: %s. ' % (min(c.feitas + (1 if c.fase not in ('imprimindo', 'parado') else 0), c.total), c.total, c.cor_atual)) + txt
        self.lfase.config(text=txt)
        if c.zmap and not self.barra.find_all(): self._preview()
