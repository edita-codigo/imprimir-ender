"""Aba "IA / MCP": token, links, configuracao pronta para colar em qualquer IA e modo somente leitura."""
import os, sys, json, subprocess, threading
import tkinter as tk
from tkinter import messagebox
import servidor_rede as sr

BG, CARD, TXT, DIM, VERDE, LARANJA, AZUL, VERM, AMARELO = '#0D1117', '#151B24', '#EAF0F8', '#93A0B5', '#38D39F', '#FF8A3D', '#5AB0FF', '#FF6B6B', '#F7C948'
LINHA = '#263041'
PASTA = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(PASTA, 'mcp_ender', 'server.py')
CFG = os.path.join(PASTA, 'mcp_cfg.json')


def python_exe():
    e = sys.executable
    if e.lower().endswith('pythonw.exe'): e = e[:-5] + '.exe'
    return e


def carregar():
    try: return json.load(open(CFG, encoding='utf-8'))
    except Exception: return {'leitura': False}


def salvar(c):
    json.dump(c, open(CFG, 'w', encoding='utf-8'))


def texto_claude_code():
    return 'claude mcp add ender-impressora --scope user -- "%s" "%s"' % (python_exe(), SERVER)


def json_mcp():
    return json.dumps({'mcpServers': {'ender-impressora': {'command': python_exe(), 'args': [SERVER]}}}, indent=2)


def texto_ia(url, tok):
    return ('Voce pode controlar a minha impressora 3D (Ender-3 V3 SE) pelo programa Imprimir Ender, pela API HTTP:\n'
            'Endereco: %s\nToken (mande no cabecalho X-Token): %s\n'
            'GET /api/status mostra tudo. Lista completa de comandos no manual: %s\n'
            'Regras: nunca comece a imprimir sem eu pedir; peca confirmacao antes de aquecer ou mexer na impressora.') % (url, tok, os.path.join(PASTA, 'mcp_ender', 'MANUAL_MCP.md'))


class PainelMCP(tk.Frame):
    def __init__(self, pai, app):
        super().__init__(pai, bg=BG)
        self.app = app; self.cfg = carregar(); sr.somente_leitura(self.cfg.get('leitura', False)); self._mostrar = False
        self._montar(); self.atualizar()

    def _copiar(self, txt, msg='Copiado.'):
        self.clipboard_clear(); self.clipboard_append(txt); self.app.say(msg)

    def _bloco(self, pai, titulo, ajuda, getter, altura=3):
        a = self.app
        a.rotulo(pai, titulo).pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(pai, text=ajuda, bg=CARD, fg=DIM, font=('Segoe UI', 9), wraplength=620, justify='left', anchor='w').pack(fill='x', padx=16)
        t = tk.Text(pai, height=altura, bg=BG, fg=TXT, relief='flat', font=('Consolas', 9), wrap='word'); t.pack(fill='x', padx=16, pady=4)

        def por():
            t.config(state='normal'); t.delete('1.0', 'end'); t.insert('1.0', getter()); t.config(state='disabled')
        por(); r = tk.Frame(pai, bg=CARD); r.pack(fill='x', padx=16)
        a.botao(r, 'Copiar', lambda: self._copiar(getter(), 'Copiado.'), AZUL).pack(side='left')
        return por, r

    def _montar(self):
        a = self.app
        canvas = tk.Canvas(self, bg=BG, highlightthickness=0); sb = tk.Scrollbar(self, command=canvas.yview); canvas.config(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y'); canvas.pack(side='left', fill='both', expand=True)
        corpo = tk.Frame(canvas, bg=BG); jan = canvas.create_window((0, 0), window=corpo, anchor='nw')
        corpo.bind('<Configure>', lambda e: canvas.config(scrollregion=canvas.bbox('all'))); canvas.bind('<Configure>', lambda e: canvas.itemconfig(jan, width=e.width))
        canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>', lambda ev: canvas.yview_scroll(int(-ev.delta / 120), 'units'))); canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))
        c1 = a.card(corpo); c1.pack(fill='x', padx=18, pady=(8, 4))
        a.rotulo(c1, 'CONEXÃO PARA A IA (MCP e API)').pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(c1, text='Uma IA (Claude, etc.) controla TUDO deste programa pelo MCP: imprimir, mesa 3D, cores, suporte, vigia, avançado, criar peça pela Zoo e diagnóstico. O MCP chama a API do programa, então as travas de segurança continuam valendo. O programa precisa estar aberto.', bg=CARD, fg=DIM, font=('Segoe UI', 9), wraplength=640, justify='left').pack(anchor='w', padx=16)
        self.l_status = tk.Label(c1, text='', bg=CARD, fg=TXT, font=('Segoe UI', 10, 'bold'), anchor='w', justify='left', wraplength=640); self.l_status.pack(fill='x', padx=16, pady=(8, 2))
        r = tk.Frame(c1, bg=CARD); r.pack(fill='x', padx=16, pady=2)
        tk.Label(r, text='Token:', bg=CARD, fg=TXT, font=('Segoe UI', 10, 'bold')).pack(side='left')
        self.e_tok = tk.Entry(r, width=36, bg=BG, fg=TXT, relief='flat', font=('Consolas', 10), readonlybackground=BG, state='readonly'); self.e_tok.pack(side='left', padx=8, ipady=3)
        a.botao(r, 'Mostrar', self.alternar, LINHA).pack(side='left'); a.botao(r, 'Copiar token', lambda: self._copiar(sr.token_atual(), 'Token copiado.'), AZUL).pack(side='left', padx=6)
        r = tk.Frame(c1, bg=CARD); r.pack(fill='x', padx=16, pady=4)
        a.botao(r, 'Copiar link do celular', self.app.copiar_link, LINHA).pack(side='left'); a.botao(r, 'Testar conexão', self.testar, VERDE).pack(side='left', padx=6)
        a.botao(r, 'GERAR NOVO TOKEN', self.gerar, LARANJA).pack(side='left'); a.botao(r, 'Abrir o manual', self.manual, LINHA).pack(side='left', padx=6)
        self.v_leit = tk.BooleanVar(value=self.cfg.get('leitura', False))
        tk.Checkbutton(c1, text='SOMENTE LEITURA: a IA e o celular só olham (status, foto, mesa), não mexem em nada. O botão PARAR continua funcionando.', variable=self.v_leit, command=self.leitura, bg=CARD, fg=AMARELO, selectcolor=LINHA, activebackground=CARD, activeforeground=AMARELO, bd=0, highlightthickness=0, anchor='w', justify='left', wraplength=640, font=('Segoe UI', 10, 'bold')).pack(fill='x', padx=14, pady=(6, 12))

        c2 = a.card(corpo); c2.pack(fill='x', padx=18, pady=4)
        self.p_cc, r = self._bloco(c2, 'CLAUDE CODE (neste PC)', 'Cole no terminal. Não leva token: o MCP lê o token do programa sozinho, então continua valendo quando você gerar um novo.', texto_claude_code, 2)
        a.botao(r, 'Registrar no Claude Code agora', self.registrar, VERDE).pack(side='left', padx=6)
        self.l_reg = tk.Label(c2, text='', bg=CARD, fg=AMARELO, font=('Segoe UI', 9), anchor='w', wraplength=640, justify='left'); self.l_reg.pack(fill='x', padx=16, pady=(2, 10))

        c3 = a.card(corpo); c3.pack(fill='x', padx=18, pady=4)
        self._bloco(c3, 'OUTROS CLIENTES MCP (Claude Desktop, Cursor, etc.)', 'Cole no arquivo de configuração de MCP do programa. Mesmo caso: sem token (lê do programa).', json_mcp, 8)
        tk.Frame(c3, bg=CARD, height=10).pack()

        c4 = a.card(corpo); c4.pack(fill='x', padx=18, pady=(4, 12))
        self.p_ia, _ = self._bloco(c4, 'QUALQUER OUTRA IA (pela API, no mesmo Wi-Fi)', 'Texto pronto para colar na conversa com a IA. Leva o token: só envie para uma IA em que você confia.', lambda: texto_ia(self.url(), sr.token_atual()), 7)
        tk.Frame(c4, bg=CARD, height=10).pack()

    def url(self):
        l = self.app.link
        return l.split('/?')[0] if l else 'http://127.0.0.1:8101'

    def atualizar(self):
        l = self.app.link
        self.l_status.config(text=('API no ar em ' + self.url()) if l else 'A API não iniciou (porta ocupada?).', fg=VERDE if l else VERM)
        t = sr.token_atual(); self.e_tok.config(state='normal'); self.e_tok.delete(0, 'end'); self.e_tok.insert(0, t if self._mostrar else '•' * 24); self.e_tok.config(state='readonly')
        self.p_ia()

    def alternar(self):
        self._mostrar = not self._mostrar; self.atualizar()

    def testar(self):
        import urllib.request
        try:
            r = urllib.request.Request(self.url() + '/api/status', headers={'X-Token': sr.token_atual()})
            d = json.loads(urllib.request.urlopen(r, timeout=5).read().decode()); messagebox.showinfo('Conexão', 'Funcionando.\nA API respondeu: %s' % (d.get('msg') or 'ok'), parent=self)
        except Exception as e: messagebox.showerror('Conexão', 'Não funcionou: %s' % e, parent=self)

    def gerar(self):
        if not messagebox.askyesno('Gerar novo token', 'O token antigo para de valer AGORA.\n\n- Links salvos no celular (ícone na tela inicial) precisam do novo link.\n- O MCP deste PC continua funcionando (lê o token do programa).\n- Quem colou o token em outra IA precisa colar o novo.\n\nGerar?', parent=self): return
        t = sr.novo_token(); l = self.app.link
        if l: self.app.link = l.split('t=')[0] + 't=' + t; self.app.copiar_link()
        self.app.say('Novo token gerado. Link novo copiado.'); self.atualizar()

    def leitura(self):
        self.cfg['leitura'] = bool(self.v_leit.get()); salvar(self.cfg); sr.somente_leitura(self.cfg['leitura'])
        self.app.say('API em SOMENTE LEITURA.' if self.cfg['leitura'] else 'API liberada para a IA/celular mexerem.')

    def manual(self):
        try: os.startfile(os.path.join(PASTA, 'mcp_ender', 'MANUAL_MCP.md'))
        except Exception as e: self.app.say('Não abri o manual: %s' % e)

    def registrar(self):
        self.l_reg.config(text='Registrando...', fg=AMARELO)

        def run():
            try:
                subprocess.run('claude mcp remove ender-impressora --scope user', shell=True, capture_output=True, timeout=60)
                r = subprocess.run('claude mcp add ender-impressora --scope user -- "%s" "%s"' % (python_exe(), SERVER), shell=True, capture_output=True, text=True, timeout=60)
                ok = r.returncode == 0; msg = 'Registrado no Claude Code. Abra uma conversa nova para ele enxergar as ferramentas.' if ok else 'Não deu: ' + (r.stderr or r.stdout)[:200]
            except Exception as e: ok = False; msg = 'Não deu: %s (o comando "claude" está instalado?)' % e
            self.after(0, lambda: self.l_reg.config(text=msg, fg=VERDE if ok else VERM))
        threading.Thread(target=run, daemon=True).start()
