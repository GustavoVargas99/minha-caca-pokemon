import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://mypcards.com"
INDEX = Path("index.html")
SAIDA = Path("precos.json")
CHECKPOINT = Path("precos_checkpoint.json")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
session = requests.Session()
session.headers.update(HEADERS)
CONDICOES = ("NM", "SP", "MP", "DM")

# Cada execução faz apenas um pequeno lote e termina.
LOTE = int(os.getenv("LOTE_CARTAS", "5"))
MAX_LINKS = 5
INTERVALO = 1.2
ultima_requisicao = 0.0

class BloqueioTemporario(RuntimeError):
    pass


def brl(v):
    return float(v.replace(".", "").replace(",", "."))


def requisitar(url):
    global ultima_requisicao
    espera = INTERVALO - (time.monotonic() - ultima_requisicao)
    if espera > 0:
        time.sleep(espera)
    try:
        r = session.get(url, timeout=20)
    finally:
        ultima_requisicao = time.monotonic()
    if r.status_code == 429:
        raise BloqueioTemporario("HTTP 429 do MYP Cards")
    r.raise_for_status()
    return r


def carregar_cartas():
    html = INDEX.read_text(encoding="utf-8")
    m = re.search(r"const\s+cards\s*=\s*(\[.*?\]);\s*\n", html, re.S)
    if not m:
        raise RuntimeError("Não encontrei const cards=[...] no index.html")
    return json.loads(m.group(1))


def chave_carta(carta):
    return "|".join(str(carta.get(k, "")).strip() for k in ("group", "name", "num", "img"))


def termos_busca(carta):
    nome = carta.get("name", "").strip()
    num = carta.get("num", "").strip()
    termos = []
    if num and re.search(r"\d", num):
        termos.append(f"{nome} {num}")
    termos.append(nome)
    simples = re.sub(r"\s*\([^)]*\)\s*", " ", nome).strip()
    if simples:
        termos.append(simples)
    return list(dict.fromkeys(t for t in termos if t))[:2]


def buscar_links_myp(termo):
    url = f"{BASE}/pokemon?ProdutoSearch%5Bquery%5D={quote_plus(termo)}&ProdutoSearch%5BexibirSomenteVenda%5D=1"
    soup = BeautifulSoup(requisitar(url).text, "html.parser")
    links = []
    for a in soup.select('a[href*="/pokemon/produto/"]'):
        href = a.get("href")
        if href:
            full = urljoin(BASE, href.split("?")[0])
            if full not in links:
                links.append(full)
        if len(links) >= MAX_LINKS:
            break
    return links


def extrair_anuncios(url):
    soup = BeautifulSoup(requisitar(url).text, "html.parser")
    titulo = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1 = soup.find("h1")
    h1txt = h1.get_text(" ", strip=True) if h1 else ""
    texto = soup.get_text(" ", strip=True)
    padrao = re.compile(r"\b(NM|SP|MP|DM)\b.{0,260}?R\$\s*([\d\.]+,\d{2})", re.I | re.S)
    anuncios = []
    for cond, preco in padrao.findall(texto):
        try:
            valor = brl(preco)
        except ValueError:
            continue
        if 0 < valor < 1000000:
            anuncios.append({"condicao": cond.upper(), "preco": valor, "url": url})
    return {"url": url, "titulo": titulo, "h1": h1txt, "anuncios": anuncios}


def compatibilidade(carta, produto):
    alvo_nome = carta.get("name", "").lower()
    alvo_num = carta.get("num", "").lower()
    texto = (produto.get("titulo", "") + " " + produto.get("h1", "")).lower()
    pokemon = alvo_nome.split()[0] if alvo_nome else ""
    if pokemon and pokemon not in texto:
        return False
    nums = re.findall(r"\d+", alvo_nome + " " + alvo_num)
    nums_prod = set(re.findall(r"\d+", texto))
    if nums and any(n in nums_prod for n in nums):
        return True
    palavras = [p for p in re.findall(r"[a-z0-9]+", alvo_nome) if len(p) > 2]
    return bool(palavras) and sum(p in texto for p in palavras) >= min(2, len(palavras))


def escolher(anuncios):
    por = {c: [] for c in CONDICOES}
    for a in anuncios:
        if a["condicao"] in por:
            por[a["condicao"]].append(a)
    for c in por:
        por[c].sort(key=lambda x: x["preco"])
    principais = sorted(por["NM"] + por["SP"], key=lambda x: x["preco"])
    return {
        "melhor_nm_sp": principais[0] if principais else None,
        "menor_por_condicao": {c: (por[c][0] if por[c] else None) for c in CONDICOES},
        "mp_dm_para_analisar": por["MP"][:3] + por["DM"][:3],
        "total_anuncios": sum(len(v) for v in por.values()),
    }


def processar(carta):
    links = []
    for termo in termos_busca(carta):
        for link in buscar_links_myp(termo):
            if link not in links:
                links.append(link)
        if len(links) >= MAX_LINKS:
            break

    produtos, anuncios = [], []
    for link in links[:MAX_LINKS]:
        p = extrair_anuncios(link)
        if compatibilidade(carta, p):
            produtos.append({"url": p["url"], "titulo": p["titulo"], "h1": p["h1"]})
            anuncios.extend(p["anuncios"])

    resultado = escolher(anuncios)
    resultado.update({
        "grupo": carta.get("group"), "nome": carta.get("name"), "numero": carta.get("num"),
        "imagem_referencia": carta.get("img"), "fonte_prioritaria": "MYP Cards",
        "produtos_compativeis": produtos,
    })
    return resultado


def carregar_progresso():
    for arq in (CHECKPOINT, SAIDA):
        if arq.exists():
            try:
                dados = json.loads(arq.read_text(encoding="utf-8"))
                if isinstance(dados.get("cartas"), list):
                    return dados
            except Exception:
                pass
    return {
        "atualizado_em": None,
        "regra": "Prioridade MYP; menor entre NM/SP; MP/DM separados para análise; mesma arte pode ser outra edição/idioma.",
        "cartas": []
    }


def salvar(dados, final=False):
    dados["atualizado_em"] = datetime.now(timezone.utc).isoformat()
    (SAIDA if final else CHECKPOINT).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    cartas = carregar_cartas()
    dados = carregar_progresso()
    prontas = {x.get("_chave") for x in dados["cartas"] if x.get("_chave")}
    pendentes = [c for c in cartas if chave_carta(c) not in prontas]

    print("=" * 72)
    print("MINHA CAÇA POKÉMON - ATUALIZAÇÃO EM LOTES")
    print(f"Total: {len(cartas)} | concluídas: {len(prontas)} | pendentes: {len(pendentes)} | lote: {LOTE}")
    print("=" * 72)

    feitas_agora = 0
    bloqueado = False
    for carta in pendentes[:LOTE]:
        chave = chave_carta(carta)
        print(f"Processando: {carta.get('name')} {carta.get('num', '')}")
        try:
            r = processar(carta)
        except BloqueioTemporario as e:
            print(f"MYP bloqueou temporariamente ({e}). Encerrando o lote sem esperar horas.")
            bloqueado = True
            break
        except Exception as e:
            print("Erro nesta carta; ela ficará pendente para outra execução:", e)
            continue

        r["_chave"] = chave
        dados["cartas"] = [x for x in dados["cartas"] if x.get("_chave") != chave]
        dados["cartas"].append(r)
        feitas_agora += 1
        melhor = r.get("melhor_nm_sp")
        print("  ->", f"{melhor['condicao']} R$ {melhor['preco']:.2f}" if melhor else "sem NM/SP confirmado")

    salvar(dados, final=False)
    concluidas = len({x.get("_chave") for x in dados["cartas"] if x.get("_chave")})
    print(f"Lote encerrado: {feitas_agora} nova(s) carta(s). Progresso: {concluidas}/{len(cartas)}.")

    if concluidas >= len(cartas):
        salvar(dados, final=True)
        if CHECKPOINT.exists():
            CHECKPOINT.unlink()
        print("TODAS AS CARTAS CONCLUÍDAS. precos.json publicado.")
    elif bloqueado:
        print("O próximo workflow retomará exatamente das pendentes.")
    else:
        print("Lote concluído normalmente. O próximo workflow continuará das pendentes.")


if __name__ == "__main__":
    main()
