import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime

URL = "https://mypcards.com/pokemon/produto/36248/charizard"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

print("=" * 70)
print("MINHA CAÇA POKÉMON - CHARIZARD RC5/RC32")
print("=" * 70)

resposta = requests.get(URL, headers=headers, timeout=30)

print("STATUS:", resposta.status_code)
print("URL:", URL)

soup = BeautifulSoup(resposta.text, "html.parser")

titulo = soup.find("h1")
titulo = titulo.get_text(" ", strip=True) if titulo else "Charizard"

print("CARTA:", titulo)
print()

# Procura blocos da página que contenham condição e preço
resultados = []

for elemento in soup.find_all(["div", "li", "tr"]):

    texto = " ".join(elemento.stripped_strings)

    if not texto:
        continue

    condicoes = re.findall(
        r'(?<![A-Za-z])(NM|SP|MP|HP|DM)(?![A-Za-z])',
        texto,
        flags=re.IGNORECASE
    )

    precos = re.findall(
        r'R\$\s*[0-9\.]+,[0-9]{2}',
        texto
    )

    if condicoes and precos:

        condicao = condicoes[0].upper()

        for preco in precos:

            valor = preco.replace("R$", "").strip()
            valor = valor.replace(".", "").replace(",", ".")

            try:
                valor_float = float(valor)
            except:
                continue

            # evita lixo óbvio da página
            if valor_float <= 0 or valor_float > 100000:
                continue

            resultados.append({
                "condicao": condicao,
                "preco": valor_float
            })

# Remove duplicações exatas
unicos = []

for item in resultados:
    if item not in unicos:
        unicos.append(item)

resultados = unicos

print("ANÚNCIOS IDENTIFICADOS:")
print()

for item in resultados:
    print(
        item["condicao"],
        "- R$",
        f'{item["preco"]:.2f}'.replace(".", ",")
    )

print()
print("=" * 70)

# Agrupa por condição
por_condicao = {}

for item in resultados:
    condicao = item["condicao"]

    if condicao not in por_condicao:
        por_condicao[condicao] = []

    por_condicao[condicao].append(item["preco"])

print("RESUMO POR CONSERVAÇÃO:")
print()

resumo = {}

for condicao in ["DM", "HP", "MP", "SP", "NM"]:

    valores = por_condicao.get(condicao, [])

    if valores:

        valores = sorted(valores)

        minimo = min(valores)
        media = sum(valores) / len(valores)
        maximo = max(valores)

        resumo[condicao] = {
            "menor": round(minimo, 2),
            "media": round(media, 2),
            "maior": round(maximo, 2),
            "quantidade": len(valores)
        }

        print(
            condicao,
            "| menor: R$",
            f"{minimo:.2f}".replace(".", ","),
            "| média: R$",
            f"{media:.2f}".replace(".", ","),
            "| maior: R$",
            f"{maximo:.2f}".replace(".", ","),
            "| anúncios:",
            len(valores)
        )

print()
print("=" * 70)

# Cria arquivo que depois será lido pelo site
dados = {
    "carta": "Charizard RC5/RC32",
    "fonte": "MYP Cards",
    "url": URL,
    "atualizado_em": datetime.now().isoformat(),
    "precos": resumo
}

with open("precos.json", "w", encoding="utf-8") as arquivo:
    json.dump(
        dados,
        arquivo,
        ensure_ascii=False,
        indent=2
    )

print("Arquivo precos.json criado.")
print("ATUALIZAÇÃO CONCLUÍDA")
print("=" * 70)
