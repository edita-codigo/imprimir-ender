# Testes

```
pip install -r ../requirements.txt pytest
python -m pytest tests -v
```

- `test_mcp_anotacoes.py`: confere as anotações (somente leitura / destrutiva) de todas as ferramentas do MCP.
- `test_modelar.py`: motor CAD da aba Modelar (sempre roda). Os testes de tela e de API só rodam com `ENDER_TESTE_COMPLETO=1`.
- Nenhum teste desta pasta manda comando para a impressora. Os testes que usam a impressora de verdade estão em `testes_hw.py` na raiz e exigem a máquina parada e a sua permissão.
