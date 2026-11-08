# Manual do MCP "ender-impressora"

Este MCP deixa uma IA (Claude Code, Claude Desktop, Cursor, qualquer cliente MCP) **controlar o programa Imprimir Ender**: olhar a impressora, mexer na Mesa 3D, trocar cores, editar peças, criar peças por texto e rodar diagnóstico. Ele NÃO fala com a impressora direto: chama a API do programa (`servidor_rede.py`, portas 8101 a 8110), então todas as travas de segurança do programa continuam valendo. **O programa precisa estar aberto.**

## Como ligar
1. No programa, aba **IA / MCP**: copie o comando do Claude Code (ou o JSON para outros clientes), ou clique em "Registrar no Claude Code agora".
2. O MCP lê o token de `_PRIVADO_token_rede.txt` (pasta do programa) ou da variável `ENDER_TOKEN`. Ao "Gerar novo token" na aba, o MCP deste PC continua funcionando sozinho. **Nunca publique esse arquivo.**
3. A aba tem também **SOMENTE LEITURA** (a IA só olha; o PARAR continua valendo).
4. Para outra IA fora do MCP, a aba mostra um texto pronto (endereço + token) para colar.

## Regras de segurança (valem para a IA)
- Nunca iniciar impressão sem o usuário pedir. `ender_imprimir` exige `confirmo=true`.
- Testes que aquecem/mexem a impressora e criação de peça pela Zoo exigem `confirmo=true` (e, na Zoo, a permissão marcada na aba Criar peça).
- G-code livre só com a impressora parada e só comandos da lista segura (bloqueia M112, M500, M502, M92 etc.; bico ≤ 275 °C, mesa ≤ 110 °C).
- A edição de peça nunca altera o arquivo original: salva uma cópia em `pecas_editadas`.
- Erro do programa volta como `{"ok": false, "erro": ...}`.

## Ferramentas

### Estado e controle da impressora

**`ender_status(completo: bool = False)`**  
Estado da impressora/programa: arquivo carregado, se esta imprimindo, temperaturas (bico/mesa), camada, progresso, tempo restante, pausa, fila, rolo de filamento, vigia. Use completo=true para incluir o log e o historico.

**`ender_enviar_arquivo(caminho: str)`**  
Envia um arquivo do PC (STL ou G-code) para o programa: ele carrega, fatia (se STL) e deixa pronto. NAO inicia a impressao. caminho = caminho completo do arquivo no PC.

**`ender_imprimir(confirmo: bool = False, pular_sensor: bool | None = None)`**  
INICIA a impressao do arquivo carregado: aquece bico e mesa e comeca a imprimir. So use com a autorizacao do usuario para ESTA impressao. confirmo precisa ser true. Recusado se ja esta imprimindo.

**`ender_parar()`**  
PARA a impressao em andamento (esfria e levanta o bico, conforme o programa). Sempre permitido.

**`ender_pausar()`**  
Pausa a impressao para trocar de filamento (retrai, sobe e vai para o canto).

**`ender_continuar()`**  
Continua a impressao depois da pausa (troca de filamento feita).

**`ender_purgar(mm: int = 40)`**  
Durante a pausa, empurra filamento (mm) para limpar a cor antiga do bico. Limite de seguranca: 5 a 150 mm.

**`ender_testar_sensor()`**  
Roda o teste do sensor de nivelamento (CR Touch). Recusado se estiver imprimindo.

**`ender_fila(acao: str)`**  
Controla a fila de impressao. acao: 'comecar' | 'continuar' (depois de tirar a peca) | 'pular' | 'parar'.

**`ender_gcode(comandos: list[str], permitir_outros: bool = False)`**  
Manda G-code direto para a impressora PARADA (ate 40 comandos, um por item) e devolve as respostas. Recusa comandos perigosos (M112, M500, M502, M92, ... mude esses so pelo painel da impressora), bico acima de 275 C e mesa acima de 110 C. Fora de uma lista simples (G0/G1/G28/G90/G91/G92, M82/M83/M84, M104-M109, M140/M190, M106/M107, M114/M115/M119, M220/M221...) so com permitir_outros=true. Nao funciona se estiver imprimindo/ocupada. Use com cuidado: mexe na maquina de verdade.

**`ender_log(linhas: int = 30)`**  
Ultimas linhas do log do programa (o que ele fez/avisou).

### Diagnóstico das peças da impressora

**`ender_diagnostico_lista()`**  
Lista os testes de diagnostico das pecas da impressora (id, nome, tipo: leitura/aquece/mexe/extrusor, o que faz) e o resultado do ultimo diagnostico rodado.

**`ender_diagnostico(testes: list = None, permitir_aquecer: bool = False, permitir_mover: bool = False, permitir_extrusor: bool = False, confirmo: bool = False, esperar_s: int = 600)`**  
DIAGNOSTICO da impressora: roda testes das pecas (comunicacao/firmware, termistores, fins de curso, sensor de filamento, cartao SD, display, ventoinha, CR Touch; e, se permitido, aquecimento do bico e da mesa, motores X/Y/Z, extrusor). testes: lista de ids (veja ender_diagnostico_lista) ou vazio = so os que apenas leem. Os que AQUECEM ou MEXEM exigem permitir_* = true E confirmo=true (o usuario tem que ter pedido; a mesa deve estar sem peca). Cada resultado: estado ok | falha | aviso | observar (o programa fez a acao, mas um HUMANO precisa confirmar olhando/ouvindo: pergunte ao usuario) + detalhe. Espera o fim e devolve tudo.

### Câmera e vigia

**`ender_flash(ligar: bool)`**  
Liga (true) ou desliga (false) o flash/lanterna do celular da camera (IP Webcam: /enabletorch e /disabletorch).

**`ender_foto()`**  
Tira uma foto da impressora agora, pela camera do vigia, e devolve a imagem (sem usar IA). O flash segue a opcao do programa.

**`ender_vigia_testar()`**  
Tira uma foto e manda para a IA do vigia (JEV/OpenAI/Gemini, com rodizio de chaves) para avaliar se a impressao esta boa. Gasta 1 uso da cota da chave.

**`ender_vigia_ativar(ativo: bool)`**  
Liga ou desliga o vigia por camera (ele so olha enquanto uma impressao esta em andamento).

### Mesa 3D (peças, cores, suporte)

**`ender_mesa_ver()`**  
Pecas na Mesa 3D (id, nome, posicao x/y em mm, rotacao, escala, tamanho, se cabe) e a mesa (220x220x250). x,y = centro da peca; a frente da mesa e y=0.

**`ender_mesa_adicionar(caminho_stl: str)`**  
Poe um STL (caminho completo no PC) na Mesa 3D, num lugar livre.

**`ender_mesa_copiar(id: int, n: int = 1)`**  
Faz n copias da peca `id` em lugares livres (as que nao couberem sao puladas).

**`ender_mesa_editar(id: int, x: float | None = None, y: float | None = None, rot: float | None = None, escala: float | None = None)`**  
Muda a peca `id`: x,y (centro, mm; 0,0 = canto da frente a esquerda), rot (graus), escala (%).

**`ender_mesa_remover(id: int)`**  
Tira a peca `id` da mesa.

**`ender_mesa_encher(id: int)`**  
Enche a mesa com copias da peca `id` ate nao caber mais.

**`ender_mesa_organizar()`**  
Arruma todas as pecas em fileiras (gira 90 graus quando ajuda).

**`ender_mesa_limpar()`**  
Tira todas as pecas da mesa.

**`ender_mesa_fatiar()`**  
Monta a mesa em um STL so e fatia (como o botao FATIAR E VOLTAR PARA IMPRIMIR). Depois use ender_status ate o arquivo ficar pronto. Recusa se houver peca fora da mesa ou colada em outra.

**`ender_suporte_ver()`**  
Ajustes do suporte (o que sustenta partes no ar): tipo, estrutura (normal/arvore), padrao, densidade, angulo, folgas, teto.

**`ender_suporte_definir(tipo: str | None = None, estrutura: str | None = None, padrao: str | None = None, densidade: int | None = None, angulo: int | None = None, folga_z: float | None = None, folga_xy: float | None = None, teto: bool | None = None)`**  
Muda o suporte. tipo: 'nenhum' | 'mesa' (so apoiado na mesa) | 'tudo' (tambem sobre a peca). estrutura: 'normal' | 'arvore' (galhos finos, bom para peca curva). padrao: zigzag|lines|grid|triangles|cross|gyroid. densidade 3-80 (%). angulo 20-80 (graus: acima disso a parte inclinada recebe suporte). folga_z/folga_xy em mm (distancia entre suporte e peca). teto: camada cheia embaixo da peca. Se ha um STL carregado ele e fatiado de novo sozinho. Nao funciona imprimindo.

**`ender_mesa_imagem(vista: str = '3d')`**  
IMAGEM da Mesa 3D (as pecas como estao agora) para voce ver. vista: 3d, frente, topo, lado.

**`ender_mesa_importar_3mf(caminho_3mf: str)`**  
IMPORTA um arquivo 3MF: cada parte vira uma peca na Mesa, com a cor lida do arquivo (do nome da parte, do extrusor/filamento ou do material). Devolve as partes e as cores.

**`ender_mesa_so_cor(cor: str = 'todas')`**  
Deixa na Mesa so as pecas de UMA cor (ex.: 'Vermelho'); as outras ficam guardadas. 'todas' traz tudo de volta. Para imprimir uma cor de cada vez (troca de filamento manual).

### Impressão colorida

**`ender_cores_ver()`**  
Mostra a configuracao de impressao colorida (cor inicial, trocas), em que CAMADA cada troca cai na peca carregada e o estado da troca em andamento.

**`ender_cores_definir(ativo: bool, cor_inicial_nome: str = '', cor_inicial_hex: str = '', trocas: list[dict] | None = None)`**  
Configura a impressao COLORIDA (troca de filamento a mao, so mesmo material). trocas = lista de {"modo": "altura" (mm) ou "camada", "valor": numero, "nome": "Vermelho", "hex": "#E5322D"}. Cada troca pausa a impressao: o bico vai ao canto, puxa o filamento velho e avisa o usuario (alarme + celular); o usuario troca e toca CONTINUAR (ender_continuar); o bico cospe ate a cor sair limpa (ender_purgar para cuspir mais) e o usuario toca CONTINUAR de novo. Nao funciona durante uma impressao.

### Editar peça (furo, corte, formas, texto, desenho)

**`ender_editar_abrir(id_peca: int = 0, caminho_stl: str = '')`**  
ABRE uma peca para editar (a copia: o original nunca e alterado). id_peca = numero da peca na Mesa 3D (veja ender_mesa_ver; ja considera escala e rotacao) OU caminho_stl de um arquivo. Devolve tamanho, min/max e centro em mm. Sistema de coordenadas da edicao: X e Y centrados na peca, Z=0 na base. Depois use ender_editar_ver para VER.

**`ender_editar_estado()`**  
Estado da edicao: peca aberta, tamanho/min/max/centro (mm), se a malha e fechada, lista de passos feitos e se da para desfazer.

**`ender_editar_ver(vista: str = '3d', largura: int = 900, altura: int = 700)`**  
IMAGEM da peca em edicao, para voce ver o resultado. vista: 3d, frente, topo, lado, tras ou baixo.

**`ender_editar_furo(x: float, y: float, z: float, diametro: float, comprimento: float = 0, eixo: str = 'z')`**  
FURO (cilindro subtraido) centrado em (x,y,z) mm no sistema da peca. eixo = direcao do furo: z (vertical), x ou y (lateral). comprimento 0 = atravessa a peca inteira.

**`ender_editar_cortar(eixo: str, posicao: float, manter: str = 'menor')`**  
CORTA a peca num plano e joga fora um lado. eixo x|y|z, posicao em mm, manter 'menor' (fica a parte de coordenada menor, ex.: z: a de baixo) ou 'maior'.

**`ender_editar_forma(tipo: str, modo: str, x: float, y: float, z: float, a: float, b: float = 0, c: float = 0, eixo: str = 'z')`**  
SOMA ou SUBTRAI uma forma. tipo: caixa (a=largura X, b=profundidade Y, c=altura Z), cilindro (a=diametro, b=comprimento, eixo) ou esfera (a=diametro). modo: 'somar' ou 'subtrair'. (x,y,z) = centro da forma, em mm.

**`ender_editar_texto(texto: str, altura_letra: float = 8, relevo_ou_fundo: float = 1, modo: str = 'relevo', face: str = 'cima', deslocar_direita: float = 0, deslocar_cima: float = 0, girar_graus: float = 0, fonte: str = 'Arial')`**  
ESCREVE texto na peca. modo: 'relevo' (sai da face) ou 'gravado' (entra). face: cima, frente, tras, esquerda, direita (a face e a do envelope da peca; em superficies curvas o gravado pode nao tocar). O texto fica centrado na face; deslocar_* move em mm; altura_letra e o tamanho da letra; relevo_ou_fundo e a espessura. Fontes: Arial, Segoe UI, Consolas, Courier New, Times New Roman, Impact, Verdana, Comic Sans MS, Georgia.

**`ender_editar_desenhar(pontos: list, plano: str, posicao_plano: float, espessura: float, modo: str = 'somar')`**  
DESENHA uma figura 2D (poligono: lista de pontos [[u,v],...] em mm, na ordem do contorno; use muitos pontos para curvas) e extruda com 'espessura'. modo 'somar' (cola na peca) ou 'subtrair' (corta). plano 'xy': u=X, v=Y, extruda de Z=posicao_plano para CIMA. plano 'xz': u=X, v=Z, extruda de Y=posicao_plano para +Y. plano 'yz': u=Y, v=Z, extruda de X=posicao_plano para +X. Os pontos usam as MESMAS coordenadas da peca (veja min/max em ender_editar_estado). Ex.: pino de 6x6 em cima de uma peca de 20 mm de altura: plano xy, posicao_plano 19.6, espessura 5.

**`ender_editar_desfazer()`**  
Desfaz o ultimo passo da edicao.

**`ender_editar_voltar_original()`**  
Descarta todos os passos e volta a peca como estava ao abrir.

**`ender_editar_salvar(adicionar_na_mesa: bool = True)`**  
SALVA a peca editada como COPIA nova (pasta pecas_editadas; o original nunca e mexido) e, se adicionar_na_mesa, poe na Mesa 3D.

### Criar peça por texto (Zoo)

**`ender_peca_status()`**  
Estado da criacao de pecas por texto (Zoo): se esta criando, resultado da ultima, chaves (quantas/de molho, sem mostrar), se o zoo.exe foi achado e se a API esta autorizada.

**`ender_peca_criar(descricao: str, confirmo: bool = False, adicionar_na_mesa: bool = True, esperar_s: int = 600)`**  
CRIA uma peca a partir de uma descricao em texto, pela Zoo (IA de CAD), e (se adicionar_na_mesa) poe o STL na Mesa 3D. GASTA tempo da conta Zoo do usuario (chaves dele): so use quando o usuario pedir e passe confirmo=true. Funciona so se o usuario marcou "permitir que a IA/celular criem pecas" na aba Criar peca. Seja especifico com as medidas (ex.: 'suporte de parede em L, 60x20x5 mm, dois furos de 4 mm'). Espera ate esperar_s segundos pelo resultado.

### Modo avançado (início/fim, ventoinha, G-code extra)

**`ender_avancado_ver()`**  
Modo avancado: o que esta ligado (inicio, fim, ventoinha, velocidade/fluxo, G-code extra, ajustes do fatiador) e os comandos de inicio e fim que vao sair.

**`ender_avancado_definir(ajustes: dict)`**  
Muda o modo avancado (mescla com o atual). So vale com "ativo": true. Chaves: ativo (bool); inicio {home, mapa, linha}; fim {retrair, subir, estacionar, bico, mesa, ventoinha, motores}; ventoinha {modo: preset|desligada|fixa|camada, pct 0-100, camada}; velocidade e fluxo (%, 20-300); gcode_antes, gcode_depois (texto, um comando por linha); por_camada (texto "camada: comando" por linha); fatiador_extra (texto "chave=valor" por linha, ajustes do CuraEngine). O arquivo carregado e preparado de novo sozinho. Nao funciona imprimindo.

## Receitas

**Editar uma peça que está na mesa**
1. `ender_mesa_ver` → veja os ids. 2. `ender_editar_abrir(id_peca=1)` → tamanho e coordenadas. 3. `ender_editar_ver` → olhe a peça. 4. Faça os passos (`ender_editar_furo`, `ender_editar_texto`, `ender_editar_forma`, `ender_editar_desenhar`...) e confira com `ender_editar_ver` depois de cada um. 5. `ender_editar_desfazer` se errar. 6. `ender_editar_salvar` (copia para a mesa).

**Desenhar à mão** (ex.: pino, suporte, gancho): `ender_editar_desenhar` recebe um polígono (lista de pontos em mm) e a espessura. Use as mesmas coordenadas de `min`/`max` de `ender_editar_estado`. Para curvas, use muitos pontos. Para um furo redondo use `ender_editar_furo`; para um recorte qualquer use `ender_editar_desenhar` com `modo="subtrair"`.

**Peça colorida (3MF)**: `ender_mesa_importar_3mf` → cada parte vira uma peça com a cor lida do arquivo (nome da parte, extrusor ou material). `ender_mesa_so_cor("Vermelho")` deixa só uma cor na mesa; imprima, troque o filamento, e repita com a próxima cor; `ender_mesa_so_cor("todas")` traz tudo de volta. Se uma peça não couber na mesa, use `ender_mesa_editar(id, escala=...)`.

**Diagnóstico**: `ender_diagnostico()` (só leitura) → firmware, termistores, fins de curso, sensor de filamento, SD, tela e ventoinha. Com `permitir_aquecer`/`permitir_mover`/`permitir_extrusor` + `confirmo=true` ele testa também o aquecimento, os motores e o extrusor. Resultados `observar` pedem confirmação humana (pergunte ao usuário se viu/ouviu).

**Imprimir**: `ender_status` (livre?) → `ender_enviar_arquivo` ou monte a mesa e `ender_mesa_fatiar` → confira tempo e custo → o usuário autoriza → `ender_imprimir(confirmo=true)` → `ender_status` de tempos em tempos, `ender_foto` para olhar.
