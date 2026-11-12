"""Motor da aba MODELAR: modelagem 3D de verdade (CAD parametrico) para criar pecas do zero e editar pecas prontas.

Ideia central: a peca e uma RECEITA de passos (igual a linha do tempo do Fusion). Cada passo e um dicionario {'op': 'caixa', 'largura': 40, ...}.
Mudou um numero de um passo antigo -> a peca inteira e refeita. A mesma receita serve para a tela (mouse) e para a IA (API/MCP).

Motor: build123d / OpenCascade (solidos exatos: arredondar, chanfrar, casca, STEP). Pecas que vem de STL viram MALHA: nelas da para somar,
furar, cortar, escrever (via manifold3d), mas nao arredondar/chanfrar/casca (isso so em peca criada aqui ou vinda de STEP).

Coordenadas em mm: X = direita, Y = fundo, Z = para cima. A mesa e Z=0. Nas formas, (x, y) e o CENTRO e z e a BASE (onde a forma apoia);
na esfera e no toro, (x, y, z) e o centro.
"""
import os, ast, math, json, copy, time, threading
import numpy as np

_bd = None
_bd_erro = None
_bd_lock = threading.Lock()


class ErroModelo(Exception):
    pass


def motor():
    """build123d (demora alguns segundos na primeira vez; por isso e carregado so quando precisa, ou em segundo plano por aquecer())."""
    global _bd, _bd_erro
    if _bd is not None: return _bd
    with _bd_lock:
        if _bd is None:
            try:
                import build123d as m
                _bd = m
            except Exception as e:
                _bd_erro = str(e)
                raise ErroModelo('O motor de modelagem (build123d) nao esta instalado. No terminal: pip install build123d   (%s)' % str(e)[:120])
    return _bd


def aquecer():
    threading.Thread(target=lambda: _tentar(motor), daemon=True).start()


def motor_pronto(): return _bd is not None


def _tentar(fn):
    try: return fn()
    except Exception: return None


# ============================ numeros e variaveis ============================
_FUNCS = {'sin': lambda g: math.sin(math.radians(g)), 'cos': lambda g: math.cos(math.radians(g)), 'tan': lambda g: math.tan(math.radians(g)),
          'sqrt': math.sqrt, 'abs': abs, 'min': min, 'max': max, 'round': round, 'pi': math.pi}


def _aval(no, vs):
    if isinstance(no, ast.Expression): return _aval(no.body, vs)
    if isinstance(no, ast.Constant) and isinstance(no.value, (int, float)): return float(no.value)
    if isinstance(no, ast.Name):
        if no.id in vs: return float(vs[no.id])
        if no.id == 'pi': return math.pi
        raise ErroModelo('variavel "%s" nao existe (crie em Variaveis)' % no.id)
    if isinstance(no, ast.BinOp):
        a, b = _aval(no.left, vs), _aval(no.right, vs)
        if isinstance(no.op, ast.Add): return a + b
        if isinstance(no.op, ast.Sub): return a - b
        if isinstance(no.op, ast.Mult): return a * b
        if isinstance(no.op, ast.Div):
            if b == 0: raise ErroModelo('divisao por zero na conta')
            return a / b
        if isinstance(no.op, ast.Pow): return a ** b
        if isinstance(no.op, ast.Mod): return a % b
    if isinstance(no, ast.UnaryOp) and isinstance(no.op, (ast.USub, ast.UAdd)):
        v = _aval(no.operand, vs); return -v if isinstance(no.op, ast.USub) else v
    if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id in _FUNCS and not no.keywords:
        return float(_FUNCS[no.func.id](*[_aval(a, vs) for a in no.args]))
    raise ErroModelo('conta nao entendida (use numeros, + - * / ( ) e nomes de variaveis)')


def num(v, vs=None, padrao=0.0):
    """Numero ou conta com variaveis: 12, '12,5', 'largura/2 + folga'."""
    if v is None or v == '': return float(padrao)
    if isinstance(v, bool): return float(v)
    if isinstance(v, (int, float)): return float(v)
    s = str(v).strip().replace(',', '.')
    try: return float(s)
    except ValueError: pass
    try: arv = ast.parse(s, mode='eval')
    except SyntaxError: raise ErroModelo('nao entendi o valor "%s"' % v)
    return _aval(arv, vs or {})


# ============================ tabela das ferramentas ============================
# parametro: (nome, tipo, padrao, rotulo[, opcoes])   tipos: n=numero/conta, i=inteiro, s=texto, e=escolha, b=sim/nao, pts=pontos, perfil=desenho 2D,
#            arestas / faces = seletores, rep = repetir, cod = codigo, arq = arquivo, secoes = lista de desenhos em alturas
MODOS = 'somar|subtrair|intersectar|novo'
P_MODO = ('modo', 'e', 'somar', 'O que fazer', MODOS)
P_POS = [('x', 'n', 0, 'Posição X'), ('y', 'n', 0, 'Posição Y'), ('z', 'n', 0, 'Posição Z (base)')]
P_EIXO = ('eixo', 'e', 'z', 'Direção (eixo)', 'z|x|y')
P_REP = ('repetir', 'rep', None, 'Repetir')
ARESTAS_FACEIS = 'todas|cima|baixo|verticais|horizontais|circulares|ultimo|frente|tras|esquerda|direita|selecionadas'
FACES_FACEIS = 'cima|baixo|frente|tras|esquerda|direita|nenhuma|selecionadas'

OPS = {
    # ---------------- criar ----------------
    'caixa': dict(t='Caixa', g='Criar', d='Bloco retangular. (x, y) = centro; z = base.',
                  p=[('largura', 'n', 40, 'Largura (X)'), ('profundidade', 'n', 30, 'Profundidade (Y)'), ('altura', 'n', 10, 'Altura (Z)'), ('raio', 'n', 0, 'Raio dos cantos'), ('giro', 'n', 0, 'Girar (graus)')] + P_POS + [P_MODO, P_REP]),
    'cilindro': dict(t='Cilindro', g='Criar', d='Cilindro. (x, y, z) = centro da base; cresce no sentido + do eixo.',
                     p=[('diametro', 'n', 20, 'Diâmetro'), ('altura', 'n', 20, 'Altura/comprimento'), P_EIXO] + P_POS + [P_MODO, P_REP]),
    'tubo': dict(t='Tubo', g='Criar', d='Cilindro oco (tubo, anel, bucha).',
                 p=[('diametro', 'n', 20, 'Diâmetro de fora'), ('parede', 'n', 2, 'Espessura da parede'), ('altura', 'n', 20, 'Altura/comprimento'), P_EIXO] + P_POS + [P_MODO, P_REP]),
    'esfera': dict(t='Esfera', g='Criar', d='Bola. (x, y, z) = centro.',
                   p=[('diametro', 'n', 20, 'Diâmetro'), ('x', 'n', 0, 'Posição X'), ('y', 'n', 0, 'Posição Y'), ('z', 'n', 10, 'Posição Z (centro)'), P_MODO, P_REP]),
    'cone': dict(t='Cone', g='Criar', d='Cone ou tronco de cone (topo 0 = ponta).',
                 p=[('diametro', 'n', 20, 'Diâmetro da base'), ('diametro_topo', 'n', 0, 'Diâmetro do topo'), ('altura', 'n', 20, 'Altura'), P_EIXO] + P_POS + [P_MODO, P_REP]),
    'toro': dict(t='Rosquinha', g='Criar', d='Toro (anel de seção redonda). (x, y, z) = centro.',
                 p=[('diametro', 'n', 30, 'Diâmetro do anel (centro do fio)'), ('diametro_fio', 'n', 6, 'Diâmetro do fio'), P_EIXO, ('x', 'n', 0, 'Posição X'), ('y', 'n', 0, 'Posição Y'), ('z', 'n', 3, 'Posição Z (centro)'), P_MODO, P_REP]),
    'prisma': dict(t='Prisma', g='Criar', d='Prisma de N lados (sextavado, triângulo, octógono...).',
                   p=[('lados', 'i', 6, 'Número de lados'), ('diametro', 'n', 20, 'Diâmetro (entre pontas)'), ('altura', 'n', 10, 'Altura'), ('giro', 'n', 0, 'Girar (graus)'), P_EIXO] + P_POS + [P_MODO, P_REP]),
    'cunha': dict(t='Rampa', g='Criar', d='Cunha/rampa: base larga em baixo, topo mais estreito (topo 0 = rampa em ponta).',
                  p=[('largura', 'n', 30, 'Largura (X)'), ('profundidade', 'n', 20, 'Profundidade (Y)'), ('altura', 'n', 15, 'Altura (Z)'), ('topo', 'n', 0, 'Largura do topo (X)'), ('giro', 'n', 0, 'Girar (graus)')] + P_POS + [P_MODO, P_REP]),
    'texto': dict(t='Texto', g='Criar', d='Texto em relevo ou gravado numa face da peça (cima, frente, trás, esquerda, direita, baixo).',
                  p=[('txt', 's', 'NOME', 'Texto'), ('tam', 'n', 8, 'Altura da letra'), ('prof', 'n', 1, 'Relevo / fundo'), ('tipo', 'e', 'relevo', 'Tipo', 'relevo|gravado'),
                     ('face', 'e', 'cima', 'Face', 'cima|frente|tras|esquerda|direita|baixo'), ('u', 'n', 0, 'Deslocar →'), ('v', 'n', 0, 'Deslocar ↑'), ('giro', 'n', 0, 'Girar (graus)'), ('fonte', 's', 'Arial', 'Fonte')]),
    # ---------------- desenho ----------------
    'extrudar': dict(t='Extrudar', g='Desenho', d='Desenho 2D que ganha espessura. Plano xy = desenha no chão e sobe (Z); xz = desenha de frente e vai para o fundo (Y); yz = desenha de lado e vai para a direita (X).',
                     p=[('perfil', 'perfil', None, 'Desenho'), ('plano', 'e', 'xy', 'Plano do desenho', 'xy|xz|yz'), ('posicao', 'n', 0, 'Posição do plano'), ('altura', 'n', 10, 'Espessura'),
                        ('simetrico', 'b', False, 'Para os dois lados'), ('conicidade', 'n', 0, 'Inclinar paredes (graus)'), P_MODO, P_REP]),
    'revolucao': dict(t='Revolução', g='Desenho', d='Desenho de MEIO perfil que gira em volta do eixo (vaso, copo, botão, polia). No desenho: u = distância do eixo (>= 0), v = altura ao longo do eixo.',
                      p=[('perfil', 'perfil', None, 'Desenho (meio perfil)'), P_EIXO, ('angulo', 'n', 360, 'Ângulo (graus)')] + P_POS + [P_MODO, P_REP]),
    'loft': dict(t='Transição', g='Desenho', d='Liga desenhos em alturas diferentes (ex.: quadrado em baixo virando círculo em cima). secoes = [{"z": 0, "perfil": [...]}, {"z": 30, "perfil": [...]}].',
                 p=[('secoes', 'secoes', None, 'Seções'), ('reto', 'b', False, 'Paredes retas'), P_MODO, P_REP]),
    'varrer': dict(t='Varrer', g='Desenho', d='Um desenho (seção) que percorre um caminho 3D (cano, alça, fio). caminho = [[x,y,z], ...].',
                   p=[('perfil', 'perfil', None, 'Desenho da seção'), ('caminho', 'pts', None, 'Caminho [[x,y,z],...]'), ('curva', 'e', 'cantos', 'Caminho', 'cantos|arredondado|suave'), ('raio', 'n', 5, 'Raio dos cantos (arredondado)'), P_MODO, P_REP]),
    # ---------------- modificar ----------------
    'arredondar': dict(t='Arredondar', g='Modificar', d='Arredonda arestas (fillet). arestas: todas, cima, baixo, verticais, horizontais, circulares, ultimo (as do passo anterior), ou lista de números/pontos.',
                       p=[('raio', 'n', 2, 'Raio'), ('arestas', 'arestas', 'todas', 'Quais arestas')]),
    'chanfrar': dict(t='Chanfrar', g='Modificar', d='Corta as arestas em ângulo (chanfro).',
                     p=[('tamanho', 'n', 1, 'Tamanho'), ('arestas', 'arestas', 'todas', 'Quais arestas')]),
    'casca': dict(t='Casca', g='Modificar', d='Deixa a peça oca com parede de espessura fixa, abrindo uma face (caixa, pote, tampa).',
                  p=[('espessura', 'n', 2, 'Espessura da parede'), ('abrir', 'faces', 'cima', 'Face aberta')]),
    'furo': dict(t='Furo', g='Modificar', d='Furo redondo. (x, y, z) = centro da boca do furo; z vazio = na superfície. direcao = para onde a broca vai. profundidade 0 = atravessa.',
                 p=[('diametro', 'n', 4, 'Diâmetro'), ('profundidade', 'n', 0, 'Profundidade (0 = atravessa)'), ('x', 'n', 0, 'Posição X'), ('y', 'n', 0, 'Posição Y'), ('z', 'n', '', 'Posição Z (vazio = superfície)'),
                    ('direcao', 'e', '-z', 'Direção da broca', '-z|+z|-y|+y|-x|+x'), ('tipo', 'e', 'simples', 'Tipo', 'simples|rebaixado|escareado'),
                    ('diametro2', 'n', 8, 'Diâmetro da cabeça'), ('profundidade2', 'n', 3, 'Fundo da cabeça'), P_REP]),
    'cortar': dict(t='Cortar', g='Modificar', d='Corta num plano e joga fora um lado (manter menor = fica a parte de coordenada menor, ex.: eixo z = parte de baixo).',
                   p=[('eixo', 'e', 'z', 'Eixo', 'z|x|y'), ('posicao', 'n', 5, 'Posição'), ('manter', 'e', 'menor', 'Ficar com a parte', 'menor|maior')]),
    # ---------------- mover ----------------
    'mover': dict(t='Mover', g='Mover', d='Desloca a peça inteira.', p=[('dx', 'n', 0, 'Mover em X'), ('dy', 'n', 0, 'Mover em Y'), ('dz', 'n', 0, 'Mover em Z')]),
    'girar': dict(t='Girar', g='Mover', d='Gira a peça inteira em volta do centro dela.', p=[('eixo', 'e', 'z', 'Eixo', 'z|x|y'), ('angulo', 'n', 90, 'Ângulo (graus)')]),
    'escalar': dict(t='Escalar', g='Mover', d='Aumenta/diminui (100 = igual). Pode ser diferente em cada eixo.', p=[('x', 'n', 100, 'X (%)'), ('y', 'n', 100, 'Y (%)'), ('z', 'n', 100, 'Z (%)')]),
    'espelhar': dict(t='Espelhar', g='Mover', d='Espelha a peça num plano. juntar = fica o original + o espelho (peça simétrica).',
                     p=[('plano', 'e', 'yz', 'Plano do espelho', 'yz|xz|xy'), ('posicao', 'n', 0, 'Posição do plano'), ('juntar', 'b', True, 'Juntar com o original')]),
    'assentar': dict(t='Assentar', g='Mover', d='Centraliza em X/Y e apoia a base em Z=0 (pronta para a mesa).', p=[]),
    # ---------------- avancado ----------------
    'importar': dict(t='Importar', g='Avançado', d='Traz um arquivo (STL, 3MF, OBJ = malha; STEP = sólido exato) para somar/subtrair ou começar dele.',
                     p=[('caminho', 'arq', '', 'Arquivo'), ('escala', 'n', 100, 'Escala (%)'), ('assentar', 'b', True, 'Centralizar e apoiar'), ('x', 'n', 0, 'Posição X'), ('y', 'n', 0, 'Posição Y'), ('z', 'n', 0, 'Posição Z'), P_MODO]),
    'codigo': dict(t='Código', g='Avançado', d='Modelagem livre por código Python (build123d). Variáveis: peca (a peça atual ou None), v (variáveis do projeto), bd, math, np. Termine com: resultado = <sólido>.',
                   p=[('codigo', 'cod', 'resultado = peca', 'Código')]),
}
GRUPOS = ['Criar', 'Desenho', 'Modificar', 'Mover', 'Avançado']
PRECISA_PECA = ('arredondar', 'chanfrar', 'casca', 'furo', 'cortar', 'mover', 'girar', 'escalar', 'espelhar', 'assentar', 'texto')
SO_CAD = ('arredondar', 'chanfrar', 'casca')


def padrao(op):
    return {p[0]: copy.deepcopy(p[2]) for p in OPS[op]['p'] if p[2] is not None}


def ajuda(op=None):
    """Texto de ajuda das ferramentas (para a IA e para a tela)."""
    if op:
        if op not in OPS: raise ErroModelo('ferramenta desconhecida: %s (existem: %s)' % (op, ', '.join(OPS)))
        o = OPS[op]
        return dict(op=op, nome=o['t'], grupo=o['g'], descricao=o['d'],
                    parametros=[dict(nome=p[0], tipo=_TIPOS.get(p[1], p[1]), padrao=p[2], rotulo=p[3], **({'opcoes': p[4].split('|')} if len(p) > 4 else {})) for p in o['p']])
    return dict(ferramentas=[dict(op=k, nome=o['t'], grupo=o['g'], descricao=o['d'], parametros=[p[0] for p in o['p']]) for k, o in OPS.items()], perfil=AJUDA_PERFIL, repetir=AJUDA_REPETIR,
                arestas=AJUDA_ARESTAS, numeros='Todo numero pode ser uma conta com variaveis do projeto: "largura/2 + folga".',
                coordenadas='mm. X = direita, Y = fundo, Z = cima. Nas formas (x, y) = centro e z = base.')


_TIPOS = {'n': 'numero ou conta', 'i': 'inteiro', 's': 'texto', 'e': 'escolha', 'b': 'true/false', 'pts': 'lista de pontos', 'perfil': 'desenho 2D (lista de figuras)',
          'arestas': 'seletor de arestas', 'faces': 'seletor de faces', 'rep': 'repetir (dict)', 'cod': 'codigo python', 'arq': 'caminho de arquivo', 'secoes': 'lista de {z, perfil}'}
AJUDA_PERFIL = ('perfil = lista de figuras 2D (u, v em mm). Cada figura: {"t":"ret","l":40,"a":20,"x":0,"y":0,"r":3,"g":0} retangulo (l=largura, a=altura, r=raio dos cantos, g=giro) | '
                '{"t":"circ","d":10,"x":0,"y":0} | {"t":"elipse","l":20,"a":10} | {"t":"reg","n":6,"d":20} poligono regular | {"t":"rasgo","c":30,"l":8} rasgo/oblongo | '
                '{"t":"poli","pts":[[0,0],[20,0],[10,15]]} poligono livre | {"t":"caminho","ini":[0,0],"seg":[["l",20,0],["a",25,5,20,10],["l",0,10]]} linhas ("l", u, v) e arcos ("a", u_meio, v_meio, u_fim, v_fim), fecha sozinho | '
                '{"t":"texto","txt":"Oi","tam":10,"fonte":"Arial"}. Em qualquer figura, "furo": true tira a figura do desenho (janela/furo).')
AJUDA_REPETIR = ('repetir = {"tipo":"linear","n":4,"dx":10,"dy":0,"dz":0} (n copias andando dx/dy/dz; opcional "n2","dx2","dy2","dz2" para grade) ou '
                 '{"tipo":"circular","n":6,"cx":0,"cy":0,"cz":0,"eixo":"z","angulo":360} (n copias em volta de um centro).')
AJUDA_ARESTAS = ('arestas: "todas" | "cima" | "baixo" | "verticais" | "horizontais" | "circulares" | "ultimo" (criadas pelo passo anterior) | "frente" | "tras" | "esquerda" | "direita" | '
                 'lista de numeros (ids de "arestas" do estado) | {"perto": [[x,y,z], ...]} (a aresta mais proxima de cada ponto) | lista misturando tudo. '
                 'faces (casca): "cima", "baixo", "frente", "tras", "esquerda", "direita", "nenhuma", lista de ids ou {"perto": [[x,y,z]]}.')


# ============================ estado de um passo ============================
class Est:
    """Resultado depois de um passo: um solido exato (CAD) ou uma malha (peca vinda de STL)."""
    __slots__ = ('sol', 'malha')

    def __init__(self, sol=None, malha=None): self.sol = sol; self.malha = malha

    @property
    def vazio(self): return self.sol is None and self.malha is None

    @property
    def tipo(self): return 'vazio' if self.vazio else ('cad' if self.sol is not None else 'malha')

    def limites(self):
        if self.sol is not None:
            b = self.sol.bounding_box(); return np.array([[b.min.X, b.min.Y, b.min.Z], [b.max.X, b.max.Y, b.max.Z]])
        if self.malha is not None: return np.asarray(self.malha.bounds, dtype=float)
        return np.zeros((2, 3))


def _vec(v): return (float(v.X), float(v.Y), float(v.Z))


def _malha_de_solido(sol, tol=0.03, ang=0.25):
    import trimesh
    V, F = sol.tessellate(tol, ang)
    if not F: raise ErroModelo('a forma ficou vazia')
    m = trimesh.Trimesh(vertices=np.array([_vec(v) for v in V]), faces=np.array(F), process=False)
    m.merge_vertices(digits_vertex=4); m.update_faces(m.nondegenerate_faces()); m.remove_unreferenced_vertices()      # sem isso sobram triangulos 'agulha' nos polos e a malha nao fecha
    return m


def _solido_valido(r, oque='o resultado'):
    bd = motor()
    if r is None: raise ErroModelo('%s ficou vazio' % oque)
    if isinstance(r, (list, tuple)) or type(r).__name__ == 'ShapeList':
        r = [x for x in r if x is not None]
        if not r: raise ErroModelo('%s ficou vazio' % oque)
        ss = [s for x in r for s in x.solids()]
        if not ss: raise ErroModelo('%s nao e um solido' % oque)
        r = bd.Part(bd.Compound(children=ss).wrapped)
    if not isinstance(r, bd.Part):
        try: ss = list(r.solids())
        except Exception: raise ErroModelo('%s nao e um solido' % oque)
        if not ss: raise ErroModelo('%s ficou vazio (a forma cobriu a peca inteira, ou nao tocou nela?)' % oque)
        r = bd.Part(bd.Compound(children=ss).wrapped)              # Part(solido.wrapped) direto fica com volume 0
    try: vol = float(r.volume)
    except Exception: vol = 0.0
    if not r.solids() or vol <= 1e-9: raise ErroModelo('%s ficou vazio (a forma cobriu a peca inteira, ou nao tocou nela?)' % oque)
    return r


def _bool_malha(a, b, modo):
    import trimesh
    try:
        if modo == 'somar': r = trimesh.boolean.union([a, b], engine='manifold')
        elif modo == 'subtrair': r = trimesh.boolean.difference([a, b], engine='manifold')
        else: r = trimesh.boolean.intersection([a, b], engine='manifold')
    except Exception as e:
        raise ErroModelo('nao consegui %s na malha: %s. Se a peca veio de um STL com buracos, conserte o STL antes.' % (modo, str(e)[:100]))
    if r is None or len(r.faces) == 0: raise ErroModelo('o resultado ficou vazio')
    return r


def combinar(est, pecas, modo):
    """Junta as formas novas (lista de solidos CAD) com a peca atual."""
    bd = motor()
    if modo not in MODOS.split('|'): raise ErroModelo("modo deve ser um de: " + MODOS.replace('|', ', '))
    pecas = [p for p in pecas if p is not None]
    if not pecas: raise ErroModelo('nenhuma forma para aplicar')
    if modo == 'novo' or est.vazio:
        if est.vazio and modo in ('subtrair', 'intersectar'): raise ErroModelo('ainda nao ha peca para %s. Crie uma forma primeiro (modo somar).' % modo)
        r = pecas[0]
        for p in pecas[1:]: r = r + p
        return Est(sol=_solido_valido(r))
    if est.sol is not None:
        try:
            if modo == 'somar': r = est.sol + pecas
            elif modo == 'subtrair': r = est.sol - pecas
            else:
                u = pecas[0]
                for p in pecas[1:]: u = u + p
                r = est.sol & u
        except ErroModelo: raise
        except Exception as e: raise ErroModelo('nao consegui %s: %s' % (modo, str(e)[:120]))
        return Est(sol=_solido_valido(r))
    m = est.malha
    for p in pecas: m = _bool_malha(m, _malha_de_solido(p), modo)
    return Est(malha=m)


# ============================ desenho 2D (perfil) ============================
def perfil_para_sketch(perfil, vs):
    """Lista de figuras -> Sketch do build123d no plano XY local (u, v)."""
    bd = motor()
    if isinstance(perfil, dict): perfil = [perfil]
    if not perfil: raise ErroModelo('o desenho esta vazio (adicione pelo menos uma figura)')
    soma, tira = None, None
    for n, f in enumerate(perfil):
        if not isinstance(f, dict) or 't' not in f: raise ErroModelo('figura %d do desenho sem tipo "t"' % (n + 1))
        t = f['t']; x, y, g = num(f.get('x'), vs), num(f.get('y'), vs), num(f.get('g'), vs)
        try:
            if t == 'ret':
                l, a, r = num(f.get('l'), vs, 10), num(f.get('a'), vs, 10), num(f.get('r'), vs)
                if l <= 0 or a <= 0: raise ErroModelo('retangulo com medida zero')
                r = min(r, min(l, a) / 2 - 0.01)
                s = bd.RectangleRounded(l, a, r) if r > 0.01 else bd.Rectangle(l, a)
            elif t == 'circ':
                d = num(f.get('d'), vs, 10)
                if d <= 0: raise ErroModelo('circulo com diametro zero')
                s = bd.Circle(d / 2)
            elif t == 'elipse': s = bd.Ellipse(num(f.get('l'), vs, 20) / 2, num(f.get('a'), vs, 10) / 2)
            elif t == 'reg':
                nl = int(num(f.get('n'), vs, 6))
                if nl < 3: raise ErroModelo('poligono regular precisa de 3 lados ou mais')
                s = bd.RegularPolygon(num(f.get('d'), vs, 20) / 2, nl)
            elif t == 'rasgo':
                c, l = num(f.get('c'), vs, 30), num(f.get('l'), vs, 8)
                if c <= l: raise ErroModelo('no rasgo, o comprimento (c) precisa ser maior que a largura (l)')
                s = bd.SlotOverall(c, l)
            elif t == 'poli':
                pts = [(num(p[0], vs), num(p[1], vs)) for p in f.get('pts', [])]
                if len(pts) < 3: raise ErroModelo('poligono precisa de pelo menos 3 pontos')
                from shapely.geometry import Polygon as _P
                if not _P(pts).is_valid: raise ErroModelo('o poligono cruza ele mesmo (confira a ordem dos pontos)')
                s = bd.Polygon(*pts, align=None)
            elif t == 'caminho':
                p0 = (num(f['ini'][0], vs), num(f['ini'][1], vs)); ini = p0; eds = []
                for sg in f.get('seg', []):
                    if sg[0] == 'l': p1 = (num(sg[1], vs), num(sg[2], vs)); eds.append(bd.Line(p0, p1))
                    elif sg[0] == 'a': pm = (num(sg[1], vs), num(sg[2], vs)); p1 = (num(sg[3], vs), num(sg[4], vs)); eds.append(bd.ThreePointArc(p0, pm, p1))
                    else: raise ErroModelo('segmento do caminho deve ser ["l", u, v] ou ["a", u_meio, v_meio, u_fim, v_fim]')
                    p0 = p1
                if len(eds) < 2: raise ErroModelo('caminho precisa de pelo menos 2 segmentos')
                if math.hypot(p0[0] - ini[0], p0[1] - ini[1]) > 1e-6: eds.append(bd.Line(p0, ini))
                s = bd.make_face(bd.Wire(eds))
            elif t == 'texto':
                txt = str(f.get('txt', '')).strip()
                if not txt: raise ErroModelo('escreva o texto')
                s = bd.Text(txt, num(f.get('tam'), vs, 10), font=str(f.get('fonte') or 'Arial'))
            else: raise ErroModelo('figura desconhecida "%s" (use ret, circ, elipse, reg, rasgo, poli, caminho, texto)' % t)
        except ErroModelo: raise
        except Exception as e: raise ErroModelo('figura %d (%s) do desenho: %s' % (n + 1, t, str(e)[:100]))
        if g: s = bd.Rot(0, 0, g) * s
        if x or y: s = bd.Pos(x, y) * s
        if f.get('furo'): tira = s if tira is None else tira + s
        else: soma = s if soma is None else soma + s
    if soma is None: raise ErroModelo('o desenho so tem furos; falta a figura principal')
    r = soma - tira if tira is not None else soma
    if not r.faces(): raise ErroModelo('o desenho ficou sem area')
    return r


def _plano(plano, pos, vs):
    """Plano do desenho: 'xy' (u=X, v=Y, sobe em Z), 'xz' (u=X, v=Z, vai em +Y), 'yz' (u=Y, v=Z, vai em +X) ou dict {o:[x,y,z], n:[..], x:[..]}."""
    bd = motor()
    if isinstance(plano, dict):
        o = [num(c, vs) for c in plano.get('o', (0, 0, 0))]; n = np.array([num(c, vs) for c in plano.get('n', (0, 0, 1))], dtype=float)
        if np.linalg.norm(n) < 1e-9: raise ErroModelo('plano com normal zero')
        n = n / np.linalg.norm(n)
        if plano.get('x'): xd = np.array([num(c, vs) for c in plano['x']], dtype=float)
        else: xd = np.array([1.0, 0, 0]) if abs(n[2]) > 0.9 else np.cross([0, 0, 1.0], n)
        xd = xd - n * float(xd @ n); xd = xd / np.linalg.norm(xd)
        return bd.Plane(origin=tuple(o), x_dir=tuple(xd), z_dir=tuple(n)), tuple(n)
    p = num(pos, vs)
    if plano == 'xy': return bd.Plane(origin=(0, 0, p), x_dir=(1, 0, 0), z_dir=(0, 0, 1)), (0, 0, 1)
    if plano == 'xz': return bd.Plane(origin=(0, p, 0), x_dir=(1, 0, 0), z_dir=(0, -1, 0)), (0, 1, 0)
    if plano == 'yz': return bd.Plane(origin=(p, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0)), (1, 0, 0)
    raise ErroModelo("plano deve ser 'xy', 'xz' ou 'yz'")


def _rot_eixo(eixo):
    bd = motor()
    if eixo == 'z': return bd.Rot(0, 0, 0)
    if eixo == 'x': return bd.Rot(0, 90, 0)
    if eixo == 'y': return bd.Rot(-90, 0, 0)
    raise ErroModelo("eixo deve ser 'x', 'y' ou 'z'")


_DIRS = {'+x': (1, 0, 0), '-x': (-1, 0, 0), '+y': (0, 1, 0), '-y': (0, -1, 0), '+z': (0, 0, 1), '-z': (0, 0, -1)}


def _cil_dir(d, comp, origem, direcao):
    """Cilindro de diametro d que comeca em 'origem' e vai 'comp' mm na direcao dada."""
    bd = motor(); dv = _DIRS[direcao]
    c = bd.Cylinder(d / 2, comp, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return bd.Location(bd.Plane(origin=tuple(origem), z_dir=dv)) * c


# ============================ repetir ============================
def _repetir(pecas, rep, vs):
    bd = motor()
    if not rep or not isinstance(rep, dict) or not rep.get('tipo') or rep.get('tipo') == 'nao': return pecas
    n = int(num(rep.get('n'), vs, 1))
    if n < 1 or n > 400: raise ErroModelo('repetir: n deve ficar entre 1 e 400')
    out = []
    if rep['tipo'] == 'linear':
        d1 = [num(rep.get(k), vs) for k in ('dx', 'dy', 'dz')]; n2 = int(num(rep.get('n2'), vs, 1)); d2 = [num(rep.get(k), vs) for k in ('dx2', 'dy2', 'dz2')]
        if n * max(1, n2) > 400: raise ErroModelo('repetir: copias demais (maximo 400)')
        for j in range(max(1, n2)):
            for i in range(n):
                t = [d1[k] * i + d2[k] * j for k in range(3)]
                out += [p if (i == 0 and j == 0) else bd.Pos(*t) * p for p in pecas]
    elif rep['tipo'] == 'circular':
        c = [num(rep.get(k), vs) for k in ('cx', 'cy', 'cz')]; ang = num(rep.get('angulo'), vs, 360.0); eixo = rep.get('eixo', 'z')
        if eixo not in 'xyz': raise ErroModelo("repetir circular: eixo deve ser x, y ou z")
        ax = bd.Axis(tuple(c), {'x': (1, 0, 0), 'y': (0, 1, 0), 'z': (0, 0, 1)}[eixo])
        passo = ang / n if abs(abs(ang) - 360) < 1e-6 else (ang / (n - 1) if n > 1 else 0)
        for i in range(n): out += [p if i == 0 else p.rotate(ax, passo * i) for p in pecas]
    else: raise ErroModelo("repetir: tipo deve ser 'linear' ou 'circular'")
    return out


# ============================ seletores ============================
def _meio(e): return np.array(_vec(e.position_at(0.5)))


def _chave_aresta(e):
    m = _meio(e); return (round(float(m[0]), 2), round(float(m[1]), 2), round(float(m[2]), 2), round(float(e.length), 2))


def _pontos_aresta(e, n=None):
    bd = motor(); gt = e.geom_type
    if gt == bd.GeomType.LINE: n = 2
    elif n is None: n = int(max(8, min(48, e.length / 1.2)))
    return np.array([_vec(p) for p in e.positions(np.linspace(0.0, 1.0, n))])


def selecionar_arestas(sol, sel, anterior=None):
    """Seletor -> lista de arestas do solido. Ver AJUDA_ARESTAS."""
    bd = motor(); es = list(sol.edges())
    if not es: raise ErroModelo('a peca nao tem arestas')
    bb = sol.bounding_box(); mn = np.array(_vec(bb.min)); mx = np.array(_vec(bb.max)); tol = 0.02

    def um(s):
        if isinstance(s, bool): raise ErroModelo('seletor de arestas invalido')
        if isinstance(s, (int, float)):
            i = int(s)
            if not (0 <= i < len(es)): raise ErroModelo('nao existe a aresta %d (a peca tem %d: de 0 a %d)' % (i, len(es), len(es) - 1))
            return [es[i]]
        if isinstance(s, dict):
            if 'perto' in s:
                meios = np.array([_meio(e) for e in es]); out = []
                for p in s['perto']:
                    d = np.linalg.norm(meios - np.array([float(c) for c in p]), axis=1); i = int(np.argmin(d))
                    if d[i] > max(3.0, float(np.linalg.norm(mx - mn)) * 0.08): raise ErroModelo('nao achei aresta perto do ponto %s (a mais proxima esta a %.1f mm; a peca mudou?)' % (list(p), d[i]))
                    out.append(es[i])
                return out
            raise ErroModelo('seletor de arestas: use {"perto": [[x,y,z], ...]}')
        if not isinstance(s, str): raise ErroModelo('seletor de arestas invalido: %r' % (s,))
        s = s.strip().lower()
        if s == 'todas': return es
        if s in ('cima', 'baixo', 'frente', 'tras', 'esquerda', 'direita'):
            k, lim = {'cima': (2, mx[2]), 'baixo': (2, mn[2]), 'frente': (1, mn[1]), 'tras': (1, mx[1]), 'esquerda': (0, mn[0]), 'direita': (0, mx[0])}[s]
            return [e for e in es if np.all(np.abs(_pontos_aresta(e, 5)[:, k] - lim) < tol)]
        if s in ('verticais', 'horizontais'):
            out = []
            for e in es:
                if e.geom_type != bd.GeomType.LINE:
                    if s == 'horizontais' and np.ptp(_pontos_aresta(e, 5)[:, 2]) < tol: out.append(e)
                    continue
                p = _pontos_aresta(e); d = p[-1] - p[0]; L = np.linalg.norm(d)
                if L < 1e-9: continue
                vert = abs(d[2]) / L > 0.999
                if (s == 'verticais') == vert and (vert or abs(d[2]) / L < 0.001): out.append(e)
            return out
        if s == 'circulares': return [e for e in es if e.geom_type in (bd.GeomType.CIRCLE, bd.GeomType.ELLIPSE)]
        if s == 'ultimo':
            if anterior is None: return es
            velhas = {_chave_aresta(e) for e in anterior.edges()}
            return [e for e in es if _chave_aresta(e) not in velhas]
        raise ErroModelo('seletor de arestas desconhecido: "%s". %s' % (s, AJUDA_ARESTAS))

    itens = sel if isinstance(sel, (list, tuple)) else [sel]
    out, vistos = [], set()
    for s in itens:
        for e in um(s):
            k = _chave_aresta(e)
            if k not in vistos: vistos.add(k); out.append(e)
    if not out: raise ErroModelo('nenhuma aresta encontrada com "%s"' % (sel,))
    return out


def selecionar_faces(sol, sel):
    bd = motor(); fs = list(sol.faces())
    bb = sol.bounding_box(); mn = np.array(_vec(bb.min)); mx = np.array(_vec(bb.max))

    def um(s):
        if isinstance(s, (int, float)) and not isinstance(s, bool):
            i = int(s)
            if not (0 <= i < len(fs)): raise ErroModelo('nao existe a face %d (a peca tem %d)' % (i, len(fs)))
            return [fs[i]]
        if isinstance(s, dict) and 'perto' in s:
            cs = np.array([_vec(f.center()) for f in fs]); out = []
            for p in s['perto']: out.append(fs[int(np.argmin(np.linalg.norm(cs - np.array([float(c) for c in p]), axis=1)))])
            return out
        if isinstance(s, str):
            s = s.strip().lower()
            if s in ('nenhuma', ''): return []
            if s in ('cima', 'baixo', 'frente', 'tras', 'esquerda', 'direita'):
                k, lim, sinal = {'cima': (2, mx[2], 1), 'baixo': (2, mn[2], -1), 'frente': (1, mn[1], -1), 'tras': (1, mx[1], 1), 'esquerda': (0, mn[0], -1), 'direita': (0, mx[0], 1)}[s]
                out = []
                for f in fs:
                    c = _vec(f.center())
                    if abs(c[k] - lim) < 0.05 and f.geom_type == bd.GeomType.PLANE: out.append(f)
                if not out:                                         # peca arredondada: a face mais extrema naquela direcao
                    out = [max(fs, key=lambda f: _vec(f.center())[k] * sinal)]
                return out
        raise ErroModelo('seletor de faces invalido: %r. %s' % (s, AJUDA_ARESTAS))

    itens = sel if isinstance(sel, (list, tuple)) else [sel]
    out = []
    for s in itens:
        for f in um(s):
            if not any(f is g for g in out): out.append(f)
    return out


# ============================ as ferramentas ============================
def _formas(op, p, vs, est):
    """Devolve a lista de solidos novos de um passo 'que cria forma' (antes de somar/subtrair)."""
    bd = motor(); N = lambda k, d=0.0: num(p.get(k), vs, d)
    A_BASE = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    pos = lambda: bd.Pos(N('x'), N('y'), N('z'))

    def positivo(*ks):
        for k in ks:
            if N(k) <= 0: raise ErroModelo('"%s" precisa ser maior que zero' % k)

    if op == 'caixa':
        positivo('largura', 'profundidade', 'altura'); r = min(N('raio'), min(N('largura'), N('profundidade')) / 2 - 0.01)
        if r > 0.01: s = bd.extrude(bd.RectangleRounded(N('largura'), N('profundidade'), r), N('altura'))
        else: s = bd.Box(N('largura'), N('profundidade'), N('altura'), align=A_BASE)
        return [pos() * bd.Rot(0, 0, N('giro')) * s]
    if op == 'cilindro':
        positivo('diametro', 'altura')
        return [pos() * _rot_eixo(p.get('eixo', 'z')) * bd.Cylinder(N('diametro') / 2, N('altura'), align=A_BASE)]
    if op == 'tubo':
        positivo('diametro', 'altura', 'parede')
        if N('parede') * 2 >= N('diametro'): raise ErroModelo('a parede do tubo e grossa demais para esse diametro')
        s = bd.Cylinder(N('diametro') / 2, N('altura'), align=A_BASE) - bd.Pos(0, 0, -0.5) * bd.Cylinder(N('diametro') / 2 - N('parede'), N('altura') + 1, align=A_BASE)
        return [pos() * _rot_eixo(p.get('eixo', 'z')) * s]
    if op == 'esfera':
        positivo('diametro'); return [pos() * bd.Sphere(N('diametro') / 2)]
    if op == 'cone':
        positivo('diametro', 'altura')
        if N('diametro_topo') < 0: raise ErroModelo('diametro do topo nao pode ser negativo')
        return [pos() * _rot_eixo(p.get('eixo', 'z')) * bd.Cone(N('diametro') / 2, N('diametro_topo') / 2, N('altura'), align=A_BASE)]
    if op == 'toro':
        positivo('diametro', 'diametro_fio')
        if N('diametro_fio') >= N('diametro'): raise ErroModelo('o fio e grosso demais para esse anel')
        return [pos() * _rot_eixo(p.get('eixo', 'z')) * bd.Torus(N('diametro') / 2, N('diametro_fio') / 2)]
    if op == 'prisma':
        positivo('diametro', 'altura'); n = int(N('lados', 6))
        if n < 3 or n > 200: raise ErroModelo('o prisma precisa de 3 a 200 lados')
        s = bd.extrude(bd.Rot(0, 0, N('giro')) * bd.RegularPolygon(N('diametro') / 2, n), N('altura'))
        return [pos() * _rot_eixo(p.get('eixo', 'z')) * s]
    if op == 'cunha':
        positivo('largura', 'profundidade', 'altura'); L, T, H, D = N('largura'), max(0.0, N('topo')), N('altura'), N('profundidade')
        if T > L: raise ErroModelo('o topo nao pode ser mais largo que a base')
        pts = [(-L / 2, 0), (L / 2, 0)] + ([(-L / 2 + T, H), (-L / 2, H)] if T > 0.01 else [(-L / 2, H)])
        pl = bd.Plane(origin=(0, -D / 2, 0), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
        s = bd.extrude(pl * bd.Polygon(*pts, align=None), D, dir=(0, 1, 0))
        return [pos() * bd.Rot(0, 0, N('giro')) * s]
    if op == 'extrudar':
        if N('altura') <= 0: raise ErroModelo('a espessura precisa ser maior que zero')
        sk = perfil_para_sketch(p.get('perfil'), vs); pl, dv = _plano(p.get('plano', 'xy'), p.get('posicao'), vs)
        kw = dict(amount=N('altura'), dir=dv)
        if p.get('simetrico'): kw['both'] = True; kw['amount'] = N('altura') / 2
        if N('conicidade'): kw['taper'] = N('conicidade')
        try: s = bd.extrude(pl * sk, **kw)
        except Exception as e: raise ErroModelo('nao consegui extrudar esse desenho: %s' % str(e)[:120])
        return [s]
    if op == 'revolucao':
        sk = perfil_para_sketch(p.get('perfil'), vs); eixo = p.get('eixo', 'z'); o = (N('x'), N('y'), N('z'))
        bbs = sk.bounding_box()
        if bbs.min.X < -1e-6: raise ErroModelo('na revolucao o desenho nao pode passar para o lado negativo de u (u = distancia do eixo). Menor u do desenho: %.2f' % bbs.min.X)
        xd, zd, ad = {'z': ((1, 0, 0), (0, -1, 0), (0, 0, 1)), 'x': ((0, 0, 1), (0, 1, 0), (1, 0, 0)), 'y': ((1, 0, 0), (0, 0, 1), (0, 1, 0))}[eixo]
        ang = N('angulo', 360.0)
        if abs(ang) < 0.01 or abs(ang) > 360: raise ErroModelo('angulo da revolucao deve ficar entre 0 e 360')
        try: s = bd.revolve(bd.Plane(origin=o, x_dir=xd, z_dir=zd) * sk, axis=bd.Axis(o, ad), revolution_arc=ang)
        except Exception as e: raise ErroModelo('nao consegui girar esse desenho: %s' % str(e)[:120])
        return [s]
    if op == 'loft':
        sec = p.get('secoes') or []
        if len(sec) < 2: raise ErroModelo('a transicao precisa de pelo menos 2 secoes: [{"z": 0, "perfil": [...]}, {"z": 20, "perfil": [...]}]')
        fs = []
        for s_ in sorted(sec, key=lambda s_: num(s_.get('z'), vs)):
            sk = perfil_para_sketch(s_.get('perfil'), vs)
            if len(sk.faces()) != 1: raise ErroModelo('cada secao da transicao deve ser UMA figura fechada (sem ilhas separadas)')
            fs.append(bd.Plane(origin=(0, 0, num(s_.get('z'), vs))) * sk)
        try: s = bd.loft(fs, ruled=bool(p.get('reto')))
        except Exception as e: raise ErroModelo('nao consegui fazer a transicao: %s' % str(e)[:120])
        return [s]
    if op == 'varrer':
        pts = [tuple(num(c, vs) for c in q) for q in (p.get('caminho') or [])]
        if len(pts) < 2 or any(len(q) != 3 for q in pts): raise ErroModelo('o caminho precisa de pelo menos 2 pontos [x, y, z]')
        sk = perfil_para_sketch(p.get('perfil'), vs); cv = p.get('curva', 'cantos')
        try:
            if cv == 'suave' and len(pts) > 2: cam = bd.Spline(*pts)
            elif cv == 'arredondado' and len(pts) > 2: cam = bd.FilletPolyline(*pts, radius=max(0.1, N('raio', 5)))
            else: cam = bd.Polyline(*pts)
            w = bd.Wire(cam.edges()) if not isinstance(cam, bd.Wire) else cam
            t0 = w.tangent_at(0); o0 = w.position_at(0)
            pl = bd.Plane(origin=_vec(o0), z_dir=_vec(t0))
            s = bd.sweep(pl * sk, path=w, transition=bd.Transition.RIGHT if cv == 'cantos' else bd.Transition.ROUND)
        except ErroModelo: raise
        except Exception as e: raise ErroModelo('nao consegui varrer por esse caminho (curvas fechadas demais para o tamanho da secao?): %s' % str(e)[:120])
        return [s]
    if op == 'furo':
        d = N('diametro'); direcao = p.get('direcao', '-z')
        if d <= 0: raise ErroModelo('o diametro do furo precisa ser maior que zero')
        if direcao not in _DIRS: raise ErroModelo('direcao deve ser uma de: ' + ', '.join(_DIRS))
        dv = np.array(_DIRS[direcao], dtype=float); k = int(np.argmax(np.abs(dv))); lim = est.limites(); o = np.array([N('x'), N('y'), N('z')])
        zvazio = p.get('xyz'[k]) in (None, '')
        if zvazio: o[k] = lim[1][k] if dv[k] < 0 else lim[0][k]                # boca na superficie de onde a broca entra
        diag = float(np.linalg.norm(lim[1] - lim[0])) + 2
        prof = N('profundidade'); folga = 0.3
        if prof > 0: f = _cil_dir(d, prof + folga, o - dv * folga, direcao)
        else: f = _cil_dir(d, diag * 2 + 2, o - dv * (diag + 1), direcao)
        tipo = p.get('tipo', 'simples'); out = [f]
        if tipo == 'rebaixado':
            if N('diametro2') <= d: raise ErroModelo('o diametro da cabeca precisa ser maior que o do furo')
            out.append(_cil_dir(N('diametro2'), N('profundidade2') + folga, o - dv * folga, direcao))
        elif tipo == 'escareado':
            d2 = N('diametro2')
            if d2 <= d: raise ErroModelo('o diametro da cabeca precisa ser maior que o do furo')
            h = (d2 - d) / 2
            c = bd.Cone(d2 / 2 + folga, d / 2, h + folga, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
            out.append(bd.Location(bd.Plane(origin=tuple(o - dv * folga), z_dir=tuple(dv))) * c)
        elif tipo != 'simples': raise ErroModelo("tipo do furo: simples, rebaixado ou escareado")
        r = out[0]
        for x in out[1:]: r = r + x
        return [r]
    if op == 'texto':
        txt = str(p.get('txt', '')).strip()
        if not txt: raise ErroModelo('escreva o texto')
        prof = N('prof', 1)
        if prof <= 0: raise ErroModelo('o relevo/fundo precisa ser maior que zero')
        lim = est.limites(); c = (lim[0] + lim[1]) / 2; face = p.get('face', 'cima'); emb = 0.25
        tab = {'cima': ((c[0], c[1], lim[1][2]), (1, 0, 0), (0, 0, 1)), 'baixo': ((c[0], c[1], lim[0][2]), (1, 0, 0), (0, 0, -1)),
               'frente': ((c[0], lim[0][1], c[2]), (1, 0, 0), (0, -1, 0)), 'tras': ((c[0], lim[1][1], c[2]), (-1, 0, 0), (0, 1, 0)),
               'direita': ((lim[1][0], c[1], c[2]), (0, 1, 0), (1, 0, 0)), 'esquerda': ((lim[0][0], c[1], c[2]), (0, -1, 0), (-1, 0, 0))}
        if face not in tab: raise ErroModelo('face deve ser uma de: ' + ', '.join(tab))
        o, xd, nd = tab[face]; nd_ = np.array(nd, dtype=float)
        try: sk = bd.Pos(N('u'), N('v')) * bd.Rot(0, 0, N('giro')) * bd.Text(txt, N('tam', 8), font=str(p.get('fonte') or 'Arial'))
        except Exception as e: raise ErroModelo('nao consegui desenhar esse texto: %s' % str(e)[:100])
        if p.get('tipo', 'relevo') == 'relevo':
            pl = bd.Plane(origin=tuple(np.array(o) - nd_ * emb), x_dir=xd, z_dir=nd); s = bd.extrude(pl * sk, prof + emb, dir=nd)
        else:
            pl = bd.Plane(origin=tuple(np.array(o) + nd_ * emb), x_dir=xd, z_dir=nd); s = bd.extrude(pl * sk, prof + emb, dir=tuple(-nd_))
        return [s]
    raise ErroModelo('ferramenta sem forma: ' + op)


def _importar(p, vs):
    c = str(p.get('caminho') or '')
    if not os.path.isfile(c): raise ErroModelo('arquivo nao encontrado: %s' % c)
    ext = os.path.splitext(c)[1].lower(); esc = num(p.get('escala'), vs, 100.0) / 100.0
    if esc <= 0: raise ErroModelo('escala precisa ser maior que zero')
    if ext in ('.step', '.stp'):
        bd = motor()
        try: s = bd.import_step(c)
        except Exception as e: raise ErroModelo('nao consegui ler o STEP: %s' % str(e)[:100])
        sol = _solido_valido(s.solids(), 'o arquivo STEP')
        if esc != 1: sol = _solido_valido(bd.scale(sol, by=esc))
        if p.get('assentar', True): sol = _assentar_sol(sol)
        return Est(sol=bd.Pos(num(p.get('x'), vs), num(p.get('y'), vs), num(p.get('z'), vs)) * sol)
    import trimesh
    try: m = trimesh.load(c, force='mesh')
    except Exception as e: raise ErroModelo('nao consegui ler o arquivo: %s' % str(e)[:100])
    if isinstance(m, trimesh.Scene): m = m.dump(concatenate=True)
    m = m.copy(); m.merge_vertices(); m.update_faces(m.nondegenerate_faces()); m.remove_unreferenced_vertices()
    if not m.is_watertight:
        try: trimesh.repair.fill_holes(m); trimesh.repair.fix_normals(m)
        except Exception: pass
    if esc != 1: m.apply_scale(esc)
    if p.get('assentar', True):
        b = m.bounds; m.apply_translation([-(b[0][0] + b[1][0]) / 2, -(b[0][1] + b[1][1]) / 2, -b[0][2]])
    m.apply_translation([num(p.get('x'), vs), num(p.get('y'), vs), num(p.get('z'), vs)])
    return Est(malha=m)


def _assentar_sol(sol):
    bd = motor(); b = sol.bounding_box()
    return bd.Pos(-(b.min.X + b.max.X) / 2, -(b.min.Y + b.max.Y) / 2, -b.min.Z) * sol


def _para_malha(est):
    """Est -> trimesh (para operar em modo malha)."""
    return est.malha if est.malha is not None else _malha_de_solido(est.sol)


def aplicar(est, passo, vs, anterior=None, permitir_codigo=False):
    """Executa UM passo sobre o estado e devolve o novo estado."""
    bd = motor(); op = passo.get('op'); p = passo
    if op not in OPS: raise ErroModelo('ferramenta desconhecida: %s' % op)
    N = lambda k, d=0.0: num(p.get(k), vs, d)
    if op in PRECISA_PECA and est.vazio: raise ErroModelo('"%s" precisa de uma peca. Crie uma forma primeiro.' % OPS[op]['t'])
    if op in SO_CAD and est.sol is None:
        raise ErroModelo('"%s" so funciona em peca criada aqui ou vinda de STEP. Esta peca veio de um STL (malha de triangulos), que nao tem arestas exatas.' % OPS[op]['t'])
    # ---- formas (somar / subtrair / intersectar / novo) ----
    if op in ('caixa', 'cilindro', 'tubo', 'esfera', 'cone', 'toro', 'prisma', 'cunha', 'extrudar', 'revolucao', 'loft', 'varrer'):
        return combinar(est, _repetir(_formas(op, p, vs, est), p.get('repetir'), vs), p.get('modo', 'somar'))
    if op == 'furo': return combinar(est, _repetir(_formas(op, p, vs, est), p.get('repetir'), vs), 'subtrair')
    if op == 'texto':
        novo = combinar(est, _formas(op, p, vs, est), 'somar' if p.get('tipo', 'relevo') == 'relevo' else 'subtrair')
        if p.get('tipo') == 'gravado' and abs(volume(novo) - volume(est)) < 1e-6: raise ErroModelo('o texto nao tocou na peca (tente outra face ou posicao)')
        return novo
    if op == 'importar':
        imp = _importar(p, vs); modo = p.get('modo', 'somar')
        if modo == 'novo' or est.vazio:
            if est.vazio and modo in ('subtrair', 'intersectar'): raise ErroModelo('ainda nao ha peca para %s' % modo)
            return imp
        if est.sol is not None and imp.sol is not None: return combinar(est, [imp.sol], modo)
        return Est(malha=_bool_malha(_para_malha(est), _para_malha(imp), modo))
    # ---- modificar ----
    if op in ('arredondar', 'chanfrar'):
        v = N('raio' if op == 'arredondar' else 'tamanho')
        if v <= 0: raise ErroModelo('o valor precisa ser maior que zero')
        es = selecionar_arestas(est.sol, p.get('arestas', 'todas'), anterior.sol if anterior is not None else None)
        try: r = bd.fillet(es, v) if op == 'arredondar' else bd.chamfer(es, v)
        except Exception:
            dica = ''
            if op == 'arredondar' and len(es) <= 80:
                try:
                    mx = math.floor(est.sol.max_fillet(es, tolerance=0.1, max_iterations=12) * 10) / 10
                    if 0 < mx < v: dica = ' O maior raio que cabe nelas e perto de %.1f mm.' % mx
                    else: dica = ' Alguma dessas arestas nao aceita arredondar junto com as outras: escolha menos arestas (clicando nelas) ou arredonde em dois passos.'
                except Exception: pass
            raise ErroModelo('%s de %.2f mm nao coube nessas arestas (%d).%s Tente um valor menor ou menos arestas.' % ('raio' if op == 'arredondar' else 'chanfro', v, len(es), dica))
        return Est(sol=_solido_valido(r))
    if op == 'casca':
        t = N('espessura')
        if t <= 0: raise ErroModelo('a espessura precisa ser maior que zero')
        fs = selecionar_faces(est.sol, p.get('abrir', 'cima'))
        try:
            if fs: r = bd.offset(est.sol, amount=-t, openings=fs)
            else: r = est.sol - bd.offset(est.sol, amount=-t)
        except Exception: raise ErroModelo('nao consegui fazer a casca com %.2f mm (parede grossa demais para a peca, ou forma complexa demais).' % t)
        return Est(sol=_solido_valido(r))
    if op == 'cortar':
        eixo = p.get('eixo', 'z'); manter = p.get('manter', 'menor')
        if eixo not in 'xyz' or manter not in ('menor', 'maior'): raise ErroModelo("cortar: eixo x/y/z e manter menor/maior")
        i = 'xyz'.index(eixo); lim = est.limites(); pos = N('posicao')
        if not (lim[0][i] < pos < lim[1][i]): raise ErroModelo('o plano de corte (%s = %.2f) esta fora da peca (ela vai de %.2f a %.2f)' % (eixo, pos, lim[0][i], lim[1][i]))
        tam = (lim[1] - lim[0]) + 20; c = (lim[0] + lim[1]) / 2; g = float(tam[i]) + 10
        c[i] = pos + (g / 2 if manter == 'menor' else -g / 2); tam[i] = g
        cx = bd.Pos(*c) * bd.Box(*[float(t_) for t_ in tam])
        return combinar(est, [cx], 'subtrair')
    # ---- mover ----
    if op in ('mover', 'girar', 'escalar', 'espelhar', 'assentar'):
        lim = est.limites(); c = (lim[0] + lim[1]) / 2
        if est.sol is not None:
            s = est.sol
            if op == 'mover': r = bd.Pos(N('dx'), N('dy'), N('dz')) * s
            elif op == 'girar': r = s.rotate(bd.Axis(tuple(c), {'x': (1, 0, 0), 'y': (0, 1, 0), 'z': (0, 0, 1)}[p.get('eixo', 'z')]), N('angulo', 90))
            elif op == 'escalar':
                f = [N('x', 100) / 100, N('y', 100) / 100, N('z', 100) / 100]
                if min(f) <= 0: raise ErroModelo('escala precisa ser maior que zero')
                r = bd.Pos(*c) * bd.scale(bd.Pos(*(-c)) * s, by=tuple(f) if len(set(f)) > 1 else f[0])
            elif op == 'espelhar':
                pl, _ = _plano({'yz': 'yz', 'xz': 'xz', 'xy': 'xy'}.get(p.get('plano', 'yz'), 'yz'), p.get('posicao'), vs)
                e = bd.mirror(s, about=pl); r = (s + e) if p.get('juntar', True) else e
            else: r = _assentar_sol(s)
            return Est(sol=_solido_valido(r))
        import trimesh
        from trimesh.transformations import rotation_matrix
        m = est.malha.copy()
        if op == 'mover': m.apply_translation([N('dx'), N('dy'), N('dz')])
        elif op == 'girar': m.apply_transform(rotation_matrix(math.radians(N('angulo', 90)), {'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]}[p.get('eixo', 'z')], point=c))
        elif op == 'escalar':
            f = [N('x', 100) / 100, N('y', 100) / 100, N('z', 100) / 100]
            if min(f) <= 0: raise ErroModelo('escala precisa ser maior que zero')
            m.apply_translation(-c); m.apply_scale(f); m.apply_translation(c)
        elif op == 'espelhar':
            i = {'yz': 0, 'xz': 1, 'xy': 2}.get(p.get('plano', 'yz'), 0); e = m.copy(); V = e.vertices.copy(); V[:, i] = 2 * N('posicao') - V[:, i]
            e = trimesh.Trimesh(vertices=V, faces=e.faces[:, ::-1], process=False)
            m = _bool_malha(m, e, 'somar') if p.get('juntar', True) else e
        else:
            b = m.bounds; m.apply_translation([-(b[0][0] + b[1][0]) / 2, -(b[0][1] + b[1][1]) / 2, -b[0][2]])
        return Est(malha=m)
    if op == 'codigo':
        if not permitir_codigo: raise ErroModelo('O passo "Codigo" esta desligado. Ligue "Permitir codigo" na aba Modelar (so ligue se confia em quem escreveu o codigo).')
        amb = {k: getattr(bd, k) for k in dir(bd) if not k.startswith('_')}
        amb.update(bd=bd, math=math, np=np, peca=est.sol, v=dict(vs), resultado=None)
        try: exec(compile(str(p.get('codigo', '')), '<codigo do passo>', 'exec'), amb)
        except ErroModelo: raise
        except Exception as e: raise ErroModelo('erro no codigo: %s: %s' % (type(e).__name__, str(e)[:200]))
        r = amb.get('resultado')
        if r is None: raise ErroModelo('o codigo precisa terminar com:  resultado = <solido>')
        return Est(sol=_solido_valido(r, 'o resultado do codigo'))
    raise ErroModelo('ferramenta nao implementada: ' + op)


def volume(est):
    if est.sol is not None: return float(est.sol.volume)
    if est.malha is not None: return float(abs(est.malha.volume))
    return 0.0


# ============================ dados para desenhar / escolher ============================
def dados_vista(est, tol=0.06, ang=0.16):
    """Triangulos (com o numero da face de cada um) + arestas (linhas) + tabelas de faces e arestas, para a tela e para a IA."""
    if est.vazio: return dict(V=np.zeros((0, 3)), F=np.zeros((0, 3), dtype=int), fid=np.zeros(0, dtype=int), arestas=[], adj=[], faces=[], info_arestas=[], tipo='vazio')
    if est.sol is None:
        m = est.malha; V = np.asarray(m.vertices, dtype=float); F = np.asarray(m.faces, dtype=int); ar = []; adjs = []
        try:
            mk = m.face_adjacency_angles > math.radians(32)
            for e, f in zip(m.face_adjacency_edges[mk][:6000], m.face_adjacency[mk][:6000]): ar.append(V[e]); adjs.append((int(f[0]), int(f[1])))
        except Exception: pass
        return dict(V=V, F=F, fid=np.arange(len(F)), arestas=ar, adj=adjs, faces=[], info_arestas=[], tipo='malha', lim=est.limites())       # em malha, a 'face' de cada aresta e o triangulo vizinho
    bd = motor(); sol = est.sol
    Vs, Fs, ids, faces = [], [], [], []; base = 0; mapa = {}
    for i, f in enumerate(sol.faces()):
        v, t = f.tessellate(tol, ang)
        if t:
            Vs.append(np.array([_vec(q) for q in v])); Fs.append(np.array(t, dtype=int) + base); ids.append(np.full(len(t), i, dtype=int)); base += len(v)
        c = _vec(f.center())
        try: n = _vec(f.normal_at(f.center()))
        except Exception: n = (0, 0, 0)
        nome = {bd.GeomType.PLANE: 'plana', bd.GeomType.CYLINDER: 'cilindrica', bd.GeomType.SPHERE: 'esferica', bd.GeomType.CONE: 'conica', bd.GeomType.TORUS: 'torica'}.get(f.geom_type, 'curva')
        faces.append(dict(id=i, tipo=nome, centro=[round(x, 2) for x in c], normal=[round(x, 3) for x in n], area=round(float(f.area), 2)))
        for e in f.edges(): mapa.setdefault(_chave_aresta(e), []).append(i)
    ar, adj, info = [], [], []
    for i, e in enumerate(sol.edges()):
        pts = _pontos_aresta(e); ar.append(pts); k = _chave_aresta(e); adj.append(tuple(mapa.get(k, ())))
        nome = {bd.GeomType.LINE: 'reta', bd.GeomType.CIRCLE: 'circular', bd.GeomType.ELLIPSE: 'eliptica'}.get(e.geom_type, 'curva')
        info.append(dict(id=i, tipo=nome, meio=[k[0], k[1], k[2]], comprimento=k[3], faces=list(adj[-1]), **({'costura': True} if len(set(adj[-1])) < 2 else {})))
    V = np.concatenate(Vs) if Vs else np.zeros((0, 3)); F = np.concatenate(Fs) if Fs else np.zeros((0, 3), dtype=int)
    return dict(V=V, F=F, fid=np.concatenate(ids) if ids else np.zeros(0, dtype=int), arestas=ar, adj=adj, faces=faces, info_arestas=info, tipo='cad', lim=est.limites())


def malha_final(est, fino=True):
    """trimesh do resultado (para STL / Mesa 3D)."""
    if est.vazio: raise ErroModelo('ainda nao ha peca')
    if est.malha is not None: return est.malha.copy()
    return _malha_de_solido(est.sol, 0.02 if fino else 0.06, 0.18 if fino else 0.28)


def malha_previa(op, passo, vs, est):
    """Malha da 'ferramenta' de um passo (o que ele vai somar/tirar), para mostrar em vermelho antes de aplicar. None se o passo nao tem forma."""
    import trimesh
    if op == 'cortar' and not est.vazio:                      # mostra o plano do corte (uma placa fina)
        i = 'xyz'.index(passo.get('eixo', 'z')) if passo.get('eixo', 'z') in 'xyz' else 2; lim = est.limites(); tam = (lim[1] - lim[0]) * 1.25 + 4; c = (lim[0] + lim[1]) / 2
        tam[i] = 0.3; c[i] = num(passo.get('posicao'), vs); m = trimesh.creation.box(extents=tam); m.apply_translation(c); return m
    if op not in ('caixa', 'cilindro', 'tubo', 'esfera', 'cone', 'toro', 'prisma', 'cunha', 'extrudar', 'revolucao', 'loft', 'varrer', 'furo', 'texto'): return None
    if op in ('furo', 'texto') and est.vazio: return None
    ps = _repetir(_formas(op, passo, vs, est), passo.get('repetir') if op != 'texto' else None, vs)
    ms = [_malha_de_solido(x, 0.08, 0.3) for x in ps]
    return trimesh.util.concatenate(ms) if len(ms) > 1 else ms[0]


# ============================ projeto (a receita) ============================
class Projeto:
    def __init__(self, nome='Peça 1'):
        self.nome = nome; self.passos = []; self.vars = {}; self.arquivo = None; self.permitir_codigo = False
        self._cache = []            # estado depois de cada passo (None = precisa refazer)
        self.erro = None            # (indice do passo, mensagem) do primeiro passo que falhou
        self._desf = []; self._ref = []; self.alterado = False; self._dv = None; self.tempo = 0.0

    # ---- historico (desfazer / refazer) ----
    def _foto(self): return (copy.deepcopy(self.passos), dict(self.vars))

    def _marcar(self):
        self._desf.append(self._foto()); self._desf = self._desf[-80:]; self._ref = []; self.alterado = True

    def desfazer(self):
        if not self._desf: raise ErroModelo('Nao ha o que desfazer.')
        self._ref.append(self._foto()); self.passos, self.vars = self._desf.pop(); self._invalidar(0); self.reconstruir()

    def refazer(self):
        if not self._ref: raise ErroModelo('Nao ha o que refazer.')
        self._desf.append(self._foto()); self.passos, self.vars = self._ref.pop(); self._invalidar(0); self.reconstruir()

    def _invalidar(self, i):
        self._cache = self._cache[:max(0, i)]; self._dv = None

    # ---- construir ----
    def reconstruir(self):
        """Refaz os passos que mudaram. Para no primeiro que der erro (os de antes ficam valendo)."""
        t0 = time.time(); self.erro = None; self._dv = None
        est = self._cache[-1] if self._cache else Est()
        for i in range(len(self._cache), len(self.passos)):
            ps = self.passos[i]
            if ps.get('desligado'): self._cache.append(est); continue
            try:
                ant = self._cache[i - 2] if i >= 2 else (Est() if i == 1 else None)
                if ps.get('op') in ('arredondar', 'chanfrar') and i >= 1:
                    ant = self._estado_antes(i - 1)
                est = aplicar(est, ps, self.vars, ant, self.permitir_codigo)
            except ErroModelo as e: self.erro = (i, str(e)); break
            except Exception as e: self.erro = (i, '%s: %s' % (type(e).__name__, str(e)[:160])); break
            self._cache.append(est)
        self.tempo = time.time() - t0
        return self.erro is None

    def _estado_antes(self, i):
        """Estado ANTES do passo i (para o seletor 'ultimo')."""
        return self._cache[i - 1] if i >= 1 and i - 1 < len(self._cache) else Est()

    @property
    def est(self): return self._cache[-1] if self._cache else Est()

    # ---- mexer na receita ----
    def _limpo(self, passo):
        if not isinstance(passo, dict) or passo.get('op') not in OPS: raise ErroModelo('passo invalido: precisa de "op" (uma de: %s)' % ', '.join(OPS))
        d = padrao(passo['op']); d.update({k: v for k, v in passo.items() if v is not None or k in ('z',)}); d['op'] = passo['op']
        conhecidos = {q[0] for q in OPS[d['op']]['p']} | {'op', 'nome', 'desligado'}
        extra = [k for k in d if k not in conhecidos]
        if extra: raise ErroModelo('parametro(s) desconhecido(s) em "%s": %s. Validos: %s' % (d['op'], ', '.join(extra), ', '.join(q[0] for q in OPS[d['op']]['p'])))
        self._fixar_seletores(d)
        return d

    def _fixar_seletores(self, d):
        """Numeros de aresta/face valem so para a peca de AGORA: troca por pontos (o seletor continua valendo se um passo antigo mudar)."""
        sol = self.est.sol
        if sol is None: return
        for k, lista, pt in (('arestas', lambda: list(sol.edges()), _meio), ('abrir', lambda: list(sol.faces()), lambda f: np.array(_vec(f.center())))):
            v = d.get(k)
            if v is None: continue
            itens = v if isinstance(v, (list, tuple)) else [v]
            if not any(isinstance(x, (int, float)) and not isinstance(x, bool) for x in itens): continue
            ls = lista(); novo = []
            for x in itens:
                if isinstance(x, (int, float)) and not isinstance(x, bool):
                    if not (0 <= int(x) < len(ls)): raise ErroModelo('nao existe %s numero %d (ha %d)' % ('a aresta' if k == 'arestas' else 'a face', int(x), len(ls)))
                    novo.append({'perto': [[round(float(c), 3) for c in pt(ls[int(x)])]]})
                else: novo.append(x)
            d[k] = novo

    def adicionar(self, passo, posicao=None):
        """Poe um passo novo no fim (ou em 'posicao'). Se der erro, o passo NAO entra e a peca fica como estava."""
        d = self._limpo(passo); self._marcar()
        i = len(self.passos) if posicao is None else max(0, min(int(posicao), len(self.passos)))
        self.passos.insert(i, d); self._invalidar(i)
        if not self.reconstruir():
            e = self.erro; self.passos, self.vars = self._desf.pop(); self._invalidar(i); self.reconstruir()
            raise ErroModelo(e[1] if e[0] == i else 'esse passo quebrou o passo %d (%s): %s' % (e[0] + 1, self.passos[e[0] - 1].get('op', '?') if e[0] > 0 else '?', e[1]))
        return i

    def editar(self, i, mud):
        """Muda parametros de um passo antigo; a peca e refeita dali para frente. Se quebrar, desfaz a mudanca."""
        i = self._idx(i); novo = dict(self.passos[i]); novo.update(mud or {}); novo = self._limpo_edit(novo); self._marcar()
        self.passos[i] = novo; self._invalidar(i)
        if not self.reconstruir():
            e = self.erro; self.passos, self.vars = self._desf.pop(); self._invalidar(i); self.reconstruir()
            raise ErroModelo(('passo %d: ' % (e[0] + 1)) + e[1])

    def _limpo_edit(self, d):
        conhecidos = {q[0] for q in OPS[d['op']]['p']} | {'op', 'nome', 'desligado'}
        extra = [k for k in d if k not in conhecidos]
        if extra: raise ErroModelo('parametro(s) desconhecido(s): ' + ', '.join(extra))
        return d

    def _idx(self, i):
        i = int(i)
        if not (0 <= i < len(self.passos)): raise ErroModelo('nao existe o passo %d (a receita tem %d)' % (i + 1, len(self.passos)))
        return i

    def remover(self, i):
        i = self._idx(i); self._marcar(); self.passos.pop(i); self._invalidar(i)
        if not self.reconstruir():
            e = self.erro; self.passos, self.vars = self._desf.pop(); self._invalidar(i); self.reconstruir()
            raise ErroModelo('nao da para apagar esse passo: o passo %d depende dele (%s)' % (e[0] + 2, e[1]))

    def alternar(self, i):
        i = self._idx(i); self._marcar(); self.passos[i]['desligado'] = not self.passos[i].get('desligado'); self._invalidar(i)
        if not self.reconstruir():
            e = self.erro; self.passos, self.vars = self._desf.pop(); self._invalidar(i); self.reconstruir()
            raise ErroModelo('nao da para desligar/ligar esse passo: passo %d: %s' % (e[0] + 1, e[1]))

    def definir_var(self, nome, valor):
        nome = str(nome).strip()
        if not nome.isidentifier() or nome in _FUNCS: raise ErroModelo('nome de variavel invalido: use letras, numeros e _ (ex.: largura, folga)')
        self._marcar()
        if valor is None or valor == '': self.vars.pop(nome, None)
        else: self.vars[nome] = num(valor, {k: v for k, v in self.vars.items() if k != nome})
        self._invalidar(0)
        if not self.reconstruir():
            e = self.erro; self.passos, self.vars = self._desf.pop(); self._invalidar(0); self.reconstruir()
            raise ErroModelo('com esse valor o passo %d falha: %s' % (e[0] + 1, e[1]))

    def limpar(self):
        self._marcar(); self.passos = []; self._invalidar(0); self.reconstruir()

    # ---- informacoes ----
    def dados(self):
        if self._dv is None:
            for tol, ang in ((0.06, 0.16), (0.12, 0.3), (0.3, 0.5)):          # peca com muita curva: malha de tela mais grossa (so a tela; o STL sai sempre fino)
                self._dv = dados_vista(self.est, tol, ang)
                if len(self._dv['F']) <= 20000 or self.est.sol is None: break
        return self._dv

    def descricao(self, i):
        ps = self.passos[i]; o = OPS[ps['op']]
        if ps.get('nome'): return ps['nome']
        g = lambda k: ps.get(k)
        f = lambda v: ('%g' % v) if isinstance(v, (int, float)) else str(v)
        op = ps['op']; m = {'somar': '', 'subtrair': ' (tirar)', 'intersectar': ' (interseção)', 'novo': ' (novo)'}.get(ps.get('modo', ''), '')
        if op == 'caixa': t = 'Caixa %s × %s × %s' % (f(g('largura')), f(g('profundidade')), f(g('altura')))
        elif op in ('cilindro', 'tubo', 'cone', 'prisma'): t = '%s ø%s × %s' % (o['t'], f(g('diametro')), f(g('altura')))
        elif op == 'esfera': t = 'Esfera ø%s' % f(g('diametro'))
        elif op == 'toro': t = 'Rosquinha ø%s' % f(g('diametro'))
        elif op == 'cunha': t = 'Rampa %s × %s × %s' % (f(g('largura')), f(g('profundidade')), f(g('altura')))
        elif op == 'texto': t = 'Texto "%s" %s' % (str(g('txt'))[:14], g('tipo'))
        elif op == 'extrudar': t = 'Extrudar %s mm (%s)' % (f(g('altura')), g('plano') if isinstance(g('plano'), str) else 'face')
        elif op == 'revolucao': t = 'Revolução %s°' % f(g('angulo'))
        elif op == 'arredondar': t = 'Arredondar %s mm' % f(g('raio'))
        elif op == 'chanfrar': t = 'Chanfrar %s mm' % f(g('tamanho'))
        elif op == 'casca': t = 'Casca %s mm' % f(g('espessura'))
        elif op == 'furo': t = 'Furo ø%s%s' % (f(g('diametro')), '' if not num(g('profundidade'), self.vars) else ' × %s' % f(g('profundidade')))
        elif op == 'cortar': t = 'Cortar em %s = %s' % (g('eixo'), f(g('posicao')))
        elif op == 'mover': t = 'Mover (%s, %s, %s)' % (f(g('dx')), f(g('dy')), f(g('dz')))
        elif op == 'girar': t = 'Girar %s° em %s' % (f(g('angulo')), g('eixo'))
        elif op == 'importar': t = 'Importar ' + os.path.basename(str(g('caminho')))[:22]
        else: t = o['t']
        rep = ps.get('repetir')
        if isinstance(rep, dict) and rep.get('tipo') in ('linear', 'circular'): t += ' ×%s' % f(rep.get('n', 1))
        return t + m

    def estado(self, detalhe=True):
        e = self.est; lim = e.limites(); tam = lim[1] - lim[0]; d = dict(projeto=self.nome, tipo=e.tipo, passos=[], variaveis=dict(self.vars), pode_desfazer=bool(self._desf), pode_refazer=bool(self._ref))
        for i, ps in enumerate(self.passos):
            d['passos'].append(dict(n=i + 1, descricao=self.descricao(i), desligado=bool(ps.get('desligado')), **{k: v for k, v in ps.items() if k not in ('desligado',)}))
        if self.erro: d['erro_no_passo'] = dict(n=self.erro[0] + 1, erro=self.erro[1])
        if not e.vazio:
            vol = volume(e); ped = len(e.sol.solids()) if e.sol is not None else 1
            if ped > 1: d['pedacos_soltos'] = ped; d['aviso_pedacos'] = 'ATENCAO: a peca ficou em %d pedacos separados (algum corte/furo dividiu a peca, ou uma forma somada nao encosta nela).' % ped
            d.update(min=[round(float(x), 2) for x in lim[0]], max=[round(float(x), 2) for x in lim[1]], tamanho=[round(float(x), 2) for x in tam],
                     centro=[round(float(x), 2) for x in (lim[0] + lim[1]) / 2], volume_cm3=round(vol / 1000.0, 2), peso_g_macico=dict(PLA=round(vol / 1000 * 1.24, 1), ABS=round(vol / 1000 * 1.04, 1), PETG=round(vol / 1000 * 1.27, 1)))
            if detalhe:
                dv = self.dados()
                if dv['tipo'] == 'cad':
                    d['n_faces'] = len(dv['faces']); d['n_arestas'] = len(dv['info_arestas'])
                    if len(dv['faces']) <= 60: d['faces'] = dv['faces']
                    if len(dv['info_arestas']) <= 90: d['arestas'] = dv['info_arestas']
                    else: d['aviso'] = 'peca com muitas arestas: use seletores por nome (cima, verticais, ultimo...) ou {"perto": [[x,y,z]]}'
                else: d['aviso'] = 'peca em MALHA (veio de STL): da para somar, furar, cortar, texto, mover; nao da para arredondar/chanfrar/casca.'
        d['dica'] = 'mm. X=direita, Y=fundo, Z=cima. Nas formas (x,y)=centro e z=base.'
        return d

    # ---- arquivos ----
    def para_json(self): return dict(formato='imprimir-ender-modelo', versao=1, nome=self.nome, variaveis=self.vars, passos=self.passos)

    def salvar(self, caminho=None):
        c = caminho or self.arquivo
        if not c: raise ErroModelo('sem nome de arquivo')
        os.makedirs(os.path.dirname(c), exist_ok=True)
        tmp = c + '.tmp'; json.dump(self.para_json(), open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1); os.replace(tmp, c)
        self.arquivo = c; self.alterado = False; return c

    @classmethod
    def abrir(cls, caminho, permitir_codigo=False):
        try: d = json.load(open(caminho, encoding='utf-8'))
        except Exception as e: raise ErroModelo('nao consegui abrir o projeto: %s' % str(e)[:100])
        if d.get('formato') != 'imprimir-ender-modelo': raise ErroModelo('esse arquivo nao e um projeto do Modelar')
        p = cls(d.get('nome') or os.path.splitext(os.path.basename(caminho))[0]); p.vars = {k: float(v) for k, v in (d.get('variaveis') or {}).items()}
        p.passos = [x for x in (d.get('passos') or []) if isinstance(x, dict) and x.get('op') in OPS]; p.arquivo = caminho; p.permitir_codigo = permitir_codigo
        p.reconstruir(); return p

    def exportar(self, caminho, assentar=True):
        """Grava STL / 3MF / OBJ (malha) ou STEP (solido exato). assentar: centraliza e apoia em Z=0 (como a Mesa 3D espera)."""
        e = self.est
        if e.vazio: raise ErroModelo('ainda nao ha peca para exportar')
        ext = os.path.splitext(caminho)[1].lower(); os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
        if ext in ('.step', '.stp'):
            if e.sol is None: raise ErroModelo('STEP so para peca criada aqui (esta veio de STL). Exporte como STL.')
            motor().export_step(_assentar_sol(e.sol) if assentar else e.sol, caminho); return caminho
        if ext not in ('.stl', '.3mf', '.obj'): raise ErroModelo('formato nao suportado: use .stl, .3mf, .obj ou .step')
        m = malha_final(e)
        if assentar:
            b = m.bounds; m.apply_translation([-(b[0][0] + b[1][0]) / 2, -(b[0][1] + b[1][1]) / 2, -b[0][2]])
        m.export(caminho); return caminho
