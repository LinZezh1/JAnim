# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'JAnim'
copyright = '2023, jkjkil4'
author = 'jkjkil4'
release = '0.0.1'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ['sphinx.ext.autodoc']
autodoc_member_order = 'bysource'
# autodoc_default_flags = ['members', 'show-inheritance']

templates_path = ['_templates']
exclude_patterns = []

language = 'zh_CN'

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
html_static_path = ['_static']
html_css_files = [
    'custom.css',
    'colors.css'
]

sys.path.insert(0, os.path.abspath('../..'))


doc_src_path = os.path.dirname(__file__)
janim_path = os.path.abspath(os.path.join(doc_src_path, '../../janim'))


generate_autodoc_exclude = ['janim.constants']
force_generate_autodoc = False


def generate_autodoc(local_path: str, module_path: str) -> bool:
    if module_path in generate_autodoc_exclude:
        return False

    search_path = os.path.join(janim_path, local_path)
    rst_path = os.path.join(doc_src_path, 'janim', local_path)
    lst = os.listdir(search_path)

    generated_dirs = []
    generated_files = []

    for filename in lst:
        sub_path = os.path.join(search_path, filename)

        if os.path.isdir(sub_path):
            if generate_autodoc(os.path.join(local_path, filename), f'{module_path}.{filename}'):
                generated_dirs.append(filename)

        elif os.path.isfile(sub_path):
            if filename.endswith('.py'):
                name = filename[:-3]
                module_name = f'{module_path}.{name}'
                rst_file_path = os.path.join(rst_path, f'{name}.rst')

                os.makedirs(rst_path, exist_ok=True)

                if not force_generate_autodoc and os.path.exists(rst_file_path):
                    print('Exists:\t', module_name)
                else:
                    with open(rst_file_path, 'w') as f:
                        f.write(
                            f'{name}\n'
                            f'{"=" * len(name)}\n'
                            '\n'
                            f'.. automodule:: {module_name}\n'
                            '   :members:\n'
                            '   :undoc-members:\n'
                            '   :show-inheritance:\n\n'
                        )
                    print('Generated:\t', module_name)

                generated_files.append(name)

        else:
            raise Exception(f'{sub_path} is not available')

    if generated_dirs or generated_files:
        with open(os.path.join(rst_path, 'modules.rst'), 'w') as f_modules:
            try:
                name = module_path[module_path.index('.') + 1:]
            except ValueError:
                name = module_path

            f_modules.write(
                f'{name}\n'
                f'{"=" * len(name)}\n'
                '\n'
                '.. toctree::\n'
                '   :maxdepth: 1\n\n'
            )

            for dir in generated_dirs:
                f_modules.write(f'   {dir}/modules.rst\n')

            for file in generated_files:
                f_modules.write(f'   {file}\n')

        return True

    return False


generate_autodoc('', 'janim')
