# Painel público de leads e produção

O Streamlit hospedado lê somente `dashboard_data_public.json`, que contém KPIs e tabelas agregadas. Relatórios originais, CPFs, telefones, nomes, contratos e o mapeamento privado de origens não são carregados pelo app hospedado.

## Atualização semanal

1. Mantenha o XLSX/ZIP original e o mapeamento real apenas no computador autorizado. Salve o mapeamento como `origin_mapping.txt` na raiz deste projeto; esse arquivo é ignorado pelo Git. `origin_mapping.example.txt` é apenas um modelo e não contém números reais.
2. Instale as dependências uma vez:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. Gere o agregado localmente, informando o relatório da semana:

   ```powershell
   .\.venv\Scripts\python.exe .\generate_public_data.py `
     --leads "C:\caminho\relatorio-da-semana.xlsx" `
     --mapping .\origin_mapping.txt
   ```

   Se a produção estiver em arquivo separado, informe também `--production "C:\caminho\producao.xlsx"`.

4. Confira os indicadores localmente e publique somente o código e `dashboard_data_public.json`. Nunca force a inclusão de XLSX, CSV, ZIP, `origin_mapping.txt`, `dashboard_data.json` ou arquivos de ambiente.

O arquivo público é atualizado junto ao repositório e o Streamlit Cloud o lê no próximo deploy/reinício do app. Não é preciso carregar planilha a cada abertura. Não há upload de dados brutos na interface hospedada.

## Segurança e limites

- O JSON publicado é público: qualquer pessoa com acesso ao repositório ou ao app poderá ver os indicadores agregados. Não use este formato para informação cuja própria agregação seja confidencial.
- O mapeamento privado é usado somente na geração local e não deve entrar no Git.
- O JSON contém apenas totais por período, origem, dia, produto e região; não inclui registros individuais, CPF, telefone, nome ou número de contrato.
- A origem é identificada pela coluna `Lead.numeroWhatsappOrigem` usando o mapeamento privado. Registros sem telefone, mas identificados como `agenda-mais` no CRM, são agrupados separadamente.
- Para CPFs repetidos, a pessoa e seus registros ficam associados à origem de seu primeiro lead válido.
- Os filtros de origem, produto e região recalculam os KPIs e gráficos a partir das tabelas agregadas.
- Produção pós-lead exige `ic_producao = 1` e data do contrato igual ou posterior à data de entrada do primeiro lead. É uma associação temporal, não uma prova de causalidade.
- “Sem produção pós-lead” não significa perda comercial confirmada.

## Filtros do painel

O filtro de período fica visível no corpo principal do painel, logo abaixo do título, e atualiza os KPIs e gráficos para o intervalo selecionado. O eixo temporal usa datas dd/mm e ajusta a frequência das marcações ao intervalo.

O agregado público precisa estar no esquema 2 para suportar o detalhamento diário do período.
