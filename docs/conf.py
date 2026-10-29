from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.abspath('..'))

project = 'SentientOS'

# Bound concurrent external requests during strict CI link validation.
linkcheck_workers = 2

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx_autodoc_typehints',
    'myst_parser',
]

html_theme = 'sphinxawesome_theme'

source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}

autodoc_default_options = {
    'members': True,
    'undoc-members': True,
    'show-inheritance': True,
}

napoleon_google_docstring = True
napoleon_numpy_docstring = True
