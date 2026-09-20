import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode

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

buscas = [
    "Charizard",
    "RC5",
    "RC5/83",
    "Charizard RC5",
    "Charizard Generations",
]

print("=" * 70)
print("MINHA CAÇA POKÉMON - TESTANDO FORMAS DE BUSCA NO MYP")
print("=" * 70)

for termo in buscas:

    params = {
        "ProdutoSearch[query]": termo,
        "ProdutoSearch[exibirSomenteVenda]": "1"
    }

    url = BASE + "/pokemon?" + urlencode(params)

    print()
    print("=" * 70)
    print("BUSCANDO:", termo)
    print("URL:", url)
    print("=" * 70)

    resposta = sessao.get(url, timeout=30)
    print("STATUS:", resposta.status_code)

    soup = BeautifulSoup(resposta.text, "html.parser")

    encontrados = []

    for link in soup.find_all("a", href=True):

        href = link.get("href", "")
        texto = " ".join(link.stripped_strings)

        if "/pokemon/produto/" not in href:
            continue

        bloco = link.parent
        texto_bloco = " ".join(bloco.stripped_strings) if bloco else texto

        encontrados.append({
            "texto": texto,
            "link": href,
            "bloco": texto_bloco[:500]
        })

    # remove links repetidos
    unicos = {}
    for item in encontrados:
        unicos[item["link"]] = item

    encontrados = list(unicos.values())

    print("PRODUTOS ENCONTRADOS:", len(encontrados))

    for numero, item in enumerate(encontrados[:15], 1):
        print()
        print("RESULTADO", numero)
        print("TEXTO:", item["texto"])
        print("LINK:", item["link"])
        print("BLOCO:", item["bloco"])

print()
print("=" * 70)
print("TESTE FINALIZADO")
print("=" * 70)
