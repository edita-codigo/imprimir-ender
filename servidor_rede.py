"""API local + pagina para o celular do programa Imprimir Ender. Protegida por token (arquivo _PRIVADO_token_rede.txt).
Endpoints (todos com ?t=TOKEN ou header X-Token):
  GET  /                 pagina para o celular
  GET  /api/status       estado completo (JSON)
  POST /api/upload?nome= corpo = arquivo (STL ou G-code); carrega e prepara
  POST /api/imprimir     {"confirmo": true}
  POST /api/parar
  POST /api/sensor       roda o teste do sensor
  POST /api/pausar | /api/continuar | /api/purgar {"mm":40}   pausa p/ trocar filamento
  POST /api/fila/continuar | /api/fila/pular | /api/fila/comecar | /api/fila/parar
  GET  /api/cores                  trocas de cor configuradas (+ camadas resolvidas)
  POST /api/cores {"ativo":bool,"inicial":{"nome","hex"},"trocas":[{"modo":"altura|camada","valor":n,"nome","hex"}]}
  GET  /api/zoo | POST /api/zoo {descricao, adicionar_na_mesa}   criar peca por texto (Zoo; so se autorizado na aba Criar peca)
  POST /api/editar {acao: abrir|estado|furo|cortar|forma|texto|poligono|desfazer|original|salvar|imagem, ...}   editar uma peca e VER o resultado (png em base64)
  GET  /api/diagnostico | POST /api/diagnostico {testes:[ids]|'seguros'|'todos', permitir_aquecer, permitir_mover, permitir_extrusor}   testa as pecas da impressora
  GET  /api/avancado | POST /api/avancado {...}   modo avancado (inicio/fim, ventoinha, G-code extra, ajustes do fatiador)
  POST /api/gcode {"comandos":[...],"permitir_outros":false}   G-code livre (parada; so comandos seguros)
  GET  /api/suporte | POST /api/suporte {tipo, estrutura, padrao, densidade, angulo, folga_z, folga_xy, teto}   ajustes do suporte
  GET  /api/mesa                   pecas na Mesa 3D (posicao, tamanho, se cabem)
  POST /api/mesa/<adicionar|copiar|editar|remover|limpar|encher|organizar|fatiar>  {id, x, y, rot, escala, caminho, n}
  GET  /api/vigia/foto             foto da camera agora (JPEG em base64)
  POST /api/vigia/flash {"ligar": true|false} | /api/vigia/testar | /api/vigia/ativar {"ativo": true|false}
"""
import json, os, hmac, secrets, socket, threading, urllib.parse
import i18n
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ_TOKEN = os.path.join(PASTA, '_PRIVADO_token_rede.txt')
PORTA_PADRAO = 8101
ICONE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="22" fill="#0B0F16"/><path d="M50 16 82 33v34L50 84 18 67V33z" fill="none" stroke="#FF8A3D" stroke-width="6" stroke-linejoin="round"/><path d="M18 33 50 50 82 33M50 50v34" fill="none" stroke="#FF8A3D" stroke-width="5"/></svg>'


def token():
    try:
        t = open(ARQ_TOKEN, encoding='utf-8').read().strip()
        if len(t) >= 16: return t
    except Exception:
        pass
    t = secrets.token_urlsafe(18)
    open(ARQ_TOKEN, 'w', encoding='utf-8').write(t)
    return t


_ATUAL = {'tok': None, 'leitura': False, 'link': None}


def token_atual():
    if not _ATUAL['tok']: _ATUAL['tok'] = token()
    return _ATUAL['tok']


def novo_token():
    """Gera outro token: o celular, o MCP (que le o arquivo) e links antigos precisam do novo. Entra em vigor na hora."""
    t = secrets.token_urlsafe(18)
    open(ARQ_TOKEN, 'w', encoding='utf-8').write(t); _ATUAL['tok'] = t
    return t


def somente_leitura(v=None):
    if v is not None: _ATUAL['leitura'] = bool(v)
    return _ATUAL['leitura']


def ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); ip = s.getsockname()[0]; s.close(); return ip
    except Exception:
        return '127.0.0.1'


class _Servidor(ThreadingHTTPServer):
    """Sem SO_REUSEADDR: no Windows ele deixava DOIS programas abrirem a mesma porta (o MCP/celular podia cair no errado)."""
    allow_reuse_address = False
    daemon_threads = True


def _traduzir_status(d):
    """Mensagens que o programa gera (em portugues) saem no idioma escolhido no PC."""
    try:
        if i18n.atual() == 'pt': return d
        d = dict(d)
        for k in ('msg', 'erro', 'info', 'custo_txt', 'etapa_nome'):
            if isinstance(d.get(k), str): d[k] = i18n.tr(d[k])
        if isinstance(d.get('log'), list): d['log'] = [i18n.tr(x) if isinstance(x, str) else x for x in d['log']]
        f = d.get('fila')
        if isinstance(f, dict):
            f = dict(f)
            if isinstance(f.get('msg'), str): f['msg'] = i18n.tr(f['msg'])
            d['fila'] = f
    except Exception: pass
    return d


def iniciar(app, porta=PORTA_PADRAO):
    token_atual()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def _ok_token(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            t = (q.get('t') or [self.headers.get('X-Token', '')])[0]
            return hmac.compare_digest(t.encode(), token_atual().encode())

        def _json(self, d, code=200):
            b = json.dumps(d, ensure_ascii=False).encode('utf-8')
            self.send_response(code); self.send_header('Content-Type', 'application/json; charset=utf-8'); self.send_header('Content-Length', str(len(b))); self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(b)

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if u.path.startswith('/idioma/') and u.path.endswith('.json'):          # dicionario da pagina do celular (publico: so textos de tela)
                cod = os.path.basename(u.path)[:-5]
                try: b = open(os.path.join(PASTA, 'idiomas', 'web_%s.json' % cod), 'rb').read() if cod in i18n.IDIOMAS and cod != 'pt' else b'{}'
                except Exception: b = b'{}'
                self.send_response(200); self.send_header('Content-Type', 'application/json; charset=utf-8'); self.send_header('Content-Length', str(len(b))); self.send_header('Cache-Control', 'no-cache'); self.end_headers(); self.wfile.write(b); return
            if u.path in ('/', '/index.html', '/manifest.json', '/icone.svg'):     # paginas publicas (sem segredo); a API continua exigindo o token
                if u.path == '/manifest.json': b = json.dumps({'name': 'Ender-3 V3 SE', 'short_name': 'Ender', 'start_url': '/', 'display': 'standalone', 'background_color': '#0B0F16', 'theme_color': '#0B0F16', 'icons': [{'src': '/icone.svg', 'sizes': 'any', 'type': 'image/svg+xml', 'purpose': 'any'}]}).encode(); ct = 'application/manifest+json'
                elif u.path == '/icone.svg': b = ICONE.encode(); ct = 'image/svg+xml'
                else: b = open(os.path.join(PASTA, 'pagina_rede.html'), 'rb').read(); ct = 'text/html; charset=utf-8'
                self.send_response(200); self.send_header('Content-Type', ct); self.send_header('Content-Length', str(len(b))); self.send_header('Cache-Control', 'no-cache'); self.end_headers(); self.wfile.write(b); return
            if not self._ok_token(): return self._json({'ok': False, 'erro': 'token invalido'}, 401)
            if u.path == '/api/status': return self._json(_traduzir_status(app.status_json()))
            if u.path == '/api/vigia/foto': return self._json(app.api_vigia_foto())
            if u.path == '/api/cores': return self._json(app.api_cores())
            if u.path == '/api/suporte': return self._json(app.no_tk(app.api_suporte))
            if u.path == '/api/avancado': return self._json(app.api_avancado())
            if u.path == '/api/zoo': return self._json(app.api_zoo())
            if u.path == '/api/diagnostico': return self._json(app.api_diagnostico())
            if u.path == '/api/mesa': return self._json(app.no_tk(app.painel_mesa.api_estado))
            self._json({'ok': False, 'erro': 'nao encontrado'}, 404)

        def do_POST(self):
            u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
            if not self._ok_token(): return self._json({'ok': False, 'erro': 'token invalido'}, 401)
            if _ATUAL['leitura'] and u.path != '/api/parar': return self._json({'ok': False, 'erro': 'Modo SOMENTE LEITURA ligado no programa (aba IA / MCP): a IA/celular so pode olhar, nao mexer (so o PARAR continua).'}, 403)
            n = int(self.headers.get('Content-Length') or 0)
            if n > 200 * 1024 * 1024: return self._json({'ok': False, 'erro': 'arquivo grande demais'}, 413)
            corpo = self.rfile.read(n) if n else b''
            try:
                if u.path == '/api/upload':
                    return self._json(app.receber_arquivo((q.get('nome') or ['arquivo'])[0], corpo))
                if u.path == '/api/imprimir':
                    d = json.loads(corpo or b'{}')
                    if not d.get('confirmo'): return self._json({'ok': False, 'erro': 'envie {"confirmo": true}: aquece bico e mesa'})
                    if 'pular_sensor' in d:
                        try: app.pular_sensor.set(bool(d['pular_sensor']))
                        except Exception: pass
                    return self._json(app.iniciar_impressao('rede'))
                if u.path == '/api/parar': app.parar_tudo(); return self._json({'ok': True})
                if u.path == '/api/sensor': return self._json(app.testar_sensor())
                if u.path == '/api/pausar': return self._json(app.pausar_agora())
                if u.path == '/api/continuar': return self._json(app.continuar())
                if u.path == '/api/purgar': return self._json(app.purgar(int(json.loads(corpo or b'{}').get('mm', 40))))
                if u.path == '/api/cores': return self._json(app.cores.definir(json.loads(corpo or b'{}')))
                if u.path == '/api/suporte': return self._json(app.no_tk(lambda: app.api_suporte(json.loads(corpo or b'{}'))))
                if u.path == '/api/avancado': return self._json(app.api_avancado(json.loads(corpo or b'{}')))
                if u.path == '/api/zoo': return self._json(app.api_zoo(json.loads(corpo or b'{}')))
                if u.path == '/api/diagnostico': return self._json(app.api_diagnostico(json.loads(corpo or b'{}') or {'testes': 'seguros'}))
                if u.path == '/api/editar': return self._json(app.no_tk(lambda: app.api_editar(json.loads(corpo or b'{}')), 300))
                if u.path == '/api/gcode':
                    d = json.loads(corpo or b'{}'); return self._json(app.api_gcode(d.get('comandos'), bool(d.get('permitir_outros'))))
                if u.path.startswith('/api/mesa/'):
                    d = json.loads(corpo or b'{}'); ac = u.path.split('/')[-1]
                    return self._json(app.no_tk(lambda: app.painel_mesa.api_acao(ac, d), 600 if ac == 'fatiar' else 120))
                if u.path == '/api/vigia/flash': return self._json(app.api_vigia_flash(json.loads(corpo or b'{}').get('ligar', True)))
                if u.path == '/api/vigia/testar': return self._json(app.api_vigia_testar())
                if u.path == '/api/vigia/ativar': return self._json(app.api_vigia_ativar(json.loads(corpo or b'{}').get('ativo', True)))
                if u.path == '/api/fila/continuar': return self._json(app.fila.continuar())
                if u.path == '/api/fila/pular': return self._json(app.fila.pular())
                if u.path == '/api/fila/comecar': return self._json(app.fila.iniciar())
                if u.path == '/api/fila/parar': return self._json(app.fila.parar())
            except Exception as e:
                return self._json({'ok': False, 'erro': str(e)})
            self._json({'ok': False, 'erro': 'nao encontrado'}, 404)

    srv = None
    for p in range(porta, porta + 10):
        try: srv = _Servidor(('0.0.0.0', p), H); break
        except OSError: continue
    if not srv: return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _ATUAL['porta'] = srv.server_address[1]
    return 'http://%s:%d/?t=%s' % (ip_local(), srv.server_address[1], token_atual())
