"""MCP do programa Imprimir Ender: deixa uma IA (Claude etc.) controlar o programa pela API local.

O MCP NAO fala com a impressora direto: ele chama a API do programa (servidor_rede.py, porta 8101..8110),
entao todas as travas de seguranca do programa continuam valendo. O programa precisa estar aberto.

Rodar:  python server.py          (stdio, para o cliente MCP)
Variaveis opcionais: ENDER_URL (ex http://127.0.0.1:8101), ENDER_TOKEN (senao le ../_PRIVADO_token_rede.txt)
Manual: MANUAL_MCP.md (nesta pasta).
"""
import os, json, base64
import httpx
from mcp.server.fastmcp import FastMCP, Image

PASTA = os.path.dirname(os.path.abspath(__file__))
PAI = os.path.dirname(PASTA)
mcp = FastMCP('ender-impressora')
_base = None


def _token():
    t = os.environ.get('ENDER_TOKEN')
    if t: return t.strip()
    return open(os.path.join(PAI, '_PRIVADO_token_rede.txt'), encoding='utf-8').read().strip()


def _achar():
    """Acha a porta do programa (8101..8110)."""
    global _base
    if _base: return _base
    cand = [os.environ['ENDER_URL']] if os.environ.get('ENDER_URL') else ['http://127.0.0.1:%d' % p for p in range(8101, 8111)]
    h = {'X-Token': _token()}
    for u in cand:
        try:
            r = httpx.get(u + '/api/status', headers=h, timeout=2)
            if r.status_code == 200: _base = u; return u
        except Exception:
            continue
    raise RuntimeError('Nao achei o programa Imprimir Ender aberto (portas 8101-8110). Abra o programa e tente de novo.')


def _chamar(metodo, caminho, corpo=None, params=None, bruto=None, timeout=30):
    global _base
    for tentativa in (1, 2):
        base = _achar()
        try:
            r = httpx.request(metodo, base + caminho, headers={'X-Token': _token()}, params=params,
                              json=corpo if bruto is None else None, content=bruto, timeout=timeout)
            try: return r.json()
            except Exception: return {'ok': False, 'erro': 'resposta nao-JSON (%s)' % r.status_code}
        except httpx.HTTPError:
            _base = None          # programa pode ter reaberto em outra porta
            if tentativa == 2: raise


def _resumo(s):
    """Versao curta do status (o completo tem log e historico)."""
    chaves = ['arquivo', 'info', 'pode_imprimir', 'imprimindo', 'ocupado', 'etapa_nome', 'msg', 'erro', 'bico', 'bico_alvo', 'mesa',
              'mesa_alvo', 'pct', 'cam', 'ncam', 'decorrido', 'falta', 'termina', 'pausado', 'pausa_fw', 'fila', 'rolo', 'custo_txt',
              'vigia', 'nivelamento', 'timelapse']
    return {k: s.get(k) for k in chaves if k in s}


@mcp.tool(annotations={'readOnlyHint': True, 'openWorldHint': False})
def ender_status(completo: bool = False) -> dict:
    """Estado da impressora/programa: arquivo carregado, se esta imprimindo, temperaturas (bico/mesa), camada, progresso, tempo restante,
    pausa, fila, rolo de filamento, vigia. Use completo=true para incluir o log e o historico."""
    s = _chamar('GET', '/api/status')
    return s if completo else _resumo(s)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': True, 'openWorldHint': False})
def ender_enviar_arquivo(caminho: str) -> dict:
    """Envia um arquivo do PC (STL ou G-code) para o programa: ele carrega, fatia (se STL) e deixa pronto. NAO inicia a impressao.
    caminho = caminho completo do arquivo no PC."""
    if not os.path.isfile(caminho): return {'ok': False, 'erro': 'arquivo nao existe: %s' % caminho}
    with open(caminho, 'rb') as f: dados = f.read()
    return _chamar('POST', '/api/upload', params={'nome': os.path.basename(caminho)}, bruto=dados, timeout=600)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': True, 'openWorldHint': False})
def ender_imprimir(confirmo: bool = False, pular_sensor: bool | None = None) -> dict:
    """INICIA a impressao do arquivo carregado: aquece bico e mesa e comeca a imprimir. So use com a autorizacao do usuario
    para ESTA impressao. confirmo precisa ser true. Recusado se ja esta imprimindo."""
    if not confirmo: return {'ok': False, 'erro': 'passe confirmo=true (so com autorizacao do usuario: aquece e imprime)'}
    s = _chamar('GET', '/api/status')
    if s.get('imprimindo') or s.get('ocupado'): return {'ok': False, 'erro': 'a impressora esta ocupada/imprimindo agora'}
    corpo = {'confirmo': True}
    if pular_sensor is not None: corpo['pular_sensor'] = pular_sensor
    return _chamar('POST', '/api/imprimir', corpo)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': True, 'openWorldHint': False})
def ender_parar() -> dict:
    """PARA a impressao em andamento (esfria e levanta o bico, conforme o programa). Sempre permitido."""
    return _chamar('POST', '/api/parar', {})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_pausar() -> dict:
    """Pausa a impressao para trocar de filamento (retrai, sobe e vai para o canto)."""
    return _chamar('POST', '/api/pausar', {})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_continuar() -> dict:
    """Continua a impressao depois da pausa (troca de filamento feita)."""
    return _chamar('POST', '/api/continuar', {})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': True, 'openWorldHint': False})
def ender_purgar(mm: int = 40) -> dict:
    """Durante a pausa, empurra filamento (mm) para limpar a cor antiga do bico. Limite de seguranca: 5 a 150 mm."""
    mm = max(5, min(150, int(mm)))
    return _chamar('POST', '/api/purgar', {'mm': mm})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_testar_sensor() -> dict:
    """Roda o teste do sensor de nivelamento (CR Touch). Recusado se estiver imprimindo."""
    s = _chamar('GET', '/api/status')
    if s.get('imprimindo') or s.get('ocupado'): return {'ok': False, 'erro': 'impressora ocupada'}
    return _chamar('POST', '/api/sensor', {})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': True, 'openWorldHint': False})
def ender_fila(acao: str) -> dict:
    """Controla a fila de impressao. acao: 'comecar' | 'continuar' (depois de tirar a peca) | 'pular' | 'parar'."""
    if acao not in ('comecar', 'continuar', 'pular', 'parar'):
        return {'ok': False, 'erro': "acao deve ser 'comecar', 'continuar', 'pular' ou 'parar'"}
    if acao == 'comecar':
        s = _chamar('GET', '/api/status')
        if s.get('imprimindo') or s.get('ocupado'): return {'ok': False, 'erro': 'impressora ocupada'}
    return _chamar('POST', '/api/fila/' + acao, {})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_flash(ligar: bool) -> dict:
    """Liga (true) ou desliga (false) o flash/lanterna do celular da camera (IP Webcam: /enabletorch e /disabletorch)."""
    return _chamar('POST', '/api/vigia/flash', {'ligar': bool(ligar)})


@mcp.tool(annotations={'readOnlyHint': True, 'openWorldHint': False})
def ender_foto() -> Image:
    """Tira uma foto da impressora agora, pela camera do vigia, e devolve a imagem (sem usar IA). O flash segue a opcao do programa."""
    r = _chamar('GET', '/api/vigia/foto', timeout=40)
    if not r.get('ok'): raise RuntimeError(r.get('erro', 'sem foto'))
    return Image(data=base64.b64decode(r['jpg_base64']), format='jpeg')


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': True})
def ender_vigia_testar() -> dict:
    """Tira uma foto e manda para a IA do vigia (JEV/OpenAI/Gemini, com rodizio de chaves) para avaliar se a impressao esta boa. Gasta 1 uso da cota da chave."""
    return _chamar('POST', '/api/vigia/testar', {}, timeout=120)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_vigia_ativar(ativo: bool) -> dict:
    """Liga ou desliga o vigia por camera (ele so olha enquanto uma impressao esta em andamento)."""
    return _chamar('POST', '/api/vigia/ativar', {'ativo': bool(ativo)})


@mcp.tool(annotations={'readOnlyHint': True, 'openWorldHint': False})
def ender_cores_ver() -> dict:
    """Mostra a configuracao de impressao colorida (cor inicial, trocas), em que CAMADA cada troca cai na peca carregada e o estado da troca em andamento."""
    return _chamar('GET', '/api/cores')


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_cores_definir(ativo: bool, cor_inicial_nome: str = '', cor_inicial_hex: str = '', trocas: list[dict] | None = None) -> dict:
    """Configura a impressao COLORIDA (troca de filamento a mao, so mesmo material). trocas = lista de
    {"modo": "altura" (mm) ou "camada", "valor": numero, "nome": "Vermelho", "hex": "#E5322D"}. Cada troca pausa a impressao: o bico vai ao canto,
    puxa o filamento velho e avisa o usuario (alarme + celular); o usuario troca e toca CONTINUAR (ender_continuar); o bico cospe ate a cor sair limpa
    (ender_purgar para cuspir mais) e o usuario toca CONTINUAR de novo. Nao funciona durante uma impressao."""
    corpo = {'ativo': bool(ativo)}
    if cor_inicial_nome or cor_inicial_hex:
        corpo['inicial'] = {k: v for k, v in (('nome', cor_inicial_nome), ('hex', cor_inicial_hex)) if v}
    if trocas is not None: corpo['trocas'] = trocas
    return _chamar('POST', '/api/cores', corpo)


@mcp.tool(annotations={'readOnlyHint': True, 'openWorldHint': False})
def ender_mesa_ver() -> dict:
    """Pecas na Mesa 3D (id, nome, posicao x/y em mm, rotacao, escala, tamanho, se cabe) e a mesa (220x220x250). x,y = centro da peca; a frente da mesa e y=0."""
    return _chamar('GET', '/api/mesa', timeout=60)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_mesa_adicionar(caminho_stl: str) -> dict:
    """Poe um STL (caminho completo no PC) na Mesa 3D, num lugar livre."""
    return _chamar('POST', '/api/mesa/adicionar', {'caminho': caminho_stl}, timeout=130)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_mesa_copiar(id: int, n: int = 1) -> dict:
    """Faz n copias da peca `id` em lugares livres (as que nao couberem sao puladas)."""
    return _chamar('POST', '/api/mesa/copiar', {'id': id, 'n': n}, timeout=130)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_mesa_editar(id: int, x: float | None = None, y: float | None = None, rot: float | None = None, escala: float | None = None) -> dict:
    """Muda a peca `id`: x,y (centro, mm; 0,0 = canto da frente a esquerda), rot (graus), escala (%)."""
    d = {'id': id}
    for k, v in (('x', x), ('y', y), ('rot', rot), ('escala', escala)):
        if v is not None: d[k] = v
    return _chamar('POST', '/api/mesa/editar', d, timeout=130)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': True, 'openWorldHint': False})
def ender_mesa_remover(id: int) -> dict:
    """Tira a peca `id` da mesa."""
    return _chamar('POST', '/api/mesa/remover', {'id': id}, timeout=130)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_mesa_encher(id: int) -> dict:
    """Enche a mesa com copias da peca `id` ate nao caber mais."""
    return _chamar('POST', '/api/mesa/encher', {'id': id}, timeout=300)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_mesa_organizar() -> dict:
    """Arruma todas as pecas em fileiras (gira 90 graus quando ajuda)."""
    return _chamar('POST', '/api/mesa/organizar', {}, timeout=130)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': True, 'openWorldHint': False})
def ender_mesa_limpar() -> dict:
    """Tira todas as pecas da mesa."""
    return _chamar('POST', '/api/mesa/limpar', {}, timeout=130)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_mesa_fatiar() -> dict:
    """Monta a mesa em um STL so e fatia (como o botao FATIAR E VOLTAR PARA IMPRIMIR). Depois use ender_status ate o arquivo ficar pronto. Recusa se houver peca fora da mesa ou colada em outra."""
    return _chamar('POST', '/api/mesa/fatiar', {}, timeout=700)


@mcp.tool(annotations={'readOnlyHint': True, 'openWorldHint': False})
def ender_suporte_ver() -> dict:
    """Ajustes do suporte (o que sustenta partes no ar): tipo, estrutura (normal/arvore), padrao, densidade, angulo, folgas, teto."""
    return _chamar('GET', '/api/suporte')


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_suporte_definir(tipo: str | None = None, estrutura: str | None = None, padrao: str | None = None, densidade: int | None = None,
                          angulo: int | None = None, folga_z: float | None = None, folga_xy: float | None = None, teto: bool | None = None) -> dict:
    """Muda o suporte. tipo: 'nenhum' | 'mesa' (so apoiado na mesa) | 'tudo' (tambem sobre a peca). estrutura: 'normal' | 'arvore' (galhos finos, bom para peca curva).
    padrao: zigzag|lines|grid|triangles|cross|gyroid. densidade 3-80 (%). angulo 20-80 (graus: acima disso a parte inclinada recebe suporte). folga_z/folga_xy em mm
    (distancia entre suporte e peca). teto: camada cheia embaixo da peca. Se ha um STL carregado ele e fatiado de novo sozinho. Nao funciona imprimindo."""
    d = {k: v for k, v in (('tipo', tipo), ('estrutura', estrutura), ('padrao', padrao), ('densidade', densidade), ('angulo', angulo), ('folga_z', folga_z), ('folga_xy', folga_xy), ('teto', teto)) if v is not None}
    return _chamar('POST', '/api/suporte', d, timeout=60) if d else _chamar('GET', '/api/suporte')


@mcp.tool(annotations={'readOnlyHint': True, 'openWorldHint': False})
def ender_avancado_ver() -> dict:
    """Modo avancado: o que esta ligado (inicio, fim, ventoinha, velocidade/fluxo, G-code extra, ajustes do fatiador) e os comandos de inicio e fim que vao sair."""
    return _chamar('GET', '/api/avancado')


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': True, 'openWorldHint': False})
def ender_avancado_definir(ajustes: dict) -> dict:
    """Muda o modo avancado (mescla com o atual). So vale com "ativo": true. Chaves: ativo (bool); inicio {home, mapa, linha}; fim {retrair, subir, estacionar, bico, mesa, ventoinha, motores};
    ventoinha {modo: preset|desligada|fixa|camada, pct 0-100, camada}; velocidade e fluxo (%, 20-300); gcode_antes, gcode_depois (texto, um comando por linha);
    por_camada (texto "camada: comando" por linha); fatiador_extra (texto "chave=valor" por linha, ajustes do CuraEngine). O arquivo carregado e preparado de novo sozinho. Nao funciona imprimindo."""
    return _chamar('POST', '/api/avancado', ajustes, timeout=60)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': True, 'openWorldHint': False})
def ender_gcode(comandos: list[str], permitir_outros: bool = False) -> dict:
    """Manda G-code direto para a impressora PARADA (ate 40 comandos, um por item) e devolve as respostas. Recusa comandos perigosos (M112, M500, M502, M92, ... mude esses so pelo painel da impressora),
    bico acima de 275 C e mesa acima de 110 C. Fora de uma lista simples (G0/G1/G28/G90/G91/G92, M82/M83/M84, M104-M109, M140/M190, M106/M107, M114/M115/M119, M220/M221...) so com permitir_outros=true.
    Nao funciona se estiver imprimindo/ocupada. Use com cuidado: mexe na maquina de verdade."""
    return _chamar('POST', '/api/gcode', {'comandos': comandos, 'permitir_outros': permitir_outros}, timeout=700)


@mcp.tool(annotations={'readOnlyHint': True, 'openWorldHint': False})
def ender_peca_status() -> dict:
    """Estado da criacao de pecas por texto (Zoo): se esta criando, resultado da ultima, chaves (quantas/de molho, sem mostrar), se o zoo.exe foi achado e se a API esta autorizada."""
    return _chamar('GET', '/api/zoo')


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': True})
def ender_peca_criar(descricao: str, confirmo: bool = False, adicionar_na_mesa: bool = True, esperar_s: int = 600) -> dict:
    """CRIA uma peca a partir de uma descricao em texto, pela Zoo (IA de CAD), e (se adicionar_na_mesa) poe o STL na Mesa 3D. GASTA tempo da conta Zoo do usuario (chaves dele):
    so use quando o usuario pedir e passe confirmo=true. Funciona so se o usuario marcou "permitir que a IA/celular criem pecas" na aba Criar peca. Seja especifico com as medidas
    (ex.: 'suporte de parede em L, 60x20x5 mm, dois furos de 4 mm'). Espera ate esperar_s segundos pelo resultado."""
    if not confirmo: return {'ok': False, 'erro': 'passe confirmo=true (gasta tempo da conta Zoo do usuario)'}
    r = _chamar('POST', '/api/zoo', {'descricao': descricao, 'adicionar_na_mesa': adicionar_na_mesa}, timeout=60)
    if not r.get('ok'): return r
    import time as _t
    fim = _t.time() + max(30, min(1800, int(esperar_s)))
    while _t.time() < fim:
        _t.sleep(3); r = _chamar('GET', '/api/zoo', timeout=30); t = r.get('tarefa', {})
        if t.get('estado') in ('pronto', 'erro'): break
    out = {'ok': r.get('tarefa', {}).get('estado') == 'pronto', 'tarefa': r.get('tarefa')}
    if out['ok'] and adicionar_na_mesa: _t.sleep(2); out['mesa'] = _chamar('GET', '/api/mesa', timeout=60)
    return out


def _editar(corpo, timeout=300):
    return _chamar('POST', '/api/editar', corpo, timeout=timeout)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_editar_abrir(id_peca: int = 0, caminho_stl: str = '') -> dict:
    """ABRE uma peca para editar (a copia: o original nunca e alterado). id_peca = numero da peca na Mesa 3D (veja ender_mesa_ver; ja considera escala e rotacao) OU caminho_stl de um arquivo.
    Devolve tamanho, min/max e centro em mm. Sistema de coordenadas da edicao: X e Y centrados na peca, Z=0 na base. Depois use ender_editar_ver para VER."""
    return _editar({'acao': 'abrir', **({'id': id_peca} if id_peca else {'caminho': caminho_stl})})


@mcp.tool(annotations={'readOnlyHint': True, 'openWorldHint': False})
def ender_editar_estado() -> dict:
    """Estado da edicao: peca aberta, tamanho/min/max/centro (mm), se a malha e fechada, lista de passos feitos e se da para desfazer."""
    return _editar({'acao': 'estado'})


@mcp.tool(annotations={'readOnlyHint': True, 'openWorldHint': False})
def ender_editar_ver(vista: str = '3d', largura: int = 900, altura: int = 700) -> Image:
    """IMAGEM da peca em edicao, para voce ver o resultado. vista: 3d, frente, topo, lado, tras ou baixo."""
    r = _editar({'acao': 'imagem', 'vista': vista, 'largura': largura, 'altura': altura}, 120)
    if not r.get('ok'): raise RuntimeError(r.get('erro', 'sem imagem'))
    return Image(data=base64.b64decode(r['png_base64']), format='png')


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_editar_furo(x: float, y: float, z: float, diametro: float, comprimento: float = 0, eixo: str = 'z') -> dict:
    """FURO (cilindro subtraido) centrado em (x,y,z) mm no sistema da peca. eixo = direcao do furo: z (vertical), x ou y (lateral). comprimento 0 = atravessa a peca inteira."""
    return _editar({'acao': 'furo', 'x': x, 'y': y, 'z': z, 'diametro': diametro, 'comprimento': comprimento, 'eixo': eixo})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_editar_cortar(eixo: str, posicao: float, manter: str = 'menor') -> dict:
    """CORTA a peca num plano e joga fora um lado. eixo x|y|z, posicao em mm, manter 'menor' (fica a parte de coordenada menor, ex.: z: a de baixo) ou 'maior'."""
    return _editar({'acao': 'cortar', 'eixo': eixo, 'posicao': posicao, 'manter': manter})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_editar_forma(tipo: str, modo: str, x: float, y: float, z: float, a: float, b: float = 0, c: float = 0, eixo: str = 'z') -> dict:
    """SOMA ou SUBTRAI uma forma. tipo: caixa (a=largura X, b=profundidade Y, c=altura Z), cilindro (a=diametro, b=comprimento, eixo) ou esfera (a=diametro). modo: 'somar' ou 'subtrair'. (x,y,z) = centro da forma, em mm."""
    return _editar({'acao': 'forma', 'tipo': tipo, 'modo': modo, 'x': x, 'y': y, 'z': z, 'a': a, 'b': b or None, 'c': c or None, 'eixo': eixo})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_editar_texto(texto: str, altura_letra: float = 8, relevo_ou_fundo: float = 1, modo: str = 'relevo', face: str = 'cima', deslocar_direita: float = 0, deslocar_cima: float = 0, girar_graus: float = 0, fonte: str = 'Arial') -> dict:
    """ESCREVE texto na peca. modo: 'relevo' (sai da face) ou 'gravado' (entra). face: cima, frente, tras, esquerda, direita (a face e a do envelope da peca; em superficies curvas o gravado pode nao tocar).
    O texto fica centrado na face; deslocar_* move em mm; altura_letra e o tamanho da letra; relevo_ou_fundo e a espessura. Fontes: Arial, Segoe UI, Consolas, Courier New, Times New Roman, Impact, Verdana, Comic Sans MS, Georgia."""
    return _editar({'acao': 'texto', 'txt': texto, 'tam': altura_letra, 'prof': relevo_ou_fundo, 'modo': modo, 'face': face, 'u': deslocar_direita, 'v': deslocar_cima, 'giro': girar_graus, 'fonte': fonte})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_editar_desenhar(pontos: list, plano: str, posicao_plano: float, espessura: float, modo: str = 'somar') -> dict:
    """DESENHA uma figura 2D (poligono: lista de pontos [[u,v],...] em mm, na ordem do contorno; use muitos pontos para curvas) e extruda com 'espessura'. modo 'somar' (cola na peca) ou 'subtrair' (corta).
    plano 'xy': u=X, v=Y, extruda de Z=posicao_plano para CIMA. plano 'xz': u=X, v=Z, extruda de Y=posicao_plano para +Y. plano 'yz': u=Y, v=Z, extruda de X=posicao_plano para +X.
    Os pontos usam as MESMAS coordenadas da peca (veja min/max em ender_editar_estado). Ex.: pino de 6x6 em cima de uma peca de 20 mm de altura: plano xy, posicao_plano 19.6, espessura 5."""
    return _editar({'acao': 'poligono', 'pontos': pontos, 'plano': plano, 'offset': posicao_plano, 'altura': espessura, 'modo': modo})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_editar_desfazer() -> dict:
    """Desfaz o ultimo passo da edicao."""
    return _editar({'acao': 'desfazer'})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': True, 'openWorldHint': False})
def ender_editar_voltar_original() -> dict:
    """Descarta todos os passos e volta a peca como estava ao abrir."""
    return _editar({'acao': 'original'})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_editar_salvar(adicionar_na_mesa: bool = True) -> dict:
    """SALVA a peca editada como COPIA nova (pasta pecas_editadas; o original nunca e mexido) e, se adicionar_na_mesa, poe na Mesa 3D."""
    return _editar({'acao': 'salvar', 'adicionar_na_mesa': adicionar_na_mesa})


@mcp.tool(annotations={'readOnlyHint': True, 'openWorldHint': False})
def ender_mesa_imagem(vista: str = '3d') -> Image:
    """IMAGEM da Mesa 3D (as pecas como estao agora) para voce ver. vista: 3d, frente, topo, lado."""
    r = _chamar('POST', '/api/mesa/imagem', {'vista': vista}, timeout=120)
    if not r.get('ok'): raise RuntimeError(r.get('erro', 'sem imagem'))
    return Image(data=base64.b64decode(r['png_base64']), format='png')


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_mesa_importar_3mf(caminho_3mf: str) -> dict:
    """IMPORTA um arquivo 3MF: cada parte vira uma peca na Mesa, com a cor lida do arquivo (do nome da parte, do extrusor/filamento ou do material). Devolve as partes e as cores."""
    return _chamar('POST', '/api/mesa/importar3mf', {'caminho': caminho_3mf}, timeout=300)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_mesa_so_cor(cor: str = 'todas') -> dict:
    """Deixa na Mesa so as pecas de UMA cor (ex.: 'Vermelho'); as outras ficam guardadas. 'todas' traz tudo de volta. Para imprimir uma cor de cada vez (troca de filamento manual)."""
    return _chamar('POST', '/api/mesa/so_cor', {'cor': cor}, timeout=120)


@mcp.tool(annotations={'readOnlyHint': True, 'openWorldHint': False})
def ender_diagnostico_lista() -> dict:
    """Lista os testes de diagnostico das pecas da impressora (id, nome, tipo: leitura/aquece/mexe/extrusor, o que faz) e o resultado do ultimo diagnostico rodado."""
    return _chamar('GET', '/api/diagnostico', timeout=30)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': True, 'openWorldHint': False})
def ender_diagnostico(testes: list = None, permitir_aquecer: bool = False, permitir_mover: bool = False, permitir_extrusor: bool = False, confirmo: bool = False, esperar_s: int = 600) -> dict:
    """DIAGNOSTICO da impressora: roda testes das pecas (comunicacao/firmware, termistores, fins de curso, sensor de filamento, cartao SD, display, ventoinha, CR Touch; e, se permitido, aquecimento do bico e da mesa, motores X/Y/Z, extrusor).
    testes: lista de ids (veja ender_diagnostico_lista) ou vazio = so os que apenas leem. Os que AQUECEM ou MEXEM exigem permitir_* = true E confirmo=true (o usuario tem que ter pedido; a mesa deve estar sem peca).
    Cada resultado: estado ok | falha | aviso | observar (o programa fez a acao, mas um HUMANO precisa confirmar olhando/ouvindo: pergunte ao usuario) + detalhe. Espera o fim e devolve tudo."""
    if (permitir_aquecer or permitir_mover or permitir_extrusor) and not confirmo: return {'ok': False, 'erro': 'esses testes aquecem/mexem a impressora: passe confirmo=true (so quando o usuario pedir)'}
    r = _chamar('POST', '/api/diagnostico', {'testes': testes or 'seguros', 'permitir_aquecer': permitir_aquecer, 'permitir_mover': permitir_mover, 'permitir_extrusor': permitir_extrusor}, timeout=60)
    if not r.get('ok'): return r
    import time as _t
    fim = _t.time() + max(30, min(1800, int(esperar_s)))
    while _t.time() < fim:
        _t.sleep(3); r = _chamar('GET', '/api/diagnostico', timeout=30)
        if r.get('diagnostico', {}).get('estado') in ('pronto', 'erro'): break
    d = r.get('diagnostico', {})
    return {'ok': d.get('estado') == 'pronto', 'estado': d.get('estado'), 'mensagem': d.get('msg'), 'resultados': d.get('resultados'), 'pulados_por_falta_de_permissao': d.get('pulados')}


@mcp.tool(annotations={'readOnlyHint': True, 'openWorldHint': False})
def ender_log(linhas: int = 30) -> list:
    """Ultimas linhas do log do programa (o que ele fez/avisou)."""
    s = _chamar('GET', '/api/status')
    return (s.get('log') or [])[-max(1, min(200, int(linhas))):]



# ============================ MODELAR (CAD: criar e editar pecas por passos) ============================
def _modelar(corpo, timeout=600):
    return _chamar('POST', '/api/modelar', corpo, timeout=timeout)


@mcp.tool(annotations={'readOnlyHint': True, 'openWorldHint': False})
def ender_modelar_ajuda(ferramenta: str = '') -> dict:
    """LEIA PRIMEIRO antes de modelar. Sem argumento: lista TODAS as ferramentas de modelagem (op) da aba Modelar, o formato do desenho 2D (perfil), de 'repetir' e dos seletores de arestas/faces.
    Com ferramenta='furo' (ou outra op): parametros dessa ferramenta com padrao e opcoes.
    Como funciona: a peca e uma RECEITA de passos (igual a linha do tempo do Fusion). Voce adiciona passos com ender_modelar_passo(s), OLHA o resultado com ender_modelar_ver e corrige com
    ender_modelar_editar_passo (muda um numero antigo e a peca inteira se refaz). Coordenadas em mm: X = direita, Y = fundo, Z = cima; a mesa e Z=0; nas formas (x, y) = centro e z = base.
    Ferramentas: caixa, cilindro, tubo, esfera, cone, toro, prisma, cunha, texto | extrudar, revolucao, loft, varrer (usam desenho 2D) | arredondar, chanfrar, casca, furo, cortar | mover, girar, escalar, espelhar, assentar | importar, codigo."""
    return _modelar({'acao': 'ajuda', **({'op': ferramenta} if ferramenta else {})}, 60)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': True, 'openWorldHint': False})
def ender_modelar_projetos(acao: str = 'listar', nome: str = '', projeto: str = '') -> dict:
    """Pecas abertas na aba Modelar (da para trabalhar em varias ao mesmo tempo). acao: 'listar' | 'novo' (cria uma peca vazia chamada 'nome' e ja deixa ativa) | 'ativar' | 'fechar' | 'renomear' | 'mostrar' (traz a aba Modelar para a frente no programa, para o usuario ver).
    projeto = numero (1, 2...) ou nome da peca (vazio = a ativa). As outras ferramentas ender_modelar_* agem na peca ATIVA, a nao ser que recebam 'projeto'."""
    ac = {'listar': 'projetos'}.get(acao, acao)
    return _modelar({'acao': ac, **({'nome': nome} if nome else {}), **({'projeto': projeto} if projeto else {})}, 120)


@mcp.tool(annotations={'readOnlyHint': True, 'openWorldHint': False})
def ender_modelar_estado(detalhe: bool = True, projeto: str = '') -> dict:
    """Estado da peca ativa: lista dos passos (com todos os parametros, numerados a partir de 1), variaveis, tamanho/min/max/centro em mm, volume, peso.
    Com detalhe=true (peca CAD): tabela de FACES (id, tipo, centro, normal) e ARESTAS (id, tipo, meio, comprimento) para usar em arredondar/chanfrar/casca.
    Se 'erro_no_passo' aparecer, aquele passo falhou e a peca mostrada vai so ate o anterior."""
    return _modelar({'acao': 'estado', 'detalhe': detalhe, **({'projeto': projeto} if projeto else {})}, 120)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_modelar_passo(op: str, parametros: dict | None = None, posicao: int | None = None, projeto: str = '') -> dict:
    """ADICIONA um passo a peca ativa. op = nome da ferramenta; parametros = dict (o que faltar usa o padrao; veja ender_modelar_ajuda(op)). Se o passo der erro, ele NAO entra e a peca fica como estava.
    Exemplos:
      op='caixa', parametros={'largura': 60, 'profundidade': 40, 'altura': 20, 'raio': 5}
      op='casca', parametros={'espessura': 2, 'abrir': 'cima'}
      op='furo', parametros={'diametro': 4, 'x': 20, 'y': 0, 'repetir': {'tipo': 'circular', 'n': 6}}          (z vazio = boca na superficie; direcao '-z' = de cima para baixo)
      op='extrudar', parametros={'perfil': [{'t': 'ret', 'l': 40, 'a': 20, 'r': 3}, {'t': 'circ', 'd': 8, 'furo': True}], 'plano': 'xy', 'posicao': 0, 'altura': 5, 'modo': 'somar'}
      op='revolucao', parametros={'perfil': [{'t': 'poli', 'pts': [[0, 0], [20, 0], [24, 30], [20, 30], [17, 3], [0, 3]]}], 'eixo': 'z'}       (u = distancia do eixo, v = altura)
      op='arredondar', parametros={'raio': 2, 'arestas': 'verticais'}      (ou 'todas', 'cima', 'ultimo', [3, 7] = ids de ender_modelar_estado, {'perto': [[x, y, z]]})
    modo (formas e desenhos): 'somar' (padrao), 'subtrair' (tira da peca), 'intersectar', 'novo'. Todo numero aceita conta com variaveis: 'largura/2 + folga'.
    posicao: indice (0 = primeiro) para inserir no meio da receita; vazio = no fim. Devolve o estado resumido. Depois OLHE com ender_modelar_ver."""
    return _modelar({'acao': 'passo', 'op': op, **(parametros or {}), **({'posicao': posicao} if posicao is not None else {}), **({'projeto': projeto} if projeto else {})})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_modelar_passos(lista: list, projeto: str = '') -> dict:
    """ADICIONA varios passos de uma vez, na ordem: lista = [{'op': 'caixa', 'largura': 60, ...}, {'op': 'furo', 'diametro': 4}, ...] (os parametros ficam JUNTO do 'op', no mesmo dict).
    Para no primeiro que der erro: devolve qual passo da lista falhou e quantos entraram ('aplicados'); os anteriores ficam valendo."""
    return _modelar({'acao': 'passos', 'lista': lista, **({'projeto': projeto} if projeto else {})})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_modelar_editar_passo(n: int, mudancas: dict, projeto: str = '') -> dict:
    """MUDA parametros de um passo que ja existe (n = numero do passo, a partir de 1; veja ender_modelar_estado). A peca e refeita dali para frente.
    Ex.: n=1, mudancas={'altura': 30}. Se a mudanca quebrar algum passo seguinte, ela e desfeita e o erro diz qual passo quebrou. Tambem serve para {'nome': 'Base'} (apelido do passo)."""
    return _modelar({'acao': 'editar', 'n': n, 'mudancas': mudancas, **({'projeto': projeto} if projeto else {})})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': True, 'openWorldHint': False})
def ender_modelar_historico(acao: str, n: int = 0, projeto: str = '') -> dict:
    """Mexe na receita: acao = 'desfazer' | 'refazer' | 'remover' (apaga o passo n) | 'alternar' (desliga/liga o passo n sem apagar) | 'limpar' (apaga todos os passos; desfazer traz de volta)."""
    return _modelar({'acao': acao, **({'n': n} if n else {}), **({'projeto': projeto} if projeto else {})})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_modelar_variavel(nome: str, valor: str = '', projeto: str = '') -> dict:
    """Cria/muda uma VARIAVEL da peca (ex.: nome='folga', valor='0.2'); valor vazio apaga. Use o nome em qualquer medida ('diametro': '5 + folga*2'). Mudou a variavel -> a peca inteira e refeita."""
    return _modelar({'acao': 'variavel', 'nome': nome, 'valor': valor, **({'projeto': projeto} if projeto else {})})


@mcp.tool(annotations={'readOnlyHint': True, 'openWorldHint': False})
def ender_modelar_ver(vista: str = '3d', numeros: str = '', az: float | None = None, el: float | None = None, largura: int = 900, altura: int = 700, projeto: str = '') -> Image:
    """IMAGEM da peca ativa, para voce VER o que fez (use sempre depois de alguns passos). vista: 3d, frente, tras, direita, esquerda, cima, baixo. Ou angulo livre: az (giro em graus) e el (elevacao, -89 a 89).
    numeros: 'arestas' (escreve o id de cada aresta visivel, em amarelo), 'faces' (id das faces, em azul) ou 'tudo': use para escolher o que arredondar/chanfrar/abrir. As cotas azuis sao o tamanho total em mm.
    Eixos: X vermelho (direita), Y verde (fundo), Z azul (cima)."""
    r = _modelar({'acao': 'imagem', 'vista': vista, 'largura': largura, 'altura': altura, **({'numeros': numeros} if numeros else {}), **({'az': az} if az is not None else {}), **({'el': el} if el is not None else {}),
                  **({'projeto': projeto} if projeto else {})}, 180)
    if not r.get('ok'): raise RuntimeError(r.get('erro', 'sem imagem'))
    return Image(data=base64.b64decode(r['png_base64']), format='png')


@mcp.tool(annotations={'readOnlyHint': True, 'openWorldHint': False})
def ender_modelar_ver_4vistas(numeros: str = '', projeto: str = '') -> Image:
    """UMA imagem com 4 vistas da peca ativa (3D, frente, direita, cima): o jeito mais rapido de conferir a forma inteira. numeros ('arestas' | 'faces' | 'tudo') vale so para a vista 3D."""
    r = _modelar({'acao': 'imagens', **({'numeros': numeros} if numeros else {}), **({'projeto': projeto} if projeto else {})}, 180)
    if not r.get('ok'): raise RuntimeError(r.get('erro', 'sem imagem'))
    return Image(data=base64.b64decode(r['png_base64']), format='png')


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_modelar_abrir(caminho: str = '', id_peca_mesa: int = 0) -> dict:
    """ABRE uma peca pronta na aba Modelar, numa aba nova. caminho = arquivo .stl/.3mf/.obj (vira MALHA: da para somar formas, furar, cortar, escrever, mover, espelhar; NAO da para arredondar/chanfrar/casca),
    .step (solido exato: todas as ferramentas) ou .modelo.json (projeto salvo). OU id_peca_mesa = numero da peca na Mesa 3D (ender_mesa_ver). O arquivo original nunca e alterado."""
    if id_peca_mesa: return _modelar({'acao': 'pegar_da_mesa', 'id': id_peca_mesa})
    return _modelar({'acao': 'abrir_arquivo', 'caminho': caminho})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_modelar_exportar(formato: str = 'stl', caminho: str = '', projeto: str = '') -> dict:
    """Grava a peca ativa num arquivo: formato 'stl' (imprimir), 'step' (solido exato; abre no Fusion/FreeCAD), '3mf' ou 'obj'. caminho vazio = pasta pecas_modeladas do programa. Devolve o caminho."""
    return _modelar({'acao': 'exportar', 'formato': formato, **({'caminho': caminho} if caminho else {}), **({'projeto': projeto} if projeto else {})})


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False})
def ender_modelar_para_mesa(projeto: str = '') -> dict:
    """Manda a peca ativa para a MESA 3D (grava o STL e adiciona na mesa, centralizada e apoiada). Depois: ender_mesa_ver, ender_mesa_fatiar e, so se o usuario pedir, ender_imprimir."""
    return _modelar({'acao': 'para_mesa', **({'projeto': projeto} if projeto else {})})


if __name__ == '__main__':
    mcp.run()
