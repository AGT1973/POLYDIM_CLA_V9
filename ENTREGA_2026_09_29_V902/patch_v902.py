import os
import glob

base_dir = r"E:\POLYDIM_EINSOF\ENTREGA_2026_09_29_V902"

for root, _, files in os.walk(base_dir):
    for f in files:
        if f.endswith('.py') or f.endswith('.md') or f.endswith('.rs') or f.endswith('.cpp'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8', errors='ignore') as file:
                content = file.read()
            
            # Reemplazar v902 por v902 case-insensitive
            new_content = content.replace('v902', 'v902').replace('V902', 'V902')
            
            if new_content != content:
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                print(f"Patched: {path}")
