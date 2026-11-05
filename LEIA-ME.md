# Painel público de leads e produção

O Streamlit hospedado lê somente `dashboard_data_public.json`, que contém KPIs e tabelas agregadas. Relatórios originais, CPFs, telefones, contratos, CNPJs e o mapeamento privado de origens não são carregados pelo app hospedado. O JSON inclui rótulos de loja e franqueado para os filtros.

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
     --leads "C:\caminho\base-completa.zip" "C:\caminho\leads-incrementais.csv" `
     --production "C:\caminho\producao-atualizada.zip" `
     --store-dimension "C:\caminho\dim_lojas_fisicas_rows.csv" `
     --mapping .\origin_mapping.txt
   ```

   Informe todos os arquivos de leads em `--leads`. O gerador consolida registros repetidos por `Lead.leadId` e mantém CPFs válidos. A produção pode vir em um ZIP ou CSV separado.

   A dimensão de lojas precisa das colunas `cod_loja_atual` e `nome_loja`; o gerador lê somente essas duas colunas. Códigos ausentes na dimensão aparecem com o código e o nome “Nome indisponível”. O franqueado vem de `no_franqueado_atual` na produção.

4. Confira os indicadores localmente e publique somente o código e `dashboard_data_public.json`. Nunca force a inclusão de XLSX, CSV, ZIP, `origin_mapping.txt`, `dashboard_data.json` ou arquivos de ambiente.

O arquivo público é atualizado junto ao repositório e o Streamlit Cloud o lê no próximo deploy/reinício do app. Não é preciso carregar planilha a cada abertura. Não há upload de dados brutos na interface hospedada.

## Segurança e limites

- O JSON publicado é público: qualquer pessoa com acesso ao repositório ou ao app poderá ver os indicadores agregados e os rótulos de loja/franqueado. Não use este formato para informação cuja própria agregação seja confidencial.
- O mapeamento privado é usado somente na geração local e não deve entrar no Git.
- O JSON contém apenas totais por período, origem, dia, produto, região, loja e franqueado; não inclui registros individuais, CPF, telefone, CNPJ ou número de contrato.
- A origem é identificada pela coluna `Lead.numeroWhatsappOrigem` usando o mapeamento privado. Registros sem telefone, mas identificados como `agenda-mais` no CRM, são agrupados separadamente.
- Para CPFs repetidos, a pessoa e seus registros ficam associados à origem de seu primeiro lead válido.
- O filtro de franqueado limita as lojas disponíveis. Franqueado e loja, como produto e região, filtram os indicadores financeiros; leads e conversão respondem ao período e à origem.
- Produção pós-lead exige `ic_producao = 1` e data do contrato ou `dt_referencia` igual ou posterior à data de entrada do primeiro lead. Quando `dt_referencia` é mensal, a ordem exata entre lead e produção dentro do mesmo mês não fica identificada. É uma associação temporal, não uma prova de causalidade.
- Contratos são contados por `nu_contrato` distinto, região por UF, e o painel usa `vl_producao_total` quando o arquivo não traz `vl_liberado`.
- “Sem produção pós-lead” não significa perda comercial confirmada.

## Filtros do painel

Os filtros de período, origem, franqueado, loja, produto e região ficam na barra lateral. O período e a origem atualizam toda a visão; franqueado e loja limitam a visão financeira. Expanda a barra lateral para escolher as datas. O eixo temporal usa datas dd/mm e ajusta a frequência das marcações ao intervalo.

O agregado público usa o esquema 3 para suportar o detalhamento diário do período e as dimensões de loja/franqueado.
