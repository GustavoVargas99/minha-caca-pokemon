import json
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}

session = requests.Session()
session.headers.update(HEADERS)

CONDICOES = ("NM", "SP", "MP", "DM")


def brl(v):
    return float(v.replace(".", "").replace(",", "."))


def carregar_cartas():
    html = INDEX.read_text(encoding="utf-8")
    m = re.search(r"const\s+cards\s*=\s*(\[.*?\]);\s*\n", html, re.S)
    if not m:
        raise RuntimeError("Não encontrei const cards=[...] no index.html")
    return json.loads(m.group(1))


def termos_busca(carta):
    nome = carta.get("name", "").strip()
    num = carta.get("num", "").strip()
    termos = [nome]
    # O número ajuda quando o nome sozinho devolve muitas versões.
    if num and re.search(r"\d", num):
        termos.insert(0, f"{nome} {num}")
    # Também tenta apenas o nome sem sufixos de coleção entre parênteses.
    simples = re.sub(r"\s*\([^)]*\)\s*", " ", nome).strip()
    if simples and simples not in termos:
        termos.append(simples)
    return list(dict.fromkeys(termos))


def buscar_links_myp(termo, limite=12):
    url = f"{BASE}/pokemon?ProdutoSearch%5Bquery%5D={quote_plus(termo)}&ProdutoSearch%5BexibirSomenteVenda%5D=1"
    r = session.get(url, timeout=35)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    for a in soup.select('a[href*="/pokemon/produto/"]'):
        href = a.get("href")
        if href:
            full = urljoin(BASE, href.split("?")[0])
            if full not in links:
                links.append(full)
        if len(links) >= limite:
            break
    return links


def extrair_anuncios(url):
    r = session.get(url, timeout=35)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    titulo = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1 = soup.find("h1")
    h1txt = h1.get_text(" ", strip=True) if h1 else ""
    texto = soup.get_text(" ", strip=True)

    # Captura condição seguida do preço. É a estrutura que já validamos no MYP.
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
    """Filtro conservador para evitar misturar artes/versões obviamente diferentes.

    A confirmação perfeita por imagem exige uma fonte de imagem consistente por anúncio.
    Por isso usamos nome + número quando disponíveis e guardamos os candidatos para auditoria.
    Reimpressões/idiomas com a mesma identificação continuam elegíveis.
    """
    alvo_nome = carta.get("name", "").lower()
    alvo_num = carta.get("num", "").lower()
    texto = (produto.get("titulo", "") + " " + produto.get("h1", "")).lower()

    pokemon = alvo_nome.split()[0] if alvo_nome else ""
    if pokemon and pokemon not in texto:
        return False

    nums = re.findall(r"\d+", alvo_nome + " " + alvo_num)
    nums_prod = set(re.findall(r"\d+", texto))
    # Se houver números específicos e algum aparecer no produto, ganha confiança.
    if nums and any(n in nums_prod for n in nums):
        return True
    # Para cartas sem numeração útil, aceita pelo nome e deixa marcado como candidato.
    palavras = [p for p in re.findall(r"[a-z0-9]+", alvo_nome) if len(p) > 2]
    return bool(palavras) and sum(p in texto for p in palavras) >= min(2, len(palavras))


def escolher(anuncios):
    por = {c: [] for c in CONDICOES}
    for a in anuncios:
        if a["condicao"] in por:
            por[a["condicao"]].append(a)
    for c in por:
        por[c].sort(key=lambda x: x["preco"])

    # Regra da coleção: entre NM e SP, vale o mais barato.
    principais = por["NM"] + por["SP"]
    principais.sort(key=lambda x: x["preco"])
    melhor = principais[0] if principais else None

    return {
        "melhor_nm_sp": melhor,
        "menor_por_condicao": {c: (por[c][0] if por[c] else None) for c in CONDICOES},
        "mp_dm_para_analisar": (por["MP"][:3] + por["DM"][:3]),
        "total_anuncios": sum(len(v) for v in por.values()),
    }


def processar(carta):
    links = []
    for termo in termos_busca(carta):
        try:
            for link in buscar_links_myp(termo):
                if link not in links:
                    links.append(link)
        except Exception as e:
            print("  busca falhou:", termo, e)
        if len(links) >= 15:
            break
        time.sleep(0.25)

    produtos = []
    anuncios = []
    for link in links[:15]:
        try:
            p = extrair_anuncios(link)
            if compatibilidade(carta, p):
                produtos.append({"url": p["url"], "titulo": p["titulo"], "h1": p["h1"]})
                anuncios.extend(p["anuncios"])
        except Exception as e:
            print("  produto falhou:", link, e)
        time.sleep(0.15)

    resultado = escolher(anuncios)
    resultado.update({
        "grupo": carta.get("group"),
        "nome": carta.get("name"),
        "numero": carta.get("num"),
        "imagem_referencia": carta.get("img"),
        "fonte_prioritaria": "MYP Cards",
        "produtos_compativeis": produtos,
    })
    return resultado


def main():
    cartas = carregar_cartas()
    print("=" * 72)
    print("MINHA CAÇA POKÉMON - ATUALIZAÇÃO GERAL MYP CARDS")
    print("Cartas no catálogo:", len(cartas))
    print("=" * 72)

    saida = {
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
        "regra": "Prioridade MYP; menor entre NM/SP; MP/DM separados para análise; mesma arte pode ser outra edição/idioma.",
        "cartas": []
    }

    for i, carta in enumerate(cartas, 1):
        print(f"[{i}/{len(cartas)}] {carta.get('name')} {carta.get('num', '')}")
        try:
            r = processar(carta)
            saida["cartas"].append(r)
            melhor = r.get("melhor_nm_sp")
            print("  ->", f"{melhor['condicao']} R$ {melhor['preco']:.2f}" if melhor else "sem NM/SP confirmado")
        except Exception as e:
            print("  ERRO:", e)
            saida["cartas"].append({
                "grupo": carta.get("group"), "nome": carta.get("name"), "numero": carta.get("num"),
                "erro": str(e), "melhor_nm_sp": None
            })

    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 72)
    print("precos.json atualizado.")


if __name__ == "__main__":
    main()
