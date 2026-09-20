import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

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

# CARTA DE TESTE
busca = "Charizard RC5"

print("=" * 70)
print("MINHA CAÇA POKÉMON - BUSCA REAL NO MYP")
print("BUSCANDO:", busca)
print("=" * 70)

params = {
    "ProdutoSearch[query]": busca,
    "ProdutoSearch[exibirSomenteVenda]": "1"
}

url = BASE + "/pokemon"

resposta = sessao.get(
    url,
    params=params,
    timeout=30
)

print("\nSTATUS:", resposta.status_code)
print("URL DA BUSCA:", resposta.url)
print("TAMANHO:", len(resposta.text))

if resposta.status_code != 200:
    raise Exception(
        f"MYP respondeu com status {resposta.status_code}"
    )

soup = BeautifulSoup(resposta.text, "html.parser")

print("\n" + "=" * 70)
print("PRODUTOS ENCONTRADOS")
print("=" * 70)

produtos = {}
total = 0

for link in soup.find_all("a", href=True):

    href = link.get("href", "")

    # Produtos individuais do MYP
    if "/pokemon/produto/" not in href:
        continue

    url_produto = urljoin(BASE, href)

    # Evita mostrar o mesmo produto várias vezes
    if url_produto in produtos:
        continue

    bloco = link

    # Sobe alguns níveis procurando o bloco completo do produto
    for _ in range(5):
        if bloco.parent:
            bloco = bloco.parent

    texto = bloco.get_text(" ", strip=True)

    # Só queremos resultados relacionados ao Charizard
    if "charizard" not in texto.lower() and "charizard" not in href.lower():
        continue

    total += 1

    produtos[url_produto] = texto

    print("\n" + "-" * 70)
    print("PRODUTO", total)
    print("LINK:", url_produto)
    print("TEXTO:")
    print(texto[:1200])

print("\n" + "=" * 70)
print("TOTAL DE PRODUTOS:", total)
print("=" * 70)

# Agora abre cada produto encontrado para procurar ofertas
for numero, (url_produto, texto_produto) in enumerate(
    produtos.items(), 1
):

    print("\n\n" + "#" * 70)
    print("ANALISANDO PRODUTO", numero)
    print(url_produto)
    print("#" * 70)

    try:

        pagina = sessao.get(
            url_produto,
            timeout=30
        )

        print("STATUS PRODUTO:", pagina.status_code)

        produto_soup = BeautifulSoup(
            pagina.text,
            "html.parser"
        )

        texto_completo = produto_soup.get_text(
            " ",
            strip=True
        )

        # Mostra trechos que contenham R$
        partes = []

        for elemento in produto_soup.find_all(
            ["div", "li", "tr", "article"]
        ):

            texto = elemento.get_text(
                " ",
                strip=True
            )

            if "R$" not in texto:
                continue

            # Evita blocos gigantes
            if len(texto) > 1000:
                continue

            if texto not in partes:
                partes.append(texto)

        print("\nPOSSÍVEIS OFERTAS:")

        if not partes:
            print("Nenhuma oferta identificada.")

        for i, parte in enumerate(partes[:30], 1):
            print(f"\nOFERTA/BLOCO {i}:")
            print(parte)

    except Exception as erro:
        print("ERRO AO ANALISAR PRODUTO:", repr(erro))

print("\n\nTESTE FINALIZADO")
