#!/usr/bin/env python3
"""Robô do 2º turno — Eleições 2026.

Lê os arquivos OFICIAIS e DOCUMENTADOS do TSE (especificações EA20/EA14/EA15 em
tse.jus.br/eleicoes/arquivos) e publica `dados-2t/br.json` + `dados-2t/uf/*.json`
no schema que o painel entende (o mesmo formato do 1º turno + campos turno/modo/
pst/eventos/sit). Só stdlib (sem dependências).

Uso no dia 25/10 (a cada ~2 min via GitHub Actions; ver github-workflows/):
    python3 robo-2t/atualizar_2t.py --out dados-2t --municipios robo-2t/municipios

Teste hoje (usa arquivos REAIS do 1º turno como se fossem do 2º):
    python3 robo-2t/atualizar_2t.py --out /tmp/t2 --municipios robo-2t/municipios \\
        --e-pres 6257 --e-gov 6259 --sempre

Códigos de eleição do 2º turno NUNCA são chutados: resolvem em tempo real de
oficial/comum/config/ele-c.json (pleito ele2026, turno 2). Se o TSE ainda não
publicou (404) ou instável, mantém os arquivos anteriores e sai com status 0.
"""

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TSE = 'https://resultados.tse.jus.br'
BASE = TSE  # sobrescrito por --base (testes, espelhos)
CONFIG_URL = TSE + '/oficial/comum/config/ele-c.json'
UFS = ['AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS',
       'MT', 'PA', 'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC',
       'SE', 'SP', 'TO']
GOV_2T = ['AC', 'AM', 'DF', 'ES', 'RJ', 'RN', 'TO']  # mesmos do painel
UA = {'User-Agent': 'painel-eleicoes-2t/1.0 (robô de apuração; dados: TSE)'}


def log(*a):
    print(*a, flush=True)


def fetch(url, timeout=25):
    """Devolve (status, bytes|None). 404 = ainda não publicado."""
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return 'REDE', None


def fetch_retry(url, tentativas=3, timeout=25):
    for i in range(tentativas):
        st, body = fetch(url, timeout)
        if st == 200 and body:
            return body
        if st == 404:
            return None  # não publicado (ainda)
        log(f'  tentativa {i + 1} falhou ({st}); aguardando…')
        time.sleep(4 * (i + 1))
    return None


def num_int(x):
    try:
        return int(str(x or '0').strip() or 0)
    except ValueError:
        return 0


def num_pct(x):
    x = str(x or '0').strip()
    try:
        return float(x.replace('.', '').replace(',', '.') if ',' in x else (x or 0))
    except ValueError:
        return 0.0


def resolve_eleicoes(e_pres=None, e_gov=None):
    """Códigos do 2º turno via config oficial (nunca chutados)."""
    if e_pres and e_gov:
        return str(e_pres), str(e_gov)
    body = fetch_retry(BASE + '/oficial/comum/config/ele-c.json')
    if not body:
        raise SystemExit('ERRO: config do TSE inacessível (ele-c.json).')
    cfg = json.loads(body)
    ele2026 = None
    for pl in cfg.get('pl', []):
        if pl.get('c') == 'ele2026':
            ele2026 = pl
            break
    if not ele2026:
        raise SystemExit('ERRO: pleito ele2026 fora da config do TSE.')
    out = {}
    for office, chave in (('1', 'pres'), ('3', 'gov')):
        ach = [e['cd'] for e in ele2026.get('e', [])
               if e.get('t') == '2' and any(c.get('cd') == office
                                            for a in e.get('abr', [])
                                            for c in a.get('cp', []))]
        if not ach:
            raise SystemExit(f'ERRO: turno 2 p/ cargo {office} ainda fora da config.')
        out[chave] = ach[0]
    log(f"eleições 2T resolvidas: pres={out['pres']} gov={out['gov']}")
    return out['pres'], out['gov']


def ea_url(uf, cargo4, elecao, mun=None):
    nome = f'{uf}{mun or ""}-c{cargo4}-e{str(elecao).zfill(6)}-u.json'
    return f'{BASE}/oficial/ele2026/{elecao}/dados/{uf}/' + nome


def converte_cargo(ea, cargo_cd):
    """EA20 (1 cargo) -> {cands, tot} no schema do painel. Devolve None se inválido."""
    if not ea or ea.get('dv') == 'n':
        return None
    cargos = [c for c in ea.get('carg', []) if c.get('cd') == cargo_cd]
    if not cargos:
        return None
    c0 = cargos[0]
    cands, subjudice, anulados = [], 0, 0
    for agr in c0.get('agr', []):
        for par in agr.get('par', []):
            for c in par.get('cand', []):
                v = num_int(c.get('vap'))
                dvt = str(c.get('dvt') or '')
                anul = None
                if 'judic' in dvt.lower():
                    anul, subjudice = 'sub judice', subjudice + v
                elif dvt and dvt != 'Válido':
                    anul, anulados = 'anulada', anulados + v
                cand = {'sq': str(c.get('sqcand') or ''), 'nr': num_int(c.get('n')),
                        'nome': c.get('nmu') or c.get('nm') or '', 'p': par.get('sg') or '',
                        'v': v, 'st': c.get('st') or '', 'e': c.get('e') == 's'}
                if anul:
                    cand['anul'] = anul
                cands.append(cand)
    if not cands:
        return None
    cands.sort(key=lambda k: (-k['v'], k['nome']))
    vv, vb, tvn = num_int(ea.get('v', {}).get('vv')), num_int(ea.get('v', {}).get('vb')), num_int(ea.get('v', {}).get('tvn'))
    te, comp, abst = num_int(ea.get('e', {}).get('te')), num_int(ea.get('e', {}).get('c')), num_int(ea.get('e', {}).get('a'))
    if not comp:
        comp = vv + vb + tvn
    return {'cands': cands,
            'tot': {'aptos': te, 'comp': comp, 'abst': abst, 'brancos': vb, 'nulos': tvn,
                    'validos': vv, 'subjudice': subjudice, 'anulados': anulados}}


def pct_urnas(ea):
    return num_pct((ea.get('s') or {}).get('pst'))


def dt_tse(ea):
    return f"{ea.get('dg', '')} {ea.get('hg', '')}".strip()


def carrega_municipios(diretorio):
    out = {}
    for uf in UFS:
        p = os.path.join(diretorio, uf + '.json')
        try:
            with open(p, encoding='utf-8') as f:
                out[uf] = json.load(f)
        except FileNotFoundError:
            out[uf] = {}
    return out


def escreve(caminho, obj):
    tmp = caminho + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, caminho)


def purge_jsdelivr(slug, arquivos):
    if not slug:
        return
    for arq in arquivos:
        url = f'https://purge.jsdelivr.net/gh/{slug}@main/{arq}'
        try:
            req = urllib.request.Request(url, headers=UA)
            urllib.request.urlopen(req, timeout=15).read()
            log(f'  purge ok: {arq}')
        except Exception as e:
            log(f'  purge falhou (ok, expira sozinho): {arq} :: {e}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='dados-2t')
    ap.add_argument('--municipios', default='robo-2t/municipios')
    ap.add_argument('--dia', default='2026-10-25')
    ap.add_argument('--sempre', action='store_true')
    ap.add_argument('--e-pres', default=None, help='override p/ teste (ex. 6257)')
    ap.add_argument('--e-gov', default=None)
    ap.add_argument('--base', default=TSE, help='base dos arquivos (padrão: TSE oficial)')
    ap.add_argument('--purge', default=os.environ.get('REPO_SLUG', ''))
    args = ap.parse_args()

    hoje = datetime.date.today().isoformat()
    if hoje != args.dia and not args.sempre:
        log(f'hoje é {hoje}; robô agenda p/ {args.dia} (use --sempre p/ forçar). Nada a fazer.')
        return 0

    global BASE
    BASE = args.base.rstrip('/')

    try:
        e_pres, e_gov = resolve_eleicoes(args.e_pres, args.e_gov)
    except SystemExit as e:
        log(e)
        return 0  # turno 2 ainda não configurado: saída limpa, tenta de novo no próximo ciclo

    os.makedirs(os.path.join(args.out, 'uf'), exist_ok=True)
    municipios = carrega_municipios(args.municipios)
    agora = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # --- presidente BR + UFs ---
    br_ea = fetch_retry(ea_url('br', '0001', e_pres))
    if not br_ea:
        log('presidente/BR ainda não publicado. Mantendo arquivos anteriores.')
        return 0
    br = json.loads(br_ea)
    pres_br = converte_cargo(br, '1')
    if not pres_br or len(pres_br['cands']) != 2:
        log('presidente/BR inválido (esperava 2 candidatos). Mantendo anteriores.')
        return 0
    tv = num_int(br.get('v', {}).get('tv'))
    if tv and tv != pres_br['tot']['validos'] + pres_br['tot']['brancos'] + pres_br['tot']['nulos']:
        log('AVISO: tv != vv+vb+tvn no BR (segue mesmo assim).')

    uf_pres, publicados = {}, 0
    for uf in UFS:
        body = fetch_retry(ea_url(uf.lower(), '0001', e_pres))
        if not body:
            log(f'  {uf}/pres: ainda não publicado (mantém anterior, se houver)')
            continue
        conv = converte_cargo(json.loads(body), '1')
        if not conv:
            continue
        uf_pres[uf] = {'cands': conv['cands'], 'tot': conv['tot'], 'pst': pct_urnas(json.loads(body))}
        publicados += 1
    log(f'presidente: {publicados}/27 UFs')

    # --- governadores 2T ---
    uf_gov = {}
    for uf in GOV_2T:
        body = fetch_retry(ea_url(uf.lower(), '0003', e_gov))
        if not body:
            log(f'  {uf}/gov: ainda não publicado')
            continue
        ea = json.loads(body)
        conv = converte_cargo(ea, '3')
        if not conv:
            continue
        uf_gov[uf] = {'cands': conv['cands'], 'tot': conv['tot'], 'pst': pct_urnas(ea)}

    # --- monta br.json ---
    uf_resumo = {}
    for uf in UFS:
        r = {}
        if uf in uf_pres:
            r['1'] = {'cands': uf_pres[uf]['cands'], 'tot': uf_pres[uf]['tot'],
                      'vagas': 1, 'pst': uf_pres[uf]['pst'], 'hora': dt_tse(br), 'sit': {}}
        if uf in uf_gov:
            r['3'] = {'cands': uf_gov[uf]['cands'], 'tot': uf_gov[uf]['tot'],
                      'vagas': 1, 'pst': uf_gov[uf]['pst'], 'hora': dt_tse(br), 'sit': {}}
        if r:
            uf_resumo[uf] = r
    brout = {'turno': 2, 'modo': '2t', 'gerado': agora, 'dt_tse': dt_tse(br),
             'pst': pct_urnas(br),
             'presidente': {'cands': pres_br['cands'], 'tot': pres_br['tot'], 'sit': {}},
             'uf': uf_resumo, 'eventos': []}
    escreve(os.path.join(args.out, 'br.json'), brout)

    # --- monta uf/*.json (nível UF; sem detalhe municipal na v1 — ver README) ---
    gerados = []
    for uf in UFS:
        cargos = {}
        if uf in uf_pres:
            cargos['1'] = {'cands': uf_pres[uf]['cands'], 'tot': uf_pres[uf]['tot'],
                           'vagas': 1, 'pst': uf_pres[uf]['pst'], 'hora': dt_tse(br),
                           'sit': {}, 'mun': {}}
        if uf in uf_gov:
            cargos['3'] = {'cands': uf_gov[uf]['cands'], 'tot': uf_gov[uf]['tot'],
                           'vagas': 1, 'pst': uf_gov[uf]['pst'], 'hora': dt_tse(br),
                           'sit': {}, 'mun': {}}
        if not cargos:
            continue
        escreve(os.path.join(args.out, 'uf', uf + '.json'),
                {'uf': uf, 'turno': 2, 'municipios': municipios.get(uf, {}), 'cargos': cargos})
        gerados.append(f'dados-2t/uf/{uf}.json')
    log(f'UFs gravadas: {len(gerados)} | dt_tse={dt_tse(br)} | pst={pct_urnas(br)}')
    purge_jsdelivr(args.purge, ['dados-2t/br.json'] + gerados)
    return 0


if __name__ == '__main__':
    sys.exit(main())
