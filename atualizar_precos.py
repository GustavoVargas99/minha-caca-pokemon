import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode, urljoin
import re
import time

BASE = "https://mypcards.com"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

sessao = requests.Session()
sessao.headers.update(headers)

# Busca ampla. Depois analisaremos cada produto individualmente.
params = {
    "ProdutoSearch[query]": "Charizard",
    "ProdutoSearch[exibirSomenteVenda]": "1"
}

url_busca = BASE + "/pokemon?" + urlencode(params)

print("=" * 70)
print("MINHA CAÇA POKÉMON - ANALISANDO PRODUTOS CHARIZARD")
print("=" * 70)

resposta = sessao.get(url_busca, timeout=30)
print("STATUS BUSCA:", resposta.status_code)

soup = BeautifulSoup(resposta.text, "html.parser")

links = []

for a in soup.find_all("a", href=True):
    href = a.get("href", "")

    if "/pokemon/produto/" in href:
        url = urljoin(BASE, href)

        if url not in links:
            links.append(url)

print("PRODUTOS ÚNICOS ENCONTRADOS:", len(links))
print()

# Primeiro vamos analisar no máximo 30 produtos.
for numero, url in enumerate(links[:30], 1):

    print("=" * 70)
    print("PRODUTO", numero)
    print("URL:", url)

    try:
        r = sessao.get(url, timeout=30)
        print("STATUS:", r.status_code)

        pagina = BeautifulSoup(r.text, "html.parser")

        titulo = pagina.title.get_text(" ", strip=True) if pagina.title else ""

        h1 = pagina.find("h1")
        h1_texto = h1.get_text(" ", strip=True) if h1 else ""

        texto = " ".join(pagina.stripped_strings)

        # procura informações que podem identificar nossa carta
        trechos = []

        termos = [
            "RC5",
            "RC5/83",
            "Generations",
            "Gerações",
            "Charizard"
        ]

        for termo in termos:
            pos = texto.lower().find(termo.lower())

            if pos != -1:
                inicio = max(0, pos - 180)
                fim = min(len(texto), pos + 350)

                trecho = texto[inicio:fim]

                if trecho not in trechos:
                    trechos.append(trecho)

        # preços encontrados na página
        precos = re.findall(
            r'R\$\s*[0-9\.\,]+',
            texto
        )

        # remove preços repetidos mantendo a ordem
        precos_unicos = []

        for preco in precos:
            if preco not in precos_unicos:
                precos_unicos.append(preco)

        print("TÍTULO:", titulo)
        print("H1:", h1_texto)

        print("PREÇOS ENCONTRADOS:", precos_unicos[:15])

        print("--- TRECHOS IMPORTANTES ---")

        if trechos:
            for trecho in trechos[:5]:
                print(trecho)
                print()
        else:
            print("Nenhum trecho relevante encontrado.")

        print()

        # pequena pausa para não bombardear o site
        time.sleep(0.3)

    except Exception as erro:
        print("ERRO AO ANALISAR:", erro)

print("=" * 70)
print("ANÁLISE FINALIZADA")
print("=" * 70)
