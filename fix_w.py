import os
file_path = r'E:\POLYDIM_EINSOF\ENTREGA_2026_09_30_V908\polydim_v908_monolito.py'
with open(file_path, 'r', encoding='utf-8') as f: content = f.read()
content = content.replace("name.encode('utf-8')", "name")
with open(file_path, 'w', encoding='utf-8') as f: f.write(content)
