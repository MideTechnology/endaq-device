The docs for this package can be found [here](https://mide-technology-endaq-device.readthedocs-hosted.com/en/latest/).

To locally build the [Sphinx](https://www.sphinx-doc.org) documentation from a clone of the repo:
1. `cd <repo root dir>`
2. `pip install -e .[docs]`
3. `pip install -r ./docs/requirements.txt`   
4. `sphinx-build -W -b html docs docs/_build`

Note: The documentation build conflicts with endaq-python; if you already have
endaq-python installed, it is easiest to work in a virtual environment (e.g., first using
`python -m venv <env dir>` followed by `<venv dir>\Scripts\activate` under Windows,
`source <venv dir>/bin/activate` under Linux/macOS). 
