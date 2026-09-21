from pathlib import Path
import nbformat
from nbclient import NotebookClient
from nbconvert import HTMLExporter

root=Path(__file__).resolve().parent
for name in ['01_assortment','02_clients']:
    path=root/'reports'/(name+'.ipynb')
    nb=nbformat.read(path,as_version=4)
    NotebookClient(nb,timeout=600,kernel_name='python3',resources={'metadata':{'path':str(root)}}).execute()
    nbformat.write(nb,path)
    exporter=HTMLExporter(template_name='lab')
    exporter.exclude_input_prompt=True
    exporter.exclude_output_prompt=True
    body,_=exporter.from_notebook_node(nb)
    (root/'reports'/(name+'.html')).write_text(body,encoding='utf-8')
    print(name,'executed and exported',flush=True)
