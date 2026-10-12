# Robô do 2º turno — Eleições 2026

Independência total da fonte original: este robô lê os **arquivos oficiais e
documentados do TSE** (especificações EA20 em `tse.jus.br/eleicoes/arquivos`;
padrão confirmado em produção por terceiros) e publica `dados-2t/br.json` +
`dados-2t/uf/*.json` **no schema que o painel já entende** — nenhum código do
site precisa mudar. Só stdlib do Python (zero dependências).

## Como funciona

1. Resolve os códigos da eleição do 2º turno em tempo real via
   `resultados.tse.jus.br/oficial/comum/config/ele-c.json` (pleito `ele2026`,
   turno 2). **Nenhum código é chutado**: se o TSE ainda não publicou, o robô
   mantém os arquivos anteriores e sai limpo (exit 0).
2. Baixa EA20 de presidente/BR + presidente/UF (27) + governador/UF (AC, AM,
   DF, ES, RJ, RN, TO) com retry e backoff (o TSE caiu ~1h no 1º turno).
3. Converte para o schema do painel (`sq/nr/nome/p/v/st/e`, `tot` com
   aptos/comp/abst/brancos/nulos/validos/subjudice/anulados, `pst`, `sit:{}`).
4. Valida (2 candidatos a presidente; `tv == vv+vb+tvn` com aviso) e grava de
   forma atômica. Dá purge no jsDelivr (melhor esforço).

## Instalação (5 min, uma vez)

Esta pasta já é a raiz do repositório do site, então o workflow já está no
lugar certo: `.github/workflows/apuracao-2t.yml`. Falta só:

1. Subir tudo para um repositório no GitHub e conectar na hospedagem
   (Netlify ou Cloudflare Pages, **via Git** — não por arrastar arquivos,
   senão o robô nunca agenda).
2. Conferir no `site-config.js` que `fontes.tempoReal` vale `"dados-2t/"`
   (padrão: o próprio espelho, mesma origem, sem CORS e sem depender de
   ninguém; o feed original entra sozinho como reserva automática).
3. No dia 25/10 o cron assume sozinho (a cada 2 min). Fora do dia, use o
   botão **Run workflow** ou `--sempre` para testar.

> `netlify.toml` na raiz evita rebuild a cada commit de dados (o painel lê
> os JSON ao vivo; rebuild só quando o resto muda). Na Cloudflare Pages o
> limite (500 builds/mês) comporta a noite inteira (~150 builds).

## Teste hoje (sem esperar o dia 25)

```bash
# usa arquivos REAIS do 1º turno como se fossem do 2º e valida o schema:
python3 robo-2t/atualizar_2t.py --out /tmp/t2 --municipios robo-2t/municipios \
    --e-pres 6257 --e-gov 6259 --sempre
```

## Limites honestos da v1

- **Sem detalhe municipal no 2º turno** (seriam 5.570 arquivos por ciclo):
  o mapa e o painel operam por UF; o drill-down de município cai de volta
  para a visão da UF (o site já trata isso sem erro).
- **Sem projeções matemáticas nem posts do X**: `sit` sai vazio e `eventos`
  vazio — valem os selos declarados pelo TSE (`eleito`) e a manchete padrão.
  Nada é inventado: o que não há dado, não há selo.
- `municipios/` é um snapshot de nomes (não muda entre turnos); se a fonte
  original sair do ar, o snapshot local continua valendo.

## Licenças

- Dados: Creative Commons Atribuição (TSE/AGEL — fonte oficial).
- Código deste robô: MIT.
