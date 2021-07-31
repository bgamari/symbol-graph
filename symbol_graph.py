#!/usr/bin/env python3

import subprocess
from typing import Dict, Iterator, NewType, Tuple, Callable
from pathlib import Path
import networkx as nx
import math

Symbol = NewType('Symbol', str)
Demangler = Callable[[Symbol], Symbol]

def to_dot(objfile: Path, demangle: Demangler, triple):
    print('digraph {')
    for src, dest in symbol_ref_edges(objfile, triple):
        src = encode_symbol(demangle(src))
        dest = encode_symbol(demangle(dest))
        print(f'  "{src}" -> "{dest}";')

    for sym, size in symbol_sizes(objfile, triple).items():
        sym = encode_symbol(demangle(sym))
        print(f'  "{sym}" [size={size} label="{sym}\\n{size} bytes"];')

    print('}')

def to_digraph(objfile: Path, demangle: Demangler, triple: str) -> nx.DiGraph:
    gr = nx.DiGraph()
    for src, dest in symbol_ref_edges(objfile, triple):
        src = encode_symbol(demangle(src))
        dest = encode_symbol(demangle(dest))
        gr.add_edge(src, dest)

    for sym, size in symbol_sizes(objfile, triple).items():
        sym = encode_symbol(demangle(sym))
        if sym in gr.nodes:
            gr.nodes[sym]['size'] = size

    return gr

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('object', type=argparse.FileType('r'), metavar='OBJFILE', help='object file')
    parser.add_argument('--dom-tree', type=str, metavar='SYMBOL', help='compute dominator tree')
    parser.add_argument('--triple', type=str, default='', metavar='TRIPLE', help='target toolchain platform prefix')
    args = parser.parse_args()

    demangle = demangle_rust

    to_dot(args.object.name, demangle, triple=args.triple)

    if args.dom_tree is not None:
        gr = to_digraph(args.object.name, demangle, triple=args.triple)
        n0 = args.dom_tree
        dom_tree = dominator_tree(gr, n0)
        from matplotlib import pyplot as pl
        max_size = max(*[n['size'] for n in gr.nodes.values()])
        pl.figure(figsize=(10,10))
        nx.draw_networkx(
            dom_tree,
            pos=nx.spring_layout(dom_tree, iterations=1000, k=5),
            edge_color='0.8',
            nodelist = [ n for n in dom_tree.nodes ],
            node_size = [ 100*gr.nodes[n]['size'] / max_size for n in dom_tree.nodes ],
            font_size=2,
            )
        pl.savefig('dom-tree.svg')

def dominator_tree(gr, n0):
    doms = nx.algorithms.dominance.immediate_dominators(gr, n0)
    tr = nx.DiGraph()
    for a,b in doms.items():
        tr.add_edge(a,b)

    return tr

def encode_symbol(sym: str) -> str:
    return sym.replace('"', '\\"')

def demangle_rust(sym: str) -> str:
    if sym.startswith('_ZN'):
        sym = sym[3:]
        parts = []
        while True:
            if sym[0] == '_':
                parts.append(sym)
                break
            elif not sym[0].isnumeric():
                parts.append(sym)
                break
            else:
                i = 1
                while sym[i].isnumeric() and i < len(sym):
                    i += 1
                
                n = int(sym[:i])
                sym = sym[i:]
                parts.append(sym[:n])
                sym = sym[n:]

        sym = '::'.join(parts[:-2])
        sym = sym.replace('$u20$', ' ')
        sym = sym.replace('$LT$', '<')
        sym = sym.replace('$GT$', '>')

    return sym # TODO

def symbol_sizes(obj: Path, triple: str='') -> Dict[Symbol, int]:
    nm = f'{triple}nm'
    out = subprocess.check_output([nm, '-S', obj], encoding='UTF-8')
    sizes = {}
    for line in out.split('\n'):
        parts = line.split(' ')
        if len(parts) == 4:
            size = int(parts[1], 16)
            symbol = parts[3]
            sizes[symbol] = size

    return sizes

def symbol_ref_edges(objfile: Path, triple: str='') -> Iterator[Tuple[Symbol, Symbol]]:
    objdump = f'{triple}objdump'
    out = subprocess.check_output([objdump, '-d', objfile], encoding='UTF-8')
    yield from parse_edges(out)

def parse_edges(asm: str) -> Iterator[Tuple[Symbol, Symbol]]:
    import re
    sym = None
    symbol_re = '([\w]+)'
    new_symbol_re = re.compile(f'[0-9a-f]+ <{symbol_re}>:')
    symbol_ref_re = re.compile(f'<{symbol_re}>')
    for line in asm.split('\n'):
        if m := new_symbol_re.match(line):
            sym = m.group(1)
        else:
            for ref in symbol_ref_re.findall(line):
                yield (sym, ref)

if __name__ == '__main__':
    main()

