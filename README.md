# Imprimir Ender

Programa para Windows (Python + tkinter) que **fatia, organiza e imprime** na **Creality Ender-3 V3 SE** direto pelo cabo USB, com mesa 3D, impressão colorida manual, editor de peças, vigia por câmera com IA, página no celular e um **servidor MCP** para uma IA (Claude, Cursor etc.) controlar tudo.

**Leia em:** Português · [English](README.en.md) · [Español](README.es.md) · [Русский](README.ru.md)

> Interface em **Português, English, Español, Русский**.

## Status: fase de testes

O que já é usado e funciona na prática: imprimir (fatiar com CuraEngine, enviar pela USB, PARAR), mesa 3D, página no celular e o servidor MCP.

**Ainda NÃO testado de verdade na impressora** (existe no código, mas está em teste): impressão colorida com troca de filamento, testes de diagnóstico das peças, editor de peças, importação de 3MF colorido, criação de peça pela Zoo e vigia por câmera com IA. Esses foram verificados só com impressora simulada. Use com a impressora à vista e conte com ajustes. Relatos e correções são bem-vindos.

## Recursos

**Imprimir**
- Abre STL ou G-code, fatia com o CuraEngine (presets ABS completo, ABS rápido, PLA) e mostra tempo e custo.
- Envia o G-code linha a linha pela serial esperando o `ok`; em erro desliga bico e mesa. Botão PARAR sempre disponível.
- Início seguro: mesa primeiro, G28, carrega o mapa de nivelamento salvo (M501 / M420 S1), ventoinha conforme o material.
- Pausa, continuar, troca de filamento (M600), sensor de filamento, fila de impressão com pausa entre peças.
- Acha a porta da impressora sozinho.

**Mesa 3D**
- Várias peças na mesa, mover, girar, escalar, copiar, organizar automático, encher a mesa.
- Visualização 3D própria (renderizador por software), com **suportes visíveis** na mesa.
- Importa **3MF com cores** (PrusaSlicer, Bambu/Orca em melhor esforço, 3MF padrão): cada parte vira uma peça com a cor lida do arquivo.
- "Imprimir só uma cor": imprime uma cor por vez, você troca o filamento e repete.
- Suportes: árvore ou normal, padrão, densidade, distância em Z e XY, teto.

**Impressão colorida manual**
- Define trocas de cor por camada; o programa pausa, leva o bico ao canto, descarrega/carrega o filamento e espera você trocar.

**Editar peça** (aba própria)
- Furo, corte por plano, formas (somar/subtrair), texto em relevo ou gravado nas 5 faces, desenho à mão por polígono, desfazer, voltar ao original. Nunca altera o arquivo original: salva cópia em `pecas_editadas`.

**Criar peça por texto (Zoo)**
- Gera uma peça a partir de uma descrição usando a Zoo (zoo.dev). Precisa da sua chave, com permissão marcada na aba.

**Testar a impressora**
- 12 testes: comunicação, termistores, fins de curso, sensor de filamento, cartão SD, tela, ventoinha, CR Touch, aquecer bico, aquecer mesa, motores, extrusor. Testes que aquecem ou mexem pedem permissão e o programa sempre desliga aquecedores no fim.

**Vigia por câmera**
- Tira foto da impressora de tempos em tempos (câmera IP) e manda para uma IA (JEV, OpenAI ou Gemini; você escolhe o modelo) para detectar falhas. Aviso por Pushover opcional.

**Outros**
- Nivelar a mesa morna, calibração (temperatura, retração), custo do rolo, histórico, time-lapse, aba Manual com explicações.
- **App na rede**: página para o celular (PWA, 4 idiomas) com status, cores, câmera, mesa e botão PARAR. Protegida por token.
- Servidor HTTP local (portas 8101 a 8110) com a API que o MCP usa.

## MCP (controlar o programa com uma IA)

O servidor `mcp_ender/server.py` tem **61 ferramentas**: status, imprimir (exige confirmação), mesa 3D, cores, editar peça (a IA consegue *ver* a peça), diagnóstico, Zoo, modo avançado, câmera e vigia. Lista completa em [`mcp_ender/MANUAL_MCP.md`](mcp_ender/MANUAL_MCP.md).

Ele não fala com a impressora direto: chama a API do programa, então as travas de segurança valem para a IA também. Na aba **IA / MCP** você gera/copia o token, copia o comando pronto para o Claude Code ou o JSON para outros clientes, e pode ligar o modo **somente leitura**.

## Instalação

1. Windows com Python 3.12.
2. Instale o [UltiMaker Cura](https://ultimaker.com/software/ultimaker-cura/) (o programa usa o CuraEngine dele; ele **não** vem neste repositório). O caminho está em `base_ender.py` (`CURA = ...`); ajuste se o seu for diferente.
3. `pip install -r requirements.txt`
4. Ligue a impressora no USB e rode `Imprimir_Ender.bat` (ou `pythonw imprimir_ender.py`).

Outras impressoras Marlin parecidas podem funcionar ajustando `perfil_impressora.json` (tamanho da mesa, canto de descarga) e os presets em `base_ender.py`.

## Segurança e privacidade

- Chaves de IA (JEV/OpenAI/Gemini/Zoo) e o token da rede ficam em arquivos `_PRIVADO_*` criados no seu PC, **ignorados pelo git**. Nunca os publique.
- O programa nunca usa chave sua sem você colocá-la.
- O token da página do celular e do MCP é gerado no seu PC; "Gerar novo token" invalida o anterior.
- **A IA só imprime com ordem sua**: `ender_imprimir` exige `confirmo=true`; `ender_peca_criar` e os testes que aquecem ou movem também pedem confirmação/permissão explícita. O botão PARAR e o modo **somente leitura** (aba IA / MCP) valem para a IA também.
- **Só fala com a sua rede**: o MCP chama apenas a API local do programa (`ENDER_URL`, padrão `http://127.0.0.1:8101`) com o seu token; não envia dados a terceiros. Só as funções opcionais de IA (vigia por câmera, Zoo) chamam serviços externos, e só com a chave que você colocou.
- **Ferramentas anotadas**: cada ferramenta do MCP declara `readOnlyHint` (só lê) ou `destructiveHint` (pode aquecer, mover, imprimir, apagar), para o cliente de IA pedir confirmação nas perigosas.
- Testes: `python -m pytest tests` (veja [`tests/README.md`](tests/README.md)); nenhum deles usa a impressora.

## Traduzir para outro idioma

`python traduzir_idiomas.py --codigo fr --nome "Français"` traduz todos os textos usando a API do Claude (modelo barato, em lotes; precisa de `ANTHROPIC_API_KEY`). `--simular` mostra o custo sem chamar. Depois acrescente o idioma em `i18n.IDIOMAS`. Limitações conhecidas: valores de listas suspensas e algumas mensagens dinâmicas continuam em português.

## Limitações conhecidas

- Escala uniforme apenas; peças maiores que a mesa (220 x 220 mm) são recusadas.
- 3MF de Bambu/Orca não foi testado com arquivos reais.
- Impressão colorida é manual (troca de filamento), não multimaterial automático.

## Comunidade

Quer ajuda, dar ideias ou mostrar sua impressão? Entre no grupo do WhatsApp: https://chat.whatsapp.com/Jn09rWfySDpDnSkwaIcdDH

Contribuições e issues aqui no GitHub são bem-vindas.

## Licença

MIT (veja `LICENSE`). O CuraEngine é AGPL e é usado como programa externo instalado por você.

Feito por [Edita Código](https://editacodigo.com.br).
