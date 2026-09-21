import json,re
from pathlib import Path
p=Path('index.html'); html=p.read_text(encoding='utf-8')
m=re.search(r'const\s+cards\s*=\s*(\[.*?\]);\s*\n',html,re.S)
if not m: raise SystemExit('cards nao encontrado')
cards=json.loads(m.group(1)); dados=json.loads(Path('precos.json').read_text(encoding='utf-8'))
precos=dados.get('precos_confirmados',{})
for c in cards:
    key=f"{c.get('group','')}|{c.get('name','')}|{c.get('num','')}"
    d=precos.get(key)
    if d:
        c['price']=float(d['preco']); c['status']='verificado'
        extras=[d.get('fonte',''),d.get('condicao',''),'Foil' if d.get('foil') else '',d.get('nota','')]
        c['note']=' • '.join(x for x in extras if x)
novo='const cards='+json.dumps(cards,ensure_ascii=False)+';\n'
html=html[:m.start()]+novo+html[m.end():]
html=re.sub(r'atualizado em \d{2}/\d{2}/\d{4}','atualizado em 21/09/2026',html)
p.write_text(html,encoding='utf-8')
print('Precos aplicados ao site')
