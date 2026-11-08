"""Calibracao (torre de temperatura e teste de retracao) + ajustes gravados por preset + rolo/custo do filamento (aba Filamento).
- Torre: 5 andares de 10 mm; cada andar imprime com uma temperatura (ou retracao) diferente; depois a tela 'qual ficou melhor?' grava a escolha no preset.
- O G-code da torre leva 'M104 S<t> ;CALIB' na troca de andar (o preparar() do programa deixa passar M104 com CALIB)."""
import os, re, json, time
import tkinter as tk
from tkinter import messagebox

PASTA = os.path.dirname(os.path.abspath(__file__))
CALIB_JSON = os.path.join(PASTA, 'calibracao.json')
AJUSTES_JSON = os.path.join(PASTA, 'presets_ajustes.json')
BG, CARD, TXT, DIM, VERDE, LARANJA, AZUL, VERM, AMARELO = '#0D1117', '#151B24', '#EAF0F8', '#93A0B5', '#38D39F', '#FF8A3D', '#5AB0FF', '#FF6B6B', '#F7C948'
LINHA = '#263041'
ALTURA_ANDAR = 10.0; ANDARES = 5


def temperaturas(bico):
    """5 temperaturas em volta da atual (ex. 245 -> 235,240,245,250,255)."""
    return [bico - 10, bico - 5, bico, bico + 5, bico + 10]


RETRACOES = [0.4, 0.8, 1.2, 1.6, 2.0]


def carregar_ajustes():
    try: return json.load(open(AJUSTES_JSON, encoding='utf-8'))
    except Exception: return {}


def salvar_ajuste(preset, chave, valor):
    a = carregar_ajustes(); a.setdefault(preset, {})[chave] = valor
    json.dump(a, open(AJUSTES_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1); return a


def gerar_stl(tipo, destino):
    """Torre de 5 andares. 'temp': bloco com ponte e pino (mostra ponte, pino e acabamento). 'retracao': dois pinos finos (mostra fios)."""
    import trimesh, numpy as np
    partes = []
    for k in range(ANDARES):
        z0 = k * ALTURA_ANDAR
        if tipo == 'temp':
            b = trimesh.creation.box(extents=[26, 12, 6]); b.apply_translation([0, 0, z0 + 3]); partes.append(b)
            for x in (-11, 11):
                p = trimesh.creation.box(extents=[4, 4, 2]); p.apply_translation([x, 0, z0 + 7]); partes.append(p)
            ponte = trimesh.creation.box(extents=[26, 4, 2]); ponte.apply_translation([0, 0, z0 + 9]); partes.append(ponte)
            pino = trimesh.creation.cylinder(radius=1.5, height=4, sections=24); pino.apply_translation([0, 4.5, z0 + 8]); partes.append(pino)
            marca = trimesh.creation.box(extents=[1.2, 1.2, 1.0])                        # k+1 marquinhas na lateral = numero do andar
            for j in range(k + 1):
                m = marca.copy(); m.apply_translation([-10 + j * 3, -6.6, z0 + 3]); partes.append(m)
        else:
            for x in (-15, 15):
                c = trimesh.creation.cylinder(radius=3.0 if k == 0 else 2.5, height=ALTURA_ANDAR, sections=32); c.apply_translation([x, 0, z0 + ALTURA_ANDAR / 2]); partes.append(c)
            if k == 0:
                base = trimesh.creation.box(extents=[40, 10, 1.2]); base.apply_translation([0, 0, 0.6]); partes.append(base)
    m = trimesh.util.concatenate(partes); m.export(destino); return destino


def pos_processar(gcode, tipo, valores):
    """Troca a temperatura (ou a retracao) a cada andar de 10 mm. Devolve o caminho do G-code novo."""
    linhas = open(gcode, encoding='utf-8', errors='ignore').read().splitlines()
    saida = []; z = 0.0; andar = -1; e = 0.0; e_abs = True; ret_ant = None
    rz = re.compile(r'Z(-?[\d.]+)'); rxy = re.compile(r'[XY]'); re_ = re.compile(r'E(-?[\d.]+)')
    for l in linhas:
        s = l.split(';')[0].strip()
        if s.startswith('M82'): e_abs = True
        elif s.startswith('M83'): e_abs = False
        elif s.startswith('G92'):
            m = re_.search(s)
            if m: e = float(m.group(1))
        if s.startswith(('G0', 'G1')):
            m = rz.search(s)
            if m:
                z = float(m.group(1)); novo = min(ANDARES - 1, max(0, int((z - 0.01) // ALTURA_ANDAR)))
                if novo != andar:
                    andar = novo
                    if tipo == 'temp': saida.append('M104 S%d ;CALIB andar %d' % (valores[andar], andar + 1))
            if tipo == 'retracao' and e_abs and andar >= 0:
                m = re_.search(s)
                if m and not rxy.search(s):
                    v = float(m.group(1))
                    if v < e - 0.05:                          # retracao: troca a distancia pela do andar
                        novo_e = e - valores[andar]
                        l = re_.sub('E%.5f' % novo_e, l, count=1); ret_ant = (v, novo_e); saida.append(l); e = v; continue
                    elif ret_ant and abs(v - e) < 0.001 + 0.0:  # (sem efeito: o Cura volta ao E original, que mantemos)
                        ret_ant = None
                if m: e = float(m.group(1))
        saida.append(l)
    destino = os.path.splitext(gcode)[0] + '_calib.gcode'
    open(destino, 'w', encoding='utf-8').write('\n'.join(saida) + '\n'); return destino


class Filamento(tk.Frame):
    """Aba Filamento: rolo atual + custo, pausa para trocar cor, calibracao."""
    def __init__(self, pai, app):
        super().__init__(pai, bg=BG)
        self.app = app; self.calib = self._ler(); self._montar()

    def _ler(self):
        try: return json.load(open(CALIB_JSON, encoding='utf-8'))
        except Exception: return {}

    def _gravar(self):
        try: json.dump(self.calib, open(CALIB_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        except Exception: pass

    def _montar(self):
        a = self.app; r = a.rolo.d
        corpo = tk.Frame(self, bg=BG); corpo.pack(fill='both', expand=True, padx=18)
        corpo.columnconfigure(0, weight=1, uniform='f'); corpo.columnconfigure(1, weight=1, uniform='f')
        # ---- rolo ----
        c1 = a.card(corpo); c1.grid(row=0, column=0, sticky='nsew', padx=(0, 7), pady=(0, 8))
        a.rotulo(c1, 'ROLO DE FILAMENTO ATUAL').pack(fill='x', padx=16, pady=(12, 4))
        self.v_nome = tk.StringVar(value=r.get('nome', '')); self.v_mat = tk.StringVar(value=r.get('material', 'ABS')); self.v_rest = tk.StringVar(value='%g' % r.get('gramas_restantes', 0))
        self.v_total = tk.StringVar(value='%g' % r.get('gramas_total', 1000)); self.v_preco = tk.StringVar(value='%g' % r.get('preco_kg', 120))
        g = tk.Frame(c1, bg=CARD); g.pack(fill='x', padx=16)
        def campo(lin, col, t, var, w=10):
            tk.Label(g, text=t, bg=CARD, fg=DIM, font=('Segoe UI', 9)).grid(row=lin, column=col, sticky='w', padx=(0, 6), pady=3)
            tk.Entry(g, textvariable=var, width=w, bg=BG, fg=TXT, insertbackground=TXT, relief='flat', font=('Segoe UI', 11)).grid(row=lin, column=col + 1, sticky='w', pady=3)
        campo(0, 0, 'Nome', self.v_nome, 18); campo(1, 0, 'Material', self.v_mat, 8)
        campo(0, 2, 'Sobram (g)', self.v_rest); campo(1, 2, 'Rolo cheio (g)', self.v_total); campo(2, 2, 'Preço do kg (R$)', self.v_preco)
        rr = tk.Frame(c1, bg=CARD); rr.pack(fill='x', padx=16, pady=(8, 4))
        a.botao(rr, 'Salvar rolo', self.salvar_rolo, VERDE).pack(side='left'); a.botao(rr, 'Rolo novo cheio', self.rolo_novo, LINHA).pack(side='left', padx=8)
        self.lrolo = tk.Label(c1, text='', bg=CARD, fg=TXT, font=('Segoe UI', 11, 'bold'), anchor='w', justify='left', wraplength=520); self.lrolo.pack(fill='x', padx=16, pady=(6, 2))
        self.lcusto = tk.Label(c1, text='', bg=CARD, fg=DIM, font=('Segoe UI', 10), anchor='w', justify='left', wraplength=520); self.lcusto.pack(fill='x', padx=16, pady=(0, 12))
        # ---- troca de cor / pausa ----
        c2 = a.card(corpo); c2.grid(row=0, column=1, sticky='nsew', padx=(7, 0), pady=(0, 8))
        a.rotulo(c2, 'PAUSA PARA TROCAR DE COR / FILAMENTO').pack(fill='x', padx=16, pady=(12, 4))
        tk.Label(c2, text='Na camada escolhida a impressora para, estaciona o bico no canto e espera você trocar o filamento. Use a aba Manual (ou o botão abaixo) para empurrar o filamento novo e depois toque em CONTINUAR.', bg=CARD, fg=DIM, font=('Segoe UI', 9), wraplength=520, justify='left').pack(anchor='w', padx=16)
        rr = tk.Frame(c2, bg=CARD); rr.pack(fill='x', padx=16, pady=(8, 4))
        tk.Checkbutton(rr, text='Pausar na camada', variable=a.v_pausa_on, bg=CARD, fg=TXT, selectcolor=LINHA, activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0, font=('Segoe UI', 11, 'bold')).pack(side='left')
        tk.Spinbox(rr, from_=1, to=2000, width=6, textvariable=a.v_pausa_cam, bg=BG, fg=TXT, buttonbackground=LINHA, relief='flat', font=('Segoe UI', 11, 'bold')).pack(side='left', padx=6)
        self.lcamz = tk.Label(rr, text='', bg=CARD, fg=DIM, font=('Segoe UI', 9), wraplength=260, justify='left'); self.lcamz.pack(side='left')
        tk.Checkbutton(c2, text='Sensor de fim de filamento ligado (M412): se acabar, a impressora pausa e o programa avisa', variable=a.v_runout, bg=CARD, fg=TXT, selectcolor=LINHA, activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 10), wraplength=520, justify='left').pack(fill='x', padx=14, pady=(4, 2))
        rr = tk.Frame(c2, bg=CARD); rr.pack(fill='x', padx=16, pady=(8, 12))
        self.bpausa = a.botao(rr, 'PAUSAR AGORA', a.pausar_agora, AMARELO); self.bpausa.pack(side='left')
        self.bpurga = a.botao(rr, 'Empurrar 40 mm', lambda: a.purgar(40), LINHA); self.bpurga.pack(side='left', padx=8)
        self.bcont = a.botao(rr, 'CONTINUAR', a.continuar, VERDE); self.bcont.pack(side='left')
        # ---- calibracao ----
        c3 = a.card(corpo); c3.grid(row=1, column=0, columnspan=2, sticky='nsew')
        a.rotulo(c3, 'CALIBRAÇÃO (torre de 5 andares de 10 mm; cada andar com um valor)').pack(fill='x', padx=16, pady=(12, 4))
        rr = tk.Frame(c3, bg=CARD); rr.pack(fill='x', padx=16)
        a.botao(rr, 'Gerar TORRE DE TEMPERATURA', lambda: self.gerar('temp'), LARANJA).pack(side='left')
        a.botao(rr, 'Gerar TESTE DE RETRAÇÃO (fios)', lambda: self.gerar('retracao'), AZUL).pack(side='left', padx=8)
        tk.Label(c3, text='Depois é só apertar IMPRIMIR na aba Imprimir. Ao terminar, escolha aqui o andar que ficou melhor.', bg=CARD, fg=DIM, font=('Segoe UI', 9), anchor='w').pack(fill='x', padx=16, pady=(4, 0))
        self.lcal = tk.Label(c3, text='', bg=CARD, fg=TXT, font=('Segoe UI', 11, 'bold'), anchor='w', justify='left', wraplength=1100); self.lcal.pack(fill='x', padx=16, pady=(8, 4))
        self.fesc = tk.Frame(c3, bg=CARD); self.fesc.pack(fill='x', padx=16, pady=(0, 10))
        self.lajuste = tk.Label(c3, text='', bg=CARD, fg=DIM, font=('Segoe UI', 9), anchor='w', justify='left', wraplength=1100); self.lajuste.pack(fill='x', padx=16, pady=(0, 12))
        self._botoes_escolha()

    # ---------- rolo ----------
    def salvar_rolo(self):
        d = self.app.rolo.d
        try:
            d.update(nome=self.v_nome.get().strip() or 'Rolo', material=(self.v_mat.get().strip().upper() or 'ABS'), gramas_restantes=float(self.v_rest.get().replace(',', '.')),
                     gramas_total=float(self.v_total.get().replace(',', '.')), preco_kg=float(self.v_preco.get().replace(',', '.')))
            self.app.rolo.salvar(); self.app.say('Rolo salvo: %s, %.0f g' % (d['nome'], d['gramas_restantes'])); self.app.atualizar_custo()
        except ValueError: messagebox.showerror('Rolo', 'Use só números nos campos de gramas e preço.')

    def rolo_novo(self):
        self.v_rest.set(self.v_total.get()); self.salvar_rolo()

    # ---------- calibracao ----------
    def gerar(self, tipo):
        a = self.app
        if a.ocupado: messagebox.showinfo('Calibração', 'A impressora está ocupada.'); return
        p = a.preset_atual(); vals = temperaturas(p['bico']) if tipo == 'temp' else RETRACOES
        self.lcal.config(text='Gerando a torre e fatiando...', fg=AMARELO)
        def run():
            try:
                stl = os.path.join(PASTA, 'mesa_calib_%s.stl' % tipo); gerar_stl(tipo, stl)
                from base_ender import fatiar
                g = os.path.join(PASTA, 'calib_%s.gcode' % tipo); pp = dict(p); pp['brim'] = 8; pp['suporte'] = 'nenhum'
                if not fatiar(stl, g, pp): raise RuntimeError('o fatiador falhou')
                g2 = pos_processar(g, tipo, vals)
                self.calib = dict(tipo=tipo, valores=vals, arquivo=g2, preset=a.preset.get(), gerado=time.strftime('%d/%m %H:%M'), impresso=False, escolha=None); self._gravar()
                a.carregar(g2)
                self.lcal.config(text=('Torre de %s pronta: andares (de baixo para cima) %s. Aperte IMPRIMIR na aba Imprimir.' % ('temperatura' if tipo == 'temp' else 'retração', ', '.join(('%d °C' % v) if tipo == 'temp' else ('%.1f mm' % v) for v in vals))), fg=VERDE)
                a.after(0, self._botoes_escolha)
            except Exception as e: self.lcal.config(text='Não consegui gerar: %s' % e, fg=VERM)
        import threading; threading.Thread(target=run, daemon=True).start()

    def marcar_impresso(self, arquivo):
        c = self.calib
        if c and c.get('arquivo') and os.path.basename(c['arquivo']) == os.path.basename(arquivo or ''):
            c['impresso'] = True; self._gravar(); self.app.after(0, self._botoes_escolha)

    def _botoes_escolha(self):
        for w in self.fesc.winfo_children(): w.destroy()
        c = self.calib
        if not c or not c.get('tipo'): self.lcal.config(text='Nenhuma torre gerada ainda.', fg=DIM); self._txt_ajustes(); return
        tipo = c['tipo']; vals = c['valores']
        if c.get('escolha') is not None:
            self.lcal.config(text='Última torre (%s): você escolheu o andar %d = %s. Já está valendo no preset "%s".' % (c.get('gerado', ''), c['escolha'] + 1, ('%d °C' % vals[c['escolha']]) if tipo == 'temp' else ('%.1f mm' % vals[c['escolha']]), c.get('preset', '')[:30]), fg=VERDE)
        elif c.get('impresso'):
            self.lcal.config(text='A torre foi impressa. QUAL ANDAR FICOU MELHOR? (andar 1 = o de baixo)', fg=AMARELO)
            for k, v in enumerate(vals):
                tk.Button(self.fesc, text='Andar %d\n%s' % (k + 1, ('%d °C' % v) if tipo == 'temp' else ('%.1f mm' % v)), command=lambda k=k: self.escolher(k), bg=LINHA, fg=TXT, activebackground=AZUL, relief='flat', bd=0, cursor='hand2', font=('Segoe UI', 11, 'bold'), width=12, pady=8).pack(side='left', padx=4)
        else:
            self.lcal.config(text='Torre de %s gerada em %s (andares: %s). Aperte IMPRIMIR na aba Imprimir; quando terminar, escolha o melhor andar aqui.' % ('temperatura' if tipo == 'temp' else 'retração', c.get('gerado', ''), ', '.join(('%d' % v) if tipo == 'temp' else ('%.1f' % v) for v in vals)), fg=TXT)
        self._txt_ajustes()

    def _txt_ajustes(self):
        a = carregar_ajustes()
        if not a: self.lajuste.config(text='Ajustes gravados: nenhum (os presets usam os valores de fábrica do programa).'); return
        t = ['%s: %s' % (k[:28], ', '.join('%s=%s' % (kk, vv) for kk, vv in v.items())) for k, v in a.items()]
        self.lajuste.config(text='Ajustes gravados por preset -> ' + ' | '.join(t))

    def escolher(self, k):
        c = self.calib; v = c['valores'][k]; chave = 'bico' if c['tipo'] == 'temp' else 'retracao'
        salvar_ajuste(c.get('preset') or self.app.preset.get(), chave, v)
        c['escolha'] = k; self._gravar(); self.app.say('Calibração: %s = %s gravado no preset' % (chave, v)); self._botoes_escolha()

    def atualizar(self):
        a = self.app; st = a.st
        pausado = getattr(a, 'pausado', False)
        self.bpausa.config(state='normal' if (a.imprimindo and not pausado) else 'disabled')
        self.bcont.config(state='normal' if pausado else 'disabled', bg=VERDE if pausado else '#1C3B30')
        self.bpurga.config(state='normal' if pausado else 'disabled')
        try:
            cam = int(a.v_pausa_cam.get()); alt = cam * float(a.altura_camada or 0.2)
            self.lcamz.config(text='≈ %.1f mm de altura%s' % (alt, ('  (a peça tem %d camadas)' % a.ncam) if a.ncam else ''))
        except Exception: self.lcamz.config(text='')
        self.lrolo.config(text=a.texto_rolo(), fg=a.cor_rolo()); self.lcusto.config(text=a.texto_custo())
