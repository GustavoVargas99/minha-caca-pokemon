import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urljoin, parse_qs, urlparse, unquote

import requests
from bs4 import BeautifulSoup

BASE = "https://mypcards.com"
INDEX = Path("index.html")
SAIDA = Path("precos.json")
CHECKPOINT = Path("precos_checkpoint.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}
session = requests.Session()
session.headers.update(HEADERS)
CONDICOES = ("NM", "SP", "MP", "DM")
LOTE = int(os.getenv("LOTE_CARTAS", "5"))
MAX_LINKS = 5
INTERVALO = 1.0
ultima_requisicao = 0.0

class BloqueioTemporario(RuntimeError):
    pass


def brl(v):
    return float(v.replace(".", "").replace(",", "."))


def requisitar(url, timeout=20):
    global ultima_requisicao
    espera = INTERVALO - (time.monotonic() - ultima_requisicao)
    if espera > 0:
        time.sleep(espera)
    try:
        r = session.get(url, timeout=timeout, allow_redirects=True)
    finally:
        ultima_requisicao = time.monotonic()
    if r.status_code == 429:
        raise BloqueioTemporario("HTTP 429")
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


def numero_carta(carta):
    texto = f"{carta.get('name','')} {carta.get('num','')}"
    # Prioriza padrões de colecionador como SV107/SV122, RC5/RC32, 025/113.
    achados = re.findall(r"(?:[A-Z]{0,4}\d{1,4})/(?:[A-Z]{0,4}\d{1,4})", texto, re.I)
    return achados[0] if achados else ""


def termos_busca(carta):
    nome = carta.get("name", "").strip()
    num = numero_carta(carta)
    nome_sem_codigo = re.sub(r"\s+(?:[A-Z]{0,4}\d{1,4})/(?:[A-Z]{0,4}\d{1,4}).*$", "", nome, flags=re.I).strip()
    termos = []
    if num:
        termos.append(f"{nome_sem_codigo} {num}")
        # MYP às vezes normaliza SV107/SV122 para 107/122.
        simplificado = re.sub(r"[A-Za-z]", "", num)
        if simplificado != num:
            termos.append(f"{nome_sem_codigo} {simplificado}")
    termos.append(nome_sem_codigo or nome)
    return list(dict.fromkeys(t for t in termos if t))[:3]


def limpar_link_busca(href):
    if not href:
        return None
    if href.startswith("//"):
        href = "https:" + href
    # DuckDuckGo encapsula o destino em uddg.
    if "duckduckgo.com/l/?" in href:
        q = parse_qs(urlparse(href).query)
        href = unquote(q.get("uddg", [""])[0])
    if href.startswith("/"):
        href = urljoin(BASE, href)
    if re.match(r"https?://(?:www\.)?mypcards\.com/pokemon/produto/\d+/", href, re.I):
        return href.split("?")[0].split("#")[0]
    return None


def buscar_links_myp_direto(termo):
    urls = [
        f"{BASE}/pokemon?ProdutoSearch%5Bquery%5D={quote_plus(termo)}&ProdutoSearch%5BexibirSomenteVenda%5D=1",
        f"{BASE}/pokemon?ProdutoSearch%5Bquery%5D={quote_plus(termo)}",
    ]
    links = []
    for url in urls:
        try:
            soup = BeautifulSoup(requisitar(url).text, "html.parser")
        except Exception:
            continue
        for a in soup.find_all("a", href=True):
            full = limpar_link_busca(urljoin(BASE, a["href"]))
            if full and full not in links:
                links.append(full)
            if len(links) >= MAX_LINKS:
                return links
    return links


def buscar_links_myp_web(termo):
    # Fallback: usa índice público de busca apenas para descobrir a URL do produto;
    # preço/condição continuam sendo lidos diretamente da página MYP Cards.
    consultas = [
        f'site:mypcards.com/pokemon/produto "{termo}"',
        f'site:mypcards.com/pokemon/produto {termo}',
    ]
    links = []
    for consulta in consultas:
        url = "https://html.duckduckgo.com/html/?q=" + quote_plus(consulta)
        try:
            soup = BeautifulSoup(requisitar(url).text, "html.parser")
        except Exception:
            continue
        for a in soup.find_all("a", href=True):
            full = limpar_link_busca(a["href"])
            if full and full not in links:
                links.append(full)
            if len(links) >= MAX_LINKS:
                return links
    return links


def buscar_links_myp(termo):
    links = buscar_links_myp_direto(termo)
    if not links:
        links = buscar_links_myp_web(termo)
    return links[:MAX_LINKS]


def extrair_anuncios(url):
    soup = BeautifulSoup(requisitar(url).text, "html.parser")
    titulo = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1 = soup.find("h1")
    h1txt = h1.get_text(" ", strip=True) if h1 else ""
    texto = soup.get_text(" ", strip=True)

    anuncios = []
    # Captura condição seguida do primeiro preço próximo. Tolera observações entre ambos.
    padrao = re.compile(r"(?:^|\s)(NM|SP|MP|DM)(?:\s|$)(.{0,180}?)R\$\s*([\d\.]+,\d{2})", re.I | re.S)
    for cond, detalhe, preco in padrao.findall(texto):
        try:
            valor = brl(preco)
        except ValueError:
            continue
        if 0 < valor < 1000000:
            anuncios.append({
                "condicao": cond.upper(),
                "preco": valor,
                "url": url,
                "detalhe": re.sub(r"\s+", " ", detalhe).strip()[:120],
            })

    # Remove duplicatas causadas pelo HTML responsivo da página.
    unicos = []
    vistos = set()
    for a in anuncios:
        k = (a["condicao"], a["preco"], a["detalhe"])
        if k not in vistos:
            vistos.add(k)
            unicos.append(a)
    return {"url": url, "titulo": titulo, "h1": h1txt, "texto": texto[:2500], "anuncios": unicos}


def compatibilidade(carta, produto):
    alvo_nome = carta.get("name", "").lower()
    texto = (produto.get("titulo", "") + " " + produto.get("h1", "")).lower()
    pokemon = alvo_nome.split()[0] if alvo_nome else ""
    if pokemon and pokemon not in texto:
        return False

    num = numero_carta(carta).lower()
    if num:
        nums_alvo = re.findall(r"\d+", num)
        nums_prod = re.findall(r"\d+", texto)
        # Para número X/Y, exige os dois números na página/título.
        if len(nums_alvo) >= 2 and all(n in nums_prod for n in nums_alvo[:2]):
            return True

    palavras = [p for p in re.findall(r"[a-z0-9]+", alvo_nome) if len(p) > 2 and not p.isdigit()]
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
    termos = termos_busca(carta)
    print("  buscas:", " | ".join(termos))
    for termo in termos:
        encontrados = buscar_links_myp(termo)
        for link in encontrados:
            if link not in links:
                links.append(link)
        if len(links) >= MAX_LINKS:
            break
    print(f"  links MYP encontrados: {len(links)}")

    produtos, anuncios = [], []
    for link in links[:MAX_LINKS]:
        try:
            p = extrair_anuncios(link)
        except Exception as e:
            print("  falha ao abrir produto:", e)
            continue
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
    return {"atualizado_em": None, "regra": "Prioridade MYP; menor entre NM/SP; MP/DM separados para análise; mesma arte pode ser outra edição/idioma.", "cartas": []}


def salvar(dados, final=False):
    dados["atualizado_em"] = datetime.now(timezone.utc).isoformat()
    (SAIDA if final else CHECKPOINT).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    cartas = carregar_cartas()
    dados = carregar_progresso()
    # Resultado sem produto e sem anúncio NÃO conta como concluído: será tentado novamente.
    prontas = {x.get("_chave") for x in dados["cartas"] if x.get("_chave") and (x.get("produtos_compativeis") or x.get("total_anuncios", 0) > 0)}
    dados["cartas"] = [x for x in dados["cartas"] if x.get("_chave") in prontas]
    pendentes = [c for c in cartas if chave_carta(c) not in prontas]

    print("=" * 72)
    print("MINHA CAÇA POKÉMON - ATUALIZAÇÃO EM LOTES")
    print(f"Total: {len(cartas)} | válidas: {len(prontas)} | pendentes: {len(pendentes)} | lote: {LOTE}")
    print("=" * 72)

    feitas_agora = 0
    for carta in pendentes[:LOTE]:
        chave = chave_carta(carta)
        print(f"Processando: {carta.get('name')} {carta.get('num', '')}")
        try:
            r = processar(carta)
        except BloqueioTemporario as e:
            print(f"Bloqueio temporário ({e}). Encerrando sem travar.")
            break
        except Exception as e:
            print("Erro nesta carta; ficará pendente:", e)
            continue

        if not r.get("produtos_compativeis") and r.get("total_anuncios", 0) == 0:
            print("  -> nenhum produto confirmado; NÃO será marcada como concluída")
            continue

        r["_chave"] = chave
        dados["cartas"] = [x for x in dados["cartas"] if x.get("_chave") != chave]
        dados["cartas"].append(r)
        feitas_agora += 1
        melhor = r.get("melhor_nm_sp")
        print("  ->", f"{melhor['condicao']} R$ {melhor['preco']:.2f}" if melhor else f"produto confirmado; {r['total_anuncios']} anúncio(s)")

    salvar(dados, final=False)
    concluidas = len({x.get("_chave") for x in dados["cartas"] if x.get("_chave")})
    print(f"Lote encerrado: {feitas_agora} confirmada(s). Progresso válido: {concluidas}/{len(cartas)}.")
    if concluidas >= len(cartas):
        salvar(dados, final=True)
        if CHECKPOINT.exists(): CHECKPOINT.unlink()
        print("TODAS AS CARTAS CONCLUÍDAS. precos.json publicado.")
    else:
        print("Próxima execução tentará novamente apenas as pendentes.")

if __name__ == "__main__":
    main()
